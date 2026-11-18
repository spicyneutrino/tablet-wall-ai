import { z } from 'zod';

export const ValidationErrorSchema = z.looseObject({ loc: z.array(z.union([z.string(), z.number()])).optional(), msg: z.string(), type: z.string().optional() });
export const ErrorDetailSchema = z.union([z.string(), z.array(ValidationErrorSchema), z.looseObject({ code: z.string(), message: z.string() })]);
export const ErrorBodySchema = z.looseObject({ detail: ErrorDetailSchema });
export type ValidationError = z.infer<typeof ValidationErrorSchema>;
export type ErrorDetail = z.infer<typeof ErrorDetailSchema>;
export type ErrorBody = z.infer<typeof ErrorBodySchema>;

export function errorMessage(detail: unknown, labelFor: (id: string) => string = () => 'Unregistered tablet'): string {
  const parsed = ErrorDetailSchema.safeParse(detail);
  if (!parsed.success) return 'The server returned an unreadable error.';
  const value = parsed.data;
  const message = typeof value === 'string' ? value : Array.isArray(value) ? value.map((error) => error.msg).join('; ') : value.message;
  return message.replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, labelFor);
}
