import { useEffect, useId, useRef, useState } from 'react';
import { ChevronRight, CircleAlert, CircleCheck, Copy, Download, FileCheck } from 'lucide-react';
import { DiagnosticsSchema } from '../../api/diagnostics';
import type { Diagnostics } from '../../api/diagnostics';
import { paths } from '../../api/paths';
import { OperatorConfigSchema, ReadinessSchema } from '../../api/readiness';
import type { OperatorConfig, Readiness } from '../../api/readiness';
import type { Session } from '../../session/session';
import { Button } from '../../ui/Button';
import { Switch } from '../../ui/Input';
import { Label } from '../../ui/Label';
import { SideSheet } from '../../ui/SideSheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../ui/Tabs';
import { useWallStore } from '../../state/hooks';
import EmptyWall from '../sources/layouts/EmptyWall';
import Playback from '../playback';
import { useShell } from '../preview/ShellContext';
import {
  HealthSchema, formatBytes, healthFacts, joiningMessage, manifestInstant, manifestSummary,
  problemText, readFailure, recordedFact, tabletAddress, uploadsText, wakeLockText,
} from './model';
import type { Fact, Health, Load, TabletAddress } from './model';
import { readPlaybackOptIn, writePlaybackOptIn } from './playbackOptIn';
import './server.css';

const loading: Load<never> = { kind: 'loading' };

async function readJson<T>(session: Session, path: string, schema: { parse: (value: unknown) => T }, subject: string): Promise<Load<T>> {
  const result = await session.request('GET', path, undefined, { parse: schema });
  if (result.kind === 'ok') return { kind: 'ready', value: result.value };
  return { kind: 'error', message: readFailure(result, subject) };
}

function saveDiagnostics(diagnostics: Diagnostics) {
  const blob = new Blob([`${JSON.stringify(diagnostics, null, 2)}\n`], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'tablet-wall-diagnostics.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function FactList({ facts }: { facts: Fact[] }) {
  if (!facts.length) return null;
  return <ul className="server-facts list-divided">
    {facts.map((fact) => <li className="fact-row" key={fact.label}>
      {fact.ok ? <CircleCheck className="text-ok" aria-hidden="true" /> : <CircleAlert className="text-err" aria-hidden="true" />}
      <span className="t-body fact-label">{fact.label}</span>
      <span className="t-body t-muted fact-value">{fact.value}</span>
    </li>)}
  </ul>;
}

function TryAgain({ onRetry }: { onRetry: () => void }) {
  return <Button variant="ghost" className="justify-self-start" onClick={onRetry}>Try again</Button>;
}

function ReportButton({ diagnostics, verifying }: { diagnostics: Load<Diagnostics>; verifying: boolean }) {
  if (verifying) return <Button variant="secondary" disabled disabledReason="Wait for the file check to finish."><Download aria-hidden="true" />Download report</Button>;
  if (diagnostics.kind !== 'ready') {
    const reason = diagnostics.kind === 'loading'
      ? 'Wait until diagnostics finish loading.'
      : 'Diagnostics did not load, so there is no report to save.';
    return <Button variant="secondary" disabled disabledReason={reason}><Download aria-hidden="true" />Download report</Button>;
  }
  return <Button variant="secondary" onClick={() => saveDiagnostics(diagnostics.value)}><Download aria-hidden="true" />Download report</Button>;
}

function VerifyButton({ verifying, onVerify }: { verifying: boolean; onVerify: () => void }) {
  if (verifying) return <Button variant="ghost" busy busyLabel="Checking files"><FileCheck aria-hidden="true" />Verify files</Button>;
  return <Button variant="ghost" onClick={onVerify}><FileCheck aria-hidden="true" />Verify files</Button>;
}

function HealthTab({ health, diagnostics, readiness, address, checkedAt, verifying, verifyNote, verifyError, onVerify, onRetry }: {
  health: Load<Health>; diagnostics: Load<Diagnostics>; readiness: Load<Readiness>; address: TabletAddress | null;
  checkedAt: string | null; verifying: boolean; verifyNote: string; verifyError: string; onVerify: () => void; onRetry: () => void;
}) {
  const healthValue = health.kind === 'ready' ? health.value : null;
  const diagnosticsValue = diagnostics.kind === 'ready' ? diagnostics.value : null;
  const uploads = readiness.kind === 'ready' ? uploadsText(readiness.value.security.uploads) : null;
  const facts = healthFacts(healthValue, diagnosticsValue, address, uploads);
  const reading = health.kind === 'loading' || diagnostics.kind === 'loading';
  const failed = health.kind === 'error' || diagnostics.kind === 'error';
  const filesOk = diagnosticsValue?.media.integrity?.ok !== false && (diagnosticsValue?.media.orphans ?? 0) === 0;
  const ready = healthValue?.ready === true && diagnostics.kind === 'ready' && readiness.kind === 'ready'
    && address?.kind === 'ready' && readiness.value.errors.length === 0 && !verifyError && filesOk;
  const problems = diagnosticsValue?.media.integrity?.problems ?? [];
  const checked = checkedAt
    ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(checkedAt))
    : null;
  return <div className="server-panel">
    {ready ? <div className="note note-ok"><p className="note-title"><CircleCheck aria-hidden="true" />All checks pass</p>
      <p className="t-body">{checked ? `Checked at ${checked}. ` : ''}Nothing needs doing.</p></div> : null}
    {readiness.kind === 'ready' && readiness.value.errors.length ? <div className="note note-warn">
      <p className="note-title"><CircleAlert aria-hidden="true" />The server reported a problem</p>
      {readiness.value.errors.map((error) => <p className="t-body" key={error}>{error}</p>)}
    </div> : null}
    <section className="server-block" aria-labelledby="server-health-title">
      <h3 id="server-health-title" className="t-heading">Diagnostics</h3>
      {reading ? <p className="t-body">Reading server health…</p> : null}
      {health.kind === 'error' ? <p className="t-body">{health.message}</p> : null}
      {diagnostics.kind === 'error' ? <p className="t-body">{diagnostics.message}</p> : null}
      {verifyError ? <p className="t-body">{verifyError}</p> : null}
      {failed || verifyError ? <TryAgain onRetry={onRetry} /> : null}
      <FactList facts={facts} />
      {verifyNote ? <p className="t-body" aria-live="polite">{verifyNote}</p> : null}
      {problems.length ? <ul className="server-facts">{problems.map((problem, index) => <li className="t-body" key={index}>{problemText(problem)}</li>)}</ul> : null}
      <div className="server-actions">
        <ReportButton diagnostics={diagnostics} verifying={verifying} />
        <VerifyButton verifying={verifying} onVerify={onVerify} />
      </div>
      {healthValue || diagnosticsValue ? <details>
        <summary><ChevronRight className="chev" aria-hidden="true" />Technical details</summary>
        <dl className="backup-facts technical-facts">
          {healthValue ? <>
            <dt className="t-muted">Generation</dt><dd>{healthValue.generation ?? 'not reported'}</dd>
            <dt className="t-muted">Revision</dt><dd>{healthValue.revision ?? 'not reported'}</dd>
            <dt className="t-muted">Schema expected</dt><dd>{healthValue.schema_expected}</dd>
          </> : null}
          {diagnosticsValue ? <>
            <dt className="t-muted">Database size</dt><dd>{formatBytes(diagnosticsValue.db.bytes)}</dd>
            <dt className="t-muted">Media used</dt><dd>{formatBytes(diagnosticsValue.media.used_bytes)} of {formatBytes(diagnosticsValue.media.quota_bytes)}</dd>
            <dt className="t-muted">Free space</dt><dd>{formatBytes(diagnosticsValue.media.free_bytes)}</dd>
            <dt className="t-muted">Reserve</dt><dd>{formatBytes(diagnosticsValue.media.reserve_bytes)}</dd>
            <dt className="t-muted">Orphans</dt><dd>{diagnosticsValue.media.orphans}</dd>
            <dt className="t-muted">Wake lock</dt><dd>{wakeLockText(diagnosticsValue.clients.wake_lock)}</dd>
          </> : null}
        </dl>
      </details> : null}
    </section>
  </div>;
}

function JoiningTab({ config, onRetry }: { config: Load<OperatorConfig>; onRetry: () => void }) {
  const [copyStatus, setCopyStatus] = useState('');
  const address = config.kind === 'ready' ? tabletAddress(config.value.tablet_origin) : null;
  const reason = address ? joiningMessage(address) : null;
  async function copy(url: string) {
    try {
      if (!navigator.clipboard) throw new Error('Clipboard is unavailable.');
      await navigator.clipboard.writeText(url);
      setCopyStatus('Copied');
    } catch {
      setCopyStatus('Copy is blocked in this browser. Select the address and copy it.');
    }
  }
  return <div className="server-panel">
    <section className="server-block" aria-label="Joining">
      {config.kind === 'loading' ? <p className="t-body">Reading the tablet address…</p> : null}
      {config.kind === 'error' ? <><p className="t-body">{config.message}</p><TryAgain onRetry={onRetry} /></> : null}
      {reason ? <p className="t-body">{reason}</p> : null}
      {address?.kind === 'ready' ? <>
        <p className="t-body">Open this address on each tablet.</p>
        <div className="join-code">
          <span className="join-qr"><img src={paths.joinQr} alt="QR code for the tablet address" width={96} height={96} /></span>
          <div className="shell-slot">
            <p className="t-heading join-address" translate="no">{address.url}</p>
            <Button className="justify-self-start" onClick={() => void copy(address.url)}><Copy aria-hidden="true" />Copy link</Button>
            <p className="t-caption" aria-live="polite">{copyStatus}</p>
          </div>
        </div>
      </> : null}
    </section>
  </div>;
}

function manifestText(readiness: Load<Readiness>, diagnostics: Load<Diagnostics>): string | null {
  const fromReadiness = readiness.kind === 'ready'
    ? recordedFact(readiness.value.backup.last_manifest_at, readiness.value.backup.recorded) : null;
  const fromDiagnostics = diagnostics.kind === 'ready' ? manifestInstant(diagnostics.value.backup.last_manifest_at) : null;
  if (fromReadiness !== null && fromDiagnostics !== null) return manifestSummary(fromReadiness, fromDiagnostics);
  return fromReadiness ?? fromDiagnostics;
}

function BackupTab({ readiness, diagnostics, onRetry }: { readiness: Load<Readiness>; diagnostics: Load<Diagnostics>; onRetry: () => void }) {
  const reading = readiness.kind === 'loading' || diagnostics.kind === 'loading';
  const manifest = manifestText(readiness, diagnostics);
  const rehearsal = readiness.kind === 'ready'
    ? recordedFact(readiness.value.restore_rehearsal.completed_utc, readiness.value.restore_rehearsal.recorded) : null;
  return <div className="server-panel">
    <section className="server-block" aria-labelledby="server-backup-title">
      <h3 id="server-backup-title" className="t-heading">Backup</h3>
      <p className="t-body measure">Backups run from the server command line. This page reports the last snapshot and the last restore rehearsal written to disk, or “not recorded”.</p>
      {reading ? <p className="t-body">Reading backup facts…</p> : null}
      {readiness.kind === 'error' ? <p className="t-body">{readiness.message}</p> : null}
      {diagnostics.kind === 'error' ? <p className="t-body">{diagnostics.message}</p> : null}
      {readiness.kind === 'error' || diagnostics.kind === 'error' ? <TryAgain onRetry={onRetry} /> : null}
      {manifest || rehearsal ? <dl className="backup-facts">
        {manifest ? <><dt className="t-muted">Last manifest</dt><dd>{manifest}</dd></> : null}
        {rehearsal ? <><dt className="t-muted">Restore rehearsal</dt><dd>{rehearsal}</dd></> : null}
      </dl> : null}
    </section>
    {/* U20 mounts EmptyWall here: the clear-wall confirmation. */}
    <div className="server-mount" data-mount="empty-wall"><EmptyWall /></div>
  </div>;
}

function PlaybackTab() {
  const helpId = useId();
  const [on, setOn] = useState(readPlaybackOptIn);
  const [storageNote, setStorageNote] = useState('');
  const { store } = useShell();
  const unreachable = useWallStore(store, state => state.server.rosterUnreachable);
  function change(next: boolean) {
    setOn(next);
    setStorageNote(writePlaybackOptIn(next) ? '' : 'This browser did not store the choice. It lasts for this visit only. Allow site storage, then switch it again.');
  }
  return <div className="server-panel">
    <Label className="playback-opt-in">
      <Switch checked={on} onChange={(event) => change(event.target.checked)} aria-describedby={helpId} />
      <span className="playback-copy">
        <span className="flex items-center gap-2">Playlist and playback <span className="tag">Experimental</span></span>
        <span id={helpId} className="t-caption">Plays saved images in order as hard cuts. Turn off to hide it.</span>
      </span>
    </Label>
    {storageNote ? <p className="t-caption">{storageNote}</p> : null}
    {/* U30 mounts playlist and transport here, and only while this switch is on. */}
    <div className="server-mount" data-mount="playback">{on ? <fieldset className="measure-source-controls" disabled={unreachable}>
      {unreachable ? <p className="t-caption" role="status">The server can’t be reached. Playlist and playback controls are paused.</p> : null}
      <Playback />
    </fieldset> : null}</div>
  </div>;
}

function ServerSheet() {
  const { session } = useShell();
  const [attempt, setAttempt] = useState(0);
  const [health, setHealth] = useState<Load<Health>>(loading);
  const [diagnostics, setDiagnostics] = useState<Load<Diagnostics>>(loading);
  const [readiness, setReadiness] = useState<Load<Readiness>>(loading);
  const [config, setConfig] = useState<Load<OperatorConfig>>(loading);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyNote, setVerifyNote] = useState('');
  const [verifyError, setVerifyError] = useState('');
  const requestId = useRef(0);
  const verifyId = useRef(0);
  useEffect(() => {
    const id = requestId.current + 1;
    requestId.current = id;
    let active = true;
    void Promise.all([
      readJson(session, '/healthz', HealthSchema, 'The healthz check'),
      readJson(session, paths.diagnostics(), DiagnosticsSchema, 'Diagnostics'),
      readJson(session, paths.readiness, ReadinessSchema, 'Backup facts'),
      readJson(session, paths.operatorConfig, OperatorConfigSchema, 'The tablet address'),
    ]).then(([nextHealth, nextDiagnostics, nextReadiness, nextConfig]) => {
      if (!active || requestId.current !== id) return;
      setCheckedAt(new Date().toISOString());
      setHealth(nextHealth);
      setDiagnostics(nextDiagnostics);
      setReadiness(nextReadiness);
      setConfig(nextConfig);
    });
    return () => { active = false; };
  }, [session, attempt]);
  function reload() {
    setHealth(loading);
    setDiagnostics(loading);
    setReadiness(loading);
    setConfig(loading);
    setCheckedAt(null);
    setVerifying(false);
    setVerifyNote('');
    setVerifyError('');
    setAttempt(value => value + 1);
  }
  async function verify() {
    const id = verifyId.current + 1;
    verifyId.current = id;
    setVerifying(true);
    setVerifyError('');
    setVerifyNote('');
    const result = await session.request('GET', paths.diagnostics(true), undefined, { parse: DiagnosticsSchema });
    if (verifyId.current !== id) return;
    setVerifying(false);
    if (result.kind === 'ok') {
      setDiagnostics({ kind: 'ready', value: result.value });
      const integrity = result.value.media.integrity;
      setVerifyNote(integrity
        ? integrity.ok
          ? 'File check passed. Every ready object matches its recorded id.'
          : 'File check found problems. These files do not match their recorded ids.'
        : 'The server did not return a file check. Close Server and open it again if this persists.');
      return;
    }
    setVerifyError(readFailure(result, 'The file check'));
  }
  const address = config.kind === 'ready' ? tabletAddress(config.value.tablet_origin) : null;
  return <Tabs className="server-sheet" defaultValue="health">
    <TabsList aria-label="Server sections">
      <TabsTrigger value="health" autoFocus>Health</TabsTrigger>
      <TabsTrigger value="joining">Joining</TabsTrigger>
      <TabsTrigger value="backup">Backup and reset</TabsTrigger>
      <TabsTrigger value="playback">Playback</TabsTrigger>
    </TabsList>
    <TabsContent value="health"><HealthTab health={health} diagnostics={diagnostics} readiness={readiness} address={address} checkedAt={checkedAt} verifying={verifying} verifyNote={verifyNote} verifyError={verifyError} onVerify={() => void verify()} onRetry={reload} /></TabsContent>
    <TabsContent value="joining"><JoiningTab config={config} onRetry={reload} /></TabsContent>
    <TabsContent value="backup"><BackupTab readiness={readiness} diagnostics={diagnostics} onRetry={reload} /></TabsContent>
    <TabsContent value="playback"><PlaybackTab /></TabsContent>
  </Tabs>;
}

export default function Server() {
  const { store } = useShell();
  const open = useWallStore(store, state => state.ui.serverOpen);
  return <SideSheet title="Server" open={open} onOpenChange={serverOpen => store.setState(state => ({ ui: { ...state.ui, serverOpen } }))}>
    {open ? <ServerSheet /> : null}
  </SideSheet>;
}
