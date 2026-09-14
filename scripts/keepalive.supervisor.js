/**
 * 学习通保活脚本 — 监督者运行时版（v2.1 + 标题信标）
 * ------------------------------------------------------------------
 * 基于 scripts/keepalive.js v2.1（65/65 实测版），仅新增一处：
 * 每个 tick 把播放状态写进 document.title（窗口标题信标），
 * 供监督者用低成本窗口枚举轮询，无需截图即可读进度。
 * 信标格式：[cx]t秒/d秒 |ENDED |QUIZ |NOVIDEO；未注入时标题无 [cx] 前缀。
 * 其余行为与 v2.1 完全一致：muted=true、2x、无条件 play()、
 * 弹题暂停交监督者、pause 事件恢复（1.5s 限流）。整页跳转后需重注入。
 */
(function () {
  if (window.__cxKeepalive) return;
  window.__cxKeepalive = true;

  var TICK_MS = 3000;
  var RATE = 2;
  var RESUME_THROTTLE_MS = 1500;

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
          } catch (e) {}
        }
      } catch (e) {}
    }
    return docs;
  }

  function findVideo(doc) {
    try { return doc.querySelector('video'); } catch (e) { return null; }
  }

  function attachRecovery(video) {
    if (video.__cx3) return;
    video.__cx3 = true;
    video.addEventListener('pause', function () {
      try {
        if (video.ended) return;
        if (window.__cx && window.__cx.quizPopup) return;
        var now = Date.now();
        if (now - (video.__cx3Last || 0) < RESUME_THROTTLE_MS) return;
        video.__cx3Last = now;
        video.play().catch(function () {});
      } catch (e) {}
    });
  }

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
        } catch (e) {}
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
        } catch (e) {}
        try {
          state.time = video.currentTime;
          state.dur = video.duration;
          state.ended = !!video.ended;
          state.rate = video.playbackRate;
          state.muted = video.muted;
        } catch (e) {}
      }
      state.quizPopup = quizPopupVisible(docs);
      if (state.quizPopup) {
        try { if (video && video.paused) video.pause(); } catch (e) {}
      }
    } catch (e) {
      state.error = String(e);
    }
    window.__cx = state;
    try {
      document.title = '[cx]' +
        (state.time != null ? Math.floor(state.time) + '/' + (state.dur ? Math.floor(state.dur) : '?') : 'novideo') +
        (state.ended ? '|ENDED' : '') +
        (state.quizPopup ? '|QUIZ' : '') +
        (state.error ? '|ERR' : '');
    } catch (e) {}
  }

  tick();
  setInterval(tick, TICK_MS);
})();
