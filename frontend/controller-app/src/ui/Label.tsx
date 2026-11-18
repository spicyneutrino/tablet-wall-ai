import type { ComponentProps } from 'react';
import { clsx } from 'clsx';

export function Label({ className, ...props }: ComponentProps<'label'>) {
  return <label className={clsx('t-label', className)} {...props} />;
}
