import { useEffect, useId, useRef } from 'react';
import type { ComponentProps, ReactNode } from 'react';
import { clsx } from 'clsx';
import { X } from 'lucide-react';
import { Button } from './Button';

export type ModalDialogProps = Omit<ComponentProps<'dialog'>, 'open' | 'title' | 'children' | 'ref'> & {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
};

export function ModalDialog({ open, onOpenChange, title, children, className, onClose, ...props }: ModalDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return <dialog {...props} ref={ref} aria-labelledby={titleId} className={clsx('modal', className)}
    onClose={(event) => {
      onClose?.(event);
      event.currentTarget.returnValue = '';
      onOpenChange(false);
    }}>
    <header className="dialog-header">
      <h2 id={titleId} className="t-title">{title}</h2>
      <Button variant="ghost" size="icon" aria-label={`Close ${title}`} onClick={() => ref.current?.requestClose()}>
        <X aria-hidden="true" />
      </Button>
    </header>
    <div className="dialog-body">{children}</div>
  </dialog>;
}
