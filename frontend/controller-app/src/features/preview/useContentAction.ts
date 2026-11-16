import { createElement, useState } from 'react';
import { patternOutcomeText, showTestPattern } from '../../state/commands/testPatterns';
import { show } from '../../state/commands/scene';
import { recallSavedScene } from '../../state/commands/savedScenes';
import { editContent, keepMine } from '../../state/store';
import { useWallStore } from '../../state/hooks';
import type { Scene, SceneInput } from '../../api/scene';
import { ContentActionFeedback } from '../sources/images/ContentActionFeedback';
import { useShell } from './ShellContext';
import type { PreviewAction } from './PrimaryAction';

const wallBackground = '#0b1120';

function alreadyOnWall(draft: SceneInput, wall: Scene): boolean {
  if (draft.type !== wall.type) return false;
  if (draft.type !== 'image' || wall.type !== 'image') return true;
  return wall.available !== false && draft.asset === wall.asset && draft.fit === wall.fit
    && (draft.background ?? wallBackground) === (wall.background ?? wallBackground);
}

export function useContentAction(): PreviewAction | null {
  const { store, session } = useShell();
  const pattern = useWallStore(store, state => state.ui.testPattern);
  const content = useWallStore(store, state => state.content);
  const wall = useWallStore(store, state => state.server.config?.scene.content ?? null);
  const [message, setMessage] = useState('');
  const [fitOpen, setFitOpen] = useState(false);
  const saved = content.savedScene;
  if (pattern) return {
    label: 'Show on wall', busyLabel: 'Showing…',
    onClick: () => { void showTestPattern(store, session, pattern).then(outcome => setMessage(patternOutcomeText(outcome))); },
    secondary: message ? createElement('p', { className: 't-caption', role: 'status' }, message) : undefined,
  };
  if (!content.selection && !message) return null;
  async function apply() {
    const trigger = document.activeElement;
    const version = store.getState().content.version;
    let moved = false;
    const track = (event: FocusEvent) => { if (event.target !== trigger) moved = true; };
    document.addEventListener('focusin', track);
    setMessage('');
    try {
      const outcome = saved
        ? await recallSavedScene(store, session, saved.name)
        : await show(store, session);
      if (outcome.kind === 'conflict') {
        try { await session.refresh(); } catch {
          setMessage('The wall changed. Refresh status before rebuilding this preview.');
          return;
        }
      }
      if (store.getState().content.version !== version && store.getState().content.selection) return;
      const applied = saved ? `Content “${saved.name}” is on the wall.` : 'Content applied.';
      const changed = saved ? 'The wall changed. Pick the saved content again to show it.'
        : 'The wall changed. Review On wall, then rebuild this preview.';
      setMessage(outcome.kind === 'ok' ? applied : outcome.kind === 'conflict' ? changed
        : outcome.kind === 'uncertain' ? 'Not confirmed. Refresh status and inspect the wall before retrying.'
        : outcome.kind === 'rejected' ? outcome.message : 'Refresh status before showing this preview.');
      requestAnimationFrame(() => {
        const active = document.activeElement;
        if (moved || active !== trigger && active !== document.body && active !== document.documentElement) return;
        if (trigger instanceof HTMLElement && trigger.isConnected && !trigger.matches(':disabled')) return;
        const selected = store.getState().ui.selected;
        const target = outcome.kind === 'ok' ? (selected ? document.querySelector('#tablet-action-name') : null) ?? document.querySelector('[data-all-images]')
          : document.querySelector('[data-rebuild-preview]');
        if (target instanceof HTMLElement) target.focus({ preventScroll: true });
      });
    } finally { document.removeEventListener('focusin', track); }
  }
  return {
    label: 'Show on wall', busyLabel: 'Showing…', onClick: () => { void apply(); },
    disabledReason: !content.selection ? 'Pick a source to preview it.' : content.conflict ? 'Review the change first.'
      : wall && alreadyOnWall(content.selection, wall) ? 'This is already on the wall.' : undefined,
    secondary: createElement(ContentActionFeedback, { content, message, fitOpen, setFitOpen,
      discard: () => { editContent(store, { type: 'discard' }); setMessage(''); },
      rebuild: () => {
        const { server, content } = store.getState();
        if (server.etag && keepMine(store, { kind: 'content' }, { etag: server.etag, version: content.version })) setMessage('Preview rebuilt. Choose Show on wall.');
      } }),
  };
}
