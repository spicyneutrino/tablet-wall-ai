"use strict";
(function (root) {
    function create() {
        const forms = new Map();
        const copy = value => JSON.parse(JSON.stringify(value));
        const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
        const key = (id, group) => JSON.stringify([id, group]);
        return {
            observe(id, group, values, etag) {
                const name = key(id, group), old = forms.get(name);
                if (!old || !old.dirty) {
                    const next = { id, group, baseline: copy(values), values: copy(values), baseEtag: etag, version: old ? old.version : 0, dirty: false, conflict: false };
                    forms.set(name, next); return copy(next);
                }
                old.conflict = !same(values, old.baseline);
                return copy(old);
            },
            edit(id, group, values, etag) {
                const form = forms.get(key(id, group));
                if (!form) throw new Error("Observe the form before editing.");
                if (!same(form.values, values)) {
                    if (!form.dirty) form.baseEtag = etag;
                    form.values = copy(values); form.version += 1;
                    form.dirty = !same(form.values, form.baseline);
                }
                return copy(form);
            },
            get(id, group) { const form = forms.get(key(id, group)); return form ? copy(form) : null; },
            saved(id, group, version, values, etag) {
                const form = forms.get(key(id, group));
                if (!form) return;
                form.baseline = copy(values); form.baseEtag = etag; form.conflict = false;
                if (form.version === version) { form.values = copy(values); form.dirty = false; }
                else form.dirty = !same(form.values, values);
            },
            review(id, group, version, baseline, etag) {
                const form = forms.get(key(id, group));
                if (!form || form.version !== version) return false;
                form.baseline = copy(baseline); form.baseEtag = etag; form.conflict = false;
                if (Object.hasOwn(baseline, "_revision")) form.values._revision = baseline._revision;
                form.version += 1; form.dirty = !same(form.values, form.baseline);
                return true;
            },
            discard(id, group) { const form = forms.get(key(id, group)); if (form) { form.values = copy(form.baseline); form.dirty = false; form.conflict = false; form.version += 1; } },
            dirty(id, group) { return [...forms.values()].some(form => form.dirty && (id === undefined || form.id === id) && (group === undefined || form.group === group)); },
            clear() { forms.clear(); }
        };
    }
    const api = { create };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorForms = api;
}(typeof window !== "undefined" ? window : globalThis));
