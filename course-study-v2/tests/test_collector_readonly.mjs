// Offline contract tests: injected DOM/options only; no user browser or network.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'course-study-readonly-'));
let checks = 0;
const check = (actual, expected) => { assert.deepEqual(actual, expected); checks++; };

function readonly(value, memo = new WeakMap()) {
  if (!value || typeof value !== 'object') return value;
  if (memo.has(value)) return memo.get(value);
  const result = new Proxy(value, {
    get(target, key, receiver) {
      if (Array.isArray(target) && key === Symbol.iterator) return function* () {
        for (let index = 0; index < target.length; index++) yield readonly(target[index], memo);
      };
      const found = Reflect.get(target, key, receiver);
      if (typeof found === 'function') return (...args) => readonly(found.apply(receiver, args), memo);
      return readonly(found, memo);
    },
    set() { throw new Error('DOM/options write attempted'); },
    defineProperty() { throw new Error('DOM/options definition attempted'); },
    deleteProperty() { throw new Error('DOM/options deletion attempted'); },
  });
  memo.set(value, result);
  return result;
}

function element(tagName, textContent = '', children = [], attrs = {}, selectors = {}) {
  return {
    nodeType: 1, tagName, textContent, innerText: textContent, childNodes: children,
    id: attrs.id || '', classList: { contains: () => false },
    getAttribute(name) { return attrs[name] || null; },
    querySelector(selector) { return selectors[selector]?.[0] || null; },
    querySelectorAll(selector) { return selectors[selector] || []; },
    contains(other) { return this === other || this.childNodes.some(child => child === other || child.contains?.(other)); },
    click() { throw new Error('Click attempted'); },
  };
}
const text = value => ({ nodeType: 3, nodeValue: value });

function fixture(css = 'normal') {
  const stem = element('DIV', 'Question', [text('Question')]);
  const label = element('SPAN', 'B', [text('B')]);
  const image = element('IMG'); image.src = 'data:image/svg+xml,synthetic'; image.alt = 'figure';
  const option = element('LI', 'B Choice', [label, text(' Choice'), image], { onclick: 'addChoice(this)' },
    { '.num_option_dx, .num_option': [label] });
  const question = element('DIV', 'Question B Choice', [stem, option], { 'data-qid': 'q-explicit' }, {
    'li': [option], '.Zy_TItle, .questionTitle, .mark_name': [stem], 'img': [image],
  });
  const title = element('H3', 'Example work');
  const deadline = element('SPAN', 'tomorrow');
  const row = element('LI', 'Example work 未交 tomorrow', [title, deadline], { 'data-id': 'work-explicit' }, {
    '.j-name, h3, h4, .posCatalog_name, .chapter_name, a.clicktitle': [title], '.deadline, .endTime, .time': [deadline],
  });
  const style = element('STYLE', css === 'embedded' ?
    '@font-face {font-family: secret-font; src:url(data:font/ttf;base64,AAAA);}' : '');
  const doc = {
    URL: 'https://example.invalid/current/questions?session=DO_NOT_CAPTURE',
    defaultView: css === 'missing' ? null : {
      getComputedStyle() {
        if (css === 'throws') throw new Error('styles unsupported');
        if (css === 'empty') return {};
        return { display: 'block', visibility: 'visible', fontFamily: css === 'normal' ? 'Arial' : 'secret-font' };
      },
    },
    querySelectorAll(selector) {
      return selector === 'style' ? [style] : selector === '.TiMu' ? [question] :
        selector === 'li[onclick*="goTask"]' ? [row] : [];
    },
  };
  if (css === 'view-throws') Object.defineProperty(doc, 'defaultView', {
    get() { throw new Error('document style view unsupported'); },
  });
  return readonly(doc);
}

function evaluate(source, context = {}) {
  const sandbox = { URL, ...context };
  for (const name of ['globalThis', 'window', 'location', 'localStorage', 'fetch']) {
    Object.defineProperty(sandbox, name, { get() { throw new Error(`Unexpected page global: ${name}`); } });
  }
  return vm.runInNewContext(source, sandbox);
}
const plain = value => JSON.parse(JSON.stringify(value));
const questionOptions = readonly({ batch_id: 'batch-explicit', source: {
  platform: 'chaoxing', course_key: 'course-explicit', task_key: 'task-explicit',
} });
const taskOptions = readonly({ platform: 'chaoxing', scope: {
  account_alias: 'account-explicit', course_key: 'course-explicit', view: 'homework',
}, loaded_scope_confirmed: true });

try {
  const collectors = Object.fromEntries(['questions', 'tasks'].map(kind => {
    const filename = kind === 'tasks' ? 'collect_task_list.js' : 'collect_questions.js';
    const source = fs.readFileSync(path.join(root, 'scripts', filename), 'utf8');
    assert.doesNotMatch(source, /\b(?:globalThis|window|location|localStorage)\b/); checks++;
    const collect = evaluate(source);
    check(typeof collect, 'function');
    return [kind, collect];
  }));
  const questions = plain(collectors.questions(fixture(), questionOptions));
  check(questions.batch_id, 'batch-explicit');
  check(questions.source.course_key, 'course-explicit');
  check(questions.source.task_key, 'task-explicit');
  check(questions.source.page_path, '/current/questions');
  check(JSON.stringify(questions).includes('DO_NOT_CAPTURE'), false);
  check(questions.questions[0].options[0].label, 'B');
  check(questions.questions[0].images[0].role, 'option');
  check(questions.questions[0].images[0].option_label, 'B');
  check(questions.warnings, []);

  for (const css of ['missing', 'view-throws', 'throws', 'empty', 'obfuscated']) {
    const capture = plain(collectors.questions(fixture(css), questionOptions));
    check(capture.questions[0].needs_review, true);
    check(capture.questions[0].stem[0].font_unresolved, true);
    check(capture.questions[0].stem[0].needs_review, true);
    assert.ok(capture.questions[0].stem[0].warnings.length); checks++;
    assert.ok(capture.warnings.length); checks++;
  }
  const embedded = plain(collectors.questions(fixture('embedded'), questionOptions));
  check(embedded.fonts[0].id, 'embedded-1');
  check(embedded.questions[0].stem[0].font, 'embedded-1');
  check(embedded.warnings, []);
  const reviewQuestions = Array.from({ length: 3 }, (_, index) => {
    const stem = element('DIV', `第${index + 1}题：以下说法中不正确的是？`, [text(`第${index + 1}题：以下说法中不正确的是？`)]);
    const rows = ['A', 'B', 'C', 'D'].map((letter, optionIndex) => {
      const label = element('I', `${letter}、`, [text(`${letter}、`)]);
      const paragraph = element('P', `选项${optionIndex + 1}`, [text(`选项${optionIndex + 1}`)]);
      const link = element('A', `选项${optionIndex + 1}`, [paragraph]);
      return element('LI', `${letter}、选项${optionIndex + 1}`, [label, link], { role: 'option' }, { 'i.fl': [label] });
    });
    const answer = element('DIV', '我的答案：A 成绩：5', [text('我的答案：A 成绩：5')]);
    return element('DIV', '题目及答案成绩', [stem, ...rows, answer], { 'data-qid': `review-${index + 1}` }, {
      '.Zy_TItle, .questionTitle, .mark_name': [stem], 'ul.Zy_ulTop > li': rows, 'li': rows, 'img': [],
    });
  });
  const reviewDoc = readonly({ URL: 'https://example.invalid/review', defaultView: {
    getComputedStyle() { return { fontFamily: 'Arial', display: 'block', visibility: 'visible' }; },
  }, querySelectorAll(selector) { return selector === '.TiMu' ? reviewQuestions : []; } });
  const defaultReview = plain(collectors.questions(reviewDoc, questionOptions));
  check(defaultReview.questions.map(question => question.options.length), [0, 0, 0]);
  const review = plain(collectors.questions(reviewDoc, {
    ...plain(questionOptions), option_selector: 'ul.Zy_ulTop > li', option_label_selector: 'i.fl',
  }));
  check(review.questions.length, 3);
  for (const question of review.questions) {
    check(question.options.length, 4);
    check(question.stem.map(run => run.text).join('').includes('不正确'), true);
    check(question.options.map(option => option.label), ['A、', 'B、', 'C、', 'D、']);
    check(question.options.every(option => option.label_inferred === false), true);
    for (const [index, option] of question.options.entries()) {
      check(option.runs.map(run => run.text).join('').trim(), `选项${index + 1}`);
    }
  }
  check(/我的答案|成绩/.test(JSON.stringify(review)), false);
  const tasks = plain(collectors.tasks(fixture(), taskOptions));
  check(tasks.scope, plain(taskOptions.scope));
  check(tasks.authoritative, true);
  check(tasks.items[0].id, 'work-explicit');
  check(tasks.items[0].status, 'pending');
  check(tasks.items[0].deadline, 'tomorrow');
  check(plain(collectors.tasks(fixture())).authoritative, false);
  for (const completed of [false, true]) {
    const title = element('A', 'Synthetic section');
    const row = element('DIV', 'Synthetic section', [title], {
      role: 'link', 'aria-labelledby': completed ? 'tab_cur123' : 'tab_curinvalid',
    }, {
      '.j-name, h3, h4, .posCatalog_name, .chapter_name, a.clicktitle': [title],
      '.icon_Completed, .ans-job-finished, .icon_yiwanc': completed ? [element('SPAN')] : [],
    });
    const doc = readonly({ querySelectorAll(selector) {
      return selector === '.catalog_title[role="link"]' ? [row] : [];
    } });
    const result = plain(collectors.tasks(doc, { ...plain(taskOptions), scope: { ...plain(taskOptions.scope), view: 'content' } }));
    check(result.items[0].title, 'Synthetic section');
    check(result.items[0].status, completed ? 'completed' : 'unknown');
    check(result.items[0].id_inferred, !completed);
    check(result.items[0].id, completed ? 'tab_cur123' : 'title:Synthetic section');
  }
  const queriedSelectors = [];
  const childRows = ['123', '456'].map(id => element('DIV', `Section ${id}`, [], {
    role: 'link', 'aria-labelledby': `tab_cur${id}`,
  }));
  const parentRows = ['123', '456'].map(id => element('DIV', `Parent ${id}`, [], { id: `cur${id}` }));
  const mixedDoc = readonly({ querySelectorAll(selector) {
    queriedSelectors.push(selector);
    if (selector === '.catalog_title[role="link"]') return childRows;
    if (selector === '.chapter_item') return parentRows;
    if (selector === '.catalog_title') return [...childRows, element('DIV', 'Chapter heading')];
    return [];
  } });
  const contentOptions = { ...plain(taskOptions), scope: { ...plain(taskOptions.scope), view: 'content' } };
  const mixed = plain(collectors.tasks(mixedDoc, contentOptions));
  check(mixed.items.length, 2);
  check(mixed.items.map(item => item.id), ['tab_cur123', 'tab_cur456']);
  check(mixed.items.every(item => item.id_inferred === false), true);
  check(queriedSelectors, ['.catalog_title[role="link"]']);
  const explicit = plain(collectors.tasks(mixedDoc, { ...contentOptions, item_selector: '.chapter_item' }));
  check(explicit.items.map(item => item.id), ['cur123', 'cur456']);
  const legacyDoc = readonly({ querySelectorAll(selector) { return selector === '.chapter_item' ? parentRows : []; } });
  check(plain(collectors.tasks(legacyDoc, contentOptions)).items.length, 2);

  const builder = path.join(root, 'scripts/browser_payload.py');
  const python = process.env.TEST_PYTHON || 'python';
  function build(kind, scope, output) {
    return spawnSync(python, [builder, kind, '--scope', scope, '--out', output], { encoding: 'utf8' });
  }
  for (const kind of ['questions', 'tasks']) {
    for (const scope of ['page', 'element']) {
      const output = path.join(temporary, `${kind}-${scope}.js`);
      const result = build(kind, scope, output);
      check(result.status, 0);
      check(JSON.parse(result.stdout).browser_connected, false);
      const doc = fixture();
      const fn = evaluate(fs.readFileSync(output, 'utf8'), scope === 'page' ? { document: doc } : {});
      const options = kind === 'tasks' ? taskOptions : questionOptions;
      const captured = plain(scope === 'page' ? fn(options) : fn(readonly({ ownerDocument: doc }), options));
      check(captured.schema_version, 1);
      check(kind === 'tasks' ? captured.scope.course_key : captured.source.course_key, 'course-explicit');
      check(build(kind, scope, output).status, 2);
    }
  }
  const originalSource = fs.readFileSync(path.join(root, 'scripts/collect_questions.js'), 'utf8');
  check(build('tasks', 'page', path.join(root, 'scripts/collect_questions.js')).status, 2);
  check(fs.readFileSync(path.join(root, 'scripts/collect_questions.js'), 'utf8'), originalSource);
  check(build('tasks', 'page', path.join(root, 'SKILL.md')).status, 2);
  const protectedOutput = path.join(root, 'scripts', `readonly-reject-${process.pid}.js`);
  check(build('tasks', 'page', protectedOutput).status, 2);
  check(fs.existsSync(protectedOutput), false);
  check(JSON.stringify(plain(questionOptions)), JSON.stringify({ batch_id: 'batch-explicit', source: {
    platform: 'chaoxing', course_key: 'course-explicit', task_key: 'task-explicit',
  } }));
  console.log(`PASS ${checks} read-only collector/builder assertions; injected synthetic DOM only.`);
} finally {
  fs.rmSync(temporary, { recursive: true, force: true });
}
