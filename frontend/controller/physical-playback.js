"use strict";

/* Frozen playback status, readiness, exclusions and transport controls. */
window.PhysicalPlayback = {
    create: function (dependencies) {
        const {
            API_PLAYBACK, ApiError, announce, api, appendText, clearChildren, clearMsg, compareDeviceIds, deviceLabel, deviceNumber, el, errorDetail, formatDuration, formatSpan, isDirty, isOnline, latestProfile, libraryAsset, maybeChooseInitialTab, numberTag, numberedLabel, savePlaylist, setMsg, setTextIfChanged, shortId, state, syncPlaylistCurrent, syncTopbarTransport, renderFactList
        } = dependencies;

        function occurrenceOf(value) {
            if (!value || typeof value !== "object") return null;
            if (value.occurrence && typeof value.occurrence === "object") {
                return value.occurrence;
            }
            if (value.item_index !== undefined) return value;
            return null;
        }

        function liveNumber(value) {
            if (value === null || value === undefined || value === "") return null;
            const number = Number(value);
            return Number.isFinite(number) ? number : null;
        }

        function liveEntryDuration(entry) {
            if (!entry) return null;
            const duration = liveNumber(entry.duration_ms);
            if (duration !== null && duration > 0) return duration;
            const dwell = liveNumber(entry.dwell_ms);
            return dwell !== null && dwell > 0 ? dwell : null;
        }

        function normalizeLiveEntry(raw) {
            if (!raw || typeof raw !== "object") return null;
            const entry = {
                occurrence: occurrenceOf(raw),
                asset: typeof raw.asset === "string" && raw.asset !== "" ? raw.asset : null,
                kind: raw.kind === "video" || raw.kind === "still" ? raw.kind : null,
                duration_ms: liveNumber(raw.duration_ms),
                dwell_ms: liveNumber(raw.dwell_ms)
            };
            return entry.occurrence || entry.asset || entry.kind ? entry : null;
        }

        function legacyLiveEntry(status, slot) {
            let raw = null;
            if (slot === "pending") raw = status.pending;
            else if (slot === "displayed") {
                raw = status.displayed;
                if (!raw && status.state !== "armed") raw = status.current;
            } else {
                raw = status.current;
            }
            if (!raw || typeof raw !== "object") return null;
            const media = raw.media && typeof raw.media === "object"
                ? raw.media
                : slot === "pending" && status.pending_media
                    && typeof status.pending_media === "object" ? status.pending_media : null;
            let kind = raw.kind === "video" || raw.kind === "still" ? raw.kind : null;
            if (!kind && media) {
                kind = media.kind === "video" || media.kind === "still" ? media.kind : null;
            }
            if (!kind && slot === "current") {
                const reported = status.current_kind;
                kind = reported === "video" || reported === "still" ? reported : null;
            }
            const rawDuration = raw.duration_ms !== undefined ? raw.duration_ms
                : raw.durationMs !== undefined ? raw.durationMs
                    : media ? media.duration_ms
                        : slot === "current" ? status.current_duration_ms : undefined;
            const entry = {
                occurrence: occurrenceOf(raw),
                asset: typeof raw.asset === "string" && raw.asset !== ""
                    ? raw.asset
                    : typeof raw.asset_id === "string" && raw.asset_id !== "" ? raw.asset_id : null,
                kind: kind,
                duration_ms: liveNumber(rawDuration),
                dwell_ms: liveNumber(raw.dwell_ms !== undefined ? raw.dwell_ms : raw.dwellMs)
            };
            return entry.occurrence || entry.asset || entry.kind ? entry : null;
        }

        /**
         * Frozen session metadata for a slot, never the editable playlist.
         * `status.live` wins; older statuses fall back to the top-level
         * occurrence/preparation fields only.
         */
        function liveSlotEntry(status, slot) {
            if (!status || typeof status !== "object") return null;
            const live = status.live;
            if (live && typeof live === "object" && !Array.isArray(live)) {
                if (Object.prototype.hasOwnProperty.call(live, slot)) {
                    const entry = normalizeLiveEntry(live[slot]);
                    if (entry) return entry;
                }
                if (slot === "displayed" && status.state !== "armed"
                        && Object.prototype.hasOwnProperty.call(live, "current")) {
                    const entry = normalizeLiveEntry(live.current);
                    if (entry) return entry;
                }
            }
            return legacyLiveEntry(status, slot);
        }

        function liveEntryName(entry) {
            if (!entry || !entry.asset) return null;
            const asset = libraryAsset(entry.asset);
            return asset ? asset.name : shortId(entry.asset) + "…";
        }

        function occurrenceLabel(occurrence) {
            if (!occurrence || typeof occurrence !== "object") return "none";
            const index = liveNumber(occurrence.item_index);
            const loop = liveNumber(occurrence.loop);
            return Number.isInteger(index)
                ? "item " + (index + 1) + " · loop "
                    + (Number.isInteger(loop) ? loop + 1 : "—")
                : "item —";
        }

        function liveEntryKindText(entry) {
            if (!entry) return "unknown item";
            if (entry.kind === "video") {
                const duration = liveEntryDuration(entry);
                return "video" + (duration !== null
                    ? " · " + formatDuration(duration) + " clip" : "");
            }
            if (entry.kind === "still") {
                const dwell = liveNumber(entry.dwell_ms);
                return "still" + (dwell !== null
                    ? " · " + formatDuration(dwell) + " dwell" : "");
            }
            const name = liveEntryName(entry);
            return name ? "asset · " + name : "media not reported";
        }

        function liveEntryLabel(entry) {
            if (!entry) return "none";
            const name = liveEntryName(entry);
            const label = entry.occurrence ? occurrenceLabel(entry.occurrence) : "";
            if (label && name) return label + " · " + name;
            if (label) return label;
            if (name) return name;
            return liveEntryKindText(entry);
        }

        function statusNow(status) {
            if (!status || typeof status !== "object") return null;
            const raw = status.now_ms !== undefined
                ? status.now_ms
                : status.server_now_ms !== undefined
                    ? status.server_now_ms
                    : status.server_ms;
            return liveNumber(raw);
        }

        function msLabel(value) {
            const number = Number(value);
            return Number.isFinite(number) ? Math.round(number) + " ms (server)" : "—";
        }

        function remainingText(ms) {
            const value = Number(ms);
            if (!Number.isFinite(value)) return null;
            if (value <= 0) return "due now";
            return formatDuration(value) + " left";
        }

        function remainingDwell(status) {
            if (!status || !status.state || status.state === "stopped") return null;
            let observed;
            if (status.state === "paused") {
                // A paused countdown is measured at the pause instant, never now.
                observed = liveNumber(status.paused_at_ms);
                if (observed === null) return null;
            } else {
                const explicit = liveNumber(status.remaining_dwell_ms !== undefined
                    ? status.remaining_dwell_ms : status.dwell_remaining_ms);
                if (explicit !== null) return explicit;
                observed = statusNow(status);
            }
            if (observed === null) return null;
            const entry = liveSlotEntry(status, "current");
            const occurrence = entry ? entry.occurrence : null;
            const duration = liveEntryDuration(entry);
            const current = status.current && typeof status.current === "object"
                ? status.current : null;
            let effective = liveNumber(status.current_effective_ms);
            if (effective === null) effective = liveNumber(current && current.current_effective_ms);
            if (effective === null) effective = liveNumber(current && current.effective_server_ms);
            if (effective === null) effective = liveNumber(status.effective_server_ms);
            if (!occurrence || duration === null || effective === null) return null;
            const pending = status.pending && typeof status.pending === "object"
                ? status.pending : null;
            const pendingEffective = pending ? liveNumber(pending.effective_server_ms) : null;
            if (pending && pendingEffective !== null && pending.occurrence
                    && !sameOccurrence(pending.occurrence, occurrence)) {
                return pendingEffective - observed;
            }
            const recovery = status.recovery;
            const recoveryAt = liveNumber(recovery && recovery.position_ms);
            if (recovery && sameOccurrence(recovery.occurrence, occurrence)) {
                if (recovery.state === "preparing") return null;
                if (recoveryAt !== null) {
                    return effective + duration - recoveryAt - observed;
                }
            }
            return effective + duration - observed;
        }

        function idArray(value) {
            if (!Array.isArray(value)) return [];
            return value.filter(function (entry) {
                return typeof entry === "string" && entry !== "";
            });
        }

        function idSet(value) {
            const out = new Set();
            idArray(value).forEach(function (id) { out.add(id); });
            if (value && typeof value === "object" && !Array.isArray(value)) {
                Object.keys(value).forEach(function (id) { out.add(id); });
            }
            return out;
        }

        function missingSet(value) {
            const out = new Map();
            if (Array.isArray(value)) {
                value.forEach(function (entry) {
                    if (typeof entry === "string") out.set(entry, "");
                    else if (entry && typeof entry === "object") {
                        const id = typeof entry.device_id === "string" ? entry.device_id : null;
                        if (id) out.set(id, typeof entry.reason === "string" ? entry.reason : "");
                    }
                });
            } else if (value && typeof value === "object") {
                Object.keys(value).forEach(function (id) {
                    const entry = value[id];
                    out.set(id, typeof entry === "string" ? entry
                        : entry && typeof entry.reason === "string" ? entry.reason : "");
                });
            }
            return out;
        }

        function leaseMap(value) {
            const out = new Map();
            if (Array.isArray(value)) {
                value.forEach(function (entry) {
                    if (entry && typeof entry === "object" && typeof entry.device_id === "string") {
                        out.set(entry.device_id, entry);
                    }
                });
            } else if (value && typeof value === "object") {
                Object.keys(value).forEach(function (id) {
                    const entry = value[id];
                    out.set(id, entry && typeof entry === "object"
                        ? entry : { ready: Boolean(entry) });
                });
            }
            return out;
        }

        function memberState(status) {
            const pending = status && status.pending && typeof status.pending === "object"
                ? status.pending : {};
            const leases = leaseMap(pending.leases || status.leases
                || pending.evidence || status.evidence || pending.members
                || status.members || status.devices);
            const required = new Set();
            [
                status.required, status.required_members, pending.required,
                pending.required_members
            ].forEach(function (value) {
                idSet(value).forEach(function (id) { required.add(id); });
            });
            const ready = new Set();
            [
                status.ready, status.ready_members, pending.ready, pending.ready_members
            ].forEach(function (value) {
                idSet(value).forEach(function (id) { ready.add(id); });
            });
            leases.forEach(function (lease, id) {
                if (lease && lease.ready === true) ready.add(id);
            });
            const missing = new Map();
            [
                status.missing, status.missing_members, status.blocked_missing,
                status.missed, pending.missing, pending.missed
            ].forEach(function (value) {
                missingSet(value).forEach(function (reason, id) { missing.set(id, reason); });
            });
            const excluded = new Set();
            [status.excluded, status.excluded_members, pending.excluded]
                .forEach(function (value) {
                    idSet(value).forEach(function (id) { excluded.add(id); });
                });
            const cohort = idArray(status.cohort).concat(idArray(pending.cohort));
            const ordered = [];
            const seen = new Set();
            function add(id) {
                if (typeof id !== "string" || id === "" || seen.has(id)) return;
                seen.add(id);
                ordered.push(id);
            }
            cohort.forEach(add);
            required.forEach(add);
            excluded.forEach(add);
            ready.forEach(add);
            missing.forEach(function (_reason, id) { add(id); });
            leases.forEach(function (_lease, id) { add(id); });
            if (status.video && typeof status.video === "object") {
                Object.keys(status.video).forEach(add);
            }
            return {
                leases: leases,
                required: required,
                excluded: excluded,
                ready: ready,
                missing: missing,
                cohort: cohort,
                ids: ordered
            };
        }

        function videoEvidence(status, lease, id) {
            const merged = {};
            let found = false;
            function take(value) {
                if (!value || typeof value !== "object") return;
                Object.keys(value).forEach(function (key) {
                    merged[key] = value[key];
                    found = true;
                });
            }
            if (lease && typeof lease === "object") {
                take(lease.video);
                if (lease.evidence && typeof lease.evidence === "object") {
                    take(lease.evidence.video);
                }
            }
            if (status && status.video && typeof status.video === "object") {
                take(status.video[id]);
            }
            return found ? merged : null;
        }

        function playStateWord(stateName) {
            if (stateName === "final") return "final item";
            if (stateName === "armed") return "armed for the cut";
            return stateName;
        }

        function applyPlaybackStatus(status) {
            const next = status && typeof status.state === "string" ? status.state : "stopped";
            state.playback = status;
            state.playbackVersion = status && status.version !== undefined
                ? status.version : null;
            if (next !== state.playbackAnnouncedState) {
                state.playbackAnnouncedState = next;
                if (next === "blocked" || next === "failed") {
                    announce("Playback " + playStateWord(next) + ".", "warn");
                } else if (next === "stopped") {
                    announce("Playback stopped.", "info");
                } else {
                    announce("Playback " + playStateWord(next) + ".", "info");
                }
            }
            renderPlayback();
        }

        async function refreshPlayback() {
            if (state.playbackFetching) return;
            state.playbackFetching = true;
            try {
                const status = await api("GET", API_PLAYBACK);
                state.playbackError = null;
                state.playbackFetchedAt = Date.now();
                state.playbackOkAt = state.playbackFetchedAt;
                applyPlaybackStatus(status);
            } catch (error) {
                state.playbackError = errorDetail(error);
                state.playbackFetchedAt = Date.now();
                renderPlayback();
            } finally {
                state.playbackFetching = false;
                renderPlaybackPollNote();
                if (!state.playbackSettled) {
                    state.playbackSettled = true;
                    maybeChooseInitialTab();
                }
            }
        }

        function renderPlaybackPollNote() {
            if (!el.playbackPollNote) return;
            let text = "Waiting for the first status read.";
            let kind = "";
            if (state.playbackError) {
                kind = "err";
                text = "Status unavailable: " + state.playbackError;
                if (state.playbackOkAt) {
                    text += ". Last answer from " + new Date(state.playbackOkAt)
                        .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                        + ".";
                } else {
                    text += ".";
                }
                text += " Retrying every second.";
            } else if (state.playbackFetchedAt) {
                text = "Live status, read at " + new Date(state.playbackFetchedAt)
                    .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                    + ". Polled once a second while this page is visible.";
            }
            setTextIfChanged(el.playbackPollNote, text);
            if (kind) el.playbackPollNote.dataset.kind = kind;
            else el.playbackPollNote.removeAttribute("data-kind");

            if (el.playbackStale) {
                el.playbackStale.hidden = !state.playbackError;
                if (state.playbackError) {
                    el.playbackStale.textContent = state.playbackOkAt ? "stale" : "no status";
                    el.playbackStale.title = state.playbackOkAt
                        ? "The last status read was at " + new Date(state.playbackOkAt).toLocaleTimeString()
                        : "No playback status has been read yet.";
                }
            }
        }

        function savedPlaylistItems() {
            return state.savedPlaylist && Array.isArray(state.savedPlaylist.items)
                ? state.savedPlaylist.items : [];
        }

        function savedPlaylistHasVideo() {
            if (!state.savedPlaylist) return null;
            if (state.libraryState !== "ready") return null;
            return savedPlaylistItems().some(function (item) {
                const asset = libraryAsset(item.asset);
                return Boolean(asset && asset.kind === "video");
            });
        }

        function committedRequiredIds() {
            const slots = state.base && state.base.slots ? state.base.slots : {};
            return Object.keys(slots).filter(function (id) {
                return slots[id] && slots[id].participating !== false;
            });
        }

        const PLAYBACK_EXCLUSIONS_KEY = "tablet-wall-playback-exclusions-v1";

        function participantIds() {
            return committedRequiredIds().slice().sort(function (left, right) {
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
            });
        }

        function exclusionIdList(value) {
            const out = [];
            const seen = new Set();
            function add(candidate) {
                const id = typeof candidate === "string" ? candidate
                    : candidate && typeof candidate === "object"
                        ? (typeof candidate.device_id === "string" ? candidate.device_id
                            : typeof candidate.id === "string" ? candidate.id : null)
                        : null;
                if (id && !seen.has(id)) {
                    seen.add(id);
                    out.push(id);
                }
            }
            if (Array.isArray(value)) {
                value.forEach(add);
            } else if (value && typeof value === "object") {
                Object.keys(value).forEach(function (id) {
                    if (value[id] === false || value[id] === null) return;
                    add(id);
                });
            }
            return out;
        }

        function hasStatusIds(status, key) {
            return Boolean(status && typeof status === "object"
                && Object.prototype.hasOwnProperty.call(status, key)
                && status[key] !== null && status[key] !== undefined);
        }

        function selectedPlaybackExclusions() {
            const eligible = new Set(committedRequiredIds());
            const seen = new Set();
            return state.playbackExclusions.filter(function (id) {
                if (typeof id !== "string" || !eligible.has(id) || seen.has(id)) return false;
                seen.add(id);
                return true;
            });
        }

        function persistPlaybackExclusions() {
            try {
                window.sessionStorage.setItem(PLAYBACK_EXCLUSIONS_KEY,
                    JSON.stringify(state.playbackExclusions));
            } catch (error) { /* Session memory remains authoritative. */ }
        }

        function syncPlaybackExclusions() {
            if (!state.configLoaded) return;
            const eligible = new Set(committedRequiredIds());
            const next = state.playbackExclusions.filter(function (id, index) {
                return typeof id === "string" && eligible.has(id)
                    && state.playbackExclusions.indexOf(id) === index;
            });
            if (next.length === state.playbackExclusions.length
                    && next.every(function (id, index) {
                        return id === state.playbackExclusions[index];
                    })) {
                return;
            }
            state.playbackExclusions = next;
            persistPlaybackExclusions();
        }

        function restorePlaybackExclusions() {
            const eligible = new Set(committedRequiredIds());
            let stored = [];
            try {
                const value = JSON.parse(window.sessionStorage.getItem(PLAYBACK_EXCLUSIONS_KEY) || "[]");
                if (Array.isArray(value)) {
                    stored = value.filter(function (id) {
                        return typeof id === "string" && eligible.has(id);
                    });
                }
            } catch (error) { stored = []; }
            state.playbackExclusions = Array.from(new Set(stored));
            state.playbackExclusionRowKey = "";
            persistPlaybackExclusions();
        }

        function playbackExclusionData(status, frozen) {
            const participants = participantIds();
            let required = participants.slice();
            let excluded = selectedPlaybackExclusions();
            let cohortCount = null;
            if (frozen && status && typeof status === "object") {
                if (hasStatusIds(status, "required")) {
                    required = exclusionIdList(status.required);
                }
                if (hasStatusIds(status, "excluded")) {
                    excluded = exclusionIdList(status.excluded);
                }
                if (hasStatusIds(status, "cohort")) {
                    cohortCount = exclusionIdList(status.cohort).length;
                }
            }
            const requiredSet = new Set(required);
            if (requiredSet.size > 0) {
                excluded = excluded.filter(function (id) { return requiredSet.has(id); });
            }
            const excludedSet = new Set(excluded);
            const effective = required.filter(function (id) { return !excludedSet.has(id); });
            return {
                participants: participants,
                required: required,
                excluded: excluded,
                effective: effective,
                cohortCount: cohortCount === null ? effective.length : cohortCount
            };
        }

        function exclusionRowKey(participants) {
            return participants.map(function (id) {
                return [id, numberTag(id), deviceLabel(id, latestProfile(id)),
                    isOnline(id) ? "online" : "offline"].join("|");
            }).join("\n");
        }

        function onPlaybackExclusionChange(event) {
            const input = event && event.currentTarget;
            const id = input && input.dataset ? input.dataset.deviceId : "";
            if (!id) return;
            const chosen = new Set(state.playbackExclusions);
            if (input.checked) chosen.add(id);
            else chosen.delete(id);
            state.playbackExclusions = participantIds().filter(function (entry) {
                return chosen.has(entry);
            });
            persistPlaybackExclusions();
            renderPlayback();
        }

        function renderPlaybackExclusionRows(participants, excluded, disabled) {
            if (!el.playbackExclusionList) return;
            const focused = document.activeElement;
            const focusedId = focused && focused.classList
                && focused.classList.contains("playback-exclusion-input")
                ? focused.dataset.deviceId : null;
            const key = exclusionRowKey(participants);
            if (key !== state.playbackExclusionRowKey) {
                state.playbackExclusionRowKey = key;
                clearChildren(el.playbackExclusionList);
                participants.forEach(function (id) {
                    const item = document.createElement("li");
                    item.className = "playback-exclusion-item";

                    const label = document.createElement("label");
                    label.className = "playback-exclusion-option";
                    label.htmlFor = "playback-exclude-" + id;

                    const checkbox = document.createElement("input");
                    checkbox.type = "checkbox";
                    checkbox.className = "playback-exclusion-input";
                    checkbox.id = label.htmlFor;
                    checkbox.dataset.deviceId = id;
                    checkbox.checked = excluded.has(id);
                    checkbox.disabled = disabled;
                    checkbox.addEventListener("change", onPlaybackExclusionChange);

                    const copy = document.createElement("span");
                    copy.className = "playback-exclusion-copy";
                    appendText(copy, "span", "playback-exclusion-name",
                        numberedLabel(id, latestProfile(id)));
                    const meta = document.createElement("span");
                    meta.className = "playback-exclusion-meta";
                    appendText(meta, "code", "playback-exclusion-id", shortId(id) + "…");
                    const online = appendText(meta, "span", "playback-exclusion-online",
                        isOnline(id) ? "online" : "offline");
                    online.dataset.online = isOnline(id) ? "true" : "false";
                    copy.appendChild(meta);

                    label.appendChild(checkbox);
                    label.appendChild(copy);
                    item.appendChild(label);
                    el.playbackExclusionList.appendChild(item);
                });
                if (focusedId) {
                    const next = el.playbackExclusionList.querySelector(
                        'input[data-device-id="' + focusedId + '"]');
                    if (next) {
                        try { next.focus({ preventScroll: true }); }
                        catch (error) { next.focus(); }
                    }
                }
            } else {
                const inputs = el.playbackExclusionList.querySelectorAll(".playback-exclusion-input");
                for (let index = 0; index < inputs.length; index += 1) {
                    const input = inputs[index];
                    input.checked = excluded.has(input.dataset.deviceId);
                    input.disabled = disabled;
                }
            }
        }

        function renderPlaybackExclusions(status, hasSession, stateName) {
            if (!el.playbackExclusions) return;
            const frozen = Boolean(status) && hasSession && stateName !== "failed";
            const available = state.configLoaded || frozen;
            if (!available) {
                el.playbackExclusions.hidden = true;
                return;
            }

            syncPlaybackExclusions();
            const data = playbackExclusionData(status, frozen);
            const excluded = new Set(data.excluded);
            el.playbackExclusions.hidden = frozen && data.excluded.length === 0;
            const title = frozen ? "This show's cohort" : "Exclude from this show";
            setTextIfChanged(el.playbackExclusionsTitle, title);
            el.playbackExclusions.dataset.frozen = frozen ? "true" : "false";

            let summary = data.required.length + " required, "
                + data.excluded.length + " excluded, "
                + data.cohortCount + " in this show.";
            summary += data.excluded.length
                ? " Excluded: " + data.excluded.map(function (id) {
                    return numberedLabel(id, latestProfile(id));
                }).join(", ") + "."
                : " Excluded: none.";
            if (frozen) summary += " Frozen for this session.";
            setTextIfChanged(el.playbackExclusionSummary, summary);

            renderPlaybackExclusionRows(data.participants, excluded, frozen);
            if (el.playbackExclusionList) {
                el.playbackExclusionList.hidden = frozen || data.participants.length === 0;
            }
            if (el.playbackExclusionEmpty) {
                el.playbackExclusionEmpty.hidden = frozen || data.participants.length > 0;
            }
            setTextIfChanged(el.playbackExclusionNote, frozen
                ? "Frozen until Stop. Excluded tablets show the persisted scene, "
                    + "are not counted as synchronized, and strict readiness ignores them."
                : "Excluded tablets show the persisted scene. They are not counted as "
                    + "synchronized, and strict readiness ignores them.");
            const allExcluded = !frozen && data.required.length > 0
                && data.effective.length === 0;
            const warning = allExcluded
                ? "Every participating tablet is excluded. Start is disabled until at least one tablet is included."
                : "";
            if (el.playbackExclusionWarning
                    && el.playbackExclusionWarning.textContent !== warning) {
                if (warning) setMsg(el.playbackExclusionWarning, warning, "err");
                else clearMsg(el.playbackExclusionWarning);
            }
        }

        function chosenPolicy() {
            const value = el.playbackPolicy ? el.playbackPolicy.value : "";
            if (value === "strict" || value === "online") return value;
            const video = savedPlaylistHasVideo();
            if (video === null) return null;
            return video ? "strict" : "online";
        }

        function firstSavedItemName() {
            const items = savedPlaylistItems();
            if (!items.length) return "";
            const asset = libraryAsset(items[0].asset);
            return asset ? asset.name : shortId(items[0].asset) + "…";
        }

        function playbackPreflight() {
            const savedCount = savedPlaylistItems().length;
            const draftCount = state.playlist.items.length;
            const dirty = state.playlistDirty;
            const canSaveDraft = dirty && draftCount > 0
                && state.playlistEtag !== null && state.playlistLoaded;
            const physical = state.layoutKind === "physical";
            const required = committedRequiredIds();
            const excluded = selectedPlaybackExclusions();
            const excludedSet = new Set(excluded);
            const effective = required.filter(function (id) { return !excludedSet.has(id); });
            const online = effective.filter(isOnline);
            const parts = [];
            const blockers = [];

            if (!state.configLoaded) {
                return {
                    ready: false, kind: "", text: "Checking the saved wall layout…",
                    label: "Start", required: required, excluded: excluded,
                    effective: effective, online: online
                };
            }

            if (!state.playlistLoaded && state.playlistLoading) {
                parts.push("Checking the saved playlist…");
            } else if (state.playlistLoaded) {
                if (savedCount > 0) {
                    parts.push("Saved playlist: " + savedCount
                        + (savedCount === 1 ? " item" : " items")
                        + " · first “" + firstSavedItemName() + "”.");
                } else if (canSaveDraft) {
                    parts.push("No saved playlist; Save and start saves the "
                        + draftCount + (draftCount === 1 ? " draft item" : " draft items") + " first.");
                } else {
                    parts.push("No saved playlist.");
                    blockers.push("Add items under Playlist, then choose Save playlist.");
                }
                if (canSaveDraft && savedCount > 0) {
                    parts.push("Draft: " + draftCount
                        + (draftCount === 1 ? " item" : " items")
                        + ", not saved; Save and start saves first.");
                }
                if (dirty && draftCount === 0) {
                    blockers.push("The playlist draft is empty. Undo the removal or add an item.");
                }
            } else {
                parts.push("The saved playlist could not be read.");
                blockers.push("Reload this page to read the saved playlist.");
            }

            if (physical) {
                if (excluded.length > 0) {
                    parts.push("Layout: " + required.length + " required · "
                        + excluded.length + " excluded · " + effective.length
                        + " in this show · " + online.length + " online.");
                    parts.push("Excluded: " + excluded.map(function (id) {
                        return numberedLabel(id, latestProfile(id));
                    }).join(", ") + ".");
                } else {
                    parts.push("Layout: " + required.length
                        + " required · " + online.length + " online.");
                }
                if (required.length === 0) {
                    blockers.push("The saved layout has no tablets on the wall. Add tablets under Tablets, then Apply arrangement.");
                } else if (effective.length === 0) {
                    blockers.push("Every participating tablet is excluded. Include at least one tablet in this show before Start.");
                }
            } else {
                parts.push("No saved physical layout.");
                blockers.push("Set the wall bounds and choose Apply arrangement before starting.");
            }

            const policy = chosenPolicy();
            if (policy === "strict") {
                parts.push("Policy: strict (all required ready).");
            } else if (policy === "online") {
                parts.push("Policy: online (hold, then record misses).");
            } else {
                parts.push("Policy: server default.");
            }

            if (physical && effective.length > 0 && online.length === 0) {
                parts.push("No wall tablets are online. Open /client/ on a tablet on the same LAN.");
            }
            if (isDirty()) {
                parts.push("Unapplied layout changes are not part of Start.");
            }

            const ready = blockers.length === 0 && state.playlistLoaded;
            let kind = "";
            if (blockers.length > 0) kind = "err";
            else if (!state.playlistLoaded) kind = "";
            else if (physical && effective.length > 0 && online.length === 0) kind = "warn";
            else if (dirty) kind = "warn";

            const text = parts.concat(blockers).join(" ");
            return {
                ready: ready,
                kind: kind,
                text: text,
                label: canSaveDraft ? "Save and start" : "Start",
                required: required,
                excluded: excluded,
                effective: effective,
                online: online
            };
        }

        function renderPlaybackPreflight(gate) {
            if (!el.playbackPreflight) return;
            setTextIfChanged(el.playbackPreflight, gate.text);
            if (gate.kind) el.playbackPreflight.dataset.kind = gate.kind;
            else el.playbackPreflight.removeAttribute("data-kind");
        }

        function failureText(status) {
            const value = status.blocked_reason || status.failure;
            if (typeof value === "string" && value !== "") return value;
            if (value && typeof value === "object") {
                if (typeof value.reason === "string" && value.reason !== "") return value.reason;
                try { return JSON.stringify(value); }
                catch (error) { return String(value); }
            }
            return "the session stopped after a failure";
        }

        function sentence(text) {
            const value = String(text === null || text === undefined ? "" : text).trim();
            if (!value) return "";
            return /[.!?]$/.test(value) ? value : value + ".";
        }

        function recoveryReasonText(reason) {
            const value = String(reason || "").trim();
            if (value === "stalled") return "a stalled video";
            if (value === "play_failed") return "a failed play";
            if (value === "buffer_lost") return "lost buffering";
            if (value === "reconnect") return "a reconnected tablet";
            return "a video stall";
        }

        function renderPlaybackCohortLine(status, hasSession) {
            if (!el.playbackCohortLine) return;
            if (!hasSession) {
                el.playbackCohortLine.hidden = true;
                setTextIfChanged(el.playbackCohortLine, "");
                return;
            }
            const data = playbackExclusionData(status, true);
            const text = data.required.length + " required · "
                + data.excluded.length + " excluded · "
                + data.cohortCount + " in this show.";
            setTextIfChanged(el.playbackCohortLine, text);
            el.playbackCohortLine.hidden = false;
        }

        function renderPlayback() {
            const status = state.playback;
            const stateName = status && typeof status.state === "string"
                ? status.state
                : (state.playbackError ? "unknown" : "stopped");
            const hasSession = Boolean(status)
                && stateName !== "stopped" && stateName !== "unknown";
            const gate = playbackPreflight();

            if (el.playbackCard) el.playbackCard.dataset.session = hasSession ? "true" : "false";
            if (el.playbackStateWord) {
                el.playbackStateWord.textContent = stateName;
                el.playbackStateWord.dataset.state = stateName;
            }
            if (el.playbackPreflight) el.playbackPreflight.hidden = hasSession;
            if (el.playbackSession) el.playbackSession.hidden = !hasSession;

            renderPlaybackPreflight(gate);
            renderPlaybackCohortLine(status, hasSession);
            renderPlaybackExclusions(status, hasSession, stateName);
            renderPlaybackPolicy(status, hasSession);
            renderPlaybackButtons(status, gate);
            renderPlaybackSummary(status);
            renderPlaybackFacts(status);
            renderPlaybackPending(status);
            renderPlaybackMembers(status);
            renderPlaybackPollNote();
            syncPlaylistCurrent();
        }

        function renderPlaybackPolicy(status, hasSession) {
            if (!el.playbackEffectivePolicy) return;
            const field = el.playbackPolicy
                ? el.playbackPolicy.closest(".field") : null;
            if (field) field.hidden = hasSession;

            let text;
            if (hasSession) {
                text = "Effective policy: " + (status.policy || "unknown")
                    + " — frozen for this session.";
            } else {
                const choice = el.playbackPolicy ? el.playbackPolicy.value : "";
                const policy = chosenPolicy();
                if (choice) {
                    text = "Effective on Start: " + choice + ".";
                } else if (policy === "strict") {
                    text = "Effective on Start: strict (server default because the saved playlist has video).";
                } else if (policy === "online") {
                    text = "Effective on Start: online (server default because the saved playlist has no video).";
                } else {
                    text = "Effective on Start: server default.";
                }
            }
            setTextIfChanged(el.playbackEffectivePolicy, text);
        }

        function renderPlaybackButtons(status, gate) {
            const stateName = status && typeof status.state === "string" ? status.state : "stopped";
            const hasSession = Boolean(status)
                && stateName !== "stopped" && stateName !== "unknown";
            const paused = stateName === "paused";
            const blocked = stateName === "blocked";
            const failed = stateName === "failed";
            const busy = state.playbackBusy;

            if (el.btnPlaybackStart) {
                const visible = !hasSession || failed;
                el.btnPlaybackStart.hidden = !visible;
                el.btnPlaybackStart.disabled = busy || !gate.ready;
                el.btnPlaybackStart.textContent = failed && gate.label === "Start"
                    ? "Start again" : gate.label;
                el.btnPlaybackStart.title = gate.ready
                    ? (state.playlistDirty
                        ? "Save the draft playlist, then start playback."
                        : "Start a new playback session.")
                    : gate.text;
            }
            if (el.btnPlaybackPause) {
                const canPause = hasSession && !paused && !blocked && !failed;
                el.btnPlaybackPause.hidden = !(canPause || paused);
                el.btnPlaybackPause.disabled = busy || !(canPause || paused);
                el.btnPlaybackPause.textContent = paused ? "Resume" : "Pause";
                el.btnPlaybackPause.classList.toggle("btn-primary", paused);
                el.btnPlaybackPause.title = paused
                    ? "Resume the paused item at a new anchor." : "Pause playback.";
            }
            if (el.btnPlaybackRetry) {
                el.btnPlaybackRetry.hidden = !blocked;
                el.btnPlaybackRetry.disabled = busy || !blocked;
                el.btnPlaybackRetry.classList.toggle("btn-primary", blocked);
            }
            if (el.btnPlaybackStop) {
                el.btnPlaybackStop.hidden = !hasSession;
                el.btnPlaybackStop.disabled = busy || !hasSession;
            }
            if (el.playbackSteps) el.playbackSteps.hidden = !hasSession;
            if (el.btnPlaybackPrevious) el.btnPlaybackPrevious.disabled = busy || !hasSession;
            if (el.btnPlaybackNext) el.btnPlaybackNext.disabled = busy || !hasSession;
            if (el.playbackPolicy) el.playbackPolicy.disabled = busy || hasSession;
            syncTopbarTransport();
        }

        function renderPlaybackCountdown(status, stateName) {
            if (!el.playbackCountdown) return;
            let text = "";
            if (stateName === "paused") {
                const lingered = remainingDwell(status);
                if (lingered !== null) text = remainingText(lingered) + " at the pause.";
            } else if (stateName === "playing") {
                const remaining = remainingDwell(status);
                if (remaining !== null) text = remainingText(remaining) + ".";
            }
            setTextIfChanged(el.playbackCountdown, text);
        }

        function renderPlaybackSummary(status) {
            if (!el.playbackStatus) return;
            const stateName = status && typeof status.state === "string"
                ? status.state
                : (state.playbackError ? "unknown" : "stopped");
            if (el.playbackStatus.dataset.state !== stateName) {
                el.playbackStatus.dataset.state = stateName;
            }
            let text;
            if (stateName === "unknown") {
                text = "Playback status is unavailable. The page keeps retrying every second.";
            } else if (stateName === "stopped") {
                text = "Playback is stopped.";
            } else if (stateName === "blocked") {
                const recovery = status.recovery && typeof status.recovery === "object"
                    ? status.recovery : null;
                const reason = String(status.blocked_reason
                    || "the cohort was not ready before the preparation deadline")
                    .trim().replace(/[.!?]+$/, "");
                text = "Blocked: " + reason
                    + (recovery && recovery.position_ms !== undefined
                        ? " at " + formatDuration(recovery.position_ms)
                            + " (attempt " + recovery.attempts + ")"
                        : "")
                    + ". Retry this item, or Stop to end the session.";
            } else if (stateName === "failed") {
                text = "Failed: " + sentence(failureText(status))
                    + " Start begins a new session; Stop clears the failed session.";
            } else if (stateName === "paused") {
                const pausedEntry = liveSlotEntry(status, "displayed")
                    || liveSlotEntry(status, "current");
                text = "Paused on " + liveEntryLabel(pausedEntry)
                    + ". Resume restarts the item at a new anchor.";
            } else if (stateName === "armed") {
                text = "Armed: " + liveEntryLabel(liveSlotEntry(status, "current"))
                    + " is committed for the next cut.";
            } else if (stateName === "recovering") {
                const recovery = status.recovery && typeof status.recovery === "object"
                    ? status.recovery : {};
                const at = Number(recovery.position_ms);
                text = "Recovering " + liveEntryLabel(liveSlotEntry(status, "current"))
                    + (Number.isFinite(at) ? " at " + formatDuration(at) : "")
                    + " after " + recoveryReasonText(recovery.reason)
                    + (recovery.device_id
                        ? " on " + numberedLabel(recovery.device_id, latestProfile(recovery.device_id))
                        : "")
                    + ". Waiting for the group buffer and a common anchor.";
            } else {
                const currentEntry = liveSlotEntry(status, "current");
                const pendingEntry = liveSlotEntry(status, "pending");
                if (stateName === "final") {
                    text = "Final item: " + liveEntryLabel(currentEntry)
                        + ". Playback holds here; Stop ends playback.";
                } else if (stateName === "preparing") {
                    text = currentEntry
                        ? "Preparing the next item. On screen: "
                            + liveEntryLabel(currentEntry) + "."
                        : "Preparing the first item.";
                    if (pendingEntry) text += " Next: " + liveEntryLabel(pendingEntry) + ".";
                } else if (!currentEntry && pendingEntry) {
                    text = "Preparing: " + liveEntryLabel(pendingEntry) + ".";
                } else {
                    text = "Playing: " + liveEntryLabel(currentEntry) + ".";
                    if (pendingEntry) text += " Next: " + liveEntryLabel(pendingEntry) + ".";
                }
            }
            setTextIfChanged(el.playbackStatus, text);
            renderPlaybackCountdown(status, stateName);
        }

        function sameOccurrence(left, right) {
            if (!left || !right || typeof left !== "object" || typeof right !== "object") {
                return false;
            }
            return ["playlist_revision", "item_index", "loop"].every(function (key) {
                return left[key] === right[key];
            });
        }

        function renderPlaybackFacts(status) {
            if (!el.playbackFacts) return;
            const savedCount = savedPlaylistItems().length;
            const draftCount = state.playlist.items.length;
            if (!status || !status.state || status.state === "stopped") {
                const facts = [
                    ["State", !status && state.playbackError ? "status unavailable" : "stopped"],
                    ["Saved playlist", savedCount + (savedCount === 1 ? " item" : " items")]
                ];
                if (state.playlistDirty) {
                    facts.push(["Draft playlist", draftCount
                        + (draftCount === 1 ? " item" : " items") + " · not saved"]);
                }
                renderFactList(el.playbackFacts, facts);
                return;
            }
            const facts = [];
            facts.push(["State", status.state]);
            if (status.session_id) facts.push(["Session", shortId(status.session_id) + "…"]);
            if (status.version !== undefined) facts.push(["Version", status.version]);
            if (status.policy) facts.push(["Policy", status.policy]);

            const currentEntry = liveSlotEntry(status, "current");
            const currentOccurrence = currentEntry ? currentEntry.occurrence : null;
            const displayedEntry = liveSlotEntry(status, "displayed");
            const displayedOccurrence = displayedEntry ? displayedEntry.occurrence : null;
            if (displayedEntry) {
                facts.push(["Displayed", liveEntryLabel(displayedEntry)]);
            } else if (status.state === "armed") {
                facts.push(["Displayed", "the previous item stays until the cut"]);
            }

            if (currentOccurrence) {
                const current = status.current && typeof status.current === "object"
                    ? status.current : null;
                let effective = liveNumber(status.current_effective_ms);
                if (effective === null) effective = liveNumber(current && current.current_effective_ms);
                if (effective === null) effective = liveNumber(current && current.effective_server_ms);
                if (effective === null) effective = liveNumber(status.effective_server_ms);
                const future = status.state === "armed"
                    || (statusNow(status) !== null && effective !== null
                        && statusNow(status) < effective);
                if (!sameOccurrence(displayedOccurrence, currentOccurrence) || future) {
                    facts.push([future ? "Committed, future" : "Committed",
                        liveEntryLabel(currentEntry)]);
                }
                if (effective !== null) {
                    facts.push([future ? "Cut anchor" : "Active anchor", msLabel(effective)]);
                }
                if (currentEntry && (currentEntry.kind || currentEntry.asset)) {
                    facts.push(["Current media", liveEntryKindText(currentEntry)]);
                }
            }

            const remaining = ["blocked", "failed", "final"].indexOf(status.state) !== -1
                ? null : remainingDwell(status);
            if (remaining !== null) facts.push(["Remaining dwell", remainingText(remaining)]);
            if (status.recovery && typeof status.recovery === "object") {
                const recovery = status.recovery;
                facts.push(["Recovery",
                    String(recovery.reason || "stall").replace(/_/g, " ")
                    + " at " + formatDuration(recovery.position_ms)
                    + " · attempt " + recovery.attempts
                    + (recovery.degraded_ms !== undefined
                        ? " · degraded " + formatDuration(recovery.degraded_ms) : "")
                    + (recovery.missing && recovery.missing.length
                        ? " · missing " + recovery.missing.length : "")]);
            }
            if (status.hold_deadline_ms !== undefined && status.hold_deadline_ms !== null
                    && status.held) {
                facts.push(["Hold deadline", msLabel(status.hold_deadline_ms)]);
            }
            if (status.held) facts.push(["Holding", "yes"]);
            if (Array.isArray(status.missed) && status.missed.length > 0) {
                facts.push([status.policy === "strict" ? "Missing members" : "Online misses",
                    status.missed.map(function (id) {
                        return numberedLabel(id, latestProfile(id));
                    }).join(", ")]);
            }
            if (status.blocked_reason) facts.push(["Blocked reason", status.blocked_reason]);
            renderFactList(el.playbackFacts, facts);
        }

        function renderPlaybackPending(status) {
            if (!el.playbackPending) return;
            if (!status || !status.state || status.state === "stopped") {
                renderFactList(el.playbackPending, [["Preparation", "none"]]);
                return;
            }
            const pending = status.pending && typeof status.pending === "object"
                ? status.pending : null;
            const entry = liveSlotEntry(status, "pending");
            if (!pending && !entry) {
                renderFactList(el.playbackPending, [["Preparation", "none"]]);
                return;
            }
            const facts = [["Next item",
                entry ? liveEntryLabel(entry) : "occurrence not reported"]];
            if (pending && pending.preparation_id) {
                facts.push(["Preparation", shortId(pending.preparation_id) + "…"]);
            }
            if (pending && pending.effective_server_ms !== undefined) {
                facts.push(["Cut anchor", msLabel(pending.effective_server_ms)]);
                const remaining = statusNow(status) !== null
                    ? pending.effective_server_ms - statusNow(status) : null;
                if (remaining !== null) facts.push(["Cut in", remainingText(remaining)]);
            }
            if (pending && pending.prepare_deadline_ms !== undefined) {
                facts.push(["Preparation deadline", msLabel(pending.prepare_deadline_ms)]);
                if (statusNow(status) !== null) {
                    facts.push(["Deadline in",
                        remainingText(pending.prepare_deadline_ms - statusNow(status))]);
                }
            }
            const media = pending && pending.media && typeof pending.media === "object"
                ? pending.media
                : (status.pending_media && typeof status.pending_media === "object")
                    ? status.pending_media : null;
            if (media) {
                if (media.kind === "video") {
                    facts.push(["Media", "video · " + formatDuration(media.duration_ms)]);
                } else if (media.kind) {
                    facts.push(["Media", String(media.kind)]);
                }
                if (media.buffer_goal_ms !== undefined) {
                    facts.push(["Buffer goal", formatDuration(media.buffer_goal_ms)]);
                }
                if (media.start_lead_ms !== undefined) {
                    facts.push(["Start lead", formatDuration(media.start_lead_ms)]);
                }
                if (media.prepare_timeout_ms !== undefined) {
                    facts.push(["Prepare timeout", formatDuration(media.prepare_timeout_ms)]);
                }
            } else if (entry && (entry.kind || entry.asset)) {
                facts.push(["Media", liveEntryKindText(entry)]);
            }
            renderFactList(el.playbackPending, facts);
        }

        function renderPlaybackMembers(status) {
            if (!el.playbackMembers) return;
            clearChildren(el.playbackMembers);
            const stateName = status && typeof status.state === "string" ? status.state : "stopped";
            if (!status || stateName === "stopped") {
                el.playbackMembersEmpty.hidden = false;
                el.playbackMembersEmpty.textContent = "Readiness appears when a session starts.";
                return;
            }
            const info = memberState(status);
            if (info.ids.length === 0) {
                el.playbackMembersEmpty.hidden = false;
                const anyOnline = Object.keys(state.roster).some(isOnline);
                el.playbackMembersEmpty.textContent = anyOnline
                    ? "The server did not report readiness for this session."
                    : "No wall tablets are online. Open /client/ on a tablet on the same LAN.";
                return;
            }
            el.playbackMembersEmpty.hidden = true;

            const media = status.pending && status.pending.media
                && typeof status.pending.media === "object" ? status.pending.media
                : (status.pending_media && typeof status.pending_media === "object")
                    ? status.pending_media : null;
            const goal = media && media.buffer_goal_ms !== undefined
                ? Number(media.buffer_goal_ms) : null;

            info.ids.slice().sort(compareDeviceIds).forEach(function (id) {
                const lease = info.leases.get(id) || {};
                const video = videoEvidence(status, lease, id);
                const strict = status.policy === "strict";
                const participant = info.cohort.indexOf(id) !== -1;
                const isExcluded = info.excluded.has(id);
                const required = !isExcluded && (info.required.has(id)
                    || (info.required.size === 0 && strict && participant));
                const ready = info.ready.has(id);
                const missingReason = info.missing.get(id);
                const roster = state.roster[id] || {};
                const online = lease.online !== undefined ? lease.online === true
                    : roster.online === true;

                const row = document.createElement("li");
                row.className = "playback-member";
                row.dataset.state = isExcluded ? "excluded"
                    : missingReason !== undefined && missingReason !== ""
                        ? "missing" : ready ? "ready" : "waiting";

                const head = document.createElement("div");
                head.className = "playback-member-head";
                appendText(head, "span", "playback-member-name",
                    numberedLabel(id, latestProfile(id)));
                appendText(head, "code", "playback-member-id", shortId(id) + "…");
                const chips = document.createElement("span");
                chips.className = "playback-member-chips";
                if (isExcluded) {
                    const excludedChip = appendText(chips, "span", "chip", "excluded");
                    excludedChip.dataset.kind = "warn";
                } else {
                    const requiredChip = appendText(chips, "span", "chip",
                        required ? "required" : participant ? "participant" : "optional");
                    requiredChip.dataset.kind = "info";
                    const stateChip = appendText(chips, "span", "chip",
                        ready ? "ready" : missingReason !== undefined ? "missing" : "preparing next");
                    stateChip.dataset.kind = ready ? "ok" : missingReason !== undefined ? "err" : "warn";
                }
                const onlineChip = appendText(chips, "span", "chip", online ? "online" : "offline");
                onlineChip.dataset.kind = online ? "ok" : "err";
                head.appendChild(chips);
                row.appendChild(head);

                const meta = document.createElement("p");
                meta.className = "playback-member-meta";
                const bits = [];
                if (isExcluded) {
                    bits.push("persisted scene · not in the synchronized cohort");
                } else {
                    if (lease.clock_ok !== undefined) {
                        bits.push("clock " + (lease.clock_ok ? "ok" : "stale"));
                    }
                    if (lease.mapping_revision !== undefined && lease.mapping_revision !== null) {
                        bits.push("mapping r" + lease.mapping_revision);
                    }
                    if (lease.protocol !== undefined && lease.protocol !== null) {
                        bits.push("protocol " + lease.protocol);
                    }
                    if (lease.unsupported === true) bits.push("protocol unsupported");
                    if (lease.reason) bits.push(String(lease.reason));
                    if (video) {
                        if (video.play_ok === "yes") bits.push("activation ok");
                        else if (video.play_ok === "needs_gesture") bits.push("activation needs a tap");
                        else if (video.play_ok === "no") bits.push("activation failed");
                        if (video.metadata !== undefined) {
                            bits.push("metadata " + (video.metadata ? "yes" : "no"));
                        }
                        if (video.seeked !== undefined) bits.push("seek " + (video.seeked ? "yes" : "no"));
                        if (video.buffered_ahead_ms !== undefined) {
                            bits.push("buffer " + formatSpan(video.buffered_ahead_ms)
                                + (goal !== null ? " / " + formatSpan(goal) : ""));
                        }
                        if (video.rvfc !== undefined) bits.push("rVFC " + (video.rvfc ? "yes" : "no"));
                        if (video.drift_ms !== undefined) {
                            bits.push("drift " + Math.round(video.drift_ms) + " ms");
                        }
                        if (video.rate !== undefined) bits.push("rate " + Number(video.rate).toFixed(2));
                        if (video.source !== undefined) bits.push("source " + video.source);
                        if (video.age_ms !== undefined) {
                            bits.push("sample " + formatSpan(video.age_ms) + " old");
                        }
                        if (video.media_ms !== undefined) {
                            bits.push("media " + formatSpan(video.media_ms));
                        }
                    }
                    if (missingReason) bits.push("missing: " + missingReason);
                }
                if (bits.length) {
                    meta.textContent = bits.join(" · ");
                    row.appendChild(meta);
                }
                el.playbackMembers.appendChild(row);
            });
        }

        function friendlyPlaybackError(error) {
            const detail = errorDetail(error);
            if (error instanceof ApiError && error.status === 409) {
                if (/no eligible physical endpoints/i.test(detail)) {
                    return "No wall tablets are online. Open /client/ on a tablet on the same LAN, then start again.";
                }
                if (/save a playlist/i.test(detail)) {
                    return "Save a playlist before starting playback.";
                }
                if (/physical layout is required/i.test(detail)) {
                    return "Apply a physical layout before starting playback.";
                }
                if (/all participating slots are excluded/i.test(detail)) {
                    return "Every participating tablet is excluded. Include at least one tablet, then start again.";
                }
            }
            return detail;
        }

        async function playbackAction(action) {
            if (state.playbackBusy) return;
            if (action === "start" && state.playlistSaving) return;
            clearMsg(el.playbackMsg);

            if (action === "start") {
                const gate = playbackPreflight();
                if (!gate.ready) {
                    setMsg(el.playbackMsg, gate.text, "err");
                    return;
                }
                if (state.playlistDirty) {
                    const saved = await savePlaylist();
                    if (!saved) {
                        setMsg(el.playbackMsg,
                            "The playlist was not saved, so playback did not start.", "err");
                        return;
                    }
                    const afterSave = playbackPreflight();
                    if (!afterSave.ready) {
                        setMsg(el.playbackMsg, afterSave.text, "err");
                        return;
                    }
                }
            }

            state.playbackBusy = true;
            renderPlaybackButtons(state.playback, playbackPreflight());
            try {
                let status;
                let retried = false;
                while (true) {
                    try {
                        if (action === "start") {
                            const policy = el.playbackPolicy ? el.playbackPolicy.value : "";
                            const body = { exclusions: selectedPlaybackExclusions() };
                            if (policy) body.policy = policy;
                            status = await api("POST", API_PLAYBACK + "/start", body);
                        } else if (action === "resume") {
                            // Resume keeps the frozen policy and cohort; send no policy.
                            status = await api("POST", API_PLAYBACK + "/start");
                        } else {
                            // A cut can advance the version between polls. Read it
                            // immediately before the write, then retry once if a
                            // commit landed in the narrow window.
                            const fresh = await api("GET", API_PLAYBACK);
                            applyPlaybackStatus(fresh);
                            if (state.playbackVersion === null) {
                                throw new ApiError(428, "No playback version is loaded.");
                            }
                            status = await api("POST", API_PLAYBACK + "/" + action, undefined,
                                { ifMatch: String(state.playbackVersion) });
                        }
                        break;
                    } catch (error) {
                        if (!retried && error instanceof ApiError && error.status === 412
                                && action !== "start" && action !== "resume") {
                            retried = true;
                            await refreshPlayback();
                            continue;
                        }
                        throw error;
                    }
                }
                state.playbackError = null;
                state.playbackFetchedAt = Date.now();
                state.playbackOkAt = state.playbackFetchedAt;
                applyPlaybackStatus(status);
            } catch (error) {
                const detail = friendlyPlaybackError(error);
                setMsg(el.playbackMsg, detail, "err");
                announce(detail, "err");
                refreshPlayback();
            } finally {
                state.playbackBusy = false;
                renderPlaybackButtons(state.playback, playbackPreflight());
            }
        }

        function actionFromPauseButton() {
            const status = state.playback;
            return status && status.state === "paused" ? "resume" : "pause";
        }

        return { actionFromPauseButton, liveSlotEntry, playbackAction, playbackPreflight, refreshPlayback, renderPlayback, renderPlaybackButtons, renderPlaybackPreflight, restorePlaybackExclusions, model: { liveSlotEntry, remainingDwell, memberState, sameOccurrence, videoEvidence } };
    }
};
