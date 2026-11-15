import { createRequire } from "node:module";
import { expect, it } from "vitest";
import * as model from "./layout";
import * as status from "./status";

const require = createRequire(import.meta.url);
const tabletView = require("../../../client/view.js") as { fitMatrix: (bounds: number[], width: number, height: number, fit: string) => number[] };

const now = Date.parse("2026-11-01T12:00:00Z");
const token: model.Token = { connection_id: "socket-1", generation: "g", revision: 8, render_seq: 4, mapping_revision: "mapping", asset: "image" };
const bezel = { top: 0, right: 0, bottom: 0, left: 0 };
function fixture() {
    return { generation: "g", revision: 8, layout: { kind: "physical", bounds: { x: -10, y: 20, width: 400, height: 100 },
        slots: { tablet: { participating: true } } } as model.Layout, scene: { content: { type: "image", asset: "image" } as model.SceneContent },
        runtime: { observed_at: new Date(now).toISOString(), presentation: { owner: "static" }, devices: { tablet: { online: true, protocol: 3 as number,
            caps: ["image", "render_ack"], mapping: { state: "ready" } as model.Mapping, identify: undefined as model.IdentifyState | undefined,
            connection_id: undefined as string | undefined, render: { state: "displayed", current: true, expected_token: { ...token }, accepted_token: { ...token }, age_ms: 0, observed_mono: now } } } } };
}
const logical: model.LogicalLayout = { kind: "logical", width: 320, height: 60, placements: { one: { x: 0, y: 0, w: 80, h: 60, bezel } }, sizing: { mode: "fixed", padding: 0 } };

it("operator_state.test.js", () => {
    const draft = model.layoutDraft(logical);
    expect(draft.kind).toBe("logical");
    expect(draft.width).toBe(320);
    expect(draft.bounds, "logical dimensions must never seed millimetre bounds").toBe(undefined);
    draft.placements!.one!.w = 40;
    expect(logical.placements!.one!.w, "draft must not mutate committed geometry").toBe(80);
    expect(() => model.layoutDraft({ kind: "future" } as unknown as model.Layout)).toThrow(/Unsupported layout/);
    expect(model.bounds(draft)).toEqual({ x: 0, y: 0, width: 320, height: 60 });
    expect(model.fitTransform({ kind: "logical", width: 400, height: 100 }, { intrinsicWidth: 100, intrinsicHeight: 100, fit: "contain" }))
        .toEqual({ x: 150, y: 0, width: 100, height: 100, scale: 1, cropX: 0, cropY: 0 });
    expect(model.fitTransform(fixture().layout, { intrinsicWidth: 100, intrinsicHeight: 100, fit: "cover" }))
        .toEqual({ x: -10, y: -130, width: 400, height: 400, scale: 4, cropX: 0, cropY: 0.75 });
    for (const invalid of [0, NaN, Infinity, true, "100"]) expect(model.fitTransform(draft, { intrinsicWidth: invalid, intrinsicHeight: 100 })).toBe(null);
    for (const layout of [draft, fixture().layout]) {
        const b = model.bounds(layout);
        for (const [width, height] of [[2000, 745], [100, 100], [900, 1600]]) for (const fit of ["cover", "contain"]) {
            const transform = model.fitTransform(layout, { intrinsicWidth: width, intrinsicHeight: height, fit })!;
            expect([transform.width, 0, 0, transform.height, transform.x, transform.y],
                "operator and tablet use the same global source transform")
                .toEqual(tabletView.fitMatrix([b.x, b.y, b.width, b.height], width!, height!, fit));
        }
    }
    const roster = { a: { number: 4 }, b: { number: 1 }, c: { label: "alpha" }, d: { label: "Zulu" }, e: { number: null, label: "Beta" } };
    expect(Object.keys(roster).sort((a, b) => model.compareIds(roster, {}, a, b))).toEqual(["b", "a", "c", "e", "d"]);
    expect(status.tabletState(fixture(), "tablet", now).showing).toBe(true);
    expect(status.tabletState(fixture(), "tablet", now).text).toBe("Reports current image");
    const sceneOnly = fixture(); sceneOnly.scene.content = { type: "color" };
    sceneOnly.runtime.devices.tablet.render.expected_token.asset = null;
    sceneOnly.runtime.devices.tablet.render.accepted_token.asset = null;
    const sceneEvidence = status.tabletState(sceneOnly, "tablet", now);
    expect(sceneEvidence.text).toBe("Reports current colour");
    expect(sceneEvidence.showing, "a displayed colour scene is healthy, not an issue").toBe(true);
    expect(status.aggregate(sceneOnly, now).showing, "healthy colour tablets count as showing").toBe(1);
    const loadingScene = fixture(); loadingScene.scene.content = { type: "color" };
    loadingScene.runtime.devices.tablet.render.state = "loading";
    expect(status.tabletState(loadingScene, "tablet", now).text, "a colour scene never claims to load an image").toMatch(/^Loading colour/);
    const failedScene = fixture(); failedScene.scene.content = { type: "color" };
    failedScene.runtime.devices.tablet.render.state = "failed";
    expect(status.tabletState(failedScene, "tablet", now).text, "a colour scene never claims an image failure").toMatch(/^Colour failed/);
    const staleScene = fixture(); staleScene.scene.content = { type: "color" };
    staleScene.runtime.devices.tablet.render.expected_token.asset = null;
    staleScene.runtime.devices.tablet.render.accepted_token.asset = null;
    staleScene.runtime.devices.tablet.render.current = false;
    expect(status.tabletState(staleScene, "tablet", now).text).toMatch(/previous paint · current colour unconfirmed/i);
    const offlineFixture = fixture(); offlineFixture.runtime.devices.tablet.online = false;
    expect(status.tabletState(offlineFixture, "tablet", now).text).toBe("Offline · spot reserved");
    const notCurrent = fixture(); notCurrent.runtime.devices.tablet.render.current = false;
    expect(status.tabletState(notCurrent, "tablet", now).showing, "server rejection cannot become a green badge").toBe(false);
    const newConnection = fixture(); newConnection.runtime.devices.tablet.connection_id = "socket-2";
    expect(status.tabletState(newConnection, "tablet", now).showing, "a reconnect cannot reuse the previous connection's evidence").toBe(false);
    const clockJump = fixture(); clockJump.runtime.observed_at = "1900-01-01T00:00:00Z";
    expect(status.tabletState(clockJump, "tablet", now).showing, "wall-clock dates must not control evidence expiry").toBe(true);
    const original = fixture();
    const observed = status.observeConfig(original, now + 1000);
    expect(original.runtime.devices.tablet.render.observed_mono, "observing a response must not mutate its input").toBe(now);
    expect(status.tabletState(observed, "tablet", now + 1000).showing).toBe(true);
    expect(status.tabletState(observed, "tablet", now + 16000).showing, "local monotonic time ages a cached response").toBe(false);
    expect(status.aggregate(fixture(), now).total).toEqual(1);
    for (const key of Object.keys(token)) {
        const config = fixture(); config.runtime.devices.tablet.render.accepted_token[key] = "obsolete";
        expect(status.tabletState(config, "tablet", now).showing, "old " + key + " must never count as showing").toBe(false);
    }
    for (const renderStatus of ["blocked", "loading", "failed", "hidden", "stale", "unsupported", "unknown", "painted", "future"]) {
        const config = fixture(); config.runtime.devices.tablet.render.state = renderStatus;
        expect(status.tabletState(config, "tablet", now).showing, renderStatus).toBe(false);
    }
    for (const mappingStatus of ["needs_calibration", "viewport_mismatch", "zoom_changed", "unsupported_content", "unsupported_client"]) {
        const config = fixture(); config.runtime.devices.tablet.mapping!.state = mappingStatus;
        expect(status.tabletState(config, "tablet", now).status).toBe(mappingStatus);
    }
    const wrongPins = fixture(); wrongPins.runtime.devices.tablet.mapping!.profile_revision = 4;
    expect(status.tabletState(wrongPins, "tablet", now).showing, "mapping evidence must describe the slot's pinned profile").toBe(false);
    for (const protocol of [1, 2, null]) {
        const config = fixture(); config.runtime.devices.tablet.protocol = protocol as number;
        expect(status.tabletState(config, "tablet", now).status).toBe("unknown");
    }
    for (const identifyStatus of ["queued", "delivered", "shown"]) {
        const config = fixture(); config.runtime.devices.tablet.identify = { state: identifyStatus, active: true };
        expect(status.tabletState(config, "tablet", now).status).toBe("identifying");
    }
    const clearedIdentify = fixture(); clearedIdentify.runtime.devices.tablet.identify = { state: "cleared", active: false };
    expect(status.tabletState(clearedIdentify, "tablet", now).showing, "cleared Identify metadata must not obscure the current scene").toBe(true);
    const carried = status.observeConfig(fixture(), now + 1000);
    expect(status.tabletState(carried, "tablet", now + 15001).status, "re-adopting a local projection cannot refresh the age of old paint evidence").toBe("stale");
    expect(status.tabletState(fixture(), "tablet", now + 14999).status, "14999 ms old paint is still current").toBe("displayed");
    expect(status.tabletState(fixture(), "tablet", now + 15000).status, "15000 ms old paint is no longer current").toBe("stale");
    const expired = fixture();
    expect(status.tabletState(expired, "tablet", now + 15001).status, "cached age grows after a snapshot").toBe("stale");
    expired.runtime.devices.tablet.online = false;
    expect(status.tabletState(expired, "tablet", now).status).toBe("offline");
    expect(status.aggregate(expired, now).total, "offline reservations remain in the denominator").toBe(1);
    expired.layout.slots!.tablet!.participating = false;
    expect(status.aggregate(expired, now).total).toBe(0);
    expect(status.tabletState(expired, "tablet", now).status).toBe("excluded");
    const noAck = fixture(); noAck.runtime.devices.tablet.caps = ["image"];
    expect(status.tabletState(noAck, "tablet", now).showing, "online and image capable does not prove a paint").toBe(false);
    const playback = fixture(); playback.runtime.presentation.owner = "playback";
    expect(status.tabletState(playback, "tablet", now).status).toBe("playback");
});

it("ported layout and status helpers the tagged file did not assert", () => {
    expect(model.layoutSignature(null)).toBe("");
    expect(model.layoutSignature({ kind: "logical", width: 100, height: 50, placements: {} }))
        .toBe(JSON.stringify({ kind: "logical", width: 100, height: 50, placements: [] }));
    const physical = model.layoutSignature(fixture().layout);
    expect(physical).toBe(JSON.stringify({ bounds: [-10, 20, 400, 100], sizing: { mode: "fixed", padding: 0 }, slots: [["tablet", null, null, null, null, null, null, null, true]] }));
    expect(model.layoutSignature({ ...fixture().layout, slots: { tablet: { participating: false } } })).not.toBe(physical);
    expect(model.entries(fixture().layout)).toEqual({ tablet: { participating: true } });
    expect(model.entries({ kind: "logical", width: 1, height: 1, placements: {}, sizing: { mode: "fixed", padding: 0 } })).toEqual({});
    expect(model.entries(null)).toEqual({});
    expect(model.clone(logical)).toEqual(logical);
    expect(model.clone(logical)).not.toBe(logical);
    expect(model.registrationCounts(fixture())).toEqual({ registered: 1, online: 1, retained: 0 });
    expect(model.registrationCounts({ ...fixture(), layout: { ...fixture().layout, slots: { tablet: { participating: true }, ghost: { participating: true } } } }))
        .toEqual({ registered: 1, online: 1, retained: 1 });
    expect(model.registrationCounts(null)).toBe(null);
    expect(model.shownSubject({ type: "image" })).toBe("image");
    expect(model.shownSubject({ type: "color" })).toBe("colour");
    expect(model.shownSubject({ type: "calibration" })).toBe("wall grid");
    expect(model.shownSubject(null)).toBe("content");
    expect(model.bounds(fixture().layout)).toEqual({ x: -10, y: 20, width: 400, height: 100 });
    expect(model.layoutDraft(fixture().layout).sizing).toEqual({ mode: "fixed", padding: 0 });
    expect(model.compareIds({ a: { label: "B" }, b: { label: "a" } }, {}, "a", "b")).toBeGreaterThan(0);
    expect(model.rotateLogical({ x: 0, y: 0, w: 80, h: 40, bezel: { top: 1, right: 2, bottom: 3, left: 4 } }))
        .toEqual({ x: 20, y: -20, w: 40, h: 80, bezel: { top: 4, right: 1, bottom: 2, left: 3 } });
    const arranged = model.arrangeLogical({ kind: "logical", width: 200, height: 100,
        placements: { a: { x: 0, y: 0, w: 80, h: 60, bezel }, b: { x: 0, y: 0, w: 80, h: 60, bezel } },
        sizing: { mode: "tablets", padding: 4 } }, ["a", "b"], { columns: 2, gap: 6 });
    expect([arranged.width, arranged.height]).toEqual([174, 68]);
    expect(arranged.placements.a).toEqual({ x: 4, y: 4, w: 80, h: 60, bezel });
    expect(arranged.placements.b).toEqual({ x: 90, y: 4, w: 80, h: 60, bezel });
    expect(() => model.arrangeLogical(logical, [], { columns: 2, rows: 1, gap: 0 })).toThrow("No tablets match this scope.");
    expect(() => model.arrangeLogical(logical, ["one"], { columns: 0, gap: 0 })).toThrow("Use positive whole rows and columns and a nonnegative whole gap.");
    const unpadded: model.LogicalLayout = { kind: "logical", width: 10, height: 10,
        placements: { a: { x: 30, y: 40, w: 40, h: 20, bezel } }, sizing: { mode: "tablets", padding: 5 } };
    model.fitLogical(unpadded);
    expect([unpadded.width, unpadded.height]).toEqual([50, 30]);
    expect(unpadded.placements.a).toEqual({ x: 5, y: 5, w: 40, h: 20, bezel });
    expect(status.needsAttention({ showing: false, status: "excluded" })).toBe(false);
    expect(status.needsAttention({ showing: false, status: "offline" })).toBe(true);
    expect(status.needsAttention({ showing: true, status: "displayed" })).toBe(false);
    expect(status.rosterStatus({ status: "displayed", online: true })).toEqual({ key: "connected", word: "Connected", tone: "ok" });
    expect(status.rosterStatus({ status: "offline", online: false })).toEqual({ key: "offline", word: "Offline", tone: "failure" });
    expect(status.rosterStatus({ status: "unplaced", online: true })).toEqual({ key: "not-placed", word: "Not placed", tone: "progress" });
    expect(status.rosterStatus({ status: "unplaced", online: false })).toEqual({ key: "offline", word: "Offline", tone: "quiet" });
    expect(status.rosterStatus({ status: "displayed", online: true }, { stale: true })).toEqual({ key: "stale", word: "Stale", tone: "failure" });
    expect(status.rosterStatus({ status: "viewport_mismatch", online: true })).toEqual({ key: "wrong-content", word: "Wrong content", tone: "failure" });
    expect(model.sameToken(token, { ...token })).toBe(true);
    expect(model.sameToken(token, { ...token, render_seq: 5 })).toBe(false);
    expect(model.sameToken(token, null)).toBe(false);
});

