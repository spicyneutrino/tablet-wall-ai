// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createWallStore } from '../../state/store';
import { createSession } from '../../session/session';
import { ShellContext } from './ShellContext';
import PrimaryAction from './PrimaryAction';
import type { PreviewAction } from './PrimaryAction';
import { usePlaybackAction } from './usePlaybackAction';
import { useArrangementAction } from './useArrangementAction';
import { useContentAction } from './useContentAction';

vi.mock('./usePlaybackAction', () => ({ usePlaybackAction: vi.fn() }));
vi.mock('./useArrangementAction', () => ({ useArrangementAction: vi.fn() }));
vi.mock('./useContentAction', () => ({ useContentAction: vi.fn() }));
afterEach(cleanup);
beforeEach(() => vi.resetAllMocks());

function setup(unreachable = false) {
  const store = createWallStore();
  const session = createSession({ store, isDirty: () => false });
  store.setState(state => ({ server: { ...state.server, supported: true, rosterError: 'No snapshot yet', rosterUnreachable: unreachable } }));
  const view = render(<ShellContext value={{ store, session }}><PrimaryAction /></ShellContext>);
  return { store, session, ...view };
}

describe('the preview action shared by feature units', () => {
  it('gives playback priority, then layout, then content, and invokes only the visible action', () => {
    const playback: PreviewAction = { label: 'Start', busyLabel: 'Starting…', onClick: vi.fn() };
    const layout: PreviewAction = { label: 'Apply layout', busyLabel: 'Applying…', onClick: vi.fn() };
    const content: PreviewAction = { label: 'Show on wall', busyLabel: 'Showing…', onClick: vi.fn() };
    vi.mocked(usePlaybackAction).mockReturnValue(playback);
    vi.mocked(useArrangementAction).mockReturnValue(layout);
    vi.mocked(useContentAction).mockReturnValue(content);
    const { rerender, store, session } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Start' }));
    expect(playback.onClick).toHaveBeenCalledOnce();
    expect(layout.onClick).not.toHaveBeenCalled();
    expect(content.onClick).not.toHaveBeenCalled();
    vi.mocked(usePlaybackAction).mockReturnValue(null);
    rerender(<ShellContext value={{ store, session }}><PrimaryAction /></ShellContext>);
    fireEvent.click(screen.getByRole('button', { name: 'Apply layout' }));
    expect(layout.onClick).toHaveBeenCalledOnce();
    vi.mocked(useArrangementAction).mockReturnValue(null);
    rerender(<ShellContext value={{ store, session }}><PrimaryAction /></ShellContext>);
    fireEvent.click(screen.getByRole('button', { name: 'Show on wall' }));
    expect(content.onClick).toHaveBeenCalledOnce();
  });

  it('shows a reason and sends no action while the server cannot be reached', () => {
    const onClick = vi.fn();
    vi.mocked(useContentAction).mockReturnValue({ label: 'Show on wall', busyLabel: 'Showing…', onClick });
    setup(true);
    const button = screen.getByRole('button', { name: 'Show on wall' });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription('The server can’t be reached.');
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});
