import { ConfigSchema, TabletAssignmentResponseSchema } from '../../api/config';
import type { Config } from '../../api/config';
import { LabelCommandSchema } from '../../api/devices';
import type { DeviceId, LabelCommand, TabletAssignmentCommand } from '../../api/devices';
import { paths } from '../../api/paths';
import type { CommandOutcome } from '../../session/outcome';
import type { Session } from '../../session/session';
import { editForm } from '../store';
import type { WallStoreApi } from '../store';
import { run } from './run';

// Ported from frontend/controller/physical.html:943 and main.py:1985 (the label limit).
export const LABEL_MAX = 80;
export const LABEL_LIMIT = `Names are ${LABEL_MAX} characters at most.`;

export type DeviceAction = 'identify' | 'retry' | 'reconnect';

/** The result line each tablet action shows when the server accepts it. */
export const ACTION_RESULT: Record<DeviceAction, string> = {
  identify: 'Flashing for 5 s', retry: 'Retry sent', reconnect: 'Reconnect sent',
};

/** Counts code points, as the server does after trimming. */
export function labelProblem(raw: string): string | null {
  const length = [...raw.trim()].length;
  return length > LABEL_MAX ? `${LABEL_LIMIT} This name has ${length}.` : null;
}

export function labelBody(raw: string): LabelCommand {
  return LabelCommandSchema.parse({ label: raw.trim() || null });
}

export function deviceMessage(outcome: CommandOutcome<unknown>): string {
  switch (outcome.kind) {
    case 'ok': return '';
    case 'conflict': return 'The wall changed. Refresh status, then try again.';
    case 'precondition-missing': return 'Refresh status, then try again.';
    case 'rejected': return outcome.message;
    case 'uncertain': return `Not confirmed. ${outcome.message}`;
    case 'refused-locally':
      return outcome.reason === 'busy' ? 'Another change is already being sent. Wait for it to finish.'
        : outcome.reason === 'uncertain' ? 'The last change was not confirmed. Refresh status first.'
          : outcome.reason === 'unsupported' ? 'Update the console before editing.'
            : 'The wall may have changed. Refresh status first.';
  }
}

export function saveLabel(store: WallStoreApi, session: Session, id: DeviceId) {
  const state = store.getState();
  const key = `${id}:name` as const;
  const form = state.forms[key];
  if (!form) return Promise.resolve<CommandOutcome<Config>>({ kind: 'rejected', status: 409, message: 'Open the tablet details before saving its name.' });
  const raw = typeof form.values.name === 'string' ? form.values.name : '';
  const problem = labelProblem(raw);
  if (problem) return Promise.resolve<CommandOutcome<Config>>({ kind: 'rejected', status: 422, message: problem });
  const body = labelBody(raw);
  // The server trims the label. Trim the draft first so a saved form and the field agree.
  if (raw !== raw.trim()) editForm(store, key, { ...form.values, name: raw.trim() });
  return run(store, { kind: 'form', key }, guard => session.request('PATCH', paths.device(id), body,
    { ifMatch: guard ?? undefined, parse: ConfigSchema }));
}

export function assignmentBody(choice: string): TabletAssignmentCommand | null {
  if (!choice) return null;
  return choice === 'manual' ? { mode: 'manual', model_id: null } : { mode: 'explicit', model_id: choice };
}

export async function saveModelChoice(store: WallStoreApi, session: Session, id: DeviceId, choice: string) {
  const body = assignmentBody(choice);
  if (!body) return { kind: 'rejected', status: 422, message: 'Choose a model or Manual measurements.' } as const;
  const key = `${id}:model` as const;
  const outcome = await run(store, { kind: 'form', key }, guard => session.request('PUT', paths.tabletAssignment(id), body,
    { ifMatch: guard ?? undefined, parse: TabletAssignmentResponseSchema }));
  // The assignment response carries no Config, so adopt the new revision before the next guarded write.
  if (outcome.kind === 'ok') await session.refresh().catch(() => undefined);
  return outcome;
}

export function deviceCommand(session: Session, id: DeviceId, action: DeviceAction) {
  const path = action === 'identify' ? paths.identify(id) : action === 'retry' ? paths.retryImage(id) : paths.reconnect(id);
  const body = action === 'identify' ? { duration_ms: 5000 } : undefined;
  return session.request('POST', path, body, { useCurrentEtag: true, parse: ConfigSchema });
}

export type BatchStatus = 'completed' | 'failed' | 'conflict' | 'uncertain' | 'untouched';
export type BatchSubject = { id: DeviceId; status: BatchStatus; message: string };
export type BatchResult = { action: DeviceAction; subjects: BatchSubject[] };

/** Sequential, as the old confirmModels loop was: the captured order never changes and a stop leaves the rest untouched. */
export async function runDeviceBatch(store: WallStoreApi, session: Session,
  action: DeviceAction, ids: readonly DeviceId[]): Promise<BatchResult> {
  const captured = [...ids];
  const subjects: BatchSubject[] = captured.map(id => ({ id, status: 'untouched', message: 'Not reached.' }));
  for (let index = 0; index < captured.length; index += 1) {
    const id = captured[index]!;
    const device = store.getState().server.roster[id];
    if (!device?.online) {
      subjects[index] = { id, status: 'failed', message: 'Offline. Commands need it online.' };
      break;
    }
    const outcome = await deviceCommand(session, id, action);
    if (outcome.kind === 'ok') {
      subjects[index] = { id, status: 'completed', message: ACTION_RESULT[action] };
      continue;
    }
    const status: BatchStatus = outcome.kind === 'conflict'
      || outcome.kind === 'refused-locally' && outcome.reason === 'stale-etag' ? 'conflict'
      : outcome.kind === 'uncertain' ? 'uncertain' : 'failed';
    subjects[index] = { id, status, message: deviceMessage(outcome) };
    break;
  }
  return { action, subjects };
}

export const BATCH_WORD: Record<BatchStatus, string> = {
  completed: 'Completed', failed: 'Failed', conflict: 'Conflict', uncertain: 'Uncertain', untouched: 'Untouched',
};
