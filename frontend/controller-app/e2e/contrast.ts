import type { Page } from '@playwright/test';

export type TextRun = { where: string; text: string; ratio: number; foreground: string; background: string };
export type Ring = { where: string; label: string; kind: 'outline' | 'shadow' | null; width: number; ratio: number; color: string; surround: string };

type Kit = {
  text: (element: Element) => TextRun[];
  ring: (element: Element) => Ring;
  settle: () => void;
};

// Runs inside the page. Both parity specs and design-rules.spec.ts install it with
// page.addInitScript, so every contrast number comes from one implementation of WCAG 2.x.
function installContrastKit() {
  type Rgba = [number, number, number, number];
  const context = document.createElement('canvas').getContext('2d');
  const parse = (value: string): Rgba | null => {
    if (!context) return null;
    context.fillStyle = '#000000';
    context.fillStyle = value;
    const normalized = String(context.fillStyle);
    if (normalized.startsWith('#')) {
      return [parseInt(normalized.slice(1, 3), 16), parseInt(normalized.slice(3, 5), 16), parseInt(normalized.slice(5, 7), 16), 1];
    }
    const match = normalized.match(/rgba?\(([^)]+)\)/);
    if (!match?.[1]) return null;
    const parts = match[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0, parts[3] ?? 1];
  };
  const over = (top: Rgba, bottom: Rgba): Rgba => [0, 1, 2].map(index => (top[index] ?? 0) * top[3] + (bottom[index] ?? 0) * (1 - top[3])).concat(1) as Rgba;
  const luminance = (colour: Rgba) => {
    const [r = 0, g = 0, b = 0] = colour.slice(0, 3).map(value => {
      const channel = value / 255;
      return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a: Rgba, b: Rgba) => {
    const one = luminance(a);
    const two = luminance(b);
    return (Math.max(one, two) + 0.05) / (Math.min(one, two) + 0.05);
  };
  const hex = (colour: Rgba) => `#${colour.slice(0, 3).map(value => Math.round(value).toString(16).padStart(2, '0')).join('')}`;
  const where = (element: Element) => `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ''}.${String(element.getAttribute('class') ?? '').slice(0, 50)}`;
  const surfaceBehind = (start: Element | null) => {
    const chain: Element[] = [];
    for (let node = start; node; node = node.parentElement) chain.push(node);
    let colour = parse(getComputedStyle(document.documentElement).backgroundColor) ?? [255, 255, 255, 1];
    if (colour[3] < 1) colour = over(colour, [255, 255, 255, 1]);
    let painted = false;
    for (const node of chain.reverse()) {
      const style = getComputedStyle(node);
      const own = parse(style.backgroundColor);
      if (own && own[3] > 0) colour = over(own, colour);
      if (style.backgroundImage !== 'none') painted = true;
    }
    return { colour, painted };
  };

  const kit: Kit = {
    // Every text run under `element`, composited over the real ancestors' backgrounds.
    text(element) {
      const rows: TextRun[] = [];
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = (node.textContent ?? '').trim();
        const parent = node.parentElement;
        if (!text || !parent || parent.closest('svg, .sr-only')) continue;
        const style = getComputedStyle(parent);
        if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') continue;
        const { colour, painted } = surfaceBehind(parent);
        if (painted) continue;
        const foreground = parse(style.color);
        if (!foreground) continue;
        const composed = over(foreground, colour);
        rows.push({ where: where(parent), text: text.slice(0, 36), ratio: ratio(composed, colour), foreground: hex(composed), background: hex(colour) });
      }
      return rows;
    },
    // The ring a focused element paints: a 2px+ outline, or a solid box-shadow ring.
    ring(element) {
      const style = getComputedStyle(element);
      const label = (element.getAttribute('aria-label') ?? element.textContent ?? '').trim().slice(0, 40);
      const none = { where: where(element), label, kind: null, width: 0, ratio: 0, color: '', surround: '' } as const;
      let kind: Ring['kind'] = null;
      let width = 0;
      let paint: string | null = null;
      if (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0) {
        kind = 'outline';
        width = parseFloat(style.outlineWidth);
        paint = style.outlineColor;
      } else {
        const solid = style.boxShadow.match(/(rgba?\([^)]+\))\s+0px\s+0px\s+0px\s+([\d.]+)px(?!\s*inset)/);
        if (solid?.[1] && solid[2]) { kind = 'shadow'; width = parseFloat(solid[2]); paint = solid[1]; }
      }
      const colour = paint ? parse(paint) : null;
      if (!kind || !colour) return none;
      // An outline with a negative offset sits on the element; every other ring sits on what is behind it.
      const inset = kind === 'outline' && parseFloat(style.outlineOffset) < 0;
      const surround = surfaceBehind(inset ? element : element.parentElement).colour;
      const composed = over(colour, surround);
      return { where: where(element), label, kind, width, ratio: ratio(composed, surround), color: hex(composed), surround: hex(surround) };
    },
    // Finish colour transitions so a hover or press is measured settled, not mid-frame.
    settle() {
      for (const animation of document.getAnimations()) {
        try { animation.finish(); } catch { /* An infinite animation has no end to finish. */ }
      }
    },
  };
  Reflect.set(window, '__contrast', kit);
}

export const installContrast = (page: Page) => page.addInitScript(installContrastKit);

export const textRuns = (element: Element): TextRun[] => {
  const kit = Reflect.get(window, '__contrast') as Kit;
  kit.settle();
  return kit.text(element);
};

export const focusRing = (element: Element): Ring => {
  const kit = Reflect.get(window, '__contrast') as Kit;
  kit.settle();
  return kit.ring(element);
};
