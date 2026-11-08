"use strict";

(function () {
    const { setTextIfChanged, clearChildren, appendText } = window.OperatorDom;
    const API_LAYOUT = "/api/v3/layout";
    const API_LAYOUTS = "/api/v3/layouts";
    const API_PLAYLIST = "/api/v3/playlist";
    const API_PLAYBACK = "/api/v3/playback";
    const API_MEDIA = "/media";
    const API_DIAGNOSTICS = "/diagnostics";
    const PLAYBACK_POLL_MS = 1000;
    const DRAG_THRESHOLD_PX = 3;
    const HISTORY_LIMIT = 80;
    const MIN_DWELL_MS = 1000;
    const MAX_DWELL_MS = 600000;
    const TAB_STORAGE_KEY = "tablet-wall-console-tab-v1";
    const TAB_NAMES = ["tablet", "show", "content", "saved", "system"];
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
        btnApply: document.getElementById("btn-apply"),
        btnCancel: document.getElementById("btn-cancel"),
        btnReload: document.getElementById("btn-reload"),
        errorText: document.getElementById("error-text"),
        conflictPanel: document.getElementById("conflict-panel"),
        conflictText: document.getElementById("conflict-text"),
        btnConflictReload: document.getElementById("btn-conflict-reload"),
        stageSvg: document.getElementById("stage-svg"),
        stageScale: document.getElementById("stage-dimensions"),
        deviceCount: document.getElementById("device-count"),
        wallHealth: document.getElementById("wall-health"),
        btnWallHealth: document.getElementById("btn-wall-health"),
        rosterStatus: document.getElementById("roster-status"),
        btnRosterRefresh: document.getElementById("btn-roster-refresh"),
        deviceList: document.getElementById("device-list"),
        boundsX: document.getElementById("bounds-x"),
        boundsY: document.getElementById("bounds-y"),
        boundsWidth: document.getElementById("bounds-width"),
        boundsHeight: document.getElementById("bounds-height"),
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
        readiness: {},
        gridPreview: null,
        base: null,
        basePlacements: {},
        draft: null,
        rosterRefreshPromise: null,
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

    let confirmingModels = false, modelBatchReview = null, modelReviewVersion = 0;
    let operatorContent = null, operatorGrid = null, operatorDevices = null, operatorReadiness = null, workspace = null;
    const tabletForms = window.OperatorForms.create();
    const session = window.OperatorSession.create({ onConflict: showConflict, isDirty });
    const authorityFields = {
        operatorConfig: view => view.config,
        scene: view => view.config && view.config.scene,
        capabilities: view => view.config && view.config.capabilities || {},
        deviceLabels: view => view.config && view.config.device_labels || {},
        snapshots: view => view.config && view.config.snapshots || {},
        roster: view => view.roster,
        rosterError: view => view.rosterError,
        connectionText: view => view.transportText,
        connectionVersions: view => view.connectionVersions,
        rosterCheckedAt: view => view.rosterCheckedAt,
        etag: view => view.etag,
        etagState: view => state.draftConflict ? "stale" : view.etagState,
        revision: view => view.config && view.config.revision,
        generation: view => view.config && view.config.generation,
        layoutKind: view => view.config && view.config.layout.kind,
        configLoaded: view => !!view.config,
        displays: view => view.config && view.config.displays || [],
        calibrations: view => view.config && view.config.calibrations || [],
        tabletModels: view => view.config && view.config.tablet_models || {},
        tabletAssignments: view => view.config && view.config.tablet_assignments || {}
    };
    for (const [key, read] of Object.entries(authorityFields)) {
        delete state[key];
        Object.defineProperty(state, key, { get: () => read(session.view()) });
    }

    let compositionBusy = false;
    delete state.busy;
    Object.defineProperty(state, "busy", { get: () => compositionBusy || session.view().busy, set: value => { compositionBusy = value; } });

    const profileCache = new Map();
    const calibrationCache = new Map();
    const deviceRows = new Map();

    const ApiError = window.OperatorSession.ApiError;

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
        return isDirty() || tabletForms.dirty() || state.playlistDirty
            || !!operatorContent && operatorContent.dirty() || !!operatorGrid && operatorGrid.dirty();
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

    const layoutSignature = window.OperatorState.layoutSignature;

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

    function placementOrder(id) {
        const layout = state.base || state.draft;
        if (!layout) return null;
        const source = layout.kind === "logical" ? (layout.placements || {}) : (layout.slots || layout.placements || {});
        const items = Object.entries(source).map(function (entry) {
            return { id: entry[0], x: Number(entry[1] && (entry[1].x ?? entry[1].center_x_mm) || 0), y: Number(entry[1] && (entry[1].y ?? entry[1].center_y_mm) || 0), h: Number(entry[1] && (entry[1].h ?? entry[1].active_height_mm) || 0) };
        });
        const heights = items.map(function (item) { return item.h; }).filter(function (value) { return value > 0; }).sort(function (left, right) { return left - right; });
        const median = heights.length ? heights[Math.floor(heights.length / 2)] : 0;
        const tolerance = layout.kind === "physical" ? 50 : Math.max(1, median * 0.4);
        items.sort(function (left, right) {
            return Math.floor(left.y / tolerance) - Math.floor(right.y / tolerance) || left.x - right.x || left.id.localeCompare(right.id);
        });
        const index = items.findIndex(function (item) { return item.id === id; });
        return index === -1 ? null : index + 1;
    }

    function deviceLabel(id, profile) {
        const explicit = state.deviceLabels[id] || state.roster[id] && state.roster[id].label;
        if (explicit) return explicit;
        const number = deviceNumber(id);
        if (number) return "Tablet " + number;
        const screen = placementOrder(id);
        return screen ? "Screen " + screen : "Unplaced tablet";
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
        if (number !== null) return "#" + number;
        const screen = placementOrder(id);
        return screen ? "S" + screen : "—";
    }

    function numberedLabel(id, profile) {
        const label = deviceLabel(id, profile), number = deviceNumber(id);
        return label === "Tablet " + number ? label : label + (number ? " · Tablet " + number : "");
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
            { name: "content", tab: el.tabContent, panel: el.panelContent },
            { name: "show", tab: el.tabShow, panel: el.panelShow },
            { name: "tablet", tab: el.tabTablet, panel: el.panelTablet },
            { name: "saved", tab: document.getElementById("tab-saved"), panel: document.getElementById("panel-saved") },
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
        return workspace ? workspace.open(name, options) : commitTask(name, options);
    }

    function resolveOutput(reason, except) { return workspace ? workspace.resolve(reason, except) : Promise.resolve(true); }

    function commitTask(name, options) {
        const settings = options || {};
        const entries = tabEntries();
        const resolved = name;
        let target = null;
        entries.forEach(function (entry) {
            if (entry.name === resolved) target = entry;
        });
        if (!target || !target.tab || !target.panel) return false;

        const deviceSheet = document.getElementById("device-sheet");
        if (resolved !== "tablet" && deviceSheet.open && deviceSheet.dataset.modal === "true") {
            state.sheetTrigger = null;
            deviceSheet.close();
        }
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
            const selector = document.getElementById("compact-task-select");
            (selector.getClientRects().length ? selector : target.tab).focus({ preventScroll: true });
        }
        if (workspace) workspace.render();
        if (changed) renderStage();
        if (changed && name === "saved") { loadLayouts(); loadScenes(); }
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
        Promise.resolve(showTab(entries[next].name, { persist: true })).then(opened => { if (opened) entries[next].tab.focus(); });
    }

    function onCompactChange() {
        showTab(state.tabName || readStoredTab() || "content", { persist: false });
    }

    function maybeChooseInitialTab() {
        if (state.tabDecided) return;
        if (!state.configLoaded) return;
        state.tabDecided = true;
        const name = Object.keys(window.OperatorState.entries(state.base)).length ? "content" : "tablet";
        showTab(name, { persist: false });
    }

    function syncTabDots() {
        const dirtyTasks = {
            content: !!operatorContent && operatorContent.dirty(),
            tablet: tabletForms.dirty(undefined, "name"),
            show: isDirty() || !!operatorGrid && operatorGrid.dirty(),
            system: state.playlistDirty || tabletForms.dirty(undefined, "model") || tabletForms.dirty(undefined, "profile") || tabletForms.dirty(undefined, "calibration")
        };
        const entries = tabEntries();
        for (const { name, tab } of entries) {
            const dot = tab.querySelector(".tab-dot"), label = tab.textContent.trim();
            if (dot) dot.hidden = !dirtyTasks[name];
            tab.setAttribute("aria-label", label + (dirtyTasks[name] ? ", unsaved changes" : ""));
        }
        const selector = document.getElementById("compact-task-select"), drafts = [];
        for (const option of selector.options) {
            const tab = entries.find(entry => entry.name === option.value).tab;
            const name = tab.textContent.trim(), dirty = dirtyTasks[option.value];
            const text = name + (dirty ? " •" : "");
            if (option.textContent !== text) option.textContent = text;
            option.setAttribute("aria-label", tab.getAttribute("aria-label"));
            if (dirty) drafts.push(name);
        }
        selector.parentElement.dataset.dirty = String(!!drafts.length);
        selector.setAttribute("aria-label", "Wall task" + (drafts.length ? ". Unsaved changes in " + drafts.join(", ") + "." : ""));
        const note = document.getElementById("task-drafts");
        const text = drafts.length ? (drafts.length === 1 ? "Draft: " : "Drafts: ") + drafts.join(", ") : "";
        if (note.textContent !== text) note.textContent = text;
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
            + " Local edits are retained. Review the relevant comparison or rebuild the preview before applying. Reload asks before discarding wall edits.";
        el.conflictPanel.hidden = false;
        state.draftConflict = isDirty() || !!operatorGrid && operatorGrid.dirty() || !!operatorContent && operatorContent.dirty();
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

    function api(method, path, body, options) {
        return session.request(method, path, body, options);
    }

    function ingestConfig(config, options) {
        session.ingest(config, options || {});
        if (config.previous_layout_saved) { showReturnPoint(config); loadLayouts(); }
    }

    function observeSession(view, settings = {}) {
        if (!view.uncertain && document.activeElement === document.getElementById("refresh-command-status")) {
            const selector = document.getElementById("compact-task-select");
            const tab = document.querySelector('[role="tab"][aria-selected="true"]');
            const target = selector && selector.getClientRects().length ? selector : tab;
            if (target && target.getClientRects().length) target.focus({ preventScroll: true });
        }
        document.getElementById("command-uncertainty").hidden = !view.uncertain;
        if (!view.config) { renderAll(); return; }
        if (settings.runtime) { renderAll(); return; }
        const config = view.config, firstConfig = !state.base;
        const dirty = isDirty(), keepDraft = settings.preserveDraft && dirty;
        const conflict = keepDraft && settings.remote && state.draftBaseEtag !== config.etag;
        if (!keepDraft) {
            state.base = window.OperatorState.layoutDraft(config.layout);
            state.basePlacements = clone(config.layout.placements || {});
            state.draft = clone(state.base);
            state.draftBaseEtag = config.etag;
            state.draftConflict = false;
            state.undo = []; state.redo = [];
            state.gridPreview = null;
            if (!operatorContent.dirty()) state.viewLive = false;
        }
        if (conflict) state.draftConflict = true;
        state.displays.forEach(rememberProfile);
        state.calibrations.forEach(rememberCalibration);
        (config.referenced_displays || []).forEach(rememberProfile);
        (config.referenced_calibrations || []).forEach(rememberCalibration);
        if (!state.readinessFetchedAt) state.readiness = config.readiness || {};
        restorePlaybackExclusions();
        ensureSelection();
        if (conflict) showConflict("The wall changed. Your arrangement preview and its original guard are retained. Review the live wall, then rebuild or discard the preview.");
        else if (!state.draftConflict) hideConflict();
        renderAll(); maybeChooseInitialTab();
        if (firstConfig) announce(Object.keys(window.OperatorState.entries(state.base)).length ? "Controller connected to the server. Review current tablet reports."
            : Object.values(state.roster).some(device => device.online) ? "Controller connected to the server. Arrange connected tablets." : "Controller connected to the server. Add tablets to begin.");
    }

    function ensureSelection() {
        const ids = new Set(Object.keys(state.roster));
        Object.keys(window.OperatorState.entries(state.draft)).forEach(id => ids.add(id));
        if (state.selectedId && ids.has(state.selectedId)) return;
        state.selectedId = Array.from(ids).sort(compareDeviceIds)[0] || null;
    }

    async function loadConfig() {
        try {
            tabletForms.clear();
            state.formDeviceId = null;
            state.profileDirty = false; state.calDirty = false;
            if (operatorContent) operatorContent.discard();
            state.gridPreview = null;
            state.draftConflict = false;
            state.draft = state.base ? clone(state.base) : null;
            if (operatorGrid) operatorGrid.reset();
            await session.refresh();
            const config = session.view().config;
            if (!config) throw new Error("Configuration unavailable.");
            observeSession(session.view());
            clearError(); return true;
        } catch (error) { showError(error.message); return false; }
    }

    async function reloadConfigWithConfirm() {
        if (state.busy) return;
        const hasUnsaved = isDirty() || tabletForms.dirty() || operatorContent.dirty() || operatorGrid.dirty();
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
        if (operatorContent) operatorContent.render();
        renderDeviceList();
        renderStage();
        populateDeviceCard();
        renderPlayback();
        if (operatorGrid) operatorGrid.render();
        if (operatorDevices) operatorDevices.render();
        if (operatorReadiness) operatorReadiness.render();
        if (workspace) workspace.render();
        renderLogicalEditor();
        const colourSubject = document.getElementById("diagnostic-colour-subject");
        if (colourSubject) colourSubject.textContent = state.selectedId ? "Selected · " + numberedLabel(state.selectedId) : "Select a tablet in Tablets.";
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
            el.layoutKindNote.textContent = "Measured arrangement · millimetres. Model dimensions remain approximate.";
        } else if (state.layoutKind === "logical") {
            el.layoutKindNote.textContent = "Quick arrangement · relative screen shapes. Use Match real sizes for measured continuity.";
        } else {
            el.layoutKindNote.textContent = "No wall configuration is loaded.";
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

    function syncDraftUi() {
        syncGeometryControls();
        renderCalibrationHelper();
        if (!state.draft) {
            el.btnApply.disabled = true;
            el.btnCancel.disabled = true;
            el.btnUndo.disabled = el.btnUndo.hidden = true;
            el.btnRedo.disabled = el.btnRedo.hidden = true;
            el.boundsMode.disabled = true;
            el.boundsPadding.disabled = true;
            el.btnPackTablets.disabled = true;
            updateSavedButtons();
            syncInspector();
            syncTabDots();
            return;
        }

        const dirty = isDirty(), inputDirty = operatorGrid && operatorGrid.dirty();

        const emptyPhysical = state.draft.kind === "physical" && Object.keys(state.draft.slots).length === 0;
        el.btnApply.disabled = state.busy || !state.etag || state.etagState !== "current" || !!sizingError()
            || !dirty || (emptyPhysical && !state.gridPreview);
        el.btnApply.title = emptyPhysical ? "This arrangement has no tablets. Use an explicit Remove action to clear a slot." : "Apply the entire previewed layout once";
        el.btnCancel.disabled = state.busy || !dirty && !inputDirty;
        el.btnUndo.disabled = el.btnUndo.hidden = state.busy || state.undo.length === 0;
        el.btnRedo.disabled = el.btnRedo.hidden = state.busy || state.redo.length === 0;
        el.btnReload.disabled = state.busy;
        el.btnProfileSave.disabled = state.busy;
        el.btnCalibrationSave.disabled = state.busy || rulerSaveBlocked();
        el.btnLayoutSave.disabled = state.busy || !state.etag;
        el.btnLayoutsRefresh.disabled = state.busy;
        el.btnConflictReload.disabled = state.busy;

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
        if (state.draft && !(state.drag && state.drag.moved)) window.OperatorState.fitLogical(state.draft);
        syncDraftUi();
        renderStage();
        renderLogicalEditor();
        if (operatorGrid) operatorGrid.render();
        if (workspace) workspace.render();
        renderPlaybackPreflight(playbackPreflight());
    }

    function canManualEdit() {
        if (operatorGrid && operatorGrid.dirty()) { showError("Finish or discard the grid proposal before adjusting individual positions."); return false; }
        if (operatorContent && operatorContent.dirty()) { showError("Show or discard the image preview before adjusting the arrangement."); return false; }
        return true;
    }

    function beginManual() {
        if (operatorGrid) operatorGrid.freezeSelection();
        if (!isDirty()) state.draftBaseEtag = state.etag;
        state.viewLive = false;
    }

    function mutateDraft(mutator) {
        if (!state.draft || state.gridPreview || state.busy || !canManualEdit()) return false;
        beginManual();
        const before = clone(state.draft);
        mutator(state.draft);
        if (layoutSignature(before) === layoutSignature(state.draft)) return false;
        pushUndo(before);
        afterDraftChange();
        return true;
    }

    function undoDraft() {
        if (state.busy || state.drag || state.undo.length === 0 || !canManualEdit()) return;
        const current = clone(state.draft);
        state.draft = state.undo.pop();
        state.redo.push(current);
        afterDraftChange();
        announce("Undid the last layout change.");
    }

    function redoDraft() {
        if (state.busy || state.drag || state.redo.length === 0 || !canManualEdit()) return;
        const current = clone(state.draft);
        state.draft = state.redo.pop();
        state.undo.push(current);
        afterDraftChange();
        announce("Redid the layout change.");
    }

    function cancelDraft() {
        if (state.busy) return;
        const restoreFocus = document.activeElement === el.btnCancel;
        observeSession(session.view());
        if (operatorGrid) operatorGrid.cancel();
        if (restoreFocus) document.getElementById("grid-preview").focus({ preventScroll: true });
        announce("Arrangement discarded. The live wall is unchanged.");
    }

    async function applyLayout() {
        if (!state.draft || !state.etag || state.busy || state.etagState !== "current") return;
        if (state.gridPreview && operatorGrid) { await operatorGrid.apply(); return; }
        if (state.draft.kind === "physical" && Object.keys(state.draft.slots).length === 0) {
            showError("An empty measured draft cannot be applied. Use a deliberate Remove action to clear an active slot."); return;
        }
        clearError();
        setBusy(true);
        try {
            const body = state.draft.kind === "physical" ? {
                bounds: clone(state.draft.bounds), slots: clone(state.draft.slots), sizing: clone(state.draft.sizing)
            } : { width: state.draft.width, height: state.draft.height,
                placements: clone(state.draft.placements), sizing: clone(state.draft.sizing) };
            const payload = await api("PUT", state.draft.kind === "physical" ? API_LAYOUT : "/api/v3/logical-layout", body, { ifMatch: state.draftBaseEtag });
            ingestConfig(payload, { resetHistory: true });
            showReturnPoint(payload);
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
     * Profile and calibration
     * ---------------------------------------------------------------- */

    const {
        requireNonNegative, requireInteger, profileFieldValues, fillViewport, calibrationFieldValues, rulerSaveBlocked, invalidateRuler, checkRuler, decideRuler, renderCalibrationHelper, loadRulerAddress, rememberFields, populateDeviceCard, saveProfile, saveCalibration
    } = window.OperatorMeasurements.create({
        elements: {
            btnCalibrationSave: el.btnCalibrationSave, calAnchorEdge: el.calAnchorEdge, calDpr: el.calDpr, calMethod: el.calMethod,
            calMmCssX: el.calMmCssX, calMmCssY: el.calMmCssY, calMode: el.calMode, calOffsetX: el.calOffsetX,
            calOffsetY: el.calOffsetY, calOrientation: el.calOrientation, calProfileRevision: el.calProfileRevision, calQuarterTurn: el.calQuarterTurn,
            calUncertainty: el.calUncertainty, calViewportHeight: el.calViewportHeight, calViewportWidth: el.calViewportWidth, calibrationCurrent: el.calibrationCurrent,
            calibrationForm: el.calibrationForm, calibrationMsg: el.calibrationMsg, deviceCardBody: el.deviceCardBody, deviceCardCal: el.deviceCardCal,
            deviceCardEmpty: el.deviceCardEmpty, deviceCardName: el.deviceCardName, profileActiveHeight: el.profileActiveHeight, profileActiveWidth: el.profileActiveWidth,
            profileBezelBottom: el.profileBezelBottom, profileBezelLeft: el.profileBezelLeft, profileBezelRight: el.profileBezelRight, profileBezelTop: el.profileBezelTop,
            profileCurrent: el.profileCurrent, profileForm: el.profileForm, profileLabel: el.profileLabel, profileMsg: el.profileMsg,
            profilePixelHeight: el.profilePixelHeight, profilePixelWidth: el.profilePixelWidth, profileProvenance: el.profileProvenance
        },
        physicalCalibration: window.PhysicalCalibration, refresh: () => session.refresh(),
        state, num, markInvalid, ValidationError, deviceLabel, formatNumber, setInputValue, setSelectValue, api, syncTabDots, setMsg, errorDetail, profileFor, latestProfile, latestCalibration, numberedLabel, calibrationStatus, bodyMetrics, tabletForms, clearMsg, clearError, announce, resolveOutput, setBusy, handleWriteError
    });

    /* ---------------------------------------------------------------- *
     * Stage
     * ---------------------------------------------------------------- */

    const {
        addSelectedDevice, deleteSelectedSlot, endDrag, geometryHelp, matchScreenShape, matchStatus, nudgeSelected, onPointerCancel, onPointerDown, onPointerMove, onPointerUp, renderDeviceHealth, renderDeviceList, renderStage: drawStage, rotateSelected, selectDevice, setViewZoom, syncInspector, viewZoom
    } = window.PhysicalStage.create({
        selectionChanged: () => {
            if (operatorDevices) operatorDevices.render(); renderLogicalEditor();
            if (state.tabName === "show") document.getElementById("arrange-custom").open = true;
        },
        DRAG_THRESHOLD_PX, afterDraftChange, announce, bodyMetrics, calibrationFor, beginManual, canManualEdit, clearMsg, clone, deviceEntries, deviceLabel, deviceNumber, deviceRows, el, finiteOr, formatNumber, isOnline, latestProfile, mutateDraft, numberTag, numberedLabel, populateDeviceCard, profileFor, pushUndo, roundTo, selectedSlot, setInputValue, showError, showTab, state, syncTabDots, validPair
    });

    const geometryReady = typeof setViewZoom === "function" && typeof viewZoom === "function"
        && typeof matchStatus === "function" && typeof matchScreenShape === "function" && typeof geometryHelp === "function";

    function syncGeometryControls() {
        const zoom = geometryReady && typeof viewZoom === "function" ? viewZoom() : "fit";
        for (const [id, value] of [["view-zoom-fit", "fit"], ["view-zoom-2x", "2x"]]) {
            const button = document.getElementById(id);
            if (!button) continue;
            button.disabled = !geometryReady;
            button.setAttribute("aria-pressed", String(value === zoom));
            if (!geometryReady) button.title = "Available with the reviewed geometry update.";
        }
        const snap = document.getElementById("logical-snap-enabled"), snapNote = document.getElementById("logical-snap-note");
        if (snap) {
            snap.disabled = !geometryReady;
            snap.title = geometryReady
                ? "Uncheck to disable grid and edge snapping for relative drags."
                : "Available with the reviewed geometry update.";
            if (snapNote) snapNote.textContent = geometryReady
                ? "Mouse and pen: hold Alt to pause snapping. Touch uses this checkbox."
                : "Edge snapping controls are available with the reviewed geometry update.";
        }
        const match = document.getElementById("btn-match-shape"), matchNote = document.getElementById("match-shape-note");
        if (match) {
            if (!geometryReady) {
                match.disabled = true;
                match.title = "Available with the reviewed geometry update.";
                if (matchNote) matchNote.textContent = "Match screen shape is available with the reviewed geometry update.";
            } else {
                let status;
                try { status = matchStatus(); }
                catch (error) { status = { available: false, reason: "Match screen shape is unavailable until the wall loads." }; }
                match.disabled = !status.available;
                match.title = status.reason || "Match the selected relative slot to its current online viewport shape.";
                if (matchNote) matchNote.textContent = status.available
                    ? "Uses the selected tablet's current online viewport shape. It changes height and vertical centre only; the draft stays unapplied."
                    : status.reason;
            }
        }
        const help = document.getElementById("geometry-help-text");
        if (help) {
            let text = "Geometry help is available with the reviewed geometry update.";
            if (geometryReady) {
                try { text = geometryHelp(); }
                catch (error) { text = "Geometry help is unavailable until the wall loads."; }
            }
            if (help.textContent !== text) help.textContent = text;
        }
    }

    document.getElementById("btn-match-shape").addEventListener("click", () => {
        if (!geometryReady) return;
        matchScreenShape();
        syncGeometryControls();
    });
    document.getElementById("view-zoom-fit").addEventListener("click", () => {
        if (geometryReady) setViewZoom("fit");
        syncGeometryControls();
    });
    document.getElementById("view-zoom-2x").addEventListener("click", () => {
        if (geometryReady) setViewZoom("2x");
        syncGeometryControls();
    });
    document.getElementById("logical-snap-enabled").addEventListener("change", event => {
        if (!geometryReady) { event.target.checked = true; return; }
        announce(event.target.checked ? "Relative drag snapping is on." : "Relative drag snapping is off.");
    });

    const logicalFields = new Map();
    function renderLogicalEditor() {
        const box = document.getElementById("logical-editor"), draft = state.draft;
        if (!box) return;
        box.hidden = !draft || draft.kind !== "logical";
        if (box.hidden) return;
        const placement = draft.placements[state.selectedId];
        for (const [field, input] of logicalFields) {
            const value = placement && (field.startsWith("bezel-") ? placement.bezel[field.slice(6)] : placement[field]);
            input.disabled = !placement || !!state.gridPreview;
            if (document.activeElement !== input) {
                input.value = value === undefined ? "" : value;
                input.dataset.deviceId = state.selectedId || "";
                markInvalid(input, false);
            }
        }
        for (const [id, value] of [["logical-width", draft.width], ["logical-height", draft.height],
            ["logical-padding", draft.sizing.padding], ["logical-mode", draft.sizing.mode]]) {
            const input = document.getElementById(id);
            if (document.activeElement !== input) input.value = value;
        }
        for (const id of ["logical-width", "logical-height"]) document.getElementById(id).readOnly = draft.sizing.mode === "tablets";
        document.getElementById("logical-message").textContent = placement ? "Editing " + numberedLabel(state.selectedId) + ". Apply arrangement writes all reviewed geometry once." : "Select a placed tablet to edit its position and size.";
    }

    function bindLogicalEditor() {
        const fields = document.getElementById("logical-fields");
        for (const [field, name] of [["x", "X"], ["y", "Y"], ["w", "Width"], ["h", "Height"],
            ["bezel-top", "Top bezel"], ["bezel-right", "Right bezel"], ["bezel-bottom", "Bottom bezel"], ["bezel-left", "Left bezel"]]) {
            const label = document.createElement("label"); label.className = "field";
            label.textContent = name + " (relative units)";
            const input = document.createElement("input"); input.className = "inp"; input.type = "number"; input.step = "1";
            input.id = "logical-" + field; input.dataset.field = field; label.htmlFor = input.id;
            label.append(input); fields.append(label); logicalFields.set(field, input);
            input.addEventListener("blur", renderLogicalEditor);
            input.addEventListener("change", () => {
                const id = input.dataset.deviceId, value = Number(input.value);
                if (!input.value || !Number.isInteger(value) || ((field === "w" || field === "h") ? value < 1 : field.startsWith("bezel-") && value < 0)) { markInvalid(input, true); return; }
                markInvalid(input, false);
                mutateDraft(draft => {
                    const p = draft.placements[id];
                    if (!p) return;
                    if (field.startsWith("bezel-")) p.bezel[field.slice(6)] = value; else p[field] = value;
                });
            });
        }
        for (const [id, field] of [["logical-width", "width"], ["logical-height", "height"], ["logical-padding", "padding"], ["logical-mode", "mode"]]) {
            document.getElementById(id).addEventListener("change", event => {
                const value = field === "mode" ? event.target.value : Number(event.target.value);
                if (field !== "mode" && (!Number.isInteger(value) || value < (field === "padding" ? 0 : 1))) { markInvalid(event.target, true); return; }
                markInvalid(event.target, false);
                mutateDraft(draft => { if (["mode", "padding"].includes(field)) draft.sizing[field] = value; else draft[field] = value; });
            });
        }
        document.getElementById("logical-rotate").addEventListener("click", rotateSelected);
        for (const id of ["tile", "pack"]) document.getElementById("logical-" + id).addEventListener("click", () => {
            try {
                const draft = clone(state.draft), scope = document.getElementById("logical-tile-scope").value;
                const ids = scope === "placed" ? Object.keys(draft.placements)
                    : Object.keys(state.roster).filter(key => scope === "all" || state.roster[key].online);
                const order = [...document.querySelectorAll("#grid-order [data-device-id]")].map(row => row.dataset.deviceId);
                ids.sort(document.getElementById("logical-tile-order").value === "id" ? (a, b) => a.localeCompare(b)
                    : (a, b) => (order.includes(a) ? order.indexOf(a) : Infinity) - (order.includes(b) ? order.indexOf(b) : Infinity) || compareDeviceIds(a, b));
                const aspects = {};
                for (const key of ids) {
                    const viewport = state.roster[key]?.viewport;
                    if (viewport?.width > 0 && viewport.height > 0) aspects[key] = viewport.width / viewport.height;
                    draft.placements[key] ||= { x: 0, y: 0, w: Math.max(1, Math.round(100 * (aspects[key] || 1))), h: 100,
                        bezel: { top: 0, right: 0, bottom: 0, left: 0 } };
                }
                const arranged = window.OperatorState.arrangeLogical(draft, ids, { columns: Number(document.getElementById("logical-tile-columns").value),
                    rows: Number(document.getElementById("logical-tile-rows").value), gap: Number(document.getElementById("logical-tile-gap").value), tile: id === "tile", aspects,
                    preserveAspect: document.getElementById("logical-tile-shape").value !== "fill" });
                mutateDraft(next => Object.assign(next, arranged));
            } catch (error) { document.getElementById("logical-message").textContent = error.message; }
        });
    }

    function syncStageSummary(view) {
        const node = document.getElementById("stage-wall-summary");
        if (!node) return;
        if (!view || !view.layout) { node.textContent = "Waiting for the wall."; return; }
        const bounds = window.OperatorState.bounds(view.layout);
        const placed = Object.keys(window.OperatorState.entries(view.layout)).length;
        node.textContent = formatNumber(bounds.width, 1) + " × " + formatNumber(bounds.height, 1)
            + (view.layout.kind === "physical" ? " mm" : " wall units")
            + " · " + placed + (placed === 1 ? " tablet" : " tablets");
    }

    function renderStage() {
        const view = window.OperatorState.stageView(state);
        syncTabDots();
        syncStageSummary(view);
        if (workspace) workspace.render(view);
        drawStage(view);
        syncGeometryControls();
    }

    function bindNumberInput(input, write, validate) {
        let before = null;

        input.addEventListener("focus", function () {
            before = state.draft ? clone(state.draft) : null;
        });

        input.addEventListener("input", function () {
            if (!canManualEdit()) return;
            const value = num(input.value);
            const valid = value !== null && (!validate || validate(value));
            markInvalid(input, !valid);
            if (!valid) return;
            beginManual();
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
        let subject = null;
        input.addEventListener("focus", () => { subject = state.selectedId; });
        bindNumberInput(input, function (value) {
            const slot = state.draft && state.draft.slots[subject];
            if (!slot || slot[field] === value) return false;
            slot[field] = value;
            return true;
        });
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
        else if (state.diagnosticsState === "ready") { text = "current"; kind = "ok"; }
        else if (state.diagnosticsState === "error") { text = "error"; kind = "err"; }
        else if (state.diagnosticsState === "forbidden") { text = "unavailable"; kind = "warn"; }
        setTextIfChanged(el.diagState, text);
        el.diagState.dataset.kind = kind;
        el.diagState.hidden = false;
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
        const reading = state.diagnosticsState === "pending" || state.diagnosticsState === "loading"
            || state.diagnosticsState === "refreshing";
        if (!data) {
            facts.push(["Status", reading ? "Reading diagnostics…" : "No diagnostics loaded."]);
        } else {
            const media = data.media && typeof data.media === "object" ? data.media : {};
            const db = data.db && typeof data.db === "object" ? data.db : {};
            const backup = data.backup && typeof data.backup === "object" ? data.backup : {};
            const clients = data.clients && typeof data.clients === "object" ? data.clients : {};
            facts.push(["Report", (state.diagnosticsState === "ready" ? "Current" : "Last known")
                + " · " + new Date(state.diagnosticsCapturedAt).toLocaleString()]);
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
        const lastKnown = document.getElementById("diag-last-known");
        if (lastKnown) {
            const stale = !!data && state.diagnosticsState !== "ready";
            lastKnown.hidden = !stale;
            lastKnown.textContent = stale
                ? (reading ? "Showing the last known diagnostics report while this refresh runs."
                    : "Showing the last known diagnostics report. This read did not complete, so it is not current evidence for the wall.")
                : "";
            lastKnown.dataset.kind = reading ? "info" : "err";
        }
        const evidence = document.getElementById("settings-evidence");
        if (evidence) evidence.dataset.state = state.diagnosticsState;
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
        try { await session.refresh(); }
        finally { state.rosterRefreshPromise = null; renderAll(); }
    }

    /* ---------------------------------------------------------------- *
     * Saved layouts
     * ---------------------------------------------------------------- */

    let layoutsVersion = 0, scenesVersion = 0, savedScenes = [], returnPoint = null;
    let layoutsLoaded = false, scenesLoaded = false;
    function snapshotMatches(entry, kind) {
        const item = (state.snapshots[kind] || []).find(row => row.name === entry.name);
        return !!item && !!entry.etag && item.etag === entry.etag;
    }

    async function loadLayouts() {
        const version = ++layoutsVersion;
        const status = document.getElementById("layouts-status");
        setMsg(status, layoutsLoaded ? "Refreshing saved arrangements…" : "Reading saved arrangements…", "info");
        if (el.btnLayoutsRefresh) el.btnLayoutsRefresh.disabled = true;
        try {
            const results = await Promise.all([api("GET", API_LAYOUTS, undefined, { fenced: "durable" }), api("GET", "/api/v3/logical-layouts", undefined, { fenced: "durable" })]);
            if (version !== layoutsVersion) return;
            const byName = new Map();
            (results[0].layouts || []).forEach(entry => byName.set(entry.name, { ...entry, logical: false }));
            (results[1].layouts || []).forEach(entry => byName.set(entry.name, { ...entry, logical: true }));
            state.savedLayouts = [...byName.values()].sort((a, b) => a.name.localeCompare(b.name));
            layoutsLoaded = true;
            renderSavedLayouts(); clearMsg(status);
            if (operatorDevices) operatorDevices.render();
        } catch (error) {
            if (version !== layoutsVersion) return;
            renderSavedLayouts();
            setMsg(status, (layoutsLoaded ? "Showing last known saved arrangements. " : "Saved arrangements could not be read. ")
                + error.message + " Use Refresh saved to retry.", "err");
        } finally {
            if (version === layoutsVersion && el.btnLayoutsRefresh) el.btnLayoutsRefresh.disabled = state.busy;
        }
    }

    const restorePointName = name => /^Before (physical|logical) [a-f0-9]{12}$/.test(name);

    function savedTag(text, kind) {
        const tag = document.createElement("span"); tag.className = "saved-tag"; tag.textContent = text;
        if (kind) tag.dataset.kind = kind;
        return tag;
    }

    function renderSavedLayouts() {
        const focused = document.activeElement;
        const focusName = focused && focused.closest("[data-snapshot-name]")?.dataset.snapshotName;
        el.savedLayouts.replaceChildren();
        for (const entry of state.savedLayouts) {
            const layout = entry.layout || {}, count = Object.keys(window.OperatorState.entries(layout)).length;
            const automatic = restorePointName(entry.name);
            const row = document.createElement("li"); row.className = "saved-row saved-row-layout"; row.dataset.snapshotName = entry.name;
            row.dataset.kind = entry.logical ? "logical" : "physical";
            if (automatic) row.dataset.automatic = "true";
            const info = document.createElement("span"); info.className = "saved-info";
            const name = document.createElement("strong"); name.className = "saved-name"; name.textContent = entry.name;
            const tags = document.createElement("span"); tags.className = "saved-tags";
            tags.append(savedTag(entry.logical ? "Relative geometry" : "Measured geometry", "kind"));
            if (automatic) tags.append(savedTag("Automatic restore point", "auto"));
            const meta = document.createElement("span"); meta.className = "saved-meta";
            meta.textContent = entry.valid === false ? "Damaged saved data · replace or delete"
                : count + (count === 1 ? " tablet" : " tablets") + " · Recall restores geometry only";
            info.append(name, tags, meta);
            if (entry.valid !== false) {
                const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
                svg.classList.add("saved-thumb"); svg.setAttribute("aria-hidden", "true");
                const bounds = window.OperatorState.bounds(layout);
                svg.setAttribute("viewBox", [bounds.x, bounds.y, bounds.width, bounds.height].join(" "));
                for (const panel of window.OperatorStage.panels(layout, profileFor)) {
                    if (panel.missing) continue;
                    const rect = document.createElementNS(svg.namespaceURI, "rect");
                    for (const [key, value] of Object.entries(panel.body)) rect.setAttribute(key, value);
                    rect.setAttribute("fill", "var(--selected)"); rect.setAttribute("stroke", "var(--accent)");
                    rect.setAttribute("stroke-width", "2"); rect.setAttribute("vector-effect", "non-scaling-stroke");
                    if (panel.angle) rect.setAttribute("transform", "rotate(" + panel.angle + " " + panel.cx + " " + panel.cy + ")");
                    svg.append(rect);
                }
                row.append(svg);
                const subjects = document.createElement("span"); subjects.className = "saved-meta";
                subjects.textContent = Object.entries(window.OperatorState.entries(layout)).map(([id, slot]) => numberedLabel(id)
                    + (layout.kind === "physical" ? " (profile r" + slot.profile_revision + ", calibration r" + slot.calibration_revision + ")" : "")).join(", ");
                const details = document.createElement("details"); details.className = "saved-details";
                const summary = document.createElement("summary"); summary.textContent = "Tablet details";
                summary.setAttribute("aria-label", "Tablet details for arrangement “" + entry.name + "”");
                if (subjects.textContent) { details.append(summary, subjects); info.append(details); }
            }
            row.append(info);
            const actions = document.createElement("span"); actions.className = "saved-actions";
            for (const [verb, handler] of [["Recall geometry", () => recallLayout(entry)], ["Delete", () => deleteLayout(entry)]]) {
                const button = document.createElement("button"); button.type = "button"; button.className = "btn btn-sm";
                if (verb === "Delete") button.classList.add("btn-danger");
                button.textContent = verb; button.setAttribute("aria-label", verb + " for arrangement “" + entry.name + "”");
                button.dataset.invalid = String(verb === "Recall geometry" && entry.valid === false);
                button.disabled = state.busy || !state.etag || state.etagState !== "current" || button.dataset.invalid === "true";
                button.addEventListener("click", handler); actions.append(button);
            }
            row.append(actions); el.savedLayouts.append(row);
        }
        el.savedEmpty.hidden = !layoutsLoaded || state.savedLayouts.length > 0;
        const countNode = document.getElementById("layouts-count");
        if (countNode) {
            countNode.textContent = state.savedLayouts.length + (state.savedLayouts.length === 1 ? " arrangement" : " arrangements");
            countNode.hidden = !layoutsLoaded;
        }
        if (focusName && document.activeElement === document.body) {
            const row = Array.from(el.savedLayouts.children).find(item => item.dataset.snapshotName === focusName);
            (row?.querySelector("button:not(:disabled)") || el.layoutName).focus({ preventScroll: true });
        }
    }

    function updateSavedButtons() {
        for (const button of el.savedLayouts.querySelectorAll("button")) button.disabled = state.busy || !state.etag || state.etagState !== "current" || button.dataset.invalid === "true";
    }

    function showReturnPoint(result) {
        if (!result.previous_layout_saved) return;
        returnPoint = { name: result.previous_layout_saved };
        document.getElementById("return-point").hidden = false;
        document.getElementById("return-point-name").textContent = result.previous_layout_saved + ". This actual arrangement keeps the previous geometry. Its image is excluded.";
    }

    async function saveLayout(event) {
        event.preventDefault();
        const name = el.layoutName.value.trim();
        if (!name) { setMsg(el.layoutMsg, "Enter an arrangement name.", "err"); el.layoutName.focus(); return; }
        if (state.busy || !await resolveOutput("Save the applied arrangement")) return;
        const existing = state.savedLayouts.find(item => item.name === name);
        if (existing && !window.confirm("Overwrite saved arrangement “" + name + "” with the applied geometry? The image is excluded.")) return;
        const guard = state.etag, kind = state.layoutKind;
        setBusy(true);
        try {
            const result = await api("PUT", (kind === "logical" ? "/api/v3/logical-layouts" : API_LAYOUTS) + "/" + encodeURIComponent(name) + (existing ? "?replace=true" : ""), undefined, { ifMatch: guard });
            ingestConfig(result, { preserveDraft: true });
            setMsg(el.layoutMsg, "Arrangement “" + result.name + "” saved.", "ok");
            await loadLayouts();
        } catch (error) { handleWriteError(error, el.layoutMsg); }
        finally { setBusy(false); }
    }

    async function recallLayout(entry) {
        if (state.busy || !await resolveOutput("Recall arrangement “" + entry.name + "”")) return;
        if (!snapshotMatches(entry, "layouts")) { setMsg(el.layoutMsg, "This saved arrangement changed. Refresh Saved and review it again.", "err"); return; }
        const oldKind = state.layoutKind, targetKind = entry.logical ? "logical" : "physical", guard = state.etag;
        if (oldKind !== targetKind && !window.confirm("Recall “" + entry.name + "” and change the sizing representation? The server creates a real named return point for the current arrangement. The image stays unchanged.")) return;
        setBusy(true);
        try {
            const result = await api("POST", (entry.logical ? "/api/v3/logical-layouts" : API_LAYOUTS) + "/" + encodeURIComponent(entry.name) + "/recall", undefined, { ifMatch: guard });
            ingestConfig(result); showReturnPoint(result);
            setMsg(el.layoutMsg, "Arrangement “" + entry.name + "” recalled. Waiting for current tablet reports. Image unchanged.", "ok");
            await loadLayouts();
        } catch (error) { handleWriteError(error, el.layoutMsg); }
        finally { setBusy(false); }
    }

    async function deleteLayout(entry) {
        if (state.busy || !await resolveOutput("Delete a saved arrangement")) return;
        if (!snapshotMatches(entry, "layouts")) { setMsg(el.layoutMsg, "This saved arrangement changed. Refresh Saved before deleting it.", "err"); return; }
        if (!window.confirm("Delete saved arrangement “" + entry.name + "”? Applied geometry and content stay unchanged.")) return;
        setBusy(true);
        try {
            const result = await api("DELETE", (entry.logical ? "/api/v3/logical-layouts" : API_LAYOUTS) + "/" + encodeURIComponent(entry.name), undefined, { etag: true });
            ingestConfig(result, { preserveDraft: true });
            await loadLayouts(); setMsg(el.layoutMsg, "Saved arrangement deleted.", "ok");
            el.layoutName.focus({ preventScroll: true });
        } catch (error) { handleWriteError(error, el.layoutMsg); }
        finally { setBusy(false); }
    }

    function sceneMeta(content) {
        if (content.type !== "image") {
            return content.type === "calibration" ? "Calibration pattern · preview only" : "Colour test · preview only";
        }
        return "Image · " + (content.fit === "contain" ? "Show whole image" : "Fill wall") + " · preview only";
    }

    function renderSavedScenes() {
        const focused = document.activeElement;
        const focusName = focused && focused.closest("[data-snapshot-name]")?.dataset.snapshotName;
        const list = document.getElementById("saved-scenes"); list.replaceChildren();
        for (const entry of savedScenes) {
            const row = document.createElement("li"); row.className = "saved-row saved-row-content"; row.dataset.snapshotName = entry.name; row.dataset.kind = "scene";
            const label = document.createElement("span"); label.className = "saved-info";
            const name = document.createElement("strong"); name.className = "saved-name"; name.textContent = entry.name;
            const tags = document.createElement("span"); tags.className = "saved-tags";
            tags.append(savedTag("Content", "kind"));
            const meta = document.createElement("span"); meta.className = "saved-meta";
            meta.textContent = entry.valid === false ? "Damaged saved data" : sceneMeta(entry.content);
            label.append(name, tags, meta);
            const image = entry.valid !== false && operatorContent.imageFor(entry.content.asset);
            if (image) {
                const thumbnail = document.createElement("img"); thumbnail.className = "saved-thumb"; thumbnail.alt = ""; thumbnail.src = image.thumbnail_url;
                thumbnail.addEventListener("error", () => { thumbnail.hidden = true; }); row.append(thumbnail);
                const source = document.createElement("span"); source.className = "saved-meta"; source.textContent = image.name; label.append(source);
            }
            row.append(label);
            const actions = document.createElement("span"); actions.className = "saved-actions";
            for (const verb of ["Preview content", "Delete"]) {
                const button = document.createElement("button"); button.type = "button"; button.className = "btn btn-sm";
                if (verb === "Delete") button.classList.add("btn-danger");
                button.textContent = verb; button.setAttribute("aria-label", verb + " for content “" + entry.name + "”");
                button.disabled = state.busy || verb === "Preview content" && entry.valid === false;
                button.addEventListener("click", async () => {
                    if (state.busy) return;
                    if (!await resolveOutput(verb + " saved content “" + entry.name + "”")) return;
                    if (!snapshotMatches(entry, "scenes")) { setMsg(document.getElementById("scene-message"), "The saved content changed. Refresh saved and review it again.", "err"); return; }
                    if (verb === "Preview content") {
                        operatorContent.previewScene(entry, state.etag); await showTab("content", { focus: true, persist: true });
                        return;
                    }
                    if (!window.confirm("Delete saved content “" + entry.name + "”? Applied content is unchanged.")) return;
                    try {
                        const result = await api("DELETE", "/api/v3/scenes/" + encodeURIComponent(entry.name), undefined, { etag: true });
                        ingestConfig(result, { preserveDraft: true }); await loadScenes();
                        setMsg(document.getElementById("scene-message"), "Saved content deleted.", "ok"); document.getElementById("scene-name").focus();
                    } catch (error) { setMsg(document.getElementById("scene-message"), error.message, "err"); }
                });
                actions.append(button);
            }
            row.append(actions);
            list.append(row);
        }
        const empty = document.getElementById("saved-scenes-empty");
        if (empty) empty.hidden = !scenesLoaded || savedScenes.length > 0;
        const countNode = document.getElementById("scenes-count");
        if (countNode) {
            countNode.textContent = savedScenes.length + (savedScenes.length === 1 ? " item" : " items");
            countNode.hidden = !scenesLoaded;
        }
        if (focusName && document.activeElement === document.body) {
            const row = Array.from(list.children).find(item => item.dataset.snapshotName === focusName);
            (row?.querySelector("button:not(:disabled)") || document.getElementById("scene-name")).focus({ preventScroll: true });
        }
    }

    async function loadScenes() {
        const version = ++scenesVersion;
        const status = document.getElementById("scenes-status");
        setMsg(status, scenesLoaded ? "Refreshing saved content…" : "Reading saved content…", "info");
        try {
            const result = await api("GET", "/api/v3/scenes", undefined, { fenced: "durable" });
            if (version !== scenesVersion) return;
            savedScenes = (result.scenes || []).slice().sort((a, b) => a.name.localeCompare(b.name));
            scenesLoaded = true;
            renderSavedScenes(); clearMsg(status);
        } catch (error) {
            if (version !== scenesVersion) return;
            renderSavedScenes();
            setMsg(status, (scenesLoaded ? "Showing last known saved content. " : "Saved content could not be read. ")
                + error.message + " Use Refresh saved to retry.", "err");
        }
    }

    function bindDiagnosticColours() {
        const message = document.getElementById("diagnostic-colour-message"), input = document.getElementById("diagnostic-colour");
        document.getElementById("diagnostic-colour-refresh").addEventListener("click", async () => {
            const id = state.selectedId;
            if (!id) { message.textContent = "Select a tablet first."; return; }
            try {
                const records = await api("GET", "/devices", undefined, { fenced: true });
                if (id !== state.selectedId) return;
                const colour = records[id]?.color;
                if (/^#[0-9a-f]{6}$/i.test(colour || "")) input.value = colour;
                message.textContent = "Diagnostic colour for " + numberedLabel(id) + " · " + (colour || "not reported") + ". Current image proof is unchanged.";
            } catch (error) { if (id === state.selectedId) message.textContent = "Diagnostic colour could not be read. " + error.message; }
        });
        for (const target of ["one", "all"]) document.getElementById("diagnostic-colour-" + target).addEventListener("click", async () => {
            const id = state.selectedId, colour = input.value;
            if (target === "one" && !id) { message.textContent = "Select a tablet first."; return; }
            if (!await resolveOutput("Set a diagnostic test colour")) return;
            try {
                const result = await api("POST", target === "all" ? "/devices/color" : "/devices/" + encodeURIComponent(id) + "/color", { color: colour });
                message.textContent = "Diagnostic colour set for " + (target === "all" ? "all currently registered tablets" : numberedLabel(id)) + ". "
                    + (result.delivered === false ? "Delivery waits for connection. " : "") + "This legacy test command has no revision guard. It does not show an image.";
                await session.refresh();
            } catch (error) { message.textContent = "Diagnostic colour command failed. " + error.message; }
        });
    }

    let measurementReview = null;
    function currentMeasurementFields(id, group, baseline) {
        if (group === "model") {
            const assignment = state.tabletAssignments[id] || {};
            return { "tablet-model": assignment.mode === "explicit" ? assignment.model_id : assignment.mode === "manual" ? "manual" : "" };
        }
        const record = group === "profile" ? latestProfile(id) : latestCalibration(id);
        return { ...baseline, ...(group === "profile" ? profileFieldValues(record, id) : calibrationFieldValues(record, latestProfile(id), id)), _revision: record?.revision || 0 };
    }

    function bindTabletSetup() {
        let arrangementReview = null;
        document.getElementById("btn-review-arrangement").addEventListener("click", async () => {
            if (!isDirty() || state.gridPreview || operatorGrid.dirty()) { announce("Use Rebuild preview for a grid proposal. Individual adjustments can be compared here."); return; }
            const signature = layoutSignature(state.draft);
            try {
                await session.refresh();
                if (signature !== layoutSignature(state.draft)) return;
                const current = session.view().config;
                arrangementReview = { signature, etag: current.etag, current: window.OperatorState.layoutDraft(current.layout) };
                const localIds = Object.keys(window.OperatorState.entries(state.draft)), liveIds = Object.keys(window.OperatorState.entries(current.layout));
                document.getElementById("manual-review-summary").textContent = "Your retained proposal has " + localIds.length + " tablet positions. The current wall has " + liveIds.length
                    + ". Positions removed by your proposal · " + (liveIds.filter(id => !localIds.includes(id)).map(numberedLabel).join(", ") || "none")
                    + ". Keeping your proposal adopts this reviewed guard only. Apply arrangement remains a separate command. Exact historical measurement pins remain in the proposal."
                    + (state.draft.kind !== current.layout.kind ? " Applying changes the sizing representation and requires a server-created return point." : "");
                document.getElementById("manual-review-details").textContent = "Current geometry\n" + JSON.stringify(current.layout, null, 2) + "\nYour proposed geometry\n" + JSON.stringify(state.draft, null, 2);
                if (!await showTab("show", { persist: true })) return;
                document.getElementById("manual-arrangement-review").hidden = false;
                document.getElementById("manual-review-summary").focus();
            } catch (error) { handleWriteError(error); }
        });
        document.getElementById("manual-review-keep").addEventListener("click", () => {
            const review = arrangementReview;
            if (!review || review.etag !== state.etag || review.signature !== layoutSignature(state.draft)) { announce("The wall or proposal changed after comparison. Compare again before keeping this arrangement.", "err"); return; }
            state.base = review.current; state.basePlacements = clone(review.current.placements || {});
            state.draftBaseEtag = review.etag; state.draftConflict = false; state.viewLive = false;
            arrangementReview = null; document.getElementById("manual-arrangement-review").hidden = true;
            hideConflict(); afterDraftChange(); announce("Your arrangement is retained against the reviewed wall. Review the preview, then Apply arrangement.");
        });
        for (const group of ["profile", "calibration", "model"]) document.getElementById("review-" + group).addEventListener("click", async () => {
            const id = state.selectedId, submitted = tabletForms.get(id, group);
            if (!submitted) return;
            try {
                await session.refresh();
                if (id !== state.selectedId || submitted.version !== tabletForms.get(id, group).version) return;
                const remote = currentMeasurementFields(id, group, submitted.baseline);
                measurementReview = { id, group, version: submitted.version, remote, etag: state.etag };
                document.getElementById("measurement-comparison").textContent = "Current saved fields\n" + JSON.stringify(remote, null, 2)
                    + "\nYour retained fields\n" + JSON.stringify(submitted.values, null, 2);
                document.getElementById("measurement-review").hidden = false;
                document.getElementById("measurement-keep").focus();
            } catch (error) { handleWriteError(error); }
        });
        document.getElementById("measurement-keep").addEventListener("click", () => {
            const review = measurementReview;
            if (!review || review.id !== state.selectedId || review.etag !== state.etag || !tabletForms.review(review.id, review.group, review.version, review.remote, review.etag)) {
                announce("The tablet, fields or wall changed. Compare the current saved fields again.", "err"); return;
            }
            measurementReview = null; document.getElementById("measurement-review").hidden = true;
            populateDeviceCard(); announce("Your fields are retained against the reviewed saved values. Save is a separate command.");
        });
        for (const group of ["profile", "calibration", "model"]) document.getElementById("discard-" + group).addEventListener("click", () => {
            tabletForms.discard(state.selectedId, group);
            state.formDeviceId = null; populateDeviceCard(); syncTabDots();
        });
        document.getElementById("clear-wall").addEventListener("click", async () => {
            if (!await resolveOutput("Clear the active wall")) return;
            if (!window.confirm("Clear all active positions? Registrations, names, measurements and saved arrangements are retained. The selected image stays unchanged.")) return;
            try { const result = await api("POST", "/api/v3/layout/clear", { confirm: true }, { etag: true }); ingestConfig(result); announce("Active positions cleared. Tablets and saved arrangements are retained."); }
            catch (error) { handleWriteError(error); }
        });
        const newModelReview = () => { modelReviewVersion += 1; modelBatchReview = null; document.getElementById("group-hardware").checked = false; operatorGrid.render(); };
        document.getElementById("group-model").addEventListener("change", newModelReview);
        document.getElementById("group-new-review").addEventListener("click", newModelReview);
        document.getElementById("group-confirm").addEventListener("click", async () => {
            const prior = modelBatchReview;
            const ids = prior ? prior.ids.slice() : operatorGrid.selectedIds(), modelId = document.getElementById("group-model").value;
            const hardwareDeclared = document.getElementById("group-hardware").checked;
            const resultNode = document.getElementById("group-result"), button = document.getElementById("group-confirm");
            if (state.busy || confirmingModels || !ids.length || !modelId || !hardwareDeclared) { resultNode.textContent = "Select the actual tablets and model, then confirm that you checked their hardware."; return; }
            if (isDirty() && !await resolveOutput("Confirm hardware measurements")) return;
            const names = ids.map(numberedLabel), reviewedEtag = state.etag, reviewVersion = modelReviewVersion;
            if (!window.confirm("Confirm “" + state.tabletModels[modelId].label + "” for " + names.join(", ") + "? Dimensions and calibration remain approximate. Each tablet saves separately; a problem stops the remaining writes.")) return;
            operatorGrid.freezeSelection(); confirmingModels = true; button.disabled = true;
            try {
                const result = await window.OperatorDevices.confirmModels({ ids, modelId, hardwareDeclared, reviewedEtag, api, ingestConfig: () => {},
                    readAuthority: async () => { await session.refresh(); return session.view().config; },
                    currentEtag: () => session.view().etag,
                    progress: value => { resultNode.textContent = "Confirmed · " + value.completed.map(numberedLabel).join(", ") + ". Remaining · " + value.untouched.map(numberedLabel).join(", "); } });
                await session.refresh();
                if (!operatorGrid.modelSetupComplete(result.expectedEtag)) showConflict("A separate wall change arrived during model confirmation. Review and rebuild the retained arrangement inputs before previewing.");
                const completed = [...new Set([...(prior?.completed || []), ...result.completed])];
                if (reviewVersion === modelReviewVersion) {
                    modelBatchReview = result.failed ? { ids: [result.failed, ...result.untouched], modelId, completed } : null;
                    if (modelBatchReview) document.getElementById("group-hardware").checked = false;
                }
                resultNode.textContent = "Completed · " + (completed.map(numberedLabel).join(", ") || "none")
                    + (result.failed ? ". " + (result.status === "uncertain" ? "Completion uncertain" : "Failed / " + result.status) + " · " + numberedLabel(result.failed) : "")
                    + ". Untouched · " + (result.untouched.map(numberedLabel).join(", ") || "none")
                    + ". " + (result.reason || "Model dimensions remain approximate. Mapping readiness is checked separately before measured use.");
            } catch (error) { resultNode.textContent = error.message; }
            finally { confirmingModels = false; operatorGrid.render(); }
        });
        document.getElementById("image-rebuild").addEventListener("click", async () => {
            await session.refresh();
            if (!window.confirm("Keep this image choice and rebuild its preview against the current applied arrangement? Review it before Show image.")) return;
            operatorContent.rebuild(); hideConflict(); renderStage();
        });
        document.getElementById("image-discard").addEventListener("click", () => { operatorContent.discard(); state.draftConflict = false; hideConflict(); renderStage(); });
    }

    function bindSavedScenes() {
        document.getElementById("return-point-recall").addEventListener("click", () => {
            if (!returnPoint) return;
            const entry = state.savedLayouts.find(item => item.name === returnPoint.name);
            if (entry) recallLayout(entry); else setMsg(el.layoutMsg, "Refresh Saved to locate the returned arrangement.", "err");
        });
        document.getElementById("scene-save-form").addEventListener("submit", async event => {
            event.preventDefault();
            const name = document.getElementById("scene-name").value.trim(), message = document.getElementById("scene-message");
            if (!name) { setMsg(message, "Enter a content name.", "err"); document.getElementById("scene-name").focus(); return; }
            if (!await resolveOutput("Save the applied content")) return;
            const existing = savedScenes.find(entry => entry.name === name);
            if (existing && !window.confirm("Overwrite saved content “" + name + "” with the applied content? Geometry is excluded.")) return;
            try {
                const result = await api("PUT", "/api/v3/scenes/" + encodeURIComponent(name) + (existing ? "?replace=true" : ""), undefined, { etag: true });
                ingestConfig(result, { preserveDraft: true }); await loadScenes(); setMsg(message, "Content saved.", "ok");
            } catch (error) { setMsg(message, error.message, "err"); }
        });
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
            if (state.tabName !== "show" || isEditableTarget(event.target)) return;
            event.preventDefault();
            if (event.shiftKey) redoDraft();
            else undoDraft();
            return;
        }

        if (modified && (key === "y" || key === "Y")) {
            if (state.tabName !== "show" || isEditableTarget(event.target)) return;
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

        if (!selectedSlot() && !(state.draft && state.draft.placements && state.draft.placements[state.selectedId])) return;
        event.preventDefault();
        nudgeSelected(deltaX, deltaY);
    }

    function bindEvents() {
        tabEntries().forEach(function (entry) {
            if (!entry.tab) return;
            entry.tab.addEventListener("click", function () {
                showTab(entry.name, { persist: true, focus: true });
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
        el.btnReload.addEventListener("click", reloadConfigWithConfirm);
        el.btnConflictReload.addEventListener("click", reloadConfigWithConfirm);

        el.btnRotate.addEventListener("click", rotateSelected);
        el.btnDeleteSlot.addEventListener("click", deleteSelectedSlot);
        el.btnNudgeXMinus.addEventListener("click", function () { nudgeSelected(-1, 0); });
        el.btnNudgeXPlus.addEventListener("click", function () { nudgeSelected(1, 0); });
        el.btnNudgeYMinus.addEventListener("click", function () { nudgeSelected(0, -1); });
        el.btnNudgeYPlus.addEventListener("click", function () { nudgeSelected(0, 1); });
        el.btnAddSlot.addEventListener("click", addSelectedDevice);
        document.getElementById("tablet-model").addEventListener("change", () => { rememberFields("model"); syncTabDots(); });
        document.getElementById("apply-tablet-model").addEventListener("click", async () => {
            const id = state.selectedId, choice = document.getElementById("tablet-model").value;
            if (!id || !choice || state.busy) return;
            rememberFields("model");
            const submitted = tabletForms.get(id, "model");
            if (tabletForms.get(id, "profile")?.dirty || tabletForms.get(id, "calibration")?.dirty) { setMsg(el.profileMsg, "Save or discard this tablet’s measurement fields first.", "err"); return; }
            if (!await resolveOutput("Change tablet measurements")) return;
            if (choice !== "manual" && !window.confirm("I checked the hardware of " + numberedLabel(id) + ". Confirm “" + state.tabletModels[choice].label + "” for it? Dimensions remain approximate.")) return;
            setBusy(true);
            try {
                const result = await api("PUT", "/api/v3/tablet-assignments/" + encodeURIComponent(id),
                    { mode: choice === "manual" ? "manual" : "explicit", model_id: choice === "manual" ? null : choice }, { ifMatch: submitted.baseEtag });
                tabletForms.saved(id, "model", submitted.version, submitted.values, result.etag);
                await session.refresh();
                announce("Model choice saved for " + numberedLabel(id) + ". Measured readiness is checked separately.");
            } catch (error) { handleWriteError(error, state.selectedId === id ? el.profileMsg : null); }
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
            rememberFields("calibration");
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
            rememberFields("profile");
            syncTabDots();
        });
        el.calibrationForm.addEventListener("input", function () {
            invalidateRuler();
            rememberFields("calibration");
            syncTabDots();
        });
        el.profileForm.addEventListener("change", function () {
            rememberFields("profile");
            syncTabDots();
        });
        el.calibrationForm.addEventListener("change", function () {
            invalidateRuler();
            rememberFields("calibration");
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
            el.playbackMore.parentElement.addEventListener("toggle", function (event) {
                if (el.playbackCard) el.playbackCard.dataset.expanded = String(event.target.open);
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

        if (el.btnWallHealth) el.btnWallHealth.addEventListener("click", async () => {
            await showTab("tablet", { persist: true });
            document.getElementById("wall-issues-panel").open = true;
            const heading = document.getElementById("issues-title");
            heading.focus({ preventScroll: true }); heading.scrollIntoView({ block: "nearest" });
        });
        if (el.btnRosterRefresh) el.btnRosterRefresh.addEventListener("click", async () => { await Promise.all([operatorReadiness.load(), refreshRoster()]); workspace.render(); });
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

        el.btnLayoutsRefresh.addEventListener("click", () => Promise.all([loadLayouts(), loadScenes()]));
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
        operatorContent = window.OperatorContent.create({
            state, api, ingestConfig, renderStage, announce, showConflict, resolveOutput,
            refreshConnection: () => session.refresh()
        });
        operatorGrid = window.OperatorGrid.create({
            state, api, labelFor, validPair, profileFor, calibrationFor,
            ingestConfig, renderStage, syncDraftUi, isDirty, announce, showConflict,
            modelBusy: () => confirmingModels,
            modelReview: () => modelBatchReview,
            identifyTablet: id => operatorDevices.identify(id),
            canIdentify: id => !!operatorDevices && operatorDevices.canIdentify(id)
        });
        operatorDevices = window.OperatorDevices.create({
            state, api, labelFor, profileFor, calibrationFor,
            ingestConfig, refreshRoster, showConflict, announce, tabletForms, resolveOutput,
            renderRoster: () => {
                renderDeviceList();
                operatorGrid.render();
            },
            removedFromWall: id => operatorGrid.exclude(id),
            selectTablet: selectDevice,
            openArrange: () => showTab("show", { focus: true, persist: true })
        });
        for (const event of ["input", "click"]) document.getElementById("tablet-label-form").addEventListener(event, syncTabDots);
        operatorReadiness = window.OperatorReadiness.create({ state, api, copyText });
        session.subscribe(observeSession);
        workspace = window.OperatorWorkspace.create({
            state, labelFor,
            arrangementDirty: () => isDirty() || operatorGrid.dirty(),
            arrangementPreview: isDirty,
            imageDirty: () => operatorContent.dirty(),
            applyArrangement: applyLayout,
            showImage: () => operatorContent.showSelected(),
            discardArrangement: cancelDraft,
            discardImage: () => operatorContent.discard(),
            canCommit: kind => kind === "image" ? !document.getElementById("show-image").disabled : isDirty() && !el.btnApply.disabled,
            selectTablet: selectDevice, commitTask, renderStage,
            stageNames: () => operatorContent.stageNames(),
            onViewChange: () => operatorContent.viewChanged()
        });
        document.getElementById("refresh-command-status").addEventListener("click", () => session.refresh().catch(error => showError(error.message)));
        const refreshStatus = document.getElementById("refresh-status");
        if (refreshStatus) refreshStatus.addEventListener("click", async () => {
            refreshStatus.disabled = true;
            try { await Promise.all([refreshRoster(), operatorReadiness.load()]); workspace.render(); }
            catch (error) { showError(error.message); }
            finally { refreshStatus.disabled = false; }
        });
        window.addEventListener("beforeunload", event => {
            if (hasUnsavedEdits()) { event.preventDefault(); event.returnValue = ""; }
        });
        document.getElementById("open-tablet-measurements").addEventListener("click", () => { showTab("system", { persist: true }); document.getElementById("measurement-details").open = true; document.getElementById("tablet-model").focus(); });
        const imageActions = document.querySelector(".image-actions");
        const workspaceNav = document.querySelector(".workspace-nav-landmark");
        const imageActionObserver = new ResizeObserver(() => {
            document.body.style.setProperty("--task-nav-height", workspaceNav.clientHeight - parseFloat(getComputedStyle(workspaceNav).paddingBottom) + "px");
            document.body.style.setProperty("--image-action-height", imageActions.offsetHeight + "px");
            window.OperatorStage.fit(el.stageSvg);
        });
        for (const chrome of [imageActions, workspaceNav]) imageActionObserver.observe(chrome);
        state.onParticipation = (id, participating) => mutateDraft(draft => { draft.slots[id].participating = participating; });
        document.getElementById("experimental-opt-in").addEventListener("change", event => {
            document.getElementById("experimental-controls").hidden = !event.target.checked;
            if (event.target.checked) { loadLibrary(true); loadPlaylist(); refreshPlayback(); }
        });
        window.addEventListener("resize", () => { renderDeviceHealth(); renderStage(); });
        window.addEventListener("pagehide", () => { imageActionObserver.disconnect(); session.destroy(); operatorContent.destroy(); workspace.destroy(); clearInterval(state.playbackTimer); });
        operatorReadiness.load();
        const storedTab = readStoredTab();
        if (storedTab) {
            showTab(storedTab, { persist: false });
            state.tabDecided = true;
        }
        bindEvents();
        bindDiagnosticColours();
        bindTabletSetup();
        bindLogicalEditor();
        bindSavedScenes();
        loadRulerAddress();
        syncMeta();
        syncDraftUi();
        renderPlaylist();
        renderPlayback();
        renderDiagnostics();
        session.start();
        operatorContent.refresh();
        loadLayouts();
        loadScenes();
        loadDiagnostics(false);
        startPlaybackPolling();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
