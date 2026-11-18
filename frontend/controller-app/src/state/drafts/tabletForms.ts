import type { Config } from '../../api/config';
import type { DeviceId } from '../../api/devices';
import type { ConfigEtag } from '../../api/etag';

export type FormGroup = 'name' | 'model' | 'profile' | 'calibration';
export type FormKey = `${DeviceId}:${FormGroup}`;
export type FormValues = Record<string, unknown>;
export type TabletForm = { id: DeviceId; group: FormGroup; baseline: FormValues; values: FormValues;
  baseEtag: ConfigEtag | null; version: number; dirty: boolean; conflict: boolean };
export const formKey = (id: DeviceId, group: FormGroup): FormKey => `${id}:${group}`;
const same = (a: FormValues, b: FormValues) => JSON.stringify(a) === JSON.stringify(b);
export type FormEvent =
  | { type: 'observe'; values: FormValues; etag: ConfigEtag | null }
  | { type: 'edit'; values: FormValues; etag: ConfigEtag | null }
  | { type: 'saved' | 'review'; values: FormValues; etag: ConfigEtag; version: number }
  | { type: 'discard'; values: FormValues; etag: ConfigEtag | null };
export function createForm(id: DeviceId, group: FormGroup, values: FormValues, etag: ConfigEtag | null): TabletForm {
  return { id, group, baseline: structuredClone(values), values: structuredClone(values), baseEtag: etag,
    version: 0, dirty: false, conflict: false };
}
export function tabletFormReducer(form: TabletForm, event: FormEvent): TabletForm {
  switch (event.type) {
    case 'observe':
      return form.dirty ? { ...form, conflict: !same(event.values, form.baseline) }
        : { ...createForm(form.id, form.group, event.values, event.etag), version: form.version };
    case 'edit':
      return same(form.values, event.values) ? form : { ...form, values: structuredClone(event.values),
        baseEtag: form.dirty ? form.baseEtag : event.etag, version: form.version + 1,
        dirty: !same(event.values, form.baseline) };
    case 'saved':
      return { ...form, baseline: structuredClone(event.values), baseEtag: event.etag, conflict: false,
        values: structuredClone(form.version === event.version ? event.values : form.values),
        dirty: form.version !== event.version && !same(form.values, event.values) };
    case 'review': {
      if (form.version !== event.version) return form;
      const values = { ...form.values, ...(Object.hasOwn(event.values, '_revision') ? { _revision: event.values._revision } : {}) };
      return { ...form, baseline: structuredClone(event.values), values, baseEtag: event.etag,
        conflict: false, version: form.version + 1, dirty: !same(values, event.values) };
    }
    case 'discard':
      return { ...createForm(form.id, form.group, event.values, event.etag), version: form.version + 1 };
  }
}
export function formBaseline(config: Config, id: DeviceId, group: FormGroup): FormValues {
  switch (group) {
    case 'name': return { name: config.device_labels[id] || config.runtime.devices[id]?.label || '' };
    case 'model': {
      const assignment = config.tablet_assignments[id];
      return { 'tablet-model': assignment?.mode === 'explicit' ? assignment.model_id : assignment?.mode === 'manual' ? 'manual' : '' };
    }
    case 'profile':
    case 'calibration': {
      const records = group === 'profile' ? config.displays : config.calibrations;
      const latest = records.filter(record => record.device_id === id).sort((a, b) => b.revision - a.revision)[0];
      return latest ? { ...latest, _revision: latest.revision } : { _revision: 0 };
    }
  }
}

export function formsDirty(forms: Partial<Record<FormKey, TabletForm>>, id?: DeviceId, group?: FormGroup): boolean {
  return Object.values(forms).some(form => form?.dirty && (id === undefined || form.id === id)
    && (group === undefined || form.group === group));
}
