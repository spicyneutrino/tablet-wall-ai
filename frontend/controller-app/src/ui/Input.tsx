import type { ComponentProps } from 'react';
import { clsx } from 'clsx';
import { ChevronDown } from 'lucide-react';

export function Input({ className, type = 'text', ...props }: ComponentProps<'input'>) {
  return <input type={type} className={clsx('input', className)} {...props} />;
}
export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return <textarea className={clsx('input', className)} {...props} />;
}
export function Select({ className, ...props }: ComponentProps<'select'>) {
  return <span className="select-wrap"><select className={clsx('input', className)} {...props} />
    <ChevronDown aria-hidden="true" /></span>;
}
export function Switch({ className, ...props }: Omit<ComponentProps<'input'>, 'type' | 'role'>) {
  return <input type="checkbox" role="switch" className={clsx('switch', className)} {...props} />;
}
