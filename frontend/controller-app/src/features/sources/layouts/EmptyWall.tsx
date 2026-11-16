import { useEffect, useId, useRef, useState } from 'react';
import { clsx } from 'clsx';
import { entries } from '../../../domain/layout';
import type { Layout as LayoutDoc } from '../../../domain/layout';
import { useWallStore } from '../../../state/hooks';
import { clearWall, outcomeMessage } from '../../../state/commands/savedLayouts';
import { Button } from '../../../ui/Button';
import { ModalDialog } from '../../../ui/ModalDialog';
import { useShell } from '../../preview/ShellContext';

const clock = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

export function EmptyWall() {
  const { store, session } = useShell();
  const config = useWallStore(store, state => state.server.config);
  const etagState = useWallStore(store, state => state.server.etagState);
  const busy = useWallStore(store, state => state.server.busy);
  const uncertain = useWallStore(store, state => state.server.uncertain);
  const supported = useWallStore(store, state => state.server.supported);
  const checkedAt = useWallStore(store, state => state.server.rosterCheckedAt);
  const [open, setOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  const headingId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const placements = config ? Object.keys(entries(config.layout as unknown as LayoutDoc)).length : 0;
  const previous = config?.previous_layout_saved ?? null;
  const restoreAt = checkedAt ? new Date(checkedAt) : new Date();

  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);

  const reason = !config ? 'Waiting for the wall.' : uncertain ? 'Refresh status first.'
    : !supported ? 'Update the console before clearing the wall.' : busy ? 'Another change is in progress.'
      : etagState !== 'current' ? 'Refresh status before clearing the wall.'
        : !placements ? 'The wall is already empty.' : null;

  async function confirmClear() {
    setWorking(true);
    const outcome = await clearWall(store, session);
    setWorking(false);
    setOpen(false);
    if (outcome.kind === 'ok') {
      setMessage({ tone: 'ok', text: 'Active positions cleared. Tablets and saved arrangements are retained.' });
      return;
    }
    setMessage({ tone: 'err', text: outcomeMessage(outcome) });
  }

  return <>
    <section className="grid gap-3" aria-labelledby={headingId}>
      <h3 id={headingId} className="t-heading">Clear wall</h3>
      <p className="t-body measure">Takes every tablet off the wall. Names, measurements and saved layouts stay.</p>
      <div>
        {reason ? <Button variant="danger" disabled disabledReason={reason}>Clear wall…</Button>
          : <Button variant="danger" onClick={() => setOpen(true)}>Clear wall…</Button>}
      </div>
      {message ? <p className={clsx('t-body', message.tone === 'ok' ? 'text-ok' : 'text-err')} role="status">{message.text}</p> : null}
    </section>

    {/* The Server panel is itself a dialog: stop its close handler from firing when this one closes. */}
    <ModalDialog open={open} onOpenChange={setOpen} title="Clear every position?"
      onClose={event => event.stopPropagation()}>
      <p className="t-body">The wall goes blank until you apply a layout.{previous
        ? ` You can bring this one back from Layouts, Restore ${clock.format(restoreAt)}.`
        : ' Names, measurements and saved layouts stay.'}</p>
      <p className="t-body t-muted">{placements === 1 ? '1 tablet is placed on the wall.'
        : `${placements} tablets are placed on the wall.`}</p>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" ref={cancelRef} autoFocus onClick={() => setOpen(false)}>Cancel</Button>
        {working ? <Button variant="danger-solid" busy busyLabel="Clearing…">Clear wall</Button>
          : <Button variant="danger-solid" onClick={() => void confirmClear()}>Clear wall</Button>}
      </div>
    </ModalDialog>
  </>;
}

export default EmptyWall;
