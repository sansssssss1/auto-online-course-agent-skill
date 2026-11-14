/* Read-only function for supported evaluate or public CDP Runtime.evaluate.
 * No writes, timers, playback control, requests, focus/visibility overrides.
 * Pass the previous successful summary as options.previous to omit unchanged
 * popup text. Its digest compresses output only; it never authorizes actions
 * or replaces the current chapter/cards/object/full-source-path checks.
 * DOM visibility does not establish native window minimization or focus. */
(function observeCourseVideo(options = {}) {
  let identity = null, summary = null, details = null;
  const abort = code => { throw { observationCode: code }; };
  const frameDocument = frame => {
    try { return frame.contentDocument; } catch { return null; }
  };
  const digest = value => {
    let a = 2166136261, b = 5381;
    for (let index = 0; index < value.length; index++) {
      const code = value.charCodeAt(index);
      a = Math.imul(a ^ code, 16777619); b = Math.imul(b, 33) ^ code;
    }
    return (a >>> 0).toString(16).padStart(8, '0') + (b >>> 0).toString(16).padStart(8, '0');
  };
  function readIdentity() {
    const page = new URL(document.URL || document.documentURI || '');
    if (page.protocol !== 'https:' || page.pathname !== '/mycourse/studentstudy' ||
        !(page.hostname === 'chaoxing.com' || page.hostname.endsWith('.chaoxing.com'))) abort('WRONG_COURSE_PAGE');
    const chapters = page.searchParams.getAll('chapterId');
    if (chapters.length !== 1 || chapters[0] !== options.expected_chapter_id) abort('CHAPTER_MISMATCH');
    const outers = Array.from(document.querySelectorAll('#iframe'));
    if (outers.length !== 1 || String(outers[0].tagName).toUpperCase() !== 'IFRAME') abort('OUTER_FRAME_NOT_UNIQUE');
    const outer = outers[0], course = frameDocument(outer);
    if (!course) abort('OUTER_FRAME_UNAVAILABLE');
    const cards = new URL(course.URL || course.documentURI || '');
    if (cards.origin !== page.origin || !['/knowledge/cards', '/mooc-ans/knowledge/cards'].includes(cards.pathname)) abort('CARDS_DOCUMENT_MISMATCH');
    const knowledge = cards.searchParams.getAll('knowledgeid');
    if (knowledge.length !== 1 || knowledge[0] !== options.expected_chapter_id) abort('CARDS_CHAPTER_MISMATCH');
    const inners = Array.from(course.querySelectorAll('iframe.ans-insertvideo-online'));
    if (inners.length !== 1 || String(inners[0].tagName).toUpperCase() !== 'IFRAME') abort('VIDEO_FRAME_NOT_UNIQUE');
    const inner = inners[0];
    let attachment;
    try { attachment = JSON.parse(inner.getAttribute('data') || ''); }
    catch { abort('ATTACHMENT_DATA_UNREADABLE'); }
    if (!attachment || attachment.objectid !== options.expected_object_id) abort('ATTACHMENT_OBJECT_MISMATCH');
    const media = frameDocument(inner);
    if (!media) abort('VIDEO_FRAME_UNAVAILABLE');
    const mediaPage = new URL(media.URL || media.documentURI || '');
    if (mediaPage.origin !== page.origin || mediaPage.pathname !== '/ananas/modules/video/index.html') abort('VIDEO_DOCUMENT_MISMATCH');
    const videos = Array.from(media.querySelectorAll('video'));
    if (videos.length !== 1 || videos[0].ownerDocument !== media) abort('VIDEO_NOT_UNIQUE');
    const video = videos[0], rawSource = video.currentSrc || video.src;
    if (typeof rawSource !== 'string' || !rawSource.trim()) abort('MEDIA_SOURCE_UNAVAILABLE');
    const source = new URL(rawSource, mediaPage);
    if (!source.pathname.split('/').some(part => {
      try { return decodeURIComponent(part) === options.expected_object_id; } catch { return false; }
    })) abort('MEDIA_OBJECT_MISMATCH');
    if (source.pathname !== options.expected_source_path) abort('MEDIA_SOURCE_PATH_MISMATCH');
    return { outer, course, inner, media, video };
  }
  function visible(node) {
    if (!node || node.ownerDocument !== identity.media) abort('QUIZ_DOCUMENT_MISMATCH');
    const view = identity.media.defaultView;
    if (!view || typeof view.getComputedStyle !== 'function') abort('QUIZ_VISIBILITY_UNAVAILABLE');
    for (let current = node; current; current = current.parentElement) {
      const css = view.getComputedStyle(current);
      if (!css || ['display', 'visibility', 'opacity'].some(key => typeof css[key] !== 'string')) abort('QUIZ_VISIBILITY_UNAVAILABLE');
      if (css.display === 'none' || css.visibility === 'hidden' || css.visibility === 'collapse' || String(css.opacity) === '0') return false;
    }
    const rect = node.getBoundingClientRect();
    if (!rect || !Number.isFinite(rect.width) || !Number.isFinite(rect.height)) abort('QUIZ_VISIBILITY_UNAVAILABLE');
    return rect.width > 0 && rect.height > 0;
  }
  const text = node => {
    if (typeof node.innerText !== 'string') abort('QUIZ_TEXT_UNREADABLE');
    return node.innerText.trim();
  };
  function readQuiz() {
    const roots = Array.from(identity.media.querySelectorAll('.tkTopic')).filter(visible);
    if (!roots.length) return { visible: false, state: 'absent' };
    if (roots.length !== 1) abort('QUIZ_NOT_UNIQUE');
    const root = roots[0];
    const singleText = selector => {
      const nodes = Array.from(root.querySelectorAll(selector)).filter(visible);
      if (nodes.length !== 1) abort('QUIZ_TEXT_NOT_UNIQUE');
      return text(nodes[0]);
    };
    details = { type: singleText('.tkTopic_title'), question: singleText('.tkItem_title'), options: [] };
    if (!details.type || !details.question) abort('QUIZ_TEXT_UNREADABLE');
    const rows = Array.from(root.querySelectorAll('li.ans-videoquiz-opt')).filter(visible);
    if (rows.length < 2) abort('QUIZ_OPTIONS_UNREADABLE');
    for (const row of rows) {
      const inputs = Array.from(row.querySelectorAll('input[name="ans-videoquiz-opt"]'));
      if (inputs.length !== 1 || inputs[0].ownerDocument !== identity.media || String(inputs[0].tagName).toUpperCase() !== 'INPUT' ||
          !['radio', 'checkbox'].includes(inputs[0].type) || typeof inputs[0].checked !== 'boolean') abort('QUIZ_INPUT_UNREADABLE');
      const displayed = text(row);
      if (!displayed) abort('QUIZ_OPTIONS_UNREADABLE');
      details.options.push({ text: displayed, checked: inputs[0].checked,
        disabled: inputs[0].disabled === true || inputs[0].getAttribute('disabled') !== null || inputs[0].getAttribute('aria-disabled') === 'true' });
    }
    const controls = {};
    for (const name of ['submit', 'submitting', 'continue']) {
      const nodes = Array.from(identity.media.querySelectorAll('#videoquiz-' + name)).filter(visible);
      if (nodes.length > 1 || nodes.some(node => !root.contains(node) || !['A', 'BUTTON'].includes(String(node.tagName).toUpperCase()))) abort('QUIZ_CONTROL_NOT_UNIQUE');
      controls[name] = nodes.length === 1;
      controls[name + '_disabled'] = nodes.length === 1 && (nodes[0].disabled === true || nodes[0].getAttribute('disabled') !== null || nodes[0].getAttribute('aria-disabled') === 'true');
    }
    const countNodes = Array.from(root.querySelectorAll('#rightNum')).filter(visible);
    const verdictSets = ['#spanHas', '#spanNot', '#spanNotBack'].map(selector => Array.from(root.querySelectorAll(selector)));
    const verdictContract = verdictSets.every(nodes => nodes.length === 1 && nodes[0].ownerDocument === identity.media) &&
      text(verdictSets[0][0]) === '回答正确' && text(verdictSets[1][0]) === '回答错误' && text(verdictSets[2][0]).startsWith('回答错误，回看');
    const visibleVerdicts = verdictContract ? verdictSets.flatMap((nodes, index) => visible(nodes[0]) ? [index] : []) : [];
    if (visibleVerdicts.length > 1) abort('QUIZ_VERDICT_AMBIGUOUS');
    const verdict = visibleVerdicts.length ? (visibleVerdicts[0] === 0 ? 'correct' : 'wrong') : null;
    let rightNum = null;
    if (countNodes.length) {
      if (countNodes.length !== 1 || !/^\d+$/.test(text(countNodes[0]))) abort('QUIZ_COUNT_UNREADABLE');
      rightNum = Number(text(countNodes[0]));
      if (!Number.isSafeInteger(rightNum)) abort('QUIZ_COUNT_UNREADABLE');
    } else if (!verdictContract) abort('QUIZ_COUNT_UNREADABLE');
    const stage = verdict === 'correct' && !controls.submitting && !controls.continue ? 'result' :
      verdict === 'wrong' && controls.submit && !controls.submitting && !controls.continue ? 'retry' :
      controls.submit && !controls.submitting && !controls.continue ? 'question' :
      controls.submitting && !controls.submit && !controls.continue ? 'submitting' :
      !controls.submit && !controls.submitting && (controls.continue || verdict !== null) ? 'result' : 'unknown';
    return { visible: true, state: stage, right_num: rightNum, result_mode: rightNum === null ? 'verdict' : 'count', verdict,
      signature: digest(JSON.stringify([details, controls, rightNum, verdict])) };
  }
  try {
    if (!options || typeof options.expected_chapter_id !== 'string' || !/^\d+$/.test(options.expected_chapter_id)) abort('EXPECTED_CHAPTER_REQUIRED');
    if (typeof options.expected_object_id !== 'string' || !options.expected_object_id.trim()) abort('EXPECTED_OBJECT_REQUIRED');
    if (typeof options.expected_source_path !== 'string' || !options.expected_source_path.startsWith('/') || /[?#]/.test(options.expected_source_path)) abort('EXPECTED_SOURCE_PATH_REQUIRED');
    identity = readIdentity();
    const video = identity.video;
    const number = value => Number.isFinite(value) ? Math.round(value * 1000) / 1000 : null;
    const visibility = doc => typeof doc.visibilityState === 'string' ? doc.visibilityState : null;
    const mediaError = video.error;
    summary = { ok: true, identity_ok: true,
      scope: digest(JSON.stringify([options.expected_chapter_id, options.expected_object_id, options.expected_source_path])),
      time: number(video.currentTime), duration: number(video.duration),
      paused: video.paused, muted: video.muted, rate: video.playbackRate, ended: video.ended,
      error: mediaError ? { media_code: Number.isInteger(mediaError.code) ? mediaError.code : null } : null,
      visibility: { page: visibility(document), video: visibility(identity.media) },
      quiz: { visible: null, state: 'unreadable' } };
    if (['paused', 'muted', 'ended'].some(key => typeof summary[key] !== 'boolean') || !Number.isFinite(summary.rate)) abort('MEDIA_STATE_UNREADABLE');
    summary.quiz = readQuiz();
    const after = readIdentity();
    if (['outer', 'course', 'inner', 'media', 'video'].some(key => after[key] !== identity[key])) abort('MEDIA_DOCUMENT_REPLACED');
    const diagnostics = [];
    if (summary.error) diagnostics.push('MEDIA_ERROR');
    if (!summary.muted) diagnostics.push('MEDIA_NOT_MUTED');
    if (summary.rate !== 1) diagnostics.push('PLAYBACK_RATE_NOT_ONE');
    if (summary.time === null || summary.duration === null) diagnostics.push('MEDIA_METADATA_UNAVAILABLE');
    if (summary.paused && !summary.ended && !summary.quiz.visible) diagnostics.push('PAUSED_WITHOUT_QUIZ');
    if (summary.visibility.page === null || summary.visibility.video === null) diagnostics.push('DOM_VISIBILITY_UNAVAILABLE');
    if (summary.quiz.state === 'unknown') diagnostics.push('QUIZ_STATE_UNKNOWN');
    const previous = options.previous;
    const unchanged = previous && previous.ok === true && previous.identity_ok === true && previous.scope === summary.scope &&
      previous.quiz && previous.quiz.visible === true && previous.quiz.state === summary.quiz.state && previous.quiz.signature === summary.quiz.signature;
    if (details && (!unchanged || diagnostics.length)) summary.details = details;
    if (diagnostics.length) summary.diagnostics = diagnostics;
    return summary;
  } catch (error) {
    const code = error && error.observationCode || 'OBSERVATION_READ_FAILED';
    // A read failure is never equivalent to no popup. Do not reuse old values.
    if (summary && code.startsWith('QUIZ_')) {
      return { ...summary, ok: false, error: { code }, quiz: { visible: null, state: 'unreadable' },
        diagnostics: [code], ...(details ? { details } : {}) };
    }
    return { ok: false, identity_ok: false, error: { code }, diagnostics: [code] };
  }
})
