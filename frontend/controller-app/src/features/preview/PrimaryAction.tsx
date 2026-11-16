import { Button } from '../../ui/Button';
import { useShellView } from './useShellView';
import { usePlaybackAction } from './usePlaybackAction';
import { useArrangementAction } from './useArrangementAction';
import { useContentAction } from './useContentAction';
import type { ReactNode } from 'react';

export type PreviewAction = { label: string; busyLabel: string; onClick: () => void; disabledReason?: string; secondary?: ReactNode };

export default function PrimaryAction() {
  const playback = usePlaybackAction();
  const arrangement = useArrangementAction();
  const content = useContentAction();
  const { loading, unreachable, firstRun, server } = useShellView();
  const action = playback ?? arrangement ?? content;
  const reason = loading ? 'Loading…' : unreachable ? 'The server can’t be reached.' : server.uncertain ? 'Refresh first.'
    : !server.supported ? 'Update the console before editing.' : firstRun ? 'Add a tablet first.' : action?.disabledReason;
  const disabledReason = reason ?? (!action ? 'Pick a source to preview it.' : undefined);
  return <div className="primary-action">
    {disabledReason ? <Button size="lg" disabled disabledReason={disabledReason}>{action?.label ?? 'Show on wall'}</Button>
      : server.busy ? <Button size="lg" busy busyLabel={action?.busyLabel ?? 'Working…'}>{action?.label ?? 'Show on wall'}</Button>
        : <Button size="lg" busyLabel={action?.busyLabel} onClick={action?.onClick}>{action?.label ?? 'Show on wall'}</Button>}
    {action?.secondary}
  </div>;
}
