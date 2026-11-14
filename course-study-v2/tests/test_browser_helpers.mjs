import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dragToTime, seekToEnd } from '../scripts/official_seek.mjs';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const code = fs.readFileSync(path.join(root, 'scripts/keepalive.beacon.js'), 'utf8');
function boot() {
  let now = 100000;
  let tick;
  let sideEffects = 0;
  const video = { muted: false, volume: 0.8, currentSrc: 'https://example.invalid/current.mp4',
    currentTime: 1, duration: 200, playbackRate: 1, paused: false, ended: false,
    play() { sideEffects++; }, pause() { sideEffects++; } };
  const window = {};
  const document = { querySelectorAll: () => [], querySelector: () => video, title: '' };
  vm.runInNewContext(code, { window, document, localStorage: { setItem() {} },
    Date: { now: () => now }, setInterval(fn) { tick = fn; } });
  return { window, video, tick: () => tick(), advance(ms) { now += ms; }, effects: () => sideEffects };
}
let assertions = 0;
let env = boot();
assert.equal(env.video.muted, true); assertions++;
assert.equal(env.video.playbackRate, 1); assertions++;
assert.equal(env.effects(), 0); assertions++;
env.window.__cxAudioTrial = { video: env.video, src: env.video.currentSrc, until: 160000 };
env.video.volume = 0.001; env.video.muted = false; env.tick();
assert.equal(env.video.muted, false); assertions++;
env.advance(60000); env.tick();
assert.equal(env.video.muted, true); assertions++;
for (const change of [
  e => { e.window.__cxAudioTrial.video = {}; },
  e => { e.window.__cxAudioTrial.src = 'other'; },
  e => { e.window.__cxAudioTrial.until = Infinity; },
  e => { e.window.__cxAudioTrial.until = 160001; },
  e => { e.video.volume = 0.01; },
]) {
  env = boot();
  env.window.__cxAudioTrial = { video: env.video, src: env.video.currentSrc, until: 160000 };
  env.video.volume = 0.001; env.video.muted = false; change(env); env.tick();
  assert.equal(env.video.muted, true); assertions++;
}

function pageFixture({ count = 1, errorOnDrag = false, duration = 100 } = {}) {
  let t = 0, up = 0, moves = 0;
  const control = { count: async () => count, hover: async () => {},
    boundingBox: async () => ({ x: 0, y: 0, width: 1000, height: 10 }),
    evaluate: async () => duration };
  const page = { evaluate: async () => ({ t, duration, paused: false, ended: false, rate: 1 }),
    locator: () => ({ first: () => control }), waitForTimeout: async () => {},
    mouse: { async move(x) { if (++moves === 2) { if (errorOnDrag) throw new Error('synthetic drag failure'); t = x / 1000 * duration; } },
      async down() {}, async up() { up++; } } };
  return { page, released: () => up };
}
let fixture = pageFixture();
assert.equal((await dragToTime(fixture.page, 92)).accepted, true); assertions++;
assert.equal(fixture.released(), 1); assertions++;
fixture = pageFixture({ count: 0 });
assert.equal((await seekToEnd(fixture.page)).reason, 'seek-control-unavailable'); assertions++;
fixture = pageFixture({ errorOnDrag: true });
assert.equal((await seekToEnd(fixture.page)).accepted, false); assertions++;
assert.equal(fixture.released(), 1); assertions++;
console.log(`PASS ${assertions} helper assertions; synthetic VM/Playwright-shaped fixture only.`);
