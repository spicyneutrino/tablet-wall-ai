"use strict";

(function () {
    const API_CONFIG = "/api/v3/config";
    const API_DEVICES = "/devices";
    const API_LAYOUT = "/api/v3/layout";
    const API_LAYOUTS = "/api/v3/layouts";
    const API_PLAYLIST = "/api/v3/playlist";
    const API_PLAYBACK = "/api/v3/playback";
    const API_MEDIA = "/media";
    const API_DIAGNOSTICS = "/diagnostics";
    const REQUEST_TIMEOUT_MS = 10000;
    const PLAYBACK_POLL_MS = 1000;
    const DRAG_THRESHOLD_PX = 3;
    const HISTORY_LIMIT = 80;
    const WAKE_LOCK_TEXT = {
        held: "Wake lock held",
        released: "Wake lock released",
        unsupported: "Wake lock unsupported",
        insecure: "Wake lock insecure",
        denied: "Wake lock denied"
    };
    const MIN_DWELL_MS = 1000;
    const MAX_DWELL_MS = 600000;
    const TAB_STORAGE_KEY = "tablet-wall-console-tab-v1";
    const TAB_NAMES = ["show", "tablet", "content", "system"];
    const COMPACT_MEDIA = typeof window.matchMedia === "function"
        ? window.matchMedia("(max-width: 719px)") : null;

    const el = {
        railTabs: document.getElementById("rail-tabs"),
        tabShow: document.getElementById("tab-show"),
        tabTablet: document.getElementById("tab-tablet"),
        tabContent: document.getElementById("tab-content"),
        tabSystem: document.getElementById("tab-system"),
        panelShow: document.getElementById("panel-show"),
        panelTablet: document.getElementById("panel-tablet"),
        panelContent: document.getElementById("panel-content"),
        panelSystem: document.getElementById("panel-system"),
        tabTabletDot: document.getElementById("tab-tablet-dot"),
        tabContentDot: document.getElementById("tab-content-dot"),
        railPanels: document.getElementById("rail-panels"),
        topbarPlaybackState: document.getElementById("topbar-playback-state"),
        btnTopbarStart: document.getElementById("btn-topbar-start"),
        btnTopbarPause: document.getElementById("btn-topbar-pause"),
        btnTopbarStop: document.getElementById("btn-topbar-stop"),
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
        wallHealth: document.getElementById("wall-health"),
        btnWallHealth: document.getElementById("btn-wall-health"),
        rosterStatus: document.getElementById("roster-status"),
        btnRosterRefresh: document.getElementById("btn-roster-refresh"),
        deviceList: document.getElementById("device-list"),
        deviceEmpty: document.getElementById("device-empty"),
        boundsX: document.getElementById("bounds-x"),
        boundsY: document.getElementById("bounds-y"),
        boundsWidth: document.getElementById("bounds-width"),
        boundsHeight: document.getElementById("bounds-height"),
        boundsNote: document.getElementById("bounds-note"),
        boundsMode: document.getElementById("bounds-mode"),
        boundsPadding: document.getElementById("bounds-padding"),
        sizingMsg: document.getElementById("sizing-msg"),
        packColumns: document.getElementById("pack-columns"),
        packGap: document.getElementById("pack-gap"),
        btnPackTablets: document.getElementById("btn-pack-tablets"),
        btnLayoutsRefresh: document.getElementById("btn-layouts-refresh"),
        layoutSaveForm: document.getElementById("layout-save-form"),
        layoutName: document.getElementById("layout-name"),
        playlistLibrary: document.getElementById("playlist-library"),
        btnPlaylistAdd: document.getElementById("btn-playlist-add"),
        btnPlaylistLibraryRefresh: document.getElementById("btn-playlist-library-refresh"),
        playlistLibraryMsg: document.getElementById("playlist-library-msg"),
        playlistItems: document.getElementById("playlist-items"),
        playlistEmpty: document.getElementById("playlist-empty"),
        playlistCount: document.getElementById("playlist-count"),
        playlistHint: document.getElementById("playlist-hint"),
        playlistLoop: document.getElementById("playlist-loop"),
        btnPlaylistSave: document.getElementById("btn-playlist-save"),
        playlistUndo: document.getElementById("playlist-undo"),
        playlistMsg: document.getElementById("playlist-msg"),
        playlistRawId: document.getElementById("playlist-raw-id"),
        playlistRawDwell: document.getElementById("playlist-raw-dwell"),
        btnPlaylistRawAdd: document.getElementById("btn-playlist-raw-add"),
        playbackPolicy: document.getElementById("playback-policy"),
        playbackPolicyBlock: document.getElementById("playback-policy-block"),
        playbackEffectivePolicy: document.getElementById("playback-effective-policy"),
        playbackCard: document.getElementById("playback-card"),
        playbackStale: document.getElementById("playback-stale"),
        playbackStateWord: document.getElementById("playback-state-word"),
        playbackPreflight: document.getElementById("playback-preflight"),
        playbackExclusions: document.getElementById("playback-exclusions"),
        playbackExclusionsTitle: document.getElementById("playback-exclusions-title"),
        playbackExclusionSummary: document.getElementById("playback-exclusion-summary"),
        playbackExclusionList: document.getElementById("playback-exclusion-list"),
        playbackExclusionEmpty: document.getElementById("playback-exclusion-empty"),
        playbackExclusionWarning: document.getElementById("playback-exclusion-warning"),
        playbackExclusionNote: document.getElementById("playback-exclusion-note"),
        playbackSession: document.getElementById("playback-session"),
        playbackSteps: document.getElementById("playback-steps"),
        btnPlaybackStart: document.getElementById("btn-playback-start"),
        btnPlaybackPause: document.getElementById("btn-playback-pause"),
        btnPlaybackStop: document.getElementById("btn-playback-stop"),
        btnPlaybackRetry: document.getElementById("btn-playback-retry"),
        btnPlaybackPrevious: document.getElementById("btn-playback-previous"),
        btnPlaybackNext: document.getElementById("btn-playback-next"),
        playbackMsg: document.getElementById("playback-msg"),
        playbackStatus: document.getElementById("playback-status"),
        playbackCountdown: document.getElementById("playback-countdown"),
        playbackCohortLine: document.getElementById("playback-cohort-line"),
        playbackMore: document.getElementById("btn-playback-more"),
        playbackFacts: document.getElementById("playback-facts"),
        playbackPending: document.getElementById("playback-pending"),
        playbackMembers: document.getElementById("playback-members"),
        playbackMembersEmpty: document.getElementById("playback-members-empty"),
        playbackPollNote: document.getElementById("playback-poll-note"),
        diagState: document.getElementById("diag-state"),
        btnDiagRefresh: document.getElementById("btn-diag-refresh"),
        btnDiagVerify: document.getElementById("btn-diag-verify"),
        btnDiagDownload: document.getElementById("btn-diag-download"),
        diagMsg: document.getElementById("diag-msg"),
        diagGrid: document.getElementById("diag-grid"),
        diagIntegrity: document.getElementById("diag-integrity"),
        diagIntegrityText: document.getElementById("diag-integrity-text"),
        diagProblems: document.getElementById("diag-problems"),
        btnLayoutSave: document.getElementById("btn-layout-save"),
        layoutMsg: document.getElementById("layout-msg"),
        savedLayouts: document.getElementById("saved-layouts"),
        savedEmpty: document.getElementById("saved-empty"),
        inspectorEmpty: document.getElementById("inspector-empty"),
        inspectorBody: document.getElementById("inspector-body"),
        selectedTitle: document.getElementById("selected-title"),
        selectedId: document.getElementById("selected-id"),
        btnCopySelectedId: document.getElementById("btn-copy-selected-id"),
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
        btnApplyLocal: document.getElementById("btn-apply-local"),
        btnCancelLocal: document.getElementById("btn-cancel-local"),
        inspectorMissing: document.getElementById("inspector-missing"),
        slotMissingText: document.getElementById("slot-missing-text"),
        btnAddSlot: document.getElementById("btn-add-slot"),
        deviceCardEmpty: document.getElementById("device-card-empty"),
        deviceCardBody: document.getElementById("device-card-body"),
        deviceCardName: document.getElementById("device-card-name"),
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
        scene: null,
        operatorConfig: null,
        capabilities: {},
        readiness: {},
        deviceLabels: {},
        snapshots: {},
        gridPreview: null,
        readFence: window.OperatorState.readFence(),
        etag: null,
        etagState: "missing",
        revision: null,
        generation: null,
        layoutKind: null,
        configLoaded: false,
        base: null,
        basePlacements: {},
        draft: null,
        displays: [],
        calibrations: [],
        tabletModels: {},
        tabletAssignments: {},
        roster: {},
        rosterRefreshPromise: null,
        rosterCheckedAt: null,
        rosterError: null,
        rosterLoading: false,
        savedLayouts: [],
        selectedId: null,
        undo: [],
        redo: [],
        stage: { scale: 1, offX: 0, offY: 0, step: 50 },
        drag: null,
        formDeviceId: null,
        profileDirty: false,
        calDirty: false,
        busy: false,
        playlistEtag: null,
        playlist: { items: [], loop: true, revision: null },
        savedPlaylist: null,
        playlistLoaded: false,
        playlistLoading: true,
        playlistDirty: false,
        playlistSaving: false,
        playlistFocus: null,
        playlistRemoval: null,
        library: [],
        libraryState: "pending",
        libraryLoading: false,
        libraryError: null,
        playback: null,
        playbackExclusions: [],
        playbackExclusionRowKey: "",
        playbackVersion: null,
        playbackError: null,
        playbackFetchedAt: null,
        playbackOkAt: null,
        playbackFetching: false,
        playbackBusy: false,
        playbackAnnouncedState: null,
        playbackTimer: null,
        diagnostics: null,
        diagnosticsCapturedAt: null,
        diagnosticsState: "pending",
        diagnosticsError: null,
        diagnosticsLoading: false,
        tabDecided: false,
        tabName: null,
        tabScroll: {},
        playbackSettled: false
    };

    let operatorContent = null, operatorGrid = null, operatorDevices = null, operatorReadiness = null, operatorSync = null;

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

    /** 1.0 s .. 600 s: one decimal below ten seconds, whole seconds above. */
    function formatDuration(ms) {
        const value = Number(ms);
        if (!Number.isFinite(value) || value <= 0) return "—";
        const seconds = value / 1000;
        return (seconds < 10 ? seconds.toFixed(1) : String(Math.round(seconds))) + " s";
    }

    /** Like formatDuration, but zero is a real reading (buffer, sample age). */
    function formatSpan(ms) {
        const value = Number(ms);
        if (!Number.isFinite(value) || value < 0) return "—";
        const seconds = value / 1000;
        return (seconds < 10 ? seconds.toFixed(1) : String(Math.round(seconds))) + " s";
    }

    function formatBytes(bytes) {
        const value = Number(bytes);
        if (!Number.isFinite(value) || value < 0) return "—";
        if (value >= 1024 * 1024 * 1024) return (value / (1024 * 1024 * 1024)).toFixed(1) + " GiB";
        if (value >= 1024 * 1024) return (value / (1024 * 1024)).toFixed(1) + " MiB";
        if (value >= 1024) return (value / 1024).toFixed(1) + " KiB";
        return Math.round(value) + " B";
    }

    function formatPercent(used, quota) {
        const part = Number(used);
        const whole = Number(quota);
        if (!Number.isFinite(part) || !Number.isFinite(whole) || whole <= 0) return "—";
        return ((part / whole) * 100).toFixed(1) + "%";
    }

    function formatTime(iso) {
        const parsed = Date.parse(iso);
        return Number.isNaN(parsed) ? String(iso) : new Date(parsed).toLocaleString();
    }

    function relativeAge(iso) {
        const parsed = Date.parse(iso);
        if (Number.isNaN(parsed)) return "";
        const seconds = Math.max(0, (Date.now() - parsed) / 1000);
        if (seconds < 60) return Math.floor(seconds) + "s ago";
        if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
        if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
        return Math.floor(seconds / 86400) + "d ago";
    }

    function clampDwell(value) {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return MIN_DWELL_MS;
        return Math.min(MAX_DWELL_MS, Math.max(MIN_DWELL_MS, Math.round(parsed)));
    }

    function setTextIfChanged(node, text) {
        if (node && node.textContent !== text) node.textContent = text;
    }

    function clearChildren(node) {
        if (node) node.textContent = "";
    }

    function appendText(parent, tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        node.textContent = text;
        parent.appendChild(node);
        return node;
    }

    function finiteOr(value, fallback) {
        return Number.isFinite(Number(value)) ? Number(value) : fallback;
    }

    async function copyText(text) {
        if (!text) return false;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (error) {
                // Plain-HTTP LAN pages are not a secure context; fall through.
            }
        }
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.top = "-1000px";
        document.body.appendChild(area);
        area.select();
        let copied = false;
        try { copied = document.execCommand("copy"); }
        catch (error) { copied = false; }
        document.body.removeChild(area);
        return copied;
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
        return { text: "calib r" + calibration.revision + " saved", kind: "ok" };
    }

    function validPair(id) {
        const profile = latestProfile(id);
        if (!profile) return null;
        const calibration = calibrationForProfile(id, profile.revision);
        if (!calibration) return null;
        return { profile: profile, calibration: calibration };
    }

    function hasUnsavedEdits() {
        return isDirty() || state.profileDirty || state.calDirty
            || operatorContent && operatorContent.dirty() || operatorDevices && operatorDevices.dirty();
    }

    function isDirty() {
        if (state.gridPreview) return true;
        if (!state.base || !state.draft) return false;
        return layoutSignature(state.base) !== layoutSignature(state.draft);
    }

    function sizingError() {
        if (!state.draft || state.draft.kind !== "physical" || state.draft.sizing.mode !== "tablets"
                || Object.keys(state.draft.slots).length === 0) return null;
        return window.PhysicalSizing.fitBounds(
            state.draft.slots, profileFor, state.draft.sizing.padding
        ).error || null;
    }

    function layoutSignature(layout) {
        if (!layout) return "";
        if (layout.kind === "logical") return JSON.stringify({ kind: "logical", width: layout.width, height: layout.height, placements: Object.entries(layout.placements || {}).sort(), sizing: layout.sizing });
        const bounds = layout.bounds || {};
        const slots = layout.slots || {};
        return JSON.stringify({
            bounds: [bounds.x, bounds.y, bounds.width, bounds.height],
            sizing: layout.sizing || { mode: "fixed", padding: 0 },
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

    function bodyMetrics(profile) {
        if (!profile) {
            return {
                bodyW: 100, bodyH: 60, activeW: 100, activeH: 60,
                activeX: -50, activeY: -30
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
            activeY: -bodyH / 2 + top
        };
    }

    function deviceLabel(id, profile) {
        return state.deviceLabels[id] || state.roster[id] && state.roster[id].label || (profile && profile.label ? profile.label : "Tablet " + shortId(id));
    }

    function deviceNumber(id) {
        const record = state.roster[id];
        const value = record ? Number(record.number) : NaN;
        return Number.isInteger(value) && value > 0 ? value : null;
    }

    function compareDeviceIds(left, right) {
        const leftNumber = deviceNumber(left);
        const rightNumber = deviceNumber(right);
        if (leftNumber !== rightNumber) {
            if (leftNumber === null) return 1;
            if (rightNumber === null) return -1;
            return leftNumber - rightNumber;
        }
        const byLabel = deviceLabel(left, latestProfile(left))
            .localeCompare(deviceLabel(right, latestProfile(right)));
        return byLabel !== 0 ? byLabel : left.localeCompare(right);
    }

    function numberTag(id) {
        const number = deviceNumber(id);
        return number === null ? "#–" : "#" + number;
    }

    function numberedLabel(id, profile) {
        return numberTag(id) + " · " + deviceLabel(id, profile);
    }

    function isOnline(id) {
        const record = state.roster[id];
        return Boolean(record && record.online === true);
    }

    function deviceEntries() {
        const ids = new Set();
        Object.keys(state.roster).forEach(function (id) { ids.add(id); });
        [state.base, state.draft].forEach(function (layout) {
            if (layout && layout.slots) {
                Object.keys(layout.slots).forEach(function (id) { ids.add(id); });
            }
        });
        Object.keys(state.basePlacements).forEach(function (id) { ids.add(id); });
        const entries = [];
        ids.forEach(function (id) {
            const profile = latestProfile(id);
            entries.push({
                id: id,
                profile: state.base && state.base.slots[id] ? profileFor(id, state.base.slots[id].profile_revision) : profile,
                calibration: state.base && state.base.slots[id] ? calibrationFor(id, state.base.slots[id].calibration_revision) : latestCalibration(id),
                slot: state.draft && state.draft.slots ? state.draft.slots[id] || null : null,
                placement: state.draft && state.draft.placements
                    ? state.draft.placements[id] || null : null,
                baseSlot: state.base && state.base.slots ? state.base.slots[id] || null : null,
                basePlacement: state.basePlacements[id] || null,
                label: deviceLabel(id, profile)
            });
        });
        entries.sort(function (left, right) {
            const leftNumber = deviceNumber(left.id);
            const rightNumber = deviceNumber(right.id);
            if (leftNumber !== rightNumber) {
                if (leftNumber === null) return 1;
                if (rightNumber === null) return -1;
                return leftNumber - rightNumber;
            }
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

    /* ---------------------------------------------------------------- *
     * Rail tabs and the topbar transport
     * ---------------------------------------------------------------- */

    function tabEntries() {
        return [
            { name: "show", tab: el.tabShow, panel: el.panelShow },
            { name: "tablet", tab: el.tabTablet, panel: el.panelTablet },
            { name: "content", tab: el.tabContent, panel: el.panelContent },
            { name: "system", tab: el.tabSystem, panel: el.panelSystem }
        ];
    }

    function readStoredTab() {
        try {
            const stored = window.sessionStorage.getItem(TAB_STORAGE_KEY);
            return TAB_NAMES.indexOf(stored) === -1 ? null : stored;
        } catch (error) {
            return null;
        }
    }

    function storeTab(name) {
        try { window.sessionStorage.setItem(TAB_STORAGE_KEY, name); }
        catch (error) { /* The current view still switches. */ }
    }

    function compactView() {
        return Boolean(COMPACT_MEDIA && COMPACT_MEDIA.matches);
    }

    function showTab(name, options) {
        const settings = options || {};
        const entries = tabEntries();
        const resolved = name;
        let target = null;
        entries.forEach(function (entry) {
            if (entry.name === resolved) target = entry;
        });
        if (!target || !target.tab || !target.panel) return false;

        const changed = state.tabName !== resolved;
        if (changed && el.railPanels && state.tabName && !compactView()) {
            state.tabScroll[state.tabName] = el.railPanels.scrollTop;
        }
        entries.forEach(function (entry) {
            if (!entry.tab || !entry.panel) return;
            const active = entry.name === resolved;
            entry.tab.setAttribute("aria-selected", active ? "true" : "false");
            entry.tab.tabIndex = active ? 0 : -1;
            entry.panel.hidden = !active;
        });
        state.tabName = resolved;
        if (changed && el.railPanels) {
            el.railPanels.scrollTop = state.tabScroll[resolved] || 0;
        }
        if (settings.persist) {
            storeTab(name);
            state.tabDecided = true;
        }
        if (settings.focus) {
            try { target.tab.focus({ preventScroll: true }); }
            catch (error) { target.tab.focus(); }
        }
        return true;
    }

    function onTabKeyDown(event) {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        const entries = tabEntries();
        const target = event.target && event.target.closest
            ? event.target.closest('[role="tab"]') : null;
        let current = -1;
        for (let index = 0; index < entries.length; index += 1) {
            if (entries[index].tab === target) {
                current = index;
                break;
            }
        }
        if (current === -1) return;

        let next = null;
        if (event.key === "ArrowLeft") next = (current - 1 + entries.length) % entries.length;
        else if (event.key === "ArrowRight") next = (current + 1) % entries.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = entries.length - 1;
        if (next === null) return;

        event.preventDefault();
        showTab(entries[next].name, { focus: true, persist: true });
    }

    function onCompactChange() {
        showTab(state.tabName || readStoredTab() || "show", { persist: false });
    }

    function maybeChooseInitialTab() {
        if (state.tabDecided) return;
        if (!state.configLoaded) return;
        state.tabDecided = true;
        const name = "show";
        showTab(name, { persist: false });
    }

    function syncTabDots() {
        if (el.tabTabletDot) {
            el.tabTabletDot.hidden = !(isDirty()
                || state.profileDirty || state.calDirty);
        }
        if (el.tabContentDot) {
            el.tabContentDot.hidden = !state.playlistDirty;
        }
    }

    function syncTopbarTransport() {
        const stateWord = el.playbackStateWord;
        if (el.topbarPlaybackState) {
            setTextIfChanged(el.topbarPlaybackState, stateWord && stateWord.textContent
                ? stateWord.textContent : "stopped");
            el.topbarPlaybackState.dataset.state = stateWord && stateWord.dataset.state
                ? stateWord.dataset.state : "stopped";
        }
        mirrorTransportButton(el.btnPlaybackStart, el.btnTopbarStart);
        mirrorTransportButton(el.btnPlaybackPause, el.btnTopbarPause);
        mirrorTransportButton(el.btnPlaybackStop, el.btnTopbarStop);
        if (el.btnPlaybackPause && el.btnTopbarPause) {
            el.btnTopbarPause.classList.toggle("btn-primary",
                el.btnPlaybackPause.classList.contains("btn-primary"));
        }
    }

    function mirrorTransportButton(rail, topbar) {
        if (!rail || !topbar) return;
        topbar.hidden = rail.hidden;
        topbar.disabled = rail.disabled;
        setTextIfChanged(topbar, rail.textContent);
        if (rail.title) topbar.title = rail.title;
        else topbar.removeAttribute("title");
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
        if (typeof detail === "object") return (detail.message || detail.code || "Request conflict") + (detail.conflicts ? ": " + JSON.stringify(detail.conflicts) : "");
        return String(detail);
    }

    async function api(method, path, body, options) {
        const settings = options || {};
        const configAtSend = state.operatorConfig;
        const init = { method: method, headers: { "Accept": "application/json" } };
        if (body !== undefined) {
            init.headers["Content-Type"] = "application/json";
            init.body = JSON.stringify(body);
        }
        if (settings.etag) {
            if (!state.etag) throw new ApiError(428, "No configuration ETag is loaded.");
            if (state.etagState === "stale") throw new ApiError(412, "Reload the configuration before saving.");
            init.headers["If-Match"] = state.etag;
        }
        if (settings.ifMatch) {
            init.headers["If-Match"] = settings.ifMatch;
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
        const current = state.operatorConfig;
        if (method !== "GET" && payload && payload.layout && current && current !== configAtSend
                && (current.etag === payload.etag || current.etag !== init.headers["If-Match"])) {
            return Object.assign({}, payload, current);
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
        if (!config.layout || !["logical", "physical", undefined].includes(config.layout.kind)
                || config.operator_state_version !== undefined && config.operator_state_version !== 1) {
            state.etagState = "stale";
            showError("Unsupported operator configuration. Update the console before editing; no replacement layout has been created.");
            el.layoutKindNote.textContent = "Configuration upgrade required. The current layout cannot be edited by this console version.";
            syncDraftUi();
            if (operatorContent) operatorContent.render();
            if (operatorDevices) operatorDevices.render();
            return;
        }
        const firstConfig = !state.configLoaded;
        const settings = options || {};
        const keepDraft = settings.preserveDraft && state.configLoaded && hasUnsavedEdits();
        const oldDraft = state.draft, oldBase = state.base, oldEtag = state.etag;
        const conflicting = keepDraft && settings.remote && config.etag !== oldEtag;
        state.readFence.event();
        config = window.OperatorState.observeConfig(config, performance.now());
        state.operatorConfig = config;
        state.scene = config.scene || null;
        state.capabilities = config.capabilities || {};
        // Readiness comes from GET /api/v3/readiness, not this config snapshot.
        // A config seed only fills the gap until the first real read succeeds.
        if (!state.readinessFetchedAt) {
            state.readiness = config.readiness || config.runtime && config.runtime.readiness || {};
        }
        state.deviceLabels = config.device_labels || {};
        state.snapshots = config.snapshots || {};
        if (config.runtime && config.runtime.devices) state.roster = config.runtime.devices;
        state.etag = typeof config.etag === "string" && config.etag ? config.etag : null;
        state.etagState = state.etag ? "current" : "missing";
        state.revision = config.revision === undefined ? null : config.revision;
        state.generation = config.generation === undefined ? null : config.generation;
        state.layoutKind = config.layout && config.layout.kind ? config.layout.kind : null;
        state.configLoaded = true;
        state.displays = Array.isArray(config.displays) ? config.displays : [];
        state.calibrations = Array.isArray(config.calibrations) ? config.calibrations : [];
        state.tabletModels = config.tablet_models || {};
        state.tabletAssignments = config.tablet_assignments || {};
        state.displays.forEach(rememberProfile);
        state.calibrations.forEach(rememberCalibration);
        (config.referenced_displays || []).forEach(rememberProfile);
        (config.referenced_calibrations || []).forEach(rememberCalibration);
        state.basePlacements = config.layout && config.layout.kind !== "physical"
            && config.layout.placements && typeof config.layout.placements === "object"
            ? clone(config.layout.placements) : {};
        state.base = window.OperatorState.layoutDraft(config.layout);
        restorePlaybackExclusions();
        state.draft = keepDraft ? oldDraft : clone(state.base);
        if (conflicting) { state.base = oldBase; state.etag = oldEtag; state.etagState = "stale"; }
        if (settings.resetHistory !== false && !keepDraft) {
            state.undo = [];
            state.redo = [];
        }
        state.drag = null;
        if (settings.resetForms) {
            state.formDeviceId = null;
            state.profileDirty = false;
            state.calDirty = false;
        }
        ensureSelection();
        if (settings.resetForms && !keepDraft) { if (operatorContent) operatorContent.discard(); if (operatorDevices) operatorDevices.discard(); }
        if (conflicting) showConflict("Configuration changed while you were editing. Your draft is retained with its original ETag. Reload to discard it and review current state.");
        else hideConflict();
        state.rosterCheckedAt = new Date().toISOString();
        renderAll();
        maybeChooseInitialTab();
        if (firstConfig) announce("Wall configuration loaded. Image display is confirmed separately for each tablet.", "info");
    }

    function ensureSelection() {
        const ids = new Set(Object.keys(state.roster));
        Object.keys(window.OperatorState.entries(state.draft)).forEach(id => ids.add(id));
        if (state.selectedId && ids.has(state.selectedId)) return;
        state.selectedId = Array.from(ids).sort(compareDeviceIds)[0] || null;
    }

    async function loadConfig() {
        if (state.busy) return false;
        state.busy = true;
        syncDraftUi();
        const ticket = state.readFence.start();
        try {
            const results = await Promise.all([
                api("GET", API_CONFIG),
                api("GET", API_DEVICES)
            ]);
            if (!state.readFence.accept(ticket)) return false;
            state.gridPreview = null;
            state.roster = results[1] && typeof results[1] === "object" ? results[1] : {};
            state.rosterCheckedAt = new Date().toISOString();
            state.rosterError = null;
            ingestConfig(results[0], { resetHistory: true, resetForms: true });
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
        const hasUnsaved = hasUnsavedEdits();
        if (hasUnsaved && !window.confirm(
            "Reload the configuration and discard unapplied layout changes, image selection and unsaved tablet fields?"
        )) {
            return;
        }
        await loadConfig();
    }

    function renderAll() {
        syncMeta();
        syncDraftUi();
        if (operatorContent) { operatorContent.render(); operatorContent.detectUploads(); }
        renderDeviceList();
        renderStage();
        populateDeviceCard(false);
        renderPlayback();
        if (operatorGrid) operatorGrid.render();
        if (operatorDevices) operatorDevices.render();
        if (operatorReadiness) operatorReadiness.render();
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
            el.layoutKindNote.textContent = "Measured wall (mm). Pinned measurements; model dimensions remain approximate.";
            el.boundsNote.textContent = "Values describe the draft in millimetres. Apply layout to save changes.";
        } else if (state.layoutKind === "logical") {
            el.layoutKindNote.textContent = "Logical wall (unit-based). No millimetre conversion. Change kind explicitly in Layout & size.";
            el.boundsNote.textContent = "Physical bounds are unavailable for a logical layout. Use Layout & size in Wall or the labelled compatibility editor.";
        } else {
            el.layoutKindNote.textContent = "No wall configuration is loaded.";
            el.boundsNote.textContent = "";
        }
    }

    function syncBoundsInputs() {
        document.querySelector(".bounds-card").hidden = !state.draft || state.draft.kind !== "physical";
        if (!state.draft || !state.draft.bounds) return;
        const bounds = state.draft.bounds;
        setInputValue(el.boundsX, formatNumber(bounds.x, 3));
        setInputValue(el.boundsY, formatNumber(bounds.y, 3));
        setInputValue(el.boundsWidth, formatNumber(bounds.width, 3));
        setInputValue(el.boundsHeight, formatNumber(bounds.height, 3));
        el.boundsMode.value = state.draft.sizing.mode;
        setInputValue(el.boundsPadding, formatNumber(state.draft.sizing.padding, 3));
        const fitted = state.draft.sizing.mode === "tablets";
        el.boundsPadding.closest(".field").hidden = !fitted;
        el.btnPackTablets.closest(".pack-row").hidden = !fitted;
        [el.boundsX, el.boundsY, el.boundsWidth, el.boundsHeight].forEach(function (input) {
            input.readOnly = fitted;
            input.setAttribute("aria-readonly", fitted ? "true" : "false");
        });
        el.boundsMode.disabled = state.busy;
        el.boundsPadding.disabled = state.busy;
        el.btnPackTablets.disabled = state.busy || !fitted;
    }

    function syncLocalDraftActions() {
        if (el.btnApplyLocal) el.btnApplyLocal.disabled = el.btnApply.disabled;
        if (el.btnCancelLocal) el.btnCancelLocal.disabled = el.btnCancel.disabled;
    }

    function syncDraftUi() {
        renderCalibrationHelper();
        if (!state.draft) {
            el.draftFlag.textContent = "No draft";
            el.draftFlag.dataset.dirty = "false";
            el.btnApply.disabled = true;
            el.btnCancel.disabled = true;
            el.btnUndo.disabled = true;
            el.btnRedo.disabled = true;
            el.boundsMode.disabled = true;
            el.boundsPadding.disabled = true;
            el.btnPackTablets.disabled = true;
            syncLocalDraftActions();
            updateSavedButtons();
            syncInspector();
            syncTabDots();
            return;
        }

        const dirty = isDirty();
        if (dirty) {
            el.draftFlag.textContent = "Unapplied changes";
            el.draftFlag.dataset.dirty = "true";
        } else if (state.base) {
            el.draftFlag.textContent = "Matches the committed layout";
            el.draftFlag.dataset.dirty = "false";
        } else {
            el.draftFlag.textContent = "Draft not applied";
            el.draftFlag.dataset.dirty = "false";
        }

        const emptyPhysical = state.draft.kind === "physical" && Object.keys(state.draft.slots).length === 0;
        el.btnApply.disabled = state.busy || !state.etag || state.etagState !== "current" || !!sizingError()
            || !dirty || (emptyPhysical && !state.gridPreview);
        el.btnApply.title = emptyPhysical ? "This arrangement has no tablets. Use an explicit Remove action to clear a slot." : "Apply the entire previewed layout once";
        el.btnCancel.disabled = state.busy || !dirty;
        el.btnUndo.disabled = state.busy || state.undo.length === 0;
        el.btnRedo.disabled = state.busy || state.redo.length === 0;
        el.btnReload.disabled = state.busy;
        el.btnProfileSave.disabled = state.busy;
        el.btnCalibrationSave.disabled = state.busy || rulerSaveBlocked();
        el.btnLayoutSave.disabled = state.busy || !state.etag;
        el.btnLayoutsRefresh.disabled = state.busy;
        el.btnConflictReload.disabled = state.busy;

        syncLocalDraftActions();
        syncBoundsInputs();
        updateSavedButtons();
        syncInspector();
        syncTabDots();
    }

    function pushUndo(before) {
        if (!before) return;
        if (layoutSignature(before) === layoutSignature(state.draft)) return;
        state.undo.push(before);
        if (state.undo.length > HISTORY_LIMIT) state.undo.shift();
        state.redo.length = 0;
    }

    function afterDraftChange() {
        if (state.draft && state.draft.kind === "physical" && state.draft.sizing.mode === "tablets"
                && !(state.drag && state.drag.moved)) {
            const result = window.PhysicalSizing.fitBounds(
                state.draft.slots, profileFor, state.draft.sizing.padding
            );
            if (result.bounds) state.draft.bounds = result.bounds;
            if (result.error) setMsg(el.sizingMsg, result.error, "err");
            else if (result.bounds) clearMsg(el.sizingMsg);
            else setMsg(el.sizingMsg, "Add tablets to fit the wall. The last wall bounds are kept.", "info");
        }
        syncDraftUi();
        renderStage();
        renderPlaybackPreflight(playbackPreflight());
    }

    function mutateDraft(mutator) {
        if (!state.draft || state.draft.kind !== "physical" || state.gridPreview || state.busy) return false;
        const before = clone(state.draft);
        mutator(state.draft);
        if (layoutSignature(before) === layoutSignature(state.draft)) return false;
        pushUndo(before);
        afterDraftChange();
        return true;
    }

    function undoDraft() {
        if (state.busy || state.drag || state.undo.length === 0) return;
        const current = clone(state.draft);
        state.draft = state.undo.pop();
        state.redo.push(current);
        afterDraftChange();
        announce("Undid the last layout change.");
    }

    function redoDraft() {
        if (state.busy || state.drag || state.redo.length === 0) return;
        const current = clone(state.draft);
        state.draft = state.redo.pop();
        state.undo.push(current);
        afterDraftChange();
        announce("Redid the layout change.");
    }

    function cancelDraft() {
        if (!state.draft || !state.base || state.busy) return;
        if (state.gridPreview && operatorGrid) { operatorGrid.cancel(); return; }
        const before = clone(state.draft);
        state.draft = clone(state.base);
        state.drag = null;
        pushUndo(before);
        afterDraftChange();
        announce("Draft restored from the committed layout.");
    }

    async function applyLayout() {
        if (!state.draft || !state.etag || state.busy || state.etagState !== "current") return;
        if (state.gridPreview && operatorGrid) { await operatorGrid.apply(); return; }
        if (state.draft.kind !== "physical" || Object.keys(state.draft.slots).length === 0) {
            showError("An empty measured draft cannot be applied. Use a deliberate Remove action to clear an active slot."); return;
        }
        clearError();
        setBusy(true);
        try {
            const body = {
                bounds: clone(state.draft.bounds),
                slots: clone(state.draft.slots),
                sizing: clone(state.draft.sizing)
            };
            const payload = await api("PUT", API_LAYOUT, body, { etag: true });
            ingestConfig(payload, { resetHistory: true });
            await loadLayouts();
            clearError();
            hideConflict();
            announce("Layout applied at revision " + (state.revision === null ? "?" : state.revision) + "."
                + (payload.previous_layout_saved ? " Previous logical layout saved as " + payload.previous_layout_saved + "." : ""), "ok");
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

    const {
        addSelectedDevice, deleteSelectedSlot, endDrag, nudgeSelected, onPointerCancel, onPointerDown, onPointerMove, onPointerUp, renderDeviceHealth, renderDeviceList, renderStage, rotateSelected, selectDevice, syncInspector
    } = window.PhysicalStage.create({
        DRAG_THRESHOLD_PX, WAKE_LOCK_TEXT, afterDraftChange, announce, bodyMetrics, calibrationFor, calibrationStatus, clearMsg, clone, compactView, deviceEntries, deviceLabel, deviceNumber, deviceRows, el, finiteOr, formatNumber, isOnline, latestProfile, mutateDraft, numberedLabel, populateDeviceCard, profileFor, pushUndo, roundTo, selectedSlot, setInputValue, shortId, showError, showTab, state, syncTabDots, validPair
    });

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
            const value = num(input.value);
            const valid = value !== null && (!validate || validate(value));
            markInvalid(input, !valid);
            if (!before) return;
            pushUndo(before);
            before = document.activeElement === input && state.draft
                ? clone(state.draft) : null;
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
                markInvalid(el.profilePixelWidth, true);
                markInvalid(el.profilePixelHeight, true);
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
        if (!el.calOrientation.value || !["tab", "fullscreen", "standalone"].includes(el.calMode.value)) {
            throw new ValidationError("Choose the tablet orientation and mode.");
        }
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
            ...(el.calMethod.value.trim() === "ruler-measured" ? { viewport_guard: true } : {}),
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

    function fillViewport(viewport) {
        setInputValue(el.calViewportWidth, viewport ? viewport.width : "");
        setInputValue(el.calViewportHeight, viewport ? viewport.height : "");
        setInputValue(el.calDpr, viewport ? viewport.dpr : "");
        el.calOrientation.value = viewport ? String(viewport.orientation) : "";
        el.calMode.value = viewport ? viewport.mode : "";
    }

    function fillCalibrationForm(calibration, profile) {
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
            fillViewport(window.PhysicalCalibration.selectedViewport(state.roster, state.selectedId));
            setSelectValue(el.calQuarterTurn, 0);
            setSelectValue(el.calAnchorEdge, "top-left");
            setInputValue(el.calOffsetX, "");
            setInputValue(el.calOffsetY, "");
            setInputValue(el.calMmCssX, "");
            setInputValue(el.calMmCssY, "");
            setInputValue(el.calUncertainty, "");
            setInputValue(el.calMethod, "manual");
        }
        state.calDirty = false;
    }

    const rulerReview = new window.PhysicalCalibration.RulerReview();

    function rulerInputs() {
        const measurements = {};
        ["x", "y"].forEach(function (axis) {
            measurements[axis] = {
                mm: document.getElementById("cal-ruler-mm-" + axis).value,
                px: document.getElementById("cal-ruler-span-" + axis).value,
                error: document.getElementById("cal-ruler-error-" + axis).value
            };
        });
        return measurements;
    }

    function rulerContext() {
        const viewport = window.PhysicalCalibration.selectedViewport(state.roster, state.selectedId);
        const revision = Number(el.calProfileRevision.value);
        const profile = profileFor(state.selectedId, revision);
        if (!profile) throw new Error("The selected profile revision is unavailable. Reload the tablet measurements.");
        const bodies = window.PhysicalCalibration.rulerCheckBodies(state.selectedId, revision,
            Number(el.calQuarterTurn.value), viewport, rulerInputs());
        return { viewport: viewport, bodies: bodies, key: JSON.stringify({ bodies: bodies, viewport: viewport, profile: profile }) };
    }

    function rulerSaveBlocked() {
        const measurements = rulerInputs();
        if (rulerReview.status === "idle" && !measurements.x.mm && !measurements.y.mm
            && el.calMethod.value.trim() !== "ruler-measured") return false;
        try { return !rulerReview.canSave(rulerContext().key); }
        catch (_) { return true; }
    }

    function invalidateRuler() {
        rulerReview.invalidate();
        document.getElementById("cal-ruler-decision").hidden = true;
        if (rulerReview.status === "stale") {
            const preview = document.getElementById("cal-ruler-preview");
            preview.hidden = false;
            preview.textContent = "Measurement or mapping changed. Check the current ruler measurements again before saving.";
        }
        el.btnCalibrationSave.disabled = state.busy || rulerSaveBlocked();
    }

    async function checkRuler() {
        if (state.busy || rulerReview.status === "checking") return;
        let context;
        try {
            context = rulerContext();
            rulerReview.begin(context.key);
            state.calDirty = true;
            syncTabDots();
            const preview = document.getElementById("cal-ruler-preview");
            preview.hidden = false;
            preview.textContent = "Checking both CSS axes. Nothing has been saved.";
            document.getElementById("cal-ruler-decision").hidden = true;
            renderCalibrationHelper();
            const results = await Promise.all(context.bodies.map(function (body) {
                return api("POST", "/api/v3/calibration-check", body);
            }));
            if (rulerContext().key !== context.key || !rulerReview.accept(context.key, results)) return;
            preview.textContent = "";
            results.forEach(function (result) {
                const section = document.createElement("section");
                const heading = document.createElement("h4");
                heading.textContent = result.axis.toUpperCase() + " CSS axis maps to native panel "
                    + result.profile.native_axis + " at quarter turn " + result.profile.quarter_turn;
                section.appendChild(heading);
                const derived = result.derived;
                const comparison = result.comparison;
                [
                    "Full labelled span " + result.inputs.span_px + " CSS px. Measured "
                        + result.inputs.span_mm + " ± " + result.inputs.span_error_mm + " mm.",
                    "Derived " + formatNumber(derived.mm_per_css, 8) + " ± "
                        + formatNumber(derived.mm_per_css_uncertainty, 8) + " mm/CSS. " + derived.quality_label + ".",
                    "Supplied full panel " + result.profile.native_axis + " " + formatNumber(comparison.supplied_mm, 3)
                        + " mm from profile r" + result.profile.revision + ". Ruler-implied usable panel extent "
                        + formatNumber(comparison.implied_mm, 3) + " ± "
                        + formatNumber(result.extrapolated_uncertainty.measured_mm, 3) + " mm.",
                    result.decision.required ? "Disagreement. Choose explicitly below." : "Within the propagated comparison tolerance."
                ].forEach(function (text) {
                    const p = document.createElement("p");
                    p.textContent = text;
                    section.appendChild(p);
                });
                preview.appendChild(section);
            });
            const note = document.createElement("p");
            note.textContent = "Both axes are measured separately. Browser insets can make the usable viewport smaller than the full panel, especially in tab or standalone mode. Review panel offsets below. No values were averaged or saved. Existing layout pins stay unchanged.";
            preview.appendChild(note);
            document.getElementById("cal-ruler-decision").hidden = false;
            preview.focus();
        } catch (error) {
            if (context && rulerReview.key !== context.key) return;
            invalidateRuler();
            setMsg(el.calibrationMsg, errorDetail(error), "err");
        } finally { renderCalibrationHelper(); }
    }

    function decideRuler(choice) {
        if (state.busy) return;
        try {
            const context = rulerContext();
            if (rulerReview.key !== context.key) throw new Error("The tablet or measurement changed. Check again.");
            rulerReview.decide(choice);
            document.getElementById("cal-ruler-decision").hidden = true;
            if (choice === "use_ruler") {
                fillViewport(context.viewport);
                const results = rulerReview.results;
                setInputValue(el.calMmCssX, results[0].derived.mm_per_css);
                setInputValue(el.calMmCssY, results[1].derived.mm_per_css);
                setInputValue(el.calUncertainty, Math.max(...results.map(function (result) {
                    return result.extrapolated_uncertainty.measured_mm;
                })));
                setInputValue(el.calMethod, "ruler-measured");
                state.calDirty = true;
                setMsg(el.calibrationMsg, "Ruler chosen. Review offsets and Save calibration to create a new revision. Supplied profile and existing layout pins stay unchanged.", "info");
                renderCalibrationHelper();
                el.btnCalibrationSave.focus();
            } else if (choice === "keep_supplied") {
                setMsg(el.calibrationMsg, "Supplied measurements kept. Nothing was written; the profile and existing mapping stay unchanged. No ruler scale will be saved.", "ok");
                document.getElementById("cal-use-ruler").focus();
            } else {
                document.getElementById("cal-ruler-mm-x").value = "";
                document.getElementById("cal-ruler-mm-y").value = "";
                invalidateRuler();
                setMsg(el.calibrationMsg, "Measure each line again using its current labelled span, then check both axes.", "info");
                document.getElementById("cal-ruler-mm-x").focus();
            }
            syncTabDots();
        } catch (error) {
            invalidateRuler();
            setMsg(el.calibrationMsg, errorDetail(error), "err");
        }
        renderCalibrationHelper();
    }

    function renderCalibrationHelper() {
        const v = window.PhysicalCalibration.selectedViewport(state.roster, state.selectedId);
        document.getElementById("cal-live-viewport").textContent = v
            ? "Selected tablet: " + v.width + " × " + v.height + " CSS px · DPR " + v.dpr + " · " + v.orientation + "° · " + v.mode
            : "Waiting for the selected tablet’s online viewport at 100% zoom. Advanced manual entry is available.";
        document.getElementById("cal-use-viewport").disabled = !v || state.busy;
        document.getElementById("cal-use-ruler").disabled = !v || state.busy || rulerReview.status === "checking";
        if (rulerReview.key && ["checking", "review", "prepared"].includes(rulerReview.status)) {
            try { if (rulerContext().key !== rulerReview.key) invalidateRuler(); }
            catch (_) { invalidateRuler(); }
        }
        el.btnCalibrationSave.disabled = state.busy || rulerSaveBlocked();
    }

    async function loadRulerAddress() {
        const link = document.getElementById("cal-ruler-link");
        const note = document.getElementById("cal-ruler-address-note");
        try {
            const config = await api("GET", "/operator-config");
            const url = window.PhysicalCalibration.rulerUrl(config.tablet_origin);
            if (!url) throw new Error("No tablet origin");
            link.href = url;
            link.textContent = url;
            link.hidden = false;
            document.getElementById("cal-copy-ruler").hidden = false;
            note.textContent = "Open this address on the selected tablet in its existing browser identity.";
        } catch (_) {
            note.textContent = "Set the server’s tablet origin to a tablet-reachable HTTP(S) address. A loopback address works only on this computer.";
        }
    }

    function updateDeviceCardHeadings() {
        const id = state.selectedId;
        const profile = latestProfile(id);
        el.deviceCardName.textContent = id ? numberedLabel(id, profile) : "–";
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
            el.calibrationCurrent.textContent = "No calibration saved. Use the tablet ruler or enter measured calibration values manually.";
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
            el.calibrationCurrent.dataset.kind = status.kind;
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

        if (changed) {
            rulerReview.reset();
            document.getElementById("cal-ruler-preview").hidden = true;
            document.getElementById("cal-ruler-decision").hidden = true;
            document.getElementById("cal-ruler-error-x").value = "";
            document.getElementById("cal-ruler-error-y").value = "";
            document.getElementById("cal-ruler-mm-x").value = "";
            document.getElementById("cal-ruler-mm-y").value = "";
            document.getElementById("cal-ruler-span-x").value = "200";
            document.getElementById("cal-ruler-span-y").value = "200";
        }
        updateDeviceCardHeadings();
        updateCurrentLines();
        const modelSelect = document.getElementById("tablet-model");
        const assignment = state.tabletAssignments[id] || { mode: "auto" };
        if (changed || !modelSelect.options.length) {
            modelSelect.textContent = "";
            [["", "Choose a confirmed model or manual measurements"], ["manual", "Manual measurements"]].concat(
                Object.keys(state.tabletModels).map(function (key) { return [key, state.tabletModels[key].label]; })
            ).forEach(function (item) {
                const option = document.createElement("option");
                option.value = item[0]; option.textContent = item[1]; modelSelect.appendChild(option);
            });
            modelSelect.value = assignment.mode === "explicit" ? assignment.model_id : assignment.mode === "manual" ? "manual" : "";
        }
        const record = state.roster[id] || {};
        const matches = Object.keys(state.tabletModels).filter(function (key) {
            const model = state.tabletModels[key];
            return Math.min(record.screen_width, record.screen_height) === Math.min(model.screen_width, model.screen_height)
                && Math.max(record.screen_width, record.screen_height) === Math.max(model.screen_width, model.screen_height)
                && Math.abs(record.screen_dpr - model.dpr) < 0.02 && record.platform_family === model.platform;
        });
        document.getElementById("tablet-model-status").textContent = matches.length === 1
            ? "Looks like " + state.tabletModels[matches[0]].label + ". Choose that model and Confirm only after checking the hardware. Screen signature is a suggestion, not proof."
            : matches.length ? "Ambiguous screen signature." : "Unknown screen signature.";
        renderCalibrationHelper();

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
            state.tabletAssignments[id] = { mode: "manual", model_id: null };
            document.getElementById("tablet-model").value = "manual";
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
            if (rulerSaveBlocked()) throw new ValidationError("Check the current ruler measurements and choose Use ruler before saving. Keep supplied writes nothing.");
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
            state.tabletAssignments[id] = { mode: "manual", model_id: null };
            document.getElementById("tablet-model").value = "manual";
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
     * Media library and playlist authoring
     * ---------------------------------------------------------------- */

    function normalizeLibraryAsset(raw) {
        if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
        const id = typeof raw.id === "string" && raw.id
            ? raw.id
            : (typeof raw.asset_id === "string" && raw.asset_id ? raw.asset_id : null);
        if (!id) return null;
        const mime = typeof raw.mime === "string" ? raw.mime : "";
        const kind = raw.kind === "video" || mime.indexOf("video/") === 0 ? "video" : "still";
        const rawDuration = raw.durationMs !== undefined ? raw.durationMs : raw.duration_ms;
        const duration = Number(rawDuration);
        const posterRaw = raw.poster || raw.thumbnail;
        const poster = posterRaw && typeof posterRaw === "object" && !Array.isArray(posterRaw)
            && typeof posterRaw.url === "string" ? posterRaw.url : null;
        const width = Number(raw.intrinsicWidth !== undefined ? raw.intrinsicWidth : raw.width);
        const height = Number(raw.intrinsicHeight !== undefined ? raw.intrinsicHeight : raw.height);
        return {
            id: id,
            name: typeof raw.name === "string" && raw.name !== "" ? raw.name : id,
            mime: mime,
            kind: kind,
            durationMs: kind === "video" && Number.isFinite(duration) && duration > 0
                ? Math.round(duration) : null,
            bytes: Number.isFinite(Number(raw.bytes)) ? Number(raw.bytes) : null,
            width: Number.isFinite(width) && width > 0 ? Math.round(width) : null,
            height: Number.isFinite(height) && height > 0 ? Math.round(height) : null,
            poster: poster
        };
    }

    function libraryAsset(id) {
        for (let index = 0; index < state.library.length; index += 1) {
            if (state.library[index].id === id) return state.library[index];
        }
        return null;
    }

    async function loadLibrary(quiet) {
        if (state.libraryLoading) return false;
        state.libraryLoading = true;
        state.libraryState = state.library.length > 0 ? "refreshing" : "pending";
        state.libraryError = null;
        if (!quiet) clearMsg(el.playlistLibraryMsg);
        renderLibraryOptions();
        try {
            const payload = await api("GET", API_MEDIA);
            const raw = Array.isArray(payload)
                ? payload
                : payload && Array.isArray(payload.assets) ? payload.assets : null;
            if (raw === null) throw new Error("the answer was not a file library");
            const seen = new Set();
            const items = [];
            raw.forEach(function (entry) {
                const asset = normalizeLibraryAsset(entry);
                if (!asset || seen.has(asset.id)) return;
                seen.add(asset.id);
                items.push(asset);
            });
            items.sort(function (left, right) {
                const byName = left.name.toLowerCase().localeCompare(right.name.toLowerCase());
                return byName !== 0 ? byName : left.id.localeCompare(right.id);
            });
            state.library = items;
            state.libraryState = "ready";
        } catch (error) {
            state.libraryState = "error";
            state.libraryError = errorDetail(error);
        }
        state.libraryLoading = false;
        renderPlaylist();
        renderPlayback();
        if (!quiet) {
            if (state.libraryState === "ready") {
                setMsg(el.playlistLibraryMsg,
                    state.library.length + (state.library.length === 1 ? " file" : " files")
                        + " in the library.", "ok");
            } else {
                setMsg(el.playlistLibraryMsg,
                    "Library unavailable: " + state.libraryError, "err");
            }
        }
        return state.libraryState === "ready";
    }

    function normalizePlaylistDocument(document) {
        if (!document || typeof document !== "object" || !Array.isArray(document.items)) {
            return null;
        }
        const items = [];
        document.items.forEach(function (raw) {
            if (!raw || typeof raw !== "object") return;
            if (typeof raw.asset !== "string" || raw.asset === "") return;
            items.push({ asset: raw.asset, dwell_ms: clampDwell(raw.dwell_ms) });
        });
        const revision = Number(document.revision);
        return {
            items: items,
            loop: document.loop !== false,
            revision: Number.isFinite(revision) ? revision : null
        };
    }

    async function loadPlaylist() {
        state.playlistLoading = true;
        try {
            const payload = await api("GET", API_PLAYLIST);
            state.playlistEtag = payload && typeof payload.etag === "string" ? payload.etag : null;
            const document = normalizePlaylistDocument(payload ? payload.playlist : null);
            state.savedPlaylist = document === null ? null : clone(document);
            if (document !== null && !state.playlistDirty) {
                state.playlist = document;
                state.playlistDirty = false;
            }
            state.playlistLoaded = true;
            renderPlaylist();
            renderPlayback();
            return true;
        } catch (error) {
            setMsg(el.playlistMsg, "Could not load the playlist: " + errorDetail(error), "err");
            return false;
        } finally {
            state.playlistLoading = false;
            renderPlayback();
        }
    }

    function renderLibraryOptions() {
        const select = el.playlistLibrary;
        if (!select) return;
        const previous = select.value;
        clearChildren(select);

        let placeholder = "Choose a file";
        if (state.libraryState === "pending") placeholder = "Loading the library…";
        else if (state.libraryState === "refreshing") placeholder = "Refreshing the library…";
        else if (state.libraryState === "error") placeholder = "Library unavailable — add by content id";
        else if (state.library.length === 0) placeholder = "No uploaded files yet";
        const first = document.createElement("option");
        first.value = "";
        first.textContent = placeholder;
        select.appendChild(first);

        state.library.forEach(function (asset) {
            const option = document.createElement("option");
            option.value = asset.id;
            option.textContent = asset.name + " — "
                + (asset.kind === "video" ? "video " + formatDuration(asset.durationMs) : "still");
            select.appendChild(option);
        });

        select.disabled = state.libraryState !== "ready" || state.library.length === 0;
        if (previous && select.querySelector('option[value="' + previous.replace(/"/g, '\\"') + '"]')) {
            select.value = previous;
        } else {
            select.selectedIndex = 0;
        }
        if (el.btnPlaylistAdd) {
            el.btnPlaylistAdd.disabled = state.playlistSaving || !select.value;
        }
    }

    function renderPlaylist() {
        if (!el.playlistItems) return;
        renderLibraryOptions();
        clearChildren(el.playlistItems);

        state.playlist.items.forEach(function (item, index) {
            el.playlistItems.appendChild(buildPlaylistRow(item, index));
        });

        el.playlistEmpty.hidden = state.playlist.items.length > 0;
        const count = state.playlist.items.length;
        setTextIfChanged(el.playlistCount, count + (count === 1 ? " item" : " items"));
        if (el.playlistLoop && document.activeElement !== el.playlistLoop) {
            el.playlistLoop.checked = state.playlist.loop;
        }
        syncPlaylistFooter();

        if (state.playlistFocus) {
            const focus = state.playlistFocus;
            state.playlistFocus = null;
            const node = el.playlistItems.querySelector(
                '[data-action="' + focus.action + '"][data-index="' + focus.index + '"]');
            if (node) {
                try { node.focus({ preventScroll: true }); }
                catch (error) { node.focus(); }
            }
        }
        syncPlaylistCurrent();
    }

    function syncPlaylistFooter() {
        const count = state.playlist.items.length;
        if (el.playlistHint) {
            let text = "At least one item.";
            if (state.playlistSaving) text = "Saving…";
            else if (state.playlistDirty) text = "Unsaved changes.";
            else if (repoSavedPlaylist()) text = "Saved on the server.";
            el.playlistHint.textContent = text;
            el.playlistHint.dataset.kind = state.playlistDirty ? "warn" : "";
        }
        if (el.playlistUndo) {
            el.playlistUndo.hidden = !state.playlistRemoval;
        }
        if (el.btnPlaylistSave) {
            el.btnPlaylistSave.disabled = state.playlistSaving || count === 0;
            el.btnPlaylistSave.textContent = state.playlistSaving ? "Saving…" : "Save playlist";
        }
    }

    function syncPlaylistCurrent() {
        if (!el.playlistItems) return;
        const status = state.playback;
        const entry = liveSlotEntry(status, "current");
        const occurrence = entry ? entry.occurrence : null;
        const index = occurrence ? Number(occurrence.item_index) : NaN;
        const reported = status ? Number(status.playlist_revision) : NaN;
        const revision = Number.isFinite(reported)
            ? reported
            : occurrence ? Number(occurrence.playlist_revision) : NaN;
        const sameRevision = state.playlist.revision === null
            || !Number.isFinite(revision) || revision === state.playlist.revision;
        const liveAsset = entry ? entry.asset : null;
        const rows = el.playlistItems.querySelectorAll(".playlist-item");
        for (let offset = 0; offset < rows.length; offset += 1) {
            const row = rows[offset];
            const rowIndex = Number(row.dataset.index);
            const rowItem = Number.isInteger(rowIndex)
                ? state.playlist.items[rowIndex] : null;
            const sameAsset = !liveAsset || Boolean(rowItem && rowItem.asset === liveAsset);
            const match = !state.playlistDirty && sameRevision && sameAsset
                && Number.isFinite(index) && rowIndex === index;
            row.dataset.current = match ? "true" : "false";
        }
    }

    function repoSavedPlaylist() {
        return state.playlistLoaded && !state.playlistDirty && state.playlistEtag !== null;
    }

    function buildPlaylistRow(item, index) {
        const asset = libraryAsset(item.asset);
        const isVideo = Boolean(asset && asset.kind === "video");
        const itemNode = document.createElement("li");
        itemNode.className = "playlist-item";
        itemNode.dataset.index = String(index);
        itemNode.dataset.kind = asset ? asset.kind : "unknown";

        const thumbUrl = asset ? asset.poster : null;
        let thumb;
        if (thumbUrl) {
            thumb = document.createElement("img");
            thumb.className = "playlist-thumb";
            thumb.src = thumbUrl;
            thumb.alt = "";
            thumb.loading = "lazy";
        } else {
            thumb = document.createElement("span");
            thumb.className = "playlist-thumb playlist-thumb-none";
            thumb.setAttribute("aria-hidden", "true");
        }

        const body = document.createElement("div");
        body.className = "playlist-item-body";
        const head = document.createElement("div");
        head.className = "playlist-item-head";
        appendText(head, "span", "playlist-index", String(index + 1) + ".");
        appendText(head, "span", "playlist-name",
            asset ? asset.name : "Unknown asset " + shortId(item.asset) + "…");
        appendText(head, "span", "playlist-now", "Now");
        const kind = appendText(head, "span", "playlist-kind",
            asset ? (isVideo ? "Video" : "Still") : "Unknown");
        kind.dataset.kind = asset ? asset.kind : "unknown";
        const meta = appendText(body, "p", "playlist-item-meta", "");
        if (isVideo) {
            meta.textContent = "Clip " + formatDuration(asset.durationMs)
                + " · dwell is the clip length";
        } else if (asset) {
            meta.textContent = "Still · " + formatDuration(item.dwell_ms) + " dwell";
        } else {
            meta.textContent = item.asset;
        }
        body.insertBefore(head, meta);

        const dwell = document.createElement("div");
        dwell.className = "playlist-dwell";
        if (isVideo) {
            appendText(dwell, "span", "playlist-dwell-label", "Fixed dwell");
            appendText(dwell, "strong", "playlist-dwell-value", formatDuration(asset.durationMs));
        } else {
            const inputId = "playlist-dwell-" + index;
            const label = appendText(dwell, "label", "playlist-dwell-label", "Dwell (ms)");
            label.setAttribute("for", inputId);
            const input = document.createElement("input");
            input.className = "inp playlist-dwell-input";
            input.id = inputId;
            input.type = "number";
            input.min = String(MIN_DWELL_MS);
            input.max = String(MAX_DWELL_MS);
            input.step = "100";
            input.inputMode = "numeric";
            input.autocomplete = "off";
            input.value = String(item.dwell_ms);
            input.addEventListener("input", function () {
                const value = Number(input.value);
                if (Number.isFinite(value) && value >= MIN_DWELL_MS && value <= MAX_DWELL_MS) {
                    state.playlist.items[index].dwell_ms = Math.round(value);
                    markPlaylistDirty();
                }
            });
            input.addEventListener("change", function () {
                const next = clampDwell(input.value);
                input.value = String(next);
                state.playlist.items[index].dwell_ms = next;
                markPlaylistDirty();
            });
            dwell.appendChild(input);
        }

        const controls = document.createElement("div");
        controls.className = "playlist-controls";

        function addControl(label, action, disabled, handler) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-ghost btn-sm playlist-control";
            button.dataset.action = action;
            button.dataset.index = String(index);
            button.textContent = label;
            button.disabled = disabled;
            button.setAttribute("aria-label", label + " " + (asset ? asset.name : item.asset)
                + ", position " + (index + 1));
            button.addEventListener("click", handler);
            controls.appendChild(button);
        }

        addControl("Up", "up", index === 0, function () {
            movePlaylistItem(index, -1);
        });
        addControl("Down", "down", index === state.playlist.items.length - 1, function () {
            movePlaylistItem(index, 1);
        });
        addControl("Remove", "remove", false, function () {
            removePlaylistItem(index);
        });

        itemNode.appendChild(thumb);
        itemNode.appendChild(body);
        itemNode.appendChild(dwell);
        itemNode.appendChild(controls);
        return itemNode;
    }

    function markPlaylistDirty() {
        const saved = state.savedPlaylist;
        state.playlistDirty = saved
            ? playlistSignature(state.playlist) !== playlistSignature(saved)
            : state.playlist.items.length > 0;
        syncPlaylistFooter();
        syncTabDots();
        const gate = playbackPreflight();
        renderPlaybackPreflight(gate);
        renderPlaybackButtons(state.playback, gate);
    }

    function playlistSignature(playlist) {
        if (!playlist) return "";
        const items = Array.isArray(playlist.items) ? playlist.items : [];
        return JSON.stringify({
            loop: playlist.loop !== false,
            items: items.map(function (item) {
                return [item.asset, clampDwell(item.dwell_ms)];
            })
        });
    }

    function movePlaylistItem(index, delta) {
        const target = index + delta;
        const items = state.playlist.items;
        if (target < 0 || target >= items.length) return;
        const moved = items[index];
        items[index] = items[target];
        items[target] = moved;
        state.playlistFocus = { index: target, action: delta < 0 ? "up" : "down" };
        markPlaylistDirty();
        renderPlaylist();
    }

    function removePlaylistItem(index) {
        const item = state.playlist.items[index];
        if (!item) return;
        state.playlist.items.splice(index, 1);
        state.playlistRemoval = { item: clone(item), index: index };
        state.playlistFocus = {
            index: Math.min(index, state.playlist.items.length - 1),
            action: "remove"
        };
        markPlaylistDirty();
        renderPlaylist();
        announce("Removed " + (libraryAsset(item.asset)
            ? libraryAsset(item.asset).name : shortId(item.asset) + "…")
            + " from the playlist. Undo is available.", "info");
    }

    function undoPlaylistRemoval() {
        const removal = state.playlistRemoval;
        if (!removal) return;
        const index = Math.min(removal.index, state.playlist.items.length);
        state.playlist.items.splice(index, 0, removal.item);
        state.playlistRemoval = null;
        state.playlistFocus = { index: index, action: "remove" };
        markPlaylistDirty();
        renderPlaylist();
        announce("Restored the removed playlist item.", "ok");
    }

    function addPlaylistAsset(id, dwell) {
        if (typeof id !== "string" || id === "") return false;
        const asset = libraryAsset(id);
        const isVideo = Boolean(asset && asset.kind === "video");
        const value = isVideo && asset.durationMs !== null
            ? clampDwell(asset.durationMs)
            : clampDwell(dwell === undefined ? 5000 : dwell);
        state.playlist.items.push({ asset: id, dwell_ms: value });
        markPlaylistDirty();
        renderPlaylist();
        announce("Added " + (asset ? asset.name : shortId(id) + "…") + " to the playlist.", "ok");
        return true;
    }

    async function savePlaylist() {
        if (state.playlistSaving) return false;
        clearMsg(el.playlistMsg);
        const items = state.playlist.items;
        if (items.length === 0) {
            setMsg(el.playlistMsg, "Add at least one item before saving.", "err");
            return false;
        }
        if (state.playlistEtag === null) {
            setMsg(el.playlistMsg, "The playlist did not load, so there is no ETag to save against. Refresh the page.", "err");
            return false;
        }
        const payloadItems = items.map(function (item) {
            const asset = libraryAsset(item.asset);
            const dwell = asset && asset.kind === "video" && asset.durationMs !== null
                ? clampDwell(asset.durationMs)
                : clampDwell(item.dwell_ms);
            return { asset: item.asset, dwell_ms: dwell };
        });

        state.playlistSaving = true;
        syncPlaylistFooter();
        let savedOk = false;
        try {
            const saved = await api("PUT", API_PLAYLIST, {
                items: payloadItems,
                loop: Boolean(el.playlistLoop && el.playlistLoop.checked)
            }, { ifMatch: state.playlistEtag });
            state.playlistEtag = saved && typeof saved.etag === "string" ? saved.etag : null;
            const document = normalizePlaylistDocument(saved ? saved.playlist : null);
            if (document !== null) state.playlist = document;
            else state.playlist.loop = Boolean(el.playlistLoop && el.playlistLoop.checked);
            state.playlistLoaded = true;
            state.playlistDirty = false;
            state.playlistRemoval = null;
            state.savedPlaylist = clone(state.playlist);
            savedOk = true;
            setMsg(el.playlistMsg, "Playlist saved: "
                + state.playlist.items.length
                + (state.playlist.items.length === 1 ? " item." : " items."), "ok");
            announce("Playlist saved.", "ok");
        } catch (error) {
            const detail = errorDetail(error);
            setMsg(el.playlistMsg, error && error.status === 412
                ? "Playlist changed on the server. Refresh the page and add your changes again. " + detail
                : detail, "err");
            announce("Playlist save failed.", "err");
        } finally {
            state.playlistSaving = false;
            renderPlaylist();
            renderPlayback();
            syncTabDots();
        }
        return savedOk;
    }

    /* ---------------------------------------------------------------- *
     * Playback status
     * ---------------------------------------------------------------- */

    function factRow(term, value) {
        const row = document.createElement("div");
        row.className = "fact";
        appendText(row, "dt", "", term);
        appendText(row, "dd", "", value === null || value === undefined ? "—" : String(value));
        return row;
    }

    function renderFactList(node, facts) {
        if (!node) return;
        clearChildren(node);
        facts.forEach(function (fact) {
            if (!fact || fact[1] === null || fact[1] === undefined || fact[1] === "") return;
            node.appendChild(factRow(fact[0], fact[1]));
        });
    }

    const {
        actionFromPauseButton, liveSlotEntry, playbackAction, playbackPreflight, refreshPlayback, renderPlayback, renderPlaybackButtons, renderPlaybackPreflight, restorePlaybackExclusions
    } = window.PhysicalPlayback.create({
        API_PLAYBACK, ApiError, announce, api, appendText, clearChildren, clearMsg, compareDeviceIds, deviceLabel, deviceNumber, el, errorDetail, formatDuration, formatSpan, isDirty, isOnline, latestProfile, libraryAsset, maybeChooseInitialTab, numberTag, numberedLabel, savePlaylist, setMsg, setTextIfChanged, shortId, state, syncPlaylistCurrent, syncTopbarTransport, renderFactList
    });

    /* ---------------------------------------------------------------- *
     * Field check: diagnostics
     * ---------------------------------------------------------------- */

    function diagChip() {
        if (!el.diagState) return;
        let text = "loading";
        let kind = "info";
        if (state.diagnosticsState === "refreshing") text = "refreshing";
        else if (state.diagnosticsState === "ready") { text = "loaded"; kind = "ok"; }
        else if (state.diagnosticsState === "error") { text = "error"; kind = "err"; }
        else if (state.diagnosticsState === "forbidden") { text = "unavailable"; kind = "warn"; }
        setTextIfChanged(el.diagState, text);
        el.diagState.dataset.kind = kind;
    }

    function wakeLockSummary(counts) {
        const order = ["held", "released", "unsupported", "insecure", "denied"];
        const source = counts && typeof counts === "object" ? counts : {};
        return order.map(function (key) {
            const value = Number(source[key]);
            return key + " " + (Number.isFinite(value) ? value : 0);
        }).join(" · ");
    }

    function problemText(problem) {
        if (typeof problem === "string") return problem;
        try { return JSON.stringify(problem); }
        catch (error) { return String(problem); }
    }

    function renderIntegrity(integrity) {
        if (!el.diagIntegrity) return;
        if (!integrity || typeof integrity !== "object") {
            el.diagIntegrity.hidden = true;
            clearChildren(el.diagProblems);
            return;
        }
        el.diagIntegrity.hidden = false;
        const problems = Array.isArray(integrity.problems) ? integrity.problems : [];
        const ok = integrity.ok === true && problems.length === 0;
        el.diagIntegrity.dataset.state = ok ? "ok" : "bad";
        if (el.diagIntegrityText) {
            el.diagIntegrityText.textContent = ok
                ? "All ready objects match their recorded ids."
                : "Damaged or missing objects were found. These files do not match their recorded ids.";
        }
        clearChildren(el.diagProblems);
        problems.forEach(function (problem) {
            appendText(el.diagProblems, "li", "diag-problem", problemText(problem));
        });
    }

    function renderDiagnostics() {
        diagChip();
        if (el.btnDiagDownload) {
            el.btnDiagDownload.disabled = state.diagnosticsLoading
                || state.diagnosticsState !== "ready";
        }
        if (!el.diagGrid) return;
        const data = state.diagnostics;
        const facts = [];
        if (!data) {
            facts.push(["Status", state.diagnosticsState === "loading"
                ? "Reading diagnostics…" : "No diagnostics loaded."]);
        } else {
            const media = data.media && typeof data.media === "object" ? data.media : {};
            const db = data.db && typeof data.db === "object" ? data.db : {};
            const backup = data.backup && typeof data.backup === "object" ? data.backup : {};
            const clients = data.clients && typeof data.clients === "object" ? data.clients : {};
            facts.push(["Last checked", new Date(state.diagnosticsCapturedAt).toLocaleString()]);
            facts.push(["Storage",
                formatBytes(media.used_bytes) + " used of " + formatBytes(media.quota_bytes)
                + " (" + formatPercent(media.used_bytes, media.quota_bytes) + ")"]);
            facts.push(["Free / reserve",
                formatBytes(media.free_bytes) + " free · " + formatBytes(media.reserve_bytes)
                + " reserve"]);
            facts.push(["Objects",
                (media.objects ?? "—") + " objects · " + (media.assets ?? "—") + " assets · "
                + (media.orphans ?? "—") + " orphans"]);
            facts.push(["Database",
                "schema " + (db.schema ?? "—") + " · " + formatBytes(db.bytes)]);
            facts.push(["Backup",
                backup.last_manifest_at
                    ? formatTime(backup.last_manifest_at) + " · "
                        + relativeAge(backup.last_manifest_at)
                    : "No backup manifest found"]);
            facts.push(["Clients",
                (clients.online ?? "—") + " online · " + (clients.total ?? "—") + " registered"]);
            facts.push(["Wake lock", wakeLockSummary(clients.wake_lock)]);
        }
        renderFactList(el.diagGrid, facts);
    }

    async function loadDiagnostics(verify) {
        if (state.diagnosticsLoading) return;
        state.diagnosticsLoading = true;
        renderIntegrity(null);
        state.diagnosticsState = state.diagnostics ? "refreshing" : "loading";
        if (el.btnDiagRefresh) el.btnDiagRefresh.disabled = true;
        if (el.btnDiagVerify) el.btnDiagVerify.disabled = true;
        renderDiagnostics();
        try {
            const data = await api("GET", API_DIAGNOSTICS + (verify ? "?verify=1" : ""));
            if (!data || typeof data !== "object" || !data.media || !data.db) {
                throw new Error("the answer was not a diagnostics report");
            }
            state.diagnostics = data;
            state.diagnosticsCapturedAt = new Date().toISOString();
            state.diagnosticsState = "ready";
            state.diagnosticsError = null;
            if (verify) {
                const integrity = data.media && data.media.integrity
                    ? data.media.integrity : data.integrity;
                const passed = integrity && integrity.ok === true
                    && (!Array.isArray(integrity.problems) || integrity.problems.length === 0);
                renderIntegrity(integrity);
                setMsg(el.diagMsg, integrity
                    ? (passed ? "Object integrity check passed." : "Object integrity check found problems.")
                    : "This server did not return an integrity report.", integrity ? (passed ? "ok" : "err") : "warn");
            } else {
                setMsg(el.diagMsg, "", null);
            }
            await refreshRoster();
        } catch (error) {
            const forbidden = error && error.status === 403;
            state.diagnosticsState = forbidden ? "forbidden" : "error";
            state.diagnosticsError = errorDetail(error);
            setMsg(el.diagMsg, forbidden
                ? "Diagnostics access was refused. Check the operator admission configuration; uploads do not need to be enabled."
                : "Could not load diagnostics: " + state.diagnosticsError, "err");
        } finally {
            state.diagnosticsLoading = false;
            if (el.btnDiagRefresh) el.btnDiagRefresh.disabled = false;
            if (el.btnDiagVerify) el.btnDiagVerify.disabled = false;
            renderDiagnostics();
        }
    }

    function downloadDiagnostics() {
        if (state.diagnosticsLoading || state.diagnosticsState !== "ready") return;
        const report = {
            format: "tablet-wall-diagnostics-v1",
            captured_at: state.diagnosticsCapturedAt,
            evidence: "Software diagnostics only. Physical tablet validation is pending.",
            diagnostics: state.diagnostics,
        };
        const blob = new Blob([JSON.stringify(report, null, 2) + "\n"], {
            type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "tablet-wall-diagnostics-"
            + state.diagnosticsCapturedAt.replace(/[:.]/g, "-") + ".json";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        setMsg(el.diagMsg, "Diagnostics report downloaded. Review it before sharing.", "ok");
    }

    function refreshRoster() {
        if (!state.rosterRefreshPromise) state.rosterRefreshPromise = fetchRoster();
        return state.rosterRefreshPromise;
    }

    async function fetchRoster() {
        try { if (operatorSync) await operatorSync.reconcile(true); }
        finally { state.rosterRefreshPromise = null; renderAll(); }
    }

    /* ---------------------------------------------------------------- *
     * Saved layouts
     * ---------------------------------------------------------------- */

    async function loadLayouts() {
        try {
            const results = await Promise.all([api("GET", API_LAYOUTS), api("GET", "/api/v3/logical-layouts")]);
            state.savedLayouts = (results[0].layouts || []).concat((results[1].layouts || []).map(function (entry) {
                return Object.assign({}, entry, { logical: true });
            }));
        } catch (error) {
            state.savedLayouts = [];
            setMsg(el.layoutMsg, "Could not load saved layouts: " + errorDetail(error), "err");
        }
        renderSavedLayouts();
        if (operatorDevices) operatorDevices.render();
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
            meta.textContent = entry.logical ? "Logical wall · " + Object.keys(layout.placements || {}).length + " tablets"
                : slotCount + (slotCount === 1 ? " tablet" : " tablets")
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
            recall.dataset.invalid = String(entry.valid === false || entry.invalid === true);
            recall.disabled = state.busy || !state.etag || recall.dataset.invalid === "true";
            recall.addEventListener("click", function () {
                recallLayout(entry.name, entry.logical);
            });

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "btn btn-danger btn-sm";
            remove.textContent = "Delete";
            remove.disabled = state.busy || !state.etag;
            remove.addEventListener("click", function () {
                deleteLayout(entry.name, entry.logical);
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
            buttons[index].disabled = state.busy || !state.etag || state.etagState !== "current" || buttons[index].dataset.invalid === "true";
        }
    }

    async function refreshSnapshotConfig() {
        state.readFence.event();
        const ticket = state.readFence.start();
        const config = await api("GET", API_CONFIG);
        if (state.readFence.accept(ticket)) ingestConfig(config, { preserveDraft: true });
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

        if (isDirty()) {
            setMsg(el.layoutMsg, "Apply or cancel the unapplied draft before saving the committed layout.", "err");
            return;
        }

        setBusy(true);
        try {
            const payload = await api(
                "PUT",
                (state.layoutKind === "logical" ? "/api/v3/logical-layouts" : API_LAYOUTS) + "/" + encodeURIComponent(name),
                undefined,
                { etag: true }
            );
            el.layoutName.value = payload && payload.name ? payload.name : name;
            setMsg(el.layoutMsg, "Saved layout \"" + (payload && payload.name ? payload.name : name) + "\".", "ok");
            announce("Saved " + state.layoutKind + " layout " + (payload && payload.name ? payload.name : name) + ".", "ok");
            await refreshSnapshotConfig();
            await loadLayouts();
        } catch (error) {
            handleWriteError(error, el.layoutMsg);
        } finally {
            setBusy(false);
        }
    }

    async function recallLayout(name, logical) {
        if (state.busy) return;
        if (!state.etag) {
            setMsg(el.layoutMsg, "No configuration ETag is loaded; reload the page.", "err");
            return;
        }
        if (isDirty() && !window.confirm("Recall \"" + name + "\" and discard the unapplied draft?")) {
            return;
        }
        if ((logical ? "logical" : "physical") !== state.layoutKind && !window.confirm("Recall “" + name + "” and switch layout kind? The server must save a named safety copy of the current arrangement. The image stays unchanged.")) return;
        clearError();
        setBusy(true);
        try {
            const payload = await api(
                "POST",
                (logical ? "/api/v3/logical-layouts" : API_LAYOUTS) + "/" + encodeURIComponent(name) + "/recall",
                undefined,
                { etag: true }
            );
            ingestConfig(payload, { resetHistory: true });
            hideConflict();
            clearError();
            announce("Recalled " + (logical ? "logical" : "physical") + " layout " + name + "." + (payload.previous_layout_saved ? " Previous arrangement saved as “" + payload.previous_layout_saved + "”." : ""), "ok");
            await loadLayouts();
        } catch (error) {
            handleWriteError(error, el.layoutMsg);
        } finally {
            setBusy(false);
        }
    }

    async function deleteLayout(name, logical) {
        if (state.busy) return;
        if (!window.confirm("Delete saved layout \"" + name + "\"?")) return;
        clearError();
        setBusy(true);
        try {
            await api(
                "DELETE",
                (logical ? "/api/v3/logical-layouts" : API_LAYOUTS) + "/" + encodeURIComponent(name),
                undefined,
                { etag: true }
            );
            setMsg(el.layoutMsg, "Deleted layout \"" + name + "\".", "ok");
            announce("Deleted saved layout " + name + ".", "ok");
            await refreshSnapshotConfig();
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

        if (state.drag) return;

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

        const nudgeHost = event.target && event.target.closest
            ? event.target.closest("#stage-svg, .nudge-block") : null;
        if (!nudgeHost) return;

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
        tabEntries().forEach(function (entry) {
            if (!entry.tab) return;
            entry.tab.addEventListener("click", function () {
                showTab(entry.name, { persist: true });
            });
        });
        if (el.railTabs) el.railTabs.addEventListener("keydown", onTabKeyDown);
        if (COMPACT_MEDIA) {
            if (typeof COMPACT_MEDIA.addEventListener === "function") {
                COMPACT_MEDIA.addEventListener("change", onCompactChange);
            } else if (typeof COMPACT_MEDIA.addListener === "function") {
                COMPACT_MEDIA.addListener(onCompactChange);
            }
        }

        el.btnUndo.addEventListener("click", undoDraft);
        el.btnRedo.addEventListener("click", redoDraft);
        el.btnApply.addEventListener("click", applyLayout);
        el.btnCancel.addEventListener("click", cancelDraft);
        if (el.btnApplyLocal) {
            el.btnApplyLocal.addEventListener("click", function () {
                el.btnApply.click();
            });
        }
        if (el.btnCancelLocal) {
            el.btnCancelLocal.addEventListener("click", function () {
                el.btnCancel.click();
            });
        }
        el.btnReload.addEventListener("click", reloadConfigWithConfirm);
        el.btnConflictReload.addEventListener("click", reloadConfigWithConfirm);

        el.btnRotate.addEventListener("click", rotateSelected);
        el.btnDeleteSlot.addEventListener("click", deleteSelectedSlot);
        el.btnNudgeXMinus.addEventListener("click", function () { nudgeSelected(-1, 0); });
        el.btnNudgeXPlus.addEventListener("click", function () { nudgeSelected(1, 0); });
        el.btnNudgeYMinus.addEventListener("click", function () { nudgeSelected(0, -1); });
        el.btnNudgeYPlus.addEventListener("click", function () { nudgeSelected(0, 1); });
        el.btnAddSlot.addEventListener("click", addSelectedDevice);
        document.getElementById("apply-tablet-model").addEventListener("click", async function () {
            if (!state.selectedId || state.busy) return;
            if (state.profileDirty || state.calDirty) {
                setMsg(el.profileMsg, "Save or discard your measurement changes before applying a tablet model.", "err");
                return;
            }
            const id = state.selectedId;
            const choice = document.getElementById("tablet-model").value;
            if (!choice) { setMsg(el.profileMsg, "Choose the actual model explicitly or use manual measurements. Automatic matches are suggestions.", "info"); return; }
            if (choice !== "manual" && !window.confirm("Confirm this tablet is “" + (state.tabletModels[choice] && state.tabletModels[choice].label || choice) + "”? Model measurements remain approximate.")) return;
            await refreshRoster();
            if (state.profileDirty || state.calDirty) {
                setMsg(el.profileMsg, "Save or discard your measurement changes before applying a tablet model.", "err");
                return;
            }
            if (state.etagState !== "current" || state.busy) return;
            const revision = state.revision;
            const generation = state.generation;
            setBusy(true);
            let modelApplied = false;
            try {
                const result = await api("PUT", "/api/v3/tablet-assignments/" + encodeURIComponent(id),
                    { mode: choice === "manual" ? "manual" : "explicit", model_id: choice === "manual" ? null : choice }, { etag: true });
                modelApplied = true;
                if (!result || !result.etag) throw new Error("The server did not return a configuration ETag.");
                state.etag = result.etag;
                const config = await api("GET", API_CONFIG);
                if (config.etag !== result.etag || config.revision !== revision || config.generation !== generation
                        || state.revision !== revision || state.generation !== generation
                        || state.etag !== result.etag || state.etagState !== "current"
                        || state.profileDirty || state.calDirty) {
                    showConflict("The configuration changed while applying the tablet model.");
                    return;
                }
                state.tabletAssignments = config.tablet_assignments || {};
                state.displays = config.displays || [];
                state.calibrations = config.calibrations || [];
                state.displays.forEach(rememberProfile); state.calibrations.forEach(rememberCalibration);
                setBusy(false);
                const pair = validPair(id);
                if (pair && state.draft && state.draft.slots[id]) {
                    mutateDraft(function (draft) {
                        draft.slots[id].profile_revision = pair.profile.revision;
                        draft.slots[id].calibration_revision = pair.calibration.revision;
                    });
                }
                populateDeviceCard(true); afterDraftChange();
                announce("Tablet model choice applied.", "ok");
            } catch (error) {
                if (modelApplied) showConflict("The tablet model was applied, but its configuration could not be refreshed.");
                handleWriteError(error, el.profileMsg);
            }
            finally { setBusy(false); }
        });
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
        el.boundsMode.addEventListener("change", function () {
            if (!state.draft) return;
            const mode = el.boundsMode.value === "tablets" ? "tablets" : "fixed";
            if (mode === "tablets" && Object.keys(state.draft.slots).length) {
                const fit = window.PhysicalSizing.fitBounds(
                    state.draft.slots, profileFor, state.draft.sizing.padding
                );
                if (fit.error) {
                    el.boundsMode.value = state.draft.sizing.mode;
                    setMsg(el.sizingMsg, fit.error, "err");
                    announce(fit.error, "err");
                    return;
                }
            }
            mutateDraft(function (draft) { draft.sizing.mode = mode; });
            if (mode === "fixed") clearMsg(el.sizingMsg);
        });
        bindNumberInput(el.boundsPadding, function (value) {
            if (!state.draft || state.draft.sizing.padding === value) return false;
            state.draft.sizing.padding = value;
            return true;
        }, function (value) { return value >= 0; });

        el.btnPackTablets.addEventListener("click", function () {
            if (!state.draft || state.busy) return;
            let columns;
            let gap;
            try {
                columns = requireInteger("Columns", el.packColumns, 1);
                gap = requireNonNegative("Gap", el.packGap);
            } catch (error) {
                setMsg(el.sizingMsg, errorDetail(error), "err");
                announce(errorDetail(error), "err");
                return;
            }
            const orderedSlots = {};
            Object.keys(state.draft.slots).sort().forEach(function (id) {
                orderedSlots[id] = state.draft.slots[id];
            });
            const result = window.PhysicalSizing.packSlots(
                orderedSlots, profileFor, columns, gap, state.draft.sizing.padding
            );
            if (result.error) {
                setMsg(el.sizingMsg, result.error, "err");
                announce(result.error, "err");
                return;
            }
            if (!result.bounds) {
                setMsg(el.sizingMsg, "Add tablets before packing the wall.", "info");
                announce("Add tablets before packing the wall.");
                return;
            }
            const changed = mutateDraft(function (draft) {
                draft.slots = result.slots;
                if (draft.sizing.mode === "tablets") {
                    draft.bounds = result.bounds;
                } else {
                    Object.keys(draft.slots).forEach(function (id) {
                        draft.slots[id].center_x_mm += draft.bounds.x;
                        draft.slots[id].center_y_mm += draft.bounds.y;
                    });
                }
            });
            if (changed) {
                clearMsg(el.sizingMsg);
                announce("Packed " + Object.keys(result.slots).length + " tablets.", "ok");
            }
        });

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
            selectDevice(group.dataset.deviceId, { reveal: true });
        });

        el.profileForm.addEventListener("submit", saveProfile);
        el.calibrationForm.addEventListener("submit", saveCalibration);
        document.getElementById("cal-use-viewport").addEventListener("click", function () {
            const v = window.PhysicalCalibration.selectedViewport(state.roster, state.selectedId);
            if (!v || state.busy) return;
            fillViewport(v);
            invalidateRuler();
            state.calDirty = true;
            syncTabDots();
            setMsg(el.calibrationMsg, "Tablet viewport copied. Review measurements before saving.", "info");
        });
        document.getElementById("cal-copy-ruler").addEventListener("click", async function () {
            const copied = await copyText(document.getElementById("cal-ruler-link").href);
            setMsg(el.calibrationMsg, copied ? "Ruler address copied." : "Copy failed. Copy the visible address manually.", copied ? "ok" : "err");
        });
        document.getElementById("cal-use-ruler").addEventListener("click", checkRuler);
        [["cal-keep-supplied", "keep_supplied"], ["cal-accept-ruler", "use_ruler"], ["cal-measure-again", "remeasure"]].forEach(function (item) {
            document.getElementById(item[0]).addEventListener("click", function () { decideRuler(item[1]); });
        });
        el.profileForm.addEventListener("input", function () {
            state.profileDirty = true;
            syncTabDots();
        });
        el.calibrationForm.addEventListener("input", function () {
            invalidateRuler();
            state.calDirty = true;
            syncTabDots();
        });
        el.profileForm.addEventListener("change", function () {
            state.profileDirty = true;
            syncTabDots();
        });
        el.calibrationForm.addEventListener("change", function () {
            invalidateRuler();
            state.calDirty = true;
            syncTabDots();
        });

        el.layoutSaveForm.addEventListener("submit", saveLayout);
        if (el.btnPlaylistAdd) {
            el.btnPlaylistAdd.addEventListener("click", function () {
                if (!el.playlistLibrary || !el.playlistLibrary.value) return;
                addPlaylistAsset(el.playlistLibrary.value);
            });
        }
        if (el.playlistLibrary) {
            el.playlistLibrary.addEventListener("change", function () {
                if (el.btnPlaylistAdd) el.btnPlaylistAdd.disabled = !el.playlistLibrary.value;
            });
        }
        if (el.btnPlaylistLibraryRefresh) {
            el.btnPlaylistLibraryRefresh.addEventListener("click", function () {
                loadLibrary(false);
            });
        }
        if (el.btnPlaylistRawAdd) {
            el.btnPlaylistRawAdd.addEventListener("click", function () {
                let value = el.playlistRawId ? el.playlistRawId.value.trim().toLowerCase() : "";
                if (/^[0-9a-f]{64}$/.test(value)) value = "sha256:" + value;
                if (!/^sha256:[0-9a-f]{64}$/.test(value)) {
                    setMsg(el.playlistMsg, "Enter a sha256 content id.", "err");
                    if (el.playlistRawId) el.playlistRawId.focus();
                    return;
                }
                const dwell = el.playlistRawDwell
                    ? clampDwell(el.playlistRawDwell.value) : 5000;
                if (el.playlistRawDwell) el.playlistRawDwell.value = String(dwell);
                addPlaylistAsset(value, dwell);
                if (el.playlistRawId) el.playlistRawId.value = "";
            });
        }
        if (el.playlistLoop) {
            el.playlistLoop.addEventListener("change", function () {
                state.playlist.loop = Boolean(el.playlistLoop.checked);
                markPlaylistDirty();
            });
        }
        if (el.btnPlaylistSave) el.btnPlaylistSave.addEventListener("click", savePlaylist);
        if (el.playlistUndo) {
            el.playlistUndo.addEventListener("click", undoPlaylistRemoval);
        }
        if (el.playbackPolicy) {
            el.playbackPolicy.addEventListener("change", renderPlayback);
        }
        if (el.playbackMore) {
            el.playbackMore.addEventListener("click", function () {
                const expanded = el.playbackMore.getAttribute("aria-expanded") === "true";
                el.playbackMore.setAttribute("aria-expanded", expanded ? "false" : "true");
                if (el.playbackCard) {
                    el.playbackCard.dataset.expanded = expanded ? "false" : "true";
                }
                el.playbackMore.textContent = expanded ? "More" : "Less";
            });
        }

        if (el.btnPlaybackStart) {
            el.btnPlaybackStart.addEventListener("click", function () {
                if (document.getElementById("experimental-opt-in").checked && window.confirm("Start experimental playback? This replaces the static image presentation. Tablet playback is not validated.")) playbackAction("start");
            });
        }
        if (el.btnTopbarStart) {
            el.btnTopbarStart.addEventListener("click", function () {
                if (el.btnPlaybackStart) el.btnPlaybackStart.click();
            });
        }
        if (el.btnPlaybackPause) {
            el.btnPlaybackPause.addEventListener("click", function () {
                playbackAction(actionFromPauseButton());
            });
        }
        if (el.btnTopbarPause) {
            el.btnTopbarPause.addEventListener("click", function () {
                if (el.btnPlaybackPause) el.btnPlaybackPause.click();
            });
        }
        if (el.btnPlaybackStop) {
            el.btnPlaybackStop.addEventListener("click", function () {
                playbackAction("stop");
            });
        }
        if (el.btnTopbarStop) {
            el.btnTopbarStop.addEventListener("click", function () {
                if (el.btnPlaybackStop) el.btnPlaybackStop.click();
            });
        }
        if (el.btnPlaybackRetry) {
            el.btnPlaybackRetry.addEventListener("click", function () {
                playbackAction("retry");
            });
        }
        if (el.btnPlaybackPrevious) {
            el.btnPlaybackPrevious.addEventListener("click", function () {
                playbackAction("previous");
            });
        }
        if (el.btnPlaybackNext) {
            el.btnPlaybackNext.addEventListener("click", function () {
                playbackAction("next");
            });
        }

        if (el.btnWallHealth) {
            el.btnWallHealth.addEventListener("click", function () {
                showTab("tablet", { focus: true, persist: true });
                if (el.rosterStatus) el.rosterStatus.scrollIntoView({ block: "nearest" });
            });
        }
        if (el.btnRosterRefresh) el.btnRosterRefresh.addEventListener("click", refreshRoster);
        if (el.btnDiagDownload) {
            el.btnDiagDownload.addEventListener("click", downloadDiagnostics);
        }
        if (el.btnDiagRefresh) {
            el.btnDiagRefresh.addEventListener("click", function () {
                loadDiagnostics(false);
            });
        }
        if (el.btnDiagVerify) {
            el.btnDiagVerify.addEventListener("click", function () {
                loadDiagnostics(true);
            });
        }

        if (el.btnCopySelectedId) {
            el.btnCopySelectedId.addEventListener("click", async function () {
                const id = el.btnCopySelectedId.dataset.deviceId || state.selectedId;
                const copied = await copyText(id);
                el.btnCopySelectedId.textContent = copied ? "Copied" : "Copy failed";
                announce(copied
                    ? "Copied the full tablet id."
                    : "Could not copy the tablet id.", copied ? "ok" : "err");
                window.setTimeout(function () {
                    if (el.btnCopySelectedId) el.btnCopySelectedId.textContent = "Copy full id";
                }, 1600);
            });
        }

        el.btnLayoutsRefresh.addEventListener("click", loadLayouts);
        el.layoutName.addEventListener("input", function () { clearMsg(el.layoutMsg); });

        document.addEventListener("keydown", onKeyDown);
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState !== "hidden") { refreshRoster(); if (document.getElementById("experimental-opt-in").checked) refreshPlayback(); }
        });
        window.addEventListener("online", function () {
            refreshRoster();
            if (document.getElementById("experimental-opt-in").checked) refreshPlayback();
        });
    }

    function startPlaybackPolling() {
        if (state.playbackTimer !== null) return;
        state.playbackTimer = window.setInterval(function () {
            if (document.visibilityState === "hidden") return;
            if (state.operatorConfig) {
                const signature = JSON.stringify(Object.keys(window.OperatorState.entries(state.operatorConfig.layout))
                    .map(id => [id, window.OperatorState.tabletState(state.operatorConfig, id, performance.now()).status]));
                if (signature !== state.evidenceSignature) { state.evidenceSignature = signature; renderAll(); }
            }
            if (state.playbackBusy || state.playbackFetching) return;
            if (document.getElementById("experimental-opt-in").checked) refreshPlayback();
        }, PLAYBACK_POLL_MS);
    }

    function init() {
        const labelFor = id => numberedLabel(id, latestProfile(id));
        operatorContent = window.OperatorContent.create({ state, api, ingestConfig, renderStage, announce, showConflict, isDirty });
        operatorGrid = window.OperatorGrid.create({ state, api, labelFor, validPair, profileFor, calibrationFor, ingestConfig, renderStage, syncDraftUi, isDirty, announce, showConflict });
        operatorDevices = window.OperatorDevices.create({ state, api, labelFor, profileFor, calibrationFor, ingestConfig, refreshRoster, showConflict, isDirty, announce });
        operatorReadiness = window.OperatorReadiness.create({ state, api, copyText });
        operatorSync = window.OperatorSync.create({ state, api, ingestConfig, renderAll, showConflict, isDirty: hasUnsavedEdits });
        document.getElementById("open-tablet-measurements").addEventListener("click", () => { showTab("system", { persist: true }); document.getElementById("measurement-details").open = true; document.getElementById("tablet-model").focus(); });
        state.onParticipation = (id, participating) => mutateDraft(draft => { draft.slots[id].participating = participating; });
        document.getElementById("open-wall-images").addEventListener("click", () => { showTab("show", { persist: true }); document.getElementById("image-select").focus(); });
        document.getElementById("experimental-opt-in").addEventListener("change", event => {
            document.getElementById("experimental-controls").hidden = !event.target.checked;
            if (event.target.checked) { loadLibrary(true); loadPlaylist(); refreshPlayback(); }
        });
        window.addEventListener("resize", () => { renderDeviceHealth(); renderStage(); });
        window.addEventListener("pagehide", () => { operatorSync.destroy(); operatorContent.destroy(); clearInterval(state.playbackTimer); });
        operatorReadiness.load();
        const storedTab = readStoredTab();
        if (storedTab) {
            showTab(storedTab, { persist: false });
            state.tabDecided = true;
        }
        bindEvents();
        loadRulerAddress();
        syncMeta();
        syncDraftUi();
        renderPlaylist();
        renderPlayback();
        renderDiagnostics();
        operatorSync.start();
        operatorContent.refresh();
        loadLayouts();
        loadDiagnostics(false);
        startPlaybackPolling();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
