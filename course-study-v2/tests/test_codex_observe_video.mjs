// Offline VM only. DOM/options proxies reject every write and active API.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const source = fs.readFileSync(path.join(root, 'scripts/codex_observe_video.js'), 'utf8');
const expected = { expected_chapter_id: '123', expected_object_id: 'object-a', expected_source_path: '/video/object-a/sd.mp4' };
let checks = 0;
const equal = (actual, value) => { assert.deepEqual(actual, value); checks++; };
const plain = value => JSON.parse(JSON.stringify(value));

function fixture(config = {}) {
  const prohibited = [];
  const memo = new WeakMap();
  function readonly(value) {
    if (!value || typeof value !== 'object') return value;
    if (memo.has(value)) return memo.get(value);
    const proxy = new Proxy(value, {
      get(target, key, receiver) {
        if (Array.isArray(target) && key === Symbol.iterator) return function* () {
          for (let index = 0; index < target.length; index++) yield readonly(target[index]);
        };
        const found = Reflect.get(target, key, receiver);
        if (typeof found === 'function') return (...args) => readonly(found.apply(receiver, args));
        return readonly(found);
      },
      set(target, key) { prohibited.push('set:' + String(key)); throw new Error('DOM/options write denied'); },
      defineProperty() { prohibited.push('defineProperty'); throw new Error('DOM/options definition denied'); },
      deleteProperty() { prohibited.push('deleteProperty'); throw new Error('DOM/options deletion denied'); },
    });
    memo.set(value, proxy); return proxy;
  }
  const forbidden = name => () => { prohibited.push(name); throw new Error('Active API denied'); };
  const media = { URL: config.mediaUrl || 'https://mooc1.chaoxing.com/ananas/modules/video/index.html?session=PRIVATE',
    visibilityState: config.mediaVisibility || 'visible' };
  media.defaultView = config.noStyles ? null : { getComputedStyle(node) {
    if (config.stylesThrow) throw new Error('PRIVATE source read failed');
    if (config.emptyStyles) return {};
    return { display: node.hidden ? 'none' : 'block', visibility: 'visible', opacity: '1' };
  } };
  const element = (tagName, innerText = '') => ({ tagName, innerText, ownerDocument: media, parentElement: null,
    hidden: false, disabled: false, click: forbidden('click'),
    getBoundingClientRect() { return { width: 100, height: 30 }; },
    getAttribute() { return null; } });
  const popup = element('DIV'), type = element('DIV', '判断题'), title = element('DIV', '管理者发挥众人智慧。');
  const count = element('I', '0');
  const verdictNodes = ['回答正确', '回答错误', '回答错误，回看  分钟'].map(value => element('SPAN', value));
  for (const node of verdictNodes) { node.parentElement = popup; node.hidden = true; }
  if (config.verdict === 'correct') verdictNodes[0].hidden = false;
  if (config.verdict === 'wrong') verdictNodes[1].hidden = false;
  if (config.verdict === 'ambiguous') { verdictNodes[0].hidden = false; verdictNodes[1].hidden = false; }
  const rows = ['A、对', 'B、错'].map(display => {
    const row = element('LI', display), input = element('INPUT');
    Object.assign(input, { type: 'radio', checked: false, value: '', parentElement: row });
    row.parentElement = popup; row.input = input;
    row.querySelectorAll = selector => { assert.equal(selector, 'input[name="ans-videoquiz-opt"]'); return config.missingInput ? [] : [input]; };
    return row;
  });
  const controls = { submit: element('A'), submitting: element('A'), continue: element('A') };
  for (const node of [type, title, count, ...Object.values(controls)]) node.parentElement = popup;
  popup.contains = node => node.parentElement === readonly(popup);
  popup.querySelectorAll = selector => ({ '.tkTopic_title': [type], '.tkItem_title': [title],
    'li.ans-videoquiz-opt': rows, '#rightNum': config.missingCount || config.verdictMode ? [] : [count],
    '#spanHas': config.verdictMode ? [verdictNodes[0]] : [], '#spanNot': config.verdictMode ? [verdictNodes[1]] : [],
    '#spanNotBack': config.verdictMode ? [verdictNodes[2]] : [] }[selector] || []);
  const values = { ownerDocument: media, currentTime: 10.123456, duration: 1000.123456,
    paused: false, muted: true, playbackRate: 1, ended: false, error: null,
    currentSrc: 'https://cdn.invalid/video/object-a/sd.mp4?signature=PRIVATE', src: '',
    play: forbidden('video.play'), pause: forbidden('video.pause'), ...config.video };
  if (config.mediaError) values.error = { code: 4, get message() { return forbidden('error.message')(); } };
  let activeVideo = values;
  media.querySelectorAll = selector => {
    if (selector === 'video') return config.duplicateVideo ? [activeVideo, activeVideo] : [activeVideo];
    if (selector === '.tkTopic') {
      if (config.replaceDuringQuiz) activeVideo = { ...values };
      if (config.quizQueryThrows) throw new Error('PRIVATE DOM channel unavailable');
      return config.duplicateQuiz ? [popup, popup] : [popup];
    }
    for (const name of Object.keys(controls)) if (selector === '#videoquiz-' + name) {
      return config.duplicateControl && name === 'submit' ? [controls[name], controls[name]] : [controls[name]];
    }
    throw new Error('Unexpected media selector ' + selector);
  };
  const inner = { tagName: 'IFRAME', get contentDocument() {
    if (config.crossOriginInner) throw new Error('PRIVATE cross origin'); return media;
  }, getAttribute(name) { assert.equal(name, 'data'); return config.attachment || '{"objectid":"object-a"}'; } };
  const course = { URL: config.cardsUrl || 'https://mooc1.chaoxing.com/mooc-ans/knowledge/cards?knowledgeid=123&private=PRIVATE',
    querySelectorAll(selector) { assert.equal(selector, 'iframe.ans-insertvideo-online'); return config.duplicateInner ? [inner, inner] : [inner]; } };
  const outer = { tagName: 'IFRAME', get contentDocument() {
    if (config.crossOriginOuter) throw new Error('PRIVATE cross origin'); return course;
  } };
  let pageReads = 0;
  const document = { get URL() {
    pageReads++;
    if (config.changeChapterDuringRead && pageReads > 1) return 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=999';
    return config.url || 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=123&private=PRIVATE';
  }, visibilityState: config.pageVisibility || 'visible',
  querySelectorAll(selector) { assert.equal(selector, '#iframe'); return config.duplicateOuter ? [outer, outer] : [outer]; } };
  const setStage = stage => {
    popup.hidden = stage === 'absent';
    controls.submit.hidden = !['question', 'unknown'].includes(stage);
    controls.submitting.hidden = stage !== 'submitting';
    controls.continue.hidden = !['result', 'unknown'].includes(stage);
  };
  setStage(config.stage || 'absent');
  const sandbox = { URL, document: readonly(document) };
  for (const name of ['window', 'globalThis', 'fetch', 'XMLHttpRequest', 'navigator', 'localStorage',
    'setTimeout', 'setInterval', 'requestAnimationFrame', 'MutationObserver']) {
    Object.defineProperty(sandbox, name, { get() { return forbidden(name)(); } });
  }
  const observer = vm.runInNewContext(source, sandbox);
  return { values, prohibited, popup, title, count, rows, controls, media, document, setStage,
    run(overrides = {}) { return plain(observer(readonly({ ...expected, ...overrides }))); } };
}

let env = fixture(), result = env.run();
assert.equal(result.ok, true, JSON.stringify(result)); checks++;
equal(result.identity_ok, true); equal(result.time, 10.123); equal(result.duration, 1000.123);
equal(result.quiz, { visible: false, state: 'absent' }); equal(result.visibility, { page: 'visible', video: 'visible' });
equal('details' in result, false); equal('diagnostics' in result, false); equal(env.prohibited, []);
env.values.currentTime = 40;
const advancing = env.run({ previous: result }); equal(advancing.time, 40); equal('details' in advancing, false);
equal(/PRIVATE|signature|https?:/.test(JSON.stringify(advancing)), false);

// Natural hidden/visible states are observed, never altered or equated to OS focus.
env = fixture({ pageVisibility: 'hidden', mediaVisibility: 'hidden' });
equal(env.run().visibility, { page: 'hidden', video: 'hidden' }); equal(env.document.visibilityState, 'hidden'); equal(env.prohibited, []);

env = fixture({ stage: 'question', video: { paused: true } });
const firstQuiz = env.run();
equal(firstQuiz.quiz.state, 'question'); equal(firstQuiz.details.question, '管理者发挥众人智慧。');
equal(firstQuiz.details.options.map(option => option.text), ['A、对', 'B、错']); equal('diagnostics' in firstQuiz, false);
const unchanged = env.run({ previous: firstQuiz });
equal('details' in unchanged, false); equal(unchanged.quiz.signature, firstQuiz.quiz.signature);
assert.ok(JSON.stringify(unchanged).length < JSON.stringify(firstQuiz).length); checks++;
env.rows[0].input.checked = true;
const selected = env.run({ previous: unchanged }); equal(selected.details.options[0].checked, true);
env.rows[0].input.disabled = true;
equal(env.run({ previous: selected }).details.options[0].disabled, true);
env.title.innerText = '管理者发挥众人智慧？';
const otherQuestion = env.run({ previous: selected }); equal(otherQuestion.details.question, '管理者发挥众人智慧？');
env.setStage('submitting'); equal(env.run({ previous: otherQuestion }).quiz.state, 'submitting');
env.setStage('result'); env.count.innerText = '1';
const judged = env.run({ previous: otherQuestion }); equal(judged.quiz.state, 'result'); equal(judged.quiz.right_num, 1); equal('details' in judged, true);
env.setStage('absent');
const absent = env.run({ previous: judged }); equal(absent.quiz.state, 'absent'); equal('details' in absent, false);
env.setStage('question'); equal('details' in env.run({ previous: absent }), true);
for (const previous of [{ ...firstQuiz, ok: false }, { ...firstQuiz, scope: 'other' }, {}]) equal('details' in env.run({ previous }), true);
equal(env.prohibited, []);

for (const [configuration, code] of [
  [{ url: 'https://chaoxing.com.evil.invalid/mycourse/studentstudy?chapterId=123' }, 'WRONG_COURSE_PAGE'],
  [{ url: 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=123&chapterId=123' }, 'CHAPTER_MISMATCH'],
  [{ url: 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=999' }, 'CHAPTER_MISMATCH'],
  [{ duplicateOuter: true }, 'OUTER_FRAME_NOT_UNIQUE'], [{ crossOriginOuter: true }, 'OUTER_FRAME_UNAVAILABLE'],
  [{ cardsUrl: 'https://other.chaoxing.com/mooc-ans/knowledge/cards?knowledgeid=123' }, 'CARDS_DOCUMENT_MISMATCH'],
  [{ cardsUrl: 'https://mooc1.chaoxing.com/not-cards?knowledgeid=123' }, 'CARDS_DOCUMENT_MISMATCH'],
  [{ cardsUrl: 'https://mooc1.chaoxing.com/mooc-ans/knowledge/cards?knowledgeid=123&knowledgeid=123' }, 'CARDS_CHAPTER_MISMATCH'],
  [{ duplicateInner: true }, 'VIDEO_FRAME_NOT_UNIQUE'], [{ crossOriginInner: true }, 'VIDEO_FRAME_UNAVAILABLE'],
  [{ attachment: '{' }, 'ATTACHMENT_DATA_UNREADABLE'], [{ attachment: '{"objectid":"other"}' }, 'ATTACHMENT_OBJECT_MISMATCH'],
  [{ mediaUrl: 'https://other.chaoxing.com/ananas/modules/video/index.html' }, 'VIDEO_DOCUMENT_MISMATCH'],
  [{ duplicateVideo: true }, 'VIDEO_NOT_UNIQUE'],
  [{ video: { currentSrc: '' } }, 'MEDIA_SOURCE_UNAVAILABLE'],
  [{ video: { currentSrc: 'https://cdn.invalid/video/other/sd.mp4?object=object-a' } }, 'MEDIA_OBJECT_MISMATCH'],
  [{ video: { currentSrc: 'https://cdn.invalid/video/prefix-object-a/sd.mp4' } }, 'MEDIA_OBJECT_MISMATCH'],
  [{ video: { currentSrc: 'https://cdn.invalid/video/object-a/hd.mp4' } }, 'MEDIA_SOURCE_PATH_MISMATCH'],
  [{ changeChapterDuringRead: true }, 'CHAPTER_MISMATCH'], [{ replaceDuringQuiz: true }, 'MEDIA_DOCUMENT_REPLACED'],
]) {
  env = fixture(configuration); result = env.run({ previous: firstQuiz });
  equal(result.ok, false); equal(result.identity_ok, false); equal(result.error.code, code);
  equal('quiz' in result, false); equal(env.prohibited, []); equal(/PRIVATE|signature|https?:/.test(JSON.stringify(result)), false);
}
for (const overrides of [{ expected_chapter_id: 123 }, { expected_object_id: '' },
  { expected_source_path: '/video/object-a/sd.mp4?signature=PRIVATE' }]) {
  env = fixture(); equal(env.run(overrides).ok, false); equal(env.prohibited, []);
}
for (const [configuration, code] of [
  [{ noStyles: true }, 'QUIZ_VISIBILITY_UNAVAILABLE'], [{ emptyStyles: true }, 'QUIZ_VISIBILITY_UNAVAILABLE'],
  [{ missingInput: true }, 'QUIZ_INPUT_UNREADABLE'], [{ missingCount: true }, 'QUIZ_COUNT_UNREADABLE'],
  [{ duplicateQuiz: true }, 'QUIZ_NOT_UNIQUE'], [{ duplicateControl: true }, 'QUIZ_CONTROL_NOT_UNIQUE'],
]) {
  env = fixture({ stage: 'question', ...configuration }); result = env.run({ previous: firstQuiz });
  equal(result.ok, false); equal(result.identity_ok, true); equal(result.quiz.state, 'unreadable'); equal(result.error.code, code); equal(env.prohibited, []);
}
for (const configuration of [{ stylesThrow: true }, { quizQueryThrows: true }]) {
  env = fixture({ stage: 'question', ...configuration }); result = env.run({ previous: firstQuiz });
  equal(result.ok, false); equal('details' in result, false); equal(/PRIVATE|signature/.test(JSON.stringify(result)), false);
}
for (const [configuration, diagnostic] of [
  [{ video: { muted: false } }, 'MEDIA_NOT_MUTED'], [{ video: { playbackRate: 2 } }, 'PLAYBACK_RATE_NOT_ONE'],
  [{ mediaError: true }, 'MEDIA_ERROR'], [{ video: { duration: NaN } }, 'MEDIA_METADATA_UNAVAILABLE'],
  [{ stage: 'unknown' }, 'QUIZ_STATE_UNKNOWN'],
]) {
  env = fixture({ stage: 'question', ...configuration }); const initial = env.run(); result = env.run({ previous: initial });
  equal(result.ok, true); equal(result.diagnostics.includes(diagnostic), true); equal('details' in result, true); equal(env.prohibited, []);
}
env = fixture({ video: { paused: true } }); equal(env.run().diagnostics, ['PAUSED_WITHOUT_QUIZ']);
env = fixture({ video: { paused: true, ended: true } }); equal('diagnostics' in env.run(), false);
env = fixture({ stage: 'question', verdictMode: true }); result = env.run();
equal(result.ok, true); equal(result.quiz.right_num, null); equal(result.quiz.verdict, null); equal(env.prohibited, []);
for (const verdict of ['correct', 'wrong']) {
  env = fixture({ stage: 'result', verdictMode: true, verdict }); result = env.run();
  equal(result.ok, true); equal(result.quiz.result_mode, 'verdict'); equal(result.quiz.verdict, verdict); equal(env.prohibited, []);
}
env = fixture({ stage: 'result', verdictMode: true, verdict: 'ambiguous' });
equal(env.run().error.code, 'QUIZ_VERDICT_AMBIGUOUS'); equal(env.prohibited, []);
env = fixture({ stage: 'question', verdictMode: true, verdict: 'correct' });
equal(env.run().quiz.state, 'result'); equal(env.prohibited, []);
console.log(`PASS ${checks} Codex read-only video-observation VM assertions; no browser, writes, or timers.`);
