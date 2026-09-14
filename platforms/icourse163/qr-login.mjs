// QR 登录：打开二维码并持续刷新截图，检测扫码成功（会话存入 profile 供 runner 使用）
// 收编自 workspace/default/mooc-runner/qr-login.mjs（2026-09-12 实战版本）。
// 实测要点（详见 knowledge/icourse163.md §5）：
//   - 成功判定必须用 window.webUser（登录按钮可见性会误判）
//   - 二维码过期检测必须匹配「已失效/已过期」，裸「刷新」文本会误伤常驻按钮
//   - 短信验证码通道会触发易盾滑块，扫码是首选登录方式
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROFILE_DIR = process.env.MOOC_PROFILE_DIR || path.join(__dirname, 'edge-profile');

const log = (m) => { const l = `[${new Date().toISOString()}] ${m}`; console.log(l); fs.appendFileSync(path.join(__dirname, 'runner.log'), l + '\n'); };

const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
  channel: 'msedge', headless: true, viewport: { width: 1280, height: 800 },
});
const page = ctx.pages()[0] || await ctx.newPage();
await page.goto('https://www.icourse163.org/', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);
await page.getByRole('button', { name: '登录/注册' }).click();
await page.waitForTimeout(2000);
// 点底部「手机扫码，安全登录」（最小文本元素精确匹配）
const qrClicked = await page.evaluate(() => {
  const cands = Array.from(document.querySelectorAll('div, span, a, i'))
    .filter(e => {
      const t = (e.textContent || '').trim();
      return e.offsetParent !== null && t.length > 0 && t.length < 20 && /手机扫码/.test(t);
    });
  if (!cands.length) return 'NOT_FOUND';
  cands.sort((a, b) => (a.textContent.length - b.textContent.length) ||
    (a.querySelectorAll('*').length - b.querySelectorAll('*').length));
  const el = cands[0];
  (el.closest('a') || el).click();
  return 'clicked:' + el.tagName + ':' + (el.className || '').toString().slice(0, 25);
});
log('qr tab clicked: ' + qrClicked);
await page.waitForTimeout(2500);

// 找二维码元素（模态内可见的近方形 img/canvas）
const findQr = async () => {
  for (const f of page.frames()) {
    const info = await f.evaluate(() => {
      const cands = [];
      for (const e of document.querySelectorAll('img, canvas')) {
        const r = e.getBoundingClientRect();
        if (r.width >= 90 && r.width <= 400 && Math.abs(r.width - r.height) < 30 && e.offsetParent !== null) {
          cands.push({ tag: e.tagName, w: Math.round(r.width), x: Math.round(r.x), y: Math.round(r.y) });
        }
      }
      return cands;
    }).catch(() => []);
    if (info.length) return { frame: f, info };
  }
  return null;
};

let found = null;
for (let i = 0; i < 10 && !found; i++) { found = await findQr(); if (!found) await page.waitForTimeout(1000); }
if (!found) { log('QR element not found'); fs.writeFileSync(path.join(__dirname, 'qr-meta.json'), JSON.stringify({ status: 'qr-not-found' })); await ctx.close(); process.exit(0); }

// 用整页裁剪截二维码区域（元素截图对跨域 iframe 内元素不稳，boundingBox 跨 frame 由 playwright 换算）
const box = await (async () => {
  const el = await found.frame.locator('img, canvas').elementHandles();
  for (const h of el) {
    const b = await h.boundingBox();
    if (b && b.width >= 90 && b.width <= 400 && Math.abs(b.width - b.height) < 30) return b;
  }
  return null;
})();
if (!box) { log('QR boundingBox fail'); fs.writeFileSync(path.join(__dirname, 'qr-meta.json'), JSON.stringify({ status: 'qr-box-fail' })); await ctx.close(); process.exit(0); }

const writeMeta = (status) => fs.writeFileSync(path.join(__dirname, 'qr-meta.json'), JSON.stringify({ status, ts: Date.now() }));
writeMeta('qr-ready');
log('QR ready (qr.png), start polling for scan');

let expiredClicks = 0;
for (let i = 0; i < 90; i++) { // 最多 7.5 分钟
  await page.screenshot({ path: path.join(__dirname, 'qr.png'), clip: { x: Math.max(0, box.x - 8), y: Math.max(0, box.y - 8), width: box.width + 16, height: box.height + 16 } });
  // 成功检测：webUser 出现即登录成功
  const st = await page.evaluate(() => ((window.webUser && window.webUser.id) || null)).catch(() => null);
  if (st) {
    log('QR LOGIN SUCCESS userId=' + st);
    writeMeta('success');
    await page.waitForTimeout(1500);
    await ctx.close();
    process.exit(0);
  }
  // 过期检测 + 自动点刷新
  const expired = await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('div, span, a')).find(e =>
      e.offsetParent !== null && /二维码已失效|二维码过期|已失效|已过期/.test(e.textContent || '') && e.textContent.trim().length < 15);
    if (el) {
      const btn = Array.from(document.querySelectorAll('div, span, a')).find(e =>
        e.offsetParent !== null && /刷新/.test(e.textContent || '') && e.textContent.trim().length < 10);
      (btn || el).click();
      return true;
    }
    return false;
  }).catch(() => false);
  if (expired) { expiredClicks++; log('qr expired, refreshed #' + expiredClicks); }
  await page.waitForTimeout(5000);
}
writeMeta('timeout');
log('QR wait timeout');
await ctx.close();
