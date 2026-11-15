import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import type { ComponentProps } from 'react';
import { clsx } from 'clsx';
import { Check } from 'lucide-react';

export function DropdownMenu({ modal = false, ...props }: ComponentProps<typeof DropdownMenuPrimitive.Root>) {
  return <DropdownMenuPrimitive.Root modal={modal} {...props} />;
}
export const DropdownMenuPortal = DropdownMenuPrimitive.Portal;
export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;
export const DropdownMenuGroup = DropdownMenuPrimitive.Group;
export function DropdownMenuContent({ className, sideOffset = 8, ...props }: ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return <DropdownMenuPrimitive.Content sideOffset={sideOffset}
    className={clsx('popover', className)} {...props} />;
}
export function DropdownMenuItem({ className, variant, ...props }: ComponentProps<typeof DropdownMenuPrimitive.Item> & { variant?: 'danger' }) {
  return <DropdownMenuPrimitive.Item data-variant={variant} className={clsx('menu-item', className)} {...props} />;
}
export function DropdownMenuLabel({ className, ...props }: ComponentProps<typeof DropdownMenuPrimitive.Label>) {
  return <DropdownMenuPrimitive.Label className={clsx('menu-label', className)} {...props} />;
}
export function DropdownMenuCheckboxItem({ className, children, ...props }: ComponentProps<typeof DropdownMenuPrimitive.CheckboxItem>) {
  return <DropdownMenuPrimitive.CheckboxItem className={clsx('menu-item', className)} {...props}>
    <span className="size-4"><DropdownMenuPrimitive.ItemIndicator><Check aria-hidden="true" /></DropdownMenuPrimitive.ItemIndicator></span>
    {children}
  </DropdownMenuPrimitive.CheckboxItem>;
}
