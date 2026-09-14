// 学习通（Chaoxing）真实播放 Runner — 无头 Edge + 凭据自适应登录
// ------------------------------------------------------------------
// 原则与 keepalive/监督手册一致：只真实播放、官方最高 2x、静音、
// 不伪造任何请求、异常即停（paused 写入 state.json，重跑即续跑）。
// 运行手册：../../SKILL.md §2；页面知识：../../knowledge/chaoxing.md；
// 状态协议：../../docs/architecture.md（v0.2 统一 Runner 形态）。
//
// 登录自适应链：会话有效 → password（页面自身表单，AES 由页面 JS 完成）→
// qr（无头截图交用户扫码，进程内等待）→ 都失败 pause。
// 无历史记忆：凭据每次运行前由监督者向用户获取（SKILL.md 安全规则第 11 条），
// 本文件不存储、不复用任何先前登录信息；账号数据只保留本地。
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATE = path.join(__dirname, 'state.json');
const LOGF = path.join(__dirname, 'runner.log');
const PROFILE_DIR = process.env.CHAOXING_PROFILE_DIR || path.join(__dirname, 'edge-profile');
const REPO = path.join(__dirname, '..', '..');
const CRED_FILE = path.join(REPO, 'credentials.local.json');
const CODE_FILE = path.join(__dirname, 'captcha-code.txt');
const STORAGE_FILE = path.join(__dirname, 'storage-state.json'); // cookie 落盘（会话 cookie 进程退出即丢）
const RATE = 2; // 平台官方最高档，勿超

// mooc2-ans 的会话 cookie 为浏览器会话级：进程退出即丢。storageState 落盘/回灌
// 让登录态跨进程存活，避免每次重启都重新扫码（实测三次踩坑的根因）。
async function restoreCookies(ctx) {
  try {
    const st = JSON.parse(fs.readFileSync(STORAGE_FILE, 'utf8'));
    if (Array.isArray(st.cookies) && st.cookies.length) {
      await ctx.addCookies(st.cookies);
      log('cookies restored from storage-state.json (' + st.cookies.length + ')');
      return true;
    }
  } catch { /* 无存档 */ }
  return false;
}
async function persistCookies(ctx) {
  try { fs.writeFileSync(STORAGE_FILE, JSON.stringify(await ctx.storageState())); } catch { /* 非致命 */ }
}

const COURSE = (() => {
  const i = process.argv.indexOf('--course');
  const file = i > -1 ? process.argv[i + 1] : process.env.COURSE_JSON;
  if (file && fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, 'utf8'));
  return { name: '未配置课程', platform: 'chaoxing', entry: {}, nodes: [], settings: {} };
})();
const ACCOUNT_NAME = (() => {
  const i = process.argv.indexOf('--account');
  return i > -1 ? process.argv[i + 1] : null;
})();

const state = {
  startedAt: new Date().toISOString(), platform: 'chaoxing',
  course: COURSE.name || COURSE.displayName || '(未命名)',
  current: null, results: [], paused: null, pausedDetail: null,
  done: false, ticks: 0,
};
const saveState = () => fs.writeFileSync(STATE, JSON.stringify(state, null, 1));
const log = (msg) => {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  fs.appendFileSync(LOGF, line + '\n');
};
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
// 跳页节奏红线（knowledge §8：跳页间隔 ≥4 秒）
const jumpGap = () => sleep(4000 + Math.floor(Math.random() * 2000));

// ---------- 凭据（每次登录前由监督者向用户获取；本文件不存储、不记忆任何账号信息） ----------
function loadAccount() {
  const p = process.env.CHAOXING_PHONE, w = process.env.CHAOXING_PASSWORD;
  if (p && w) return { name: 'env', phone: p, password: w };
  let db = null;
  try { db = JSON.parse(fs.readFileSync(CRED_FILE, 'utf8')); } catch { /* 无凭据文件 */ }
  const accs = (db && db.chaoxing && db.chaoxing.accounts) || [];
  const acc = ACCOUNT_NAME ? accs.find(a => a.name === ACCOUNT_NAME) : accs[0];
  return acc ? { ...acc } : null;
}

function activeHoursOk() {
  const wh = COURSE.settings && COURSE.settings.activeHours;
  if (!wh || wh.length !== 2) return true;
  const [a, b] = wh.map(s => String(s).split(':').map(Number));
  const now = new Date();
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= a[0] * 60 + a[1] && mins < b[0] * 60 + b[1];
}

// ---------- 登录 ----------
const IS_LOGIN_URL = (u) => /passport2\.chaoxing\.com|fanya\.chaoxing\.com\/login|\/login/i.test(u || '');

async function firstVisible(page, selectors) {
  for (const s of selectors) {
    try {
      const l = page.locator(s).first();
      if (await l.count() && await l.isVisible()) return l;
    } catch { /* 下一个 */ }
  }
  return null;
}

async function loginByPassword(page, account) {
  try {
    const user = await firstVisible(page, ['#phone', 'input[name="phone"]', 'input[type="tel"]', 'input[placeholder*="手机号"]', 'input[placeholder*="账号"]', 'input[placeholder*="学号"]']);
    const pwd = await firstVisible(page, ['#pwd', 'input[name="pwd"]', 'input[type="password"]']);
    const btn = await firstVisible(page, ['#loginBtn', 'button:has-text("登 录")', 'button:has-text("登录")', 'a:has-text("登录")', '[class*="loginbtn"]', '[class*="login-btn"]']);
    if (!user || !pwd || !btn) return { detail: '登录表单元素未找到 url=' + page.url() };
    await user.fill(account.phone);
    await pwd.fill(account.password);
    await btn.click();
    await page.waitForTimeout(6000);
    // 极验/滑块出现在登录页 → 人工通道（不对抗）
    let slider = false;
    for (const f of page.frames()) {
      if (await f.locator('[class*="geetest"], [aria-label*="滑块"], [title*="滑块"]').count().catch(() => 0)) { slider = true; break; }
    }
    if (slider) return { detail: '密码通道触发滑块验证（不对抗），转扫码通道' };
    if (IS_LOGIN_URL(page.url())) {
      const err = await page.evaluate(() =>
        (document.querySelector('.err-msg, .tips, [class*="error"], [class*="wrong"]') || {}).textContent
        || '').catch(() => '');
      return { detail: '登录未跳转 ' + String(err || '').trim().slice(0, 120) + ' | ' + page.url() };
    }
    return { ok: true };
  } catch (e) {
    return { pause: 'login-error', detail: String(e.message).slice(0, 200) };
  }
}

async function findQrElement(page) {
  // 通用近方形查找（img/canvas，实测登录页右侧默认展示二维码，无需点 tab）
  for (const f of [page, ...page.frames()]) {
    try {
      const h = await f.evaluateHandle(() => {
        const els = Array.from(document.querySelectorAll('img, canvas'));
        return els.find(el => {
          try {
            const r = el.getBoundingClientRect();
            return r.width >= 90 && r.width <= 420 && Math.abs(r.width - r.height) < 40 &&
              el.offsetParent !== null;
          } catch (e) { return false; }
        }) || null;
      }).catch(() => null);
      if (!h) continue;
      const el = h.asElement();
      if (!el) { h.dispose().catch(() => {}); continue; }
      return { el, dispose: () => h.dispose().catch(() => {}) };
    } catch { /* 下一个 frame */ }
  }
  return null;
}

async function loginByQr(page) {
  try {
    let qr = await findQrElement(page);
    if (!qr) {
      // 兜底：尝试点开「扫码登录」类入口后再找（多皮肤）
      for (const t of ['text=扫码登录', 'text=二维码登录', 'text=二维码']) {
        try { const tab = page.locator(t).first(); if (await tab.count() && await tab.isVisible()) { await tab.click(); await page.waitForTimeout(1500); break; } } catch { /* 下一个 */ }
      }
      qr = await findQrElement(page);
    }
    if (!qr) {
      await page.screenshot({ path: path.join(__dirname, 'login-page.png') }).catch(() => {});
      return { detail: '登录页未找到二维码入口 url=' + page.url() + '（已存 login-page.png 供修选择器）' };
    }
    await qr.el.screenshot({ path: path.join(__dirname, 'qr.png') });
    log('qr.png saved, waiting for scan (max 7.5 min)');
    state.paused = 'qr-wait'; state.pausedDetail = '用学习通 App 扫描 platforms/chaoxing/qr.png（进程内等待，≤7.5分钟）'; saveState();
    let stableOk = 0;
    for (let i = 0; i < 150; i++) { // 最多 7.5 分钟（与 icourse163 qr-login 一致）
      await sleep(3000);
      // 连续 3 拍（9 秒）不在登录页才算成功：二维码兑换 cookie 的 302 跳转链
      // 需要走完，过早判定会打断链路导致会话未持久化（实测两次踩坑）
      if (IS_LOGIN_URL(page.url())) { stableOk = 0; continue; }
      if (++stableOk < 3) continue;
      await page.waitForTimeout(3000);
      state.paused = null; saveState(); qr.dispose(); return { ok: true };
      // 二维码过期刷新（勿匹配裸「刷新」，knowledge §5 同款教训）
      try {
        const exp = page.locator('text=已失效').first();
        if (await exp.count() && await exp.isVisible()) {
          const rf = await firstVisible(page, ['text=刷新二维码', 'text=点击刷新', 'text=点击刷新二维码', 'a:has-text("刷新")']);
          if (rf) {
            await rf.click(); await page.waitForTimeout(1500);
            const fresh = await findQrElement(page);
            if (fresh) { qr.dispose(); qr = fresh; }
            await qr.el.screenshot({ path: path.join(__dirname, 'qr.png') });
          }
        }
      } catch { /* 轮询继续 */ }
    }
    qr.dispose();
    return { pause: 'qr-wait', detail: '扫码等待超时（5 分钟）' };
  } catch (e) {
    return { pause: 'login-error', detail: 'qr: ' + String(e.message).slice(0, 200) };
  }
}

async function ensureLogin(page, account) {
  const catalogUrl = COURSE.entry && COURSE.entry.catalogUrl;
  if (!catalogUrl) return { pause: 'navigation-failed', detail: '课程配置缺 entry.catalogUrl' };
  await page.goto(catalogUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  if (IS_LOGIN_URL(page.url())) {
    // 护照域持久 cookie 可能触发自动登录（passport 重定向链），给 12 秒观察
    for (let i = 0; i < 6 && IS_LOGIN_URL(page.url()); i++) await page.waitForTimeout(2000);
  }
  if (!IS_LOGIN_URL(page.url())) return { ok: true, channel: 'session' };
  log('session invalid, need login; url=' + page.url());
  if (!account) log('无凭据（CHAOXING_PHONE/PASSWORD 与 credentials.local.json 均缺）→ 仅走扫码通道（SKILL.md §2）');
  const order = !account ? ['qr'] : ['password', 'qr'];
  let lastDetail = '';
  for (const ch of order) {
    if (ch === 'password' && account.password) {
      log('login channel: password');
      const r = await loginByPassword(page, account);
      if (r.ok) { return { ok: true, channel: 'password' }; }
      lastDetail = r.detail || '';
      if (r.pause) return r; // captcha / login-error 直接停
      log('password channel failed: ' + lastDetail + ' → fallback qr');
    }
    if (ch === 'qr') {
      log('login channel: qr');
      const r = await loginByQr(page);
      if (r.ok) { return { ok: true, channel: 'qr' }; }
      lastDetail = r.detail || lastDetail;
      if (r.pause && r.pause !== 'qr-wait') return r;
      if (r.pause === 'qr-wait') return r;
    }
  }
  return { pause: 'login-failed', detail: '自适应登录全部失败：' + lastDetail };
}

// ---------- 页面工具 ----------
async function visibleTop(page, sel) {
  try {
    return await page.evaluate((s) => {
      const el = document.querySelector(s);
      if (!el) return false;
      const st = getComputedStyle(el);
      return st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null;
    }, sel);
  } catch { return false; }
}

async function quizPopup(page) {
  for (const f of page.frames()) {
    try {
      if (await f.evaluate(() => {
        const els = document.querySelectorAll('.popups-box, .mark_infoDialog, [class*="popups"]');
        for (const el of els) {
          const st = getComputedStyle(el);
          if (st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null) return true;
        }
        return false;
      })) return true;
    } catch { /* 跨域等 */ }
  }
  return false;
}

// mArg：knowledge/cards 页内的任务点 JSON（attachments[].isPassed 是完成口径）
async function readMArg(page) {
  for (const f of page.frames()) {
    if (!/knowledge\/cards/i.test(f.url())) continue;
    try {
      const html = await f.content();
      for (const re of [/mArg\s*=\s*(\{[\s\S]*?\})\s*;\s*[\r\n]/, /mArg\s*=\s*(\{[\s\S]*?\});/, /"attachments"\s*:\s*(\[[\s\S]*?\])\s*,\s*"defaults"/]) {
        const m = html.match(re);
        if (!m) continue;
        try {
          const parsed = JSON.parse(m[1]);
          if (Array.isArray(parsed)) return { attachments: parsed };
          if (parsed && parsed.attachments) return parsed;
        } catch { /* 试下一个正则 */ }
      }
    } catch { /* 跨域 */ }
  }
  return null;
}

async function findVideoFrame(page, objectId) {
  for (const f of page.frames()) {
    if (!/ananas\/modules\/video/i.test(f.url())) continue;
    if (objectId && !f.url().includes(objectId)) continue;
    try { if (await f.locator('video').count()) return f; } catch { /* 下一个 */ }
  }
  if (objectId) return findVideoFrame(page, null); // 退化：任意视频帧
  return null;
}

async function detectCaptchaFrame(page) {
  for (const f of page.frames()) {
    try { if (await f.locator('#ucode').count().catch(() => 0)) return f; } catch { /* 下一个 */ }
  }
  return null;
}

// 验证码（403/9010）：页面内 fetch 图转 base64 存 captcha.png，
// 监督者读码写 captcha-code.txt，进程内等待提交（不对抗、无第三方打码）。
async function handleCaptcha(page) {
  const f = await detectCaptchaFrame(page);
  if (!f) return false;
  const b64 = await f.evaluate(async () => {
    const img = document.querySelector('img[src*="processVerifyPng"], img[src*="Verify"]');
    if (!img) return null;
    const r = await fetch(img.src, { credentials: 'include' });
    const b = await r.blob();
    return await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); });
  }).catch(() => null);
  if (b64) fs.writeFileSync(path.join(__dirname, 'captcha.png'), Buffer.from(String(b64).split(',')[1], 'base64'));
  log('captcha detected; saved captcha.png; waiting ' + CODE_FILE);
  state.paused = 'captcha';
  state.pausedDetail = '读 platforms/chaoxing/captcha.png，把结果写入 platforms/chaoxing/captcha-code.txt（进程内等待 ≤5 分钟）';
  saveState();
  for (let i = 0; i < 100; i++) {
    await sleep(3000);
    if (!fs.existsSync(CODE_FILE)) continue;
    const code = fs.readFileSync(CODE_FILE, 'utf8').trim();
    if (!/^[a-zA-Z0-9]{3,8}$/.test(code)) continue;
    await f.fill('#ucode', code).catch(() => {});
    await f.evaluate(() => { const b = document.querySelector('input.submit'); if (b) b.click(); }).catch(() => {});
    await page.waitForTimeout(5000);
    if (fs.existsSync(CODE_FILE)) fs.unlinkSync(CODE_FILE);
    if (!(await detectCaptchaFrame(page))) { state.paused = null; saveState(); log('captcha passed'); return true; }
    state.pausedDetail = '验证码提交后仍未通过，请人工处理'; saveState();
    return false;
  }
  state.pausedDetail = '等待验证码超时（5 分钟）'; saveState();
  return false;
}

// ---------- 任务发现 ----------
async function readSidebar(page) {
  return await page.evaluate(() =>
    Array.from(document.querySelectorAll('.chapter_item'))
      .map(el => ({
        chapterId: (el.id || '').replace(/^cur/, ''),
        name: (el.getAttribute('title') || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80),
      })).filter(x => x.chapterId)
  ).catch(() => []);
}

// 目录页 enc 失效（「无效的参数」）→ 1) 试去 enc 直开；2) 课程列表接口重取（knowledge §1）
async function refreshCatalogUrl(page) {
  const shortName = (COURSE.displayName || COURSE.name || '').replace(/（.*$/, '');
  const catalogUrl = COURSE.entry.catalogUrl;
  // 1) 去掉 enc 直接开（部分部署不校验）
  const noEnc = catalogUrl.replace(/([?&])enc=[^&]*&?/, '$1').replace(/[?&]$/, '');
  await page.goto(noEnc, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  const txt = await page.evaluate(() => document.body.innerText.slice(0, 500)).catch(() => '');
  if (!/无效的参数|参数错误/.test(txt) && !IS_LOGIN_URL(page.url())) {
    COURSE.entry.catalogUrl = noEnc;
    log('catalog works without enc');
    return true;
  }
  // 2) 个人空间（i.chaoxing.com，同 SSO）：从空间页面 DOM/HTML 找带新 enc 的课程链接
  await page.goto('https://i.chaoxing.com/', { waitUntil: 'domcontentloaded' }).catch(() => {});
  await page.waitForTimeout(5000);
  const found = await page.evaluate((key) => {
    // 收集顶层与同源 iframe 文档里的 stu 链接
    const docs = [document];
    for (const d of docs) {
      try { for (const f of d.querySelectorAll('iframe')) { const cd = f.contentDocument; if (cd && !docs.includes(cd)) docs.push(cd); } } catch (e) {}
    }
    const links = [];
    for (const d of docs) {
      try {
        for (const a of d.querySelectorAll('a[href*="mycourse/stu"], [onclick*="mycourse/stu"]')) {
          const href = a.getAttribute('href') || a.getAttribute('onclick') || '';
          links.push({ href: href.replace(/&amp;/g, '&'), text: (a.textContent || '').trim() });
        }
        const html = d.documentElement.innerHTML.replace(/&amp;/g, '&');
        let i = html.indexOf('/mycourse/stu?');
        while (i !== -1) { links.push({ href: html.slice(i, i + 300).split(/[\"']/)[0], text: '' }); i = html.indexOf('/mycourse/stu?', i + 1); }
      } catch (e) {}
    }
    const pick = (l) => {
      let u = l.href;
      if (u.startsWith('/')) u = 'https://i.chaoxing.com' + u;
      return /^https?:\/\//.test(u) ? u : null;
    };
    const named = links.find(l => !key || l.text.includes(key) || l.href.includes(key));
    if (named) return pick(named);
    return links.length ? pick(links[0]) : null;
  }, shortName).catch(() => null);
  if (found) {
    await page.goto(found, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4000);
    const txt2 = await page.evaluate(() => document.body.innerText.slice(0, 500)).catch(() => '');
    if (!/无效的参数|参数错误/.test(txt2) && !IS_LOGIN_URL(page.url())) {
      COURSE.entry.catalogUrl = found;
      log('catalogUrl refreshed via i.chaoxing.com space');
      return true;
    }
  }
  await page.screenshot({ path: path.join(__dirname, 'mycourses-debug.png') }).catch(() => {});
  return false;
}

async function gotoNode(page, node) {
  const tpl = COURSE.entry && COURSE.entry.playerUrlTemplate;
  const sp = (COURSE.entry && COURSE.entry.sessionParams) || {};
  if (tpl) {
    const map = { ...sp, chapterId: node.chapterId, courseid: sp.courseId, courseId: sp.courseId };
    const url = tpl.replace(/\{(\w+)\}/g, (m, k) => {
      const key = Object.keys(map).find(x => x.toLowerCase() === String(k).toLowerCase());
      return key != null ? String(map[key] ?? '') : m;
    });
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4000);
    if (!IS_LOGIN_URL(page.url()) && (await readSidebar(page)).length) return true;
    log('playerUrlTemplate 落地异常（' + page.url().slice(0, 100) + '），回退目录页点击');
  }
  // 兜底：目录页按名称点击 .chapter_item（toOld 入口，knowledge §2）
  const catalogUrl = COURSE.entry && COURSE.entry.catalogUrl;
  if (!catalogUrl) return false;
  await page.goto(catalogUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  const clicked = await page.evaluate((name) => {
    const items = Array.from(document.querySelectorAll('.chapter_item'));
    const el = (name && items.find(e =>
      ((e.getAttribute('title') || '') + ' ' + (e.textContent || '')).replace(/\s+/g, ' ').includes(name))
    ) || items[0];
    if (el) { el.click(); return true; }
    return false;
  }, node.name || '').catch(() => false);
  await page.waitForTimeout(6000);
  return !!clicked && !IS_LOGIN_URL(page.url());
}

// ---------- 节点处理 ----------
async function watchVideo(page, att, node, attemptLabel) {
  let vf = await findVideoFrame(page, att.objectId || null);
  if (!vf) return { pause: 'video-lost', detail: (node.name || '') + ' 找不到视频 iframe' };
  // 启动播放（autoplay 策略已在启动参数放开；仍失败点播放器按钮）
  let started = false;
  for (let a = 0; a < 3 && !started; a++) {
    const st = await vf.evaluate(() => {
      const v = document.querySelector('video');
      if (!v) return null;
      v.muted = true; v.volume = 0; v.playbackRate = 2;
      v.play().catch(() => {});
      return { paused: v.paused };
    }).catch(() => null);
    if (st && !st.paused) { started = true; break; }
    await vf.evaluate(() => {
      const b = document.querySelector('.vjs-big-play-button, [class*="bigplay"], [class*="playbtn"]');
      if (b) b.click();
    }).catch(() => {});
    await page.waitForTimeout(3000);
  }
  if (!started) return { pause: 'video-stuck', detail: (node.name || '') + ' 无法启动播放 ' + (attemptLabel || '') };
  log(`VIDEO ${node.name || node.chapterId} playing (attempt ${attemptLabel || 1})`);
  // 看门狗：钉静音/2x/恢复播放，检测弹题与日上限；paused/ended 判定同 keepalive
  let lastT = -1, stall = 0, reloads = 0, lostTicks = 0;
  while (true) {
    await page.waitForTimeout(5000);
    if (await visibleTop(page, '.jobCountDiv')) return { pause: 'daily-cap', detail: '今日视频任务点已达上限' };
    if (await quizPopup(page)) return { pause: 'quiz-popup', detail: (node.name || '') + ' 视频中途弹题，交监督者作答' };
    const cf = await detectCaptchaFrame(page);
    if (cf && !(await handleCaptcha(page))) return { pause: 'captcha', detail: '验证码处理未通过' };
    const st = await vf.evaluate(() => {
      const v = document.querySelector('video');
      if (!v) return { noVideo: true };
      if (!v.muted) { v.muted = true; v.volume = 0; }
      if (Math.abs(v.playbackRate - 2) > 0.01) v.playbackRate = 2;
      if (v.paused && !v.ended) v.play().catch(() => {});
      return { t: v.currentTime, d: v.duration, ended: v.ended, paused: v.paused };
    }).catch(() => null);
    if (!st) {
      // 帧引用失效（reload/跳转后 evaluate 抛错）：重新找视频帧，持续丢失才判 video-lost
      if (++lostTicks > 6) return { pause: 'video-lost', detail: node.name || node.chapterId };
      vf = (await findVideoFrame(page, att.objectId || null)) || vf;
      continue;
    }
    lostTicks = 0;
    state.current = { node: node.name || node.chapterId, chapterId: String(node.chapterId), t: st.t != null ? Math.round(st.t) : null, video: att.objectId || null };
    state.ticks += 1;
    if (state.ticks % 12 === 0) saveState();
    if (st.ended) break;
    if (st.noVideo) {
      if (++reloads > 3) return { pause: 'video-lost', detail: node.name || node.chapterId };
      log('video element lost, reload #' + reloads);
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(5000);
      vf = (await findVideoFrame(page, att.objectId || null)) || vf;
      continue;
    }
    if (st.t === lastT && !st.paused) {
      if (++stall >= 6) {
        if (++reloads > 3) return { pause: 'video-stuck', detail: node.name || node.chapterId };
        log('video stalled, reload #' + reloads);
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(5000);
        vf = (await findVideoFrame(page, att.objectId || null)) || vf;
        stall = 0;
      }
    } else stall = 0;
    lastT = st.t;
  }
  // 完成核对（ended ≠ 已记录，假完成防御，knowledge §3）
  await page.waitForTimeout(4000);
  const mArg = await readMArg(page);
  const me = mArg && (mArg.attachments || []).find(a =>
    a.type === 'video' && (!att.objectId || String(a.objectId) === String(att.objectId)));
  if (me) return me.isPassed ? { result: 'passed' } : { replay: true };
  // mArg 拿不到时退化为 icon_Completed 旁证；再不行如实记 unverified
  let icon = false;
  for (const f of page.frames()) {
    try { if (await f.evaluate(() => !!document.querySelector('.icon_Completed')).catch(() => false)) { icon = true; break; } } catch { /* 下一个 */ }
  }
  return icon ? { result: 'passed(icon)' } : { result: 'ended-unverified' };
}

async function processNode(page, node) {
  if (node.type === 'quiz') return { pause: 'quiz', detail: (node.name || '') + ' 为测验节点，按手册 §4.1 由监督者处理' };
  if (!(await gotoNode(page, node))) return { pause: 'navigation-failed', detail: '无法进入节点页 ' + (node.name || node.chapterId) };
  await page.waitForTimeout(3000);
  if (await visibleTop(page, '.jobCountDiv')) return { pause: 'daily-cap', detail: '今日视频任务点已达上限' };
  if (await detectCaptchaFrame(page) && !(await handleCaptcha(page))) return { pause: 'captcha', detail: '验证码处理未通过' };
  let mArg = await readMArg(page);
  const atts = (mArg && mArg.attachments) || [];
  const videos = atts.filter(a => a.type === 'video' && !a.isPassed);
  log(`NODE ${node.name || node.chapterId}: ${atts.length} attachment(s), ${videos.length} video to watch`);
  for (let i = 0; i < videos.length; i++) {
    let r = await watchVideo(page, videos[i], node, String(i + 1));
    if (r.pause) return r;
    if (r.replay) { // 假完成防御：重播一次
      log('completion not recorded, replay once');
      r = await watchVideo(page, videos[i], node, String(i + 1) + 'R');
      if (r.pause) return r;
      if (r.replay) return { pause: 'completion-unverified', detail: (node.name || '') + ' 重播仍未核对到完成标记' };
    }
    state.results.push({ node: node.name || node.chapterId, chapterId: String(node.chapterId), type: 'video', result: r.result || 'passed' });
    saveState();
  }
  // 文档/阅读：节点页打开即触发完成 GET，稍候复查
  const docs = atts.filter(a => (a.type === 'document' || a.type === 'read') && !a.isPassed);
  if (docs.length) {
    await page.waitForTimeout(8000);
    mArg = await readMArg(page);
    const stillDoc = ((mArg && mArg.attachments) || []).some(a => (a.type === 'document' || a.type === 'read') && !a.isPassed);
    if (stillDoc) state.results.push({ node: node.name || node.chapterId, type: 'doc', result: 'opened-unverified' });
  }
  // 测验最后处理：有未完成测验 → 停给监督者
  mArg = await readMArg(page);
  const stillWork = ((mArg && mArg.attachments) || []).some(a => (a.type === 'workid' || a.type === 'homework') && !a.isPassed);
  if (stillWork) return { pause: 'quiz', detail: (node.name || '') + ' 有未完成测验，按手册 §4.1 处理' };
  return { result: 'node-done' };
}

async function discoverFromCatalog(page, ctx) {
  let catalogUrl = COURSE.entry && COURSE.entry.catalogUrl;
  if (!catalogUrl) return { pause: 'navigation-failed', detail: '缺 catalogUrl 且未配置 nodes' };
  await page.goto(catalogUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  // enc 会话级：失效页显示「无效的参数」→ 回课程列表重取新 enc（knowledge §1）
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 500)).catch(() => '');
  if (/无效的参数|参数错误/.test(bodyText)) {
    log('catalog enc invalid, refreshing from course list');
    if (!(await refreshCatalogUrl(page))) return { pause: 'navigation-failed', detail: '课程列表未找到课程卡片/新 enc（已存 mycourses-debug.png）' };
    catalogUrl = COURSE.entry.catalogUrl;
  }
  // 章节入口多选择器：toOld/studentstudy 属性、.chapter_item（knowledge §2）
  const clicked = await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('[onclick*="toOld"], [onclick*="studentstudy"], .chapter_item'))
      .filter(e => e.offsetParent !== null);
    if (!els.length) return false;
    els[0].click();
    return true;
  }).catch(() => false);
  await page.waitForTimeout(6000);
  if (!clicked) {
    // 兜底：属性中含 studentstudy 的入口
    await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('a, div, li, span')).find(e => {
        const attrs = ((e.getAttribute && (e.getAttribute('onclick') || '')) + (e.getAttribute && (e.getAttribute('href') || '')));
        return /studentstudy/i.test(attrs);
      });
      if (el) { el.click(); return true; }
      return false;
    }).catch(() => false);
    await page.waitForTimeout(6000);
  }
  let cur = null;
  for (const p of ctx.pages()) if (/studentstudy/i.test(p.url())) { cur = p; break; }
  if (!cur) {
    await page.screenshot({ path: path.join(__dirname, 'catalog-debug.png') }).catch(() => {});
    return { pause: 'navigation-failed', detail: '目录页点击章节未进入 studentstudy（已存 catalog-debug.png）' };
  }
  const chapters = await readSidebar(cur);
  if (!chapters.length) {
    await cur.screenshot({ path: path.join(__dirname, 'sidebar-debug.png') }).catch(() => {});
    return { pause: 'navigation-failed', detail: 'studentstudy 侧栏未解析出章节（.chapter_item 可能改版，已存 sidebar-debug.png）' };
  }
  return { chapters, page: cur };
}

// ---------- 主流程 ----------
async function main() {
  log('chaoxing runner start, profile=' + PROFILE_DIR + ', course=' + state.course);
  const account = loadAccount();
  // 无凭据不快速失败：ensureLogin 会自动走扫码通道（SKILL.md §2 无密码路径）
  if (!activeHoursOk()) {
    state.paused = 'outside-active-hours';
    state.pausedDetail = '当前时间不在 settings.activeHours=' + JSON.stringify(COURSE.settings && COURSE.settings.activeHours);
    saveState(); log(state.pausedDetail); return;
  }
  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'msedge', headless: process.env.CHAOXING_HEADED !== '1',
    viewport: { width: 1600, height: 900 },
    args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'],
  });
  try {
    let page = ctx.pages()[0] || await ctx.newPage();
    page.setDefaultTimeout(15000);
    await restoreCookies(ctx);
    const lr = await ensureLogin(page, account);
    if (lr.pause) { state.paused = lr.pause; state.pausedDetail = lr.detail || null; return; }
    log('login ok via ' + lr.channel);
    await persistCookies(ctx);
    let chapters;
    if (COURSE.nodes && COURSE.nodes.length) {
      chapters = COURSE.nodes.filter(n => n.type !== 'skip');
      log('chapters from config: ' + chapters.length);
    } else {
      const d = await discoverFromCatalog(page, ctx);
      if (d.pause) { state.paused = d.pause; state.pausedDetail = d.detail; return; }
      chapters = d.chapters; page = d.page;
      log('chapters discovered: ' + chapters.length);
    }
    for (const node of chapters) {
      await jumpGap();
      state.current = { node: node.name || node.chapterId, chapterId: String(node.chapterId) };
      saveState();
      const r = await processNode(page, node);
      if (r.pause) {
        state.paused = r.pause;
        state.pausedDetail = (r.detail || '') + ' @' + (node.name || node.chapterId);
        break;
      }
    }
    if (!state.paused) { state.done = true; log('ALL DONE'); }
  } catch (e) {
    log('FATAL ' + String(e.stack || e.message).slice(0, 500));
    state.paused = 'error';
    state.pausedDetail = String(e.message).slice(0, 200);
  } finally {
    await persistCookies(ctx);
    saveState();
    await ctx.close().catch(() => {});
    log('runner exit, paused=' + state.paused + ' done=' + state.done);
  }
}

main();
