import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Grid2x2Plus } from 'lucide-react';
import { DeviceIdSchema } from '../../../api/devices';
import { useWallStore } from '../../../state/hooks';
import { applyGrid, buildGridPreview, changeGrid, gridOutdated, includeInGrid, moveInGrid, observeGrid, sizeInGrid } from '../../../state/commands/grid';
import { outcomeMessage } from '../../../state/commands/savedLayouts';
import { Button } from '../../../ui/Button';
import { Field } from '../../../ui/Field';
import { Input, Select, Switch } from '../../../ui/Input';
import { ModalDialog } from '../../../ui/ModalDialog';
import { SideSheet } from '../../../ui/SideSheet';
import { useShell } from '../../preview/ShellContext';

function GridFields() {
  const { store } = useShell();
  const grid = useWallStore(store, state => state.grid);
  if (!grid) return null;
  const input = grid.command;
  const units = input.kind === 'physical' ? 'mm' : 'logical units';
  return <div className="grid gap-4">
    <Field label="Units">{props => <Select {...props} name="kind" value={input.kind}
      onChange={event => changeGrid(store, { kind: event.target.value === 'physical' ? 'physical' : 'logical' })}>
      <option value="logical">Logical units</option><option value="physical">Measured millimetres</option>
    </Select>}</Field>
    <div className="grid grid-cols-2 gap-4">
      {(['columns', 'rows', 'gap', 'padding'] as const).map(key => <Field key={key}
        label={key === 'columns' ? 'Columns' : key === 'rows' ? 'Rows' : `${key === 'gap' ? 'Gap' : 'Padding'} (${units})`}>
        {props => <Input {...props} name={key} type="number" required min={key === 'rows' || key === 'columns' ? 1 : 0}
          max={key === 'rows' || key === 'columns' ? 64 : undefined} step={input.kind === 'physical' && (key === 'gap' || key === 'padding') ? 'any' : 1}
          value={Number.isFinite(input[key]) ? input[key] : ''} onChange={event => changeGrid(store, { [key]: event.target.valueAsNumber })} />}
      </Field>)}
    </div>
    <Field label="Wall sizing">{props => <Select {...props} name="sizing" value={input.sizing}
      onChange={event => changeGrid(store, { sizing: event.target.value === 'fixed' ? 'fixed' : 'tablets' })}>
      <option value="tablets">Fit to tablets</option><option value="fixed">Fixed bounds</option>
    </Select>}</Field>
    {input.kind === 'logical' ? <Field label="Orientation">{props => <Select {...props} name="orientation" value={input.orientation}
      onChange={event => {
        const value = event.target.value;
        if (value === 'preserve' || value === 'auto' || value === 'portrait' || value === 'landscape') changeGrid(store, { orientation: value });
      }}>
      <option value="preserve">Preserve</option><option value="auto">Auto from viewport</option>
      <option value="portrait">Portrait</option><option value="landscape">Landscape</option>
    </Select>}</Field> : null}
    <label className="flex items-center gap-3 t-body"><Switch name="holes" checked={input.allow_empty_cells}
      onChange={event => changeGrid(store, { allow_empty_cells: event.target.checked })} />Allow empty trailing cells</label>
  </div>;
}

function GridMembers() {
  const { store } = useShell();
  const grid = useWallStore(store, state => state.grid);
  const server = useWallStore(store, state => state.server);
  if (!grid || !server.config) return null;
  const input = grid.command;
  const active = server.config.layout.kind === 'logical' ? server.config.layout.placements : server.config.layout.slots;
  const order = [...input.device_ids, ...Object.keys(grid.members).filter(id => !input.device_ids.some(key => key === id))
    .sort((a, b) => (server.roster[a]?.number ?? Infinity) - (server.roster[b]?.number ?? Infinity) || a.localeCompare(b))];
  return <section className="grid gap-3" aria-labelledby="grid-members-title">
    <h3 id="grid-members-title" className="t-heading">Order and sizes</h3>
    <p className="t-caption">{input.device_ids.length} tablets · left to right, then top to bottom. New tablets wait for Include after your first edit.</p>
    <ol className="grid gap-4" aria-label="Grid tablet order">
      {order.map(id => {
        const member = grid.members[id]!;
        const index = input.device_ids.findIndex(key => key === id);
        const name = server.config?.device_labels[DeviceIdSchema.parse(id)] || server.roster[id]?.label || `Tablet ${server.roster[id]?.number ?? id.slice(0, 8)}`;
        return <li key={id} data-grid-device={id} className="grid gap-2 min-w-0 rounded-control bg-well p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="t-body min-w-0 flex-1 break-words">{member.included ? `${index + 1}. ` : ''}{name}</span>
            <Button variant={member.included ? 'ghost' : 'secondary'} aria-label={`${member.included ? 'Exclude' : 'Include'} ${name}`}
              onClick={() => includeInGrid(store, id, !member.included)}>{member.included ? 'Exclude' : 'Include'}</Button>
          </div>
          <p className="t-caption">{server.roster[id]?.online ? 'Online' : 'Offline reservation'} · {member.membershipSource === 'operator' ? 'Your choice' : member.included ? 'Included automatically' : 'Available to include'}</p>
          {member.included ? <>
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" size="sm" aria-label={`Move earlier, ${name}`} aria-disabled={index === 0}
                onClick={() => moveInGrid(store, id, -1)}><ArrowUp aria-hidden="true" />Earlier</Button>
              <Button variant="ghost" size="sm" aria-label={`Move later, ${name}`} aria-disabled={index === input.device_ids.length - 1}
                onClick={() => moveInGrid(store, id, 1)}><ArrowDown aria-hidden="true" />Later</Button>
            </div>
            <details>
              <summary className="t-label cursor-pointer rounded-control p-2 hover:bg-tonal focus-visible:outline-2 focus-visible:outline-focus">
                {input.kind === 'logical' ? `${member.size.w} × ${member.size.h} logical units · ${member.sizeSource}` : 'Mount angle'}</summary>
              {input.kind === 'logical' ? <div className="grid grid-cols-2 gap-3 pt-2">
                {(['w', 'h'] as const).map(key => <Field key={key} label={`${key === 'w' ? 'Width' : 'Height'} for ${name}`}>
                  {props => <Input {...props} name={`${id}-${key}`} type="number" min={1} step={1} required
                    value={Number.isFinite(member.size[key]) ? member.size[key] : ''}
                    onChange={event => sizeInGrid(store, id, key, event.target.valueAsNumber)} />}</Field>)}
              </div> : <Field label={`Mount angle for ${name}`}>{props => <Select {...props} name={`${id}-angle`}
                value={input.mount_angles?.[DeviceIdSchema.parse(id)] ?? (server.config?.layout.kind === 'physical' ? server.config.layout.slots[DeviceIdSchema.parse(id)]?.mount_angle : '') ?? ''}
                onChange={event => {
                  const angles = { ...input.mount_angles };
                  if (event.target.value === '') delete angles[DeviceIdSchema.parse(id)];
                  else {
                    const angle = Number(event.target.value);
                    if (angle === 0 || angle === 90 || angle === 180 || angle === 270) angles[DeviceIdSchema.parse(id)] = angle;
                  }
                  changeGrid(store, { mount_angles: angles });
                }}><option value="">Choose mounted top edge</option>
                {[0, 90, 180, 270].map(angle => <option key={angle} value={angle}>{angle}°</option>)}</Select>}</Field>}
            </details>
          </> : active[DeviceIdSchema.parse(id)] ? <label className="flex items-start gap-3 t-body">
            <Switch name={`release-${id}`} checked={input.release_unselected.some(key => key === id)} onChange={event => changeGrid(store,
              { release_unselected: event.target.checked ? [...input.release_unselected, DeviceIdSchema.parse(id)] : input.release_unselected.filter(key => key !== id) })} />
            Release {name} from the active arrangement</label> : null}
        </li>;
      })}
    </ol>
    {!order.length ? <p className="t-body">No tablets yet. Use Add a tablet, then return here to build the grid.</p> : null}
  </section>;
}

export default function GridBuilder() {
  const { store, session } = useShell();
  const grid = useWallStore(store, state => state.grid);
  const server = useWallStore(store, state => state.server);
  const open = useWallStore(store, state => state.ui.gridBuilderOpen);
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const pending = useRef(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const outdated = grid ? gridOutdated(grid, server.etag) : false;
  useEffect(() => { if (open) observeGrid(store); }, [open, server.roster, server.config, store]);
  const close = () => store.setState(state => ({ ui: { ...state.ui, gridBuilderOpen: false } }));
  const blocked = !server.config ? 'Waiting for the wall.' : server.rosterUnreachable ? 'The server can’t be reached.'
    : server.uncertain ? 'Refresh status first.' : !server.supported ? 'Update the console before editing.'
      : server.busy ? 'Another change is in progress.' : server.etagState !== 'current' ? 'Refresh status first.' : null;
  async function preview() {
    if (pending.current) return;
    pending.current = true;
    setWorking(true);
    setMessage(null);
    const result = await buildGridPreview(store, session, outdated);
    pending.current = false;
    setWorking(false);
    if (result.kind === 'ok') close();
    else { setMessage(outcomeMessage(result)); requestAnimationFrame(() => errorRef.current?.focus()); }
  }
  return <>
    <Button variant="ghost" className="src h-auto flex-col self-start" aria-haspopup="dialog" onClick={() => {
      observeGrid(store);
      setMessage(null);
      store.setState(state => ({ ui: { ...state.ui, gridBuilderOpen: true } }));
    }}><span className="thumb add"><Grid2x2Plus aria-hidden="true" /></span><span className="src-name">{grid?.dirty || grid?.preview ? 'Edit grid…' : 'New grid…'}</span></Button>
    <SideSheet open={open} onOpenChange={value => store.setState(state => ({ ui: { ...state.ui, gridBuilderOpen: value } }))} title="Build grid">
      <form className="grid gap-6" aria-label="Build grid" onSubmit={event => { event.preventDefault(); void preview(); }}>
        <p className="t-body">Choose the shape and tablet order. Preview leaves the wall unchanged.</p>
        <fieldset className="grid gap-6 min-w-0" disabled={working}>
          <legend className="sr-only">Grid inputs</legend>
          <GridFields /><GridMembers />
        </fieldset>
        {message ? <p ref={errorRef} tabIndex={-1} className="t-body text-err" role="alert">{message}</p> : null}
        {outdated ? <p className="t-body">The wall changed. Rebuild to review these inputs against the current wall.</p> : null}
        <div className="sticky bottom-0 grid gap-2 bg-overlay py-3">
          <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-full h-6 bg-overlay" />
          {blocked ? <Button type="submit" disabled disabledReason={blocked}>Preview grid</Button>
            : <Button type="submit" {...(working ? { busy: true as const, busyLabel: 'Building preview…' } : { busy: false as const })}>{outdated ? 'Rebuild preview' : 'Preview grid'}</Button>}
          <Button variant="ghost" onClick={close}>Keep inputs and close</Button>
        </div>
      </form>
    </SideSheet>
  </>;
}

export function GridApplyAction() {
  const { store, session } = useShell();
  const grid = useWallStore(store, state => state.grid);
  const server = useWallStore(store, state => state.server);
  const [message, setMessage] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const pending = useRef(false);
  const preview = grid?.preview;
  if (!grid || !preview) return null;
  const reason = server.rosterUnreachable ? 'The server can’t be reached.' : server.uncertain ? 'Refresh status first.'
    : !server.supported ? 'Update the console before editing.' : server.etagState !== 'current' || gridOutdated(grid, server.etag) ? 'Rebuild preview first.' : undefined;
  const edit = () => store.setState(state => ({ ui: { ...state.ui, gridBuilderOpen: true } }));
  async function apply() {
    if (pending.current) return;
    pending.current = true;
    setMessage(null);
    const result = await applyGrid(store, session);
    pending.current = false;
    setConfirm(false);
    if (result.kind !== 'ok') setMessage(outcomeMessage(result));
  }
  return <div className="primary-action">
    {reason ? <Button size="lg" disabled disabledReason={reason}>Apply layout</Button>
      : <Button size="lg" {...(server.busy ? { busy: true as const, busyLabel: 'Applying…' } : { busy: false as const })} onClick={() => {
        if (preview.previous_kind !== preview.layout.kind) setConfirm(true); else void apply();
      }}>Apply layout</Button>}
    <p className="t-caption">{grid.command.columns} columns × {grid.command.rows} rows · {preview.order.length} tablets. Image unchanged.</p>
    {preview.warnings.length ? <p className="t-caption text-warn" role="status">{preview.warnings.join(' ')}</p> : null}
    {message ? <p className="t-caption text-err" role="alert">{message}</p> : null}
    <div className="flex gap-2">
      <Button variant="ghost" onClick={edit}>{gridOutdated(grid, server.etag) ? 'Rebuild preview' : 'Edit grid'}</Button>
      <Button variant="ghost" onClick={() => store.setState({ grid: null })}>Discard</Button>
    </div>
    <ModalDialog open={confirm} onOpenChange={setConfirm} title="Change the wall kind">
      <p className="t-body">Apply this {preview.layout.kind} grid in place of the {preview.previous_kind} arrangement? The server saves a named return point first. The image stays unchanged.</p>
      <div className="flex flex-wrap justify-end gap-2 pt-4">
        <Button variant="ghost" autoFocus onClick={() => setConfirm(false)}>Cancel</Button>
        <Button {...(server.busy ? { busy: true as const, busyLabel: 'Applying…' } : { busy: false as const })} onClick={() => void apply()}>Apply grid</Button>
      </div>
    </ModalDialog>
  </div>;
}
