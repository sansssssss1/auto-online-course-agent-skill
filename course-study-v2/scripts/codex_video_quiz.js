/* Writable public CDP Runtime.evaluate only; never use read-only evaluate.
 * Narrow single-choice Chaoxing video popup, not homework/chapter exams.
 * Expected text is visible innerText.trim(), preserving internal whitespace.
 * Options are bound by their displayed order: input values may all be empty.
 * A private Symbol on the popup blocks repeat submit/continue attempts on the
 * same DOM question, even if click throws. A replaced document still requires
 * caller-side reconciliation; never retry an attempted action blindly. */
(function courseVideoQuiz(options = {}) {
  let action = 'inspect', identity = null, before = null, after = null;
  let attempted = false, clicked = false, verifiedAfter = false;
  let selector = null;
  const abort = code => { throw { quizGuardCode: code }; };
  const frameDocument = frame => {
    try { return frame.contentDocument; } catch { return null; }
  };
  const state = video => ({ muted: video.muted, defaultMuted: video.defaultMuted,
    paused: video.paused, playbackRate: video.playbackRate,
    currentTime: Number.isFinite(video.currentTime) ? video.currentTime : null });
  const result = (ok, code = null) => ({ ok, ...(code ? { error: { code } } : {}), action,
    media_key: identity ? identity.key : null, action_attempted: attempted,
    control_clicked: clicked, control_selector: selector,
    identity_verified_after: verifiedAfter, before, after,
    submission_status: action === 'submit' && attempted ?
      (after && after.state === 'result' ? 'result-visible' : 'unconfirmed') : 'not-submitted' });
  function readIdentity(previous = null) {
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
    const found = { outer, course, inner, media, video,
      key: { chapter_id: chapters[0], object_id: attachment.objectid, source_path: source.pathname } };
    if (previous && ['outer', 'course', 'inner', 'media', 'video'].some(key => found[key] !== previous[key])) abort('MEDIA_DOCUMENT_REPLACED');
    return found;
  }
  function visible(node, media) {
    if (!node || node.ownerDocument !== media) return false;
    const view = media.defaultView;
    if (!view || typeof view.getComputedStyle !== 'function') abort('VISIBILITY_UNAVAILABLE');
    for (let current = node; current; current = current.parentElement) {
      const css = view.getComputedStyle(current);
      if (!css) abort('VISIBILITY_UNAVAILABLE');
      if (css.display === 'none' || css.visibility === 'hidden' || css.visibility === 'collapse' || String(css.opacity) === '0') return false;
    }
    const rect = node.getBoundingClientRect();
    return !!rect && rect.width > 0 && rect.height > 0;
  }
  const text = node => {
    if (typeof node.innerText !== 'string') abort('VISIBLE_TEXT_UNAVAILABLE');
    return node.innerText.trim();
  };
  const disabled = node => node.disabled === true || node.getAttribute('disabled') !== null || node.getAttribute('aria-disabled') === 'true';
  function readQuiz(found) {
    const media = found.media;
    const roots = Array.from(media.querySelectorAll('.tkTopic')).filter(node => visible(node, media));
    if (!roots.length) return { root: null, inputs: [], snapshot: { state: 'absent', video: state(found.video) } };
    if (roots.length !== 1) abort('QUIZ_NOT_UNIQUE');
    const root = roots[0];
    function singleText(selector) {
      const nodes = Array.from(root.querySelectorAll(selector)).filter(node => visible(node, media));
      if (nodes.length !== 1) abort('QUESTION_TEXT_NOT_UNIQUE');
      return text(nodes[0]);
    }
    const question = singleText('.tkItem_title'), type = singleText('.tkTopic_title');
    if (question !== options.expected_question || type !== options.expected_type) abort('QUESTION_MISMATCH');
    const rows = Array.from(root.querySelectorAll('li.ans-videoquiz-opt')).filter(node => visible(node, media));
    if (rows.length !== options.expected_options.length || rows.some((row, index) => text(row) !== options.expected_options[index])) abort('OPTIONS_MISMATCH');
    const inputs = rows.map(row => {
      const matches = Array.from(row.querySelectorAll('input[name="ans-videoquiz-opt"]'));
      if (matches.length !== 1 || matches[0].ownerDocument !== media || String(matches[0].tagName).toUpperCase() !== 'INPUT' ||
          matches[0].type !== 'radio') abort('OPTION_INPUT_NOT_UNIQUE');
      return matches[0];
    });
    if (new Set(inputs).size !== inputs.length || new Set(inputs.map(input => input.type)).size !== 1) abort('OPTION_INPUT_NOT_UNIQUE');
    const countNodes = Array.from(root.querySelectorAll('#rightNum')).filter(node => visible(node, media));
    const verdictSets = ['#spanHas', '#spanNot', '#spanNotBack'].map(selector => Array.from(root.querySelectorAll(selector)));
    const verdictContract = verdictSets.every(nodes => nodes.length === 1 && nodes[0].ownerDocument === media) &&
      text(verdictSets[0][0]) === '回答正确' && text(verdictSets[1][0]) === '回答错误' && text(verdictSets[2][0]).startsWith('回答错误，回看');
    const visibleVerdicts = verdictContract ? verdictSets.flatMap((nodes, index) => visible(nodes[0], media) ? [index] : []) : [];
    if (visibleVerdicts.length > 1) abort('RESULT_VERDICT_AMBIGUOUS');
    const verdict = visibleVerdicts.length ? (visibleVerdicts[0] === 0 ? 'correct' : 'wrong') : null;
    let rightNum = null;
    if (countNodes.length) {
      if (countNodes.length !== 1 || !/^\d+$/.test(text(countNodes[0]))) abort('RESULT_COUNT_UNREADABLE');
      rightNum = Number(text(countNodes[0]));
      if (!Number.isSafeInteger(rightNum)) abort('RESULT_COUNT_UNREADABLE');
    } else if (!verdictContract) abort('RESULT_COUNT_UNREADABLE');
    function control(controlSelector) {
      const nodes = Array.from(media.querySelectorAll(controlSelector)).filter(node => visible(node, media));
      if (nodes.length > 1 || nodes.some(node => !root.contains(node) || !['A', 'BUTTON'].includes(String(node.tagName).toUpperCase()))) abort('CONTROL_NOT_UNIQUE');
      return nodes[0] || null;
    }
    const submit = control('#videoquiz-submit'), continuing = control('#videoquiz-continue'), submitting = control('#videoquiz-submitting');
    const stage = verdict === 'correct' && !continuing && !submitting ? 'result' :
      verdict === 'wrong' && submit && !continuing && !submitting ? 'retry' :
      submit && !continuing && !submitting ? 'question' :
      !submit && !submitting && (continuing || verdict !== null) ? 'result' :
      submitting && !submit && !continuing ? 'submitting' : 'unknown';
    return { root, inputs, submit, continuing, snapshot: { state: stage, question, type,
      options: rows.map((row, index) => ({ index, text: text(row), checked: inputs[index].checked === true, disabled: disabled(inputs[index]) })),
      selected_indices: inputs.flatMap((input, index) => input.checked === true ? [index] : []),
      right_num: rightNum, result_mode: rightNum === null ? 'verdict' : 'count', verdict,
      can_continue: !!continuing, video: state(found.video) } };
  }
  function verifyMediaState(found) {
    if (found.video.muted !== true || found.video.defaultMuted !== true) abort('MEDIA_NOT_MUTED');
    if (found.video.playbackRate !== 1) abort('PLAYBACK_RATE_NOT_ONE');
  }
  function expectedSelection(count) {
    const indices = options.expected_selected_indices;
    if (!Array.isArray(indices) || !indices.length || indices.some(index => !Number.isInteger(index) || index < 0 || index >= count) || new Set(indices).size !== indices.length) abort('EXPECTED_SELECTION_REQUIRED');
    return [...indices].sort((a, b) => a - b);
  }
  const sameIndices = (left, right) => left.length === right.length && left.every((value, index) => value === right[index]);
  try {
    if (!options || typeof options.expected_chapter_id !== 'string' || !/^\d+$/.test(options.expected_chapter_id)) abort('EXPECTED_CHAPTER_REQUIRED');
    if (typeof options.expected_object_id !== 'string' || !options.expected_object_id.trim()) abort('EXPECTED_OBJECT_REQUIRED');
    if (typeof options.expected_source_path !== 'string' || !options.expected_source_path.startsWith('/') || /[?#]/.test(options.expected_source_path)) abort('EXPECTED_SOURCE_PATH_REQUIRED');
    if (typeof options.expected_question !== 'string' || !options.expected_question.trim() || typeof options.expected_type !== 'string' || !options.expected_type.trim()) abort('EXPECTED_QUESTION_REQUIRED');
    if (!Array.isArray(options.expected_options) || options.expected_options.length < 2 || options.expected_options.some(item => typeof item !== 'string' || !item.trim()) || new Set(options.expected_options).size !== options.expected_options.length) abort('EXPECTED_OPTIONS_REQUIRED');
    action = options.action === undefined ? 'inspect' : options.action;
    if (!['inspect', 'select', 'submit', 'continue'].includes(action)) abort('INVALID_ACTION');
    identity = readIdentity();
    const quiz = readQuiz(identity);
    before = quiz.snapshot;
    if (action === 'inspect') {
      readIdentity(identity); verifiedAfter = true; after = before;
      return result(true);
    }
    verifyMediaState(identity);
    if (!quiz.root) abort('QUIZ_NOT_VISIBLE');
    if (before.result_mode === 'verdict') {
      if (options.expected_right_num !== null) abort('RESULT_COUNT_MISMATCH');
      if (action === 'continue' && (!['correct', 'wrong'].includes(options.expected_verdict) || options.expected_verdict !== before.verdict)) abort('RESULT_VERDICT_MISMATCH');
    } else if (!Number.isSafeInteger(options.expected_right_num) || options.expected_right_num < 0 || options.expected_right_num !== before.right_num) abort('RESULT_COUNT_MISMATCH');
    const expected = expectedSelection(quiz.inputs.length);
    if (expected.length !== 1) abort('EXPECTED_SELECTION_INVALID');
    let control;
    if (action === 'select') {
      if (before.state !== 'question') abort('QUIZ_NOT_PENDING');
      if (!Number.isInteger(options.select_index) || !expected.includes(options.select_index)) abort('SELECT_INDEX_INVALID');
      control = quiz.inputs[options.select_index]; selector = 'input[name="ans-videoquiz-opt"]';
      if (control.checked === true) {
        if (!sameIndices(before.selected_indices, expected)) abort('SELECTED_SET_MISMATCH');
        readIdentity(identity); verifiedAfter = true; after = before;
        return result(true);
      }
    } else {
      if (!sameIndices(before.selected_indices, expected)) abort('SELECTED_SET_MISMATCH');
      if (action === 'submit' && before.state !== 'question') abort('QUIZ_NOT_PENDING');
      if (action === 'continue' && before.state !== 'result') abort('QUIZ_RESULT_NOT_CONFIRMED');
      control = action === 'submit' ? quiz.submit : quiz.continuing;
      selector = action === 'submit' ? '#videoquiz-submit' : '#videoquiz-continue';
    }
    if (!control || disabled(control)) abort('CONTROL_DISABLED');
    if (typeof control.click !== 'function') abort('CONTROL_UNAVAILABLE');
    // This local DOM receipt deliberately survives a later Runtime.evaluate.
    // It never marks a submission as accepted and never changes platform state.
    const marker = Symbol.for('course-study-v2.codex-videoquiz.attempts.v1');
    const fingerprint = JSON.stringify([identity.key, options.expected_type, options.expected_question, options.expected_options]);
    if (action !== 'select') {
      let receipt = quiz.root[marker];
      if (!receipt) {
        receipt = new Set();
        try { Object.defineProperty(quiz.root, marker, { value: receipt }); }
        catch { abort('ACTION_GUARD_UNAVAILABLE'); }
      }
      if (!(receipt instanceof Set)) abort('ACTION_GUARD_UNAVAILABLE');
      const key = action + ':' + fingerprint;
      if (receipt.has(key)) abort('ACTION_ALREADY_ATTEMPTED');
      receipt.add(key);
    }
    attempted = true;
    let clickFailed = false;
    try { control.click(); clicked = true; } catch { clickFailed = true; }
    try { readIdentity(identity); verifiedAfter = true; }
    catch { abort('POST_ACTION_IDENTITY_MISMATCH'); }
    verifyMediaState(identity);
    const current = readQuiz(identity);
    after = current.snapshot;
    if (clickFailed) abort('CONTROL_CLICK_FAILED');
    if (action === 'select' && (current.root !== quiz.root || current.inputs[options.select_index] !== control)) abort('QUIZ_REPLACED');
    if (action === 'select' && !sameIndices(after.selected_indices || [], expected)) abort('SELECTION_NOT_CONFIRMED');
    if (action === 'submit' && current.root && current.root !== quiz.root) abort('QUIZ_REPLACED');
    return result(true);
  } catch (error) {
    // Never return arbitrary page exception text, URLs, cookies, or signatures.
    return result(false, error && error.quizGuardCode || 'PAGE_READ_FAILED');
  }
})
