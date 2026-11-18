import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import Facts from './Facts';
import Commands from './Commands';
import Lifecycle from './Lifecycle';
import PlacementFields from './PlacementFields';

export default function Tablet() {
  const { store } = useShell();
  const { tablets } = useShellView();
  const ui = useWallStore(store, state => state.ui);
  const tablet = tablets.find(tablet => tablet.id === (ui.drill ?? ui.selected));
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (ui.drill) title.current?.focus({ preventScroll: true }); }, [ui.drill]);
  if (!tablet) return null;
  return <section className="tablet-detail" aria-labelledby="tablet-title">
    {ui.drill ? <Button variant="ghost" className="justify-self-start" onClick={() => {
      store.setState(state => ({ ui: { ...state.ui, drill: null, selected: null } }));
      document.querySelector<HTMLButtonElement>('#tablet-health .row[aria-current="true"]')?.focus({ preventScroll: true });
    }}><ChevronLeft aria-hidden="true" />All tablets</Button> : null}
    <div className="detail-heading"><span className="num is-current">{tablet.number ?? '?'}</span>
      <div><h2 ref={title} tabIndex={-1} id="tablet-title" className="t-title">{tablet.name}</h2><p className="t-caption">{tablet.model}</p></div></div>
    {ui.editLayout ? null : <><Facts /><Commands key={tablet.id} /></>}
    {ui.editLayout ? <PlacementFields /> : null}
    {!ui.editLayout && !ui.drill ? <Button variant="ghost" className="justify-self-start" onClick={() => store.setState(state => ({ ui: { ...state.ui, drill: tablet.id } }))}>
      Tablet details<ChevronRight aria-hidden="true" /></Button> : null}
    {ui.editLayout ? null : <Lifecycle />}
  </section>;
}
