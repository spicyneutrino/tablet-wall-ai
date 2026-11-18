import { useState } from 'react';
import { SceneSchema } from '../api/scene';
import { WallSvg } from '../stage/WallSvg';
import type { WallStatus } from '../stage/WallSvg';
import { walls } from '../../e2e/fixtures/walls';
import EditableStageFixture from './EditableStageFixture';

export default function StageFixture() {
  const query = new URLSearchParams(location.search);
  const fixture = walls.find((wall) => wall.name === query.get('wall')) ?? walls[0]!;
  const [selected, setSelected] = useState<string>();
  const [notice, setNotice] = useState(false);
  const [mode, setMode] = useState('Preview');
  const [status, setStatus] = useState('displayed');
  const [fit, setFit] = useState(query.get('fit') === 'contain' ? 'contain' : 'cover');
  const content = query.get('image') ? SceneSchema.parse({ type: 'image', asset: `sha256:${'0'.repeat(64)}`,
    url: query.get('image'), intrinsicWidth: 1600, intrinsicHeight: 900, fit, background: '#102030' }) : null;
  const ids = Object.keys(fixture.layout.kind === 'physical' ? fixture.layout.slots ?? {} : fixture.layout.placements ?? {});
  const statuses = Object.fromEntries(ids.map((id, index): [string, WallStatus] =>
    [id, { status, text: status === 'offline' ? 'Offline' : 'Displayed', label: `Tablet ${index + 1}`, number: index + 1 }]));

  if (query.has('edit')) return <EditableStageFixture fixture={fixture} content={content} />;

  return (
    <main aria-label="Stage fixture" style={{ padding: '1rem', display: 'grid', gap: '1rem', gridTemplateColumns: 'minmax(0, 1fr)' }}>
      <h1 className="t-title">{fixture.name}</h1>
      <nav aria-label="Fixture controls" style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
        <label>Wall <select value={fixture.name} onChange={(event) => {
          query.set('wall', event.target.value); location.search = query.toString();
        }}>{walls.map((wall) => <option key={wall.name}>{wall.name}</option>)}</select></label>
        <label>Fit <select value={fit} onChange={(event) => setFit(event.target.value)}>
          <option value="cover">Fill</option><option value="contain">Fit</option>
        </select></label>
        <label>Status <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="displayed">Displayed</option><option value="offline">Offline</option>
        </select></label>
        <button onClick={() => setSelected(selected ? undefined : ids[0])}>Toggle selection</button>
        <button onClick={() => setNotice(!notice)}>Toggle alert</button>
        <button onClick={() => setMode(mode === 'Preview' ? 'On wall' : 'Preview')}>{mode}</button>
        <button onClick={() => { query.set('edit', ''); location.search = query.toString(); }}>Edit fixture</button>
      </nav>
      <div data-stage="preview" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)',
        aspectRatio: '16 / 9', inlineSize: '100%', maxBlockSize: '70dvh', minBlockSize: 0 }}>
        <WallSvg layout={fixture.layout} profileFor={() => fixture.profile} content={content}
          statuses={statuses} selected={selected} interactive={false} />
      </div>
      {notice ? <p role="alert">The wall needs attention.</p> : null}
    </main>
  );
}
