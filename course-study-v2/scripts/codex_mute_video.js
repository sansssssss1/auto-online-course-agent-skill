/* Writable CDP Runtime.evaluate only; never use through read-only evaluate.
 * Default action='mute' never plays/pauses. Explicit play/pause clicks only a
 * verified visible platform button in the same verified video document. */
(function muteCourseVideo(options = {}) {
  let scope = null;
  let mediaKey = null;
  let video = null;
  let before = null;
  let action = 'mute';
  let controlClicked = false;
  let controlSelector = null;
  let identityVerifiedAfter = false;
  const state = media => ({
    muted: media.muted, defaultMuted: media.defaultMuted,
    paused: media.paused, ended: media.ended,
    currentTime: Number.isFinite(media.currentTime) ? media.currentTime : null,
    duration: Number.isFinite(media.duration) ? media.duration : null,
    playbackRate: media.playbackRate, volume: media.volume,
  });
  const fail = (code, details = {}) => ({ ok: false, error: { code, ...details }, scope, media_key: mediaKey,
    action, control_clicked: controlClicked, control_selector: controlSelector,
    identity_verified_after: identityVerifiedAfter, before,
    after: video && before ? state(video) : null });
  const frameDocument = frame => {
    try { return frame.contentDocument; } catch { return null; }
  };
  function visibleButtons(media, selector) {
    const view = media.defaultView;
    if (!view || typeof view.getComputedStyle !== 'function') throw new Error('visibility-unavailable');
    return Array.from(media.querySelectorAll(selector)).filter(button => {
      if (String(button.tagName).toUpperCase() !== 'BUTTON' || button.ownerDocument !== media) return false;
      const css = view.getComputedStyle(button);
      const rect = button.getBoundingClientRect();
      return css && css.display !== 'none' && css.visibility !== 'hidden' && css.visibility !== 'collapse' &&
        String(css.opacity) !== '0' && rect && rect.width > 0 && rect.height > 0;
    });
  }
  function verifyAfterControl() {
    const page = new URL(document.URL || document.documentURI || '');
    const chapters = page.searchParams.getAll('chapterId');
    if (page.pathname !== '/mycourse/studentstudy' ||
        !(page.hostname === 'chaoxing.com' || page.hostname.endsWith('.chaoxing.com')) ||
        chapters.length !== 1 || chapters[0] !== options.expected_chapter_id) return 'CHAPTER_MISMATCH';
    const outer = Array.from(document.querySelectorAll('#iframe'));
    if (outer.length !== 1 || String(outer[0].tagName).toUpperCase() !== 'IFRAME') return 'OUTER_FRAME_NOT_UNIQUE';
    const course = frameDocument(outer[0]);
    if (!course) return 'OUTER_FRAME_UNAVAILABLE';
    const cards = new URL(course.URL || course.documentURI || '');
    const knowledgeIds = cards.searchParams.getAll('knowledgeid');
    if (knowledgeIds.length !== 1 || knowledgeIds[0] !== options.expected_chapter_id) return 'CARDS_CHAPTER_MISMATCH';
    const inner = Array.from(course.querySelectorAll('iframe.ans-insertvideo-online'));
    if (inner.length !== 1) return 'VIDEO_FRAME_NOT_UNIQUE';
    const attachment = JSON.parse(inner[0].getAttribute('data') || '');
    if (!attachment || attachment.objectid !== options.expected_object_id) return 'ATTACHMENT_OBJECT_MISMATCH';
    const media = frameDocument(inner[0]);
    if (!media) return 'VIDEO_FRAME_UNAVAILABLE';
    const videos = Array.from(media.querySelectorAll('video'));
    if (videos.length !== 1) return 'VIDEO_NOT_UNIQUE';
    if (videos[0] !== video) return 'VIDEO_REPLACED';
    const rawSource = videos[0].currentSrc || videos[0].src;
    if (typeof rawSource !== 'string' || !rawSource.trim()) return 'MEDIA_SOURCE_UNAVAILABLE';
    const source = new URL(rawSource, media.URL || media.documentURI || undefined);
    const matches = source.pathname.split('/').some(segment => {
      try { return decodeURIComponent(segment) === options.expected_object_id; } catch { return false; }
    });
    if (!matches) return 'MEDIA_OBJECT_MISMATCH';
    mediaKey = { chapter_id: chapters[0], object_id: attachment.objectid, source_path: source.pathname };
    return null;
  }
  try {
    if (!options || typeof options.expected_chapter_id !== 'string' || !/^\d+$/.test(options.expected_chapter_id)) {
      return fail('EXPECTED_CHAPTER_REQUIRED');
    }
    if (typeof options.expected_object_id !== 'string' || !options.expected_object_id.trim()) {
      return fail('EXPECTED_OBJECT_REQUIRED');
    }
    action = options.action === undefined ? 'mute' : options.action;
    if (!['mute', 'play', 'pause'].includes(action)) return fail('INVALID_ACTION');
    const page = new URL(document.URL || document.documentURI || '');
    if (page.pathname !== '/mycourse/studentstudy' ||
        !(page.hostname === 'chaoxing.com' || page.hostname.endsWith('.chaoxing.com'))) {
      return fail('WRONG_COURSE_PAGE');
    }
    const chapters = page.searchParams.getAll('chapterId');
    if (chapters.length !== 1 || chapters[0] !== options.expected_chapter_id) return fail('CHAPTER_MISMATCH');
    scope = { kind: 'current-course-video-only', chapter_id: chapters[0],
      document_path: page.pathname, frame_chain: ['#iframe', 'iframe.ans-insertvideo-online'] };
    const outer = Array.from(document.querySelectorAll('#iframe'));
    if (outer.length !== 1 || String(outer[0].tagName).toUpperCase() !== 'IFRAME') return fail('OUTER_FRAME_NOT_UNIQUE');
    const course = frameDocument(outer[0]);
    if (!course) return fail('OUTER_FRAME_UNAVAILABLE');
    let cards;
    try { cards = new URL(course.URL || course.documentURI || ''); }
    catch { return fail('CARDS_DOCUMENT_UNREADABLE'); }
    const knowledgeIds = cards.searchParams.getAll('knowledgeid');
    if (knowledgeIds.length !== 1 || knowledgeIds[0] !== options.expected_chapter_id) {
      return fail('CARDS_CHAPTER_MISMATCH');
    }
    const inner = Array.from(course.querySelectorAll('iframe.ans-insertvideo-online'));
    if (inner.length !== 1) return fail('VIDEO_FRAME_NOT_UNIQUE');
    let attachment;
    try { attachment = JSON.parse(inner[0].getAttribute('data') || ''); }
    catch { return fail('ATTACHMENT_DATA_UNREADABLE'); }
    if (!attachment || typeof attachment.objectid !== 'string' || !attachment.objectid.trim()) {
      return fail('ATTACHMENT_OBJECT_UNAVAILABLE');
    }
    if (attachment.objectid !== options.expected_object_id) return fail('ATTACHMENT_OBJECT_MISMATCH');
    const media = frameDocument(inner[0]);
    if (!media) return fail('VIDEO_FRAME_UNAVAILABLE');
    const videos = Array.from(media.querySelectorAll('video'));
    if (videos.length !== 1) return fail('VIDEO_NOT_UNIQUE');
    video = videos[0];
    let source;
    try {
      const rawSource = video.currentSrc || video.src;
      if (typeof rawSource !== 'string' || !rawSource.trim()) return fail('MEDIA_SOURCE_UNAVAILABLE');
      source = new URL(rawSource, media.URL || media.documentURI || undefined);
    } catch { return fail('MEDIA_SOURCE_UNREADABLE'); }
    const objectMatchesPath = source.pathname.split('/').some(segment => {
      try { return decodeURIComponent(segment) === options.expected_object_id; }
      catch { return false; }
    });
    if (!objectMatchesPath) return fail('MEDIA_OBJECT_MISMATCH');
    mediaKey = { chapter_id: chapters[0], object_id: attachment.objectid, source_path: source.pathname };
    before = state(video);
    let control = null;
    const needsControl = action === 'play' ? before.paused === true : action === 'pause' ? before.paused === false : false;
    if (needsControl) {
      let buttons;
      try {
        if (action === 'play') {
          controlSelector = 'button.vjs-big-play-button';
          buttons = visibleButtons(media, controlSelector);
          if (!buttons.length) {
            controlSelector = 'button.vjs-play-control';
            buttons = visibleButtons(media, controlSelector);
          }
        } else {
          controlSelector = 'button.vjs-play-control';
          buttons = visibleButtons(media, controlSelector);
        }
      } catch { return fail('CONTROL_VISIBILITY_UNAVAILABLE'); }
      if (buttons.length !== 1) return fail('PLATFORM_CONTROL_NOT_UNIQUE');
      control = buttons[0];
      if (control.disabled || control.getAttribute('aria-disabled') === 'true') return fail('PLATFORM_CONTROL_DISABLED');
      if (typeof control.click !== 'function') return fail('PLATFORM_CONTROL_UNAVAILABLE');
    }
    video.muted = true;
    video.defaultMuted = true;
    if (video.muted !== true || video.defaultMuted !== true) return fail('MUTE_NOT_CONFIRMED');
    if (control) {
      try { control.click(); controlClicked = true; }
      catch { return fail('PLATFORM_CONTROL_FAILED'); }
      let mismatch;
      try { mismatch = verifyAfterControl(); }
      catch { return fail('POST_ACTION_IDENTITY_UNAVAILABLE'); }
      if (mismatch) return fail('POST_ACTION_IDENTITY_MISMATCH', { identity_error: mismatch });
      identityVerifiedAfter = true;
    }
    const after = state(video);
    if (after.muted !== true || after.defaultMuted !== true) return fail('MUTE_NOT_CONFIRMED');
    return { ok: true, scope, media_key: mediaKey, action, control_clicked: controlClicked,
      control_selector: controlSelector, identity_verified_after: identityVerifiedAfter, before, after };
  } catch {
    // Do not expose page URLs, signed media sources, or arbitrary exception text.
    try { return fail(before ? 'MUTE_WRITE_FAILED' : 'PAGE_READ_FAILED'); }
    catch { return { ok: false, error: { code: 'MEDIA_STATE_UNAVAILABLE' }, scope, media_key: mediaKey,
      action, control_clicked: controlClicked, control_selector: controlSelector,
      identity_verified_after: identityVerifiedAfter, before, after: null }; }
  }
})
