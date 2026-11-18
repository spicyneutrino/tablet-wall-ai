import { useCallback, useId } from 'react';
import type { ComponentProps } from 'react';
import { cva } from 'class-variance-authority';
import { clsx } from 'clsx';
import { LoaderCircle } from 'lucide-react';

const buttonVariants = cva('btn', {
  variants: {
    variant: {
      primary: 'btn-primary', secondary: 'btn-tonal', ghost: 'btn-ghost',
      danger: 'btn-danger', 'danger-solid': 'btn-danger-solid',
    },
    size: { default: '', sm: 'btn-sm', lg: 'btn-lg', icon: 'btn-icon' },
  },
  defaultVariants: { variant: 'primary', size: 'default' },
});

type ButtonProps = Omit<ComponentProps<'button'>, 'disabled'> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'danger-solid';
  size?: 'default' | 'sm' | 'lg' | 'icon';
} & ({ busy: true; busyLabel: string } | { busy?: false; busyLabel?: string }) & ({ disabled: true; disabledReason: string } | { disabled?: false; disabledReason?: never });

export function Button({ variant, size, busy, busyLabel, disabled, disabledReason, children,
  className, onClick, autoFocus, ref, 'aria-describedby': describedBy, ...props }: ButtonProps) {
  const reasonId = useId();
  const controlRef = useCallback((node: HTMLButtonElement | null) => {
    if (node) node.autofocus = !!autoFocus;
    if (typeof ref === 'function') return ref(node);
    if (ref) ref.current = node;
  }, [autoFocus, ref]);
  const blocked = disabled || !!busy || props['aria-disabled'] === true || props['aria-disabled'] === 'true';
  const button = (
    <button type="button" {...props} ref={controlRef} autoFocus={autoFocus} disabled={disabled}
      aria-disabled={blocked || undefined} aria-busy={!!busy || undefined}
      aria-describedby={clsx(describedBy, disabledReason && reasonId) || undefined}
      className={clsx(buttonVariants({ variant, size }), busy && 'is-busy', className)}
      onClick={(event) => {
        if (blocked) { event.preventDefault(); return; }
        onClick?.(event);
      }}>
      {busyLabel ? <span className="btn-content">
        <span className="btn-rest" aria-hidden={busy || undefined}>{children}</span>
        <span className="btn-busy" aria-hidden={!busy || undefined}><LoaderCircle className="spin" aria-hidden="true" />{busyLabel}</span>
      </span> : children}
    </button>
  );
  return disabledReason ? <span className="btn-reason">{button}
    <span className="t-caption" id={reasonId}>{disabledReason}</span>
  </span> : button;
}
