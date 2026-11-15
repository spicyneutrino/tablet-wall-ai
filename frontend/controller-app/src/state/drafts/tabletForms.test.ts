import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
import { A, B } from '../../session/testFixtures';
import { ConfigEtagSchema } from '../../api/etag';
import { createForm, formKey, formsDirty, tabletFormReducer } from './tabletForms';
import type { FormValues, FormGroup } from './tabletForms';
const require = createRequire(import.meta.url);
const legacy = require('../../../../controller/operator-forms.js') as { create(): {
  observe(id: string, group: string, values: FormValues, etag: string): unknown;
  edit(id: string, group: string, values: FormValues, etag: string): unknown;
  get(id: string, group: string): { version: number; values: FormValues };
  saved(id: string, group: string, version: number, values: FormValues, etag: string): void;
  review(id: string, group: string, version: number, values: FormValues, etag: string): boolean;
} };
const etag = ConfigEtagSchema.parse;
it.each<FormGroup>(['name', 'model', 'profile', 'calibration'])('ports create assertions for keyed %s drafts against legacy', group => {
  const old = legacy.create();
  let form = createForm(A, group, { field: 'baseline' }, etag('original'));
  old.observe(A, group, { field: 'baseline' }, 'original');
  form = tabletFormReducer(form, { type: 'edit', values: { field: 'exact unsaved value' }, etag: etag('original') });
  old.edit(A, group, { field: 'exact unsaved value' }, 'original');
  form = tabletFormReducer(form, { type: 'observe', values: { field: 'baseline' }, etag: etag('runtime') });
  expect(form).toEqual(old.observe(A, group, { field: 'baseline' }, 'runtime'));
  form = tabletFormReducer(form, { type: 'observe', values: { field: 'remote changed' }, etag: etag('changed') });
  expect(form).toEqual(old.observe(A, group, { field: 'remote changed' }, 'changed'));
  expect(form.values.field).toBe('exact unsaved value'); expect(form.conflict).toBe(true); expect(form.baseEtag).toBe('original');
  const version = form.version;
  expect(tabletFormReducer(form, { type: 'review', version: version - 1, values: { field: 'remote' }, etag: etag('fresh') })).toBe(form);
  expect(old.review(A, group, version - 1, { field: 'remote' }, 'fresh')).toBe(false);
  form = tabletFormReducer(form, { type: 'review', version, values: { field: 'remote' }, etag: etag('reviewed') });
  expect(old.review(A, group, version, { field: 'remote' }, 'reviewed')).toBe(true);
  expect(form).toEqual(old.get(A, group));
  const submitted = form;
  form = tabletFormReducer(form, { type: 'edit', values: { field: 'newer' }, etag: etag('reviewed') });
  old.edit(A, group, { field: 'newer' }, 'reviewed');
  const other = createForm(B, group, { field: 'B' }, etag('original'));
  form = tabletFormReducer(form, { type: 'saved', version: submitted.version, values: submitted.values, etag: etag('returned') });
  old.saved(A, group, submitted.version, submitted.values, 'returned');
  expect(form).toEqual(old.get(A, group)); expect(form.dirty).toBe(true); expect(other.values.field).toBe('B');
});
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
