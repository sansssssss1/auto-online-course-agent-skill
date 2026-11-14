// Offline DOM/VM boundary tests; no browser, network, or real course submission.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const source = fs.readFileSync(path.join(root, 'scripts/codex_video_quiz.js'), 'utf8');
const expected = { expected_chapter_id: '123', expected_object_id: 'object-a',
  expected_source_path: '/video/object-a/sd.mp4', expected_type: '判断题',
  expected_question: '管理者发挥众人智慧。', expected_options: ['A、对', 'B、错'],
  expected_selected_indices: [0], expected_right_num: 0 };
let checks = 0;
const equal = (actual, value) => { assert.deepEqual(actual, value); checks++; };
const plain = value => JSON.parse(JSON.stringify(value));

function fixture(config = {}) {
  const clicks = [], writes = [];
  const values = { muted: true, defaultMuted: true, paused: true, playbackRate: 1, currentTime: 649,
    currentSrc: 'https://media.example.invalid/video/object-a/sd.mp4?signature=private', ...config.video };
  let selected = config.selected || [];
  const media = { URL: config.mediaUrl || 'https://mooc1.chaoxing.com/ananas/modules/video/index.html',
    defaultView: config.noVisibility ? null : { getComputedStyle(node) {
      return { display: node.hidden ? 'none' : 'block', visibility: 'visible', opacity: '1' };
    } } };
  const node = (tagName, innerText = '') => ({ tagName, innerText, ownerDocument: media,
    parentElement: null, hidden: false, disabled: false,
    getAttribute(name) { return name === 'aria-disabled' && this.ariaDisabled ? 'true' : null; },
    getBoundingClientRect() { return { width: 100, height: 20 }; } });
  const popup = node('DIV');
  const title = node('DIV', config.question || expected.expected_question);
  const type = node('DIV', expected.expected_type), rightNum = node('I', '0');
  const verdictNodes = ['回答正确', '回答错误', '回答错误，回看  分钟'].map(value => node('SPAN', value));
  for (const verdict of verdictNodes) { verdict.parentElement = popup; verdict.hidden = true; }
  const rows = (config.options || expected.expected_options).map((text, index) => {
    const row = node('LI', text), input = node('INPUT');
    Object.assign(input, { type: config.inputType || 'radio', value: '', parentElement: row });
    Object.defineProperty(input, 'checked', { get: () => selected.includes(index), set() {
      writes.push('checked'); throw new Error('Direct checked write prohibited');
    } });
    row.parentElement = popup;
    row.querySelectorAll = selector => { assert.equal(selector, 'input[name="ans-videoquiz-opt"]'); return [input]; };
    input.click = () => { clicks.push(`input:${index}`); if (!config.selectionNoEffect) selected = [index]; effect(); };
    row.input = input;
    return row;
  });
  const submit = node('A'), continuing = node('A'), submitting = node('A');
  continuing.hidden = true; submitting.hidden = true;
  for (const child of [title, type, rightNum, submit, continuing, submitting]) child.parentElement = popup;
  popup.contains = element => [title, type, rightNum, submit, continuing, submitting, ...rows, ...rows.map(row => row.input)].includes(element);
  popup.querySelectorAll = selector => ({ '.tkItem_title': [title], '.tkTopic_title': [type],
    'li.ans-videoquiz-opt': rows, '#rightNum': config.verdictMode ? [] : [rightNum],
    '#spanHas': config.verdictMode ? [verdictNodes[0]] : [], '#spanNot': config.verdictMode ? [verdictNodes[1]] : [],
    '#spanNotBack': config.verdictMode ? [verdictNodes[2]] : [] }[selector] || []);
  submit.click = () => {
    clicks.push('submit');
    if (!config.submitNoEffect) { submit.hidden = !config.retryWrong && !config.keepSubmitOnCorrect; continuing.hidden = !!config.autoContinue || !!config.retryWrong || !!config.keepSubmitOnCorrect; rightNum.innerText = '1';
      verdictNodes[config.wrongVerdict ? 1 : 0].hidden = false; }
    effect();
    if (config.clickThrows) throw new Error('Sensitive URL must not escape: https://private.invalid/?signature=private');
  };
  continuing.click = () => { clicks.push('continue'); popup.hidden = true; effect(); };
  const video = new Proxy({ ownerDocument: media }, {
    get(target, key) { if (key === 'ownerDocument') return media;
      if (['play', 'pause'].includes(key)) throw new Error('Direct media method prohibited');
      return values[key]; },
    set(target, key) { writes.push(key); throw new Error('Media writes prohibited'); },
  });
  let currentVideo = video;
  media.querySelectorAll = selector => ({ video: [currentVideo], '.tkTopic': config.duplicatePopup ? [popup, popup] : [popup],
    '#videoquiz-submit': config.duplicateSubmit ? [submit, submit] : [submit],
    '#videoquiz-continue': [continuing], '#videoquiz-submitting': [submitting] }[selector] || []);
  const inner = { tagName: 'IFRAME', get contentDocument() { if (config.innerUnavailable) throw new Error('Cross origin'); return media; },
    getAttribute(name) { assert.equal(name, 'data'); return config.attachment || '{"objectid":"object-a"}'; } };
  const course = { URL: config.cardsUrl || 'https://mooc1.chaoxing.com/mooc-ans/knowledge/cards?knowledgeid=123',
    querySelectorAll(selector) { assert.equal(selector, 'iframe.ans-insertvideo-online'); return [inner]; } };
  const outer = { tagName: 'IFRAME', contentDocument: course };
  const document = { URL: config.url || 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=123',
    querySelectorAll(selector) {
      // Top-level decoys must never be used for quiz controls (the live failure).
      assert.equal(selector, '#iframe'); return [outer];
    } };
  function effect() {
    if (config.effect === 'chapter') document.URL = 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=999';
    if (config.effect === 'cards') course.URL = 'https://mooc1.chaoxing.com/mooc-ans/knowledge/cards?knowledgeid=999';
    if (config.effect === 'source') values.currentSrc = 'https://media.example.invalid/video/object-a/hd.mp4?signature=private';
    if (config.effect === 'replace') currentVideo = { ...values, ownerDocument: media };
    if (config.effect === 'unmute') values.muted = false;
    if (config.effect === 'question') title.innerText = '另一道题';
  }
  if (config.stage === 'result') { submit.hidden = true; continuing.hidden = false; rightNum.innerText = '1'; }
  if (config.stage === 'submitting') { submit.hidden = true; submitting.hidden = false; }
  if (config.stage === 'ambiguous') continuing.hidden = false;
  if (config.stage === 'absent') popup.hidden = true;
  if (config.controlDisabled) submit.disabled = true;
  if (config.inputDisabled) rows[0].input.disabled = true;
  if (config.hiddenAncestor) { const hidden = node('DIV'); hidden.hidden = true; submit.parentElement = hidden; }
  const sandbox = { URL, document };
  for (const key of ['fetch', 'XMLHttpRequest', 'navigator', 'localStorage', 'window', 'setTimeout', 'setInterval']) {
    Object.defineProperty(sandbox, key, { get() { throw new Error(`Forbidden API ${key}`); } });
  }
  const context = vm.createContext(sandbox);
  return { clicks, writes, values, popup, rows, submit, continuing, rightNum,
    run(action = 'inspect', overrides = {}) {
      // Re-evaluate the function for every invocation, like distinct CDP calls.
      const helper = vm.runInContext(source, context);
      return plain(helper({ ...expected, action, ...overrides }));
    } };
}

let env = fixture();
let result = env.run();
equal(result.ok, true); equal(result.before.state, 'question'); equal(env.clicks, []); equal(env.writes, []);
equal(result.media_key.source_path, expected.expected_source_path);
equal(/signature|private|https?:/.test(JSON.stringify(result)), false);
result = env.run('select', { select_index: 0 });
equal(result.ok, true); equal(result.after.selected_indices, [0]); equal(result.identity_verified_after, true);
equal(env.clicks, ['input:0']); equal(env.writes, []);
equal(env.run('select', { select_index: 0 }).action_attempted, false); equal(env.clicks, ['input:0']);
result = env.run('submit');
equal(result.ok, true); equal(result.submission_status, 'result-visible'); equal(result.after.right_num, 1);
equal(env.clicks, ['input:0', 'submit']);
equal(env.run('submit', { expected_right_num: 1 }).ok, false); equal(env.clicks, ['input:0', 'submit']);
result = env.run('continue', { expected_right_num: 1 });
equal(result.ok, true); equal(result.after.state, 'absent'); equal(env.clicks, ['input:0', 'submit', 'continue']);
equal(env.run('continue', { expected_right_num: 1 }).ok, false); equal(env.clicks.length, 3);

for (const [config, code] of [
  [{ url: 'https://chaoxing.com.evil.invalid/mycourse/studentstudy?chapterId=123' }, 'WRONG_COURSE_PAGE'],
  [{ url: 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=123&chapterId=123' }, 'CHAPTER_MISMATCH'],
  [{ url: 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=999' }, 'CHAPTER_MISMATCH'],
  [{ cardsUrl: 'https://other.chaoxing.com/mooc-ans/knowledge/cards?knowledgeid=123' }, 'CARDS_DOCUMENT_MISMATCH'],
  [{ cardsUrl: 'https://mooc1.chaoxing.com/not-cards?knowledgeid=123' }, 'CARDS_DOCUMENT_MISMATCH'],
  [{ cardsUrl: 'https://mooc1.chaoxing.com/mooc-ans/knowledge/cards?knowledgeid=999' }, 'CARDS_CHAPTER_MISMATCH'],
  [{ attachment: '{"objectid":"other"}' }, 'ATTACHMENT_OBJECT_MISMATCH'],
  [{ innerUnavailable: true }, 'VIDEO_FRAME_UNAVAILABLE'],
  [{ mediaUrl: 'https://other.chaoxing.com/ananas/modules/video/index.html' }, 'VIDEO_DOCUMENT_MISMATCH'],
  [{ mediaUrl: 'https://mooc1.chaoxing.com/other' }, 'VIDEO_DOCUMENT_MISMATCH'],
  [{ video: { currentSrc: 'https://cdn.invalid/video/other/sd.mp4?object=object-a' } }, 'MEDIA_OBJECT_MISMATCH'],
  [{ video: { currentSrc: 'https://cdn.invalid/video/prefix-object-a/sd.mp4' } }, 'MEDIA_OBJECT_MISMATCH'],
  [{ video: { currentSrc: 'https://cdn.invalid/video/object-a/hd.mp4' } }, 'MEDIA_SOURCE_PATH_MISMATCH'],
  [{ question: '管理者发挥众人智慧？' }, 'QUESTION_MISMATCH'],
  [{ options: ['B、错', 'A、对'] }, 'OPTIONS_MISMATCH'],
  [{ options: ['A、对', 'B、错', 'C、未知'] }, 'OPTIONS_MISMATCH'],
  [{ inputType: 'checkbox' }, 'OPTION_INPUT_NOT_UNIQUE'],
  [{ duplicatePopup: true }, 'QUIZ_NOT_UNIQUE'], [{ duplicateSubmit: true }, 'CONTROL_NOT_UNIQUE'],
  [{ noVisibility: true }, 'VISIBILITY_UNAVAILABLE'],
  [{ selected: [0], controlDisabled: true }, 'CONTROL_DISABLED'],
  [{ selected: [0], hiddenAncestor: true }, 'QUIZ_NOT_PENDING'],
  [{ selected: [0], stage: 'submitting' }, 'QUIZ_NOT_PENDING'],
  [{ selected: [0], stage: 'ambiguous' }, 'QUIZ_NOT_PENDING'],
  [{ selected: [0], stage: 'absent' }, 'QUIZ_NOT_VISIBLE'],
  [{ video: { muted: false } }, 'MEDIA_NOT_MUTED'],
  [{ video: { playbackRate: 2 } }, 'PLAYBACK_RATE_NOT_ONE'],
]) {
  env = fixture(config); result = env.run('submit');
  equal(result.ok, false); equal(result.error.code, code); equal(env.clicks, []); equal(env.writes, []);
}
for (const overrides of [ { expected_chapter_id: '' }, { expected_object_id: '' },
  { expected_source_path: '/video/object-a/sd.mp4?signature=private' }, { expected_question: '' },
  { expected_options: ['A、对', 'A、对'] }, { expected_selected_indices: [0, 0] },
  { expected_selected_indices: [2] }, { expected_selected_indices: [0, 1] },
  { expected_selected_indices: [] }, { expected_right_num: 9 } ]) {
  env = fixture({ selected: [0] }); result = env.run('submit', overrides);
  equal(result.ok, false); equal(env.clicks, []);
}
env = fixture(); equal(env.run('submit').error.code, 'SELECTED_SET_MISMATCH'); equal(env.clicks, []);
env = fixture({ inputDisabled: true }); equal(env.run('select', { select_index: 0 }).error.code, 'CONTROL_DISABLED'); equal(env.clicks, []);
env = fixture({ selectionNoEffect: true }); result = env.run('select', { select_index: 0 });
equal(result.error.code, 'SELECTION_NOT_CONFIRMED'); equal(result.action_attempted, true);
env = fixture(); equal(env.run('continue').ok, false); equal(env.clicks, []);
env = fixture({ stage: 'absent' }); equal(env.run().after.state, 'absent'); equal(env.clicks, []);

// A timed-out/throwing submission cannot be blindly retried on the same DOM.
for (const clickThrows of [false, true]) {
  env = fixture({ selected: [0], submitNoEffect: true, clickThrows });
  result = env.run('submit'); equal(result.action_attempted, true); equal(result.submission_status, 'unconfirmed');
  equal(result.ok, !clickThrows); equal(env.clicks, ['submit']);
  result = env.run('submit'); equal(result.error.code, 'ACTION_ALREADY_ATTEMPTED'); equal(env.clicks, ['submit']);
  equal(/signature|private|https?:/.test(JSON.stringify(result)), false);
}
for (const effect of ['chapter', 'cards', 'source', 'replace']) {
  env = fixture({ selected: [0], effect }); result = env.run('submit');
  equal(result.ok, false); equal(result.error.code, 'POST_ACTION_IDENTITY_MISMATCH');
  equal(result.action_attempted, true); equal(result.identity_verified_after, false); equal(env.clicks, ['submit']);
}
env = fixture({ selected: [0], effect: 'unmute' }); equal(env.run('submit').error.code, 'MEDIA_NOT_MUTED');
env = fixture({ effect: 'question' }); equal(env.run('select', { select_index: 0 }).error.code, 'QUESTION_MISMATCH');
// Live count-free popup: absence of a counter is accepted only with the known
// three-label verdict contract. Hidden correct text must never count as proof.
env = fixture({ verdictMode: true }); result = env.run('select', { select_index: 0, expected_right_num: null });
equal(result.ok, true); equal(result.after.right_num, null); equal(result.after.verdict, null);
result = env.run('submit', { expected_right_num: null });
equal(result.ok, true); equal(result.after.verdict, 'correct');
result = env.run('continue', { expected_right_num: null, expected_verdict: 'correct' });
equal(result.ok, true); equal(result.after.state, 'absent'); equal(env.clicks, ['input:0', 'submit', 'continue']);
env = fixture({ verdictMode: true }); equal(env.run('select', { select_index: 0 }).ok, false); equal(env.clicks, []);
env = fixture({ verdictMode: true, selected: [0], wrongVerdict: true });
equal(env.run('submit', { expected_right_num: null }).after.verdict, 'wrong');
equal(env.run('continue', { expected_right_num: null, expected_verdict: 'correct' }).ok, false);
equal(env.clicks, ['submit']);
env = fixture({ verdictMode: true, selected: [0], autoContinue: true });
result = env.run('submit', { expected_right_num: null });
equal(result.after.state, 'result'); equal(result.after.verdict, 'correct'); equal(result.after.can_continue, false);
env = fixture({ verdictMode: true, selected: [0], wrongVerdict: true, retryWrong: true });
result = env.run('submit', { expected_right_num: null }); equal(result.after.state, 'retry');
equal(env.run('select', { expected_right_num: null, select_index: 0 }).ok, false); equal(env.clicks, ['submit']);
env = fixture({ verdictMode: true, selected: [0], keepSubmitOnCorrect: true });
result = env.run('submit', { expected_right_num: null }); equal(result.after.state, 'result');
equal(result.after.verdict, 'correct'); equal(result.after.can_continue, false);
console.log(`PASS ${checks} Codex video-quiz VM assertions; no browser or real submissions.`);
