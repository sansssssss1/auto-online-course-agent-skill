// Offline VM only: does not attach to CDP or open any browser.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const source = fs.readFileSync(path.join(root, 'scripts/codex_mute_video.js'), 'utf8');
let checks = 0;
const equal = (actual, expected) => { assert.deepEqual(actual, expected); checks++; };
const plain = value => JSON.parse(JSON.stringify(value));
function fixture({ url = 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=123',
  cardsUrl = 'https://mooc1.chaoxing.com/knowledge/cards?knowledgeid=123&clazzid=private',
  objectId = 'object-a', attachmentData = JSON.stringify({ objectid: objectId, type: '.mp4' }),
  currentSrc = `https://media.example.invalid/video/${objectId}/sd.mp4?signature=TEST&session=hidden`,
  src = '', mediaUrl = 'https://mooc1.chaoxing.com/ananas/modules/video/index.html',
  sourceThrows = false, attachmentThrows = false, cardsThrows = false,
  initialPaused = true, bigCount = 1, playCount = 1, bigVisible = true, playVisible = true,
  controlDisabled = false, ariaDisabled = false, visibilityUnavailable = false,
  clickThrows = false, clickEffect = 'toggle',
  outerCount = 1, innerCount = 1, videoCount = 1, outerUnavailable = false,
  innerUnavailable = false, outerThrows = false, innerThrows = false, wrongOuterTag = false,
  writeFails = false } = {}) {
  const writes = [];
  const buttonClicks = [];
  const values = { muted: false, defaultMuted: false, paused: initialPaused, ended: false,
    currentTime: 12, duration: 200, playbackRate: 1, volume: 0.8, currentSrc, src };
  const target = new Proxy(values, {
    set(object, key, value) {
      if (!['muted', 'defaultMuted'].includes(key)) throw new Error(`Unexpected write ${key}`);
      writes.push(key);
      if (writeFails && key === 'defaultMuted') throw new Error('Synthetic write denial');
      object[key] = value;
      return true;
    },
    get(object, key) {
      if (['play', 'pause'].includes(key)) throw new Error(`Unexpected media access ${key}`);
      if (sourceThrows && ['src', 'currentSrc'].includes(key)) throw new Error('Synthetic source read denial');
      return object[key];
    },
  });
  const otherVideo = new Proxy({ muted: false, defaultMuted: false, currentTime: 40, volume: 0.7 }, {
    set() { throw new Error('Unrelated media changed'); },
  });
  let mediaVideo = target;
  let bigButtons = [], playButtons = [];
  const mediaDocument = { URL: mediaUrl,
    defaultView: visibilityUnavailable ? null : { getComputedStyle(button) {
      return { display: button.testVisible ? 'block' : 'none', visibility: 'visible', opacity: '1' };
    } },
    querySelectorAll(selector) {
    if (selector === 'button.vjs-big-play-button') return bigButtons;
    if (selector === 'button.vjs-play-control') return playButtons;
    assert.equal(selector, 'video');
    return videoCount === 0 ? [] : videoCount === 1 ? [mediaVideo] : [mediaVideo, otherVideo];
  } };
  const innerFrame = { tagName: 'IFRAME', getAttribute(name) {
    assert.equal(name, 'data');
    if (attachmentThrows) throw new Error('Synthetic attachment read denial');
    return attachmentData;
  }, get contentDocument() {
    if (innerThrows) throw new Error('Cross-origin inner frame');
    return innerUnavailable ? null : mediaDocument;
  } };
  const courseDocument = { get URL() {
    if (cardsThrows) throw new Error('Synthetic cards URL read denial');
    return cardsUrl;
  }, querySelectorAll(selector) {
    assert.equal(selector, 'iframe.ans-insertvideo-online');
    return innerCount === 0 ? [] : innerCount === 1 ? [innerFrame] : [innerFrame, innerFrame];
  } };
  const outerFrame = { tagName: wrongOuterTag ? 'DIV' : 'IFRAME', get contentDocument() {
    if (outerThrows) throw new Error('Cross-origin outer frame');
    return outerUnavailable ? null : courseDocument;
  } };
  const document = { URL: url, querySelectorAll(selector) {
    assert.equal(selector, '#iframe');
    return outerCount === 0 ? [] : outerCount === 1 ? [outerFrame] : [outerFrame, outerFrame];
  } };
  function button(selector, visible) {
    return { tagName: 'BUTTON', ownerDocument: mediaDocument, testVisible: visible, disabled: controlDisabled,
      getAttribute(name) { assert.equal(name, 'aria-disabled'); return ariaDisabled ? 'true' : null; },
      getBoundingClientRect() { return { width: visible ? 60 : 0, height: visible ? 60 : 0 }; },
      click() {
        equal(values.muted, true); equal(values.defaultMuted, true);
        if (clickThrows) throw new Error('Synthetic platform click failure');
        buttonClicks.push(selector);
        if (clickEffect === 'chapter') document.URL = 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=999';
        else if (clickEffect === 'cards') cardsUrl = 'https://mooc1.chaoxing.com/knowledge/cards?knowledgeid=999';
        else if (clickEffect === 'attachment') attachmentData = '{"objectid":"other-object"}';
        else if (clickEffect === 'source') values.currentSrc = 'https://media.example.invalid/video/other-object/sd.mp4';
        else if (clickEffect === 'quality') values.currentSrc = 'https://media.example.invalid/video/object-a/hd.mp4?signature=TEST';
        else if (clickEffect === 'unmute') values.muted = false;
        else if (clickEffect === 'replace') mediaVideo = otherVideo;
        else if (clickEffect === 'invalidcards') cardsUrl = 'not-a-url';
        else if (clickEffect === 'toggle') values.paused = !values.paused;
      },
    };
  }
  bigButtons = Array.from({ length: bigCount }, () => button('button.vjs-big-play-button', bigVisible));
  playButtons = Array.from({ length: playCount }, () => button('button.vjs-play-control', playVisible));
  const sandbox = { URL, document };
  for (const name of ['window', 'globalThis', 'localStorage', 'setInterval', 'fetch', 'navigator']) {
    Object.defineProperty(sandbox, name, { get() { throw new Error(`Unexpected global ${name}`); } });
  }
  const mute = vm.runInNewContext(source, sandbox);
  return { run(options = { expected_chapter_id: '123', expected_object_id: 'object-a' }) {
    return plain(mute(options)); }, values, otherVideo, writes, buttonClicks };
}

let environment = fixture();
const first = environment.run();
equal(first.ok, true);
equal(first.before.muted, false);
equal(first.before.defaultMuted, false);
equal(first.after.muted, true);
equal(first.after.defaultMuted, true);
equal(first.scope.chapter_id, '123');
equal(first.scope.kind, 'current-course-video-only');
equal(first.action, 'mute'); equal(first.control_clicked, false); equal(environment.buttonClicks, []);
equal(first.media_key, { chapter_id: '123', object_id: 'object-a', source_path: '/video/object-a/sd.mp4' });
equal(environment.writes, ['muted', 'defaultMuted']);
for (const key of ['paused', 'ended', 'currentTime', 'duration', 'playbackRate', 'volume']) equal(first.after[key], first.before[key]);
equal(environment.otherVideo.muted, false);
equal(environment.otherVideo.defaultMuted, false);
equal(/src|http|session|signature/i.test(JSON.stringify(first)), false);
const second = environment.run();
equal(second.ok, true);
equal(second.before.muted, true);
equal(second.before.defaultMuted, true);
equal(second.after, first.after);
equal(second.media_key, first.media_key);

for (const options of [{}, null, { expected_chapter_id: 123 }, { expected_chapter_id: '' },
  { expected_chapter_id: '123 ' },
  { expected_chapter_id: '0123', expected_object_id: 'object-a' },
  { expected_chapter_id: '999', expected_object_id: 'object-a' },
  { expected_chapter_id: '123' }, { expected_chapter_id: '123', expected_object_id: '' },
  { expected_chapter_id: '123', expected_object_id: ' ' },
  { expected_chapter_id: '123', expected_object_id: 123 }]) {
  environment = fixture();
  equal(environment.run(options).ok, false);
  equal(environment.writes, []);
}
for (const [configuration, code] of [
  [{ url: 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=999' }, 'CHAPTER_MISMATCH'],
  [{ url: 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=123&chapterId=123' }, 'CHAPTER_MISMATCH'],
  [{ url: 'https://mooc1.chaoxing.com/mycourse/studentstudy' }, 'CHAPTER_MISMATCH'],
  [{ url: 'https://mooc1.chaoxing.com/mycourse/studentcourse?chapterId=123' }, 'WRONG_COURSE_PAGE'],
  [{ url: 'https://chaoxing.com.example.invalid/mycourse/studentstudy?chapterId=123' }, 'WRONG_COURSE_PAGE'],
  [{ outerCount: 0 }, 'OUTER_FRAME_NOT_UNIQUE'], [{ outerCount: 2 }, 'OUTER_FRAME_NOT_UNIQUE'],
  [{ wrongOuterTag: true }, 'OUTER_FRAME_NOT_UNIQUE'],
  [{ outerUnavailable: true }, 'OUTER_FRAME_UNAVAILABLE'], [{ outerThrows: true }, 'OUTER_FRAME_UNAVAILABLE'],
  [{ cardsUrl: 'https://mooc1.chaoxing.com/knowledge/cards?knowledgeid=old' }, 'CARDS_CHAPTER_MISMATCH'],
  [{ cardsUrl: 'https://mooc1.chaoxing.com/knowledge/cards?knowledgeid=123&knowledgeid=123' }, 'CARDS_CHAPTER_MISMATCH'],
  [{ cardsUrl: 'https://mooc1.chaoxing.com/knowledge/cards' }, 'CARDS_CHAPTER_MISMATCH'],
  [{ cardsUrl: '' }, 'CARDS_DOCUMENT_UNREADABLE'], [{ cardsUrl: 'not-a-url' }, 'CARDS_DOCUMENT_UNREADABLE'],
  [{ cardsThrows: true }, 'CARDS_DOCUMENT_UNREADABLE'],
  [{ innerCount: 0 }, 'VIDEO_FRAME_NOT_UNIQUE'], [{ innerCount: 2 }, 'VIDEO_FRAME_NOT_UNIQUE'],
  [{ attachmentData: '{' }, 'ATTACHMENT_DATA_UNREADABLE'], [{ attachmentThrows: true }, 'ATTACHMENT_DATA_UNREADABLE'],
  [{ attachmentData: 'null' }, 'ATTACHMENT_OBJECT_UNAVAILABLE'],
  [{ attachmentData: '{}' }, 'ATTACHMENT_OBJECT_UNAVAILABLE'],
  [{ attachmentData: '{"objectid":123}' }, 'ATTACHMENT_OBJECT_UNAVAILABLE'],
  [{ attachmentData: '{"objectid":" "}' }, 'ATTACHMENT_OBJECT_UNAVAILABLE'],
  [{ attachmentData: '{"objectid":"old-object"}' }, 'ATTACHMENT_OBJECT_MISMATCH'],
  [{ innerUnavailable: true }, 'VIDEO_FRAME_UNAVAILABLE'], [{ innerThrows: true }, 'VIDEO_FRAME_UNAVAILABLE'],
  [{ videoCount: 0 }, 'VIDEO_NOT_UNIQUE'], [{ videoCount: 2 }, 'VIDEO_NOT_UNIQUE'],
  [{ currentSrc: '', src: '' }, 'MEDIA_SOURCE_UNAVAILABLE'],
  [{ sourceThrows: true }, 'MEDIA_SOURCE_UNREADABLE'],
  [{ currentSrc: 'http://[broken' }, 'MEDIA_SOURCE_UNREADABLE'],
  [{ currentSrc: 'https://media.example.invalid/video/old-object/sd.mp4?object=object-a' }, 'MEDIA_OBJECT_MISMATCH'],
  [{ currentSrc: 'https://media.example.invalid/video/prefix-object-a/sd.mp4' }, 'MEDIA_OBJECT_MISMATCH'],
  [{ currentSrc: 'https://media.example.invalid/video/object-a-suffix/sd.mp4' }, 'MEDIA_OBJECT_MISMATCH'],
  [{ currentSrc: 'https://media.example.invalid/video/object-a.mp4' }, 'MEDIA_OBJECT_MISMATCH'],
  [{ currentSrc: 'https://object-a.example.invalid/video/old-object/sd.mp4' }, 'MEDIA_OBJECT_MISMATCH'],
  [{ currentSrc: 'https://media.example.invalid/video/%broken/sd.mp4' }, 'MEDIA_OBJECT_MISMATCH'],
]) {
  environment = fixture(configuration);
  const result = environment.run();
  equal(result.ok, false);
  equal(result.error.code, code);
  equal(environment.writes, []);
  equal(environment.values.muted, false);
  equal(environment.otherVideo.muted, false);
  equal(result.media_key, null);
}
// Metadata is not loaded before first play: use the real src property when currentSrc is empty.
environment = fixture({ currentSrc: '', src: 'https://media.example.invalid/video/object-a/sd.mp4?signature=TEST' });
equal(environment.run().ok, true);
equal(environment.writes, ['muted', 'defaultMuted']);
// Object IDs are evidence strings, not restricted to one historical hex format.
environment = fixture({ objectId: 'lesson-asset_42' });
const nonHex = environment.run({ expected_chapter_id: '123', expected_object_id: 'lesson-asset_42' });
equal(nonHex.ok, true);
equal(nonHex.media_key.object_id, 'lesson-asset_42');
environment = fixture({ objectId: 'asset name', currentSrc: 'https://media.example.invalid/video/asset%20name/sd.mp4?signature=TEST' });
equal(environment.run({ expected_chapter_id: '123', expected_object_id: 'asset name' }).ok, true);
// A signed source is never included in the result, on success or identity failure.
environment = fixture({ currentSrc: 'https://media.example.invalid/video/old-object/sd.mp4?signature=TEST' });
equal(/secret|signature|https?:|session/i.test(JSON.stringify(environment.run())), false);
environment = fixture({ writeFails: true });
const failedWrite = environment.run();
equal(failedWrite.ok, false);
equal(failedWrite.error.code, 'MUTE_WRITE_FAILED');
equal(failedWrite.after.muted, true);
equal(failedWrite.after.defaultMuted, false);
equal(environment.writes, ['muted', 'defaultMuted']);
equal(failedWrite.media_key.object_id, 'object-a');
// Explicit actions never call media.play/pause. They click one visible platform button only after muting.
const actionOptions = action => ({ expected_chapter_id: '123', expected_object_id: 'object-a', action });
environment = fixture();
const played = environment.run(actionOptions('play'));
equal(played.ok, true); equal(played.action, 'play'); equal(played.control_clicked, true);
equal(played.control_selector, 'button.vjs-big-play-button'); equal(played.identity_verified_after, true);
equal(played.before.paused, true); equal(played.after.paused, false);
equal(environment.buttonClicks, ['button.vjs-big-play-button']);
for (const key of ['currentTime', 'duration', 'playbackRate', 'volume']) equal(played.after[key], played.before[key]);
environment = fixture({ bigVisible: false });
const fallbackPlay = environment.run(actionOptions('play'));
equal(fallbackPlay.ok, true); equal(fallbackPlay.control_selector, 'button.vjs-play-control');
equal(environment.buttonClicks, ['button.vjs-play-control']);
environment = fixture({ initialPaused: false });
const paused = environment.run(actionOptions('pause'));
equal(paused.ok, true); equal(paused.action, 'pause'); equal(paused.after.paused, true);
equal(paused.identity_verified_after, true); equal(environment.buttonClicks, ['button.vjs-play-control']);
for (const [configuration, action] of [[{ initialPaused: false, bigCount: 0, playCount: 0 }, 'play'],
  [{ initialPaused: true, bigCount: 0, playCount: 0 }, 'pause']]) {
  environment = fixture(configuration); const result = environment.run(actionOptions(action));
  equal(result.ok, true); equal(result.control_clicked, false); equal(environment.buttonClicks, []);
  equal(result.before.paused, result.after.paused); equal(result.after.muted, true);
}
for (const action of ['seek', 'PLAY', '', null, 1, {}]) {
  environment = fixture(); const result = environment.run(actionOptions(action));
  equal(result.ok, false); equal(result.error.code, 'INVALID_ACTION'); equal(environment.writes, []); equal(environment.buttonClicks, []);
}
for (const [configuration, action, code] of [
  [{ bigCount: 0, playCount: 0 }, 'play', 'PLATFORM_CONTROL_NOT_UNIQUE'],
  [{ bigCount: 2 }, 'play', 'PLATFORM_CONTROL_NOT_UNIQUE'],
  [{ bigCount: 0, playCount: 2 }, 'play', 'PLATFORM_CONTROL_NOT_UNIQUE'],
  [{ initialPaused: false, playCount: 0 }, 'pause', 'PLATFORM_CONTROL_NOT_UNIQUE'],
  [{ initialPaused: false, playCount: 2 }, 'pause', 'PLATFORM_CONTROL_NOT_UNIQUE'],
  [{ bigVisible: false, playVisible: false }, 'play', 'PLATFORM_CONTROL_NOT_UNIQUE'],
  [{ controlDisabled: true }, 'play', 'PLATFORM_CONTROL_DISABLED'],
  [{ ariaDisabled: true }, 'play', 'PLATFORM_CONTROL_DISABLED'],
  [{ visibilityUnavailable: true }, 'play', 'CONTROL_VISIBILITY_UNAVAILABLE'],
]) {
  environment = fixture(configuration); const result = environment.run(actionOptions(action));
  equal(result.ok, false); equal(result.error.code, code); equal(environment.writes, []);
  equal(environment.buttonClicks, []); equal(result.control_clicked, false);
}
for (const [clickEffect, identityError] of [
  ['chapter', 'CHAPTER_MISMATCH'], ['cards', 'CARDS_CHAPTER_MISMATCH'],
  ['attachment', 'ATTACHMENT_OBJECT_MISMATCH'], ['source', 'MEDIA_OBJECT_MISMATCH'], ['replace', 'VIDEO_REPLACED'],
]) {
  environment = fixture({ clickEffect }); const result = environment.run(actionOptions('play'));
  equal(result.ok, false); equal(result.error.code, 'POST_ACTION_IDENTITY_MISMATCH');
  equal(result.error.identity_error, identityError); equal(result.control_clicked, true);
  equal(result.identity_verified_after, false); equal(environment.buttonClicks.length, 1);
}
environment = fixture({ clickEffect: 'invalidcards' });
equal(environment.run(actionOptions('play')).error.code, 'POST_ACTION_IDENTITY_UNAVAILABLE');
environment = fixture({ clickThrows: true });
const clickFailed = environment.run(actionOptions('play'));
equal(clickFailed.ok, false); equal(clickFailed.error.code, 'PLATFORM_CONTROL_FAILED');
equal(clickFailed.after.muted, true); equal(clickFailed.control_clicked, false); equal(environment.buttonClicks, []);
environment = fixture({ clickEffect: 'quality' });
const qualityChanged = environment.run(actionOptions('play'));
equal(qualityChanged.ok, true); equal(qualityChanged.media_key.source_path, '/video/object-a/hd.mp4');
equal(/signature|secret/.test(JSON.stringify(qualityChanged)), false);
environment = fixture({ clickEffect: 'unmute' });
const unmuted = environment.run(actionOptions('play'));
equal(unmuted.ok, false); equal(unmuted.error.code, 'MUTE_NOT_CONFIRMED'); equal(unmuted.control_clicked, true);
console.log(`PASS ${checks} Codex local-mute VM assertions; no browser, playback, or system audio access.`);
