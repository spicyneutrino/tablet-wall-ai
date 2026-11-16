// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ConfigSchema } from '../../../api/config';
import { A, configFixture, deviceFixture, renderFixture } from '../../../session/testFixtures';
import { createSession } from '../../../session/session';
import { createWallStore } from '../../../state/store';
import { ShellContext } from '../../preview/ShellContext';
import Tests from './index';

afterEach(cleanup);

function setup(online: boolean) {
  const store = createWallStore();
  const transport = vi.fn<typeof fetch>();
  const session = createSession({ store, fetch: transport, isDirty: () => false });
  const base = configFixture('base');
  const device = deviceFixture(A, { online, number: 1, render: renderFixture(online ? 'displayed' : 'offline') });
  const config = ConfigSchema.parse({ ...base, runtime: { ...base.runtime, devices: { [A]: device } } });
  store.setState(state => ({ server: { ...state.server, config, etag: config.etag, etagState: 'current',
    roster: { [A]: device }, transportText: 'Live operator updates connected.' } }));
  const view = render(<ShellContext value={{ store, session }}><Tests /></ShellContext>);
  return { store, session, transport, ...view };
}

it('shows both test patterns and the five colour swatches', () => {
  const { session } = setup(true);
  expect(screen.getByRole('button', { name: 'Calibration grid' })).toHaveAttribute('aria-pressed', 'false');
  expect(screen.getByRole('button', { name: 'Black' })).toBeVisible();
  for (const name of ['Red', 'Green', 'Blue', 'White', 'Black']) expect(screen.getByLabelText(name)).toBeVisible();
  session.destroy();
});

it('selecting a test pattern previews it and sends nothing', () => {
  const { store, transport, session } = setup(true);
  fireEvent.click(screen.getByRole('button', { name: 'Calibration grid' }));
  expect(store.getState().ui.testPattern).toBe('grid');
  expect(screen.getByRole('button', { name: 'Calibration grid' })).toHaveAttribute('aria-pressed', 'true');
  expect(transport).not.toHaveBeenCalled();
  session.destroy();
});

it('disables both colour commands with the visible reason when no tablet is online', () => {
  const { session } = setup(false);
  const all = screen.getByRole('button', { name: 'All tablets' });
  const one = screen.getByRole('button', { name: 'This tablet' });
  expect(all).toBeDisabled();
  expect(one).toBeDisabled();
  expect(screen.getAllByText('No tablets online')).toHaveLength(2);
  expect(all).toHaveAccessibleDescription('No tablets online');
  session.destroy();
});

it('asks for a selection before sending a colour to one tablet', () => {
  const { session } = setup(true);
  expect(screen.getByRole('button', { name: 'All tablets' })).toBeEnabled();
  const one = screen.getByRole('button', { name: 'This tablet' });
  expect(one).toBeDisabled();
  expect(one).toHaveAccessibleDescription('Select a tablet in the list first.');
  session.destroy();
});
