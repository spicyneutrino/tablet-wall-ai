import { entries } from "./layout";
import type { Layout as LayoutDoc } from "./layout";
import { rosterStatus } from "./status";

export interface Bezel { left?: number; top?: number; right?: number; bottom?: number }

export interface Placement { x: number; y: number; w: number; h: number; bezel?: Bezel | null; participating?: boolean }

export interface Slot {
    center_x_mm: number;
    center_y_mm: number;
    mount_angle?: number;
    nudge_x_mm?: number;
    nudge_y_mm?: number;
    profile_revision?: number | string;
    participating?: boolean;
}

export type Layout =
    | { kind: "logical"; width: number; height: number; placements?: Record<string, Placement> }
    | { kind: "physical"; slots?: Record<string, Slot> };

export interface PanelProfile {
    active_width_mm: number;
    active_height_mm: number;
    panel_pixels_width?: number;
    bezels?: Bezel | null;
}

export interface PanelRect { x: number; y: number; width: number; height: number }

export interface PlacedPanel {
    id: string;
    slot: Placement | Slot;
    profile?: PanelProfile;
    cx?: number;
    cy?: number;
    angle: number;
    body: PanelRect;
    active: PanelRect;
    missing?: false;
}

export interface MissingPanel {
    id: string;
    slot: Placement | Slot;
    missing: true;
    cx: number;
    cy: number;
}

export type Panel = PlacedPanel | MissingPanel;

export interface PowerDevice { wake_lock?: string; online?: boolean; last_seen?: string }

export interface PowerOptions { stale?: boolean; checkedAt?: string | null }

const WAKE_STATES = {
    held: { label: "held", warning: false, guidance: "The browser reports the screen wake lock held. This is not proof the operating system will keep the screen on; check Auto-Lock, charging and kiosk settings." },
    released: { label: "released", warning: true, guidance: "The browser reports the screen wake lock released. Bring the tablet page to the foreground and check Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely." },
    denied: { label: "denied", warning: true, guidance: "The browser denied the screen wake lock. Allow it in the browser and check the trusted origin, Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely." },
    insecure: { label: "insecure origin", warning: true, guidance: "This page is not a trusted secure origin, so the screen wake lock is unavailable. Open the wall over its configured trusted HTTPS origin, then check Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely." },
    unsupported: { label: "unsupported", warning: false, guidance: "This browser does not report a screen wake lock. Keep the tablet charging and check Auto-Lock and kiosk settings. The operator cannot wake the tablet remotely." },
    unknown: { label: "unknown", warning: false, guidance: "The tablet has not reported a screen wake-lock state. Check the current tablet page, Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely." }
};

export type WakeState = keyof typeof WAKE_STATES;

export interface PowerReadiness {
    state: WakeState;
    stale: boolean;
    warning: boolean;
    label: string;
    report: string;
    short: string;
    fact: string;
    guidance: string;
    checkedAt: string | null;
}

const EXCEPTION_LABELS: Record<string, string> = { loading: "Loading", unknown: "Unconfirmed", excluded: "Excluded", identifying: "Identify", playback: "Playback" };

export function exceptionLabel(status?: string | null): string {
    if (!status || status === "displayed" || status === "preview") return "";
    const roster = rosterStatus({ status, online: status !== "offline" });
    if (roster.key !== "connected") return roster.word;
    if (EXCEPTION_LABELS[status]) return EXCEPTION_LABELS[status];
    return "Needs review";
}

export function powerReadiness(device: PowerDevice | null | undefined, options: PowerOptions = {}): PowerReadiness {
    const state: WakeState = device && typeof device.wake_lock === "string" && Object.prototype.hasOwnProperty.call(WAKE_STATES, device.wake_lock)
        ? device.wake_lock as WakeState : "unknown";
    const entry = WAKE_STATES[state];
    const offline = !!device && device.online === false;
    const stale = options.stale === true || offline;
    const checkedAt = offline && device.last_seen || options.checkedAt || null;
    const checked = checkedAt ? Date.parse(checkedAt) : NaN;
    const stamp = stale && Number.isFinite(checked)
        ? " Last checked " + new Date(checked).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + "." : "";
    const label = stale ? "Last known wake lock " + entry.label + " · status stale" : "Wake lock: " + entry.label;
    const report = state === "denied" ? "Denied by browser" : entry.label[0]!.toUpperCase() + entry.label.slice(1);
    return { state, stale, warning: entry.warning, label, report: (stale ? "Last known · " : "") + report,
        short: stale ? "Last known wake lock " + entry.label : "Wake lock " + entry.label,
        fact: stale ? "Last known browser wake-lock state: " + entry.label + "." : entry.guidance,
        guidance: stale ? (offline ? "Tablet is offline; this is the last known report." : "Status is stale; this is the last known report.")
            + stamp + " Last known browser wake-lock state: " + entry.label + ". " + powerHelp : entry.guidance,
        checkedAt };
}

export function fleetPower(entries: Array<{ online?: boolean; power?: PowerReadiness | null }>): { state: WakeState; label: string; count: number } | null {
    const online = entries.filter(entry => entry.online);
    if (online.length < 2) return null;
    const power = online[0]!.power;
    if (!power || !(power.warning || power.state === "unknown")
            || !online.every(entry => entry.power && entry.power.stale === false && entry.power.state === power.state)) return null;
    return { state: power.state, label: WAKE_STATES[power.state].label, count: online.length };
}

const powerHelp = "Screen wake locks are browser reports, not proof the operating system will keep the screen on. "
    + "Check Auto-Lock, charging and kiosk settings. An insecure origin cannot take a wake lock, so open the wall over its trusted HTTPS origin. "
    + "The operator cannot wake a sleeping tablet remotely.";

export function panels(layout: Layout, profileFor: (id: string, revision?: number | string) => PanelProfile | null | undefined): Panel[] {
    return Object.entries(entries(layout as unknown as LayoutDoc)).map(([id, entry]) => {
        if (layout.kind !== "physical") {
            const slot = entry as Placement;
            const bezel = slot.bezel || {};
            return { id, slot, body: { x: slot.x, y: slot.y, width: slot.w, height: slot.h },
                active: { x: slot.x + (bezel.left || 0), y: slot.y + (bezel.top || 0),
                    width: slot.w - (bezel.left || 0) - (bezel.right || 0), height: slot.h - (bezel.top || 0) - (bezel.bottom || 0) }, angle: 0 };
        }
        const slot = entry as Slot;
        const profile = profileFor(id, slot.profile_revision);
        const cx = slot.center_x_mm + (slot.nudge_x_mm || 0), cy = slot.center_y_mm + (slot.nudge_y_mm || 0);
        if (!profile) return { id, slot, missing: true, cx, cy };
        const bezel = profile.bezels || {};
        const width = profile.active_width_mm + (bezel.left || 0) + (bezel.right || 0);
        const height = profile.active_height_mm + (bezel.top || 0) + (bezel.bottom || 0);
        return { id, slot, profile, cx, cy, angle: slot.mount_angle || 0,
            body: { x: cx - width / 2, y: cy - height / 2, width, height },
            active: { x: cx - width / 2 + (bezel.left || 0), y: cy - height / 2 + (bezel.top || 0),
                width: profile.active_width_mm, height: profile.active_height_mm } };
    });
}

export interface Resolution { pixels: number; target: number | null; upscale: number | null }

export function resolution(panel: Panel, transform: { scale: number } | null | undefined, content: { intrinsicWidth: number },
        device?: { viewport?: { width: number; dpr: number } } | null): Resolution | null {
    if (!transform || panel.missing) return null;
    const pixels = Math.round(Math.min(content.intrinsicWidth, panel.active.width / transform.scale));
    const target = panel.profile && panel.profile.panel_pixels_width
        || device && device.viewport && Math.round(device.viewport.width * device.viewport.dpr);
    return { pixels, target: target || null, upscale: target ? target / Math.max(1, pixels) : null };
}

export interface ViewSize { zoom: "2x" | "fit"; inlineSize: number; blockSize: number; fieldBlockSize: number | null; overflow: string }

export function viewZoom(svg?: SVGSVGElement | null): "2x" | "fit" {
    const body = svg && svg.ownerDocument && svg.ownerDocument.body;
    return body && body.dataset && body.dataset.viewZoom === "2x" ? "2x" : "fit";
}

export function viewSize(width: number, height: number, zoom?: string): ViewSize {
    const zoomed = zoom === "2x";
    return { zoom: zoomed ? "2x" : "fit", inlineSize: zoomed ? width * 2 : width,
        blockSize: zoomed ? height * 2 : height, fieldBlockSize: zoomed ? height : null,
        overflow: zoomed ? "auto" : "" };
}

export function helpText(editable: boolean, kind?: string): string {
    if (!editable) {
        return "Wall preview. Select a tablet to inspect its identity and status. Numeric position and size fields are available in Arrange when a draft is editable. " + powerHelp;
    }
    if (kind === "physical") {
        return "Wall. Select a tablet and drag it, or use the arrow keys to nudge it by 1 millimetre, or Shift with an arrow for 10 millimetres. "
            + "Escape cancels a drag. Measured positions use decimal millimetres and pinned measurements; numeric centre, nudge, angle and measurement fields are in Arrange. " + powerHelp;
    }
    return "Wall. Select a tablet and drag it, or use the arrow keys to move it by 1 wall unit, or Shift with an arrow for 10 units. "
        + "Escape cancels a drag. Alt pauses snapping while dragging with a mouse or pen; on touch use the snap checkbox. "
        + "Numeric position, size and bezel fields are available in Arrange. Fit and 2x change the view only. " + powerHelp;
}

const LABEL_MAX = 16;

// The label attributes are written with numbers as well as strings, as the old module does.
type LabelNode = {
    dataset: Record<string, string | undefined>;
    style: { display: string };
    textContent: string;
    classList?: { contains(token: string): boolean };
    previousElementSibling: LabelNode | null;
    getScreenCTM(): { a: number; b: number } | null;
    getComputedTextLength?(): number;
    setAttribute(name: string, value: string | number): void;
};

type MeasuredLabel = { label: LabelNode; scale: number; width: number; fit: number };
type MeasuredStatus = { label: LabelNode; scale: number; width: number; height: number; text: string; offline: boolean; fit: number };

function fitLabels(svg: SVGSVGElement): void {
    const labels = ([...svg.querySelectorAll(".operator-slot-label")] as unknown as LabelNode[]).map(label => {
        const matrix = label.getScreenCTM();
        const scale = matrix ? Math.hypot(matrix.a, matrix.b) : 0;
        if (!scale) return null;
        const width = Number(label.dataset.width) * scale, height = Number(label.dataset.height) * scale;
        const fit = Math.min(LABEL_MAX, height - 8, (width - 12) / (Math.min(4, label.dataset.label!.length) * 0.6));
        return { label, scale, width, fit };
    }).filter((item): item is MeasuredLabel => Boolean(item));
    const numberedWall = labels.some(({ label, width }) => label.dataset.label!.length * LABEL_MAX * 0.6 > width - 12);
    const wallSize = Math.min(LABEL_MAX, ...labels.map(item => item.fit));
    labels.forEach(({ label, scale }) => {
        const text = label.dataset.label!;
        const size = Math.max(1, wallSize);
        const numbered = /^Tablet (\d+)\b/.exec(text);
        label.style.display = "";
        label.textContent = numberedWall && numbered ? numbered[1]! : text;
        label.setAttribute("font-size", size / scale);
        label.setAttribute("stroke-width", 0);
        label.setAttribute("x", Number(label.dataset.x) + 6 / scale);
        label.setAttribute("y", Number(label.dataset.y) + (size + 4) / scale);
        const bg = label.previousElementSibling;
        if (bg && bg.classList && bg.classList.contains("operator-slot-label-bg")) {
            const textWidth = typeof label.getComputedTextLength === "function" ? label.getComputedTextLength() : label.textContent.length * size * 0.6 / scale;
            bg.setAttribute("x", Number(label.dataset.x) + 3 / scale);
            bg.setAttribute("y", Number(label.dataset.y) + 1.5 / scale);
            bg.setAttribute("width", textWidth + 6 / scale);
            bg.setAttribute("height", (size + 5) / scale);
            bg.setAttribute("rx", 2 / scale);
        }
    });
    const statusLabels = ([...svg.querySelectorAll(".operator-slot-status")] as unknown as LabelNode[]).map(label => {
        if (!label.classList || !label.classList.contains("operator-slot-status")) return;
        const matrix = label.getScreenCTM();
        if (!matrix) return;
        const scale = Math.hypot(matrix.a, matrix.b);
        if (!scale) return;
        const width = Number(label.dataset.width) * scale, height = Number(label.dataset.height) * scale;
        let text = label.dataset.label || "";
        const offline = label.dataset.status === "offline";
        if (offline && (width - 12) / (Math.max(1, text.length) * 0.6) < 9) text = "Offline";
        const fit = Math.min(LABEL_MAX, height - 10, (width - 12) / (Math.max(1, text.length) * 0.6));
        return { label, scale, width, height, text, offline, fit };
    }).filter((item): item is MeasuredStatus => Boolean(item));
    const statusSize = Math.min(LABEL_MAX, ...statusLabels.map(item => item.fit).filter(fit => fit >= 9));
    statusLabels.forEach(({ label, scale, width, height, text, offline, fit }) => {
        label.textContent = text;
        const size = Math.min(statusSize, fit);
        const room = Math.max(1, Math.floor((width - 12) / (Math.max(1, size) * 0.6)));
        const fits = offline || size >= 9 && text.length <= room;
        label.style.display = fits ? "" : "none";
        if (!fits) return;
        label.setAttribute("font-size", size / scale);
        label.setAttribute("stroke-width", 2 / scale);
        if (offline) {
            label.setAttribute("text-anchor", "middle");
            label.setAttribute("x", Number(label.dataset.x) + Number(label.dataset.width) / 2);
            label.setAttribute("y", Number(label.dataset.y) + Number(label.dataset.height) / 2 + size / 3 / scale);
            return;
        }
        label.setAttribute("x", Number(label.dataset.x) + 6 / scale);
        label.setAttribute("y", Number(label.dataset.y) + height / scale - 6 / scale);
    });
}

export interface FitAvailable {
    width: number;
    height: number;
    borderWidth?: number;
    borderHeight?: number;
    availableWidth?: number;
    availableHeight?: number;
    scrollHeight?: number;
}

export interface FitOptions { field?: HTMLElement }

export interface FitResult { width: number; height: number; availableWidth: number; availableHeight: number; zoom: "2x" | "fit" }

export function fit(svg: SVGSVGElement, available: FitAvailable, { field = svg.closest(".stage-scroll") as HTMLElement }: FitOptions = {}): FitResult | null {
    if (svg.classList.contains("is-dragging")) return null;
    const { width, height: availableHeight, borderWidth = 0, borderHeight = 0 } = available;
    const aspect = svg.viewBox.baseVal.width / svg.viewBox.baseVal.height;
    const height = Math.min(availableHeight, width / aspect);
    const fitWidth = Math.min(width, height * aspect);
    const size = viewSize(fitWidth, height, viewZoom(svg));
    field.style.inlineSize = fitWidth + borderWidth + "px";
    field.style.blockSize = size.fieldBlockSize === null ? ""
        : Math.min(size.fieldBlockSize, available.scrollHeight || availableHeight) + borderHeight + "px";
    field.style.overflow = size.overflow;
    svg.style.inlineSize = size.inlineSize + "px";
    svg.style.blockSize = size.blockSize + "px";
    fitLabels(svg);
    return { width: fitWidth, height, availableWidth: available.availableWidth ?? width,
        availableHeight: available.availableHeight ?? availableHeight, zoom: size.zoom };
}

export interface MeasureWellOptions { field: HTMLElement; well: HTMLElement; tally?: HTMLElement | null }

export interface WellRect {
    width: number;
    height: number;
    borderWidth: number;
    borderHeight: number;
    availableWidth: number;
    availableHeight: number;
    scrollHeight: number;
}

export function measureWell(svg: SVGSVGElement, { field, well, tally }: MeasureWellOptions): WellRect | null {
    const win = svg.ownerDocument.defaultView!;
    if (!well.getClientRects().length) return null;
    const wellStyle = win.getComputedStyle(well), fieldStyle = win.getComputedStyle(field);
    const gap = parseFloat(win.getComputedStyle(field.parentElement!).rowGap) || 0;
    const contentWidth = well.clientWidth - parseFloat(wellStyle.paddingLeft) - parseFloat(wellStyle.paddingRight);
    const contentHeight = well.clientHeight - parseFloat(wellStyle.paddingTop) - parseFloat(wellStyle.paddingBottom)
        - (tally ? tally.getBoundingClientRect().height + gap : 0);
    const borderWidth = parseFloat(fieldStyle.borderLeftWidth) + parseFloat(fieldStyle.borderRightWidth);
    const borderHeight = parseFloat(fieldStyle.borderTopWidth) + parseFloat(fieldStyle.borderBottomWidth);
    const availableWidth = Math.max(0, contentWidth), availableHeight = Math.max(0, contentHeight - borderHeight);
    if (availableWidth <= 0) return null;
    const width = Math.max(0, availableWidth - borderWidth);
    return { width, height: availableHeight, borderWidth, borderHeight, availableWidth, availableHeight, scrollHeight: availableHeight };
}
