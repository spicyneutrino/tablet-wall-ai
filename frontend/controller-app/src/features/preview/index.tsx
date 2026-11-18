import { Move, TabletSmartphone, Clock, Undo2, Redo2 } from 'lucide-react';
import { useState } from 'react';
import { WallSvg } from '../../stage/WallSvg';
import { useWallStore, selectPreviewLayout, selectPreviewContent, selectStageMode } from '../../state/hooks';
import { testPatternName } from '../../state/commands/testPatterns';
import { Button } from '../../ui/Button';
import { Tally } from '../../ui/Tally';
import { useShell } from './ShellContext';
import { useShellView, contentName } from './useShellView';
import { MobileOnWall } from '../onwall';
import { describeLayoutChange } from '../conflict/model';
import WallPlaceholder from './WallPlaceholder';
import { EditOverlay } from '../../stage/EditOverlay';
import EditToolbar, { useArrangementEditor } from './EditToolbar';

export default function Preview() {
  const { store } = useShell();
  const { gesture, snap, setSnap, enabled } = useArrangementEditor();
  const { loading, firstRun, unreachable, lastReport, config, statuses, profileFor, tablets } = useShellView();
  const layout = useWallStore(store, selectPreviewLayout);
  const content = useWallStore(store, selectPreviewContent);
  const savedScene = useWallStore(store, state => state.content.savedScene);
  const selected = useWallStore(store, state => state.ui.selected);
  const arrangement = useWallStore(store, state => state.arrangement);
  const editing = useWallStore(store, state => state.ui.editLayout);
  const mode = useWallStore(store, selectStageMode);
  const testPattern = useWallStore(store, state => state.ui.testPattern);
  const measureStep = useWallStore(store, state => state.ui.measureStep);
  const measureId = useWallStore(store, state => state.ui.drill ?? state.ui.selected);
  const [liveExpanded, setLiveExpanded] = useState(false);
  const savedLabel = savedScene && content?.type === 'image'
    ? `${savedScene.name}, ${content.fit === 'contain' ? 'Fit' : 'Fill'}` : null;
  const change = arrangement ? describeLayoutChange(arrangement.base, arrangement.draft) : '';
  const yourLayout = !change || change === 'Layout unchanged' ? 'Your layout' : `Your layout: ${change.charAt(0).toLowerCase()}${change.slice(1)}`;
  const measureName = tablets.find(tablet => tablet.id === measureId)?.name ?? 'tablet';
  const label = measureStep ? `Measuring ${measureName}` : loading ? 'Loading the wall…' : firstRun ? 'Waiting for tablets' : unreachable ? 'Last known wall'
    : arrangement?.conflict ? 'Your layout, kept while you review'
    : editing || mode === 'arrangement-preview' ? yourLayout
      : testPattern ? `${testPatternName(testPattern)}, not on the wall yet` : mode === 'image-preview' ? savedLabel ?? contentName(content) : 'Same as the wall';
  function reportStamp(className: string) {
    return <span className={`chip chip-err ${className}`}><Clock aria-hidden="true" />
      {lastReport ? <>As of <time data-report-time dateTime={lastReport.dateTime}>{lastReport.label}</time></> : 'Last known wall'}</span>;
  }
  function selectFromStage(target: EventTarget | null) {
    if (!(target instanceof Element)) return;
    const key = target.closest('[data-device-id]')?.getAttribute('data-device-id');
    const tablet = tablets.find(tablet => tablet.id === key);
    if (tablet) store.setState(state => ({ ui: { ...state.ui, selected: tablet.id, drill: null } }));
  }
  return <section className="preview-pinned" aria-label="Preview">
    <div className="monitor-label">
      <Tally kind="preview" /><span className="t-body t-muted monitor-description">{content?.type === 'image' && 'available' in content && content.available === false ? 'Image unavailable' : label}</span>
      {unreachable ? reportStamp('monitor-stamp') : null}
      <div className="preview-tools">
        {editing ? <><Button variant="ghost" size="icon" className="sm:hidden" aria-label="Undo layout edit" aria-disabled={!enabled || !arrangement?.undo.length} onClick={() => gesture.history('undo')}><Undo2 aria-hidden="true" /></Button>
          <Button variant="ghost" size="icon" className="sm:hidden" aria-label="Redo layout edit" aria-disabled={!enabled || !arrangement?.redo.length} onClick={() => gesture.history('redo')}><Redo2 aria-hidden="true" /></Button><EditToolbar /></> : null}
        {!loading && !firstRun && !unreachable && config ? <Button variant="secondary" aria-pressed={editing}
          aria-label="Edit layout" onClick={() => store.setState(state => ({ ui: { ...state.ui, editLayout: !editing, drill: null } }))}>
          <Move aria-hidden="true" /><span className="edit-label">Edit layout</span>
        </Button> : null}
      </div>
    </div>
    <div className={`stage-well preview-stage${mode !== 'live' || testPattern ? ' is-draft' : ''}`} data-stage="preview" tabIndex={0} role="group"
      aria-label="Preview wall. Use Left and Right to select a tablet."
      onClick={event => selectFromStage(event.target)}
      onKeyDown={event => {
        if (editing || event.target !== event.currentTarget || !tablets.length || !['ArrowLeft', 'ArrowRight', 'Enter', ' '].includes(event.key)) return;
        event.preventDefault();
        const index = tablets.findIndex(tablet => tablet.id === selected);
        const next = event.key === 'ArrowRight' ? index + 1
          : event.key === 'ArrowLeft' ? (index < 0 ? tablets.length - 1 : index - 1) : Math.max(0, index);
        const tablet = tablets[(next + tablets.length) % tablets.length];
        if (tablet) store.setState(state => ({ ui: { ...state.ui, selected: tablet.id, drill: null } }));
      }}>
      {loading ? <WallPlaceholder loading />
        : layout && !firstRun ? <div className="wall-frame max-sm:[&_[role=toolbar]]:hidden max-sm:[&_.bottom-2]:hidden max-sm:[&_[data-layout-readout]]:top-auto max-sm:[&_[data-layout-readout]]:bottom-2"><WallSvg layout={layout} content={content} profileFor={profileFor}
          statuses={statuses} testPattern={testPattern} preview={mode !== 'live' || !!testPattern} selected={selected ?? undefined} interactive />
          {editing ? <EditOverlay store={store} layout={layout} profileFor={profileFor} statuses={statuses}
            selected={selected} editable={enabled} gesture={gesture} snap={snap} onSnapChange={setSnap} /> : null}</div>
        : <><WallPlaceholder /><div className="stage-empty"><TabletSmartphone aria-hidden="true" /><p className="t-heading">No tablets on the wall yet</p>
          <p className="t-body">They appear here as they join.</p></div></>}
      {unreachable ? <span className="chip chip-err stage-stamp"><Clock aria-hidden="true" />
        {lastReport ? <>As of <time data-report-time dateTime={lastReport?.dateTime}>{lastReport.label}</time></> : 'Last known wall'}</span> : null}
    </div>
    <MobileOnWall expanded={liveExpanded} onExpandedChange={setLiveExpanded} />
  </section>;
}
