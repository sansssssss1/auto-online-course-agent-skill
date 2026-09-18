/**
 * 学习通保活脚本 — 只读信标版（锁速课程专用 v1）
 * ------------------------------------------------------------------
 * 适用场景：教师锁定了倍速的课程（`video.playbackRate` 恒为 1，倍速控件整体隐藏）。
 * 实测依据：docs/field-notes.md 2026-09-16 条目（新版 video.js v7 播放器 + 观后题）。
 *
 * 与 scripts/keepalive.js v2.1 的关键差别（**锁速课程禁止使用 v2.1**）：
 *   - 绝不写 `playbackRate`：v2.1 会把倍速钉成 2，在锁速课程上等于变相加速 → 违反安全规则第 1/7 条
 *   - 绝不调用 `play()` / `pause()` / 合成点击：新版播放器无"无焦点暂停"行为（实测 1x 持续播放），
 *     不需要恢复；而直接驱动 video 会扰乱播放器状态机（旧版实测死锁，新版实测需验证式重试）
 *   - 只做三件事：① 保持静音；② 探测**未处理**弹题；③ 把状态写进信标
 *
 * 信标（同时写 document.title / localStorage / window.__cx，供监督者低成本轮询）：
 *   [cx]t=<当前秒>/<总秒>|p=<1暂停|0播放>|e=<1已结束>|q=<1未处理弹题>|qw=<1答错滞留层>|r=<倍速>|i=<进度停滞秒数>
 *   例：[cx]t=352/1261|p=0|e=0|q=0|qw=0|r=1|i=6
 *   - 未注入时标题不含 [cx] 前缀（监督者据此判断是否需要重注入）
 *   - `i`（idle 秒数）是**自适应巡检**的输入：i 持续增长 = 视频卡住或已结束，监督者应切短周期
 *   - `q=1` = 有未处理弹题，交监督者作答（SKILL.md §5.2 / knowledge/chaoxing.md §11.3）
 *   - `qw=1` = 存在「回答错误」滞留层：答错了但视频已自动续播，**必须重答**（重选 radio
 *     再点同一提交键即可）。v1.0 只看 `q` 会把这种情况静默漏掉——实测 1.3 踩过
 *
 * 弹题探测口径（2026-09-16 修正 + 2026-09-18 v1.1 补充）：
 *   - 容器 `.tkTopic` 已答的浮层会滞留 DOM：含「回答正确」滞留无害；含「回答错误」
 *     滞留 = 答错未重答，单独以 `qw` 上报
 *   - 仅"可见 + 无判定文字"才算未处理弹题（q）
 *   - 旧版浮层选择器（`.popups-box` / `.mark_infoDialog` / `[class*="popups"]`）一并兜底
 *
 * 用法：在**顶层文档**执行一次（F12 控制台粘贴；整页跳转后需重注入）。
 * 只读不控制，因此可安全地与其他只读探针共存。
 */
(function () {
  if (window.__cxBeacon) return;
  window.__cxBeacon = true;

  var TICK_MS = 3000;
  var LEGACY_POPUP_SEL = ['.popups-box', '.mark_infoDialog', '[class*="popups"]'];

  // 广度优先收集顶层文档可达的同源子文档（播放器在嵌套 iframe 内）
  function collectDocs() {
    var docs = [document];
    for (var i = 0; i < docs.length; i++) {
      try {
        var frames = docs[i].querySelectorAll('iframe');
        for (var j = 0; j < frames.length; j++) {
          try {
            var cd = frames[j].contentDocument;
            if (cd && docs.indexOf(cd) === -1) docs.push(cd);
          } catch (e) { /* 跨域，跳过 */ }
        }
      } catch (e) { /* 防御 */ }
    }
    return docs;
  }

  function visible(el) {
    try {
      var st = el.ownerDocument.defaultView.getComputedStyle(el);
      return st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null;
    } catch (e) { return false; }
  }

  // 弹题探测（v1.1 修正口径）：
  //   unhandled     = 未处理弹题（.tkTopic 可见且不含判定文字）→ 监督者需作答
  //   answeredWrong = 存在含「回答错误/回答不完整」的滞留层 → 答错了但视频已自动续播，
  //                   **必须重答**（实测直接重选 radio 再点同一提交键即可）
  //   含「回答正确」的滞留层无害，忽略。旧版浮层可见即算 unhandled。
  function detectPopup(docs) {
    var r = { unhandled: false, answeredWrong: false };
    for (var i = 0; i < docs.length; i++) {
      try {
        var topics = docs[i].querySelectorAll('.tkTopic');
        for (var k = 0; k < topics.length; k++) {
          var el = topics[k];
          if (!visible(el)) continue;
          var txt = (el.innerText || '').trim();
          if (/回答错误|回答不完整/.test(txt)) r.answeredWrong = true;
          else if (/回答正确/.test(txt)) { /* 已答对，滞留无害 */ }
          else r.unhandled = true;
        }
      } catch (e) { /* 防御 */ }
      for (var j = 0; j < LEGACY_POPUP_SEL.length; j++) {
        try {
          var els = docs[i].querySelectorAll(LEGACY_POPUP_SEL[j]);
          for (var m = 0; m < els.length; m++) {
            if (visible(els[m])) { r.unhandled = true; }
          }
        } catch (e) { /* 防御 */ }
      }
    }
    return r;
  }

  function findVideo(docs) {
    for (var i = 0; i < docs.length; i++) {
      try { var v = docs[i].querySelector('video'); if (v) return v; } catch (e) { /* 防御 */ }
    }
    return null;
  }

  var lastTime = null, lastChangeAt = Date.now();

  function tick() {
    var s = {
      ts: Date.now(), hasVideo: false, t: null, d: null,
      paused: null, ended: false, rate: null, muted: null,
      quizPopup: false, quizWrong: false, idleSec: 0, error: null,
    };
    try {
      var docs = collectDocs();
      var video = findVideo(docs);
      if (video) {
        s.hasVideo = true;
        try {
          // 只做静音保持；不碰 play/pause/playbackRate
          if (!video.muted) video.muted = true;
          s.t = video.currentTime; s.d = video.duration;
          s.paused = video.paused; s.ended = !!video.ended;
          s.rate = video.playbackRate; s.muted = video.muted;
        } catch (e) { /* 防御 */ }
      }
      var pop = detectPopup(docs);
      s.quizPopup = pop.unhandled;
      s.quizWrong = pop.answeredWrong;

      // idle：进度是否还在推进（自适应巡检的核心输入）
      if (s.t !== null) {
        if (lastTime === null || Math.abs(s.t - lastTime) > 0.05) {
          lastTime = s.t; lastChangeAt = Date.now();
        }
        s.idleSec = Math.round((Date.now() - lastChangeAt) / 1000);
      }
    } catch (e) {
      s.error = String(e);
    }

    window.__cx = s;
    var beacon = '[cx]t=' + (s.t === null ? '-' : Math.round(s.t)) +
      '/' + (s.d === null || !isFinite(s.d) ? '-' : Math.round(s.d)) +
      '|p=' + (s.paused === null ? '-' : (s.paused ? 1 : 0)) +
      '|e=' + (s.ended ? 1 : 0) +
      '|q=' + (s.quizPopup ? 1 : 0) +
      '|qw=' + (s.quizWrong ? 1 : 0) +
      '|r=' + (s.rate === null ? '-' : s.rate) +
      '|i=' + s.idleSec;
    window.__cxBeaconText = beacon;
    try { document.title = beacon; } catch (e) { /* 防御 */ }
    try { localStorage.setItem('cx:beacon', beacon); } catch (e) { /* 防御 */ }
  }

  tick();
  setInterval(tick, TICK_MS);
})();
