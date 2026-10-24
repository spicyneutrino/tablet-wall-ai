"use strict";

(function () {
    const API_CONFIG = "/api/v3/config";
    const API_DEVICES = "/devices";
    const API_LAYOUT = "/api/v3/layout";
    const API_LAYOUTS = "/api/v3/layouts";
    const REQUEST_TIMEOUT_MS = 10000;
    const SVG_NS = "http://www.w3.org/2000/svg";
    const STAGE_W = 720;
    const STAGE_H = 480;
    const STAGE_MARGIN = 28;
    const DRAG_THRESHOLD_PX = 3;
    const HISTORY_LIMIT = 80;

    const el = {
        wallRevision: document.getElementById("wall-revision"),
        wallGeneration: document.getElementById("wall-generation"),
        etagValue: document.getElementById("etag-value"),
        etagState: document.getElementById("etag-state"),
        layoutKindNote: document.getElementById("layout-kind-note"),
        btnUndo: document.getElementById("btn-undo"),
        btnRedo: document.getElementById("btn-redo"),
        draftFlag: document.getElementById("draft-flag"),
        btnApply: document.getElementById("btn-apply"),
        btnCancel: document.getElementById("btn-cancel"),
        btnReload: document.getElementById("btn-reload"),
        errorText: document.getElementById("error-text"),
        conflictPanel: document.getElementById("conflict-panel"),
        conflictText: document.getElementById("conflict-text"),
        btnConflictReload: document.getElementById("btn-conflict-reload"),
        stageSvg: document.getElementById("stage-svg"),
        stageScale: document.getElementById("stage-scale"),
        deviceCount: document.getElementById("device-count"),
        deviceList: document.getElementById("device-list"),
        deviceEmpty: document.getElementById("device-empty"),
        boundsX: document.getElementById("bounds-x"),
        boundsY: document.getElementById("bounds-y"),
        boundsWidth: document.getElementById("bounds-width"),
        boundsHeight: document.getElementById("bounds-height"),
        boundsNote: document.getElementById("bounds-note"),
        btnLayoutsRefresh: document.getElementById("btn-layouts-refresh"),
        layoutSaveForm: document.getElementById("layout-save-form"),
        layoutName: document.getElementById("layout-name"),
        btnLayoutSave: document.getElementById("btn-layout-save"),
        layoutMsg: document.getElementById("layout-msg"),
        savedLayouts: document.getElementById("saved-layouts"),
        savedEmpty: document.getElementById("saved-empty"),
        inspectorEmpty: document.getElementById("inspector-empty"),
        inspectorBody: document.getElementById("inspector-body"),
        selectedTitle: document.getElementById("selected-title"),
        selectedId: document.getElementById("selected-id"),
        selectedState: document.getElementById("selected-state"),
        selectedNote: document.getElementById("selected-note"),
        slotCenterX: document.getElementById("slot-center-x"),
        slotCenterY: document.getElementById("slot-center-y"),
        slotAngle: document.getElementById("slot-angle"),
        slotNudgeX: document.getElementById("slot-nudge-x"),
        slotNudgeY: document.getElementById("slot-nudge-y"),
        btnRotate: document.getElementById("btn-rotate"),
        btnDeleteSlot: document.getElementById("btn-delete-slot"),
        btnNudgeXMinus: document.getElementById("btn-nudge-x-minus"),
        btnNudgeXPlus: document.getElementById("btn-nudge-x-plus"),
        btnNudgeYMinus: document.getElementById("btn-nudge-y-minus"),
        btnNudgeYPlus: document.getElementById("btn-nudge-y-plus"),
        inspectorMissing: document.getElementById("inspector-missing"),
        slotMissingText: document.getElementById("slot-missing-text"),
        btnAddSlot: document.getElementById("btn-add-slot"),
        deviceCardEmpty: document.getElementById("device-card-empty"),
        deviceCardBody: document.getElementById("device-card-body"),
        deviceCardName: document.getElementById("device-card-name"),
        deviceCardId: document.getElementById("device-card-id"),
        deviceCardCal: document.getElementById("device-card-cal"),
        profileForm: document.getElementById("profile-form"),
        profileCurrent: document.getElementById("profile-current"),
        profileActiveWidth: document.getElementById("profile-active-width"),
        profileActiveHeight: document.getElementById("profile-active-height"),
        profileBezelTop: document.getElementById("profile-bezel-top"),
        profileBezelRight: document.getElementById("profile-bezel-right"),
        profileBezelBottom: document.getElementById("profile-bezel-bottom"),
        profileBezelLeft: document.getElementById("profile-bezel-left"),
        profileLabel: document.getElementById("profile-label"),
        profileProvenance: document.getElementById("profile-provenance"),
        profilePixelWidth: document.getElementById("profile-pixel-width"),
        profilePixelHeight: document.getElementById("profile-pixel-height"),
        profileMsg: document.getElementById("profile-msg"),
        btnProfileSave: document.getElementById("btn-profile-save"),
        calibrationForm: document.getElementById("calibration-form"),
        calibrationCurrent: document.getElementById("calibration-current"),
        calProfileRevision: document.getElementById("cal-profile-revision"),
        calViewportWidth: document.getElementById("cal-viewport-width"),
        calViewportHeight: document.getElementById("cal-viewport-height"),
        calDpr: document.getElementById("cal-dpr"),
        calOrientation: document.getElementById("cal-orientation"),
        calMode: document.getElementById("cal-mode"),
        calQuarterTurn: document.getElementById("cal-quarter-turn"),
        calAnchorEdge: document.getElementById("cal-anchor-edge"),
        calOffsetX: document.getElementById("cal-offset-x"),
        calOffsetY: document.getElementById("cal-offset-y"),
        calMmCssX: document.getElementById("cal-mm-css-x"),
        calMmCssY: document.getElementById("cal-mm-css-y"),
        calUncertainty: document.getElementById("cal-uncertainty"),
        calMethod: document.getElementById("cal-method"),
        calibrationMsg: document.getElementById("calibration-msg"),
        btnCalibrationSave: document.getElementById("btn-calibration-save"),
        statusStamp: document.getElementById("status-stamp"),
        pageStatus: document.getElementById("page-status")
    };

    const state = {
        etag: null,
        etagState: "missing",
        revision: null,
        generation: null,
        layoutKind: null,
        base: null,
        draft: null,
        displays: [],
        calibrations: [],
        roster: {},
        savedLayouts: [],
        selectedId: null,
        undo: [],
        redo: [],
        stage: { scale: 1, offX: 0, offY: 0, step: 50 },
        drag: null,
        formDeviceId: null,
        profileDirty: false,
        calDirty: false,
        busy: false
    };

    const profileCache = new Map();
    const calibrationCache = new Map();
    const deviceRows = new Map();

    class ApiError extends Error {
        constructor(status, detail) {
            super(detail);
            this.name = "ApiError";
            this.status = status;
            this.detail = detail;
        }
    }

    class ValidationError extends Error {
        constructor(message) {
            super(message);
            this.name = "ValidationError";
        }
    }

    /* ---------------------------------------------------------------- *
     * Small helpers
     * ---------------------------------------------------------------- */

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function num(value) {
        if (typeof value === "number") return Number.isFinite(value) ? value : null;
        if (typeof value !== "string" || value.trim() === "") return null;
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function roundTo(value, digits) {
        const factor = Math.pow(10, digits);
        return Math.round((value + Number.EPSILON) * factor) / factor;
    }

    function formatNumber(value, digits) {
        if (value === null || value === undefined || value === "") return "";
        if (typeof value === "string" && value.trim() === "") return "";
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return "";
        const rounded = roundTo(parsed, digits);
        return String(Object.is(rounded, -0) ? 0 : rounded);
    }

    function shortId(id) {
        return id ? String(id).slice(0, 8) : "—";
    }

    function finiteOr(value, fallback) {
        return Number.isFinite(Number(value)) ? Number(value) : fallback;
    }

    function setInputValue(input, value) {
        if (!input || document.activeElement === input) return;
        input.value = value === null || value === undefined ? "" : String(value);
    }

    function setSelectValue(select, value) {
        if (!select) return;
        select.value = String(value);
        if (select.value !== String(value)) select.selectedIndex = 0;
    }

    function markInvalid(input, invalid) {
        if (!input) return;
        if (invalid) input.setAttribute("aria-invalid", "true");
        else input.removeAttribute("aria-invalid");
    }

    function cacheKey(id, revision) {
        return String(id) + ":" + String(revision);
    }

    function rememberProfile(profile) {
        if (profile && profile.device_id && profile.revision !== undefined) {
            profileCache.set(cacheKey(profile.device_id, profile.revision), profile);
        }
    }

    function rememberCalibration(calibration) {
        if (calibration && calibration.device_id && calibration.revision !== undefined) {
            calibrationCache.set(cacheKey(calibration.device_id, calibration.revision), calibration);
        }
    }

    function latestProfile(id) {
        return state.displays.find(function (profile) {
            return profile.device_id === id;
        }) || null;
    }

    function profileFor(id, revision) {
        return profileCache.get(cacheKey(id, revision)) || null;
    }

    function latestCalibration(id) {
        return state.calibrations.find(function (calibration) {
            return calibration.device_id === id;
        }) || null;
    }

    function calibrationFor(id, revision) {
        return calibrationCache.get(cacheKey(id, revision)) || null;
    }

    function calibrationForProfile(id, revision) {
        let best = null;
        calibrationCache.forEach(function (calibration) {
            if (calibration.device_id !== id) return;
            if (calibration.profile_revision !== revision) return;
            if (!best || calibration.revision > best.revision) best = calibration;
        });
        return best;
    }

    function calibrationStatus(profile, calibration) {
        if (!profile) return { text: "no profile", kind: "info" };
        if (!calibration) return { text: "no calibration", kind: "warn" };
        if (calibration.profile_revision !== profile.revision) {
            return {
                text: "calib r" + calibration.revision + " stale",
                kind: "warn"
            };
        }
        return { text: "calib r" + calibration.revision + " valid", kind: "ok" };
    }

    function validPair(id) {
        const profile = latestProfile(id);
        if (!profile) return null;
        const calibration = calibrationForProfile(id, profile.revision);
        if (!calibration) return null;
        return { profile: profile, calibration: calibration };
    }

    function isDirty() {
        if (!state.base || !state.draft) return false;
        return layoutSignature(state.base) !== layoutSignature(state.draft);
    }

    function layoutSignature(layout) {
        if (!layout) return "";
        const bounds = layout.bounds || {};
        const slots = layout.slots || {};
        return JSON.stringify({
            bounds: [bounds.x, bounds.y, bounds.width, bounds.height],
            slots: Object.keys(slots).sort().map(function (id) {
                const slot = slots[id];
                return [
                    id,
                    slot.center_x_mm,
                    slot.center_y_mm,
                    slot.mount_angle,
                    slot.nudge_x_mm,
                    slot.nudge_y_mm,
                    slot.profile_revision,
                    slot.calibration_revision,
                    slot.participating !== false
                ];
            })
        });
    }

    function selectedSlot() {
        if (!state.draft || !state.selectedId) return null;
        return state.draft.slots[state.selectedId] || null;
    }

    function physicalFromConfig(layout) {
        if (layout && layout.kind === "physical") {
            const bounds = normalizeBounds(layout.bounds);
            const slots = layout.slots && typeof layout.slots === "object"
                ? clone(layout.slots) : {};
            return { kind: "physical", bounds: bounds, slots: slots };
        }
        const width = layout && num(layout.width) > 0 ? Number(layout.width) : 1200;
        const height = layout && num(layout.height) > 0 ? Number(layout.height) : 800;
        return {
            kind: "physical",
            bounds: { x: 0, y: 0, width: width, height: height },
            slots: {}
        };
    }

    function normalizeBounds(bounds) {
        const source = bounds || {};
        return {
            x: finiteOr(source.x, 0),
            y: finiteOr(source.y, 0),
            width: finiteOr(source.width, 1200) > 0 ? finiteOr(source.width, 1200) : 1200,
            height: finiteOr(source.height, 800) > 0 ? finiteOr(source.height, 800) : 800
        };
    }

    function bodyMetrics(profile) {
        if (!profile) {
            return {
                bodyW: 100, bodyH: 60, activeW: 100, activeH: 60,
                activeX: -50, activeY: -30, known: false
            };
        }
        const activeW = finiteOr(profile.active_width_mm, 100) > 0
            ? finiteOr(profile.active_width_mm, 100) : 100;
        const activeH = finiteOr(profile.active_height_mm, 60) > 0
            ? finiteOr(profile.active_height_mm, 60) : 60;
        const bezels = profile.bezels || {};
        const left = Math.max(0, finiteOr(bezels.left, 0));
        const top = Math.max(0, finiteOr(bezels.top, 0));
        const right = Math.max(0, finiteOr(bezels.right, 0));
        const bottom = Math.max(0, finiteOr(bezels.bottom, 0));
        const bodyW = left + activeW + right;
        const bodyH = top + activeH + bottom;
        return {
            bodyW: bodyW,
            bodyH: bodyH,
            activeW: activeW,
            activeH: activeH,
            activeX: -bodyW / 2 + left,
            activeY: -bodyH / 2 + top,
            known: true
        };
    }

    function niceStep(target) {
        if (!Number.isFinite(target) || target <= 0) return 50;
        const exponent = Math.floor(Math.log10(target));
        const base = Math.pow(10, exponent);
        const fraction = target / base;
        let picked;
        if (fraction <= 1) picked = 1;
        else if (fraction <= 2) picked = 2;
        else if (fraction <= 5) picked = 5;
        else picked = 10;
        return picked * base;
    }

    function deviceLabel(id, profile) {
        return profile && profile.label ? profile.label : "Tablet " + shortId(id);
    }

    function deviceEntries() {
        const ids = new Set();
        Object.keys(state.roster).forEach(function (id) { ids.add(id); });
        state.displays.forEach(function (profile) { ids.add(profile.device_id); });
        if (state.draft && state.draft.slots) {
            Object.keys(state.draft.slots).forEach(function (id) { ids.add(id); });
        }
        const entries = [];
        ids.forEach(function (id) {
            const profile = latestProfile(id);
            entries.push({
                id: id,
                profile: profile,
                calibration: latestCalibration(id),
                slot: state.draft && state.draft.slots ? state.draft.slots[id] || null : null,
                label: deviceLabel(id, profile)
            });
        });
        entries.sort(function (left, right) {
            const byLabel = left.label.localeCompare(right.label);
            return byLabel !== 0 ? byLabel : left.id.localeCompare(right.id);
        });
        return entries;
    }

    /* ---------------------------------------------------------------- *
     * Status and messages
     * ---------------------------------------------------------------- */

    function announce(text, kind) {
        el.pageStatus.textContent = text;
        if (kind) el.pageStatus.dataset.kind = kind;
        else el.pageStatus.removeAttribute("data-kind");
        el.statusStamp.textContent = new Date().toLocaleTimeString([], {
            hour: "2-digit", minute: "2-digit", second: "2-digit"
        });
    }

    function showError(text) {
        el.errorText.textContent = text;
        el.errorText.hidden = false;
    }

    function clearError() {
        el.errorText.textContent = "";
        el.errorText.hidden = true;
    }

    function setMsg(node, text, kind) {
        if (!node) return;
        if (!text) {
            node.textContent = "";
            node.hidden = true;
            node.removeAttribute("data-kind");
            return;
        }
        node.textContent = text;
        node.dataset.kind = kind || "info";
        node.hidden = false;
    }

    function clearMsg(node) {
        setMsg(node, "", null);
    }

    function showConflict(detail) {
        el.conflictText.textContent = detail
            + " Your draft is kept. Reload the configuration to continue; reloading discards the draft after you confirm.";
        el.conflictPanel.hidden = false;
        state.etagState = "stale";
        syncMeta();
        syncDraftUi();
    }

    function hideConflict() {
        el.conflictPanel.hidden = true;
        el.conflictText.textContent = "";
    }

    function errorDetail(error) {
        if (error && typeof error.detail === "string" && error.detail) return error.detail;
        if (error && typeof error.message === "string" && error.message) return error.message;
        return "The request failed.";
    }

    function handleWriteError(error, messageNode) {
        const detail = errorDetail(error);
        if (error && error.status === 412) {
            showConflict(detail);
        } else if (error && error.status === 428) {
            showError("Write rejected: the If-Match header was missing (428). " + detail);
        } else {
            showError(detail);
        }
        if (messageNode) setMsg(messageNode, detail, "err");
        announce(detail, "err");
    }

    /* ---------------------------------------------------------------- *
     * HTTP
     * ---------------------------------------------------------------- */

    function detailFromPayload(payload, status) {
        if (!payload || payload.detail === undefined) return "HTTP " + status;
        const detail = payload.detail;
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail)) {
            return detail.map(function (item) {
                if (typeof item === "string") return item;
                if (!item || typeof item !== "object") return String(item);
                const where = Array.isArray(item.loc) ? item.loc.join(".") : "";
                const msg = item.msg || JSON.stringify(item);
                return where ? where + ": " + msg : msg;
            }).join("; ");
        }
        if (typeof detail === "object") return JSON.stringify(detail);
        return String(detail);
    }

    async function api(method, path, body, options) {
        const settings = options || {};
        const init = { method: method, headers: { "Accept": "application/json" } };
        if (body !== undefined) {
            init.headers["Content-Type"] = "application/json";
            init.body = JSON.stringify(body);
        }
        if (settings.etag) {
            if (!state.etag) throw new ApiError(428, "No configuration ETag is loaded.");
            init.headers["If-Match"] = state.etag;
        }

        let timer = null;
        if (typeof AbortController === "function") {
            const controller = new AbortController();
            init.signal = controller.signal;
            timer = setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS);
        }

        let response;
        try {
            response = await fetch(path, init);
        } catch (error) {
            throw new ApiError(0, error && error.name === "AbortError"
                ? "request timed out" : "server unreachable");
        } finally {
            if (timer) clearTimeout(timer);
        }

        let payload = null;
        try {
            payload = await response.json();
        } catch (error) {
            payload = null;
        }
        if (!response.ok) {
            throw new ApiError(response.status, detailFromPayload(payload, response.status));
        }
        return payload;
    }

    /* ---------------------------------------------------------------- *
     * Configuration load and draft lifecycle
     * ---------------------------------------------------------------- */

    function ingestConfig(config, options) {
        if (!config || typeof config !== "object") {
            throw new Error("The server returned an empty configuration.");
        }
        const settings = options || {};
        state.etag = typeof config.etag === "string" && config.etag ? config.etag : null;
        state.etagState = state.etag ? "current" : "missing";
        state.revision = config.revision === undefined ? null : config.revision;
        state.generation = config.generation === undefined ? null : config.generation;
        state.layoutKind = config.layout && config.layout.kind ? config.layout.kind : null;
        state.displays = Array.isArray(config.displays) ? config.displays : [];
        state.calibrations = Array.isArray(config.calibrations) ? config.calibrations : [];
        state.displays.forEach(rememberProfile);
        state.calibrations.forEach(rememberCalibration);
        state.base = physicalFromConfig(config.layout);
        state.draft = clone(state.base);
        if (settings.resetHistory !== false) {
            state.undo = [];
            state.redo = [];
        }
        state.drag = null;
        state.formDeviceId = null;
        state.profileDirty = false;
        state.calDirty = false;
        ensureSelection();
        hideConflict();
        renderAll();
    }

    function ensureSelection() {
        const ids = new Set();
        Object.keys(state.roster).forEach(function (id) { ids.add(id); });
        state.displays.forEach(function (profile) { ids.add(profile.device_id); });
        if (state.draft && state.draft.slots) {
            Object.keys(state.draft.slots).forEach(function (id) { ids.add(id); });
        }
        if (state.selectedId && ids.has(state.selectedId)) return;
        const slotIds = state.draft && state.draft.slots
            ? Object.keys(state.draft.slots).sort() : [];
        if (slotIds.length) {
            state.selectedId = slotIds[0];
        } else if (state.displays.length) {
            state.selectedId = state.displays.slice().sort(function (a, b) {
                return a.device_id.localeCompare(b.device_id);
            })[0].device_id;
        } else {
            const rosterIds = Object.keys(state.roster).sort();
            state.selectedId = rosterIds.length ? rosterIds[0] : null;
        }
    }

    async function loadConfig() {
        if (state.busy) return false;
        state.busy = true;
        syncDraftUi();
        try {
            const results = await Promise.all([
                api("GET", API_CONFIG),
                api("GET", API_DEVICES)
            ]);
            state.roster = results[1] && typeof results[1] === "object" ? results[1] : {};
            ingestConfig(results[0], { resetHistory: true });
            clearError();
            announce("Loaded wall revision " + (state.revision === null ? "?" : state.revision) + ".", "ok");
            return true;
        } catch (error) {
            const detail = errorDetail(error);
            showError("Could not load the configuration: " + detail);
            announce("Could not load the configuration.", "err");
            return false;
        } finally {
            state.busy = false;
            syncDraftUi();
        }
    }

    async function reloadConfigWithConfirm() {
        if (state.busy) return;
        if (isDirty() && !window.confirm("Reload the configuration and discard the unapplied draft?")) {
            return;
        }
        await loadConfig();
    }

    function renderAll() {
        syncMeta();
        syncDraftUi();
        renderDeviceList();
        renderStage();
        populateDeviceCard(true);
    }

    function syncMeta() {
        el.wallRevision.textContent = state.revision === null || state.revision === undefined
            ? "–" : String(state.revision);
        el.wallGeneration.textContent = state.generation || "–";
        if (state.etag) {
            el.etagValue.textContent = state.etag.slice(0, 12) + "…";
            el.etagValue.title = state.etag;
        } else {
            el.etagValue.textContent = "–";
            el.etagValue.title = "";
        }

        if (state.etagState === "current") {
            el.etagState.textContent = "current";
            el.etagState.dataset.kind = "ok";
        } else if (state.etagState === "stale") {
            el.etagState.textContent = "stale — reload";
            el.etagState.dataset.kind = "err";
        } else {
            el.etagState.textContent = "missing";
            el.etagState.dataset.kind = "warn";
        }

        if (state.layoutKind === "physical") {
            el.layoutKindNote.textContent = "Editing the committed physical layout. Apply sends bounds and every slot in one write.";
            el.boundsNote.textContent = "The committed layout uses these bounds. Values are millimetres.";
        } else if (state.layoutKind === "logical") {
            el.layoutKindNote.textContent = "The active wall is still logical. This draft starts from its dimensions; applying it replaces the logical layout with a physical one.";
            el.boundsNote.textContent = "The active wall is logical, so its dimensions only seed this draft. Check the millimetre values before applying.";
        } else {
            el.layoutKindNote.textContent = "No wall configuration is loaded.";
            el.boundsNote.textContent = "";
        }
    }

    function syncBoundsInputs() {
        if (!state.draft || !state.draft.bounds) return;
        const bounds = state.draft.bounds;
        setInputValue(el.boundsX, formatNumber(bounds.x, 3));
        setInputValue(el.boundsY, formatNumber(bounds.y, 3));
        setInputValue(el.boundsWidth, formatNumber(bounds.width, 3));
        setInputValue(el.boundsHeight, formatNumber(bounds.height, 3));
    }

    function syncDraftUi() {
        if (!state.draft) {
            el.draftFlag.textContent = "No draft";
            el.draftFlag.dataset.dirty = "false";
            el.btnApply.disabled = true;
            el.btnCancel.disabled = true;
            el.btnUndo.disabled = true;
            el.btnRedo.disabled = true;
            updateSavedButtons();
            syncInspector();
            return;
        }

        const dirty = isDirty();
        if (dirty) {
            el.draftFlag.textContent = "Unapplied changes";
            el.draftFlag.dataset.dirty = "true";
        } else if (state.layoutKind === "physical") {
            el.draftFlag.textContent = "Matches the committed layout";
            el.draftFlag.dataset.dirty = "false";
        } else {
            el.draftFlag.textContent = "Draft not applied";
            el.draftFlag.dataset.dirty = "false";
        }

        el.btnApply.disabled = state.busy || !state.etag || (!dirty && state.layoutKind === "physical");
        el.btnCancel.disabled = state.busy || !dirty;
        el.btnUndo.disabled = state.busy || state.undo.length === 0;
        el.btnRedo.disabled = state.busy || state.redo.length === 0;
        el.btnReload.disabled = state.busy;
        el.btnProfileSave.disabled = state.busy;
        el.btnCalibrationSave.disabled = state.busy;
        el.btnLayoutSave.disabled = state.busy;
        el.btnLayoutsRefresh.disabled = state.busy;
        el.btnConflictReload.disabled = state.busy;

        syncBoundsInputs();
        updateSavedButtons();
        syncInspector();
    }

    function pushUndo(before) {
        if (!before) return;
        if (layoutSignature(before) === layoutSignature(state.draft)) return;
        state.undo.push(before);
        if (state.undo.length > HISTORY_LIMIT) state.undo.shift();
        state.redo.length = 0;
    }

    function afterDraftChange() {
        syncDraftUi();
        renderStage();
    }

    function mutateDraft(mutator) {
        if (!state.draft || state.busy) return false;
        const before = clone(state.draft);
        mutator(state.draft);
        if (layoutSignature(before) === layoutSignature(state.draft)) return false;
        pushUndo(before);
        afterDraftChange();
        return true;
    }

    function undoDraft() {
        if (state.busy || state.undo.length === 0) return;
        const current = clone(state.draft);
        state.draft = state.undo.pop();
        state.redo.push(current);
        afterDraftChange();
        announce("Undid the last layout change.");
    }

    function redoDraft() {
        if (state.busy || state.redo.length === 0) return;
        const current = clone(state.draft);
        state.draft = state.redo.pop();
        state.undo.push(current);
        afterDraftChange();
        announce("Redid the layout change.");
    }

    function cancelDraft() {
        if (!state.draft || !state.base || state.busy) return;
        const before = clone(state.draft);
        state.draft = clone(state.base);
        state.drag = null;
        pushUndo(before);
        afterDraftChange();
        announce("Draft restored from the committed layout.");
    }

    async function applyLayout() {
        if (!state.draft || !state.etag || state.busy) return;
        clearError();
        setBusy(true);
        try {
            const body = {
                bounds: clone(state.draft.bounds),
                slots: clone(state.draft.slots)
            };
            const payload = await api("PUT", API_LAYOUT, body, { etag: true });
            ingestConfig(payload, { resetHistory: true });
            clearError();
            hideConflict();
            announce("Layout applied at revision " + (state.revision === null ? "?" : state.revision) + ".", "ok");
        } catch (error) {
            handleWriteError(error, null);
        } finally {
            setBusy(false);
        }
    }

    function setBusy(busy) {
        state.busy = busy;
        syncDraftUi();
    }

    /* ---------------------------------------------------------------- *
     * Stage
     * ---------------------------------------------------------------- */

    function svgNode(tag, attributes) {
        const node = document.createElementNS(SVG_NS, tag);
        if (attributes) {
            Object.keys(attributes).forEach(function (key) {
                const value = attributes[key];
                if (value !== undefined && value !== null) node.setAttribute(key, String(value));
            });
        }
        return node;
    }

    function computeStage() {
        const bounds = state.draft && state.draft.bounds
            ? state.draft.bounds : { x: 0, y: 0, width: 1200, height: 800 };
        const width = bounds.width > 0 ? bounds.width : 1200;
        const height = bounds.height > 0 ? bounds.height : 800;
        const scale = Math.min(
            (STAGE_W - STAGE_MARGIN * 2) / width,
            (STAGE_H - STAGE_MARGIN * 2) / height
        );
        return {
            scale: scale,
            offX: STAGE_W / 2 - (bounds.x + width / 2) * scale,
            offY: STAGE_H / 2 - (bounds.y + height / 2) * scale,
            step: niceStep(56 / scale)
        };
    }

    function focusStageSlot(id) {
        const groups = el.stageSvg.querySelectorAll(".slot");
        for (let index = 0; index < groups.length; index += 1) {
            if (groups[index].dataset.deviceId === id) {
                try { groups[index].focus({ preventScroll: true }); }
                catch (error) { groups[index].focus(); }
                return;
            }
        }
    }

    function renderStage() {
        const svg = el.stageSvg;
        const focused = document.activeElement;
        const focusedSlotId = focused && focused.classList
            && focused.classList.contains("slot") ? focused.dataset.deviceId : null;

        while (svg.firstChild) svg.removeChild(svg.firstChild);

        if (!state.draft) {
            el.stageScale.textContent = "Waiting for the wall.";
            return;
        }

        const bounds = state.draft.bounds;
        const stage = computeStage();
        state.stage = stage;
        const scale = stage.scale;
        const wallX = stage.offX + bounds.x * scale;
        const wallY = stage.offY + bounds.y * scale;
        const wallW = bounds.width * scale;
        const wallH = bounds.height * scale;

        const defs = svgNode("defs");
        const clip = svgNode("clipPath", { id: "wall-clip" });
        clip.appendChild(svgNode("rect", {
            x: wallX, y: wallY, width: wallW, height: wallH
        }));
        defs.appendChild(clip);
        svg.appendChild(defs);

        svg.appendChild(svgNode("rect", {
            x: wallX, y: wallY, width: wallW, height: wallH,
            "class": "wall-bounds", rx: 4
        }));

        const grid = svgNode("g", {
            "class": "wall-grid", "clip-path": "url(#wall-clip)"
        });
        const startX = Math.ceil(bounds.x / stage.step) * stage.step;
        const endX = bounds.x + bounds.width;
        for (let x = startX; x <= endX + 1e-6; x += stage.step) {
            const px = stage.offX + x * scale;
            const major = Math.round(x / stage.step) % 5 === 0;
            grid.appendChild(svgNode("line", {
                x1: px, y1: wallY, x2: px, y2: wallY + wallH,
                "data-major": major ? "true" : "false"
            }));
        }
        const startY = Math.ceil(bounds.y / stage.step) * stage.step;
        const endY = bounds.y + bounds.height;
        for (let y = startY; y <= endY + 1e-6; y += stage.step) {
            const py = stage.offY + y * scale;
            const major = Math.round(y / stage.step) % 5 === 0;
            grid.appendChild(svgNode("line", {
                x1: wallX, y1: py, x2: wallX + wallW, y2: py,
                "data-major": major ? "true" : "false"
            }));
        }
        svg.appendChild(grid);

        const caption = svgNode("text", {
            x: wallX + 6, y: wallY + 15, "class": "wall-caption"
        });
        caption.textContent = formatNumber(bounds.width, 1) + " × "
            + formatNumber(bounds.height, 1) + " mm";
        svg.appendChild(caption);

        const slotIds = Object.keys(state.draft.slots);
        slotIds.sort(function (left, right) {
            const leftSelected = left === state.selectedId ? 1 : 0;
            const rightSelected = right === state.selectedId ? 1 : 0;
            if (leftSelected !== rightSelected) return leftSelected - rightSelected;
            return left.localeCompare(right);
        });

        slotIds.forEach(function (id) {
            const slot = state.draft.slots[id];
            const selected = id === state.selectedId;
            const exactProfile = profileFor(id, slot.profile_revision);
            const profile = exactProfile || latestProfile(id);
            const metrics = bodyMetrics(profile);
            const stale = !exactProfile;
            const centerX = stage.offX
                + (finiteOr(slot.center_x_mm, 0) + finiteOr(slot.nudge_x_mm, 0)) * scale;
            const centerY = stage.offY
                + (finiteOr(slot.center_y_mm, 0) + finiteOr(slot.nudge_y_mm, 0)) * scale;
            const angle = finiteOr(slot.mount_angle, 0);
            const label = deviceLabel(id, profile);

            const group = svgNode("g", {
                "class": "slot",
                "data-device-id": id,
                "data-stale": stale ? "true" : "false",
                "aria-pressed": selected ? "true" : "false",
                "aria-label": label + ", " + formatNumber(metrics.activeW, 1) + " by "
                    + formatNumber(metrics.activeH, 1) + " millimetre active panel. "
                    + (selected ? "Selected." : "Not selected."),
                role: "button",
                tabindex: "0",
                transform: "translate(" + centerX + " " + centerY + ") rotate(" + angle + ")"
            });

            const title = svgNode("title");
            title.textContent = label + " · " + shortId(id) + " · centre "
                + formatNumber(slot.center_x_mm, 1) + ", "
                + formatNumber(slot.center_y_mm, 1) + " mm · mount "
                + formatNumber(angle, 1) + "°";
            group.appendChild(title);

            group.appendChild(svgNode("rect", {
                "class": "slot-hit",
                x: -metrics.bodyW / 2 * scale - 8,
                y: -metrics.bodyH / 2 * scale - 8,
                width: (metrics.bodyW + 16) * scale,
                height: (metrics.bodyH + 16) * scale
            }));

            group.appendChild(svgNode("rect", {
                "class": "slot-body",
                x: -metrics.bodyW / 2 * scale,
                y: -metrics.bodyH / 2 * scale,
                width: metrics.bodyW * scale,
                height: metrics.bodyH * scale,
                rx: Math.min(4, Math.min(metrics.bodyW, metrics.bodyH) * scale * 0.08)
            }));

            group.appendChild(svgNode("rect", {
                "class": "slot-active",
                x: metrics.activeX * scale,
                y: metrics.activeY * scale,
                width: metrics.activeW * scale,
                height: metrics.activeH * scale,
                rx: Math.min(3, Math.min(metrics.activeW, metrics.activeH) * scale * 0.06)
            }));

            const fontSize = Math.max(7, Math.min(12,
                Math.min(metrics.bodyW * scale, metrics.bodyH * scale) * 0.26));
            const text = svgNode("text", {
                x: 0,
                y: fontSize * 0.36,
                "class": "slot-label",
                "font-size": fontSize
            });
            const fullLabel = label.length > 18 ? label.slice(0, 17) + "…" : label;
            text.textContent = fullLabel;
            group.appendChild(text);

            if (selected) {
                group.appendChild(svgNode("rect", {
                    "class": "slot-ring",
                    x: -metrics.bodyW / 2 * scale - 3,
                    y: -metrics.bodyH / 2 * scale - 3,
                    width: metrics.bodyW * scale + 6,
                    height: metrics.bodyH * scale + 6,
                    rx: 4
                }));
                group.appendChild(svgNode("path", {
                    "class": "slot-mark",
                    d: "M " + (-metrics.bodyW / 2 * scale) + " "
                        + (-metrics.bodyH / 2 * scale)
                        + " l 0 14 l 14 0 z"
                }));
            }

            svg.appendChild(group);
        });

        if (slotIds.length === 0) {
            const note = svgNode("text", {
                x: STAGE_W / 2,
                y: STAGE_H / 2,
                "class": "stage-note"
            });
            note.textContent = "No tablets on the wall. Use Add beside a tablet.";
            svg.appendChild(note);
        }

        el.stageScale.textContent = formatNumber(scale, 3) + " stage px per mm · grid "
            + formatNumber(stage.step, stage.step >= 1 ? 0 : 2) + " mm · wall "
            + formatNumber(bounds.width, 1) + " × " + formatNumber(bounds.height, 1) + " mm";

        if (focusedSlotId) focusStageSlot(focusedSlotId);
    }

    function pointerToStage(event) {
        const matrix = el.stageSvg.getScreenCTM();
        if (!matrix) return null;
        const point = el.stageSvg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        return point.matrixTransform(matrix.inverse());
    }

    function onPointerDown(event) {
        if (state.busy) return;
        if (event.button !== 0 && event.pointerType === "mouse") return;
        const group = event.target && event.target.closest
            ? event.target.closest(".slot") : null;
        if (!group) return;
        const id = group.dataset.deviceId;
        if (!id || !state.draft || !state.draft.slots[id]) return;

        selectDevice(id);
        const point = pointerToStage(event);
        if (!point) return;

        state.drag = {
            id: id,
            pointerId: event.pointerId,
            startClientX: event.clientX,
            startClientY: event.clientY,
            startStageX: point.x,
            startStageY: point.y,
            scale: state.stage.scale,
            moved: false,
            preDraft: clone(state.draft)
        };
        focusStageSlot(id);
        try { el.stageSvg.setPointerCapture(event.pointerId); } catch (error) { /* no capture */ }
        event.preventDefault();
    }

    function onPointerMove(event) {
        const drag = state.drag;
        if (!drag || event.pointerId !== drag.pointerId) return;

        const distance = Math.hypot(
            event.clientX - drag.startClientX,
            event.clientY - drag.startClientY
        );
        if (!drag.moved) {
            if (distance <= DRAG_THRESHOLD_PX) return;
            drag.moved = true;
            el.stageSvg.classList.add("is-dragging");
        }

        const point = pointerToStage(event);
        if (!point) return;
        const slot = state.draft.slots[drag.id];
        const before = drag.preDraft.slots[drag.id];
        if (!slot || !before) return;

        const deltaX = (point.x - drag.startStageX) / drag.scale;
        const deltaY = (point.y - drag.startStageY) / drag.scale;
        slot.center_x_mm = roundTo(finiteOr(before.center_x_mm, 0) + deltaX, 2);
        slot.center_y_mm = roundTo(finiteOr(before.center_y_mm, 0) + deltaY, 2);
        event.preventDefault();
        afterDraftChange();
    }

    function endDrag(commit) {
        const drag = state.drag;
        if (!drag) return;
        state.drag = null;
        el.stageSvg.classList.remove("is-dragging");
        try {
            if (el.stageSvg.hasPointerCapture(drag.pointerId)) {
                el.stageSvg.releasePointerCapture(drag.pointerId);
            }
        } catch (error) { /* capture already gone */ }

        if (!drag.moved) {
            afterDraftChange();
            return;
        }
        if (!commit) {
            state.draft = drag.preDraft;
            afterDraftChange();
            announce("Move cancelled.");
            return;
        }
        pushUndo(drag.preDraft);
        afterDraftChange();
        const slot = state.draft.slots[drag.id];
        if (slot) {
            announce("Moved " + deviceLabel(drag.id, latestProfile(drag.id))
                + " to " + formatNumber(slot.center_x_mm, 1) + ", "
                + formatNumber(slot.center_y_mm, 1) + " mm.");
        }
    }

    function onPointerUp(event) {
        if (state.drag && event.pointerId === state.drag.pointerId) endDrag(true);
    }

    function onPointerCancel(event) {
        if (state.drag && event.pointerId === state.drag.pointerId) endDrag(false);
    }

    /* ---------------------------------------------------------------- *
     * Selection
     * ---------------------------------------------------------------- */

    function selectDevice(id) {
        if (!id) return;
        if (state.selectedId !== id) {
            state.selectedId = id;
            state.formDeviceId = null;
            state.profileDirty = false;
            state.calDirty = false;
            clearMsg(el.profileMsg);
            clearMsg(el.calibrationMsg);
            syncDeviceRows();
            syncInspector();
            renderStage();
            populateDeviceCard(true);
        } else {
            syncDeviceRows();
            syncInspector();
        }
    }

    function syncDeviceRows() {
        deviceRows.forEach(function (row, id) {
            const selected = id === state.selectedId;
            row.item.dataset.selected = selected ? "true" : "false";
            row.pick.setAttribute("aria-pressed", selected ? "true" : "false");
            row.flag.textContent = selected ? "Selected" : "";
        });
        renderDeviceCount();
    }

    function renderDeviceCount() {
        el.deviceCount.textContent = String(deviceRows.size);
        el.deviceEmpty.hidden = deviceRows.size > 0;
    }

    function renderDeviceList() {
        const focused = document.activeElement;
        const focusedId = focused && focused.classList
            && focused.classList.contains("dev-pick") ? focused.dataset.deviceId : null;

        el.deviceList.textContent = "";
        deviceRows.clear();
        const entries = deviceEntries();

        entries.forEach(function (entry) {
            const item = document.createElement("li");
            item.className = "dev-row";
            item.dataset.deviceId = entry.id;
            item.dataset.selected = entry.id === state.selectedId ? "true" : "false";

            const pick = document.createElement("button");
            pick.type = "button";
            pick.className = "dev-pick";
            pick.dataset.deviceId = entry.id;
            pick.setAttribute("aria-pressed", entry.id === state.selectedId ? "true" : "false");
            pick.setAttribute("aria-label", entry.label + ", device " + shortId(entry.id));

            const label = document.createElement("span");
            label.className = "dev-label";
            label.textContent = entry.label;

            const flag = document.createElement("span");
            flag.className = "dev-flag";
            flag.textContent = entry.id === state.selectedId ? "Selected" : "";

            const meta = document.createElement("span");
            meta.className = "dev-meta";

            const idText = document.createElement("span");
            idText.className = "mono";
            idText.textContent = shortId(entry.id) + "…";
            idText.title = entry.id;
            meta.appendChild(idText);

            const sizeText = document.createElement("span");
            sizeText.textContent = entry.profile
                ? formatNumber(entry.profile.active_width_mm, 1) + " × "
                    + formatNumber(entry.profile.active_height_mm, 1) + " mm"
                : "size unknown";
            meta.appendChild(sizeText);

            const profileText = document.createElement("span");
            profileText.textContent = entry.profile
                ? "profile r" + entry.profile.revision : "no profile";
            meta.appendChild(profileText);

            const status = calibrationStatus(entry.profile, entry.calibration);
            const calText = document.createElement("span");
            calText.className = "dev-cal";
            calText.dataset.kind = status.kind;
            calText.textContent = status.text;
            meta.appendChild(calText);

            pick.appendChild(label);
            pick.appendChild(flag);
            pick.appendChild(meta);
            pick.addEventListener("click", function () {
                selectDevice(entry.id);
            });

            item.appendChild(pick);

            if (entry.slot) {
                const onWall = document.createElement("span");
                onWall.className = "dev-slot";
                onWall.textContent = "On wall";
                item.appendChild(onWall);
            } else {
                const pair = validPair(entry.id);
                const add = document.createElement("button");
                add.type = "button";
                add.className = "btn btn-sm dev-action";
                add.textContent = "Add";
                add.disabled = !pair;
                add.title = pair
                    ? "Add this tablet to the wall"
                    : "Save a profile, then a calibration for its newest revision, before adding it.";
                add.addEventListener("click", function () {
                    selectDevice(entry.id);
                    addSelectedDevice();
                });
                item.appendChild(add);
            }

            el.deviceList.appendChild(item);
            deviceRows.set(entry.id, {
                item: item,
                pick: pick,
                flag: flag
            });
        });

        renderDeviceCount();

        if (focusedId) {
            const row = deviceRows.get(focusedId);
            if (row) {
                try { row.pick.focus({ preventScroll: true }); }
                catch (error) { row.pick.focus(); }
            }
        }
    }

    /* ---------------------------------------------------------------- *
     * Inspector
     * ---------------------------------------------------------------- */

    function syncInspector() {
        const id = state.selectedId;
        if (!id) {
            el.inspectorEmpty.hidden = false;
            el.inspectorBody.hidden = true;
            el.inspectorMissing.hidden = true;
            return;
        }

        const profile = latestProfile(id);
        const label = deviceLabel(id, profile);
        el.inspectorEmpty.hidden = true;
        const slot = selectedSlot();

        if (!slot) {
            el.inspectorBody.hidden = true;
            el.inspectorMissing.hidden = false;
            const pair = validPair(id);
            el.btnAddSlot.disabled = state.busy || !pair;
            if (pair) {
                el.slotMissingText.textContent = label
                    + " has no slot. Add it to the wall at the centre, then drag or nudge it.";
            } else {
                el.slotMissingText.textContent = label
                    + " needs a profile and a calibration for that profile revision before it can be added.";
            }
            return;
        }

        el.inspectorBody.hidden = false;
        el.inspectorMissing.hidden = true;
        el.selectedTitle.textContent = label;
        el.selectedId.textContent = id;

        const participating = slot.participating !== false;
        el.selectedState.textContent = participating ? "On the wall" : "Not participating";
        el.selectedState.dataset.kind = participating ? "ok" : "warn";

        setInputValue(el.slotCenterX, formatNumber(slot.center_x_mm, 2));
        setInputValue(el.slotCenterY, formatNumber(slot.center_y_mm, 2));
        setInputValue(el.slotAngle, formatNumber(slot.mount_angle, 2));
        setInputValue(el.slotNudgeX, formatNumber(slot.nudge_x_mm, 2));
        setInputValue(el.slotNudgeY, formatNumber(slot.nudge_y_mm, 2));

        const metrics = bodyMetrics(profileFor(id, slot.profile_revision) || profile);
        const notes = ["Body " + formatNumber(metrics.bodyW, 1) + " × "
            + formatNumber(metrics.bodyH, 1) + " mm; active "
            + formatNumber(metrics.activeW, 1) + " × " + formatNumber(metrics.activeH, 1) + " mm."];
        const latest = latestProfile(id);
        if (latest && slot.profile_revision !== latest.revision) {
            notes.push("Slot uses profile r" + slot.profile_revision
                + "; the newest profile is r" + latest.revision + ".");
        }
        const calibration = calibrationFor(id, slot.calibration_revision);
        if (!calibration) {
            notes.push("Calibration r" + slot.calibration_revision
                + " is not in the current configuration; reload to check it.");
        } else if (calibration.profile_revision !== slot.profile_revision) {
            notes.push("Slot calibration belongs to profile r"
                + calibration.profile_revision + ".");
        }
        el.selectedNote.textContent = notes.join(" ");

        el.btnRotate.disabled = state.busy;
        el.btnDeleteSlot.disabled = state.busy;
        el.btnNudgeXMinus.disabled = state.busy;
        el.btnNudgeXPlus.disabled = state.busy;
        el.btnNudgeYMinus.disabled = state.busy;
        el.btnNudgeYPlus.disabled = state.busy;
    }

    function nudgeSelected(deltaX, deltaY) {
        const slot = selectedSlot();
        if (!slot || state.busy) return;
        const before = clone(state.draft);
        slot.nudge_x_mm = roundTo(finiteOr(slot.nudge_x_mm, 0) + deltaX, 3);
        slot.nudge_y_mm = roundTo(finiteOr(slot.nudge_y_mm, 0) + deltaY, 3);
        pushUndo(before);
        afterDraftChange();
        announce("Nudge " + formatNumber(slot.nudge_x_mm, 2) + ", "
            + formatNumber(slot.nudge_y_mm, 2) + " mm.");
    }

    function rotateSelected() {
        const slot = selectedSlot();
        if (!slot || state.busy) return;
        const before = clone(state.draft);
        const angle = finiteOr(slot.mount_angle, 0) + 90;
        slot.mount_angle = roundTo(((angle % 360) + 360) % 360, 2);
        pushUndo(before);
        afterDraftChange();
        announce("Mount angle " + formatNumber(slot.mount_angle, 1) + "°.");
    }

    function deleteSelectedSlot() {
        const id = state.selectedId;
        if (!id || !selectedSlot() || state.busy) return;
        const changed = mutateDraft(function (draft) {
            delete draft.slots[id];
        });
        if (!changed) return;
        renderDeviceList();
        syncInspector();
        announce("Removed " + deviceLabel(id, latestProfile(id)) + " from the draft wall.");
        el.btnAddSlot.focus();
    }

    function addSelectedDevice() {
        const id = state.selectedId;
        if (!id || state.busy) return;
        if (state.draft.slots[id]) return;
        const pair = validPair(id);
        if (!pair) {
            showError("This tablet needs a profile and a calibration for that profile revision before it can be added.");
            return;
        }

        const metrics = bodyMetrics(pair.profile);
        const bounds = state.draft.bounds;
        const count = Object.keys(state.draft.slots).length;
        const column = count % 3;
        const row = Math.floor(count / 3);
        let centerX = bounds.x + bounds.width / 2
            + (column - 1) * (metrics.bodyW + 24);
        let centerY = bounds.y + bounds.height / 2
            + row * (metrics.bodyH + 24);
        const minX = bounds.x + metrics.bodyW / 2 + 10;
        const maxX = bounds.x + bounds.width - metrics.bodyW / 2 - 10;
        const minY = bounds.y + metrics.bodyH / 2 + 10;
        const maxY = bounds.y + bounds.height - metrics.bodyH / 2 - 10;
        centerX = minX <= maxX ? Math.min(Math.max(centerX, minX), maxX)
            : bounds.x + bounds.width / 2;
        centerY = minY <= maxY ? Math.min(Math.max(centerY, minY), maxY)
            : bounds.y + bounds.height / 2;

        const changed = mutateDraft(function (draft) {
            draft.slots[id] = {
                center_x_mm: roundTo(centerX, 2),
                center_y_mm: roundTo(centerY, 2),
                mount_angle: 0,
                nudge_x_mm: 0,
                nudge_y_mm: 0,
                profile_revision: pair.profile.revision,
                calibration_revision: pair.calibration.revision,
                participating: true
            };
        });
        if (!changed) return;
        renderDeviceList();
        renderStage();
        syncInspector();
        focusStageSlot(id);
        announce("Added " + pair.profile.label + " to the draft wall.");
    }

    /* ---------------------------------------------------------------- *
     * Bounds and slot inputs
     * ---------------------------------------------------------------- */

    function bindNumberInput(input, write, validate) {
        let before = null;

        input.addEventListener("focus", function () {
            before = state.draft ? clone(state.draft) : null;
        });

        input.addEventListener("input", function () {
            const value = num(input.value);
            const valid = value !== null && (!validate || validate(value));
            markInvalid(input, !valid);
            if (!valid) return;
            if (write(value)) afterDraftChange();
        });

        function commit() {
            markInvalid(input, false);
            if (!before) return;
            pushUndo(before);
            before = null;
            syncDraftUi();
        }

        input.addEventListener("change", commit);
        input.addEventListener("blur", commit);
    }

    function bindSlotField(input, field) {
        bindNumberInput(input, function (value) {
            const slot = selectedSlot();
            if (!slot || slot[field] === value) return false;
            slot[field] = value;
            return true;
        });
    }

    /* ---------------------------------------------------------------- *
     * Profile and calibration
     * ---------------------------------------------------------------- */

    function requirePositive(label, input) {
        const value = num(input.value);
        if (value === null || value <= 0) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be a positive number.");
        }
        markInvalid(input, false);
        return value;
    }

    function requireNonNegative(label, input) {
        const value = num(input.value);
        if (value === null || value < 0) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be a non-negative number.");
        }
        markInvalid(input, false);
        return value;
    }

    function requireFinite(label, input) {
        const value = num(input.value);
        if (value === null) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be a number.");
        }
        markInvalid(input, false);
        return value;
    }

    function requireInteger(label, input, minimum) {
        const value = num(input.value);
        if (value === null || !Number.isInteger(value) || value < minimum) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be an integer of at least " + minimum + ".");
        }
        markInvalid(input, false);
        return value;
    }

    function requireText(label, input, minimum, maximum) {
        const value = input.value.trim();
        if (value.length < minimum || value.length > maximum) {
            markInvalid(input, true);
            throw new ValidationError(label + " must be " + minimum + " to " + maximum + " characters.");
        }
        markInvalid(input, false);
        return value;
    }

    function buildProfileBody() {
        const panelWidthRaw = el.profilePixelWidth.value.trim();
        const panelHeightRaw = el.profilePixelHeight.value.trim();
        let panelPixels = null;
        if (panelWidthRaw || panelHeightRaw) {
            const width = requirePositive("Panel pixel width", el.profilePixelWidth);
            const height = requirePositive("Panel pixel height", el.profilePixelHeight);
            if (!Number.isInteger(width) || !Number.isInteger(height)) {
                throw new ValidationError("Panel pixel dimensions must be whole numbers.");
            }
            panelPixels = { width: width, height: height };
        }
        return {
            active_width_mm: requirePositive("Active width", el.profileActiveWidth),
            active_height_mm: requirePositive("Active height", el.profileActiveHeight),
            bezels: {
                left: requireNonNegative("Left bezel", el.profileBezelLeft),
                top: requireNonNegative("Top bezel", el.profileBezelTop),
                right: requireNonNegative("Right bezel", el.profileBezelRight),
                bottom: requireNonNegative("Bottom bezel", el.profileBezelBottom)
            },
            panel_pixels: panelPixels,
            label: requireText("Label", el.profileLabel, 1, 80),
            provenance: requireText("Provenance", el.profileProvenance, 1, 40)
        };
    }

    function buildCalibrationBody() {
        const orientation = Number(el.calOrientation.value);
        if ([0, 90, 180, 270].indexOf(orientation) === -1) {
            throw new ValidationError("Orientation must be 0, 90, 180 or 270 degrees.");
        }
        const quarter = Number(el.calQuarterTurn.value);
        if ([0, 1, 2, 3].indexOf(quarter) === -1) {
            throw new ValidationError("Quarter turn must be 0, 1, 2 or 3.");
        }
        const anchor = el.calAnchorEdge.value;
        if (["top-left", "top-right", "bottom-left", "bottom-right"].indexOf(anchor) === -1) {
            throw new ValidationError("Anchor edge is not supported.");
        }
        return {
            profile_revision: requireInteger("Profile revision", el.calProfileRevision, 1),
            viewport_width: requirePositive("Viewport width", el.calViewportWidth),
            viewport_height: requirePositive("Viewport height", el.calViewportHeight),
            dpr: requirePositive("Device pixel ratio", el.calDpr),
            orientation: orientation,
            mode: el.calMode.value,
            quarter_turn: quarter,
            panel_offset_mm: [
                requireFinite("Panel offset X", el.calOffsetX),
                requireFinite("Panel offset Y", el.calOffsetY)
            ],
            mm_per_css: [
                requirePositive("mm per CSS pixel X", el.calMmCssX),
                requirePositive("mm per CSS pixel Y", el.calMmCssY)
            ],
            anchor_edge: anchor,
            uncertainty_mm: requireNonNegative("Uncertainty", el.calUncertainty),
            method: requireText("Method", el.calMethod, 1, 80)
        };
    }

    function replaceDisplay(display) {
        rememberProfile(display);
        state.displays = state.displays.filter(function (item) {
            return item.device_id !== display.device_id;
        });
        state.displays.push(display);
    }

    function replaceCalibration(calibration) {
        rememberCalibration(calibration);
        state.calibrations = state.calibrations.filter(function (item) {
            return item.device_id !== calibration.device_id;
        });
        state.calibrations.push(calibration);
    }

    function profileDefaults(profile) {
        const id = state.selectedId;
        return {
            label: profile ? profile.label : "Tablet " + shortId(id),
            provenance: profile ? profile.provenance : "manual",
            activeWidth: profile ? profile.active_width_mm : "",
            activeHeight: profile ? profile.active_height_mm : "",
            bezels: profile && profile.bezels ? profile.bezels : {
                left: 0, top: 0, right: 0, bottom: 0
            },
            panelPixels: profile && profile.panel_pixels ? profile.panel_pixels : null
        };
    }

    function fillProfileForm(profile) {
        const values = profileDefaults(profile);
        setInputValue(el.profileActiveWidth, formatNumber(values.activeWidth, 3));
        setInputValue(el.profileActiveHeight, formatNumber(values.activeHeight, 3));
        setInputValue(el.profileBezelTop, formatNumber(values.bezels.top, 3));
        setInputValue(el.profileBezelRight, formatNumber(values.bezels.right, 3));
        setInputValue(el.profileBezelBottom, formatNumber(values.bezels.bottom, 3));
        setInputValue(el.profileBezelLeft, formatNumber(values.bezels.left, 3));
        setInputValue(el.profileLabel, values.label);
        setInputValue(el.profileProvenance, values.provenance);
        setInputValue(el.profilePixelWidth, values.panelPixels
            ? formatNumber(values.panelPixels.width, 0) : "");
        setInputValue(el.profilePixelHeight, values.panelPixels
            ? formatNumber(values.panelPixels.height, 0) : "");
        state.profileDirty = false;
    }

    function orientationNow() {
        if (window.screen && window.screen.orientation
            && typeof window.screen.orientation.angle === "number") {
            const angle = ((Math.round(window.screen.orientation.angle) % 360) + 360) % 360;
            if ([0, 90, 180, 270].indexOf(angle) !== -1) return angle;
        }
        const legacy = Number(window.orientation);
        return [0, 90, 180, 270].indexOf(legacy) !== -1 ? legacy : 0;
    }

    function modeNow() {
        if (window.matchMedia
            && window.matchMedia("(display-mode: fullscreen)").matches) return "fullscreen";
        if (document.fullscreenElement) return "fullscreen";
        if (window.matchMedia
            && window.matchMedia("(display-mode: standalone)").matches) return "standalone";
        return "tab";
    }

    function fillCalibrationForm(calibration, profile) {
        const viewportWidth = window.innerWidth || 1;
        const viewportHeight = window.innerHeight || 1;
        const dpr = window.devicePixelRatio || 1;
        const activeWidth = profile ? finiteOr(profile.active_width_mm, 0) : 0;
        const activeHeight = profile ? finiteOr(profile.active_height_mm, 0) : 0;

        if (calibration) {
            setInputValue(el.calProfileRevision, formatNumber(calibration.profile_revision, 0));
            setInputValue(el.calViewportWidth, formatNumber(calibration.viewport_width, 3));
            setInputValue(el.calViewportHeight, formatNumber(calibration.viewport_height, 3));
            setInputValue(el.calDpr, formatNumber(calibration.dpr, 4));
            setSelectValue(el.calOrientation, calibration.orientation);
            setSelectValue(el.calMode, calibration.mode);
            setSelectValue(el.calQuarterTurn, calibration.quarter_turn);
            setSelectValue(el.calAnchorEdge, calibration.anchor_edge);
            setInputValue(el.calOffsetX, formatNumber(calibration.panel_offset_mm[0], 3));
            setInputValue(el.calOffsetY, formatNumber(calibration.panel_offset_mm[1], 3));
            setInputValue(el.calMmCssX, formatNumber(calibration.mm_per_css[0], 6));
            setInputValue(el.calMmCssY, formatNumber(calibration.mm_per_css[1], 6));
            setInputValue(el.calUncertainty, formatNumber(calibration.uncertainty_mm, 3));
            setInputValue(el.calMethod, calibration.method);
        } else {
            setInputValue(el.calProfileRevision, profile
                ? formatNumber(profile.revision, 0) : "");
            setInputValue(el.calViewportWidth, formatNumber(viewportWidth, 3));
            setInputValue(el.calViewportHeight, formatNumber(viewportHeight, 3));
            setInputValue(el.calDpr, formatNumber(dpr, 4));
            setSelectValue(el.calOrientation, orientationNow());
            setSelectValue(el.calMode, modeNow());
            setSelectValue(el.calQuarterTurn, 0);
            setSelectValue(el.calAnchorEdge, "top-left");
            setInputValue(el.calOffsetX, "0");
            setInputValue(el.calOffsetY, "0");
            setInputValue(el.calMmCssX, activeWidth > 0
                ? formatNumber(activeWidth / viewportWidth, 6) : "");
            setInputValue(el.calMmCssY, activeHeight > 0
                ? formatNumber(activeHeight / viewportHeight, 6) : "");
            setInputValue(el.calUncertainty, "0");
            setInputValue(el.calMethod, "manual");
        }
        state.calDirty = false;
    }

    function updateDeviceCardHeadings() {
        const id = state.selectedId;
        const profile = latestProfile(id);
        el.deviceCardName.textContent = deviceLabel(id, profile);
        el.deviceCardId.textContent = id;
        const status = calibrationStatus(profile, latestCalibration(id));
        el.deviceCardCal.textContent = status.text;
        el.deviceCardCal.dataset.kind = status.kind;
    }

    function updateCurrentLines() {
        const id = state.selectedId;
        const profile = latestProfile(id);
        const calibration = latestCalibration(id);
        const status = calibrationStatus(profile, calibration);

        if (profile) {
            const metrics = bodyMetrics(profile);
            el.profileCurrent.textContent = "Newest revision " + profile.revision
                + " · active " + formatNumber(metrics.activeW, 1) + " × "
                + formatNumber(metrics.activeH, 1) + " mm · body "
                + formatNumber(metrics.bodyW, 1) + " × "
                + formatNumber(metrics.bodyH, 1) + " mm.";
            el.profileCurrent.dataset.kind = "ok";
        } else {
            el.profileCurrent.textContent = "No profile saved for this tablet yet.";
            el.profileCurrent.dataset.kind = "warn";
        }

        if (!profile) {
            el.calibrationCurrent.textContent = "Save a profile before saving a calibration.";
            el.calibrationCurrent.dataset.kind = "warn";
        } else if (!calibration) {
            el.calibrationCurrent.textContent = "No calibration saved. Defaults use this browser window ("
                + (window.innerWidth || "?") + " × " + (window.innerHeight || "?")
                + " CSS px) and profile revision " + profile.revision + ".";
            el.calibrationCurrent.dataset.kind = "warn";
        } else if (calibration.profile_revision !== profile.revision) {
            el.calibrationCurrent.textContent = "Newest calibration is revision "
                + calibration.revision + " for profile revision "
                + calibration.profile_revision + " (stale for newest profile revision "
                + profile.revision + ").";
            el.calibrationCurrent.dataset.kind = "warn";
        } else {
            el.calibrationCurrent.textContent = "Newest calibration is revision "
                + calibration.revision + " for profile revision "
                + calibration.profile_revision + " · " + status.text + ".";
            el.calibrationCurrent.dataset.kind = "ok";
        }
    }

    function populateDeviceCard(force) {
        const id = state.selectedId;
        if (!id) {
            el.deviceCardEmpty.hidden = false;
            el.deviceCardBody.hidden = true;
            state.formDeviceId = null;
            return;
        }

        el.deviceCardEmpty.hidden = true;
        el.deviceCardBody.hidden = false;
        const profile = latestProfile(id);
        const calibration = latestCalibration(id);
        const changed = state.formDeviceId !== id || force;

        updateDeviceCardHeadings();
        updateCurrentLines();

        if (changed || !state.profileDirty) fillProfileForm(profile);
        if (changed || !state.calDirty) fillCalibrationForm(calibration, profile);
        state.formDeviceId = id;
    }

    async function saveProfile(event) {
        event.preventDefault();
        if (!state.selectedId || state.busy) return;
        clearMsg(el.profileMsg);
        clearError();

        let body;
        try {
            body = buildProfileBody();
        } catch (error) {
            setMsg(el.profileMsg, errorDetail(error), "err");
            announce(errorDetail(error), "err");
            return;
        }

        const id = state.selectedId;
        setBusy(true);
        try {
            const payload = await api(
                "PUT",
                "/api/v3/displays/" + encodeURIComponent(id),
                body,
                { etag: true }
            );
            if (!payload || !payload.display || !payload.etag) {
                throw new Error("The server returned an incomplete profile.");
            }
            state.etag = payload.etag;
            state.etagState = "current";
            replaceDisplay(payload.display);
            state.profileDirty = false;
            fillProfileForm(payload.display);
            setInputValue(el.calProfileRevision, String(payload.display.revision));
            updateDeviceCardHeadings();
            updateCurrentLines();
            syncMeta();
            renderDeviceList();
            renderStage();
            hideConflict();
            clearError();
            setMsg(el.profileMsg, "Saved profile revision " + payload.display.revision + ".", "ok");
            announce("Saved profile revision " + payload.display.revision + ".", "ok");
        } catch (error) {
            handleWriteError(error, el.profileMsg);
        } finally {
            setBusy(false);
        }
    }

    async function saveCalibration(event) {
        event.preventDefault();
        if (!state.selectedId || state.busy) return;
        clearMsg(el.calibrationMsg);
        clearError();

        let body;
        try {
            body = buildCalibrationBody();
        } catch (error) {
            setMsg(el.calibrationMsg, errorDetail(error), "err");
            announce(errorDetail(error), "err");
            return;
        }

        const id = state.selectedId;
        setBusy(true);
        try {
            const payload = await api(
                "PUT",
                "/api/v3/calibrations/" + encodeURIComponent(id),
                body,
                { etag: true }
            );
            if (!payload || !payload.calibration || !payload.etag) {
                throw new Error("The server returned an incomplete calibration.");
            }
            state.etag = payload.etag;
            state.etagState = "current";
            replaceCalibration(payload.calibration);
            state.calDirty = false;
            fillCalibrationForm(payload.calibration, latestProfile(id));
            updateDeviceCardHeadings();
            updateCurrentLines();
            syncMeta();
            renderDeviceList();
            renderStage();
            hideConflict();
            clearError();
            setMsg(el.calibrationMsg, "Saved calibration revision "
                + payload.calibration.revision + " for profile revision "
                + payload.calibration.profile_revision + ".", "ok");
            announce("Saved calibration revision " + payload.calibration.revision + ".", "ok");
        } catch (error) {
            handleWriteError(error, el.calibrationMsg);
        } finally {
            setBusy(false);
        }
    }

    /* ---------------------------------------------------------------- *
     * Saved layouts
     * ---------------------------------------------------------------- */

    async function loadLayouts() {
        try {
            const payload = await api("GET", API_LAYOUTS);
            state.savedLayouts = payload && Array.isArray(payload.layouts)
                ? payload.layouts : [];
        } catch (error) {
            state.savedLayouts = [];
            setMsg(el.layoutMsg, "Could not load saved layouts: " + errorDetail(error), "err");
        }
        renderSavedLayouts();
    }

    function renderSavedLayouts() {
        el.savedLayouts.textContent = "";
        state.savedLayouts.forEach(function (entry) {
            const layout = entry.layout || {};
            const bounds = layout.bounds || {};
            const slotCount = layout.slots && typeof layout.slots === "object"
                ? Object.keys(layout.slots).length : 0;

            const item = document.createElement("li");
            item.className = "saved-row";

            const info = document.createElement("span");
            info.className = "saved-info";
            const name = document.createElement("span");
            name.className = "saved-name";
            name.textContent = entry.name;
            const meta = document.createElement("span");
            meta.className = "saved-meta";
            meta.textContent = slotCount + (slotCount === 1 ? " tablet" : " tablets")
                + " · " + formatNumber(bounds.width, 1) + " × "
                + formatNumber(bounds.height, 1) + " mm";
            info.appendChild(name);
            info.appendChild(meta);

            const actions = document.createElement("span");
            actions.className = "saved-actions";

            const recall = document.createElement("button");
            recall.type = "button";
            recall.className = "btn btn-sm";
            recall.textContent = "Recall";
            recall.disabled = state.busy || !state.etag;
            recall.addEventListener("click", function () {
                recallLayout(entry.name);
            });

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "btn btn-danger btn-sm";
            remove.textContent = "Delete";
            remove.disabled = state.busy || !state.etag;
            remove.addEventListener("click", function () {
                deleteLayout(entry.name);
            });

            actions.appendChild(recall);
            actions.appendChild(remove);
            item.appendChild(info);
            item.appendChild(actions);
            el.savedLayouts.appendChild(item);
        });
        el.savedEmpty.hidden = state.savedLayouts.length > 0;
    }

    function updateSavedButtons() {
        const buttons = el.savedLayouts.querySelectorAll("button");
        for (let index = 0; index < buttons.length; index += 1) {
            buttons[index].disabled = state.busy || !state.etag;
        }
    }

    async function saveLayout(event) {
        event.preventDefault();
        if (state.busy) return;
        clearMsg(el.layoutMsg);

        const name = el.layoutName.value.trim();
        if (!name) {
            setMsg(el.layoutMsg, "Enter a name for this layout.", "err");
            el.layoutName.focus();
            return;
        }
        if (state.layoutKind !== "physical") {
            setMsg(el.layoutMsg, "Apply the physical draft first; there is no committed physical layout to save.", "err");
            return;
        }
        if (isDirty()) {
            setMsg(el.layoutMsg, "Apply or cancel the unapplied draft before saving the committed layout.", "err");
            return;
        }

        setBusy(true);
        try {
            const payload = await api(
                "PUT",
                API_LAYOUTS + "/" + encodeURIComponent(name),
                undefined,
                { etag: true }
            );
            el.layoutName.value = payload && payload.name ? payload.name : name;
            setMsg(el.layoutMsg, "Saved layout \"" + (payload && payload.name ? payload.name : name) + "\".", "ok");
            announce("Saved physical layout " + (payload && payload.name ? payload.name : name) + ".", "ok");
            await loadLayouts();
        } catch (error) {
            handleWriteError(error, el.layoutMsg);
        } finally {
            setBusy(false);
        }
    }

    async function recallLayout(name) {
        if (state.busy) return;
        if (!state.etag) {
            setMsg(el.layoutMsg, "No configuration ETag is loaded; reload the page.", "err");
            return;
        }
        if (isDirty() && !window.confirm("Recall \"" + name + "\" and discard the unapplied draft?")) {
            return;
        }
        clearError();
        setBusy(true);
        try {
            const payload = await api(
                "POST",
                API_LAYOUTS + "/" + encodeURIComponent(name) + "/recall",
                undefined,
                { etag: true }
            );
            ingestConfig(payload, { resetHistory: true });
            hideConflict();
            clearError();
            announce("Recalled physical layout " + name + ".", "ok");
        } catch (error) {
            handleWriteError(error, el.layoutMsg);
        } finally {
            setBusy(false);
        }
    }

    async function deleteLayout(name) {
        if (state.busy) return;
        if (!window.confirm("Delete saved layout \"" + name + "\"?")) return;
        clearError();
        setBusy(true);
        try {
            await api(
                "DELETE",
                API_LAYOUTS + "/" + encodeURIComponent(name),
                undefined,
                { etag: true }
            );
            setMsg(el.layoutMsg, "Deleted layout \"" + name + "\".", "ok");
            announce("Deleted physical layout " + name + ".", "ok");
            await loadLayouts();
        } catch (error) {
            handleWriteError(error, el.layoutMsg);
        } finally {
            setBusy(false);
        }
    }

    /* ---------------------------------------------------------------- *
     * Input wiring and startup
     * ---------------------------------------------------------------- */

    function isEditableTarget(target) {
        if (!target || !target.tagName) return false;
        const tag = target.tagName.toLowerCase();
        return tag === "input" || tag === "textarea" || tag === "select"
            || target.isContentEditable === true;
    }

    function onKeyDown(event) {
        const key = event.key;
        const modified = event.ctrlKey || event.metaKey;

        if (key === "Escape" && state.drag) {
            event.preventDefault();
            endDrag(false);
            return;
        }

        if (modified && (key === "z" || key === "Z")) {
            if (isEditableTarget(event.target)) return;
            event.preventDefault();
            if (event.shiftKey) redoDraft();
            else undoDraft();
            return;
        }

        if (modified && (key === "y" || key === "Y")) {
            if (isEditableTarget(event.target)) return;
            event.preventDefault();
            redoDraft();
            return;
        }

        if (isEditableTarget(event.target)) return;
        if (event.altKey || event.ctrlKey || event.metaKey) return;

        const step = event.shiftKey ? 10 : 1;
        let deltaX = 0;
        let deltaY = 0;
        if (key === "ArrowLeft") deltaX = -step;
        else if (key === "ArrowRight") deltaX = step;
        else if (key === "ArrowUp") deltaY = -step;
        else if (key === "ArrowDown") deltaY = step;
        if (deltaX === 0 && deltaY === 0) return;

        if (!selectedSlot()) return;
        event.preventDefault();
        nudgeSelected(deltaX, deltaY);
    }

    function bindEvents() {
        el.btnUndo.addEventListener("click", undoDraft);
        el.btnRedo.addEventListener("click", redoDraft);
        el.btnApply.addEventListener("click", applyLayout);
        el.btnCancel.addEventListener("click", cancelDraft);
        el.btnReload.addEventListener("click", reloadConfigWithConfirm);
        el.btnConflictReload.addEventListener("click", reloadConfigWithConfirm);

        el.btnRotate.addEventListener("click", rotateSelected);
        el.btnDeleteSlot.addEventListener("click", deleteSelectedSlot);
        el.btnNudgeXMinus.addEventListener("click", function () { nudgeSelected(-1, 0); });
        el.btnNudgeXPlus.addEventListener("click", function () { nudgeSelected(1, 0); });
        el.btnNudgeYMinus.addEventListener("click", function () { nudgeSelected(0, -1); });
        el.btnNudgeYPlus.addEventListener("click", function () { nudgeSelected(0, 1); });
        el.btnAddSlot.addEventListener("click", addSelectedDevice);

        bindSlotField(el.slotCenterX, "center_x_mm");
        bindSlotField(el.slotCenterY, "center_y_mm");
        bindSlotField(el.slotAngle, "mount_angle");
        bindSlotField(el.slotNudgeX, "nudge_x_mm");
        bindSlotField(el.slotNudgeY, "nudge_y_mm");

        bindNumberInput(el.boundsX, function (value) {
            if (!state.draft) return false;
            state.draft.bounds.x = value;
            return true;
        });
        bindNumberInput(el.boundsY, function (value) {
            if (!state.draft) return false;
            state.draft.bounds.y = value;
            return true;
        });
        bindNumberInput(el.boundsWidth, function (value) {
            if (!state.draft) return false;
            state.draft.bounds.width = value;
            return true;
        }, function (value) { return value > 0; });
        bindNumberInput(el.boundsHeight, function (value) {
            if (!state.draft) return false;
            state.draft.bounds.height = value;
            return true;
        }, function (value) { return value > 0; });

        el.stageSvg.addEventListener("pointerdown", onPointerDown);
        el.stageSvg.addEventListener("pointermove", onPointerMove, { passive: false });
        el.stageSvg.addEventListener("pointerup", onPointerUp);
        el.stageSvg.addEventListener("pointercancel", onPointerCancel);
        el.stageSvg.addEventListener("lostpointercapture", function (event) {
            if (state.drag && event.pointerId === state.drag.pointerId) endDrag(true);
        });
        el.stageSvg.addEventListener("focusin", function (event) {
            const group = event.target && event.target.closest
                ? event.target.closest(".slot") : null;
            if (group && group.dataset.deviceId) selectDevice(group.dataset.deviceId);
        });
        el.stageSvg.addEventListener("keydown", function (event) {
            if (event.key !== "Enter" && event.key !== " ") return;
            const group = event.target && event.target.closest
                ? event.target.closest(".slot") : null;
            if (!group) return;
            event.preventDefault();
            selectDevice(group.dataset.deviceId);
        });

        el.profileForm.addEventListener("submit", saveProfile);
        el.calibrationForm.addEventListener("submit", saveCalibration);
        el.profileForm.addEventListener("input", function () { state.profileDirty = true; });
        el.calibrationForm.addEventListener("input", function () { state.calDirty = true; });
        el.profileForm.addEventListener("change", function () { state.profileDirty = true; });
        el.calibrationForm.addEventListener("change", function () { state.calDirty = true; });

        el.layoutSaveForm.addEventListener("submit", saveLayout);
        el.btnLayoutsRefresh.addEventListener("click", loadLayouts);
        el.layoutName.addEventListener("input", function () { clearMsg(el.layoutMsg); });

        document.addEventListener("keydown", onKeyDown);
    }

    function init() {
        bindEvents();
        syncMeta();
        syncDraftUi();
        loadConfig();
        loadLayouts();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
