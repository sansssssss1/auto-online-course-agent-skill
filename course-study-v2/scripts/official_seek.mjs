/** Use the visible icourse163 player seek bar; leave progress reporting to the player. */
export async function dragToTime(page, targetSeconds, { selector = '.m-progressbar.progresswrap' } = {}) {
  const read = () => page.evaluate(() => {
    const v = document.querySelector('video');
    return v ? { t:v.currentTime, duration:v.duration, paused:v.paused, ended:v.ended, rate:v.playbackRate } : null;
  });
  const before = await read();
  if (!before || !Number.isFinite(before.duration) || before.duration <= 0) return { accepted:false, reason:'metadata-unavailable', before };
  const bar = page.locator(selector).first();
  if (!await bar.count()) return { accepted:false, reason:'seek-control-unavailable', before };
  await bar.hover();
  const rect = await bar.boundingBox();
  if (!rect || rect.width < 100) return { accepted:false, reason:'seek-control-unavailable', before };
  const target = Math.max(0, Math.min(before.duration - .5, targetSeconds));
  const start = Math.max(2, Math.min(rect.width - 2, rect.width * before.t / before.duration));
  const end = Math.max(2, Math.min(rect.width - 2, rect.width * target / before.duration));
  await page.mouse.move(rect.x + start, rect.y + rect.height / 2);
  await page.mouse.down();
  try {
    await page.mouse.move(rect.x + end, rect.y + rect.height / 2, {steps:12});
  } finally {
    await page.mouse.up();
  }
  await page.waitForTimeout(1500);
  const after = await read();
  return { accepted:!!after && Math.abs(after.t - target) <= 15, target, before, after };
}

export async function seekToEnd(page, options = {}) {
  try {
    const duration = await page.locator('video').first().evaluate(v => v.duration).catch(() => NaN);
    if (!Number.isFinite(duration)) return { accepted:false, reason:'metadata-unavailable' };
    return await dragToTime(page, Math.max(0, duration - 8), options);
  } catch (error) {
    return { accepted:false, reason:'seek-ui-error', detail:String(error.message || error).slice(0,200) };
  }
}
