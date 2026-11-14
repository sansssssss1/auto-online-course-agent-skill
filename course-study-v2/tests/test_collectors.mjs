// Integration on a new local synthetic browser document, never a user session.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import vm from 'node:vm';
import { pathToFileURL, fileURLToPath } from 'node:url';

if (!process.env.TEST_PLAYWRIGHT_MODULE) {
  console.log('SKIP synthetic DOM browser: set TEST_PLAYWRIGHT_MODULE to an existing approved playwright-core module');
  process.exit(0);
}
const { chromium } = await import(pathToFileURL(process.env.TEST_PLAYWRIGHT_MODULE).href);
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'course-study-collector-'));
function payload(kind, scope) {
  const target = path.join(temporary, `${kind}-${scope}.js`);
  execFileSync(process.env.TEST_PYTHON || 'python', [path.join(root, 'scripts/browser_payload.py'),
    kind, '--scope', scope, '--out', target]);
  // Standard Playwright invokes function arguments, not arrow-expression strings.
  return vm.runInThisContext(fs.readFileSync(target, 'utf8'));
}
const questionsScript = payload('questions', 'page');
const questionsElementScript = payload('questions', 'element');
const listsScript = payload('tasks', 'page');
const questionOptions = { batch_id: 'synthetic-dom', source: { course_key: 'example', task_key: 'example-question' } };
const taskOptions = { platform: 'chaoxing',
  scope: { account_alias: 'synthetic', course_key: 'example', view: 'homework' }, loaded_scope_confirmed: true };
const browser = await chromium.launch({ channel: 'msedge', headless: true,
  args: ['--disable-background-networking', '--disable-component-update'] });
let checks = 0;
try {
  const context = await browser.newContext();
  let networkAttempts = 0;
  await context.route('**/*', route => { networkAttempts++; return route.abort(); });
  const page = await context.newPage();
  await page.setContent(`<html><body>
    <input type="password" value="DO_NOT_CAPTURE_LOGIN">
    <div class="TiMu" data-qid="q-1"><div class="Zy_TItle">Current synthetic question</div>
      <ul><li onclick="addChoice(this)"><span class="num_option_dx" data="C">B</span>
        <label>Visible target answer<input type="radio" checked value="C"></label></li></ul>
      <img alt="figure" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E">
    </div></body></html>`);
  const originalQuestionPage = await page.content();
  const captured = await page.evaluate(questionsScript, questionOptions);
  assert.equal(captured.schema_version, 1); checks++;
  assert.equal(captured.questions.length, 1); checks++;
  assert.equal(captured.questions[0].id, 'q-1'); checks++;
  assert.equal(captured.questions[0].options[0].label, 'B'); checks++;
  assert.equal(captured.questions[0].options[0].runs.map(x => x.text).join('').trim(), 'Visible target answer'); checks++;
  assert.equal(captured.questions[0].images.length, 1); checks++;
  assert.equal(captured.questions[0].images[0].role, 'stem'); checks++;
  assert.ok(!JSON.stringify(captured).includes('DO_NOT_CAPTURE_LOGIN')); checks++;
  assert.equal(await page.content(), originalQuestionPage); checks++;
  assert.equal(captured.source.course_key, 'example'); checks++;
  assert.equal(captured.batch_id, 'synthetic-dom'); checks++;
  const elementCaptured = await page.locator('body').evaluate(questionsElementScript, questionOptions);
  assert.deepEqual(elementCaptured.questions, captured.questions); checks++;
  if (process.env.TEST_CAPTURE_OUT) fs.writeFileSync(process.env.TEST_CAPTURE_OUT, JSON.stringify(captured, null, 2));

  await page.setContent(`<div class="TiMu"><div class="Zy_TItle">Figure choices</div><ul>
    <li onclick="addChoice(this)"><span class="num_option_dx">B</span><img alt="figure" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"></li>
    <li onclick="addChoice(this)"><span class="num_option_dx">A</span><img alt="figure" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"></li>
  </ul></div>`);
  const figures = await page.evaluate(questionsScript, questionOptions);
  assert.equal(figures.questions[0].images[0].option_label, 'B'); checks++;
  assert.equal(figures.questions[0].images[1].option_label, 'A'); checks++;
  assert.equal(figures.questions[0].images[0].role, 'option'); checks++;

  await page.setContent(Array.from({ length: 3 }, (_, index) => `<div class="TiMu" data-qid="review-${index + 1}">
    <div class="Zy_TItle">第${index + 1}题：以下说法中不正确的是？</div>
    <ul class="Zy_ulTop qtDetail">${['A', 'B', 'C', 'D'].map((letter, optionIndex) =>
      `<li class="clearfix" role="option"><i class="fl">${letter}、</i><a><p>选项${optionIndex + 1}</p></a></li>`).join('')}</ul>
    <div class="Py_answer"><span>我的答案：A</span><span>成绩：5</span></div>
  </div>`).join(''));
  const defaultReview = await page.evaluate(questionsScript, questionOptions);
  assert.deepEqual(defaultReview.questions.map(question => question.options.length), [0, 0, 0]); checks++;
  const review = await page.evaluate(questionsScript, { ...questionOptions,
    option_selector: 'ul.Zy_ulTop > li', option_label_selector: 'i.fl' });
  assert.equal(review.questions.length, 3); checks++;
  for (const question of review.questions) {
    assert.equal(question.options.length, 4); checks++;
    assert.ok(question.stem.map(run => run.text).join('').includes('不正确')); checks++;
    assert.deepEqual(question.options.map(option => option.label), ['A、', 'B、', 'C、', 'D、']); checks++;
    assert.ok(question.options.every(option => option.label_inferred === false)); checks++;
    for (const [index, option] of question.options.entries()) {
      assert.equal(option.runs.map(run => run.text).join('').trim(), `选项${index + 1}`); checks++;
    }
  }
  assert.ok(!/我的答案|成绩/.test(JSON.stringify(review))); checks++;

  await page.setContent(`<ul>
    <li id="row-a" onclick="goTask(this)" data="https://example.invalid/work?workId=w1"><h3>Example one</h3>未交<span class="deadline">tomorrow as displayed</span></li>
    <li id="row-b" onclick="goTask(this)"><h3>Example two</h3>待批阅</li>
  </ul>`);
  const originalTaskPage = await page.content();
  const tasks = await page.evaluate(listsScript, taskOptions);
  assert.equal(tasks.items.length, 2); checks++;
  assert.equal(tasks.items[0].status, 'pending'); checks++;
  assert.equal(tasks.items[1].status, 'submitted'); checks++;
  assert.equal(tasks.items[0].deadline, 'tomorrow as displayed'); checks++;
  assert.equal(await page.content(), originalTaskPage); checks++;
  assert.deepEqual(tasks.scope, taskOptions.scope); checks++;
  assert.equal(tasks.authoritative, true); checks++;
  await page.setContent(`<div class="catalog_title chapter_Thats_bnt">Chapter heading</div>
    <div class="chapter_item" id="cur123"><div class="catalog_title" tabindex="0" role="link" aria-labelledby="tab_cur123">
      <a class="clicktitle">Completed synthetic section</a><span class="icon_yiwanc"></span>
    </div></div><div class="chapter_item" id="cur456"><div class="catalog_title" role="link" aria-labelledby="tab_curinvalid">
      <a class="clicktitle">Unknown synthetic section</a></div></div>`);
  const catalog = await page.evaluate(listsScript, { ...taskOptions, scope: { ...taskOptions.scope, view: 'content' } });
  assert.equal(catalog.items.length, 2); checks++;
  assert.equal(catalog.items[0].title, 'Completed synthetic section'); checks++;
  assert.equal(catalog.items[0].status, 'completed'); checks++;
  assert.equal(catalog.items[1].status, 'unknown'); checks++;
  assert.equal(catalog.items[0].id_inferred, false); checks++;
  assert.equal(catalog.items[0].id, 'tab_cur123'); checks++;
  assert.equal(catalog.items[1].id_inferred, true); checks++;
  const parents = await page.evaluate(listsScript, { ...taskOptions,
    scope: { ...taskOptions.scope, view: 'content' }, item_selector: '.chapter_item' });
  assert.equal(parents.items.length, 2); checks++;
  assert.equal(parents.items[0].id, 'cur123'); checks++;
  await page.setContent('<div>No parsed list structure</div>');
  const empty = await page.evaluate(listsScript, taskOptions);
  assert.equal(empty.authoritative, false); checks++;
  assert.ok(empty.warnings.length); checks++;
  await assert.rejects(page.evaluate(questionsScript, questionOptions), /NO_QUESTIONS/); checks++;
  assert.equal(networkAttempts, 0); checks++;
  console.log(`PASS ${checks} assertions on synthetic DOM; zero task clicks/navigation/network requests.`);
} finally {
  await browser.close();
  fs.rmSync(temporary, { recursive: true, force: true });
}
