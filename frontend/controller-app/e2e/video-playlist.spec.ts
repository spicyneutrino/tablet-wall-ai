import { expect, test } from './fixtures';
import type { Tablet } from './fixtures';
import { makeClip } from './fixtures/video';

test.use({ serverScope: 'video-playlist' });

type Assets = { assets: { id: string; name: string; kind?: string; durationMs?: number }[] };
type Playlist = { etag: string; playlist: { items: { asset: string; dwell_ms: number }[]; loop: boolean } };
type Playback = { state: string; live?: { current?: { kind?: string } | null } };

async function placeWall(api: Parameters<Parameters<typeof test>[2]>[0]['api'], tablet: Tablet) {
  const display = await api.request.put(`/api/v3/displays/${tablet.id}`, { headers: { 'If-Match': (await api.config()).etag }, data: {
    active_width_mm: 400, active_height_mm: 225, bezels: { left: 0, top: 0, right: 0, bottom: 0 },
    label: 'Tablet 1', provenance: 'hand-derived' } });
  expect(display.ok(), await display.text()).toBe(true);
  const calibration = await api.request.put(`/api/v3/calibrations/${tablet.id}`, { headers: { 'If-Match': ((await display.json()) as { etag: string }).etag }, data: {
    profile_revision: 1, viewport_width: 800, viewport_height: 450, dpr: 1, orientation: 0, mode: 'tab', quarter_turn: 0,
    panel_offset_mm: [0, 0], mm_per_css: [0.5, 0.5], anchor_edge: 'top-left', uncertainty_mm: 0, method: 'hand-derived' } });
  expect(calibration.ok(), await calibration.text()).toBe(true);
  const layout = await api.request.put('/api/v3/layout', { headers: { 'If-Match': (await api.config()).etag }, data: {
    bounds: { x: 0, y: 0, width: 440, height: 250 },
    slots: { [tablet.id]: { center_x_mm: 220, center_y_mm: 125, mount_angle: 0,
      nudge_x_mm: 0, nudge_y_mm: 0, profile_revision: 1, calibration_revision: 1, participating: true } } } });
  expect(layout.ok(), await layout.text()).toBe(true);
}

const sample = (tablet: Tablet) => tablet.page.evaluate(() => {
  const video = [...document.querySelectorAll('video')].find(candidate => {
    const rect = candidate.getBoundingClientRect();
    const style = getComputedStyle(candidate);
    return style.display !== 'none' && style.visibility !== 'hidden' && Number.parseFloat(style.opacity) > 0 && rect.width > 0 && rect.height > 0;
  });
  return video ? { paused: video.paused, ready: video.readyState, time: video.currentTime, width: video.videoWidth } : null;
});

test('A video uploaded in the app joins the playlist, is saved, and plays on a real tablet', async ({
  server, api, tablets, page, guard, axe,
}, info) => {
  test.setTimeout(120_000);
  await guard(page);
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('One tablet is required.');
  await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.online, { timeout: 15_000 }).toBe(true);
  await placeWall(api, tablet);
  const clip = await makeClip(info.outputPath('clip.mp4'));

  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Upload…', exact: true }).click();
  await page.setInputFiles('input[type="file"]', clip);
  const media = async () => ((await (await api.request.get('/media')).json()) as Assets).assets;
  await expect.poll(async () => (await media()).find(asset => asset.name === 'clip.mp4')?.kind, { timeout: 30_000 }).toBe('video');
  const video = (await media()).find(asset => asset.name === 'clip.mp4');
  if (!video?.durationMs) throw new Error('The uploaded clip has no duration.');
  await expect(page.getByText('clip.mp4, Fill'), 'a video is never previewed as an image scene').toHaveCount(0);

  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await sheet.getByRole('tab', { name: 'Playback' }).click();
  await sheet.getByRole('switch', { name: /Playlist and playback/ }).check();
  await sheet.getByLabel('Image to add').selectOption({ label: 'clip.mp4' });
  await sheet.getByRole('button', { name: 'Add', exact: true }).click();
  const seconds = sheet.getByLabel('clip.mp4: seconds on screen');
  await expect(seconds).toHaveValue('Full clip');
  await expect(seconds).toBeDisabled();
  await sheet.getByRole('switch', { name: 'Loop' }).check();
  const clipSeconds = `${video.durationMs / 1000} s loop`;
  const summary = sheet.locator('.playback-head .t-caption');
  await expect(summary, 'an unsaved video item already counts its own length').toHaveText(`1 item, ${clipSeconds}`);
  const save = sheet.getByRole('button', { name: 'Save playlist' });
  await save.click();
  await expect(sheet.getByText('Playlist saved.')).toBeVisible();
  await expect(summary).toHaveText(`1 item, ${clipSeconds}`);
  await expect(save).toBeDisabled();
  await expect(save).toHaveAccessibleDescription('No changes to save.');

  const saved = (await (await api.request.get('/api/v3/playlist')).json()) as Playlist;
  expect(saved.playlist).toMatchObject({ items: [{ asset: video.id, dwell_ms: video.durationMs }], loop: true });

  const state = sheet.locator('.playback-head .state');
  await sheet.getByRole('button', { name: 'Start', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Start playback' });
  await dialog.getByRole('button', { name: 'Start playback', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(state).toHaveText('Playing', { timeout: 30_000 });

  await expect.poll(async () => ((await (await api.request.get('/api/v3/playback')).json()) as Playback).live?.current?.kind,
    { message: 'the server plays the video item' }).toBe('video');
  await expect.poll(async () => {
    const first = await sample(tablet);
    await page.waitForTimeout(500);
    const second = await sample(tablet);
    return Boolean(first && second && !first.paused && !second.paused && second.ready >= 2 && second.width === 320 && second.time - first.time >= 0.15);
  }, { timeout: 20_000, message: 'the tablet shows a visible video whose currentTime advances' }).toBe(true);

  expect((await axe(page)).violations).toEqual([]);
  await sheet.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(state).toHaveText('Stopped');
});
