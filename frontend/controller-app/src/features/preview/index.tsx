import { Move, TabletSmartphone, Clock } from 'lucide-react';
import { useState } from 'react';
import { WallSvg } from '../../stage/WallSvg';
import { useWallStore, selectPreviewLayout, selectPreviewContent, selectStageMode } from '../../state/hooks';
import { testPatternName } from '../../state/commands/testPatterns';
import { Button } from '../../ui/Button';
import { Tally } from '../../ui/Tally';
import { useShell } from './ShellContext';
import { useShellView, contentName } from './useShellView';
import { MobileOnWall } from '../onwall';
import WallPlaceholder from './WallPlaceholder';

export default function Preview() {
  const { store } = useShell();
  const { loading, firstRun, unreachable, lastReport, config, statuses, profileFor, tablets } = useShellView();
  const layout = useWallStore(store, selectPreviewLayout);
  const content = useWallStore(store, selectPreviewContent);
  const selected = useWallStore(store, state => state.ui.selected);
  const editing = useWallStore(store, state => state.ui.editLayout);
  const mode = useWallStore(store, selectStageMode);
  const testPattern = useWallStore(store, state => state.ui.testPattern);
  const [liveExpanded, setLiveExpanded] = useState(false);
  const label = loading ? 'Loading the wall…' : firstRun ? 'Waiting for tablets' : unreachable ? 'Last known wall'
    : editing || mode === 'arrangement-preview' ? 'Your layout'
      : testPattern ? testPatternName(testPattern) : mode === 'image-preview' ? contentName(content) : 'Same as the wall';
  function selectFromStage(target: EventTarget | null) {
    if (!(target instanceof Element)) return;
    const key = target.closest('[data-device-id]')?.getAttribute('data-device-id');
    const tablet = tablets.find(tablet => tablet.id === key);
    if (tablet) store.setState(state => ({ ui: { ...state.ui, selected: tablet.id, drill: null } }));
  }
  return <section className="preview-pinned" aria-label="Preview">
    <div className="monitor-label">
      <Tally kind="preview" /><span className="t-body t-muted monitor-description">{label}</span>
      <div className="preview-tools">
        {!loading && !firstRun && !unreachable && config ? <Button variant="secondary" aria-pressed={editing}
          aria-label="Edit layout" onClick={() => store.setState(state => ({ ui: { ...state.ui, editLayout: !editing } }))}>
          <Move aria-hidden="true" /><span className="edit-label">Edit layout</span>
        </Button> : null}
      </div>
    </div>
    <div className={`stage-well preview-stage${mode !== 'live' || testPattern ? ' is-draft' : ''}`} data-stage="preview" tabIndex={0} role="group"
      aria-label="Preview wall. Use Left and Right to select a tablet."
      onClick={event => selectFromStage(event.target)}
      onKeyDown={event => {
        if (event.target !== event.currentTarget || !tablets.length || !['ArrowLeft', 'ArrowRight', 'Enter', ' '].includes(event.key)) return;
        event.preventDefault();
        const index = tablets.findIndex(tablet => tablet.id === selected);
        const next = event.key === 'ArrowRight' ? index + 1
          : event.key === 'ArrowLeft' ? (index < 0 ? tablets.length - 1 : index - 1) : Math.max(0, index);
        const tablet = tablets[(next + tablets.length) % tablets.length];
        if (tablet) store.setState(state => ({ ui: { ...state.ui, selected: tablet.id, drill: null } }));
      }}>
      {loading ? <WallPlaceholder loading />
        : layout && !firstRun ? <div className="wall-frame"><WallSvg layout={layout} content={content} profileFor={profileFor}
          statuses={statuses} selected={selected ?? undefined} interactive /></div>
        : <><WallPlaceholder /><div className="stage-empty"><TabletSmartphone aria-hidden="true" /><p className="t-heading">No tablets on the wall yet</p>
          <p className="t-body">They appear here as they join.</p></div></>}
      {unreachable ? <span className="chip chip-err stage-stamp"><Clock aria-hidden="true" />
        {lastReport ? <>As of <time data-report-time dateTime={lastReport?.dateTime}>{lastReport.label}</time></> : 'Last known wall'}</span> : null}
    </div>
    <MobileOnWall expanded={liveExpanded} onExpandedChange={setLiveExpanded} />
  </section>;
}
