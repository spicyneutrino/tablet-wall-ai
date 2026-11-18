import { useState } from 'react';
import { CircleCheck, CloudOff, Info, Grid3X3, Magnet, Move, Plus, TriangleAlert, Upload } from 'lucide-react';
import { Button } from '../ui/Button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/Tabs';
import { ToggleGroup, ToggleGroupItem } from '../ui/ToggleGroup';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/Tooltip';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from '../ui/DropdownMenu';
import { Input, Select, Switch, Textarea } from '../ui/Input';
import { Field } from '../ui/Field';
import { Label } from '../ui/Label';
import { StatusBadge } from '../ui/StatusBadge';
import { Tally } from '../ui/Tally';
import { ModalDialog } from '../ui/ModalDialog';
import { SideSheet } from '../ui/SideSheet';

const variants = [
  { variant: 'primary', label: 'Primary', action: 'Show on wall', busy: 'Showing…' },
  { variant: 'secondary', label: 'Tonal', action: 'Identify', busy: 'Saving…' },
  { variant: 'ghost', label: 'Ghost', action: 'Cancel', busy: 'Cancelling…' },
  { variant: 'danger', label: 'Danger', action: 'Clear wall…', busy: 'Clearing…' },
] satisfies { variant: 'primary' | 'secondary' | 'ghost' | 'danger'; label: string; action: string; busy: string }[];

export default function PrimitivesGallery() {
  const [overlay, setOverlay] = useState<'none' | 'confirm' | 'sheet'>('none');
  const [guarded, setGuarded] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [message, setMessage] = useState('');
  return <TooltipProvider delayDuration={150}>
    <main className="gallery mx-auto grid max-w-[1100px] gap-8 px-4 py-8 lg:px-8" aria-labelledby="gallery-title">
      <header><h1 id="gallery-title" className="t-title">Component states</h1>
        <p className="t-body t-muted mt-1">Every interactive state, with working keyboard controls and tonal surfaces.</p></header>
      <section className="grid gap-4" aria-labelledby="buttons-title">
        <h2 id="buttons-title" className="t-heading">Buttons</h2>
        <div className="gallery-buttons">
          <div className="gallery-column-labels t-caption"><span /><span>Rest</span><span>Hover</span><span>Focus-visible</span><span>Pressed / selected</span><span>Busy</span><span>Disabled</span></div>
          {variants.map(({ variant, label, action, busy }) => <div className="gallery-button-row" key={variant}>
            <h3 className="t-label t-muted">{label}</h3>
            <div><span className="gallery-state t-caption">Rest</span><Button variant={variant}>{action}</Button></div>
            <div><span className="gallery-state t-caption">Hover</span><Button variant={variant} className="is-hover">{action}</Button></div>
            <div><span className="gallery-state t-caption">Focus-visible</span><Button variant={variant} className="is-focus">{action}</Button></div>
            <div><span className="gallery-state t-caption">Pressed / selected</span>
              <Button variant={variant === 'danger' ? 'danger-solid' : variant} aria-pressed={variant !== 'danger' ? true : undefined}>
                {variant === 'ghost' ? <><Magnet aria-hidden="true" />Snap</> : variant === 'danger' ? 'Clear wall' : 'Edit layout'}
              </Button></div>
            <div><span className="gallery-state t-caption">Busy</span><Button variant={variant} busy busyLabel={busy}>{action}</Button></div>
            <div><span className="gallery-state t-caption">Disabled</span><Button variant={variant} disabled disabledReason="The server can’t be reached.">{action}</Button></div>
          </div>)}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="lg">Show on wall</Button><Button size="sm" variant="secondary">Try now</Button>
          <Button variant="danger-solid">Clear wall</Button><Button variant="danger-solid" className="is-hover">Clear wall</Button>
          <Button variant="ghost" size="icon" aria-label="Add source"><Plus aria-hidden="true" /></Button>
        </div>
      </section>
      <section className="grid gap-4" aria-labelledby="navigation-title">
        <h2 id="navigation-title" className="t-heading">Tabs, sources and rows</h2>
        <Tabs defaultValue="selected"><TabsList aria-label="Tab states">
          <TabsTrigger value="selected">Selected</TabsTrigger><TabsTrigger value="rest">Rest</TabsTrigger>
          <TabsTrigger value="hover" className="is-hover">Hover</TabsTrigger><TabsTrigger value="focus" className="is-focus">Focus</TabsTrigger>
          <TabsTrigger value="disabled" disabled>Unavailable</TabsTrigger>
        </TabsList>
          {['selected', 'rest', 'hover', 'focus', 'disabled'].map((value) => <TabsContent value={value} key={value}><p className="sr-only">{value} panel</p></TabsContent>)}
        </Tabs>
        <div className="flex flex-wrap gap-6">
          {['Selected', 'Rest', 'Hover', 'Focus', 'Loading'].map((state) => <button type="button" key={state}
            className={`src ${state === 'Hover' ? 'is-hover' : state === 'Focus' ? 'is-focus' : ''}`}
            aria-pressed={state === 'Selected'} disabled={state === 'Loading'}>
            <span className={`thumb ${state !== 'Loading' ? 'dark' : 'skel'}`}>{state !== 'Loading' ? <Grid3X3 aria-hidden="true" /> : null}</span>
            <span className="src-name">{state}</span>
          </button>)}
        </div>
        <ul className="side grid max-w-[400px] gap-1 p-2" aria-label="Row states">
          {['Rest', 'Hover', 'Current', 'Focus'].map((state, index) => <li key={state}>
            <button type="button" className={`row ${state === 'Hover' ? 'is-hover' : state === 'Focus' ? 'is-focus' : ''}`} aria-current={state === 'Current' ? 'true' : undefined}>
              <span className="num">{index + 1}</span><span className="min-w-0 flex-1"><span className="row-name block">{state}</span>
                <span className="t-caption">{['Pixel C', 'iPad Air 2', 'iPad mini 4', 'iPad mini 2'][index]}</span></span>
              <span className={`state ${index === 3 ? 'state-warn' : 'state-ok'}`}>{index === 3 ? <TriangleAlert aria-hidden="true" /> : <CircleCheck aria-hidden="true" />}{index === 3 ? 'Offline 12 min' : 'Showing'}</span>
            </button>
          </li>)}
        </ul>
      </section>
      <section className="grid gap-4" aria-labelledby="forms-title">
        <h2 id="forms-title" className="t-heading">Inputs and status</h2>
        <div className="grid max-w-[860px] gap-4 sm:grid-cols-4">
          <Field label="Rest">{(props) => <div className="unit"><Input {...props} name="rest" defaultValue="197.1" inputMode="decimal" autoComplete="off" /><span>mm</span></div>}</Field>
          <Field label="Hover">{(props) => <Input {...props} name="hover" className="is-hover" defaultValue="Tablet 2" autoComplete="off" />}</Field>
          <Field label="Focus">{(props) => <Input {...props} name="focus" className="is-focus" defaultValue="Tablet 2" autoComplete="off" />}</Field>
          <Field label="Invalid" error="Use a number above 0.">{(props) => <Input {...props} name="invalid" defaultValue="-4" inputMode="decimal" autoComplete="off" />}</Field>
          <Field label="Disabled">{(props) => <Input {...props} name="disabled" defaultValue="Model value" disabled />}</Field>
          <Label className="flex items-center gap-3"><Switch defaultChecked name="on" />Switch on</Label>
          <Label className="flex items-center gap-3"><Switch name="off" />Switch off</Label>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status="ok" label="4 of 4 showing" /><StatusBadge status="warn" label="3 of 4 showing" />
          <StatusBadge status="error" onClick={() => setOverlay('sheet')} /><StatusBadge status="connecting" /><StatusBadge status="unknown" />
          <span className="tag">Experimental</span><Tally kind="preview" /><Tally kind="live" />
        </div>
        <div className="grid max-w-[860px] gap-4 sm:grid-cols-2">
          <div className="drop"><Upload aria-hidden="true" /><p className="t-label">Drop target, rest</p></div>
          <div className="drop is-over"><Upload aria-hidden="true" /><p className="t-label">Drop target, file over it</p></div>
        </div>
      </section>
      <section className="grid gap-4" aria-labelledby="controls-title">
        <h2 id="controls-title" className="t-heading">Selection and overlays</h2>
        <div className="grid max-w-[860px] gap-4 sm:grid-cols-2">
          <Field label="Image fit" hint="Fit keeps the full image visible.">{(props) => <Select {...props} name="fit" defaultValue="fit"><option value="fit">Fit</option><option value="fill">Fill</option></Select>}</Field>
          <Field label="Notes">{(props) => <Textarea {...props} name="notes" autoComplete="off" placeholder="For example, tablets on the north wall…" />}</Field>
        </div>
        <ToggleGroup type="multiple" defaultValue={['move']} aria-label="Canvas tools">
          <ToggleGroupItem value="move"><Move aria-hidden="true" />Move</ToggleGroupItem>
          <ToggleGroupItem value="snap"><Magnet aria-hidden="true" />Snap</ToggleGroupItem>
          <ToggleGroupItem value="disabled" disabled>Unavailable</ToggleGroupItem>
        </ToggleGroup>
        <div className="flex flex-wrap gap-3">
          <Tooltip><TooltipTrigger asChild><Button variant="secondary">Identify tablet</Button></TooltipTrigger><TooltipContent>Flash the tablet’s number on its screen.</TooltipContent></Tooltip>
          <DropdownMenu><DropdownMenuTrigger asChild><Button variant="secondary">More actions</Button></DropdownMenuTrigger>
            <DropdownMenuContent><DropdownMenuLabel>Tablet 2</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => setMessage('Tablet identified.')}>Identify</DropdownMenuItem>
              <DropdownMenuItem disabled>Reconnect unavailable</DropdownMenuItem>
              <DropdownMenuItem variant="danger" onSelect={() => setOverlay('confirm')}>Clear wall…</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="danger" onClick={() => setOverlay('confirm')}>Open confirmation</Button>
          <Button variant="secondary" onClick={() => setOverlay('sheet')}>Open server sheet</Button>
        </div>
        <p role="status" className="t-caption">{message}</p>
        <div className="grid max-w-[860px] gap-4 sm:grid-cols-2">
          {['ok', 'warn', 'err', 'info'].map((role) => <div className={`note note-${role}`} key={role}><p className="note-title">{role === 'warn' ? <TriangleAlert aria-hidden="true" /> : role === 'err' ? <CloudOff aria-hidden="true" /> : role === 'info' ? <Info aria-hidden="true" /> : <CircleCheck aria-hidden="true" />}{role === 'ok' ? 'All checks pass' : role === 'warn' ? 'Bring the tablet back' : role === 'err' ? 'Wait for the server' : 'Preview your change'}</p><p className="t-body">Your wall stays visible while you review the next step.</p></div>)}
        </div>
      </section>
      <ModalDialog open={overlay === 'confirm'} onOpenChange={(open) => { if (!open) setOverlay('none'); }} title="Clear wall?"
        onCancel={(event) => { if (guarded) { event.preventDefault(); setCancelled(true); } }}>
        <p className="t-body">Remove every tablet from the wall layout?</p>
        <Label className="mt-4 flex items-center gap-3"><Switch name="guard" checked={guarded} onChange={(event) => setGuarded(event.target.checked)} />Protect unsaved changes</Label>
        <p className="t-caption mt-2" role="status">{cancelled ? 'Review your unsaved changes before closing.' : ''}</p>
        <form method="dialog" className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" autoFocus onClick={(event) => event.currentTarget.closest('dialog')?.requestClose()}>Cancel</Button>
          <Button variant="danger-solid" type="submit" value="clear" onClick={() => setMessage('Wall cleared in the gallery.')}>Clear wall</Button>
        </form>
      </ModalDialog>
      <SideSheet open={overlay === 'sheet'} onOpenChange={(open) => { if (!open) setOverlay('none'); }} title="Server">
        <Tabs defaultValue="health"><TabsList aria-label="Server sections"><TabsTrigger value="health" autoFocus>Health</TabsTrigger><TabsTrigger value="data">Data</TabsTrigger></TabsList>
          <TabsContent value="health"><StatusBadge status="ok" label="All checks pass" /><p className="t-body mt-4">The server is ready for the wall.</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Tooltip><TooltipTrigger asChild><Button variant="secondary">Download report</Button></TooltipTrigger><TooltipContent>Download the server diagnostics.</TooltipContent></Tooltip>
              <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost">Sheet actions</Button></DropdownMenuTrigger><DropdownMenuContent><DropdownMenuItem onSelect={() => setMessage('Report selected.')}>Select report</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
            </div>
          </TabsContent>
          <TabsContent value="data"><p className="t-body">Download a backup before clearing the wall.</p></TabsContent>
        </Tabs>
      </SideSheet>
    </main>
  </TooltipProvider>;
}
