import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";
import * as stage from "./stagePanels";
import type { Layout, PanelProfile } from "./stagePanels";

type OldFunction = (...args: unknown[]) => unknown;
type OldStage = Record<"panels" | "resolution" | "fit" | "exceptionLabel" | "powerReadiness" | "fleetPower" | "viewZoom" | "viewSize" | "helpText", OldFunction>;

const load = createRequire(import.meta.url);
const oldStage = load("../../../controller/operator-stage.js") as OldStage;
const oldViewport = load("../../../controller/operator-stage-viewport.js") as { measureWell: OldFunction };

const profile: PanelProfile = { active_width_mm: 200, active_height_mm: 100, panel_pixels_width: 1920,
    bezels: { left: 2, right: 2, top: 1, bottom: 1 } };
const bare: PanelProfile = { active_width_mm: 640, active_height_mm: 480 };
const profileFor = (id: string) => id === "z" ? undefined : profile;
const content = { intrinsicWidth: 1600 };
const device = { viewport: { width: 1920, dpr: 2 } };

const logical: Layout = { kind: "logical", width: 200, height: 100, placements: {
    a: { x: 20, y: 30, w: 100, h: 80, bezel: { left: 4, top: 2, right: 3, bottom: 5 } },
    b: { x: 0, y: 0, w: 50, h: 40 },
} };
const physical: Layout = { kind: "physical", slots: {
    a: { center_x_mm: 1200, center_y_mm: 800, mount_angle: 15, nudge_x_mm: 4, nudge_y_mm: -3, profile_revision: 3 },
    b: { center_x_mm: 300, center_y_mm: 200, profile_revision: 4 },
    z: { center_x_mm: 0, center_y_mm: 0 },
} };

const surface = (dragging = false, zoom = "fit") => ({
    classList: { contains: () => dragging },
    ownerDocument: { defaultView: { getComputedStyle: (node: { computed: Record<string, string> }) => node.computed },
        body: { dataset: { viewZoom: zoom } } },
    viewBox: { baseVal: { width: 720, height: 370 } },
    style: {} as { inlineSize?: string; blockSize?: string },
    closest: () => null,
    querySelectorAll: () => [],
});
const field = () => ({ style: {} as Record<string, string> });
const well = (clientWidth: number, clientHeight: number, visible: boolean) => ({ clientWidth, clientHeight,
    getClientRects: () => (visible ? [1] : []),
    computed: { paddingLeft: "16px", paddingRight: "16px", paddingTop: "8px", paddingBottom: "8px" } });
const measuredField = () => ({ parentElement: { computed: { rowGap: "8px" } }, style: {},
    computed: { borderLeftWidth: "1px", borderRightWidth: "1px", borderTopWidth: "1px", borderBottomWidth: "1px" } });
const tally = { getBoundingClientRect: () => ({ height: 28 }) };
const measuredSurface = { ownerDocument: { defaultView: { getComputedStyle: (node: { computed: Record<string, string> }) => node.computed } } };

describe("stage panels differential", () => {
    it("panels", () => {
        expect(stage.panels(logical, profileFor)).toEqual(oldStage.panels(logical, profileFor));
        expect(stage.panels(physical, profileFor)).toEqual(oldStage.panels(physical, profileFor));
        expect(stage.panels({ kind: "logical", width: 0, height: 0 }, profileFor)).toEqual(oldStage.panels({ kind: "logical", width: 0, height: 0 }, profileFor));
        expect(stage.panels({ kind: "physical" }, profileFor)).toEqual(oldStage.panels({ kind: "physical" }, profileFor));
        expect(stage.panels(physical, () => bare)).toEqual(oldStage.panels(physical, () => bare));
    });

    it("resolution", () => {
        const panels = [...stage.panels(logical, profileFor), ...stage.panels(physical, profileFor)];
        for (const panel of panels) {
            expect(stage.resolution(panel, { scale: 0.5 }, content, device)).toEqual(oldStage.resolution(panel, { scale: 0.5 }, content, device));
            expect(stage.resolution(panel, null, content, device)).toEqual(oldStage.resolution(panel, null, content, device));
            expect(stage.resolution(panel, { scale: 0.25 }, { intrinsicWidth: 640 }, null)).toEqual(oldStage.resolution(panel, { scale: 0.25 }, { intrinsicWidth: 640 }, null));
            expect(stage.resolution(panel, { scale: 1 }, content, { viewport: { width: 800, dpr: 1.5 } })).toEqual(oldStage.resolution(panel, { scale: 1 }, content, { viewport: { width: 800, dpr: 1.5 } }));
        }
    });

    it("exceptionLabel", () => {
        for (const status of [undefined, null, "", "displayed", "preview", "offline", "unplaced", "loading", "unknown",
            "excluded", "identifying", "playback", "failed", "needs_profile", "stale", "connected"]) {
            expect(stage.exceptionLabel(status)).toBe(oldStage.exceptionLabel(status));
        }
    });

    it("powerReadiness", () => {
        const devices = [null, {}, { wake_lock: "bogus" }, { wake_lock: "held", online: true, last_seen: "2026-01-01T10:00:00Z" },
            { wake_lock: "denied", online: false, last_seen: "2026-01-01T10:00:00Z" }, { wake_lock: "insecure", online: true },
            { wake_lock: "unsupported", online: false }, { wake_lock: "released", online: true }, { wake_lock: "unknown" }];
        for (const device of devices) {
            expect(stage.powerReadiness(device)).toEqual(oldStage.powerReadiness(device));
            expect(stage.powerReadiness(device, { stale: true })).toEqual(oldStage.powerReadiness(device, { stale: true }));
            expect(stage.powerReadiness(device, { checkedAt: "2026-02-03T04:05:06Z" })).toEqual(oldStage.powerReadiness(device, { checkedAt: "2026-02-03T04:05:06Z" }));
        }
    });

    it("fleetPower", () => {
        const held = stage.powerReadiness({ wake_lock: "held", online: true });
        const denied = stage.powerReadiness({ wake_lock: "denied", online: true });
        const stale = stage.powerReadiness({ wake_lock: "held", online: true }, { stale: true });
        const unknown = stage.powerReadiness({});
        const sets = [
            [],
            [{ online: true, power: held }],
            [{ online: true, power: held }, { online: true, power: held }],
            [{ online: true, power: unknown }, { online: true, power: unknown }],
            [{ online: true, power: denied }, { online: true, power: denied }],
            [{ online: true, power: denied }, { online: true, power: held }],
            [{ online: true, power: denied }, { online: false, power: denied }],
            [{ online: true, power: stale }, { online: true, power: stale }],
            [{ online: true, power: denied }, { online: true, power: null }],
        ];
        for (const entries of sets) expect(stage.fleetPower(entries)).toEqual(oldStage.fleetPower(entries));
    });

    it("viewZoom", () => {
        for (const zoom of ["2x", "fit", ""]) {
            expect(stage.viewZoom(surface(false, zoom) as unknown as SVGSVGElement)).toBe(oldStage.viewZoom(surface(false, zoom)));
        }
        expect(stage.viewZoom(null)).toBe(oldStage.viewZoom(null));
        expect(stage.viewZoom(undefined)).toBe(oldStage.viewZoom(undefined));
    });

    it("viewSize", () => {
        const cases: Array<[number, number, string | undefined]> = [[100, 50, "2x"], [100, 50, "fit"], [0, 0, "2x"], [33, 44, undefined]];
        for (const [width, height, zoom] of cases) expect(stage.viewSize(width, height, zoom)).toEqual(oldStage.viewSize(width, height, zoom));
    });

    it("helpText", () => {
        const cases: Array<[boolean, string | undefined]> = [[true, "physical"], [true, "logical"], [true, undefined], [false, "physical"], [false, undefined]];
        for (const [editable, kind] of cases) expect(stage.helpText(editable, kind)).toBe(oldStage.helpText(editable, kind));
    });

    it("fit", () => {
        const cases = [{ width: 966, height: 546, borderWidth: 2, borderHeight: 2, availableWidth: 968, availableHeight: 546, scrollHeight: 546 },
            { width: 640, height: 300 }, { width: 0, height: 0 }, { width: 100, height: 50, scrollHeight: 20 }];
        for (const available of cases) {
            for (const dragging of [false, true]) {
                for (const zoom of ["fit", "2x"]) {
                    const next = field(), previous = field();
                    const nextSurface = surface(dragging, zoom), previousSurface = surface(dragging, zoom);
                    expect(stage.fit(nextSurface as unknown as SVGSVGElement, available, { field: next as unknown as HTMLElement }))
                        .toEqual(oldStage.fit(previousSurface, available, { field: previous }));
                    expect(next.style).toEqual(previous.style);
                    expect(nextSurface.style).toEqual(previousSurface.style);
                }
            }
        }
    });

    it("measureWell", () => {
        const cases: Array<[number, number, boolean, boolean]> = [[1000, 600, true, true], [1000, 600, true, false], [1000, 300, true, true],
            [170, 600, true, true], [1000, 600, false, true], [0, 0, true, true], [1000, 30, true, true]];
        for (const [clientWidth, clientHeight, visible, withTally] of cases) {
            const nextWell = well(clientWidth, clientHeight, visible), nextField = measuredField();
            expect(stage.measureWell(measuredSurface as unknown as SVGSVGElement, {
                well: nextWell as unknown as HTMLElement, field: nextField as unknown as HTMLElement,
                tally: withTally ? tally as unknown as HTMLElement : null }))
                .toEqual(oldViewport.measureWell(measuredSurface, { well: well(clientWidth, clientHeight, visible),
                    field: measuredField(), tally: withTally ? tally : null }));
        }
    });
});
