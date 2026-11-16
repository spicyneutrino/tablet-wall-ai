import { useEffect, useState } from 'react';
import { ToggleGroup, ToggleGroupItem } from '../../../ui/ToggleGroup';
import { Button } from '../../../ui/Button';
import { useShell } from '../../preview/ShellContext';
import { useShellView } from '../../preview/useShellView';
import { useWallStore } from '../../../state/hooks';
import { editContent } from '../../../state/store';
import { colourOutcomeText, selectTestPattern, sendTestColour, testColours, testPatterns } from '../../../state/commands/testPatterns';
import type { ColourTarget, TestColour } from '../../../state/commands/testPatterns';
import './tests.css';

export default function Tests() {
  const { store, session } = useShell();
  const { loading, unreachable, tablets } = useShellView();
  const pattern = useWallStore(store, state => state.ui.testPattern);
  const selected = useWallStore(store, state => state.ui.selected);
  const [colour, setColour] = useState<TestColour>('red');
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState<ColourTarget['kind'] | null>(null);
  useEffect(() => () => selectTestPattern(store, null), [store]);

  const online = tablets.filter(tablet => tablet.online);
  const tablet = tablets.find(entry => entry.id === selected);
  const reason = loading ? 'Loading…' : unreachable ? 'The server can’t be reached.'
    : !online.length ? 'No tablets online' : undefined;
  const chosen = testColours.find(entry => entry.value === colour) ?? testColours[0];
  function choose(pattern: (typeof testPatterns)[number]['value']) {
    if (store.getState().content.selection) editContent(store, { type: 'discard' });
    selectTestPattern(store, pattern);
  }
  const all = reason ? { disabled: true as const, disabledReason: reason } : { disabled: false as const };
  const one = reason ? { disabled: true as const, disabledReason: reason }
    : tablet ? { disabled: false as const }
      : { disabled: true as const, disabledReason: 'Select a tablet in the list first.' };

  async function send(target: ColourTarget) {
    setPending(target.kind);
    setMessage('');
    const outcome = await sendTestColour(session, chosen.color, target);
    setPending(null);
    setMessage(colourOutcomeText(outcome, target));
  }

  return <div className="tests-source" aria-label="Test sources">
    <div className="source-strip" role="group" aria-label="Test patterns">
      {testPatterns.map(entry => <button key={entry.value} type="button" className="source-preview test-tile"
        aria-pressed={pattern === entry.value} onClick={() => choose(entry.value)}>
        <span className="thumb dark">{entry.value === 'grid' ? <svg viewBox="0 0 120 76" width="120" height="76" aria-hidden="true">
          <path d="M0 19H120M0 38H120M0 57H120M20 0V76M40 0V76M60 0V76M80 0V76M100 0V76" fill="none" stroke="currentColor" />
        </svg> : null}</span>
        <span className="t-caption test-tile-name">{entry.name}</span>
      </button>)}
    </div>
    <div className="test-colours">
      <ToggleGroup className="test-colour-group" type="single" value={colour} aria-label="Test colour"
        onValueChange={value => { if (value) setColour(value as TestColour); }}>
        {testColours.map(entry => <ToggleGroupItem key={entry.value} value={entry.value} className="test-colour"
          aria-label={entry.name} data-colour={entry.value}>
          <span className="test-swatch" style={{ background: entry.color }} aria-hidden="true" />
        </ToggleGroupItem>)}
      </ToggleGroup>
      <div className="test-colour-actions">
        <Button variant="secondary" size="sm" {...all} busy={pending === 'all'} busyLabel="Sending…"
          onClick={() => { void send({ kind: 'all' }); }}>All tablets</Button>
        <Button variant="secondary" size="sm" {...one} busy={pending === 'tablet'} busyLabel="Sending…"
          onClick={() => { if (tablet) void send({ kind: 'tablet', id: tablet.id, name: tablet.name }); }}>
          {tablet ? `This tablet: ${tablet.name}` : 'This tablet'}
        </Button>
      </div>
      {message ? <p className="t-caption test-message" role="status">{message}</p> : null}
    </div>
  </div>;
}
