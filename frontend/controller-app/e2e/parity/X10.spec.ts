import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-X10' });
test('X10 On an empty wall at 1280×800, the join address and Add tablets are inside the first viewport', async ({ page, server, guard }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { name: 'Next step: add your first tablet', exact: true })).toBeVisible();
  const join = page.locator('.nextstep-join .join-address');
  await expect(join).toBeVisible();
  await expect(join, 'the join address is a host and port a tablet can open').toHaveText(/^((\d{1,3}\.){3}\d{1,3}|localhost):\d+$/);
  await expect(page.locator('.nextstep-join img[alt="QR code for the tablet address"]')).toBeVisible();
  const copy = page.getByRole('button', { name: 'Copy link', exact: true });
  await expect(copy).toBeVisible();
  await expect(page.locator('.nextstep-join')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));

  const boxes = await page.evaluate(() => {
    const box = (element: Element | null) => {
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    };
    return {
      viewport: { width: innerWidth, height: innerHeight },
      scrollY: window.scrollY,
      documentWidth: document.documentElement.scrollWidth,
      heading: box(document.querySelector('#next-step-title')),
      card: box(document.querySelector('.nextstep-join')),
      address: box(document.querySelector('.nextstep-join .join-address')),
      copy: box([...document.querySelectorAll('button')].find(button => button.textContent?.trim() === 'Copy link') ?? null),
      qr: box(document.querySelector('.nextstep-join img')),
    };
  });
  expect(boxes.scrollY, 'the first viewport is not scrolled').toBe(0);
  expect(boxes.documentWidth, 'no horizontal overflow at 1280x800').toBeLessThanOrEqual(1280);
  const inside = (name: string, box: { x: number; y: number; width: number; height: number } | null) => {
    if (!box) throw new Error(`${name} must be visible and measurable`);
    expect(box.x, `${name} starts inside the first viewport`).toBeGreaterThanOrEqual(0);
    expect(box.y, `${name} starts inside the first viewport`).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width, `${name} ends inside the first viewport`).toBeLessThanOrEqual(boxes.viewport.width + 0.5);
    expect(box.y + box.height, `${name} ends inside the first viewport`).toBeLessThanOrEqual(boxes.viewport.height + 0.5);
  };
  inside('the Add-tablets card', boxes.card);
  inside('the join address', boxes.address);
  inside('the Copy link button', boxes.copy);
  inside('the QR code', boxes.qr);
  inside('the Next step heading', boxes.heading);
  console.log(`X10 1280x800: ${JSON.stringify(boxes)}`);
});
