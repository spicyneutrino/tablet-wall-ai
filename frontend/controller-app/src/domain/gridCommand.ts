// Ported from frontend/controller/operator-grid.js (`command`, `membership`).
// Local shapes stand in for src/api/config.ts until U02 merges; field names follow §4.1.
export type GridKind = "logical" | "physical";
export type GridSizing = "fixed" | "tablets";
export type GridOrientation = "preserve" | "auto" | "portrait" | "landscape";
export type GridSize = { w: number; h: number };
export type GridRevision = { profile_revision: number; calibration_revision: number };

export type GridCommandInput = {
    kind: GridKind;
    ids: string[];
    rows: number;
    columns: number;
    gap: number;
    padding: number;
    sizing: GridSizing;
    orientation: GridOrientation;
    holes?: boolean;
    releases: string[];
    sizes?: Record<string, GridSize>;
    revisions?: Record<string, GridRevision>;
    angles?: Record<string, string | number>;
};

export type GridCommand = {
    kind: GridKind;
    device_ids: string[];
    rows: number;
    columns: number;
    gap: number;
    padding: number;
    sizing: GridSizing;
    orientation: GridOrientation;
    allow_empty_cells: boolean | undefined;
    release_unselected: string[];
    logical_sizes?: Record<string, GridSize>;
    physical_revisions?: Record<string, GridRevision>;
    mount_angles?: Record<string, number>;
};

export type PlacementLike = { w: number; h: number };
export type LayoutLike = {
    kind?: string;
    slots?: Record<string, unknown>;
    placements?: Record<string, PlacementLike>;
};
export type RosterDevice = { online?: boolean; viewport?: { width?: number; height?: number } };
export type Member = {
    included: boolean;
    membershipSource: "automatic" | "operator";
    size: GridSize;
    sizeSource: "fallback" | "saved" | "viewport" | "operator";
};
export type MembershipOptions = { refreshSaved?: boolean };
export type Membership = {
    observe(roster: Record<string, RosterDevice>, layout: LayoutLike, options?: MembershipOptions): void;
    commit(layout: LayoutLike): void;
    include(id: string, included: boolean): void;
    size(id: string, size: GridSize): void;
    freeze(): void;
    view(): Record<string, Member>;
};

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const layoutEntries = (layout: LayoutLike | null | undefined): Record<string, unknown> =>
    layout && (layout.kind === "physical" ? layout.slots : layout.placements) || {};

export function membership(): Membership {
    const members: Record<string, Member> = {};
    let frozen = false;
    return {
        observe(roster, layout, { refreshSaved = false } = {}) {
            const entries = layoutEntries(layout);
            for (const id of new Set([...Object.keys(roster), ...Object.keys(entries)])) {
                const device = roster[id] || {}, saved = layout.placements && layout.placements[id];
                const member = members[id] ||= { included: !!entries[id], membershipSource: "automatic",
                    size: saved ? { w: saved.w, h: saved.h } : { w: 100, h: 100 }, sizeSource: saved ? "saved" : "fallback" };
                if (!frozen && member.membershipSource === "automatic" && device.online) member.included = true;
                if (refreshSaved && saved && member.sizeSource === "saved") member.size = { w: saved.w, h: saved.h };
                const viewport = device.viewport;
                const viewportWidth = Number(viewport && viewport.width);
                const viewportHeight = Number(viewport && viewport.height);
                const logicalWidth = Math.round(100 * (viewportWidth / viewportHeight));
                if (!frozen && ["fallback", "viewport"].includes(member.sizeSource) && device.online
                        && Number.isFinite(viewportWidth) && Number.isFinite(viewportHeight)
                        && viewportWidth > 0 && viewportHeight > 0 && Number.isFinite(logicalWidth)) {
                    member.size = { w: Math.max(1, logicalWidth), h: 100 };
                    member.sizeSource = "viewport";
                }
            }
        },
        commit(layout) {
            for (const [id, p] of Object.entries(layout.placements || {})) if (members[id]) {
                members[id]!.size = { w: p.w, h: p.h }; members[id]!.sizeSource = "saved";
            }
        },
        include(id, included) { frozen = true; members[id]!.included = included; members[id]!.membershipSource = "operator"; },
        size(id, size) { members[id]!.size = { ...size }; members[id]!.sizeSource = "operator"; },
        freeze() { frozen = true; },
        view() { return clone(members); }
    };
}

export function command({ kind, ids, rows, columns, gap, padding, sizing, orientation, holes, releases, sizes, revisions, angles }: GridCommandInput): GridCommand {
    if (!["logical", "physical"].includes(kind)) throw new Error("Choose logical units or measured millimetres.");
    if (![rows, columns].every(n => Number.isInteger(n) && n > 0 && n <= 64)) throw new Error("Rows and columns must be whole numbers from 1 to 64.");
    if (!ids.length || new Set(ids).size !== ids.length) throw new Error("Select at least one tablet, with no duplicate identities.");
    if (ids.length > rows * columns || (!holes && ids.length !== rows * columns)) throw new Error("Select exactly " + (rows * columns) + " tablets or explicitly allow empty trailing cells.");
    if (![gap, padding].every(n => Number.isFinite(n) && n >= 0 && (kind === "physical" || Number.isInteger(n)))) throw new Error("Gap and padding must be nonnegative" + (kind === "logical" ? " whole logical units." : " millimetres."));
    if (!["fixed", "tablets"].includes(sizing) || !["preserve", "auto", "portrait", "landscape"].includes(orientation)) throw new Error("Choose a supported sizing and orientation policy.");
    const result: GridCommand = { kind, device_ids: ids.slice(), rows, columns, gap, padding, sizing, orientation,
        allow_empty_cells: holes, release_unselected: releases.slice() };
    if (kind === "logical") {
        result.logical_sizes = {};
        ids.forEach(id => {
            const size = sizes![id];
            if (!size || ![size.w, size.h].every(n => Number.isInteger(n) && n > 0)) throw new Error("Enter positive whole logical sizes for every selected tablet, including offline reservations.");
            result.logical_sizes![id] = { w: size.w, h: size.h };
        });
    } else {
        result.physical_revisions = {}; result.mount_angles = {};
        ids.forEach(id => {
            if (!revisions![id] || ![revisions![id].profile_revision, revisions![id].calibration_revision].every(n => Number.isInteger(n) && n > 0)) throw new Error("Confirm a model or save measurements for every selected tablet before a measured preview.");
            result.physical_revisions![id] = revisions![id];
            if (angles![id] !== "" && angles![id] !== undefined) {
                const angle = Number(angles![id]);
                if (![0, 90, 180, 270].includes(angle)) throw new Error("Grid mount angles must be 0, 90, 180 or 270 degrees.");
                result.mount_angles![id] = angle;
            }
        });
    }
    return result;
}
