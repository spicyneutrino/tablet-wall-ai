import { CircleCheck, Replace } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { disabledWhen, replacementPair, unsavedBlock, wallBlock } from '../../state/commands/lifecycle';
import type { Pair } from '../../state/commands/lifecycle';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { useTabletName } from '../playback/useTabletName';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
import { ReplaceDialog } from '../tablet/Lifecycle';

export default function ReplacementOffer() {
  const { store } = useShell();
  const { tablets, config, server, loading, unreachable, firstRun } = useShellView();
  const notice = useWallStore(store, state => state.ui.lifecycleNotice);
  const forms = useWallStore(store, state => state.forms);
  const nameOf = useTabletName();
  const [open, setOpen] = useState(false);
  // The pair is kept while the dialog is open: a tablet that blips offline must not close the review.
  const [target, setTarget] = useState<Pair | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!notice) return;
    // After the dialog closes, which hands focus back to a control that may be gone.
    const timer = window.setTimeout(() => noticeRef.current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [notice]);
  const pair = loading || unreachable || firstRun ? null : replacementPair(config, server.roster);
  const model = pair ? tablets.find(tablet => tablet.id === pair.newId)?.model : undefined;
  const block = pair ? wallBlock(server) || unsavedBlock(forms, [pair.newId, pair.oldId]) : '';
  return <>
    {notice ? <div className="note note-ok" role="status" tabIndex={-1} ref={noticeRef}>
      <p className="note-title"><CircleCheck aria-hidden="true" />Done</p>
      <p className="t-body">{notice}</p>
      <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => {
        store.setState(state => ({ ui: { ...state.ui, lifecycleNotice: null } }));
        document.getElementById('tablet-health')?.focus({ preventScroll: true });
      }}>Dismiss</Button>
    </div> : null}
    {pair ? <section className="note note-info" aria-labelledby="replacement-offer-title">
      <h3 className="note-title" id="replacement-offer-title"><Replace aria-hidden="true" />
        {model && model !== 'Model not set' ? `A new ${model} joined` : 'A new tablet joined'}</h3>
      <p className="t-body">{nameOf(pair.newId)} is online and not on the wall. If it replaces {nameOf(pair.oldId)}, put it in {nameOf(pair.oldId)}’s place.
        You review everything before anything changes.</p>
      <Button variant="secondary" className="justify-self-start"
        {...disabledWhen(block)} onClick={() => { setTarget(pair); setOpen(true); }}>
        <Replace aria-hidden="true" />Use the new tablet here</Button>
    </section> : null}
    {target ? <ReplaceDialog newId={target.newId} oldId={target.oldId} open={open} onOpenChange={setOpen} /> : null}
  </>;
}
