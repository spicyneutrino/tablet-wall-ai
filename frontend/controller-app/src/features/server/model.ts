import { z } from 'zod';
import type { Diagnostics } from '../../api/diagnostics';
import type { Readiness } from '../../api/readiness';
import type { CommandOutcome } from '../../session/outcome';

/** `/healthz` has no shared schema in `src/api`. This unit cannot add one there. */
export const HealthSchema = z.looseObject({
  ready: z.boolean(),
  schema: z.int().nullable(),
  schema_expected: z.int(),
  generation: z.string().nullable(),
  revision: z.int().nullable(),
  counts: z.looseObject({
    devices_online: z.int().nonnegative(),
    devices_total: z.int().nonnegative(),
  }),
  storage_readable: z.boolean(),
});
export type Health = z.infer<typeof HealthSchema>;

export type Load<T> = { kind: 'loading' } | { kind: 'ready'; value: T } | { kind: 'error'; message: string };
export type Fact = { label: string; value: string; ok: boolean };
export type TabletAddress =
  | { kind: 'ready'; url: string }
  | { kind: 'missing' }
  | { kind: 'unusable' };

const MISSING_ORIGIN = 'No tablet address is configured. Set TABLET_WALL_TABLET_ORIGIN to the http or https origin the tablets open, then close Server and open it again.';
const UNUSABLE_ORIGIN = 'The configured tablet origin is not a usable http or https address. Set TABLET_WALL_TABLET_ORIGIN to an origin such as http://10.42.0.1:8080, with no path, query, or password, then close Server and open it again.';

export function tabletAddress(origin: string | null): TabletAddress {
  if (origin === null) return { kind: 'missing' };
  let url: URL;
  try { url = new URL(origin); } catch { return { kind: 'unusable' }; }
  const usable = (url.protocol === 'http:' || url.protocol === 'https:')
    && url.username === '' && url.password === '' && url.search === '' && url.hash === ''
    && url.pathname === '/' && url.origin === origin;
  return usable ? { kind: 'ready', url: `${origin}/client/` } : { kind: 'unusable' };
}

export function joiningMessage(address: TabletAddress): string | null {
  if (address.kind === 'missing') return MISSING_ORIGIN;
  if (address.kind === 'unusable') return UNUSABLE_ORIGIN;
  return null;
}

export function recordedFact(value: string | null, recorded: boolean): string {
  if (!recorded) return 'not recorded';
  const trimmed = value?.trim() ?? '';
  return trimmed || 'Recorded, time not reported';
}

export function manifestInstant(value: string | null): string {
  const trimmed = value?.trim() ?? '';
  return trimmed || 'not recorded';
}

export function manifestSummary(readinessAt: string, diagnosticsAt: string): string {
  return readinessAt === diagnosticsAt ? readinessAt : `Readiness: ${readinessAt}. Diagnostics: ${diagnosticsAt}.`;
}

export function uploadsText(uploads: Readiness['security']['uploads']): string {
  switch (uploads) {
    case 'disabled': return 'Off';
    case 'loopback': return 'On, this computer only';
    case 'proxy': return 'On, through the proxy';
    default: {
      const _exhaustive: never = uploads;
      return _exhaustive;
    }
  }
}

export function formatBytes(value: number | null): string {
  if (value === null) return 'size not reported';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'] as const;
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const unit = units[index] ?? 'TB';
  const shown = index === 0 || size >= 10 ? size.toFixed(0) : size.toFixed(1);
  return `${shown} ${unit}`;
}

export function wakeLockText(counts: Record<string, number>): string {
  const order = ['held', 'released', 'unsupported', 'insecure', 'denied'] as const;
  const parts = order.flatMap((key) => {
    const count = counts[key] ?? 0;
    return count > 0 ? [`${String(count)} ${key}`] : [];
  });
  return parts.length ? parts.join(', ') : 'No reports';
}

export function healthFacts(health: Health | null, diagnostics: Diagnostics | null, address: TabletAddress | null, uploads: string | null): Fact[] {
  const facts: Fact[] = [];
  if (health) {
    facts.push({ label: 'Server', value: health.ready ? 'Ready' : 'Not ready', ok: health.ready });
    facts.push({
      label: 'Database',
      value: health.storage_readable ? `Readable, schema ${health.schema ?? 'not reported'}` : 'Not readable',
      ok: health.storage_readable,
    });
  }
  if (diagnostics) {
    const { media } = diagnostics;
    const verified = media.integrity ? (media.integrity.ok ? ', files match' : ', files do not match') : '';
    facts.push({
      label: 'Media files',
      value: `${String(media.assets)} assets, ${String(media.objects)} objects${verified}`,
      ok: media.orphans === 0 && media.integrity?.ok !== false,
    });
    facts.push({
      label: 'Clients',
      value: `${String(diagnostics.clients.online)} of ${String(diagnostics.clients.total)} online`,
      ok: true,
    });
  }
  if (address?.kind === 'ready') {
    facts.push({ label: 'Tablet joining', value: new URL(address.url).host, ok: true });
  } else if (address) {
    facts.push({ label: 'Tablet joining', value: 'Not configured', ok: false });
  }
  if (uploads) facts.push({ label: 'Uploads', value: uploads, ok: true });
  return facts;
}

export function readFailure(result: Exclude<CommandOutcome<unknown>, { kind: 'ok' }>, subject: string): string {
  switch (result.kind) {
    case 'rejected':
      if (result.status === 503) return `${subject} says the server is not ready. Check that the server is running, then close Server and open it again.`;
      if (result.status === 403) return `${subject} was refused. Open the controller on the wall’s computer, then try again.`;
      if (result.status === 0) return `${subject} could not be read because the connection was lost. Close Server and open it again.`;
      return `${subject} could not be read. ${result.message} Close Server and open it again.`;
    case 'uncertain':
      return `${subject} may not have been read. ${result.message}`;
    case 'conflict':
      return `${subject} was refused because the wall changed. Close Server and open it again.`;
    case 'precondition-missing':
      return `${subject} was refused because this page has no current wall version. Close Server and open it again.`;
    case 'refused-locally':
      return `${subject} was not read. Close Server and open it again.`;
    default: {
      const _exhaustive: never = result;
      return _exhaustive;
    }
  }
}

export function problemText(problem: unknown): string {
  if (typeof problem === 'string') return problem;
  try { return JSON.stringify(problem); } catch { return 'Unreadable problem'; }
}
