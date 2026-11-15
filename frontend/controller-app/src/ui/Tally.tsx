import type { ComponentProps } from 'react';
import { clsx } from 'clsx';

export function Tally({ kind, className, ...props }: Omit<ComponentProps<'span'>, 'children'> & { kind: 'preview' | 'live' }) {
  return <span className={clsx('tally', kind === 'preview' ? 'tally-preview' : 'tally-live', className)} {...props}>
    {kind === 'preview' ? 'Preview' : 'On wall'}
  </span>;
}
