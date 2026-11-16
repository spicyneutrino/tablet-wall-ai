import { ChevronDown, ChevronUp } from 'lucide-react';
import { useId } from 'react';
import { WallSvg } from '../../stage/WallSvg';
import { Tally } from '../../ui/Tally';
import { Button } from '../../ui/Button';
import WallPlaceholder from '../preview/WallPlaceholder';
import { useShellView, contentName } from '../preview/useShellView';

function Monitor() {
  const { config, loading, firstRun, unreachable, statuses, profileFor } = useShellView();
  return <div className={`stage-well live-stage${loading ? ' skel' : ''}${unreachable ? ' live-stale' : ''}`} data-stage="onwall">
    {firstRun ? <WallPlaceholder /> : config ? <div className="wall-frame"><WallSvg layout={config.layout} content={config.scene.content}
      statuses={statuses} profileFor={profileFor} interactive={false} /></div> : null}
  </div>;
}

export default function OnWall() {
  const { config, loading, firstRun, unreachable, lastReport, server } = useShellView();
  return <section className="desktop-onwall" aria-label="On wall">
    <div className="monitor-label"><Tally kind="live" />
      <span className="t-caption monitor-description">{loading ? null : firstRun ? 'Nothing yet' : unreachable ? <>Unknown since <time data-report-time dateTime={lastReport?.dateTime}>{lastReport?.label ?? 'the last report'}</time></>
        : server.uncertain ? 'Not confirmed' : contentName(config?.scene.content ?? null)}</span>
    </div>
    <Monitor />
  </section>;
}

export function MobileOnWall({ expanded, onExpandedChange }: { expanded: boolean; onExpandedChange: (value: boolean) => void }) {
  const { config, loading, unreachable, firstRun, lastReport, server } = useShellView();
  const id = useId();
  return <div className="mobile-onwall">
    <div className="mobile-onwall-line"><Tally kind="live" />
      {loading ? <span className="skel live-line-skeleton" aria-label="Loading wall status" role="img" />
        : <span className="t-body t-muted monitor-description">{firstRun ? 'Nothing yet'
          : unreachable ? <>Unknown since <time data-report-time dateTime={lastReport?.dateTime}>{lastReport?.label ?? 'the last report'}</time></>
            : server.uncertain ? 'Not confirmed' : contentName(config?.scene.content ?? null)}</span>}
      {!loading && !firstRun ? <Button variant="ghost" size="sm" aria-expanded={expanded} aria-controls={id}
        onClick={() => onExpandedChange(!expanded)}>{expanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
        {expanded ? 'Hide' : 'View'}</Button> : null}
    </div>
    <div id={id} hidden={!expanded}><Monitor /></div>
  </div>;
}
