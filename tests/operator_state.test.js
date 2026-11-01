"use strict";
const assert = require("node:assert/strict");
const model = require("../frontend/controller/operator-state.js");
const tabletView = require("../frontend/client/view.js");
const now = Date.parse("2026-11-01T12:00:00Z");
const token = { connection_id: "socket-1", generation: "g", revision: 8, render_seq: 4, mapping_revision: "mapping", asset: "image" };
function fixture() {
    return { generation: "g", revision: 8, layout: { kind: "physical", bounds: { x: -10, y: 20, width: 400, height: 100 },
        slots: { tablet: { participating: true } } }, scene: { content: { type: "image", asset: "image" } },
        runtime: { observed_at: new Date(now).toISOString(), presentation: { owner: "static" }, devices: { tablet: { online: true, protocol: 3,
            caps: ["image", "render_ack"], mapping: { status: "ready" }, render: { status: "displayed", expected_token: { ...token }, token: { ...token }, age_ms: 0 } } } } };
}
const logical = { width: 320, height: 60, placements: { one: { x: 0, y: 0, w: 80, h: 60 } } };
const draft = model.layoutDraft(logical);
assert.equal(draft.kind, "logical");
assert.equal(draft.width, 320);
assert.equal(draft.bounds, undefined, "logical dimensions must never seed millimetre bounds");
draft.placements.one.w = 40;
assert.equal(logical.placements.one.w, 80, "draft must not mutate committed geometry");
assert.throws(() => model.layoutDraft({ kind: "future" }), /Unsupported layout/);
assert.deepEqual(model.bounds(draft), { x: 0, y: 0, width: 320, height: 60 });
assert.deepEqual(model.fitTransform({ kind: "logical", width: 400, height: 100 }, { intrinsicWidth: 100, intrinsicHeight: 100, fit: "contain" }),
    { x: 150, y: 0, width: 100, height: 100, scale: 1, cropX: 0, cropY: 0 });
assert.deepEqual(model.fitTransform(fixture().layout, { intrinsicWidth: 100, intrinsicHeight: 100, fit: "cover" }),
    { x: -10, y: -130, width: 400, height: 400, scale: 4, cropX: 0, cropY: 0.75 });
for (const invalid of [0, NaN, Infinity, true, "100"]) assert.equal(model.fitTransform(draft, { intrinsicWidth: invalid, intrinsicHeight: 100 }), null);
for (const layout of [draft, fixture().layout]) {
    const b = model.bounds(layout);
    for (const [width, height] of [[2000, 745], [100, 100], [900, 1600]]) for (const fit of ["cover", "contain"]) {
        const transform = model.fitTransform(layout, { intrinsicWidth: width, intrinsicHeight: height, fit });
        assert.deepEqual([transform.width, 0, 0, transform.height, transform.x, transform.y],
            tabletView.fitMatrix([b.x, b.y, b.width, b.height], width, height, fit), "operator and tablet use the same global source transform");
    }
}
const roster = { a: { number: 4 }, b: { number: 1 }, c: { label: "alpha" }, d: { label: "Zulu" }, e: { number: null, label: "Beta" } };
assert.deepEqual(Object.keys(roster).sort((a, b) => model.compareIds(roster, {}, a, b)), ["b", "a", "c", "e", "d"]);
assert.equal(model.tabletState(fixture(), "tablet", now).showing, true);
assert.deepEqual(model.aggregate(fixture(), now).total, 1);
for (const key of Object.keys(token)) {
    const config = fixture(); config.runtime.devices.tablet.render.token[key] = "obsolete";
    assert.equal(model.tabletState(config, "tablet", now).showing, false, "old " + key + " must never count as showing");
}
for (const status of ["blocked", "loading", "failed", "hidden", "stale", "unsupported", "unknown", "painted", "future"]) {
    const config = fixture(); config.runtime.devices.tablet.render.status = status;
    assert.equal(model.tabletState(config, "tablet", now).showing, false, status);
}
for (const status of ["needs_calibration", "viewport_mismatch", "zoom_changed", "unsupported_content", "unsupported_client"]) {
    const config = fixture(); config.runtime.devices.tablet.mapping.status = status;
    assert.equal(model.tabletState(config, "tablet", now).status, status);
}
const wrongPins = fixture(); wrongPins.runtime.devices.tablet.mapping.profile_revision = 4;
assert.equal(model.tabletState(wrongPins, "tablet", now).showing, false, "mapping evidence must describe the slot's pinned profile");
for (const protocol of [1, 2, null]) {
    const config = fixture(); config.runtime.devices.tablet.protocol = protocol;
    assert.equal(model.tabletState(config, "tablet", now).status, "unknown");
}
for (const status of ["queued", "delivered", "shown"]) {
    const config = fixture(); config.runtime.devices.tablet.identify = { status };
    assert.equal(model.tabletState(config, "tablet", now).status, "identifying");
}
const expired = fixture();
assert.equal(model.tabletState(expired, "tablet", now + 15001).status, "stale", "cached age grows after a snapshot");
expired.runtime.devices.tablet.online = false;
assert.equal(model.tabletState(expired, "tablet", now).status, "offline");
assert.equal(model.aggregate(expired, now).total, 1, "offline reservations remain in the denominator");
expired.layout.slots.tablet.participating = false;
assert.equal(model.aggregate(expired, now).total, 0);
assert.equal(model.tabletState(expired, "tablet", now).status, "excluded");
const noAck = fixture(); noAck.runtime.devices.tablet.caps = ["image"];
assert.equal(model.tabletState(noAck, "tablet", now).showing, false, "online and image capable does not prove a paint");
const playback = fixture(); playback.runtime.presentation.owner = "playback";
assert.equal(model.tabletState(playback, "tablet", now).status, "playback");
const fence = model.readFence();
const slow = fence.start(); fence.event(); assert.equal(fence.accept(slow), false, "snapshot wins over a slower HTTP read");
const first = fence.start(), second = fence.start(); assert.equal(fence.accept(second), true); assert.equal(fence.accept(first), false, "older requests cannot replace a newer accepted response");
console.log("Operator tagged layout, fit, evidence, ordering and read-fence contracts passed");
