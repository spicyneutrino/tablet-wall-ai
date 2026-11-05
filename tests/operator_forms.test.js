"use strict";
const assert = require("node:assert/strict");
const forms = require("../frontend/controller/operator-forms.js").create();
forms.observe("A", "name", { name: "Tablet 1" }, "original");
forms.edit("A", "name", { name: "Lobby left" }, "original");
forms.observe("B", "name", { name: "Tablet 2" }, "original");
assert.equal(forms.observe("A", "name", { name: "Tablet 1" }, "heartbeat").values.name, "Lobby left");
const submitted = forms.get("A", "name");
forms.edit("A", "name", { name: "Lobby left newer" }, "original");
forms.edit("B", "name", { name: "Keep B edit" }, "original");
forms.saved("A", "name", submitted.version, submitted.values, "returned");
assert.equal(forms.get("A", "name").dirty, true, "late A save cannot clear a newer A edit");
assert.equal(forms.get("B", "name").values.name, "Keep B edit", "A result cannot change selected B");
for (const group of ["profile", "calibration", "model"]) {
    forms.observe("A", group, { field: "baseline" }, "original");
    forms.edit("A", group, { field: "exact unsaved value" }, "original");
    assert.equal(forms.observe("A", group, { field: "baseline" }, "runtime").values.field, "exact unsaved value");
    assert.equal(forms.observe("A", group, { field: "remote changed" }, "changed").conflict, true);
    assert.equal(forms.get("A", group).baseEtag, "original");
}
console.log("Keyed names, measurements, model choices, conflicts and edit-version saves passed");

const beforeReview = forms.get("A", "profile");
assert.equal(forms.review("A", "profile", beforeReview.version - 1, { field: "remote" }, "fresh"), false, "an old comparison cannot authorize newer input");
assert.equal(forms.review("A", "profile", beforeReview.version, { field: "remote" }, "reviewed"), true);
assert.equal(forms.get("A", "profile").values.field, "exact unsaved value");
assert.equal(forms.get("A", "profile").baseEtag, "reviewed");

const grouped = require("../frontend/controller/operator-forms.js").create();
grouped.observe("A", "name", { name: "A" }, "base");
grouped.observe("A", "profile", { width: 100 }, "base");
grouped.edit("A", "profile", { width: 101 }, "base");
assert.equal(grouped.dirty(undefined, "profile"), true, "Settings can find measurement edits across tablets");
assert.equal(grouped.dirty(undefined, "name"), false, "measurement edits do not mark tablet naming dirty");
assert.equal(grouped.dirty("A"), true, "existing all-group guards still cover the tablet");
