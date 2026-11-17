import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { DeviceId } from '../../api/devices';
import { ACTION_RESULT, deviceCommand, deviceMessage, labelProblem, saveLabel, saveModelChoice } from '../../state/commands/devices';
import type { DeviceAction } from '../../state/commands/devices';
import { editForm, keepMine, observeForm, useTheirs as discardForm } from '../../state/store';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { Field } from '../../ui/Field';
import { Input, Select } from '../../ui/Input';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
import MeasureEntry from './MeasureEntry';

type Saving = 'name' | 'model' | DeviceAction;
type Message = { text: string; error: boolean };

type Disabled = { disabled: true; disabledReason: string } | { disabled?: never };
type Busy = { busy: true; busyLabel: string } | { busy?: never };
function disabledProps(reason: string): Disabled {
  return reason ? { disabled: true, disabledReason: reason } : {};
}
function busyProps(active: boolean, label: string): Busy {
  return active ? { busy: true, busyLabel: label } : {};
}

export default function Commands() {
  const { store, session } = useShell();
  const { tablets, config, server } = useShellView();
  const id = useWallStore(store, state => state.ui.drill ?? state.ui.selected);
  const nameForm = useWallStore(store, state => id ? state.forms[`${id}:name`] : undefined);
  const modelForm = useWallStore(store, state => id ? state.forms[`${id}:model`] : undefined);
  const [saving, setSaving] = useState<Saving | null>(null);
  const [formMessage, setFormMessage] = useState<Message | null>(null);
  const [commandMessage, setCommandMessage] = useState<Message | null>(null);
  useEffect(() => {
    if (!id) return;
    observeForm(store, id, 'name');
    observeForm(store, id, 'model');
  }, [store, id]);
  const tablet = tablets.find(tablet => tablet.id === id);
  if (!id || !tablet) return null;
  const deviceId: DeviceId = id;
  const device = server.roster[deviceId], online = device?.online === true, caps = device?.caps ?? [];
  const current = server.etagState === 'current';
  const away = server.rosterUnreachable ? 'The server can’t be reached.' : '';
  const confirm = server.uncertain ? 'The last change was not confirmed. Refresh status first.' : '';
  const wallBlock = away || (!current ? 'Refresh status before saving.' : confirm
    || (server.busy ? 'Another change is being sent. Wait for it to finish.' : ''));
  const actionBlock = away || (!online ? 'This tablet is offline. Commands need it online.'
    : !current ? 'Refresh status before sending commands.'
      : confirm || (server.busy ? 'Another change is being sent. Wait for it to finish.' : ''));
  const name = typeof nameForm?.values.name === 'string' ? nameForm.values.name
    : config?.device_labels[deviceId] ?? device?.label ?? '';
  const nameProblem = labelProblem(name);
  const nameBlock = wallBlock
    || (nameForm?.conflict ? 'The saved name changed elsewhere. Keep yours or use the current name.' : '')
    || (nameProblem ? 'Fix the name first.' : '');
  const choice = typeof modelForm?.values['tablet-model'] === 'string' ? modelForm.values['tablet-model'] : '';
  const modelBlock = wallBlock
    || (modelForm?.conflict ? 'The saved model changed elsewhere. Keep yours or use the current model.' : '')
    || (choice ? '' : 'Choose a model or Manual measurements.');
  const identifyBlock = online && !caps.includes('identify') ? 'This tablet does not report Identify support.' : '';
  const retryBlock = online && !caps.includes('render_ack') ? 'This tablet does not report image support.' : '';
  const groupProps = actionBlock ? { 'aria-disabled': true as const, 'aria-describedby': 'tablet-command-reason' } : {};
  const models = Object.entries(config?.tablet_models ?? {}).map(([key, model]) => ({ key, label: model.label }))
    .sort((left, right) => left.label.localeCompare(right.label));

  function edit(group: 'name' | 'model', values: Record<string, unknown>) {
    const key = `${deviceId}:${group}` as const;
    if (!store.getState().forms[key]) observeForm(store, deviceId, group);
    editForm(store, key, { ...store.getState().forms[key]?.values, ...values });
    setFormMessage(null);
  }
  async function submitName(event: FormEvent) {
    event.preventDefault();
    if (!nameForm || nameBlock || !nameForm.dirty) return;
    setSaving('name');
    try {
      const outcome = await saveLabel(store, session, deviceId);
      setFormMessage(outcome.kind === 'ok' ? { text: 'Name saved.', error: false } : { text: deviceMessage(outcome), error: true });
    } catch (error) {
      setFormMessage({ text: error instanceof Error ? error.message : 'The name may not be saved. Refresh status.', error: true });
    } finally { setSaving(null); }
  }
  async function submitModel() {
    if (!modelForm || modelBlock || !modelForm.dirty) return;
    setSaving('model');
    try {
      const outcome = await saveModelChoice(store, session, deviceId, choice);
      setFormMessage(outcome.kind === 'ok'
        ? { text: 'Model saved. Measured readiness is checked separately.', error: false }
        : { text: deviceMessage(outcome), error: true });
    } catch (error) {
      setFormMessage({ text: error instanceof Error ? error.message : 'The model may not be saved. Refresh status.', error: true });
    } finally { setSaving(null); }
  }
  async function run(action: DeviceAction) {
    setSaving(action);
    setCommandMessage(null);
    try {
      const outcome = await deviceCommand(session, deviceId, action);
      setCommandMessage(outcome.kind === 'ok' ? { text: ACTION_RESULT[action], error: false } : { text: deviceMessage(outcome), error: true });
    } catch (error) {
      setCommandMessage({ text: error instanceof Error ? error.message : 'The command may not have arrived. Refresh status.', error: true });
    } finally { setSaving(null); }
  }
  function keep(group: 'name' | 'model') {
    const form = store.getState().forms[`${deviceId}:${group}`];
    if (!form || !server.etag) return;
    keepMine(store, { kind: 'form', key: `${deviceId}:${group}` }, { version: form.version, etag: server.etag });
  }

  return <div className="tablet-commands">
    <div className="tablet-command-bar">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Tablet commands">
        <MeasureEntry />
        <Button variant="secondary" {...groupProps} {...disabledProps(identifyBlock)} {...busyProps(saving === 'identify', 'Identify')}
          onClick={() => void run('identify')}>Identify</Button>
        <Button variant="secondary" {...groupProps} {...disabledProps(retryBlock)} {...busyProps(saving === 'retry', 'Retry image')}
          onClick={() => void run('retry')}>Retry image</Button>
        <Button variant="secondary" {...groupProps} {...busyProps(saving === 'reconnect', 'Reconnect')}
          onClick={() => void run('reconnect')}>Reconnect</Button>
      </div>
      {actionBlock ? <p id="tablet-command-reason" className="t-caption">{actionBlock}</p> : null}
    </div>
    <p className={`t-caption${commandMessage?.error ? ' text-err' : ''}`} role="status" data-command-result>
      {commandMessage?.text ?? ''}</p>
    <form onSubmit={event => void submitName(event)}>
      <Field label="Name" hint="Leave empty to use the generated name." error={nameProblem ?? undefined}>
        {props => <div className="flex gap-2">
          <Input {...props} name="tablet-name" value={name} placeholder={tablet.name}
            autoComplete="off" spellCheck={false}
            onChange={event => edit('name', { name: event.target.value })} />
          <Button type="submit" variant="secondary" {...disabledProps(nameBlock)} {...busyProps(saving === 'name', 'Saving…')}>Save</Button>
        </div>}
      </Field>
      {nameForm?.conflict ? <div className="flex flex-wrap gap-2">
        <Button variant="ghost" size="sm" onClick={() => keep('name')}>Keep my name</Button>
        <Button variant="ghost" size="sm" onClick={() => discardForm(store, { kind: 'form', key: `${deviceId}:name` })}>Use the current name</Button>
      </div> : null}
    </form>
    <div className="tablet-model-field">
      <Field label="Model">
        {props => <Select {...props} value={choice} onChange={event => edit('model', { 'tablet-model': event.target.value })}>
          <option value="">Choose a model or manual measurements</option>
          <option value="manual">Manual measurements</option>
          {models.map(model => <option key={model.key} value={model.key}>{model.label}</option>)}
        </Select>}
      </Field>
      <Button variant="secondary" className="justify-self-start" {...disabledProps(modelBlock)}
        {...busyProps(saving === 'model', 'Saving…')} onClick={() => void submitModel()}>Save model</Button>
      {modelForm?.conflict ? <div className="flex flex-wrap gap-2">
        <Button variant="ghost" size="sm" onClick={() => keep('model')}>Keep my model</Button>
        <Button variant="ghost" size="sm" onClick={() => discardForm(store, { kind: 'form', key: `${deviceId}:model` })}>Use the current model</Button>
      </div> : null}
    </div>
    <p className={`t-caption${formMessage?.error ? ' text-err' : ''}`} role="status" data-form-result>
      {formMessage?.text ?? ''}</p>
  </div>;
}
