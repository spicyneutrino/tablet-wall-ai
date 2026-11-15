// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import { useState } from 'react';
import { Button } from './Button';
import { Field } from './Field';
import { Input } from './Input';
import { StatusBadge } from './StatusBadge';
import { ModalDialog } from './ModalDialog';
import { SideSheet } from './SideSheet';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './Tabs';
import { ToggleGroup, ToggleGroupItem } from './ToggleGroup';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal');
  Reflect.deleteProperty(HTMLDialogElement.prototype, 'close');
});

it('a disabled Button exposes its visible reason through aria-describedby', async () => {
  const clicked = vi.fn();
  render(<><p id="existing">Preview required.</p><Button disabled disabledReason="Pick a source to preview it."
    aria-describedby="existing" onClick={clicked}>Show on wall</Button></>);
  const button = screen.getByRole('button', { name: 'Show on wall' });
  expect(button).toBeDisabled();
  expect(button).toHaveAccessibleDescription('Preview required. Pick a source to preview it.');
  expect(screen.getByText('Pick a source to preview it.')).toBeVisible();
  await userEvent.click(button);
  expect(clicked).not.toHaveBeenCalled();
});

it('a busy Button keeps its action and blocks pointer and keyboard activation', async () => {
  const clicked = vi.fn();
  render(<Button busy busyLabel="Showing…" onClick={clicked}>Show on wall</Button>);
  const button = screen.getByRole('button', { name: 'Showing…' });
  expect(button).toHaveAttribute('aria-busy', 'true');
  expect(button).toHaveAttribute('aria-disabled', 'true');
  expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  await userEvent.click(button);
  button.focus();
  await userEvent.keyboard('{Enter} ');
  expect(clicked).not.toHaveBeenCalled();
});

it('a Field associates its persistent label, hint and error with its control', () => {
  render(<Field label="Width" hint="Measure in millimetres." error="Use a number above 0.">
    {(props) => <Input {...props} defaultValue="-4" />}
  </Field>);
  const input = screen.getByRole('textbox', { name: 'Width' });
  expect(input).toHaveAttribute('aria-invalid', 'true');
  expect(input).toHaveAccessibleDescription('Measure in millimetres. Use a number above 0.');
});

describe('StatusBadge', () => {
  it.each([
    ['ok', 'Showing'], ['warn', 'Offline'], ['error', 'Server unreachable'],
    ['connecting', 'Connecting…'], ['unknown', 'Unknown'],
  ] satisfies [Parameters<typeof StatusBadge>[0]['status'], string][])
  ('renders an icon and a word for %s', (status, label) => {
    render(<StatusBadge status={status} />);
    const badge = screen.getByText(label);
    expect(badge).toBeVisible();
    expect(badge.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
  it('uses a real button when the status opens its cause', async () => {
    const clicked = vi.fn();
    render(<StatusBadge status="warn" label="3 of 4 showing" onClick={clicked} />);
    await userEvent.click(screen.getByRole('button', { name: '3 of 4 showing' }));
    expect(clicked).toHaveBeenCalledOnce();
  });
});

it('tabs support arrow-key navigation and expose the matching panel', async () => {
  render(<Tabs defaultValue="preview"><TabsList aria-label="Views">
    <TabsTrigger value="preview">Preview</TabsTrigger><TabsTrigger value="wall">On wall</TabsTrigger>
  </TabsList><TabsContent value="preview">Preview content</TabsContent><TabsContent value="wall">Wall content</TabsContent></Tabs>);
  screen.getByRole('tab', { name: 'Preview' }).focus();
  await userEvent.keyboard('{ArrowRight}');
  await waitFor(() => expect(screen.getByRole('tab', { name: 'On wall' })).toHaveAttribute('aria-selected', 'true'));
  expect(screen.getByRole('tabpanel')).toHaveTextContent('Wall content');
});

it('toggle groups expose selection and support keyboard activation', async () => {
  render(<ToggleGroup type="multiple" aria-label="Tools"><ToggleGroupItem value="snap">Snap</ToggleGroupItem></ToggleGroup>);
  const toggle = screen.getByRole('button', { name: 'Snap' });
  toggle.focus();
  await userEvent.keyboard(' ');
  expect(toggle).toHaveAttribute('aria-pressed', 'true');
});

function DialogFixture({ sheet = false }: { sheet?: boolean }) {
  const [open, setOpen] = useState(false);
  const Dialog = sheet ? SideSheet : ModalDialog;
  return <><Button onClick={() => setOpen(true)}>Open</Button>
    <Dialog title="Clear wall?" open={open} onOpenChange={setOpen} onCancel={(event) => event.preventDefault()}>
      <Button variant="ghost" autoFocus onClick={(event) => event.currentTarget.closest('dialog')?.close()}>Cancel</Button>
    </Dialog></>;
}

function installNativeDialogShim() {
  let opener: Element | null = null;
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: vi.fn(function (this: HTMLDialogElement) {
    opener = document.activeElement;
    this.setAttribute('open', '');
    this.querySelector<HTMLElement>('[autofocus]')?.focus();
  }) });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: vi.fn(function (this: HTMLDialogElement) {
    this.removeAttribute('open');
    if (opener instanceof HTMLElement) opener.focus();
    this.dispatchEvent(new Event('close'));
  }) });
}

it.each([false, true])('ModalDialog / SideSheet preserves native focus return to its opener (sheet=%s)', async (sheet) => {
  installNativeDialogShim();
  render(<DialogFixture sheet={sheet} />);
  const opener = screen.getByRole('button', { name: 'Open' });
  await userEvent.click(opener);
  const dialog = screen.getByRole('dialog', { name: 'Clear wall?' });
  expect(dialog).not.toHaveAttribute('role');
  expect(dialog).not.toHaveAttribute('aria-modal');
  expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledOnce();
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(opener).toHaveFocus();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('keeps unsaved-change guards on native cancel events', async () => {
  installNativeDialogShim();
  render(<DialogFixture />);
  await userEvent.click(screen.getByRole('button', { name: 'Open' }));
  const dialog = screen.getByRole('dialog');
  expect(fireEvent(dialog, new Event('cancel', { cancelable: true }))).toBe(false);
  expect(dialog).toHaveAttribute('open');
});
