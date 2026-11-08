"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const { createPayloads, liveViewportText, updateLiveViewport } = require("../frontend/controller/operator-measurements.js");

function form(overrides = {}, markInvalid) {
    const values = {
        profileActiveWidth: "200.5", profileActiveHeight: "120", profileBezelLeft: "0", profileBezelTop: "1",
        profileBezelRight: "2", profileBezelBottom: "3", profilePixelWidth: "", profilePixelHeight: "",
        profileLabel: " Tablet A ", profileProvenance: " manual ", calProfileRevision: "2",
        calViewportWidth: "800", calViewportHeight: "600", calDpr: "2", calOrientation: "90", calMode: "tab",
        calQuarterTurn: "1", calOffsetX: "-1.5", calOffsetY: "0", calMmCssX: "0.25", calMmCssY: "0.2",
        calAnchorEdge: "top-left", calUncertainty: "0", calMethod: " manual ", ...overrides
    };
    const fields = Object.fromEntries(Object.entries(values).map(([id, value]) => [id, { id, value }]));
    const num = value => value.trim() !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
    return createPayloads({ fields, num, markInvalid });
}

test("measurement field state builds profile payloads without a DOM", () => {
    assert.deepEqual(form().buildProfileBody(), {
        active_width_mm: 200.5, active_height_mm: 120, bezels: { left: 0, top: 1, right: 2, bottom: 3 },
        panel_pixels: null, label: "Tablet A", provenance: "manual"
    });
    assert.deepEqual(form({ profilePixelWidth: "2048", profilePixelHeight: "1536" }).buildProfileBody().panel_pixels,
        { width: 2048, height: 1536 });
    for (const value of ["", " ", "0", "-1", "Infinity", "NaN"]) {
        assert.throws(() => form({ profileActiveWidth: value }).buildProfileBody(), /Active width must be a positive number\./);
    }
    assert.throws(() => form({ profileBezelLeft: "-1" }).buildProfileBody(), /Left bezel must be a non-negative number\./);
    assert.throws(() => form({ profileLabel: " " }).buildProfileBody(), /Label must be 1 to 80 characters\./);
    assert.throws(() => form({ profileProvenance: "a".repeat(41) }).buildProfileBody(), /Provenance must be 1 to 40 characters\./);
});

test("profile pixel validation retains field marking and first-error order", () => {
    const marked = [];
    assert.throws(() => form({ profilePixelWidth: "3.5", profilePixelHeight: "4", profileActiveWidth: "" },
        (field, invalid) => marked.push([field.id, invalid])).buildProfileBody(), /Panel pixel dimensions must be whole numbers\./);
    assert.deepEqual(marked, [["profilePixelWidth", false], ["profilePixelHeight", false],
        ["profilePixelWidth", true], ["profilePixelHeight", true]]);
    assert.throws(() => form({ profilePixelWidth: "4" }).buildProfileBody(), /Panel pixel height must be a positive number\./);
});

test("calibration payload retains independent axes, offsets and ruler guard", () => {
    const expected = {
        profile_revision: 2, viewport_width: 800, viewport_height: 600, dpr: 2, orientation: 90, mode: "tab",
        quarter_turn: 1, panel_offset_mm: [-1.5, 0], mm_per_css: [0.25, 0.2], anchor_edge: "top-left",
        uncertainty_mm: 0, method: "manual"
    };
    assert.deepEqual(form().buildCalibrationBody(), expected);
    assert.deepEqual(form({ calMethod: " ruler-measured " }).buildCalibrationBody(),
        { ...expected, method: "ruler-measured", viewport_guard: true });
    for (const orientation of ["0", "90", "180", "270"]) {
        for (const mode of ["tab", "fullscreen", "standalone"]) {
            assert.equal(form({ calOrientation: orientation, calMode: mode }).buildCalibrationBody().orientation, Number(orientation));
        }
    }
});

test("identical live viewport text is written once per distinct viewport", () => {
    let text = "", writes = 0;
    const node = {
        get textContent() { return text; },
        set textContent(value) { text = String(value); writes += 1; }
    };
    const first = { width: 800, height: 600, dpr: 2, orientation: 90, mode: "tab" };
    updateLiveViewport(node, first);
    updateLiveViewport(node, { ...first });
    assert.equal(writes, 1, "an unchanged routine render must not rewrite the live region");
    assert.equal(node.textContent, "Selected tablet: 800 × 600 CSS px · DPR 2 · 90° · tab");
    updateLiveViewport(node, { ...first, width: 801 });
    assert.equal(writes, 2, "changed evidence still updates");
    assert.match(liveViewportText(null), /Waiting for the selected tablet/);
});

test("calibration validation rejects invalid form state with the existing messages", () => {
    for (const [field, value, message] of [
        ["calOrientation", "", "Choose the tablet orientation and mode."],
        ["calMode", "other", "Choose the tablet orientation and mode."],
        ["calOrientation", "45", "Orientation must be 0, 90, 180 or 270 degrees."],
        ["calQuarterTurn", "4", "Quarter turn must be 0, 1, 2 or 3."],
        ["calAnchorEdge", "center", "Anchor edge is not supported."],
        ["calProfileRevision", "1.5", "Profile revision must be an integer of at least 1."],
        ["calViewportWidth", "0", "Viewport width must be a positive number."],
        ["calDpr", "Infinity", "Device pixel ratio must be a positive number."],
        ["calOffsetX", "", "Panel offset X must be a number."],
        ["calMmCssY", "0", "mm per CSS pixel Y must be a positive number."],
        ["calUncertainty", "-1", "Uncertainty must be a non-negative number."],
        ["calMethod", "", "Method must be 1 to 80 characters."]
    ]) assert.throws(() => form({ [field]: value }).buildCalibrationBody(), { message });
});
