import { useId } from 'react';
import type { ReactNode } from 'react';
import { Label } from './Label';

type FieldControl = { id: string; 'aria-describedby'?: string; 'aria-invalid'?: true };
type FieldProps = {
  id?: string;
  label: string;
  hint?: string;
  error?: string;
  children: (props: FieldControl) => ReactNode;
};

export function Field({ id, label, hint, error, children }: FieldProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const hintId = `${controlId}-hint`;
  const errorId = `${controlId}-error`;
  const description = [hint && hintId, error && errorId].filter(Boolean).join(' ') || undefined;
  return <div className="field">
    <Label htmlFor={controlId}>{label}</Label>
    {children({ id: controlId, 'aria-describedby': description, 'aria-invalid': error ? true : undefined })}
    {hint ? <span id={hintId} className="t-caption">{hint}</span> : null}
    <span id={errorId} className="t-caption field-error" aria-live="polite">{error}</span>
  </div>;
}
