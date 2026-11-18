import { CircleCheck, TriangleAlert, CloudOff, LoaderCircle, CircleHelp } from 'lucide-react';
import type { ComponentProps } from 'react';
import { clsx } from 'clsx';

const statuses = {
  ok: { icon: CircleCheck, label: 'Showing', className: 'chip-ok' },
  warn: { icon: TriangleAlert, label: 'Offline', className: 'chip-warn' },
  error: { icon: CloudOff, label: 'Server unreachable', className: 'chip-err' },
  connecting: { icon: LoaderCircle, label: 'Connecting…', className: 'chip-neutral spin-chip' },
  unknown: { icon: CircleHelp, label: 'Unknown', className: 'chip-neutral' },
};

type StatusBadgeProps = { status: keyof typeof statuses; label?: string; className?: string } & (
  { onClick: NonNullable<ComponentProps<'button'>['onClick']>; 'aria-describedby'?: string } |
  { onClick?: never; 'aria-describedby'?: string }
);

export function StatusBadge({ status, label, className, ...props }: StatusBadgeProps) {
  const state = statuses[status];
  const Icon = state.icon;
  const content = <><Icon aria-hidden="true" />{label || state.label}</>;
  const classes = clsx('chip', state.className, className);
  return props.onClick ? <button type="button" className={classes} {...props}>{content}</button>
    : <span className={classes} aria-describedby={props['aria-describedby']}>{content}</span>;
}
