import type { ConfigEtag } from '../api/etag';

export type CommandOutcome<T> =
  | { kind: 'ok'; value: T; commandEtag?: ConfigEtag }
  | { kind: 'conflict' }
  | { kind: 'precondition-missing' }
  | { kind: 'rejected'; status: number; message: string }
  | { kind: 'refused-locally'; reason: 'busy' | 'uncertain' | 'unsupported' | 'stale-etag' }
  | { kind: 'uncertain'; message: string };

export class ApiError extends Error {
  constructor(readonly status: number, detail: string, readonly uncertain = status === 0) {
    super(detail);
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
