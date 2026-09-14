// MOOC Runner — 中国大学MOOC（icourse163）真实播放挂机
// 收编自 workspace/default/mooc-runner/runner.mjs（2026-09-12 首轮实战版本，原路径保留）。
// 相对原版的改动（均有 field-notes/knowledge 依据）：
//   1. 任务来源改为自动发现：扫描课件矩阵，跳过已 learned，播放未完成的视频/文档
//      （原版硬编码 cid 清单，新周发布的内容会被漏掉）
//   2. 登录态路径可用环境变量 MOOC_PROFILE_DIR 指向已有 profile（默认本目录 edge-profile）
//   3. 课程可用 --course <file.json> 或 COURSE_JSON 外置；缺省为内置课程
//   4. 自适应登录（2026-09-14）：有 MOOC_PASSWORD 或 credentials.local.json 密码时
//      优先走页面自身表单的密码登录（新设备被风控拒绝会自动降级短信通道）；
//      凭据每次运行前由监督者向用户获取，本文件不存储、不记忆任何账号信息
//      （2026-09-14 起：移除 login-hint 渠道记忆，符合"不使用先前登录信息"纪律）
// 原则不变：只真实播放；官方最高 2x；静音；一次一个视频；不伪造任何请求；异常即停。
// 页面知识见 knowledge/icourse163.md；监督协议见 ../../SKILL.md 与 ../../docs/architecture.md。
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATE = path.join(__dirname, 'state.json');
const LOGF = path.join(__dirname, 'runner.log');
const PROFILE_DIR = process.env.MOOC_PROFILE_DIR || path.join(__dirname, 'edge-profile');

const COURSE = (() => {
  const i = process.argv.indexOf('--course');
  const file = i > -1 ? process.argv[i + 1] : process.env.COURSE_JSON;
  if (file && fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, 'utf8'));
  // 隐私纪律：不内置任何真实课程（课程属于账号数据，见 SKILL.md 安全规则第 11 条）。
  // 必须通过 --course <file.json> 或 COURSE_JSON 提供课程配置（模板 courses/icourse163.example.json）。
  return null;
})();
const RATE = 2; // 平台官方最高档

const state = {
  startedAt: new Date().toISOString(), platform: 'icourse163',
  course: COURSE ? (COURSE.name || '(未命名)') : '(未配置课程)',
  current: null, results: [], paused: null, pausedDetail: null,
  matrix: null, ticks: 0,
};
const saveState = () => fs.writeFileSync(STATE, JSON.stringify(state, null, 1));
const log = (msg) => {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  fs.appendFileSync(LOGF, line + '\n');
};
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ---------- 自适应登录（凭据获取顺序：环境变量 > credentials.local.json） ----------
const REPO = path.join(__dirname, '..', '..');
function loadIcAccount() {
  const p = process.env.MOOC_PHONE, w = process.env.MOOC_PASSWORD;
  if (p && w) return { name: 'env', phone: p, password: w };
  let db = null;
  try { db = JSON.parse(fs.readFileSync(path.join(REPO, 'credentials.local.json'), 'utf8')); } catch { /* 无凭据文件 */ }
  const accs = (db && db.icourse163 && db.icourse163.accounts) || [];
  const nameI = process.argv.indexOf('--account');
  const name = nameI > -1 ? process.argv[nameI + 1] : null;
  const acc = name ? accs.find(a => a.name === name) : accs[0];
  return acc ? { ...acc } : null;
}
// 密码通道：页面自身表单（登录表单在 iframe 内，密码框用 :visible 过滤，knowledge §5）。
// 实测先例：新设备密码登录可能被风控拒绝（「请设置登录密码」）→ 返回 false 自动降级短信/扫码。
async function tryPasswordLogin163(page, account) {
  try {
    await page.goto('https://www.icourse163.org/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);
    await page.getByRole('button', { name: '登录/注册' }).click();
    await page.waitForTimeout(2000);
    let frame = null;
    for (let i = 0; i < 8 && !frame; i++) {
      for (const f of page.frames()) {
        if (await f.locator('input[type="password"]:visible').count().catch(() => 0)) { frame = f; break; }
      }
      if (!frame) await page.waitForTimeout(1000);
    }
    if (!frame) { log('password channel: login form/iframe not found'); return false; }
    await frame.locator('input[placeholder*="手机号"]:visible').first().fill(account.phone).catch(async () => {
      await frame.locator('input[type="tel"]:visible, input[type="text"]:visible').first().fill(account.phone);
    });
    await frame.locator('input[type="password"]:visible').first().fill(account.password);
    await frame.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('div, a, button, span')).find(e =>
        e.children.length === 0 && /^登\s*录$/.test((e.textContent || '').trim()) && e.offsetParent !== null);
      if (btn) btn.click();
    });
    await page.waitForTimeout(7000);
    if (await page.evaluate(() => !!(window.webUser && window.webUser.id)).catch(() => false)) return true;
    log('password channel not confirmed (风控/错密/滑块)，自动降级下一通道');
    return false;
  } catch (e) { log('password channel error: ' + e.message.slice(0, 120)); return false; }
}

async function main() {
  log('runner start (repo build), profile=' + PROFILE_DIR + ', course=' + state.course);
  if (!COURSE || !COURSE.courseUrl) {
    state.paused = 'course-config-required';
    state.pausedDetail = '必须提供课程配置：--course <file.json> 或 COURSE_JSON（模板 courses/icourse163.example.json）；不内置任何真实课程';
    saveState(); log(state.pausedDetail); return;
  }
  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'msedge',
    headless: process.env.MOOC_HEADED !== '1',
    viewport: { width: 1600, height: 900 },
    args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  page.setDefaultTimeout(15000);

  // ---------- 登录 ----------
  await page.goto(COURSE.courseUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  let userId = await page.evaluate(() => (window.webUser && window.webUser.id) || null).catch(() => null);
  if (!userId) {
    // 通道 1：密码（页面自身表单；新设备可能被风控拒绝 → 自动降级短信；扫码仍可走 qr-login.mjs）
    const acc = loadIcAccount();
    if (acc && acc.password) {
      log('no session; login channel: password (adaptive)');
      if (await tryPasswordLogin163(page, acc)) {
        await page.goto(COURSE.courseUrl, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(4000);
        userId = await page.evaluate(() => (window.webUser && window.webUser.id) || null).catch(() => null);
      }
    }
  }
  if (!userId) {
    try {
      log('no session; 登录通道：短信兜底（密码未设/失败/被风控；无凭据时也可用 qr-login.mjs 扫码）');
      const acc = loadIcAccount();
      const phone = process.env.MOOC_PHONE || (acc && acc.phone);
      if (!phone) { state.paused = 'no-credentials'; state.pausedDetail = '登录前需获取账号密码：MOOC_PHONE/MOOC_PASSWORD 或 credentials.local.json（模板 credentials.example.json）；或先跑 qr-login.mjs 扫码'; saveState(); await ctx.close(); return; }
      // 去主页打开登录弹窗
      await page.goto('https://www.icourse163.org/', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(3000);
      await page.getByRole('button', { name: '登录/注册' }).click();
      await page.waitForTimeout(2000);
      await page.evaluate(() => {
        const el = Array.from(document.querySelectorAll('li, div, span')).find(e =>
          e.children.length === 0 && e.textContent.trim() === '手机号登录');
        if (el) el.click();
      });
      await page.waitForTimeout(1200);
      // 找到手机号登录表单所在 frame
      let loginFrame = null;
      for (let i = 0; i < 8 && !loginFrame; i++) {
        for (const f of page.frames()) {
          const inp = f.getByPlaceholder('请输入手机号');
          if (await inp.count().catch(() => 0) && await inp.first().isVisible().catch(() => false)) { loginFrame = f; break; }
        }
        if (!loginFrame) await page.waitForTimeout(1000);
      }
      if (!loginFrame) { state.paused = 'login-form-not-found'; saveState(); await ctx.close(); return; }
      // 切到短信验证码模式
      const toggled = await loginFrame.evaluate(() => {
        const cands = Array.from(document.querySelectorAll('a, div, span, i, label'))
          .filter(e => {
            const t = (e.textContent || '').trim();
            return t.length > 0 && t.length < 12 && /短信快捷登录|短信验证码登录|验证码登录/.test(t) && e.offsetParent !== null;
          });
        if (!cands.length) return 'NOT_FOUND';
        cands.sort((a, b) => (a.textContent.length - b.textContent.length) ||
          (a.querySelectorAll('*').length - b.querySelectorAll('*').length));
        const el = cands[0];
        (el.closest('a') || el).click();
        return 'clicked:' + el.tagName + ':' + (el.className || '').toString().slice(0, 30);
      });
      log('sms toggle: ' + toggled);
      await page.waitForTimeout(1500);
      const formCheck = await loginFrame.evaluate(() =>
        Array.from(document.querySelectorAll('input'))
          .filter(i => i.offsetParent !== null)
          .map(i => i.placeholder || i.name || i.id));
      log('form inputs after toggle: ' + JSON.stringify(formCheck));
      if (!formCheck.some(p => /验证码/.test(p))) {
        state.paused = 'sms-toggle-failed'; state.pausedDetail = '表单未切换到验证码模式: ' + JSON.stringify(formCheck);
        saveState(); await ctx.close(); return;
      }
      // 填手机号并点获取验证码
      const smsState = await loginFrame.evaluate((phone) => {
        const out = { inputs: [], clicked: false };
        const phoneInput = Array.from(document.querySelectorAll('input')).find(i =>
          i.offsetParent !== null && /手机/.test(i.placeholder || ''));
        if (phoneInput) {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(phoneInput, phone);
          phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        const getCode = Array.from(document.querySelectorAll('a, div, span, button')).find(e =>
          e.children.length === 0 && /获取验证码|获取短信验证码/.test(e.textContent.trim()) && e.offsetParent !== null);
        if (getCode) { getCode.click(); out.clicked = true; }
        return out;
      }, phone);
      log('sms form: ' + JSON.stringify(smsState));
      await page.screenshot({ path: path.join(__dirname, 'sms-form.png') });
      await page.waitForTimeout(2000);
      // 滑块检测（获取验证码动作可能触发易盾滑块）
      let captcha = false;
      for (const f of page.frames()) {
        if (await f.locator('[aria-label*="滑块"], [title*="滑块"]').count().catch(() => 0) ||
            await f.getByText('请完成安全验证').count().catch(() => 0)) { captcha = true; break; }
      }
      if (captcha) {
        log('CAPTCHA on get-code -> stop');
        state.paused = 'captcha'; state.pausedDetail = '获取验证码触发滑块验证，需人工完成';
        saveState(); await ctx.close(); return;
      }
      // 等监督者把验证码写入 code.txt（凭据文件握手，不落盘到脚本/状态）
      const codeFile = path.join(__dirname, 'code.txt');
      log('WAITING_FOR_SMS_CODE (write it to ' + codeFile + ')');
      state.paused = 'waiting-sms-code'; saveState();
      let code = null;
      for (let i = 0; i < 200; i++) { // 最多 10 分钟
        await page.waitForTimeout(3000);
        if (fs.existsSync(codeFile)) {
          const c = fs.readFileSync(codeFile, 'utf8').trim();
          if (/^\d{4,8}$/.test(c)) { code = c; break; }
        }
      }
      if (!code) { state.paused = 'sms-code-timeout'; saveState(); await ctx.close(); return; }
      log('got code from file, submitting');
      const submit = await loginFrame.evaluate((code) => {
        const codeInput = Array.from(document.querySelectorAll('input')).find(i =>
          i.offsetParent !== null && /验证码/.test(i.placeholder || ''));
        if (!codeInput) return 'NO_CODE_INPUT';
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(codeInput, code);
        codeInput.dispatchEvent(new Event('input', { bubbles: true }));
        const btn = Array.from(document.querySelectorAll('div, a, button, span')).find(e =>
          e.children.length === 0 && /^(登\s*录|登录|注册并登录)$/.test(e.textContent.trim()) && e.offsetParent !== null);
        if (btn) { btn.click(); return 'submitted'; }
        return 'NO_BUTTON';
      }, code);
      log('sms submit: ' + submit);
      await page.waitForTimeout(7000);
      captcha = false;
      for (const f of page.frames()) {
        if (await f.locator('[aria-label*="滑块"], [title*="滑块"]').count().catch(() => 0) ||
            await f.getByText('请完成安全验证').count().catch(() => 0)) { captcha = true; break; }
      }
      if (captcha) {
        log('CAPTCHA after sms submit -> stop');
        state.paused = 'captcha'; state.pausedDetail = '提交验证码触发滑块验证，需人工完成';
        saveState(); await ctx.close(); return;
      }
      await page.goto(COURSE.courseUrl, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(4000);
      userId = await page.evaluate(() => (window.webUser && window.webUser.id) || null).catch(() => null);
      if (!userId) {
        await page.screenshot({ path: path.join(__dirname, 'sms-after.png') });
        const needPwd = await page.evaluate(() => /请设置登录密码/.test(document.body.innerText)).catch(() => false);
        state.paused = needPwd ? 'need-set-password' : 'login-failed';
        saveState(); await ctx.close(); return;
      }
      log('logged in, userId=' + userId);
      fs.existsSync(codeFile) && fs.unlinkSync(codeFile);
    } catch (e) {
      log('login error: ' + e.message.slice(0, 200));
      state.paused = 'login-error'; state.pausedDetail = String(e.message).slice(0, 200);
      saveState(); await ctx.close(); return;
    }
  } else {
    log('logged in (valid session), userId=' + userId);
  }

  // ---------- 工具 ----------
  const gotoList = async () => {
    await page.evaluate(() => { location.hash = '#/learn/content'; });
    await page.waitForTimeout(2200);
    // 展开所有 lessonBox 为空的章节（章节默认折叠，见 knowledge/icourse163.md §2）
    for (let i = 0; i < 10; i++) {
      const need = await page.evaluate(() => {
        const ch = Array.from(document.querySelectorAll('.m-learnChapterNormal'))
          .find(c => c.querySelectorAll('.u-learnLesson').length === 0);
        if (ch) { (ch.querySelector('.titleBox') || ch.querySelector('h3')).click(); return true; }
        return false;
      });
      if (!need) break;
      await page.waitForTimeout(1500);
    }
  };
  const learned = (cid) => page.evaluate((cid) => {
    const ic = document.querySelector(`.f-icon.lsicon[data-cid="${cid}"]`);
    return ic ? ic.classList.contains('learned') : null;
  }, cid);

  const ensurePlaying = async () => {
    for (let round = 0; round < 3; round++) {
      const v = page.locator('video');
      if (await v.count() === 0) { await page.waitForTimeout(2000); continue; }
      const st = await page.evaluate(() => {
        const v = document.querySelector('video');
        if (v) { v.muted = true; v.volume = 0; }
        return v ? { paused: v.paused, rate: v.playbackRate } : null;
      });
      if (st && !st.paused) return true;
      log('video paused, try bigplaybtn (round ' + round + ')');
      await page.evaluate(() => {
        const big = document.querySelector('.j-bigplaybtn');
        const btn = (big && big.offsetParent !== null) ? big : document.querySelector('.j-playbtn');
        if (btn) ['pointerdown', 'mousedown', 'mouseup', 'click'].forEach(t =>
          btn.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window })));
        else { const v = document.querySelector('video'); if (v) v.play().catch(() => {}); }
      });
      await page.waitForTimeout(4000);
    }
    // 最后手段：reload（观察到的可靠恢复法）
    log('reload to recover playback');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);
    const st = await page.evaluate(() => {
      const v = document.querySelector('video');
      if (v) { v.muted = true; v.volume = 0; }
      return v ? { paused: v.paused } : null;
    });
    return !!st && !st.paused;
  };

  const setRateViaUI = async () => {
    try {
      await page.evaluate(() => {
        const btn = document.querySelector('.j-ratebtn');
        if (btn) btn.click();
      });
      await page.waitForTimeout(600);
      await page.evaluate((rate) => {
        // 倍速菜单动态渲染，首次只抓到 4 档是陷阱；按全文匹配目标档
        const li = Array.from(document.querySelectorAll('.m-popover-rate li')).find(e => e.textContent.trim() === rate);
        if (li) li.click();
        const v = document.querySelector('video');
        if (v) { v.muted = true; v.volume = 0; }
      }, RATE + '倍速');
      await page.waitForTimeout(500);
      await page.evaluate(() => { const b = document.querySelector('.j-ratebtn'); if (b) b.click(); });
    } catch (e) { log('setRate err: ' + e.message); }
  };

  // ---------- 任务发现 ----------
  const scanMatrix = () => page.evaluate(() =>
    Array.from(document.querySelectorAll('.u-learnLesson')).flatMap(ls => {
      const lesson = (ls.querySelector('h4')?.textContent || '').trim();
      return Array.from(ls.querySelectorAll('.f-icon.lsicon')).map(ic => ({
        lesson, type: ic.querySelector('.tag')?.textContent.trim(), cid: ic.getAttribute('data-cid'),
        learned: ic.classList.contains('learned'),
      }));
    }));
  const discoverTasks = async () => {
    await gotoList();
    state.matrix = await scanMatrix();
    saveState();
    const pick = (re) => state.matrix
      .filter(m => !m.learned && m.cid && re.test(m.type || ''))
      .map(m => ({ lesson: m.lesson, cid: m.cid }));
    return {
      videos: COURSE.videos?.length ? COURSE.videos : pick(/视频/),
      docs: COURSE.docs?.length ? COURSE.docs : pick(/文档/),
    };
  };

  // ---------- 视频任务 ----------
  const watchVideo = async (task) => {
    log(`VIDEO ${task.lesson} start (cid=${task.cid})`);
    await gotoList();
    if (await learned(task.cid)) { log(`VIDEO ${task.lesson} already learned, skip`); state.results.push({ ...task, type: 'video', result: 'learned-before' }); saveState(); return true; }
    await page.evaluate((cid) => {
      const ic = document.querySelector(`.f-icon.lsicon[data-cid="${cid}"]`);
      ic.click();
    }, task.cid);
    await page.waitForTimeout(4000);
    for (let i = 0; i < 8 && await page.locator('video').count() === 0; i++) await page.waitForTimeout(1500);
    if (!(await ensurePlaying())) {
      state.paused = 'video-stuck'; state.pausedDetail = `${task.lesson} 无法启动播放`;
      saveState(); return false;
    }
    await setRateViaUI();
    // 看门狗：钉静音/倍速；以 hash 切换为准判自动连播（SPA 复用 video 元素，见 knowledge §3）
    let lastT = -1, stallRounds = 0, reloads = 0;
    while (true) {
      await page.waitForTimeout(5000);
      const st = await page.evaluate(() => {
        const v = document.querySelector('video');
        if (!v) return { noVideo: true, hash: location.hash };
        if (!v.muted) { v.muted = true; v.volume = 0; }
        if (Math.abs(v.playbackRate - 2) > 0.01) v.playbackRate = 2;
        return { t: v.currentTime, ended: v.ended, paused: v.paused, hash: location.hash };
      }).catch(() => null);
      if (!st) continue;
      if (st.noVideo) {
        if (!st.hash.includes(`cid=${task.cid}`)) { log(`VIDEO ${task.lesson} hash moved (auto-next) -> done`); break; }
        if (++reloads > 3) { state.paused = 'video-lost'; state.pausedDetail = task.lesson; saveState(); return false; }
        await page.reload({ waitUntil: 'domcontentloaded' }); await page.waitForTimeout(4000);
        continue;
      }
      if (st.ended) { log(`VIDEO ${task.lesson} ended`); break; }
      if (st.paused) {
        if (!(await ensurePlaying())) { state.paused = 'video-stuck'; state.pausedDetail = task.lesson; saveState(); return false; }
        continue;
      }
      if (st.t === lastT) {
        if (++stallRounds >= 6) {
          if (++reloads > 3) { state.paused = 'video-stuck'; state.pausedDetail = task.lesson; saveState(); return false; }
          log(`VIDEO ${task.lesson} stalled, reload #${reloads}`);
          await page.reload({ waitUntil: 'domcontentloaded' }); await page.waitForTimeout(5000);
          if (!(await ensurePlaying())) { state.paused = 'video-stuck'; saveState(); return false; }
          stallRounds = 0;
        }
      } else stallRounds = 0;
      lastT = st.t;
      state.current = { ...task, type: 'video', t: Math.round(st.t) };
      state.ticks += 1;
      if (state.ticks % 12 === 0) saveState();
    }
    // 播完后回列表确认 learned（ended ≠ 已记录的教训同源，此处以平台标记为准）
    await gotoList();
    const ok = await learned(task.cid);
    log(`VIDEO ${task.lesson} learned=${ok}`);
    state.results.push({ ...task, type: 'video', result: ok ? 'learned' : 'ended-not-learned' });
    saveState();
    return true;
  };

  // ---------- 文档任务 ----------
  const doDoc = async (task) => {
    log(`DOC ${task.lesson} start (cid=${task.cid})`);
    await gotoList();
    if (await learned(task.cid)) { log(`DOC ${task.lesson} already learned`); state.results.push({ ...task, type: 'doc', result: 'learned-before' }); saveState(); return true; }
    for (let round = 1; round <= 3; round++) {
      await page.evaluate((cid) => {
        const ic = document.querySelector(`.f-icon.lsicon[data-cid="${cid}"]`);
        ic.click();
      }, task.cid);
      await page.waitForTimeout(round * 20000); // 第 1/2/3 轮各停留 20/40/60 秒
      await gotoList();
      const ok = await learned(task.cid);
      log(`DOC ${task.lesson} round ${round} learned=${ok}`);
      if (ok) { state.results.push({ ...task, type: 'doc', result: 'learned-round' + round }); saveState(); return true; }
    }
    state.results.push({ ...task, type: 'doc', result: 'not-learned-after-3-rounds' });
    saveState();
    return true;
  };

  // ---------- 主循环 ----------
  try {
    const { videos, docs } = await discoverTasks();
    log(`tasks: ${videos.length} video(s), ${docs.length} doc(s) to do`);
    if (!videos.length && !docs.length) {
      log('nothing to do (all learned)');
      state.done = true;
    } else {
      for (const t of videos) if (!await watchVideo(t)) break;
      if (!state.paused) for (const t of docs) await doDoc(t);
    }
    if (!state.paused) {
      await gotoList();
      state.matrix = await scanMatrix();
      log('ALL DONE');
      state.done = true;
    }
  } catch (e) {
    log('FATAL: ' + (e.stack || e.message).slice(0, 500));
    state.paused = 'error'; state.pausedDetail = String(e.message).slice(0, 200);
  }
  saveState();
  await ctx.close();
  log('runner exit');
}

main();
