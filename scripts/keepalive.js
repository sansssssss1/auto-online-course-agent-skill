/**
 * 学习通视频保活脚本 v2.1（独立版）
 * ------------------------------------------------------------------
 * 行为均经 2026-09-11/12 真实账号全流程实测验证（65/65 任务点跑通）。
 * 实测记录见 docs/field-notes.md；页面知识见 knowledge/chaoxing.md。
 *
 * 用法：在 studentstudy 播放页的顶层文档执行一次（console 粘贴或 agent 页面执行 JS）。
 * 整页跳转（点"下一节"）后脚本会丢失，需要重新注入。
 *
 * 组成（两者都必须装，onboard 缺一不可）：
 *   v2 保活：每 3 秒穿透 iframe 链找 <video>，钉 muted=true、playbackRate=2（官方最高档），
 *            无条件尝试 play()（勿改回"等 readyState"——preload="none" 会死锁），
 *            检测弹题浮层，状态写 window.__cx
 *   v3 事件恢复：给 video 挂 pause 监听 → 立即重播（1.5 秒限流，ended/弹题让行）。
 *            实测依据：页面无焦点时播放器主动暂停，且 setInterval 被浏览器节流，
 *            定时器方案失效，事件监听不受节流影响（~0.2x 恢复 2.0x）
 *
 * 已知边界：OS 锁屏（Win+L）下暂停来自原生层（毫秒级），页面脚本无法对抗，
 *           需监督者侧 3.5 秒高频踢循环（见 field-notes 熄屏/锁屏协议）。
 *
 * 设计约束：只做确定性动作，不做任何决策；异常一律写进 __cx 交监督者。
 */
(function () {
  if (window.__cxKeepalive) return;
  window.__cxKeepalive = true;

  var TICK_MS = 3000;
  var RATE = 2; // 播放器官方最高档，勿超
  var RESUME_THROTTLE_MS = 1500;

  // 广度优先收集顶层文档可达的所有同源子文档
  function collectDocs() {
    var docs = [document];
    for (var i = 0; i < docs.length; i++) {
      var d = docs[i];
      try {
        var frames = d.querySelectorAll('iframe');
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

  function findVideo(doc) {
    try { return doc.querySelector('video'); } catch (e) { return null; }
  }

  // v3 事件驱动恢复：pause 监听不受定时器节流影响（每个 video 只挂一次）
  function attachRecovery(video) {
    if (video.__cx3) return;
    video.__cx3 = true;
    video.addEventListener('pause', function () {
      try {
        if (video.ended) return;                        // 播完让行
        if (window.__cx && window.__cx.quizPopup) return; // 弹题让行，交监督者
        var now = Date.now();
        if (now - (video.__cx3Last || 0) < RESUME_THROTTLE_MS) return; // 限流
        video.__cx3Last = now;
        video.play().catch(function () {});
      } catch (e) { /* 防御 */ }
    });
  }

  // 弹题/弹窗浮层：可见即视为有弹题（选择器来自实测 + 常见变体）
  function quizPopupVisible(docs) {
    var sel = ['.popups-box', '.mark_infoDialog', '[class*="popups"]'];
    for (var i = 0; i < docs.length; i++) {
      for (var j = 0; j < sel.length; j++) {
        try {
          var els = docs[i].querySelectorAll(sel[j]);
          for (var k = 0; k < els.length; k++) {
            var el = els[k];
            var st = el.ownerDocument.defaultView.getComputedStyle(el);
            if (st.display !== 'none' && st.visibility !== 'hidden' &&
                el.offsetParent !== null) {
              return true;
            }
          }
        } catch (e) { /* 防御 */ }
      }
    }
    return false;
  }

  function tick() {
    var state = {
      ts: Date.now(),
      time: null, dur: null, ended: false,
      hasVideo: false, quizPopup: false,
      rate: null, muted: null
    };
    try {
      var docs = collectDocs();
      var video = null;
      for (var i = 0; i < docs.length; i++) {
        var v = findVideo(docs[i]);
        if (v) { video = v; break; }
      }
      if (video) {
        state.hasVideo = true;
        attachRecovery(video);
        try {
          if (!video.muted) video.muted = true;
          if (video.playbackRate !== RATE) video.playbackRate = RATE;
          if (video.paused) video.play().catch(function () {});
        } catch (e) { /* 防御 */ }
        try {
          state.time = video.currentTime;
          state.dur = video.duration;
          state.ended = !!video.ended;
          state.rate = video.playbackRate;
          state.muted = video.muted;
        } catch (e) { /* 防御 */ }
      }
      state.quizPopup = quizPopupVisible(docs);
      if (state.quizPopup) {
        // 有弹题时不代答、不恢复播放，交监督者（见 SKILL.md 异常手册）
        try { if (video && video.paused) video.pause(); } catch (e) { /* 防御 */ }
      }
    } catch (e) {
      state.error = String(e);
    }
    window.__cx = state;
  }

  tick();
  setInterval(tick, TICK_MS);
})();
