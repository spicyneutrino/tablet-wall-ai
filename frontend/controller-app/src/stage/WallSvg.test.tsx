// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { SceneSchema } from '../api/scene';
import { WallSvg } from './WallSvg';
import type { WallLayout, WallSvgProps } from './WallSvg';

afterEach(cleanup);
beforeAll(() => vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }));

const layout: WallLayout = { kind: 'logical', width: 200, height: 200, placements: {
  a: { x: 20, y: 30, w: 100, h: 80, bezel: { left: 4, top: 2, right: 3, bottom: 5 } },
} };
const image = SceneSchema.parse({ type: 'image', asset: `sha256:${'a'.repeat(64)}`, url: '/assets/a',
  fit: 'cover', intrinsicWidth: 1600, intrinsicHeight: 1000, background: '#102030' });
const props: WallSvgProps = { layout, content: image, profileFor: () => null,
  statuses: { a: { status: 'offline', text: 'Offline', label: 'Tablet 1', number: 1 } }, interactive: false };

describe('WallSvg read-only drawing', () => {
  it.each([[2000, 1000], [1000, 2000], [8000, 200]])('preserves placements, bezels and empty bounds on a %sx%s wall', (width, height) => {
    const value = { ...layout, width, height };
    const before = structuredClone(value);
    const { container } = render(<WallSvg {...props} layout={value} />);
    const margin = width / 70;
    expect(container.querySelector('svg')?.getAttribute('viewBox')).toBe(`${-margin} ${-margin} ${width + margin * 2} ${height + margin * 2}`);
    expect(container.querySelector('svg')?.getAttribute('preserveAspectRatio')).toBe('xMidYMid meet');
    expect(value).toEqual(before);
    const active = container.querySelector('[data-screen="a"]');
    expect(['x', 'y', 'width', 'height'].map((name) => active?.getAttribute(name))).toEqual(['24', '32', '93', '73']);
    expect(container.querySelector('[data-body]')?.getAttribute('stroke')).toBeNull();
  });

  it('defines one wall-wide image and clips its uses to screens and wall bounds', () => {
    const { container } = render(<WallSvg {...props} statuses={{ a: { status: 'showing', text: 'Showing' } }} />);
    const images = container.querySelectorAll('image');
    expect(images).toHaveLength(1);
    expect(['x', 'y', 'width', 'height'].map((name) => images[0]?.getAttribute(name))).toEqual(['-60', '0', '320', '200']);
    const use = container.querySelector('use');
    expect(use?.getAttribute('href')).toBe(`#${images[0]?.id}`);
    expect(use?.parentElement?.getAttribute('clip-path')).toContain('-wall)');
    expect(use?.parentElement?.parentElement?.getAttribute('clip-path')).toContain('-screen)');
  });

  it('keeps labels, status text, hatching and selection available without making read-only tablets buttons', () => {
    const { container } = render(<WallSvg {...props} selected="a" />);
    expect(screen.getByRole('img', { name: 'Tablet 1, Offline, selected' })).toBeTruthy();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(container.querySelectorAll('[tabindex]')).toHaveLength(0);
    expect(container.querySelector('[data-device-id]')?.textContent).toContain('Offline');
    expect(container.querySelector('rect[fill^="url"]')).not.toBeNull();
    expect(container.querySelector('use')).toBeNull();
    expect(container.querySelector('rect[stroke="var(--stage-warn)"]')).not.toBeNull();
    expect(container.querySelector('rect[stroke="var(--stage-sel)"]')).not.toBeNull();
  });

  it('does not draw unavailable images or invent missing physical screens', () => {
    const profileFor = (id: string, revision?: number | string) => {
      expect([id, revision]).toEqual(['a', 7]);
      return null;
    };
    const { container } = render(<WallSvg {...props} profileFor={profileFor}
      layout={{ kind: 'physical', bounds: { x: -100, y: -100, width: 200, height: 200 },
        slots: { a: { center_x_mm: 0, center_y_mm: 0, profile_revision: 7 } } }}
      content={SceneSchema.parse({ ...image, available: false })} />);
    expect(container.querySelector('image')).toBeNull();
    expect(container.querySelector('[data-screen]')).toBeNull();
    expect(screen.getByRole('img', { name: /Missing profile/ })).toBeTruthy();
    expect(container.textContent).toContain('Missing profile');
  });

  it('keeps excluded tablets visible without painting the wall image on them', () => {
    const { container } = render(<WallSvg {...props} layout={{ kind: 'physical',
      bounds: { x: 0, y: 0, width: 200, height: 200 }, slots: { a: { center_x_mm: 100, center_y_mm: 100, participating: false } } }}
      profileFor={() => ({ active_width_mm: 80, active_height_mm: 100 })} />);
    expect(container.querySelector('[data-screen]')).not.toBeNull();
    expect(container.querySelector('use')).toBeNull();
    expect(screen.getByRole('img', { name: /Excluded/ })).toBeTruthy();
  });

  it('keeps tablet number order independent of insertion order and selection', () => {
    const value: WallLayout = { kind: 'logical', width: 300, height: 100, placements:
      Object.fromEntries(['m', 'a', 'z'].map((id, i) => [id, { x: i * 100, y: 0, w: 100, h: 100 }])) };
    const statuses = Object.fromEntries(['z', 'a', 'm'].map((id, i) => [id, { status: 'preview', text: 'Local preview', number: i + 1 }]));
    const { container, rerender } = render(<WallSvg {...props} layout={value} statuses={statuses} />);
    for (const selected of ['a', 'z', 'm']) {
      rerender(<WallSvg {...props} layout={value} statuses={statuses} selected={selected} />);
      expect([...container.querySelectorAll('[data-device-id]')].map((node) => node.getAttribute('data-device-id'))).toEqual(['z', 'a', 'm']);
    }
  });

  it('isolates clip and image IDs for simultaneous Preview and On wall monitors', () => {
    const { container } = render(<><WallSvg {...props} /><WallSvg {...props} /></>);
    const ids = [...container.querySelectorAll('[id]')].map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const use of container.querySelectorAll('use')) {
      expect(use.closest('svg')?.querySelectorAll('image')).toHaveLength(1);
    }
  });

  it('renders the supplied preview and applied layouts/content independently without changing them', () => {
    const applied = structuredClone({ layout: props.layout, content: props.content });
    const preview = SceneSchema.parse({ ...image, url: '/assets/preview', fit: 'contain' });
    const { container, rerender } = render(<WallSvg {...props} content={preview} layout={{ ...layout, width: 300 }} />);
    expect(container.querySelector('image')?.getAttribute('href')).toBe('/assets/preview');
    expect(container.querySelector('image')?.getAttribute('width')).toBe('300');
    rerender(<WallSvg {...props} />);
    expect(container.querySelector('image')?.getAttribute('href')).toBe('/assets/a');
    expect(container.querySelector('image')?.getAttribute('width')).toBe('320');
    expect(props.layout).toEqual(applied.layout);
    expect(props.content).toEqual(applied.content);
  });

  it('paints draft patterns in Preview without changing the applied image on On wall', () => {
    const showing = { a: { status: 'showing', text: 'Showing' } };
    const { container, rerender } = render(<><WallSvg {...props} statuses={showing} testPattern="grid" preview />
      <WallSvg {...props} statuses={showing} /></>);
    const [preview, live] = container.querySelectorAll('svg');
    expect(preview?.querySelector('image')).toBeNull();
    expect(preview?.querySelector('[data-preview-pattern="grid"]')).not.toBeNull();
    expect(live?.querySelector('image')?.getAttribute('href')).toBe('/assets/a');
    expect(live?.querySelector('[data-preview-pattern]')).toBeNull();
    rerender(<WallSvg {...props} statuses={showing} testPattern="black" preview />);
    expect(container.querySelector('image')).toBeNull();
    expect(container.querySelector('[data-preview-pattern]')).toBeNull();
    expect(container.querySelector('rect[fill="black"]')).not.toBeNull();
  });

  it('shows an explicit empty state', () => {
    render(<WallSvg {...props} layout={{ kind: 'logical', width: 200, height: 100, placements: {} }} content={null} />);
    expect(screen.getByText('No tablets placed')).toBeTruthy();
  });

  it('releases its size observation when the monitor unmounts', () => {
    const disconnect = vi.fn();
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect = disconnect; });
    const { unmount } = render(<WallSvg {...props} />);
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });
});
