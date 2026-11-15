export type Viewport = {
    width: number;
    height: number;
    dpr: number;
    orientation: number;
    mode: string;
};

type RosterRecord = {
    online?: unknown;
    viewport?: Viewport & { visual_scale?: unknown };
};

export function selectedViewport(roster: Record<string, RosterRecord | undefined>, id: string): Viewport | null {
    const record = roster[id];
    const v = record && record.online === true && record.viewport;
    if (!v || ![v.width, v.height, v.dpr].every(n => typeof n === "number" && Number.isFinite(n) && n > 0)
        || ![0, 90, 180, 270].includes(v.orientation)
        || !["tab", "fullscreen", "standalone"].includes(v.mode)
        || (v.visual_scale !== undefined && (typeof v.visual_scale !== "number"
            || !Number.isFinite(v.visual_scale) || Math.abs(v.visual_scale - 1) > 0.01))) return null;
    return { width: v.width, height: v.height, dpr: v.dpr, orientation: v.orientation, mode: v.mode };
}

export function rulerScale(measuredX: string | number, measuredY: string | number, spanX: string | number, spanY: string | number): number[] {
    const values = [measuredX, measuredY, spanX, spanY].map(Number) as [number, number, number, number];
    if (!values.every(n => Number.isFinite(n) && n > 0)) throw new Error("Enter positive measured lengths and CSS spans for both lines.");
    const scale = [values[0] / values[2], values[1] / values[3]];
    if (!scale.every(n => Number.isFinite(n) && n > 0)) throw new Error("Ruler scale must be finite and positive.");
    return scale;
}

export function rulerUrl(origin: string | null): string | null {
    try {
        const url = new URL(origin as string);
        const host = url.hostname.toLowerCase().replace(/\.+$/, "");
        if (!["http:", "https:"].includes(url.protocol) || url.username || url.password
            || host === "localhost" || host.endsWith(".localhost") || host === "[::1]"
            || /^127\./.test(host)) return null;
        return new URL("/client/?calibrate=1", url.origin).href;
    } catch { return null; }
}

export type AxisMeasurement = {
    mm: string | number;
    px: string | number;
    error: string | number;
};

export type RulerMeasurements = { x: AxisMeasurement; y: AxisMeasurement };

export type RulerCheckBody = {
    device_id: string;
    profile_revision: number;
    quarter_turn: number;
    axis: "x" | "y";
    span_px: number;
    span_mm: number;
    span_error_mm: number;
    usable_width_px: number;
    usable_height_px: number;
};

export function rulerCheckBodies(deviceId: string, profileRevision: number, quarterTurn: number, viewport: Viewport | null, measurements: RulerMeasurements): RulerCheckBody[] {
    if (!viewport) throw new Error("Capture the selected tablet's online viewport first.");
    if (!Number.isInteger(profileRevision) || profileRevision < 1) throw new Error("Choose an existing profile revision.");
    if (![0, 1, 2, 3].includes(quarterTurn)) throw new Error("Choose the native-panel quarter turn first.");
    rulerScale(measurements.x.mm, measurements.y.mm, measurements.x.px, measurements.y.px);
    return (["x", "y"] as const).map(axis => {
        const error = measurements[axis].error;
        if (error === "" || !Number.isFinite(Number(error)) || Number(error) < 0) {
            throw new Error("Enter an estimated ruler error in mm for each axis, including zero if appropriate.");
        }
        return {
            device_id: deviceId, profile_revision: profileRevision, quarter_turn: quarterTurn,
            axis, span_px: Number(measurements[axis].px), span_mm: Number(measurements[axis].mm),
            span_error_mm: Number(error), usable_width_px: viewport.width, usable_height_px: viewport.height
        };
    });
}

export class RulerReview {
    status: string;
    key: string | null;
    results: unknown;

    constructor() { this.status = "idle"; this.key = null; this.results = null; }
    reset(): void { this.status = "idle"; this.key = null; this.results = null; }
    begin(key: string): void { this.key = key; this.results = null; this.status = "checking"; }
    accept(key: string, results: unknown): boolean {
        if (this.status !== "checking" || this.key !== key) return false;
        this.results = results;
        this.status = "review";
        return true;
    }
    decide(choice: "keep_supplied" | "use_ruler" | "remeasure"): void {
        if (this.status !== "review") throw new Error("Check the current ruler measurements before choosing.");
        if (!["keep_supplied", "use_ruler", "remeasure"].includes(choice)) throw new Error("Choose a ruler decision.");
        this.status = { keep_supplied: "kept", use_ruler: "prepared", remeasure: "stale" }[choice];
    }
    invalidate(): void { if (this.status !== "idle") this.status = "stale"; }
    canSave(key: string): boolean { return this.status === "prepared" && this.key === key; }
}
