import { ChevronRight, Ruler } from 'lucide-react';
import type { RulerCheckResult } from '../../api/measure';
import { Input } from '../../ui/Input';
import { Button } from '../../ui/Button';
import MeasureField from './MeasureField';
import type { Values } from './model';

export type RulerState = { kind: 'idle' } | { kind: 'checking'; key: string } | { kind: 'stale'; key: string }
  | { kind: 'review'; key: string; results: RulerCheckResult[]; choice: 'keep_supplied' | 'use_ruler' | null };
type Props = { name: string; values: Values; change: (key: string, value: string) => void; errors: Values;
  url: string | null; addressLoading: boolean; review: RulerState; stale: boolean; check: () => void;
  decide: (choice: 'keep_supplied' | 'use_ruler') => void; canCheck: boolean };
const mm = (value: number) => value.toFixed(1);

function rulerGives(results: RulerCheckResult[]) {
  const width = results.find(result => result.axis === 'x')?.implied_dimensions_mm.width;
  const height = results.find(result => result.axis === 'y')?.implied_dimensions_mm.height;
  return width !== undefined && height !== undefined ? `Ruler gives ${mm(width)} × ${mm(height)} mm` : 'Ruler result';
}

function withinModel(results: RulerCheckResult[]) {
  const gaps = results.flatMap(({ comparison }) => comparison.supplied_mm !== null && comparison.implied_mm !== null
    ? [Math.abs(comparison.implied_mm - comparison.supplied_mm)] : []);
  if (!gaps.length || results.some(result => result.decision.required)) return null;
  return <p className="t-body">Within {mm(Math.max(...gaps))} mm of the model. Either choice lines up across seams.</p>;
}

export default function RulerStep({ name, values, change, errors, url, addressLoading, review, stale, check, decide, canCheck }: Props) {
  const checked = review.kind === 'review' && !stale;
  const address = <>{url ? <a className="measure-ruler-link t-caption" href={url} target="_blank" rel="noreferrer">{url}</a>
    : <p className="t-caption">{addressLoading ? 'Loading the tablet ruler address…' : 'Set the server’s tablet origin to a tablet-reachable HTTP(S) address.'}</p>}</>;
  const spanLabel = values.rulerSpanX && values.rulerSpanX === values.rulerSpanY ? `${values.rulerSpanX} px each` : 'CSS px';
  const field = (name: string, label: string, unit?: string) => <MeasureField name={name} label={label}
    value={values[name] ?? ''} onChange={change} error={errors[name]} unit={unit} />;
  return <>
    {checked ? <details><summary><ChevronRight className="chev" aria-hidden="true" />Ruler address and instructions</summary>{address}<p className="t-caption">Measure the full labelled lines at 100% zoom. Browser insets may reduce the usable screen.</p></details>
      : <><p className="t-body">{name} now shows two lines, A and B. Hold a ruler against each and enter what it reads.</p>{address}
        <p className="t-caption">Measure the full lines at 100% zoom.</p></>}
    <div className="measure-grid">
      {field('rulerX', 'Line A')}{field('rulerY', 'Line B')}
      <div className="measure-wide"><MeasureField name="rulerErrorX" label="How sure, either way" unit="± mm" value={values.rulerErrorX ?? ''}
        error={errors.rulerErrorX} onChange={(key, value) => { change(key, value); change('rulerErrorY', value); }} /></div>
    </div>
    <details><summary><ChevronRight className="chev" aria-hidden="true" />Line lengths on screen ({spanLabel})</summary><div className="measure-grid">
      {field('rulerSpanX', 'Line A span', 'px')}{field('rulerSpanY', 'Line B span', 'px')}
      {field('rulerErrorY', 'Line B error override', '± mm')}
    </div></details>
    {!checked ? <Button variant="secondary" {...(review.kind === 'checking' ? { busy: true, busyLabel: 'Checking…' } : { busy: false })} onClick={check}
      {...(!canCheck ? { disabled: true, disabledReason: 'Save an initial profile first, then reopen Measure with this tablet online at 100% zoom.' } : { disabled: false })}>Check result</Button> : null}
    {stale ? <p className="measure-warning t-body" role="status">The tablet, viewport or inputs changed. Check the current ruler measurements again before saving.</p>
      : review.kind === 'review' ? <>
        <div className="note note-info" role="status"><div className="measure-check-heading"><p className="note-title"><Ruler aria-hidden="true" />{rulerGives(review.results)}</p><Button variant="ghost" size="sm" onClick={check}>Check result</Button></div>
          {withinModel(review.results) ?? review.results.map(result => <p className="t-caption" key={result.axis}>{result.axis === 'x' ? 'A' : 'B'}: {result.derived.mm_per_css.toFixed(4)} mm/px, ±{result.extrapolated_uncertainty.measured_mm.toFixed(2)} mm. {result.decision.required ? 'Review disagreement.' : 'Within tolerance.'}</p>)}
        </div>
        <fieldset className="measure-choices"><legend className="sr-only">Which values to save</legend>
          <label className="radio-row"><Input className="measure-radio" type="radio" name="ruler-choice" checked={review.choice === 'keep_supplied'}
            onChange={() => decide('keep_supplied')} /><span>Keep the model values</span></label>
          <label className="radio-row"><Input className="measure-radio" type="radio" name="ruler-choice" checked={review.choice === 'use_ruler'}
            onChange={() => decide('use_ruler')} /><span>Use the ruler values</span></label>
        </fieldset>
      </> : null}
  </>;
}
