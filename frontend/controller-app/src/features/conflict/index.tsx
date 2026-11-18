import { useState } from 'react';
import { GitCompareArrows } from 'lucide-react';
import { buildGridPreview } from '../../state/commands/grid';
import { keepMine, useTheirs as discardDraft } from '../../state/store';
import type { DraftTarget } from '../../state/store';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { useShell } from '../preview/ShellContext';
import { conflictItems } from './model';
import type { ConflictItem } from './model';
import './conflict.css';

const targetOf = (item: ConflictItem): DraftTarget => item.kind === 'form' ? { kind: 'form', key: item.key } : { kind: item.kind };
const keyOf = (item: ConflictItem) => item.kind === 'form' ? item.key : item.kind;

function focusPreview() {
  requestAnimationFrame(() => document.querySelector<HTMLElement>('[data-stage="preview"]')?.focus({ preventScroll: true }));
}

export default function Conflict() {
  const { store, session } = useShell();
  const state = useWallStore(store, value => value);
  const [message, setMessage] = useState('');
  const items = conflictItems(state);
  if (!items.length) return null;
  const { server } = state;
  const reason = server.rosterUnreachable ? 'The server can’t be reached.' : server.uncertain || server.etagState !== 'current'
    ? 'Refresh status first.' : server.busy ? 'Wait for the current change to finish.' : undefined;

  async function keep(item: ConflictItem) {
    setMessage('');
    const current = store.getState();
    if (item.kind === 'grid') {
      const outcome = await buildGridPreview(store, session, true);
      if (outcome.kind !== 'ok') { setMessage(outcome.kind === 'rejected' ? outcome.message : 'Refresh status, then keep your grid again.'); return; }
      focusPreview();
      return;
    }
    const target = targetOf(item);
    const draft = target.kind === 'form' ? current.forms[target.key] : target.kind === 'arrangement' ? current.arrangement : current.content;
    if (!draft || !current.server.etag || !keepMine(store, target, { etag: current.server.etag, version: draft.version })) {
      setMessage('The wall changed again. Review the new change first.');
      return;
    }
    focusPreview();
  }
  function discard(item: ConflictItem) {
    setMessage('');
    discardDraft(store, targetOf(item));
    focusPreview();
  }
  return <section id="conflict" tabIndex={-1} className="conflict-review" aria-labelledby="conflict-title">
    <h2 className="note-title" id="conflict-title"><GitCompareArrows aria-hidden="true" />Review the change</h2>
    {items.map(item => <div className="conflict-item" key={keyOf(item)} role="group" aria-label={`${item.title} change`}>
      <dl className="conflict-diff t-body">
        <dt className="t-muted">{item.title} on wall now</dt><dd>{item.wall}</dd>
        <dt className="t-muted">Your edit</dt><dd>{item.mine}</dd>
      </dl>
      <div className="conflict-actions">
        {item.keepable ? reason ? <Button variant="secondary" disabled disabledReason={reason}>Keep mine</Button>
          : <Button variant="secondary" onClick={() => void keep(item)}>Keep mine</Button> : null}
        <Button variant="ghost" onClick={() => discard(item)}>Use theirs</Button>
      </div>
    </div>)}
    <p className="t-caption">Keep mine puts your edit on top of the change. Use theirs drops your edit.</p>
    {message ? <p className="t-caption text-err" role="status">{message}</p> : null}
  </section>;
}
