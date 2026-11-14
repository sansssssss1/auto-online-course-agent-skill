import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { createCodexSession } from '../scripts/codex_session.mjs';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const source = await fs.readFile(path.join(root, 'scripts/codex_video_transaction.js'), 'utf8');
let checks = 0;
function fixture(config = {}) {
  let now = 0, serial = 0, settled = false, result;
  const timers = new Map(), listeners = new Map(), actions = [];
  const activeObservers = new Set();
  let disconnected = 0, connected = 0, submittedAt = null, continued = false;
  const video = {
    addEventListener(name, fn) { listeners.set(name, fn); },
    removeEventListener(name, fn) { assert.equal(listeners.get(name), fn); listeners.delete(name); }
  };
  const media = { querySelector(selector) { if (selector === '.tkTopic') return config.flashVerdict ? {} : null;
    assert.equal(selector, 'video'); return video; } };
  const course = { querySelector() { return { contentDocument: media }; } };
  const document = { querySelector() { return { contentDocument: course }; } };
  const schedule = (fn, ms) => { const id = ++serial; timers.set(id, { fn, at: now + ms }); return id; };
  const helpers = {
    observe() {
      if (config.invalid || now >= (config.identityFailsAt ?? Infinity)) return { ok: false, identity_ok: false };
      return { ok: true, identity_ok: true, rate: config.rate ?? 1, error: null, time: 10 + (config.stalled ? 0 : now / 1000), duration: 100,
        quiz: { visible: now >= (config.popupAt ?? Infinity) && !continued, state: 'question' },
        ...(config.diagnostics ? { diagnostics: ['MEDIA_NOT_MUTED'] } : {}),
        ended: now >= (config.endsAt ?? Infinity) };
    },
    mute() { actions.push('play'); return { ok: !config.startFails }; },
    quiz(options) {
      actions.push(options.action);
      if (config.failAction === options.action) return { ok: false, action_attempted: true };
      if (options.action === 'submit') submittedAt = now;
      if (options.action === 'continue') continued = true;
      const judged = submittedAt !== null && now - submittedAt >= (config.judgeDelay ?? 0);
      const disappeared = config.disappearWithoutVerdict || config.flashVerdict && now - submittedAt >= 630;
      return { ok: true, after: { state: judged ? (config.retryWrong ? 'retry' : disappeared ? 'absent' : 'result') :
          config.preexistingWrong && submittedAt !== null ? 'submitting' : 'question', can_continue: !config.autoContinue,
        video: { currentTime: 10 },
        result_mode: config.verdictMode ? 'verdict' : 'count',
        verdict: judged && config.verdictMode && !disappeared ? (config.wrong ? 'wrong' : 'correct') :
          config.preexistingWrong && submittedAt !== null && !judged ? 'wrong' : null,
        right_num: config.verdictMode ? null : judged && !config.wrong ? 4 : 3 } };
    }
  };
  const transaction = vm.runInNewContext(source, { document, Date: { now: () => now },
    setTimeout: schedule, clearTimeout: id => timers.delete(id),
    MutationObserver: class {
      constructor(callback) { this.callback = callback; }
      observe() { connected++; activeObservers.add(this); if (config.flashVerdict && connected === 1) schedule(this.callback, 620);
        if (connected === 1 && config.storm) schedule(() => {
        for (let index = 0; index < 1000; index++) listeners.get('timeupdate')?.();
      }, 500); }
      disconnect() { disconnected++; activeObservers.delete(this); }
    } });
  return {
    actions,
    async run(mode = 'watch', overrides = {}) {
      const pending = transaction(helpers, { mode, budget_ms: 3500, expected_right_num: 3, ...overrides });
      pending.then(value => { settled = true; result = value; });
      for (let step = 0; step < 200 && !settled; step++) {
        await Promise.resolve(); await Promise.resolve();
        if (settled) break;
        const next = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        timers.delete(next[0]); now = next[1].at; next[1].fn();
      }
      await pending;
      assert.equal(timers.size, 0); assert.equal(listeners.size, 0);
      assert.equal(activeObservers.size, 0);
      checks += 3;
      return JSON.parse(JSON.stringify(result));
    }
  };
}

let env = fixture(), result = await env.run();
assert.equal(result.reason, 'deadline'); assert.equal(result.from, 10); assert.equal(result.to, 13.5); checks += 3;
env = fixture({ storm: true }); result = await env.run();
assert.equal(result.reason, 'deadline'); assert.ok(result.checks <= 8); checks += 2;
for (const [config, reason] of [
  [{ popupAt: 1000 }, 'quiz'], [{ endsAt: 1000 }, 'ended'],
  [{ identityFailsAt: 1000 }, 'identity-or-read-error'], [{ diagnostics: true }, 'diagnostic'],
  [{ stalled: true }, 'stalled']
]) {
  env = fixture(config); result = await env.run('watch', { budget_ms: 10000 });
  assert.equal(result.reason, reason); assert.deepEqual(env.actions, []); checks += 2;
}
env = fixture({ invalid: true }); result = await env.run('start');
assert.equal(result.ok, false); assert.deepEqual(env.actions, []); checks += 2;
env = fixture(); result = await env.run('start');
assert.equal(result.reason, 'deadline'); assert.deepEqual(env.actions, ['play']); checks += 2;
env = fixture({ startFails: true }); result = await env.run('start');
assert.equal(result.reason, 'start-unconfirmed'); assert.deepEqual(env.actions, ['play']); checks += 2;
env = fixture({ rate: 2 }); result = await env.run('start');
assert.equal(result.reason, 'diagnostic'); assert.deepEqual(env.actions, []); checks += 2;
env = fixture({ judgeDelay: 600 }); result = await env.run('answer');
assert.equal(result.reason, 'continued');
assert.equal(env.actions.filter(x => x === 'submit').length, 1);
assert.equal(env.actions.filter(x => x === 'continue').length, 1);
assert.ok(env.actions.filter(x => x === 'inspect').length >= 1); checks += 4;
for (const [config, reason] of [
  [{ judgeDelay: 99999 }, 'result-pending'], [{ wrong: true }, 'answer-not-confirmed-correct'],
  [{ verdictMode: true, disappearWithoutVerdict: true }, 'result-pending'],
  [{ failAction: 'select' }, 'selection-unconfirmed'], [{ failAction: 'submit' }, 'submission-unconfirmed']
]) {
  env = fixture(config); result = await env.run('answer', { budget_ms: 4500 });
  assert.equal(result.reason, reason); assert.equal(env.actions.includes('continue'), false);
  assert.ok(env.actions.filter(x => x === 'submit').length <= 1); checks += 3;
}
env = fixture(); result = await env.run('answer', { budget_ms: 45001 });
assert.equal(result.reason, 'INVALID_TRANSACTION_OPTIONS'); assert.deepEqual(env.actions, []); checks += 2;
env = fixture({ verdictMode: true, judgeDelay: 400 }); result = await env.run('answer', { expected_right_num: null });
assert.equal(result.ok, true); assert.equal(env.actions.filter(x => x === 'submit').length, 1);
assert.equal(env.actions.filter(x => x === 'continue').length, 1); checks += 3;
env = fixture({ verdictMode: true, wrong: true }); result = await env.run('answer', { expected_right_num: null });
assert.equal(result.reason, 'answer-not-confirmed-correct'); assert.equal(env.actions.includes('continue'), false); checks += 2;
env = fixture({ verdictMode: true, wrong: true, retryWrong: true, judgeDelay: 120 }); result = await env.run('answer', { expected_right_num: null });
assert.equal(result.reason, 'answer-not-confirmed-correct'); assert.ok(result.elapsed_ms < 1000);
assert.equal(env.actions.filter(x => x === 'submit').length, 1); checks += 3;
env = fixture({ verdictMode: true, preexistingWrong: true, judgeDelay: 600, autoContinue: true });
result = await env.run('answer', { expected_right_num: null });
assert.equal(result.answer_correct, true); assert.equal(result.reason, 'continued');
assert.equal(env.actions.filter(x => x === 'submit').length, 1); checks += 3;

env = fixture({ verdictMode: true, autoContinue: true, judgeDelay: 400 }); result = await env.run('answer', { expected_right_num: null });
assert.equal(result.reason, 'continued'); assert.equal(result.answer_correct, true);
assert.equal(env.actions.filter(x => x === 'submit').length, 1); assert.equal(env.actions.includes('continue'), false); checks += 4;
env = fixture({ verdictMode: true, autoContinue: true, judgeDelay: 610, flashVerdict: true });
result = await env.run('answer', { expected_right_num: null });
assert.equal(result.answer_correct, true); assert.equal(result.reason, 'continued');
assert.equal(env.actions.filter(x => x === 'submit').length, 1);
assert.ok(result.result_trace.some(item => item.at_ms === 620 && item.verdict === 'correct')); checks += 4;

const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'codex-course-test-'));
try {
  const calls = [];
  const session = await createCodexSession({ skillRoot: root, runDir: temp, reserveMs: 50000,
    cdp: { async send(method, params, options) {
      calls.push({ method, params, options });
      if (calls.length === 1) return { result: { value: { ok: true, reason: 'deadline', elapsed_ms: 0,
        from: 1, to: 2, observation: { ok: true, time: 2 } } } };
      throw new Error('PRIVATE signed source');
    } } });
  result = await session.run('watch', {}, { budget_ms: 30000 });
  assert.equal(result.to, 2); assert.equal(calls[0].options.timeoutMs, 15000);
  assert.ok(calls[0].params.expression.includes('"budget_ms":10000'));
  result = await session.run('answer', {}, { budget_ms: 30000 });
  assert.equal(result.reason, 'transport-unconfirmed'); assert.equal(calls.length, 2);
  const log = await fs.readFile(path.join(temp, 'transactions.jsonl'), 'utf8');
  assert.equal(log.includes('PRIVATE'), false);
  const rows = log.trim().split('\n').map(JSON.parse);
  assert.equal(rows[0].actual_tokens, null); assert.equal(rows[1].result.action_may_have_occurred, true); checks += 8;

  const packets = [], pending = [];
  const batched = await createCodexSession({ skillRoot: root, runDir: temp,
    cdp: { send(method, params) {
      packets.push(params.expression);
      return new Promise(resolve => pending.push(resolve));
    } } });
  const first = batched.run('watch', {});
  const overlapping = await batched.run('answer', {});
  assert.equal(overlapping.reason, 'transaction-in-flight'); assert.equal(packets.length, 1);
  assert.ok(packets[0].includes('function observeCourseVideo'));
  assert.equal(packets[0].includes('function muteCourseVideo'), false);
  assert.equal(packets[0].includes('function videoQuizAction'), false);
  assert.equal(packets[0].includes('mute:('), false); assert.equal(packets[0].includes('quiz:('), false);
  const detailMarker = 'DO_NOT_RESEND_OLD_QUESTION';
  pending.shift()({ result: { value: { ok: true, reason: 'quiz', observation: { ok: true,
    identity_ok: true, scope: 'scope-a', quiz: { visible: true, state: 'question', signature: 'digest-a' },
    details: { question: detailMarker } } } } });
  assert.equal((await first).details.question, detailMarker);
  const second = batched.run('start', {});
  assert.equal(packets[1].includes(detailMarker), false);
  assert.ok(packets[1].includes('"signature":"digest-a"'));
  assert.ok(packets[1].includes('mute:(')); assert.equal(packets[1].includes('quiz:('), false);
  pending.shift()({ result: { value: { ok: true, reason: 'deadline' } } });
  await second;
  const third = batched.run('answer', {});
  assert.ok(packets[2].includes('quiz:(')); assert.equal(packets[2].includes('mute:('), false);
  pending.shift()({ result: { value: { ok: true, reason: 'continued' } } });
  await third;
  assert.equal((await batched.run('invalid', {})).reason, 'INVALID_TRANSACTION_OPTIONS');
  assert.equal((await batched.run('watch', {}, { budget_ms: NaN })).reason, 'INVALID_TRANSACTION_OPTIONS');
  assert.equal(packets.length, 3);
  checks += 17;
} finally { await fs.rm(temp, { recursive: true, force: true }); }
console.log(`PASS ${checks} Codex transaction assertions: cleanup, budgets, identity failure, result accuracy, single submission and transport uncertainty.`);
