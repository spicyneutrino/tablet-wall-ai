import { Check, ChevronLeft } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { DeviceId } from '../../api/devices';
import { RulerCheckSchema } from '../../api/measure';
import { OperatorConfigSchema } from '../../api/readiness';
import { rulerCheckBodies, rulerUrl } from '../../domain/calibration';
import { useWallStore } from '../../state/hooks';
import { editForm, observeForm, useTheirs as discardForm } from '../../state/store';
import { checkRuler, outcomeMessage, saveMeasurements } from '../../state/commands/measure';
import { Button } from '../../ui/Button';
import { Field } from '../../ui/Field';
import { Select } from '../../ui/Input';
import { Tally } from '../../ui/Tally';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
import { useAppliedContentName } from '../onwall';
import { calibrationBody, latestProfile, liveViewport, measurementValues, modelChoice, payloads, profileBody, stepNames, steps } from './model';
import type { Values } from './model';
import MeasureField from './MeasureField';
import RulerStep from './RulerStep';
import type { RulerState } from './RulerStep';
import AdvancedFields from './AdvancedFields';
import './measure.css';

export default function Measure() {
  const { store } = useShell();
  const id = useWallStore(store, state => state.ui.drill ?? state.ui.selected);
  const step = useWallStore(store, state => state.ui.measureStep);
  useEffect(() => {
    if (!id || !store.getState().ui.measureStep) return;
    for (const group of ['model', 'profile', 'calibration'] as const) observeForm(store, id, group);
    store.setState(state => ({ ui: { ...state.ui, measureStep: 'model' } }));
  }, [id, store]);
  return id && step ? <MeasureScreen key={id} id={id} /> : null;
}
function MeasureScreen({ id }: { id: DeviceId }) {
  const { store, session } = useShell();
  const state = useWallStore(store, state => state);
  const { tablets } = useShellView();
  const config = state.server.config;
  const values = config ? measurementValues(state, id) : {};
  const step = state.ui.measureStep;
  const index = steps.findIndex(item => item === step);
  const tablet = tablets.find(tablet => tablet.id === id);
  const name = tablet?.name ?? 'tablet';
  const wallName = useAppliedContentName(config?.scene.content ?? null);
  const choice = modelChoice(state, id);
  const model = config?.tablet_models[choice];
  const viewport = liveViewport(state, id);
  const [errors, setErrors] = useState<Values>({});
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [edges, setEdges] = useState(() => values.profileBezelLeft !== values.profileBezelRight || values.profileBezelTop !== values.profileBezelBottom);
  const [review, setReview] = useState<RulerState>({ kind: 'idle' });
  const [address, setAddress] = useState<{ loading: boolean; url: string | null }>({ loading: true, url: null });
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [step]);
  useEffect(() => {
    let active = true;
    void session.request('GET', '/operator-config', undefined, { parse: OperatorConfigSchema }).then(outcome => {
      if (active) setAddress({ loading: false, url: outcome.kind === 'ok' ? rulerUrl(outcome.value.tablet_origin) : null });
    });
    return () => { active = false; };
  }, [session]);
  const checkKey = JSON.stringify({ id, viewport,
    values: Object.entries(values).filter(([key]) => key !== 'calProfileRevision'), model: choice });
  const currentKey = useRef(checkKey);
  useEffect(() => { currentKey.current = checkKey; }, [checkKey]);
  const stale = review.kind === 'stale' || review.kind !== 'idle' && review.key !== checkKey;
  const rulerEntered = !!values.rulerX || !!values.rulerY || values.calMethod === 'ruler-measured' || review.kind !== 'idle';
  const rulerReady = !rulerEntered || !stale && review.kind === 'review' && !!review.choice;
  useEffect(() => store.subscribe((current, previous) => {
    if (JSON.stringify(liveViewport(current, id)) !== JSON.stringify(liveViewport(previous, id))) {
      setReview(review => review.kind === 'idle' ? review : { kind: 'stale', key: review.key });
    }
  }), [id, store]);
  function change(key: string, value: string) {
    setReview(review => review.kind === 'idle' ? review : { kind: 'stale', key: review.key });
    const group = key.startsWith('profile') ? 'profile' : 'calibration';
    const patch: Values = { [key]: value };
    if (!edges && key === 'profileBezelLeft') patch.profileBezelRight = value;
    if (!edges && key === 'profileBezelTop') patch.profileBezelBottom = value;
    editForm(store, `${id}:${group}`, { ...store.getState().forms[`${id}:${group}`]?.values,
      ...Object.fromEntries(Object.entries(measurementValues(store.getState(), id)).filter(([key]) => group === 'profile' ? key.startsWith('profile') : !key.startsWith('profile'))), ...patch });
    setErrors(old => Object.fromEntries(Object.entries(old).filter(([name]) => !(name in patch))));
    setMessage('');
  }
  function move(next: number) {
    setErrors({}); setMessage('');
    store.setState(state => ({ ui: { ...state.ui, measureStep: steps[next] ?? 'model' } }));
  }
  function close(discard = false) {
    if (discard) for (const group of ['model', 'profile', 'calibration'] as const) discardForm(store, { kind: 'form', key: `${id}:${group}` });
    store.setState(state => ({ ui: { ...state.ui, measureStep: null } }));
    requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('.tablet-detail .btn-primary')?.focus({ preventScroll: true }));
  }
  function invalid(error: unknown, fields: Values = {}) {
    const text = error instanceof Error ? error.message : 'Check the entered measurements.';
    setErrors(fields); setMessage(text);
    const first = Object.keys(fields)[0];
    requestAnimationFrame(() => {
      const input = document.getElementById(`measure-${first}`);
      const details = input?.closest('details');
      if (details) details.open = true;
      input?.focus();
    });
  }
  function validateProfile() {
    const fields: Values = {};
    let invalidField = '';
    try { payloads(values, (key, invalid) => { if (invalid) invalidField = key; }).buildProfileBody(); return true; }
    catch (error) {
      if (invalidField) fields[invalidField] = error instanceof Error ? error.message : 'Enter a valid measurement.';
      invalid(error, fields); return false;
    }
  }
  function next() {
    if (index === 0 && !choice) { setErrors({ model: 'Choose a confirmed model or manual measurements.' }); return; }
    if (index === 1) {
      if (!validateProfile()) return;
      if (viewport && !state.forms[`${id}:calibration`]?.dirty) {
        const quarter = Number(values.calQuarterTurn) % 2;
        change('calMmCssX', String(Number(quarter ? values.profileActiveHeight : values.profileActiveWidth) / viewport.width));
        change('calMmCssY', String(Number(quarter ? values.profileActiveWidth : values.profileActiveHeight) / viewport.height));
      }
    }
    if (index === 2 && !rulerReady) { setMessage('Check the current ruler measurements and choose which values to use, or Skip the optional check.'); return; }
    move(index + 1);
  }
  async function check() {
    if (!config) return;
    setErrors({}); setMessage('');
    try {
      const profile = latestProfile(config, id);
      const bodies = rulerCheckBodies(id, profile?.revision ?? 0, Number(values.calQuarterTurn), viewport, {
        x: { mm: values.rulerX ?? '', px: values.rulerSpanX ?? '', error: values.rulerErrorX ?? '' },
        y: { mm: values.rulerY ?? '', px: values.rulerSpanY ?? '', error: values.rulerErrorY ?? '' },
      }).map(body => RulerCheckSchema.parse(body));
      setReview({ kind: 'checking', key: checkKey });
      const outcomes = await checkRuler(session, bodies, state.server.etag);
      if (currentKey.current !== checkKey) return;
      const failed = outcomes.find(outcome => outcome.kind !== 'ok');
      if (failed) throw new Error(outcomeMessage(failed));
      setReview(current => current.kind === 'checking' && current.key === checkKey
        ? { kind: 'review', key: checkKey, results: outcomes.flatMap(outcome => outcome.kind === 'ok' ? [outcome.value] : []), choice: null } : current);
    } catch (error) {
      setReview({ kind: 'idle' });
      const invalidFields = Object.fromEntries(['rulerX', 'rulerY', 'rulerErrorX', 'rulerErrorY', 'rulerSpanX', 'rulerSpanY']
        .filter(key => !values[key]?.trim() || !Number.isFinite(Number(values[key])) || Number(values[key]) < 0
          || !key.includes('Error') && Number(values[key]) === 0).map(key => [key, 'Enter a valid ruler measurement.']));
      invalid(error, invalidFields);
    }
  }
  async function save() {
    if (busy || !config || !validateProfile()) return;
    if (!rulerReady) { setMessage('The ruler review is stale or incomplete. Return to Ruler check and check again.'); return; }
    try {
      const prepared = { ...values };
      if (review.kind === 'review' && review.choice === 'use_ruler') {
        prepared.calMmCssX = String(review.results.find(result => result.axis === 'x')?.derived.mm_per_css);
        prepared.calMmCssY = String(review.results.find(result => result.axis === 'y')?.derived.mm_per_css);
        prepared.calUncertainty = String(Math.max(...review.results.map(result => result.extrapolated_uncertainty.measured_mm)));
        prepared.calMethod = 'ruler-measured';
        if (viewport) Object.assign(prepared, { calViewportWidth: String(viewport.width), calViewportHeight: String(viewport.height),
          calDpr: String(viewport.dpr), calOrientation: String(viewport.orientation), calMode: viewport.mode });
      }
      const profile = profileBody(prepared);
      let invalidField = '';
      try { payloads(prepared, (key, invalid) => { if (invalid) invalidField = key; }).buildCalibrationBody(); }
      catch (error) { invalid(error, invalidField ? { [invalidField]: error instanceof Error ? error.message : 'Enter a valid calibration.' } : {}); return; }
      const calibration = calibrationBody(prepared);
      const versions = (['model', 'profile', 'calibration'] as const).map(group => state.forms[`${id}:${group}`]?.version);
      const viewportKey = JSON.stringify(viewport);
      setBusy(true); setMessage('');
      const result = await saveMeasurements(store, session, { id, profile, calibration,
        assignment: choice === 'manual' ? { mode: 'manual' } : { mode: 'explicit', model_id: choice },
        isCurrent: () => {
          const current = store.getState();
          return (current.ui.drill ?? current.ui.selected) === id && JSON.stringify(liveViewport(current, id)) === viewportKey
            && (['model', 'profile', 'calibration'] as const).every((group, i) => current.forms[`${id}:${group}`]?.version === versions[i]);
        } });
      if (result) setMessage(result); else close();
    } catch (error) { invalid(error); }
    finally { setBusy(false); }
  }
  if (!config) return <p role="status">Loading measurements… Wait for wall status, then try again.</p>;
  const field = (key: string, label: string) => <MeasureField name={key} label={label} value={values[key] ?? ''} onChange={change} error={errors[key]} />;
  const summaries = [model?.label ?? (choice === 'manual' ? 'Manual' : ''), `${values.profileActiveWidth} × ${values.profileActiveHeight} mm`,
    review.kind === 'review' && review.choice === 'use_ruler' ? 'Ruler values' : 'Model values'];
  return <section className="measure-stepper" aria-labelledby="measure-title">
    <div className="monitor-label"><Tally kind="live" /><span className="t-caption monitor-description">{wallName} · Measuring blanks only {name}</span></div>
    <Button variant="ghost" className="measure-back" onClick={() => close()} aria-disabled={busy}><ChevronLeft aria-hidden="true" />{name}</Button>
    <div><h2 className="t-title" id="measure-title">Measure {name}</h2><p className="t-caption">{model?.label ?? (choice === 'manual' ? 'Manual measurements' : tablet?.model)}. Nothing is saved until the last step.</p></div>
    <fieldset disabled={busy} className="measure-controls"><ol className="measure-steps">
      {steps.map((item, i) => <li key={item} aria-current={step === item ? 'step' : undefined} data-done={i < index || undefined}>
        <div className="measure-step-head"><span className="step-dot">{i < index ? <><Check aria-hidden="true" /><span className="sr-only">Done</span></> : i + 1}</span>
          <h3 className="t-label" ref={step === item ? heading : undefined} tabIndex={step === item ? -1 : undefined}>{stepNames[i]}</h3>
          {i < index ? <span className="t-caption measure-summary">{summaries[i]}</span> : i === 2 ? <span className="tag">Optional</span> : null}</div>
        {step === item ? <div className="measure-step-body">
          {item === 'model' ? <><Field id="measure-model" label="Which model is it?" error={errors.model}>{control => <Select {...control} name="model" value={choice} onChange={event => {
            setReview(current => current.kind === 'idle' ? current : { kind: 'stale', key: current.key });
            const key = event.target.value;
            editForm(store, `${id}:model`, { 'tablet-model': key });
            const chosen = config.tablet_models[key];
            if (chosen) {
              const previous = store.getState().forms[`${id}:profile`]?.values;
              editForm(store, `${id}:profile`, { ...previous, profileActiveWidth: String(chosen.active_width_mm), profileActiveHeight: String(chosen.active_height_mm),
                profileBezelLeft: String(chosen.bezels.left), profileBezelRight: String(chosen.bezels.right), profileBezelTop: String(chosen.bezels.top), profileBezelBottom: String(chosen.bezels.bottom),
                profileLabel: chosen.label, profileProvenance: 'model' });
            }
            setErrors({}); setMessage('');
          }}><option value="">Choose a confirmed model</option>{Object.entries(config.tablet_models).map(([key, model]) => <option key={key} value={key}>{model.label}</option>)}<option value="manual">Other, enter sizes</option></Select>}</Field>
            <p className="t-body t-muted">The browser can suggest a model. Confirm the hardware; its screen size and bezels can be corrected next.</p></>
            : item === 'profile' ? <><p className="t-body t-muted">{model ? `From the ${model.label} model. Change them only if a ruler says otherwise.` : 'Measure the visible screen and the distance from its edges to the case.'}</p>
              <fieldset className="measure-grid"><legend className="t-label">Visible screen</legend>{field('profileActiveWidth', 'Width')}{field('profileActiveHeight', 'Height')}</fieldset>
              <fieldset className="measure-grid"><legend className="t-label">Bezel, screen edge to case edge</legend>
                {field('profileBezelLeft', edges ? 'Left' : 'Sides')}{field('profileBezelTop', edges ? 'Top' : 'Top and bottom')}
                {edges ? <>{field('profileBezelRight', 'Right')}{field('profileBezelBottom', 'Bottom')}</> : null}</fieldset>
              <Button variant="ghost" size="sm" className="justify-self-start" aria-expanded={edges} onClick={() => {
                if (edges) { change('profileBezelRight', values.profileBezelLeft ?? '0'); change('profileBezelBottom', values.profileBezelTop ?? '0'); }
                setEdges(!edges);
              }}>{edges ? 'Use paired edges' : 'Set each edge separately'}</Button></>
            : item === 'ruler' ? <RulerStep values={values} change={change} errors={errors} url={address.url} addressLoading={address.loading}
              review={review} stale={stale} check={() => void check()} canCheck={!!viewport && !!latestProfile(config, id)}
              decide={choice => setReview(current => current.kind === 'review' ? { ...current, choice } : current)} />
            : <><dl className="measure-review t-body"><dt>Screen</dt><dd>{summaries[1]}</dd><dt>Bezels</dt><dd>{values.profileBezelLeft} / {values.profileBezelTop} / {values.profileBezelRight} / {values.profileBezelBottom} mm <span className="t-caption">left / top / right / bottom</span></dd>
              <dt>Checked by</dt><dd>{review.kind === 'review' && review.choice === 'use_ruler' ? 'Ruler, each axis measured' : 'Supplied measurements'}</dd></dl>
              <p className="t-body t-muted">Saving adds profile and calibration revisions. Existing layout pins stay unchanged. Apply a layout with the new revisions to change the wall.</p>
              <AdvancedFields values={values} errors={errors} change={change} /></>}
        </div> : null}
      </li>)}
    </ol></fieldset>
    {message ? <p className="measure-error t-body" role="alert">{message}</p> : null}
    <div className="measure-footer">
      <Button variant="ghost" onClick={() => index === 0 ? close(true) : move(index - 1)} aria-disabled={busy}>{index === 0 ? 'Cancel' : <><ChevronLeft aria-hidden="true" />Back</>}</Button>
      {index === 2 ? <Button variant="ghost" className="measure-next" onClick={() => {
        change('rulerX', ''); change('rulerY', ''); change('calMethod', model ? 'model-estimate' : 'manual'); setReview({ kind: 'idle' }); move(3);
      }}>Skip</Button> : null}
      {index === 3 ? <Button className="measure-next" {...(busy ? { busy: true, busyLabel: 'Saving…' } : { busy: false })} onClick={() => void save()}><Check aria-hidden="true" />Save measurements</Button>
        : <Button className={index === 2 ? '' : 'measure-next'} {...(review.kind === 'checking' ? { busy: true, busyLabel: 'Checking…' } : { busy: false })} onClick={next}>
          {['Next: size and bezels', 'Next: ruler check', 'Next: review'][index]}</Button>}
    </div>
  </section>;
}
