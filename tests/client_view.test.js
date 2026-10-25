/*
 * Independent checks for the client-side v3 geometry.
 *
 *     node tests/client_view.test.js
 *
 * The shared fixture is data derived by hand; this file recomputes every
 * expected value through frontend/client/view.js and compares them.
 */

"use strict";

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const view = require("../frontend/client/view.js");

const FIXTURES = path.join(
    __dirname,
    "fixtures",
    "geometry",
    "render_cases.json"
);
const CASES = JSON.parse(fs.readFileSync(FIXTURES, "utf8")).cases;
const TOLERANCE = 1e-9;

const tests = [];

function test(name, fn) {
    tests.push({ name, fn });
}

function close(actual, expected, label) {
    if (Array.isArray(expected)) {
        assert.ok(Array.isArray(actual), label + ": expected an array");
        assert.strictEqual(actual.length, expected.length, label + ": length");
        expected.forEach((value, index) => {
            close(actual[index], value, label + "[" + index + "]");
        });
    } else if (expected && typeof expected === "object") {
        assert.ok(actual && typeof actual === "object", label + ": expected an object");
        assert.deepStrictEqual(
            Object.keys(actual).sort(),
            Object.keys(expected).sort(),
            label + ": keys"
        );
        for (const key of Object.keys(expected)) {
            close(actual[key], expected[key], label + "." + key);
        }
    } else {
        assert.strictEqual(typeof actual, "number", label + ": expected a number");
        assert.ok(
            Math.abs(actual - expected) <= TOLERANCE,
            label + ": " + actual + " != " + expected
        );
    }
}

function planFor(entry) {
    return view.normalizedSourceToPanel({
        active_size: entry.active_size,
        bezels: entry.bezels,
        center_mm: entry.center_mm,
        nudge_mm: entry.nudge_mm,
        mount_angle: entry.mount_angle,
        bounds: entry.bounds,
        source_size: entry.source_size,
        fit: entry.fit
    });
}

for (const entry of CASES) {
    test("fixture: " + entry.name, () => {
        const plan = planFor(entry);
        const expected = entry.expected;

        close(plan.body, expected.body, entry.name + " body");
        close(plan.active, expected.active, entry.name + " active");
        close(plan.panel_to_wall, expected.panel_to_wall, entry.name + " panel_to_wall");
        close(
            plan.panel_from_source,
            expected.panel_from_source,
            entry.name + " panel_from_source"
        );

        const calibration = entry.calibration;
        const uCToPanel = view.cssToPanel({
            viewport_width: calibration.viewport_width,
            viewport_height: calibration.viewport_height,
            quarter_turn: calibration.quarter_turn,
            panel_offset_mm: calibration.panel_offset_mm,
            mm_per_css: calibration.mm_per_css
        });
        close(uCToPanel, expected.u_c_to_p, entry.name + " u_c_to_p");

        const components = view.canvasTransformComponents({
            backing: entry.backing,
            rect: entry.rect,
            calibration: calibration,
            panel_from_source: plan.panel_from_source,
            source_size: entry.source_size
        });
        close(components.matrix, expected.canvas, entry.name + " canvas");
        close(components.clip, expected.clip, entry.name + " clip");

        close(
            view.canvasTransform({
                backing: entry.backing,
                rect: entry.rect,
                calibration: calibration,
                panel_from_source: plan.panel_from_source,
                source_size: entry.source_size
            }),
            expected.canvas,
            entry.name + " canvasTransform"
        );

        for (const point of expected.points) {
            close(
                view.apply(components.matrix, point.source),
                point.backing,
                entry.name + " source " + JSON.stringify(point.source)
            );
        }
    });
}

test("every panel_from_source inverts and round-trips three points", () => {
    const probes = [
        [0, 0],
        [0.5, 0.25],
        [1, 1]
    ];
    for (const entry of CASES) {
        const matrix = planFor(entry).panel_from_source;
        const inverted = view.inverse(matrix);
        for (const probe of probes) {
            close(
                view.apply(inverted, view.apply(matrix, probe)),
                probe,
                entry.name + " round trip "
            );
        }
    }
});

test("negative or missing bezels and quarter turn 4 are refused", () => {
    assert.throws(
        () =>
            view.bodyGeometry(100, 60, {
                left: -1,
                top: 0,
                right: 0,
                bottom: 0
            }),
        Error
    );
    assert.throws(
        () => view.bodyGeometry(100, 60, { left: 0, top: 0, right: 0 }),
        Error
    );
    assert.throws(() => view.quarterTurn(4, 100, 100), Error);
});

test("other invalid input is refused", () => {
    assert.throws(() => view.inverse([0, 0, 0, 0, 0, 0]), Error);
    assert.throws(() => view.scale(0, 1), Error);
    assert.throws(() => view.quarterTurn(0, 0, 100), Error);
    assert.throws(() => view.fitMatrix([0, 0, 0, 100], 10, 10, "cover"), Error);
    assert.throws(() => view.fitMatrix([0, 0, 100, 100], 10, 10, "fill"), Error);
    assert.throws(
        () =>
            view.cssToPanel({
                viewport_width: 100,
                viewport_height: 100,
                quarter_turn: 0,
                panel_offset_mm: [0, 0],
                mm_per_css: [0, 1]
            }),
        Error
    );
});

test("cover and contain share the centre but not the extent", () => {
    close(view.fitMatrix([0, 0, 200, 100], 400, 200, "cover"), [200, 0, 0, 100, 0, 0], "cover");
    close(view.fitMatrix([0, 0, 200, 100], 100, 100, "contain"), [100, 0, 0, 100, 50, 0], "contain");
});

/* ------------------------------------------------------------------ */
/* Video drift correction                                             */
/* ------------------------------------------------------------------ */

test("video drift is observed minus target, in both directions", () => {
    assert.strictEqual(view.videoDriftMs(1010, 1000), 10);
    assert.strictEqual(view.videoDriftMs(990, 1000), -10);
    assert.throws(() => view.videoDriftMs("1", 0), Error);
    assert.throws(() => view.videoDriftMs(0, NaN), Error);
});

test("video correction: 50 ms deadband keeps rate 1 and never seeks", () => {
    for (const drift of [0, 25, -25, 50, -50]) {
        const decision = view.videoCorrection({
            driftMs: drift,
            nowMs: 1000,
            lastSeekMs: null,
        });
        assert.deepStrictEqual(
            decision,
            { rate: 1, seek: false },
            "drift " + drift
        );
    }
});

test("video correction: 50..250 ms is proportional rate inside 0.98..1.02", () => {
    const cases = [
        [100, 0.992],
        [-100, 1.008],
        [200, 0.984],
        [-200, 1.016],
        [250, 0.98],
        [-250, 1.02],
    ];
    for (const [drift, rate] of cases) {
        const decision = view.videoCorrection({
            driftMs: drift,
            nowMs: 1000,
            lastSeekMs: null,
        });
        assert.strictEqual(decision.seek, false, "drift " + drift + " seek");
        close(decision.rate, rate, "drift " + drift + " rate");
    }
    /* Even a value past the boundary cannot leave the rate band. */
    const huge = view.videoCorrection({
        driftMs: 249,
        nowMs: 1000,
        lastSeekMs: null,
    });
    assert.ok(huge.rate >= 0.98 && huge.rate <= 1.02, "rate stays bounded");
});

test("video correction: above 250 ms one seek per 5 s", () => {
    const first = view.videoCorrection({
        driftMs: 251,
        nowMs: 10000,
        lastSeekMs: null,
    });
    assert.deepStrictEqual(first, { rate: 1, seek: true }, "no seek yet");

    const spent = view.videoCorrection({
        driftMs: 251,
        nowMs: 12000,
        lastSeekMs: 10000,
    });
    assert.strictEqual(spent.seek, false, "within the 5 s budget");
    close(spent.rate, 0.98, "ahead and out of budget slows at the limit");

    const late = view.videoCorrection({
        driftMs: -400,
        nowMs: 15000,
        lastSeekMs: 10000,
    });
    assert.deepStrictEqual(late, { rate: 1, seek: true }, "budget renewed");

    const notYet = view.videoCorrection({
        driftMs: -400,
        nowMs: 14999,
        lastSeekMs: 10000,
    });
    assert.strictEqual(notYet.seek, false, "one millisecond short");
    close(notYet.rate, 1.02, "behind and out of budget speeds at the limit");
});

let failed = 0;
for (const entry of tests) {
    try {
        entry.fn();
        console.log("ok   - " + entry.name);
    } catch (err) {
        failed++;
        console.error("FAIL - " + entry.name);
        console.error((err && err.stack) || err);
    }
}
console.log(
    failed === 0
        ? "\n" + tests.length + " passed"
        : "\n" + failed + " of " + tests.length + " FAILED"
);
process.exit(failed === 0 ? 0 : 1);
