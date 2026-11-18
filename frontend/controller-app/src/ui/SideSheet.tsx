import { clsx } from 'clsx';
import { ModalDialog } from './ModalDialog';
import type { ModalDialogProps } from './ModalDialog';

export function SideSheet({ className, ...props }: ModalDialogProps) {
  return <ModalDialog className={clsx('sheet', className)} {...props} />;
}
