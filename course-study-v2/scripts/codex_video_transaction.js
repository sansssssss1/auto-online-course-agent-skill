/* Public writable CDP only. Compose the existing identity guards as helpers;
 * never serialise caller-supplied page code. No playback/progress API writes.
 * Timers are bounded per call, not a persistent background executor. */
(async function videoTransaction(helpers, options = {}) {
  const started = Date.now();
  const mode = options.mode;
  const budget = options.budget_ms;
  const fail = (reason, extra = {}) => ({ ok: false, reason, elapsed_ms: Date.now() - started, ...extra });
  if (!['watch', 'start', 'answer'].includes(mode) || !Number.isInteger(budget) || budget < 0 || budget > 45000)
    return fail('INVALID_TRANSACTION_OPTIONS');
  let checks = 0, initial = null, last = null, lastProgress = started;
  let answerConfirmed = false, answerTime = null, autoContinue = false, autoSignature = null;
  let resultObserver = null;
  const receipts = [], resultTrace = [];
  const read = () => { checks++; return helpers.observe({ ...options, previous: last || options.previous }); };
  const reasonFor = value => {
    if (!value?.ok || !value.identity_ok) return 'identity-or-read-error';
    if (value.quiz?.visible) {
      const matches = value.details && value.details.question === options.expected_question &&
        JSON.stringify(value.details.options?.map(item => item.text)) === JSON.stringify(options.expected_options);
      if (autoContinue && value.quiz.state === 'result' && value.quiz.verdict === 'correct' && (matches || value.quiz.signature === autoSignature))
        autoSignature = value.quiz.signature;
      else return 'quiz';
    }
    if (value.ended) return 'ended';
    if (answerConfirmed && !value.quiz?.visible && Number.isFinite(answerTime) && value.time > answerTime + 0.05) return 'continued';
    const transient = mode !== 'watch' && Date.now() - started < 2500;
    return value.diagnostics?.some(code => !transient || !['PAUSED_WITHOUT_QUIZ', 'MEDIA_METADATA_UNAVAILABLE'].includes(code)) ? 'diagnostic' : null;
  };
  const finish = reason => ({ ok: last?.ok === true, reason, elapsed_ms: Date.now() - started,
    checks, from: initial?.time ?? null, to: last?.time ?? null, answer_correct: answerConfirmed,
    receipts, result_trace: resultTrace, observation: last });
  try {
    if (mode === 'start') {
      initial = last = read();
      if (!last?.ok || !last.identity_ok) return finish('identity-or-read-error');
      if (last.quiz?.visible || last.ended) return finish(last.ended ? 'ended' : 'quiz');
      if (last.rate !== 1 || last.error) return finish('diagnostic');
      const action = helpers.mute({ ...options, action: 'play' });
      receipts.push(action);
      if (!action.ok) return fail('start-unconfirmed', { receipts });
    }
    if (mode === 'answer') {
      // The model has already solved this exact question and option order.
      const selected = helpers.quiz({ ...options, action: 'select' });
      receipts.push(selected);
      if (!selected.ok) return fail('selection-unconfirmed', { receipts });
      answerTime = selected.after?.video?.currentTime ?? null;
      let captured = null;
      const judgedWrong = value => value.after?.verdict === 'wrong' && value.after?.state !== 'submitting';
      const inspectResult = () => {
        const value = helpers.quiz({ ...options, action: 'inspect' });
        const item = { at_ms: Date.now() - started, state: value.after?.state,
          verdict: value.after?.verdict, can_continue: value.after?.can_continue };
        const previous = resultTrace.at(-1);
        if (!previous || ['state', 'verdict', 'can_continue'].some(key => previous[key] !== item[key])) resultTrace.push(item);
        if (value.ok && (value.after?.state === 'result' || judgedWrong(value)) && !captured) captured = value;
        return value;
      };
      // Attach before the one submit click: auto-dismissed verdicts can be
      // shorter than a polling interval. The existing guard reads each event.
      try {
        const media = document.querySelector('#iframe').contentDocument.querySelector('iframe.ans-insertvideo-online').contentDocument;
        const root = media.querySelector('.tkTopic');
        if (root) {
          resultObserver = new MutationObserver(() => { try { inspectResult(); } catch { /* polling reconciles */ } });
          resultObserver.observe(root, { subtree: true, childList: true, attributes: true, characterData: true });
        }
      } catch { resultObserver?.disconnect(); resultObserver = null; }
      const submitted = helpers.quiz({ ...options, action: 'submit' });
      receipts.push(submitted);
      if (!submitted.ok) return fail('submission-unconfirmed', { receipts });
      let judged = submitted;
      const resultDeadline = started + Math.min(budget, 4000);
      while (judged.after?.state !== 'result' && !judgedWrong(judged) && Date.now() < resultDeadline) {
        await new Promise(resolve => setTimeout(resolve, Math.min(200, resultDeadline - Date.now())));
        judged = captured || inspectResult();
        if (!judged.ok) return fail('result-read-failed', { receipts, result: judged });
      }
      resultObserver?.disconnect(); resultObserver = null;
      // A visible result alone does not prove a correct answer.
      if (judgedWrong(judged)) return fail('answer-not-confirmed-correct', { receipts, result: judged, result_trace: resultTrace });
      if (judged.after?.state !== 'result') return fail('result-pending', { receipts, result: judged, result_trace: resultTrace });
      const correct = judged.after.result_mode === 'verdict' ? judged.after.verdict === 'correct' :
        judged.after.right_num === options.expected_right_num + 1 && judged.after.verdict !== 'wrong';
      if (!correct)
        return fail('answer-not-confirmed-correct', { receipts, result: judged });
      answerConfirmed = true;
      receipts.push(judged);
      autoContinue = judged.after.can_continue === false;
      if (!autoContinue) {
        const continued = helpers.quiz({ ...options, action: 'continue', expected_right_num: judged.after.right_num, expected_verdict: 'correct' });
        receipts.push(continued);
        if (!continued.ok) return fail('continue-unconfirmed', { receipts });
      }
    }
    initial = last = read();
    if (Number.isFinite(answerTime)) initial = { time: answerTime };
    const immediate = reasonFor(last);
    if (immediate) return finish(immediate);
    if (!budget || Date.now() - started >= budget) return finish('deadline');
    // Resolve listeners only after the complete existing identity guard passed.
    const course = document.querySelector('#iframe').contentDocument;
    const media = course.querySelector('iframe.ans-insertvideo-online').contentDocument;
    const video = media.querySelector('video');
    return await new Promise(resolve => {
      let done = false, tick = null, deadline = null, queued = null, observer = null;
      const events = ['timeupdate', 'pause', 'ended', 'error', 'ratechange', 'volumechange'];
      const cleanup = () => {
        clearTimeout(tick); clearTimeout(deadline); clearTimeout(queued); observer?.disconnect();
        for (const name of events) video.removeEventListener(name, changed);
      };
      const complete = reason => { if (done) return; done = true; cleanup(); resolve(finish(reason)); };
      function check() {
        if (done) return;
        try {
          const before = last;
          last = read();
          const reason = reasonFor(last);
          if (reason) return complete(reason);
          if (last.time > before.time + 0.05) lastProgress = Date.now();
          if (Date.now() - lastProgress >= 8000) return complete('stalled');
        } catch { last = { ok: false, identity_ok: false }; complete('observation-failed'); }
      }
      function poll() {
        check();
        if (!done) tick = setTimeout(poll, 1000);
      }
      function changed() {
        if (done || queued !== null) return;
        queued = setTimeout(() => { queued = null; check(); }, 100);
      }
      try {
        for (const name of events) video.addEventListener(name, changed);
        observer = new MutationObserver(changed);
        for (const doc of [document, course, media]) observer.observe(doc, { subtree: true, childList: true, attributes: true, characterData: true });
        deadline = setTimeout(() => { check(); complete('deadline'); }, Math.max(0, budget - (Date.now() - started)));
        tick = setTimeout(poll, 1000);
      } catch { cleanup(); resolve(fail('observer-unavailable', { observation: last, receipts })); }
    });
  } catch { return fail('transaction-failed', { receipts }); }
  finally { resultObserver?.disconnect(); }
})
