import { expect, it } from 'vitest';
import { A, B } from '../../session/testFixtures';
import { ConfigEtagSchema } from '../../api/etag';
import { createForm, formKey, formsDirty, tabletFormReducer } from './tabletForms';
const etag = ConfigEtagSchema.parse;
it('review carries the new revision without replacing exact unsaved fields; discard invalidates old reviews', () => {
  let form = createForm(A, 'profile', { width: '100', _revision: 1 }, etag('base'));
  form = tabletFormReducer(form, { type: 'edit', values: { width: '101', _revision: 1 }, etag: etag('base') });
  form = tabletFormReducer(form, { type: 'review', values: { width: '102', _revision: 2 }, etag: etag('remote'), version: form.version });
  expect(form.values).toEqual({ width: '101', _revision: 2 });
  const discarded = tabletFormReducer(form, { type: 'discard', values: form.baseline, etag: etag('remote') });
  expect(discarded).toMatchObject({ dirty: false, conflict: false, values: form.baseline, version: form.version + 1 });
});

it('ports create dirty queries across devices and form groups', () => {
  const name = createForm(A, 'name', { name: 'A' }, etag('base'));
  const profile = tabletFormReducer(createForm(A, 'profile', { width: 100 }, etag('base')),
    { type: 'edit', values: { width: 101 }, etag: etag('base') });
  const forms = { [formKey(A, 'name')]: name, [formKey(A, 'profile')]: profile };
  expect(formsDirty(forms, undefined, 'profile')).toBe(true);
  expect(formsDirty(forms, undefined, 'name')).toBe(false);
  expect(formsDirty(forms, A)).toBe(true);
  expect(formsDirty(forms, B)).toBe(false);
});
