// Differential proof that the TypeScript port matches frontend/controller/operator-state.js.
// Deleted at switch-over; layoutStatus.test.ts stays.

import { createRequire } from "node:module";
import { expect, it } from "vitest";
import * as model from "./layout";
import * as status from "./status";

const require = createRequire(import.meta.url);

type OldState = {
    layoutSignature: typeof model.layoutSignature;
    entries: typeof model.entries;
    clone: typeof model.clone;
    layoutDraft: typeof model.layoutDraft;
    bounds: typeof model.bounds;
    fitTransform: typeof model.fitTransform;
    fitLogical: typeof model.fitLogical;
    arrangeLogical: typeof model.arrangeLogical;
    rotateLogical: typeof model.rotateLogical;
    compareIds: typeof model.compareIds;
    sameToken: typeof model.sameToken;
    registrationCounts: typeof model.registrationCounts;
    shownSubject: typeof model.shownSubject;
    observeDevice: typeof status.observeDevice;
    observeConfig: typeof status.observeConfig;
    tabletState: typeof status.tabletState;
    needsAttention: typeof status.needsAttention;
    rosterStatus: typeof status.rosterStatus;
    aggregate: typeof status.aggregate;
};

const old = require("../../../controller/operator-state.js") as OldState;

const now = Date.parse("2026-11-01T12:00:00Z");
const token: model.Token = { connection_id: "socket-1", generation: "g", revision: 8, render_seq: 4, mapping_revision: "mapping", asset: "image" };
const bezel = { top: 0, right: 0, bottom: 0, left: 0 };
const tokenKeys = Object.keys(token);

function fixture() {
    return { generation: "g", revision: 8, layout: { kind: "physical", bounds: { x: -10, y: 20, width: 400, height: 100 },
        slots: { tablet: { participating: true } } } as model.Layout, scene: { content: { type: "image", asset: "image" } as model.SceneContent },
        runtime: { observed_at: new Date(now).toISOString(), presentation: { owner: "static" }, devices: { tablet: { online: true, protocol: 3 as number,
            caps: ["image", "render_ack"], mapping: { state: "ready" } as model.Mapping, identify: undefined as model.IdentifyState | undefined,
            connection_id: undefined as string | undefined, render: { state: "displayed", current: true, expected_token: { ...token }, accepted_token: { ...token }, age_ms: 0, observed_mono: now, reason: undefined as string | undefined } } } } };
}

const logical: model.LogicalLayout = { kind: "logical", width: 320, height: 60, placements: { one: { x: 0, y: 0, w: 80, h: 60, bezel } }, sizing: { mode: "fixed", padding: 0 } };

const message = (call: () => unknown): string | null => {
    try { call(); return null; } catch (error) { return error instanceof Error ? error.message : String(error); }
};

it("layout.js matches operator-state.js", () => {
    const layouts = (): Array<model.Layout | null | undefined> => [null, undefined, logical, fixture().layout, { kind: "logical", width: 100, height: 50, placements: {} },
        { kind: "physical", bounds: { x: 0, y: 0, width: 1, height: 2 }, slots: { a: { participating: false }, b: {} } },
        { kind: "physical" }];
    for (const layout of layouts()) {
        expect(model.layoutSignature(layout)).toEqual(old.layoutSignature(layout));
        expect(model.entries(layout)).toEqual(old.entries(layout));
    }

    expect(model.clone(logical)).toEqual(old.clone(logical));
    expect(model.layoutDraft(logical)).toEqual(old.layoutDraft(logical));
    expect(model.layoutDraft(fixture().layout)).toEqual(old.layoutDraft(fixture().layout));
    expect(model.layoutDraft({ width: 5, height: 5 })).toEqual(old.layoutDraft({ width: 5, height: 5 }));
    const future = { kind: "future" } as unknown as model.Layout;
    expect(message(() => model.layoutDraft(future))).toBe(message(() => old.layoutDraft(future)));
    expect(message(() => model.layoutDraft(null))).toBe(message(() => old.layoutDraft(null)));

    const drafts = () => [model.layoutDraft(logical), model.layoutDraft(fixture().layout)];
    for (const draft of drafts()) expect(model.bounds(draft)).toEqual(old.bounds(draft));

    expect(model.fitTransform({ kind: "logical", width: 400, height: 100 }, { intrinsicWidth: 100, intrinsicHeight: 100, fit: "contain" }))
        .toEqual(old.fitTransform({ kind: "logical", width: 400, height: 100 }, { intrinsicWidth: 100, intrinsicHeight: 100, fit: "contain" }));
    expect(model.fitTransform(fixture().layout, { intrinsicWidth: 100, intrinsicHeight: 100, fit: "cover" }))
        .toEqual(old.fitTransform(fixture().layout, { intrinsicWidth: 100, intrinsicHeight: 100, fit: "cover" }));
    for (const invalid of [0, NaN, Infinity, true, "100"]) {
        expect(model.fitTransform(logical, { intrinsicWidth: invalid, intrinsicHeight: 100 }))
            .toEqual(old.fitTransform(logical, { intrinsicWidth: invalid, intrinsicHeight: 100 }));
    }
    for (const layout of [logical, fixture().layout] as const) {
        for (const [width, height] of [[2000, 745], [100, 100], [900, 1600]]) for (const fit of ["cover", "contain"]) {
            expect(model.fitTransform(layout, { intrinsicWidth: width, intrinsicHeight: height, fit }))
                .toEqual(old.fitTransform(layout, { intrinsicWidth: width, intrinsicHeight: height, fit }));
        }
    }

    const padded = (): model.LogicalLayout => ({ kind: "logical", width: 10, height: 10, placements: { a: { x: 30, y: 40, w: 40, h: 20, bezel } }, sizing: { mode: "tablets", padding: 5 } });
    const newPadded = padded(), oldPadded = padded();
    model.fitLogical(newPadded);
    old.fitLogical(oldPadded);
    expect(newPadded).toEqual(oldPadded);
    const fixed = (): model.LogicalLayout => ({ kind: "logical", width: 10, height: 10, placements: { a: { x: 30, y: 40, w: 40, h: 20, bezel } }, sizing: { mode: "fixed", padding: 5 } });
    const newFixed = fixed(), oldFixed = fixed();
    model.fitLogical(newFixed);
    old.fitLogical(oldFixed);
    expect(newFixed).toEqual(oldFixed);

    const grid = (): model.LogicalLayout => ({ kind: "logical", width: 200, height: 100,
        placements: { a: { x: 0, y: 0, w: 80, h: 60, bezel }, b: { x: 0, y: 0, w: 80, h: 60, bezel } }, sizing: { mode: "tablets", padding: 4 } });
    const arrangeCases: model.ArrangeOptions[] = [
        { columns: 2, gap: 6 },
        { columns: 2, rows: 1, gap: 6 },
        { columns: 1, gap: 0, tile: true },
        { columns: 2, gap: 0, tile: true, preserveAspect: false },
        { columns: 2, gap: 6, tile: true, aspects: { a: 2 } },
        { columns: 0, gap: 0 },
        { columns: 2, gap: -1 },
    ];
    for (const options of arrangeCases) {
        for (const ids of [["a", "b"], ["b"], [], ["a", "b", "a"]]) {
            const newGrid = grid(), oldGrid = grid();
            const newMessage = message(() => model.arrangeLogical(newGrid, ids, options));
            const oldMessage = message(() => old.arrangeLogical(oldGrid, ids, options));
            expect(newMessage).toBe(oldMessage);
            if (newMessage === null) expect(newGrid).toEqual(oldGrid);
        }
    }

    expect(model.rotateLogical({ x: 0, y: 0, w: 80, h: 40, bezel: { top: 1, right: 2, bottom: 3, left: 4 } }))
        .toEqual(old.rotateLogical({ x: 0, y: 0, w: 80, h: 40, bezel: { top: 1, right: 2, bottom: 3, left: 4 } }));
    expect(model.rotateLogical({ x: 5, y: 7, w: 80, h: 40, bezel })).toEqual(old.rotateLogical({ x: 5, y: 7, w: 80, h: 40, bezel }));

    const roster = { a: { number: 4 }, b: { number: 1 }, c: { label: "alpha" }, d: { label: "Zulu" }, e: { number: null, label: "Beta" }, f: { number: 4, label: "beta" } };
    const labels = { a: "Delta", f: "alpha" };
    for (const left of Object.keys(roster)) for (const right of Object.keys(roster)) {
        expect(model.compareIds(roster, labels, left, right)).toBe(old.compareIds(roster, labels, left, right));
    }
    expect(Object.keys(roster).sort((a, b) => model.compareIds(roster, {}, a, b)))
        .toEqual(Object.keys(roster).sort((a, b) => old.compareIds(roster, {}, a, b)));

    for (const other of [{ ...token }, { ...token, render_seq: 5 }, { ...token, asset: "other" }, null, undefined, {}]) {
        expect(model.sameToken(token, other)).toBe(old.sameToken(token, other));
        expect(model.sameToken(other, token)).toBe(old.sameToken(other, token));
    }

    const counts: model.Config[] = [fixture(), { runtime: { devices: {} } }, { runtime: {} }, {},
        { runtime: { devices: { tablet: { online: true } } }, layout: { ...fixture().layout, slots: { tablet: { participating: true }, ghost: { participating: true } } } },
        { runtime: { devices: { tablet: { online: false } } }, layout: fixture().layout }];
    for (const config of counts) expect(model.registrationCounts(config)).toEqual(old.registrationCounts(config));
    expect(model.registrationCounts(null)).toEqual(old.registrationCounts(null));
    const arrayDevices = { runtime: { devices: [] } } as unknown as model.Config;
    expect(model.registrationCounts(arrayDevices)).toEqual(old.registrationCounts(arrayDevices));

    for (const content of [{ type: "image" }, { type: "color" }, { type: "calibration" }, { type: "other" }, {}, null, undefined]) {
        expect(model.shownSubject(content)).toEqual(old.shownSubject(content));
    }
});

it("status.js matches operator-state.js", () => {
    const devices: model.Device[] = [
        { render: { observed_mono: now, age_ms: 0, state: "displayed" } },
        { render: { observed_mono: now, state: "loading" } },
        { render: { state: "failed" } },
        { render: {} },
        { online: true },
        {},
    ];
    for (const device of devices) expect(status.observeDevice(device, now + 1000)).toEqual(old.observeDevice(device, now + 1000));

    expect(status.observeConfig(fixture(), now + 1000)).toEqual(old.observeConfig(fixture(), now + 1000));
    expect(status.observeConfig({ ...fixture(), runtime: {} }, now + 1000)).toEqual(old.observeConfig({ ...fixture(), runtime: {} }, now + 1000));
    expect(status.observeConfig({}, now + 1000)).toEqual(old.observeConfig({}, now + 1000));

    const sceneOnly = () => { const config = fixture(); config.scene.content = { type: "color" };
        config.runtime.devices.tablet.render.expected_token.asset = null; config.runtime.devices.tablet.render.accepted_token.asset = null; return config; };
    const loadingScene = () => { const config = sceneOnly(); config.runtime.devices.tablet.render.state = "loading"; return config; };
    const failedScene = () => { const config = sceneOnly(); config.runtime.devices.tablet.render.state = "failed"; return config; };
    const staleScene = () => { const config = sceneOnly(); config.runtime.devices.tablet.render.current = false; return config; };
    const offlineFixture = () => { const config = fixture(); config.runtime.devices.tablet.online = false; return config; };
    const notCurrent = () => { const config = fixture(); config.runtime.devices.tablet.render.current = false; return config; };
    const newConnection = () => { const config = fixture(); config.runtime.devices.tablet.connection_id = "socket-2"; return config; };
    const clockJump = () => { const config = fixture(); config.runtime.observed_at = "1900-01-01T00:00:00Z"; return config; };
    const wrongPins = () => { const config = fixture(); config.runtime.devices.tablet.mapping!.profile_revision = 4; return config; };
    const wrongCalibration = () => { const config = fixture(); config.runtime.devices.tablet.mapping!.calibration_revision = 4; return config; };
    const playback = () => { const config = fixture(); config.runtime.presentation.owner = "playback"; return config; };
    const noAck = () => { const config = fixture(); config.runtime.devices.tablet.caps = ["image"]; return config; };
    const clearedIdentify = () => { const config = fixture(); config.runtime.devices.tablet.identify = { state: "cleared", active: false }; return config; };
    const expired = () => { const config = fixture(); config.runtime.devices.tablet.online = false; config.layout.slots!.tablet!.participating = false; return config; };

    const cases: Array<[() => ReturnType<typeof fixture>, number]> = [[fixture, now], [sceneOnly, now], [loadingScene, now], [failedScene, now],
        [staleScene, now], [offlineFixture, now], [notCurrent, now], [newConnection, now], [clockJump, now], [wrongPins, now],
        [wrongCalibration, now], [playback, now], [noAck, now], [clearedIdentify, now], [expired, now], [fixture, now + 14999],
        [fixture, now + 15000], [fixture, now + 15001], [fixture, now + 16000]];
    for (const [config, at] of cases) {
        expect(status.tabletState(config(), "tablet", at)).toEqual(old.tabletState(config(), "tablet", at));
        expect(status.aggregate(config(), at)).toEqual(old.aggregate(config(), at));
    }
    for (const key of tokenKeys) {
        const config = () => { const next = fixture(); next.runtime.devices.tablet.render.accepted_token[key] = "obsolete"; return next; };
        expect(status.tabletState(config(), "tablet", now)).toEqual(old.tabletState(config(), "tablet", now));
    }
    for (const renderStatus of ["blocked", "loading", "failed", "hidden", "stale", "unsupported", "unknown", "painted", "future", "displayed"]) {
        const config = () => { const next = fixture(); next.runtime.devices.tablet.render.state = renderStatus; return next; };
        expect(status.tabletState(config(), "tablet", now)).toEqual(old.tabletState(config(), "tablet", now));
    }
    for (const mappingStatus of ["needs_calibration", "viewport_mismatch", "zoom_changed", "unsupported_content", "unsupported_client", "ready", ""]) {
        const config = () => { const next = fixture(); next.runtime.devices.tablet.mapping!.state = mappingStatus; return next; };
        expect(status.tabletState(config(), "tablet", now)).toEqual(old.tabletState(config(), "tablet", now));
    }
    for (const protocol of [1, 2, 3, null]) {
        const config = () => { const next = fixture(); next.runtime.devices.tablet.protocol = protocol as number; return next; };
        expect(status.tabletState(config(), "tablet", now)).toEqual(old.tabletState(config(), "tablet", now));
    }
    for (const identifyStatus of ["queued", "delivered", "shown"]) {
        const config = () => { const next = fixture(); next.runtime.devices.tablet.identify = { state: identifyStatus, active: true }; return next; };
        expect(status.tabletState(config(), "tablet", now)).toEqual(old.tabletState(config(), "tablet", now));
    }
    const reason = () => { const next = fixture(); next.runtime.devices.tablet.render.state = "failed"; next.runtime.devices.tablet.render = { ...next.runtime.devices.tablet.render, reason: "decode error" }; return next; };
    expect(status.tabletState(reason(), "tablet", now)).toEqual(old.tabletState(reason(), "tablet", now));
    const unplaced = () => ({ ...fixture(), layout: { kind: "physical", bounds: { x: 0, y: 0, width: 1, height: 1 }, slots: {} } as model.Layout });
    expect(status.tabletState(unplaced(), "tablet", now)).toEqual(old.tabletState(unplaced(), "tablet", now));
    const missingDevice = () => ({ ...fixture(), runtime: { ...fixture().runtime, devices: {} } });
    expect(status.tabletState(missingDevice(), "tablet", now)).toEqual(old.tabletState(missingDevice(), "tablet", now));
    const logicalLayout = () => ({ ...fixture(), layout: { kind: "logical", width: 100, height: 50, placements: { tablet: { x: 0, y: 0, w: 10, h: 10, bezel } }, sizing: { mode: "fixed", padding: 0 } } as model.Layout });
    expect(status.tabletState(logicalLayout(), "tablet", now)).toEqual(old.tabletState(logicalLayout(), "tablet", now));
    expect(status.aggregate(logicalLayout(), now)).toEqual(old.aggregate(logicalLayout(), now));

    for (const item of [{ showing: true, status: "displayed" }, { showing: false, status: "excluded" }, { showing: false, status: "offline" },
        { showing: false, status: "stale" }, { showing: false, status: "unknown" }]) {
        expect(status.needsAttention(item)).toEqual(old.needsAttention(item));
    }
    for (const item of [{ status: "displayed", online: true }, { status: "unplaced", online: true }, { status: "unplaced", online: false },
        { status: "offline", online: false }, { status: "unknown", online: false }, { status: "unknown", online: true },
        { status: "stale", online: true }, { status: "viewport_mismatch", online: true }]) {
        for (const options of [undefined, {}, { stale: true }]) {
            expect(status.rosterStatus(item, options)).toEqual(old.rosterStatus(item, options));
        }
    }
});
