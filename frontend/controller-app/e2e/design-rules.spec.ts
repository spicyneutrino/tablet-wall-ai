import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { installContrast, type Ring } from './contrast';

const image = fileURLToPath(new URL('./fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const tokens = readFileSync(fileURLToPath(new URL('../src/styles/tokens.css', import.meta.url)), 'utf8');
const viewports = [[390, 844], [820, 1180], [1440, 900]] as const;
const themes = ['light', 'dark'] as const;

// The scales come from tokens.css itself, so a token change moves the check with it.
const typeScale = [...tokens.matchAll(/--text-(?:title|heading|body|label|caption):\s*([\d.]+)rem/g)].map(match => Number(match[1]) * 16);
const spaceScale = [...tokens.matchAll(/--space-\d+:\s*(\d+)px/g)].map(match => Number(match[1]));

// 03-visual-spec.md section 9 names the only off-scale spacing: 2 px (logo mark gap, switch
// alignment), 36 px (step body under its label, select padding that clears the chevron), 44 px
// (input padding that clears a unit suffix). Hairlines (1 px) and 0 are always fine, and a
// margin that resolves from `auto` is not a chosen value. Each exception is scoped to the
// element that owns it, so the same number anywhere else still fails.
const exceptions: { selector: string; values: number[] }[] = [
  { selector: '.wall-mark', values: [2] },
  { selector: 'select.input', values: [36] },
  { selector: '.measure-step-body', values: [36] },
  { selector: '.unit .input', values: [44] },
];

type Issue = { rule: string; where: string; detail: string };

const walkType = ({ scale }: { scale: number[] }): Issue[] => {
  const issues: Issue[] = [];
  const control = 'input, select, textarea';
  for (const element of document.querySelectorAll('body *')) {
    if (element.closest('.sr-only, svg')) continue;
    if (!element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) || element.getClientRects().length === 0) continue;
    const owns = [...element.childNodes].some(node => node.nodeType === Node.TEXT_NODE && (node.textContent ?? '').trim());
    if (!owns && !element.matches(control)) continue;
    const size = Math.round(parseFloat(getComputedStyle(element).fontSize) * 100) / 100;
    if (!scale.includes(size)) {
      issues.push({
        rule: 'type',
        where: `${element.tagName.toLowerCase()}.${String(element.getAttribute('class') ?? '').slice(0, 60)}`,
        detail: `${size}px "${(element.textContent ?? '').trim().slice(0, 30)}"`,
      });
    }
  }
  return issues;
};

const walkSpace = ({ scale, scoped }: { scale: number[]; scoped: { selector: string; values: number[] }[] }): Issue[] => {
  const properties = [
    'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'row-gap', 'column-gap',
  ];
  const issues: Issue[] = [];
  for (const element of document.querySelectorAll('body *')) {
    if (element.closest('.sr-only, svg')) continue;
    if (!element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) || element.getClientRects().length === 0) continue;
    const style = getComputedStyle(element);
    const authored = element.computedStyleMap();
    for (const property of properties) {
      const computed = authored.get(property);
      if (computed instanceof CSSKeywordValue) continue;
      const raw = style.getPropertyValue(property);
      if (raw === 'normal' || raw === '') continue;
      const value = Math.abs(Math.round(parseFloat(raw) * 100) / 100);
      if (Number.isNaN(value) || value === 0 || value === 1 || scale.includes(value)) continue;
      if (scoped.some(entry => entry.values.includes(value) && element.closest(entry.selector))) continue;
      issues.push({
        rule: 'space',
        where: `${element.tagName.toLowerCase()}.${String(element.getAttribute('class') ?? '').slice(0, 60)}`,
        detail: `${property} ${value}px`,
      });
    }
  }
  return issues;
};

// Focuses every enabled control after one real Tab press, so :focus-visible applies exactly as
// it does for keyboard users, then measures the ring the browser actually painted.
const focusSweep = (): { checked: number; rings: Ring[]; unreachable: string[]; notVisible: string[] } => {
  const selector = 'button, a[href], input:not([type="hidden"]), select, textarea, summary, [role="tab"], '
    + '[role="button"], [role="switch"], [tabindex]:not([tabindex="-1"])';
  const modal = document.querySelector('dialog[open]');
  const kit = Reflect.get(window, '__contrast') as { ring: (element: Element) => Ring; settle: () => void };
  const controls = [...document.querySelectorAll(selector)].filter(element => {
    if (element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true') return false;
    if (element.closest('[inert], [aria-hidden="true"], .sr-only, details:not([open]) > :not(summary)')) return false;
    if (modal && !modal.contains(element)) return false;
    // A Radix roving-focus root (tab list, toggle group) keeps no ring of its own; its items own it.
    if (element.matches('[data-orientation]') && element.querySelector('[tabindex], button')) return false;
    return element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
  });
  const rings: Ring[] = [];
  const unreachable: string[] = [];
  const notVisible: string[] = [];
  const name = (element: Element) => `${element.tagName.toLowerCase()}.${String(element.getAttribute('class') ?? '').slice(0, 40)} "${(element.getAttribute('aria-label') ?? element.textContent ?? '').trim().slice(0, 30)}"`;
  for (const element of controls) {
    if (element instanceof HTMLElement || element instanceof SVGElement) element.focus({ preventScroll: true });
    // Focus handed to a child (toggle group) is the child's turn, and the child is in this list.
    if (document.activeElement !== element && element.contains(document.activeElement)) continue;
    if (document.activeElement !== element) { unreachable.push(name(element)); continue; }
    if (!element.matches(':focus-visible')) { notVisible.push(name(element)); continue; }
    kit.settle();
    rings.push(kit.ring(element));
  }
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  return { checked: controls.length, rings, unreachable, notVisible };
};

async function audit(page: Page, state: string, problems: string[]) {
  await page.evaluate(() => document.fonts.ready);
  const label = `${state}`;
  const type = await page.evaluate(walkType, { scale: typeScale });
  const space = await page.evaluate(walkSpace, { scale: spaceScale, scoped: exceptions });
  for (const issue of [...type, ...space]) problems.push(`${label}: ${issue.rule} ${issue.where} ${issue.detail}`);
  await page.keyboard.press('Tab');
  const sweep = await page.evaluate(focusSweep);
  for (const name of sweep.unreachable) problems.push(`${label}: focus does not land on ${name}`);
  for (const name of sweep.notVisible) problems.push(`${label}: focus on ${name} is not :focus-visible`);
  for (const ring of sweep.rings) {
    if (!ring.kind) problems.push(`${label}: no focus ring on ${ring.where} "${ring.label}"`);
    else if (ring.width < 2) problems.push(`${label}: focus ring ${ring.width}px on ${ring.where} "${ring.label}" is under 2px`);
    else if (ring.ratio < 3) problems.push(`${label}: focus ring ${ring.color} on ${ring.surround} is ${ring.ratio.toFixed(2)}:1 on ${ring.where} "${ring.label}"`);
  }
  return { type: type.length, space: space.length, controls: sweep.checked };
}

test.use({ serverScope: 'design-rules' });
test('Rendered type and spacing use the spec scales, and every enabled control has a visible focus ring', async ({ page, server, api, tablets, guard }) => {
  test.setTimeout(420_000);
  const fleet = await tablets(4);
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(4);
  const asset = await api.upload(image);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  await installContrast(page);
  await guard(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(typeScale.sort((a, b) => a - b), 'the type scale read from tokens.css').toEqual([13, 14, 16, 18, 22]);
  expect(spaceScale.sort((a, b) => a - b), 'the spacing scale read from tokens.css').toEqual([4, 8, 12, 16, 24, 32, 48]);

  const problems: string[] = [];
  const totals = { states: 0, controls: 0 };
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    for (const theme of themes) {
      const check = async (state: string) => {
        const where = `${width}x${height} ${theme} ${state}`;
        const counts = await audit(page, where, problems);
        expect(counts.controls, `${where}: the sweep found controls`).toBeGreaterThan(2);
        totals.states++;
        totals.controls += counts.controls;
      };
      const fresh = async () => {
        await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
        await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4, { timeout: 20_000 });
        await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
      };

      await fresh();
      await check('wall with an image');

      await page.locator(`#tablet-row-${fleet[0]!.id}`).click();
      await expect(page.locator('#tablet-title')).toHaveText(/\S+/);
      await check('tablet details');
      await page.getByRole('button', { name: 'Measure…', exact: true }).click();
      await page.getByLabel('Which model is it?').selectOption('manual');
      await check('measure model');
      await page.getByRole('button', { name: 'Next: size and bezels', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Size and bezels', exact: true })).toBeVisible();
      await check('measure size');
      await page.getByLabel('Width', { exact: true }).fill('220');
      await page.getByLabel('Height', { exact: true }).fill('123.75');
      await page.getByRole('button', { name: 'Next: ruler check', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Skip', exact: true })).toBeVisible();
      await check('measure ruler');
      await page.getByRole('button', { name: 'Skip', exact: true }).click();
      await check('measure review');

      await fresh();
      await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveAttribute('aria-pressed', 'true');
      await check('edit layout');

      await fresh();
      await page.getByRole('button', { name: 'Server', exact: true }).click();
      const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
      await expect(sheet).toBeVisible();
      const tabs = await sheet.getByRole('tab').allInnerTexts();
      expect(tabs.length, 'the Server sheet has several tabs').toBeGreaterThan(2);
      for (const tab of tabs) {
        await sheet.getByRole('tab', { name: tab.trim(), exact: true }).click();
        await check(`Server sheet, ${tab.trim()}`);
      }

      await fresh();
      await page.getByRole('button', { name: 'All images', exact: true }).click();
      await expect(page.getByRole('dialog', { name: 'Library', exact: true })).toBeVisible();
      await check('Library');
    }
  }
  console.log(`DESIGN RULES: ${totals.states} states, ${totals.controls} focus checks, ${problems.length} problems`);
  expect(problems, 'type scale, spacing scale and focus rings across every state, size and theme').toEqual([]);
});
