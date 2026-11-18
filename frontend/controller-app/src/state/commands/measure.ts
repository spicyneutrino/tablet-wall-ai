import { TabletAssignmentResponseSchema } from '../../api/config';
import type { DeviceId, TabletAssignmentCommand } from '../../api/devices';
import type { ConfigEtag } from '../../api/etag';
import { CalibrationResponseSchema, DisplayResponseSchema, RulerCheckResultSchema } from '../../api/measure';
import type { CalibrationCommand, ProfileCommand, RulerCheck } from '../../api/measure';
import { paths } from '../../api/paths';
import type { Session } from '../../session/session';
import type { CommandOutcome } from '../../session/outcome';
import type { WallStoreApi } from '../store';
import { run } from './run';

export function outcomeMessage(outcome: CommandOutcome<unknown>) {
  switch (outcome.kind) {
    case 'ok': return '';
    case 'rejected': return outcome.status === 409
      ? `${outcome.message} Return to Ruler check, restore the tablet viewport at 100% zoom, and check again.` : outcome.message;
    case 'conflict': return 'Saved measurements changed. Close Measure, review the current wall, and reopen before saving.';
    case 'uncertain': return outcome.message;
    case 'precondition-missing': return 'Refresh wall status before saving measurements.';
    case 'refused-locally': return outcome.reason === 'uncertain' ? 'Refresh wall status to confirm the previous save before retrying.'
      : outcome.reason === 'busy' ? 'Wait for the current command to finish.' : 'Refresh wall status before saving measurements.';
  }
}
export function checkRuler(session: Session, bodies: RulerCheck[], etag: ConfigEtag | null) {
  return Promise.all(bodies.map(body => session.request('POST', paths.calibrationCheck, body,
    { ifMatch: etag ?? '', parse: RulerCheckResultSchema })));
}

export async function saveMeasurements(store: WallStoreApi, session: Session, input: {
  id: DeviceId; assignment: TabletAssignmentCommand; profile: ProfileCommand; calibration: CalibrationCommand;
  isCurrent: () => boolean;
}): Promise<string> {
  const { id } = input;
  const groups = ['model', 'profile', 'calibration'] as const;
  const before = store.getState();
  const forms = groups.map(group => before.forms[`${id}:${group}`]);
  if (forms.some(form => !form || form.conflict)) return 'Saved measurements changed. Close Measure and review the current values before saving.';
  if (forms.some(form => form?.dirty && form.baseEtag !== before.server.etag)) return 'The wall changed. Close Measure and review the current values before saving.';
  if (!input.isCurrent()) return 'The tablet or measurements changed. Return to Ruler check and check again.';
  let guard = before.server.etag;
  const versions = forms.map(form => form?.version);
  async function advance(etag: ConfigEtag) {
    await session.refresh();
    if (store.getState().server.etag !== etag) throw new Error('The wall changed during saving. Review current measurements before retrying.');
    guard = etag;
    store.setState(state => ({ forms: Object.fromEntries(Object.entries(state.forms).map(([key, form]) =>
      [key, form?.id === id && form.group !== 'name' ? { ...form, baseEtag: etag, conflict: false } : form])) }));
  }
  try {
    if (forms[0]?.dirty) {
      const assigned = await run(store, { kind: 'form', key: `${id}:model` }, () =>
        session.request('PUT', paths.tabletAssignment(id), input.assignment, { ifMatch: guard ?? '', parse: TabletAssignmentResponseSchema }));
      if (assigned.kind !== 'ok') return outcomeMessage(assigned);
      await advance(assigned.value.etag);
    }
    if (!input.isCurrent()) return 'The tablet or measurements changed. Return to Ruler check and check again.';
    const profile = await run(store, { kind: 'form', key: `${id}:profile` }, () =>
      session.request('PUT', paths.display(id), input.profile, { ifMatch: guard ?? '', parse: DisplayResponseSchema }));
    if (profile.kind !== 'ok') return outcomeMessage(profile);
    await advance(profile.value.etag);
    if (!input.isCurrent()) return `Profile revision ${profile.value.display.revision} saved. The tablet changed; return to Ruler check before saving calibration.`;
    const calibration = await run(store, { kind: 'form', key: `${id}:calibration` }, () => session.request('PUT', paths.calibration(id),
      { ...input.calibration, profile_revision: profile.value.display.revision, viewport_guard: true },
      { ifMatch: guard ?? '', parse: CalibrationResponseSchema }));
    if (calibration.kind !== 'ok') return `Profile revision ${profile.value.display.revision} saved. ${outcomeMessage(calibration)}`;
    await advance(calibration.value.etag);
    const state = store.getState();
    if (groups.some((group, i) => state.forms[`${id}:${group}`]?.version !== versions[i])) {
      return 'Measurements saved. New edits were kept; review them before saving again.';
    }
    return '';
  } catch (error) { return error instanceof Error ? error.message : 'Refresh wall status and review the saved measurements.'; }
}
