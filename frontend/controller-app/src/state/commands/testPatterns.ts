import { ConfigSchema } from '../../api/config';
import { ColorDeliverySchema } from '../../api/devices';
import type { ColorDelivery, DeviceId } from '../../api/devices';
import { TestPatternSchema } from '../../api/images';
import { paths } from '../../api/paths';
import type { CommandOutcome } from '../../session/outcome';
import type { Session } from '../../session/session';
import type { WallStoreApi } from '../store';
import { run } from './run';

export const testPatterns = [
  { value: 'grid', name: 'Calibration grid' },
  { value: 'black', name: 'Black' },
] as const;
export type TestPattern = (typeof testPatterns)[number]['value'];

export const testColours = [
  { value: 'red', name: 'Red', color: '#ef4444' },
  { value: 'green', name: 'Green', color: '#22c55e' },
  { value: 'blue', name: 'Blue', color: '#3b82f6' },
  { value: 'white', name: 'White', color: '#ffffff' },
  { value: 'black', name: 'Black', color: '#000000' },
] as const;
export type TestColour = (typeof testColours)[number]['value'];

export function selectTestPattern(store: WallStoreApi, pattern: TestPattern | null) {
  store.setState(state => ({ ui: { ...state.ui, testPattern: pattern } }));
}

export function testPatternName(pattern: TestPattern) {
  return testPatterns.find(entry => entry.value === pattern)?.name ?? pattern;
}

/*
 * The pattern endpoint publishes an asset but does not select a scene, so the
 * wall only shows the pattern after the scene write that follows it.
 */
export function showTestPattern(store: WallStoreApi, session: Session, pattern: TestPattern) {
  return run(store, { kind: 'content' }, async guard => {
    const posted = await session.request('POST', paths.testPattern, { pattern },
      { ifMatch: guard ?? '', parse: TestPatternSchema });
    if (posted.kind !== 'ok') return posted;
    return session.request('PUT', paths.scene,
      { content: { type: 'image', asset: posted.value.id, fit: 'contain',
        ...(pattern === 'black' ? { background: '#000000' } : {}) } },
      { ifMatch: posted.value.etag, parse: ConfigSchema });
  });
}

export type ColourTarget = { kind: 'all' } | { kind: 'tablet'; id: DeviceId; name: string };

export function sendTestColour(session: Session, color: string, target: ColourTarget) {
  return session.request('POST', paths.color(target.kind === 'tablet' ? target.id : undefined),
    { color }, { parse: ColorDeliverySchema });
}

export function colourDeliveryText(delivery: ColorDelivery, target: ColourTarget) {
  if ('updated' in delivery) {
    return `Sent to ${delivery.delivered} ${delivery.delivered === 1 ? 'tablet' : 'tablets'}`;
  }
  const name = target.kind === 'tablet' ? target.name : 'The tablet';
  return delivery.delivered ? `Sent to ${name}` : `Not delivered. ${name} is offline.`;
}

export function patternOutcomeText(outcome: CommandOutcome<unknown>): string {
  switch (outcome.kind) {
    case 'ok': return 'Test pattern on the wall.';
    case 'conflict': return 'The wall changed while showing this pattern. Refresh status, then try again.';
    case 'uncertain': return outcome.message;
    case 'rejected': return outcome.message;
    case 'precondition-missing': return 'Refresh status before showing this pattern.';
    case 'refused-locally':
      return outcome.reason === 'busy' ? 'Another command is running.'
        : outcome.reason === 'unsupported' ? 'Update the console first.'
          : 'Refresh status before showing this pattern.';
  }
}

export function colourOutcomeText(outcome: CommandOutcome<ColorDelivery>, target: ColourTarget): string {
  switch (outcome.kind) {
    case 'ok': return colourDeliveryText(outcome.value, target);
    case 'uncertain': return outcome.message;
    case 'rejected': return outcome.message;
    case 'refused-locally':
      return outcome.reason === 'busy' ? 'Another command is running.'
        : outcome.reason === 'unsupported' ? 'Update the console first.'
          : 'Refresh status before sending a colour.';
    default: return 'The colour command was not accepted. Refresh status and try again.';
  }
}
