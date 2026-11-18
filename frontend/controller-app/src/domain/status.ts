// Ported unchanged from frontend/controller/operator-state.js, with types added.
// readFence belongs to the session port; stageEditable and stageView are not ported.

import { entries, sameToken, shownSubject } from "./layout";
import type { Config, Device, Slot } from "./layout";

export type TabletState = { status: string; text: string; showing: boolean; online: boolean };

export type RosterStatus = { key: string; word: string; tone: "failure" | "progress" | "quiet" | "ok" };

export type Aggregate = { total: number; showing: number; states: TabletState[] };

export function observeDevice(device: Device, nowMono: number): Device {
  const render = device.render;
  const elapsed = render && Number.isFinite(render.observed_mono) ? Math.max(0, nowMono - render.observed_mono!) : 0;
  return { ...device, ...(render ? { render: { ...render,
    ...(typeof render.age_ms === "number" ? { age_ms: render.age_ms + elapsed } : {}), observed_mono: nowMono } } : {}) };
}

export function observeConfig(config: Config, nowMono: number): Config {
  if (!config.runtime || !config.runtime.devices) return config;
  const devices = Object.fromEntries(Object.entries(config.runtime.devices)
    .map(([id, device]) => [id, observeDevice(device, nowMono)]));
  return { ...config, runtime: { ...config.runtime, devices } };
}

export function tabletState(config: Config, id: string, nowMono: number): TabletState {
  const slot = entries(config.layout)[id] as Slot | undefined;
  const device = config.runtime && config.runtime.devices && config.runtime.devices[id];
  const content = config.scene && config.scene.content || {};
  const image = content.type === "image";
  const subject = shownSubject(content);
  const result = (status: string, text: string, showing = false): TabletState => ({ status, text, showing, online: !!device && device.online === true });
  if (!slot) return result("unplaced", "No placement");
  if (!device) return result("unknown", "Missing tablet · spot reserved");
  if (slot.participating === false) return result("excluded", "Excluded from show");
  if (!device.online) return result("offline", "Offline · spot reserved");
  const mapping = device.mapping || {};
  if (mapping.state && mapping.state !== "ready") return result(mapping.state, mapping.reason || mapping.state.replaceAll("_", " "));
  if (config.layout?.kind === "physical" && ((mapping.profile_revision !== undefined && mapping.profile_revision !== slot.profile_revision)
          || (mapping.calibration_revision !== undefined && mapping.calibration_revision !== slot.calibration_revision))) return result("stale", "Active mapping revisions differ from the pinned slot");
  if (device.identify && device.identify.active === true) return result("identifying", "Identify overlay · image obscured");
  if (config.runtime?.presentation?.owner === "playback") return result("playback", "Experimental playback owns the display");
  const render = device.render || {};
  const status = render.state || "unknown";
  if (device.protocol !== 3 || !(device.caps || []).includes("render_ack")) return result("unknown", "No confirmation · update client or check manually");
  if (status === "displayed") {
    const expected = render.expected_token;
    const accepted = render.accepted_token;
    const elapsed = Number.isFinite(render.observed_mono) ? Math.max(0, nowMono - render.observed_mono!) : Infinity;
    const age = typeof render.age_ms === "number" ? render.age_ms + elapsed : Infinity;
    if (render.current !== true || !sameToken(expected, accepted) || !Number.isFinite(age) || age < 0 || age >= 15000
            || expected?.generation !== config.generation || expected?.revision !== config.revision
            || expected?.asset !== (image ? content.asset : null) || mapping.state !== "ready"
            || device.connection_id !== undefined && expected?.connection_id !== device.connection_id) {
      return result("stale", "Previous paint · current " + subject + " unconfirmed");
    }
    return result("displayed", "Reports current " + subject, true);
  }
  const texts: Record<string, string> = { blocked: "Blocked", loading: "Loading " + subject, failed: subject[0]!.toUpperCase() + subject.slice(1) + " failed", hidden: "Page hidden",
    stale: "Confirmation expired", unsupported: "Unsupported client or content", unplaced: "No placement", unknown: "Current " + subject + " unconfirmed" };
  return result(status in texts ? status : "unknown", (texts[status] || texts.unknown!) + (render.reason ? " · " + render.reason : ""));
}

export function needsAttention(item: { showing: boolean; status: string }): boolean {
  return !item.showing && item.status !== "excluded";
}

const WRONG_CONTENT = new Set(["failed", "blocked", "hidden", "unsupported", "unsupported_client", "unsupported_content", "viewport_mismatch", "zoom_changed",
  "mapping_mismatch", "invalid", "invalid_mapping", "stale_calibration", "needs_calibration", "needs_profile", "missing_profile", "missing_calibration"]);

export function rosterStatus(item: { status: string; online: boolean }, { stale = false }: { stale?: boolean } = {}): RosterStatus {
  const result = (key: string, word: string, tone: RosterStatus["tone"]): RosterStatus => ({ key, word, tone });
  if (stale) return result("stale", "Stale", "failure");
  if (item.status === "unplaced") return item.online ? result("not-placed", "Not placed", "progress") : result("offline", "Offline", "quiet");
  if (item.status === "offline" || (item.status === "unknown" && !item.online)) return result("offline", "Offline", "failure");
  if (item.status === "stale") return result("stale", "Stale", "failure");
  if (WRONG_CONTENT.has(item.status)) return result("wrong-content", "Wrong content", "failure");
  return result("connected", "Connected", "ok");
}

export function aggregate(config: Config, nowMs: number): Aggregate {
  const ids = Object.keys(entries(config.layout)).filter(id => (entries(config.layout)[id] as Slot | undefined)?.participating !== false);
  const states = ids.map(id => tabletState(config, id, nowMs));
  return { total: ids.length, showing: states.filter(item => item.showing).length, states };
}
