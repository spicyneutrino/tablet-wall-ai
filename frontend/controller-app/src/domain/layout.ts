// Ported unchanged from frontend/controller/operator-state.js, with types added.
// stageEditable and stageView are not ported (they need frontend/controller/operator-composition.js).
// readFence belongs to the session port.

export type Rect = { x: number; y: number; width: number; height: number };
export type Bezel = { top: number; right: number; bottom: number; left: number };
export type Sizing = { mode: "fixed" | "tablets"; padding: number };

export type Placement = { x: number; y: number; w: number; h: number; bezel: Bezel };

export type Slot = {
  center_x_mm?: number;
  center_y_mm?: number;
  mount_angle?: number;
  nudge_x_mm?: number;
  nudge_y_mm?: number;
  profile_revision?: number;
  calibration_revision?: number;
  participating?: boolean;
};

export type Layout = {
  kind?: "logical" | "physical";
  width?: number;
  height?: number;
  bounds?: Rect;
  placements?: Record<string, Placement>;
  slots?: Record<string, Slot>;
  sizing?: Sizing;
};

export type LogicalLayout = Layout & {
  kind: "logical";
  width: number;
  height: number;
  placements: Record<string, Placement>;
  sizing: Sizing;
};

export type SceneContent = { type?: string; asset?: string | null };

export type Token = Record<string, unknown>;

export type RenderEvidence = {
  state?: string;
  current?: boolean;
  age_ms?: number;
  observed_mono?: number;
  expected_token?: Token;
  accepted_token?: Token;
  reason?: string;
};

export type Mapping = { state?: string; reason?: string; profile_revision?: number; calibration_revision?: number };

export type IdentifyState = { active?: boolean; state?: string };

export type Device = {
  online?: boolean;
  protocol?: number;
  caps?: string[];
  mapping?: Mapping;
  render?: RenderEvidence;
  identify?: IdentifyState;
  connection_id?: string;
  number?: number | null;
  label?: string;
};

export type Config = {
  generation?: string;
  revision?: number;
  layout?: Layout;
  scene?: { content?: SceneContent };
  runtime?: { devices?: Record<string, Device>; presentation?: { owner?: string } };
};

export type RegistrationCounts = { registered: number; online: number; retained: number };

export type FitTransform = { x: number; y: number; width: number; height: number; scale: number; cropX: number; cropY: number };

export type FitContent = { intrinsicWidth?: unknown; intrinsicHeight?: unknown; fit?: string };

export type ArrangeOptions = {
  columns: number;
  rows?: number;
  gap: number;
  tile?: boolean;
  preserveAspect?: boolean;
  aspects?: Record<string, number>;
};

export type RosterEntry = { number?: number | null; label?: string };

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

// Physical layouts hold slots and logical layouts hold placements. Both kinds are
// read through this accessor by the tagged controller, so the entry type is loose.
export function entries(layout: Layout | null | undefined): Record<string, Slot | Placement> {
  return layout && (layout.kind === "physical" ? layout.slots : layout.placements) || {};
}

export function layoutSignature(layout: Layout | null | undefined): string {
  if (!layout) return "";
  if (layout.kind === "logical") return JSON.stringify({ kind: "logical", width: layout.width, height: layout.height, placements: Object.entries(layout.placements || {}).sort(), sizing: layout.sizing });
  const bounds: Partial<Rect> = layout.bounds || {};
  const slots: Record<string, Slot> = layout.slots || {};
  return JSON.stringify({
    bounds: [bounds.x, bounds.y, bounds.width, bounds.height],
    sizing: layout.sizing || { mode: "fixed", padding: 0 },
    slots: Object.keys(slots).sort().map(function (id) {
      const slot = slots[id]!;
      return [
        id,
        slot.center_x_mm,
        slot.center_y_mm,
        slot.mount_angle,
        slot.nudge_x_mm,
        slot.nudge_y_mm,
        slot.profile_revision,
        slot.calibration_revision,
        slot.participating !== false,
      ];
    }),
  });
}

export function registrationCounts(config: Config | null | undefined): RegistrationCounts | null {
  const devices = config && config.runtime && config.runtime.devices;
  if (!devices || typeof devices !== "object" || Array.isArray(devices)) return null;
  const ids = Object.keys(devices);
  return {
    registered: ids.length,
    online: ids.filter(id => devices[id]?.online === true).length,
    retained: Object.keys(entries(config?.layout)).filter(id => !Object.prototype.hasOwnProperty.call(devices, id)).length,
  };
}

export function layoutDraft(layout: Layout | null | undefined): Layout {
  if (!layout || !["physical", "logical", undefined].includes(layout.kind)) throw new Error("Unsupported layout. Update the console before editing.");
  const draft = clone(layout);
  draft.kind = draft.kind || "logical";
  draft.sizing = draft.sizing || { mode: "fixed", padding: 0 };
  // Existing physical editing and experimental playback read slots on both kinds.
  if (draft.kind === "logical") draft.slots = {};
  return draft;
}

export function bounds(layout: Layout): Rect {
  return layout.kind === "physical" ? layout.bounds! : { x: 0, y: 0, width: layout.width!, height: layout.height! };
}

export function fitTransform(layout: Layout, content: FitContent): FitTransform | null {
  const b = bounds(layout);
  const width = content.intrinsicWidth as number, height = content.intrinsicHeight as number;
  if (![b.width, b.height, width, height].every(n => typeof n === "number" && Number.isFinite(n) && n > 0)) return null;
  const scale = (content.fit === "contain" ? Math.min : Math.max)(b.width / width, b.height / height);
  return { x: b.x + (b.width - width * scale) / 2, y: b.y + (b.height - height * scale) / 2,
    width: width * scale, height: height * scale, scale,
    cropX: Math.max(0, 1 - b.width / (width * scale)),
    cropY: Math.max(0, 1 - b.height / (height * scale)) };
}

export function fitLogical(layout: Layout): void {
  const list = Object.values(layout.placements || {});
  if (layout.kind !== "logical" || layout.sizing!.mode !== "tablets" || !list.length) return;
  const left = Math.min(...list.map(p => p.x)), top = Math.min(...list.map(p => p.y));
  const right = Math.max(...list.map(p => p.x + p.w)), bottom = Math.max(...list.map(p => p.y + p.h));
  const padding = layout.sizing!.padding;
  for (const p of list) { p.x += padding - left; p.y += padding - top; }
  layout.width = Math.max(1, right - left + padding * 2);
  layout.height = Math.max(1, bottom - top + padding * 2);
}

export function arrangeLogical(layout: LogicalLayout, ids: string[], options: ArrangeOptions): LogicalLayout {
  const { columns, rows = Math.ceil(ids.length / options.columns), gap, tile = false, preserveAspect = true, aspects = {} } = options;
  if (!Number.isInteger(columns) || columns < 1 || !Number.isInteger(rows) || rows < 1 || !Number.isInteger(gap) || gap < 0) throw new Error("Use positive whole rows and columns and a nonnegative whole gap.");
  if (!ids.length) throw new Error("No tablets match this scope.");
  if (ids.length > rows * columns) throw new Error("The chosen tablets do not fit in these rows and columns.");
  const result = clone(layout);
  const cellW = Math.floor((layout.width - gap * (columns - 1)) / columns);
  const cellH = Math.floor((layout.height - gap * (rows - 1)) / rows);
  if (tile && (cellW < 1 || cellH < 1)) throw new Error("The gap leaves no room for tablet cells.");
  let y = result.sizing.padding || 0;
  for (let row = 0; row < rows; row += 1) {
    let x = result.sizing.padding || 0, height = 0;
    for (let col = 0; col < columns; col += 1) {
      const id = ids[row * columns + col];
      if (!id) break;
      const p = result.placements[id];
      if (!p) throw new Error("The captured tablet order changed. Review it again.");
      if (tile) {
        const b = p.bezel, ratio = aspects[id] || (p.w - b.left - b.right) / (p.h - b.top - b.bottom);
        let w = cellW, h = cellH;
        if (preserveAspect) {
          const activeW = cellW - b.left - b.right, activeH = cellH - b.top - b.bottom;
          const contentW = Math.min(activeW, activeH * ratio);
          w = Math.round(contentW + b.left + b.right);
          h = Math.round(contentW / ratio + b.top + b.bottom);
        }
        if (w <= b.left + b.right || h <= b.top + b.bottom) throw new Error("The tile is smaller than its bezels. Increase the wall or reduce the gap.");
        p.w = w; p.h = h;
        p.x = Math.round(col * (cellW + gap) + (cellW - w) / 2);
        p.y = Math.round(row * (cellH + gap) + (cellH - h) / 2);
      } else { p.x = x; p.y = y; x += p.w + gap; height = Math.max(height, p.h); }
    }
    y += height + gap;
  }
  fitLogical(result);
  return result;
}

export function rotateLogical(p: Placement): Placement {
  const b = p.bezel;
  return { ...p, x: Math.round(p.x + (p.w - p.h) / 2), y: Math.round(p.y + (p.h - p.w) / 2),
    w: p.h, h: p.w, bezel: { top: b.left, right: b.top, bottom: b.right, left: b.bottom } };
}

export function compareIds(roster: Record<string, RosterEntry>, labels: Record<string, string | undefined>, a: string, b: string): number {
  const number = (id: string) => {
    const value = roster[id]?.number;
    return Number.isInteger(value) && (value as number) > 0 ? (value as number) : Infinity;
  };
  const label = (id: string) => String(labels[id] || roster[id]?.label || "").trim().toLowerCase();
  return number(a) - number(b) || label(a).localeCompare(label(b)) || a.localeCompare(b);
}

export function sameToken(a: Token | null | undefined, b: Token | null | undefined): boolean {
  return !!a && !!b && ["connection_id", "generation", "revision", "render_seq", "mapping_revision", "asset"]
    .every(key => a[key] !== undefined && a[key] === b[key]);
}

export function shownSubject(content: SceneContent | null | undefined): string {
  const type = content && content.type;
  return type === "image" ? "image" : type === "color" ? "colour" : type === "calibration" ? "wall grid" : "content";
}
