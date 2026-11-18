import { createElement, Fragment, useState } from 'react';
import { REVIEW_CHANGE_FIRST } from '../../copy';
import { arrangementDirty } from '../../state/drafts/arrangement';
import { applyArrangement } from '../../state/commands/layout';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { useShell } from './ShellContext';
import { useArrangementEditor } from './EditToolbar';
import type { PreviewAction } from './PrimaryAction';

export function useArrangementAction(): PreviewAction | null {
  const { store, session } = useShell();
  const { discard, error, gesture } = useArrangementEditor();
  const arrangement = useWallStore(store, state => state.arrangement);
  const editing = useWallStore(store, state => state.ui.editLayout);
  const busy = useWallStore(store, state => state.server.busy);
  const blocked = useWallStore(store, state => !!state.grid?.preview || !!state.content.selection);
  const [message, setMessage] = useState('');
  if (!editing && !arrangementDirty(arrangement)) return null;
  return { label: 'Apply layout', busyLabel: 'Applying…',
    disabledReason: blocked ? 'Discard the other preview before editing the layout.' : arrangement?.conflict ? REVIEW_CHANGE_FIRST
      : error || gesture.error || (!arrangementDirty(arrangement) ? 'Move a tablet to change the layout.' : undefined),
    onClick: () => {
      setMessage('');
      void applyArrangement(store, session).then(async outcome => {
        if (outcome.kind === 'conflict') {
          try { await session.refresh(); } catch { setMessage('The wall changed. Refresh status before applying again.'); return; }
        }
        setMessage(outcome.kind === 'ok' ? 'Layout applied.' : outcome.kind === 'rejected' ? outcome.message
          : outcome.kind === 'conflict' ? 'The wall changed. Review On wall before applying again.'
          : outcome.kind === 'uncertain' ? 'Not confirmed. Refresh status and inspect the wall before retrying.' : 'Refresh status before applying the layout.');
      });
    },
    secondary: createElement(Fragment, null,
      createElement(Button, { variant: 'ghost', 'aria-disabled': busy, onClick: () => { discard(); setMessage(''); } }, 'Discard'),
      message ? createElement('p', { role: 'status', className: 't-caption col-span-2' }, message) : null),
  };
}
