import { Send } from 'lucide-react';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { GridApplyAction } from '../sources/layouts/GridBuilder';
import { useShellView } from './useShellView';
import { usePlaybackAction } from './usePlaybackAction';
import { useArrangementAction } from './useArrangementAction';
import { useContentAction } from './useContentAction';
import { useShell } from './ShellContext';
import type { ReactNode } from 'react';

export type PreviewAction = { label: string; busyLabel: string; onClick: () => void; disabledReason?: string; secondary?: ReactNode };

export default function PrimaryAction() {
  const { store } = useShell();
  const measuring = useWallStore(store, state => !!state.ui.measureStep);
  const gridPreview = useWallStore(store, state => !!state.grid?.preview);
  const gridBuilderOpen = useWallStore(store, state => state.ui.gridBuilderOpen);
  const playback = usePlaybackAction();
  const arrangement = useArrangementAction();
  const content = useContentAction();
  const { loading, unreachable, firstRun, server } = useShellView();
  if (gridBuilderOpen) return <div className="primary-action" />;
  if (gridPreview) return <GridApplyAction />;
  const action = playback ?? arrangement ?? content;
  const reason = loading ? 'Loading…' : unreachable ? 'The server can’t be reached.' : server.uncertain ? 'Refresh first.'
    : !server.supported ? 'Update the console before editing.' : firstRun ? 'Add a tablet first.'
      : measuring ? 'Finish measuring first.' : action?.disabledReason;
  const disabledReason = reason ?? (!action ? 'Pick a source to preview it.' : undefined);
  // While measuring, the measure stepper owns the primary action; keep this one secondary.
  const variant = measuring ? 'secondary' : 'primary';
  return <div className={`primary-action${action ? ' is-draft' : ''}${arrangement ? ' max-lg:!grid max-lg:!grid-cols-[minmax(0,1fr)_auto] max-lg:items-start' : ''}`}>
    {disabledReason ? <Button variant={variant} size="lg" disabled disabledReason={disabledReason}>{action?.label ?? 'Show on wall'}</Button>
      : server.busy ? <Button variant={variant} size="lg" busy busyLabel={action?.busyLabel ?? 'Working…'}>{action?.label ?? 'Show on wall'}</Button>
        : <Button variant={variant} size="lg" busyLabel={action?.busyLabel} onClick={action?.onClick}>{action?.label === 'Show on wall' ? <Send aria-hidden="true" /> : null}{action?.label ?? 'Show on wall'}</Button>}
    {action?.secondary}
  </div>;
}
