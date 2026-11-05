"use strict";

/* Physical stage rendering, selection, pointer editing and slot inspector. */
function rosterSummary(config, stale) {
    const counts = window.OperatorState.registrationCounts(config);
    if (!counts) return "Tablet status unknown";
    return (stale ? "Status stale · Last known: " : "") + counts.online + " online"
        + (counts.retained ? " · " + counts.retained + (counts.retained === 1 ? " retained wall position" : " retained wall positions") : "");
}
function configureDeviceSheet(deviceSheet, compact, previousCompact) {
    if (previousCompact === compact) return previousCompact;
    if (compact) {
        if (deviceSheet.open) deviceSheet.close();
        deviceSheet.removeAttribute("open");
    } else {
        if (deviceSheet.open && deviceSheet.dataset.modal === "true") deviceSheet.close();
        if (!deviceSheet.open) deviceSheet.setAttribute("open", "");
    }
    return compact;
}

window.PhysicalStage = {
    rosterSummary: rosterSummary,
    configureDeviceSheet: configureDeviceSheet,
    create: function (dependencies) {
        const {
            identifyTablet = () => {}, canIdentify = () => false, DRAG_THRESHOLD_PX, afterDraftChange, announce, bodyMetrics, calibrationFor, beginManual, canManualEdit, clearMsg, clone, deviceEntries, deviceLabel, deviceNumber, deviceRows, el, finiteOr, formatNumber, isOnline, latestProfile, mutateDraft, numberTag, numberedLabel, populateDeviceCard, profileFor, pushUndo, roundTo, selectedSlot, selectionChanged, setInputValue, showError, showTab, state, syncTabDots, validPair
        } = dependencies;

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

        function renderStage(view = window.OperatorState.stageView(state)) {
            if (!view.layout) { el.stageScale.textContent = "Waiting for the wall."; return; }
            const { layout, content, preview, editable } = view;
            const config = state.operatorConfig || { layout: state.base, scene: state.scene, runtime: { devices: state.roster }, revision: state.revision, generation: state.generation };
            const presentation = { content: "images", tablet: "tablets", show: "arrange" }[state.tabName] || "context";
            state.stage = window.OperatorStage.draw({ svg: el.stageSvg, layout, presentation,
                viewport: state.drag && state.drag.viewport,
                content, profileFor,
                labelFor: id => numberedLabel(id, latestProfile(id)),
                statusFor: id => state.rosterError ? { status: "stale", text: "Status stale · refresh the operator connection" } : window.OperatorState.tabletState(config, id, performance.now()),
                selectedId: state.selectedId, runtime: config.runtime, preview, editable,
                resolutionNode: document.getElementById("stage-resolution") });
            const stageKey = document.getElementById("stage-key");
            if (stageKey) {
                const bounds = window.OperatorState.bounds(layout);
                const placed = window.OperatorStage.panels(layout, profileFor).filter(panel => !panel.missing && panel.slot.participating !== false);
                const area = placed.reduce((sum, panel) => sum + panel.active.width * panel.active.height, 0);
                const share = bounds.width && bounds.height ? Math.min(100, Math.round(area * 100 / (bounds.width * bounds.height))) : 0;
                stageKey.hidden = !(share > 0 && share < 100);
                stageKey.textContent = placed.length + (placed.length === 1 ? " tablet covers " : " tablets cover ") + share + "% of the wall.";
            }
            const summary = document.getElementById("stage-identities") || document.createElement("details");
            if (!summary.id) {
                summary.id = "stage-identities";
                summary.className = "stage-identities";
                summary.innerHTML = "<summary>Tablet status</summary><ul></ul>";
                (document.getElementById("stage-key") || el.stageSvg.parentElement).insertAdjacentElement("afterend", summary);
            }
            if (summary.dataset.presentation !== presentation) {
                summary.open = presentation === "tablets";
                summary.dataset.presentation = presentation;
            }
            const identities = summary.querySelector("ul");
            const rows = window.OperatorStage.panels(layout, profileFor).map(panel => {
                const status = preview ? "Local preview · not tablet output" : state.rosterError
                    ? "Status stale · refresh the operator connection" : window.OperatorState.tabletState(config, panel.id, performance.now()).text;
                return numberedLabel(panel.id, latestProfile(panel.id)) + (panel.id === state.selectedId ? " · selected" : "") + " · " + status + (panel.missing ? " · pinned profile missing" : "");
            });
            if (identities.textContent !== rows.join("")) {
                identities.replaceChildren(...rows.map(text => { const item = document.createElement("li"); item.textContent = text; return item; }));
            }
            summary.hidden = !rows.length;
            const bounds = window.OperatorState.bounds(layout);
            el.stageScale.textContent = formatNumber(bounds.width, 1) + " × " + formatNumber(bounds.height, 1)
                + (layout.kind === "physical" ? " mm" : " logical units");
        }

        function pointerToStage(event, matrix = el.stageSvg.getScreenCTM()) {
            if (!matrix) return null;
            const point = el.stageSvg.createSVGPoint();
            point.x = event.clientX;
            point.y = event.clientY;
            return point.matrixTransform(matrix.inverse());
        }

        function onPointerDown(event) {
            if (event.button !== 0 && event.pointerType === "mouse") return;
            const group = event.target && event.target.closest
                ? event.target.closest(".slot") : null;
            if (!group) return;
            const id = group.dataset.deviceId;
            if (!id || !state.draft) return;
            if (!window.OperatorState.entries(state.draft)[id]) return;

            selectDevice(id, { reveal: false });
            if (state.tabName !== "show" || state.busy || state.gridPreview || state.viewLive || state.previewContent) {
                state.stageTap = { id: id, pointerId: event.pointerId, x: event.clientX, y: event.clientY };
                return;
            }
            if (!canManualEdit()) return;
            const screenMatrix = el.stageSvg.getScreenCTM();
            const point = pointerToStage(event, screenMatrix);
            if (!point) return;

            state.drag = {
                screenMatrix,
                id: id,
                mode: event.target.closest(".logical-resize") ? "resize" : "move",
                pointerId: event.pointerId,
                startClientX: event.clientX,
                startClientY: event.clientY,
                startStageX: point.x,
                startStageY: point.y,
                scale: state.stage.scale,
                viewport: state.stage,
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
                beginManual(); drag.moved = true;
                el.stageSvg.classList.add("is-dragging");
            }

            const point = pointerToStage(event, drag.screenMatrix);
            if (!point) return;
            const slot = window.OperatorState.entries(state.draft)[drag.id];
            const before = window.OperatorState.entries(drag.preDraft)[drag.id];
            if (!slot || !before) return;
            const deltaX = (point.x - drag.startStageX) / drag.scale;
            const deltaY = (point.y - drag.startStageY) / drag.scale;
            if (state.draft.kind === "logical") {
                const step = Math.max(1, Math.round(Number(document.getElementById("logical-snap").value) || 1));
                const snap = value => Math.round(value / step) * step;
                if (drag.mode === "resize") {
                    slot.w = Math.max(slot.bezel.left + slot.bezel.right + 1, snap(before.w + deltaX));
                    slot.h = Math.max(slot.bezel.top + slot.bezel.bottom + 1, snap(before.h + deltaY));
                } else { slot.x = snap(before.x + deltaX); slot.y = snap(before.y + deltaY); }
            } else {
                slot.center_x_mm = roundTo(finiteOr(before.center_x_mm, 0) + deltaX, 2);
                slot.center_y_mm = roundTo(finiteOr(before.center_y_mm, 0) + deltaY, 2);
            }
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
                revealInspector();
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
            const slot = window.OperatorState.entries(state.draft)[drag.id];
            if (slot && state.draft.kind === "physical") {
                announce("Moved " + deviceLabel(drag.id, latestProfile(drag.id))
                    + " to " + formatNumber(slot.center_x_mm, 1) + ", "
                    + formatNumber(slot.center_y_mm, 1) + " mm.");
            }
        }

        function onPointerUp(event) {
            const tap = state.stageTap;
            if (tap && event.pointerId === tap.pointerId) {
                state.stageTap = null;
                const moved = Math.hypot(event.clientX - tap.x, event.clientY - tap.y) > DRAG_THRESHOLD_PX;
                if (!moved && state.selectedId === tap.id) revealInspector();
            }
            if (state.drag && event.pointerId === state.drag.pointerId) endDrag(true);
        }

        function onPointerCancel(event) {
            if (state.stageTap && event.pointerId === state.stageTap.pointerId) state.stageTap = null;
            if (state.drag && event.pointerId === state.drag.pointerId) endDrag(false);
        }

        /* ---------------------------------------------------------------- *
         * Selection
         * ---------------------------------------------------------------- */

        const deviceSheet = typeof document !== "undefined" ? document.getElementById("device-sheet") : null;
        let deviceSheetCompactMode = null;
        function compactSheet() {
            return typeof window.matchMedia === "function" && window.matchMedia("(max-width: 48rem)").matches;
        }
        function syncDeviceSheetMode() {
            if (!deviceSheet) return;
            const compact = compactSheet();
            deviceSheetCompactMode = configureDeviceSheet(deviceSheet, compact, deviceSheetCompactMode);
        }
        function openDeviceSheet(trigger) {
            if (!deviceSheet || !compactSheet()) return;
            state.sheetTrigger = trigger || document.activeElement;
            if (!deviceSheet.open) { deviceSheet.dataset.modal = "true"; deviceSheet.showModal(); }
            const heading = document.getElementById("tablet-action-name");
            if (heading) heading.focus({ preventScroll: true });
        }
        function revealInspector() {
            if (state.drag || state.tabName === "show") return;
            const id = state.selectedId, trigger = document.activeElement;
            Promise.resolve(showTab("tablet", { persist: true })).then(opened => {
                if (!opened || state.selectedId !== id || state.tabName !== "tablet") return;
                if (compactSheet()) { openDeviceSheet(trigger); return; }
                const heading = document.getElementById("tablet-action-name");
                if (heading) { heading.focus({ preventScroll: true }); heading.scrollIntoView({ block: "nearest" }); }
            });
        }
        if (deviceSheet && deviceSheet.addEventListener) {
            deviceSheet.addEventListener("close", function () {
                deviceSheet.dataset.modal = "";
                const trigger = state.sheetTrigger;
                state.sheetTrigger = null;
                if (trigger && trigger.isConnected && !trigger.disabled) trigger.focus({ preventScroll: true });
            });
            document.getElementById("device-sheet-close")?.addEventListener("click", function () { deviceSheet.close(); });
            window.addEventListener("resize", syncDeviceSheetMode);
            syncDeviceSheetMode();
        }

        function selectDevice(id, options) {
            if (!id) return;
            if (state.selectedId !== id) {
                state.selectedId = id;
                clearMsg(el.profileMsg);
                clearMsg(el.calibrationMsg);
                syncDeviceRows();
                syncInspector();
                renderStage();
                populateDeviceCard();
                syncTabDots();
            } else {
                syncDeviceRows();
                syncInspector();
            }
            selectionChanged();
            if (options && options.reveal) {
                const trigger = typeof document !== "undefined" ? document.activeElement : null;
                Promise.resolve(showTab("tablet", { persist: true })).then(function (opened) {
                    if (!opened) return;
                    if (compactSheet()) openDeviceSheet(trigger);
                });
            }
        }

        function syncDeviceRows() {
            deviceRows.forEach(function (row, id) {
                const selected = id === state.selectedId;
                row.item.dataset.selected = selected ? "true" : "false";
                row.pick.setAttribute("aria-pressed", selected ? "true" : "false");
            });
            renderDeviceCount();
        }

        function renderDeviceCount() {
            el.deviceEmpty.hidden = deviceRows.size > 0;
            renderDeviceHealth();
        }

        function renderDeviceHealth() {
            if (window.OperatorState && state.operatorConfig) {
                const result = window.OperatorState.aggregate(state.operatorConfig, performance.now());
                const stale = !!state.rosterError;
                const paint = result.total
                    ? (stale ? "Current image evidence unavailable" : result.showing + " of " + result.total + " showing the current image")
                    : "No tablets on the wall";
                el.wallHealth.textContent = (stale ? "Status stale · " : "") + paint;
                el.btnWallHealth.dataset.kind = stale || result.states.some(item => !["displayed", "offline", "excluded"].includes(item.status)) ? "warn" : "info";
                const compact = typeof window.matchMedia === "function" && window.matchMedia("(max-width: 36rem)").matches;
                if (compact) el.wallHealth.textContent = (stale ? "Stale · " : "") + (result.total ? result.showing + "/" + result.total + " showing image" : "No wall");
                el.btnWallHealth.setAttribute("aria-label", (stale ? "Status stale. " : "") + (result.total ? result.showing + " of " + result.total + " tablets showing the current image. Issues." : "No tablets on the wall. Issues."));
                el.deviceCount.textContent = rosterSummary(state.operatorConfig, stale);
                el.rosterStatus.hidden = !stale;
                el.rosterStatus.textContent = stale ? "Status stale. " + state.rosterError + ". Refresh status to retry." : "";
                return;
            }
            let online = 0;
            let uncalibrated = 0;
            let unplaced = 0;
            let wakeWarnings = 0;
            deviceRows.forEach(function (_row, id) {
                const connected = isOnline(id);
                if (connected) online += 1;
                if (!validPair(id)) uncalibrated += 1;
                if (!(state.base && state.base.slots && state.base.slots[id])
                        && !state.basePlacements[id]) unplaced += 1;
                const wake = state.roster[id] && state.roster[id].wake_lock;
                if (connected && ["released", "denied", "insecure"].indexOf(wake) !== -1) {
                    wakeWarnings += 1;
                }
            });
            const total = deviceRows.size;
            const stale = Boolean(state.rosterError);
            const checked = Boolean(state.rosterCheckedAt);
            el.deviceCount.textContent = !checked ? "Status unknown"
                : online + " of " + total + (stale ? " last known online" : " online");
            const facts = [online + " online", (total - online) + " offline"];
            if (uncalibrated) facts.push(uncalibrated + " needs calibration");
            if (unplaced) facts.push(unplaced + " unplaced");
            if (wakeWarnings) facts.push(wakeWarnings + " wake-lock warning" + (wakeWarnings === 1 ? "" : "s"));
            if (el.wallHealth) {
                el.wallHealth.textContent = checked
                    ? (stale ? "Last known: " : "") + (total ? facts.join(" · ") : "No known tablets")
                    : (stale ? "Tablet status unavailable" : "Checking tablet status…");
            }
            if (el.btnWallHealth) {
                el.btnWallHealth.dataset.kind = stale || (checked && (online < total || uncalibrated || unplaced || wakeWarnings))
                    ? "warn" : checked ? "ok" : "info";
            }
            if (el.rosterStatus) {
                const stamp = checked ? new Date(state.rosterCheckedAt).toLocaleTimeString() : null;
                el.rosterStatus.hidden = !stale;
                el.rosterStatus.textContent = stale
                    ? "Tablet status could not refresh. " + (stamp ? "Last checked " + stamp + ". Showing last known status." : "No status has been loaded.")
                    : "";
                el.rosterStatus.dataset.kind = stale ? "warn" : "info";
                el.rosterStatus.title = state.rosterError || state.rosterCheckedAt || "";
            }
        }

        function renderDeviceList() {
            const entries = deviceEntries(), ids = new Set(entries.map(entry => entry.id));
            for (const [id, row] of deviceRows) if (!ids.has(id)) { row.item.remove(); deviceRows.delete(id); }
            for (const [index, entry] of entries.entries()) {
                let row = deviceRows.get(entry.id);
                if (!row) {
                    const item = document.createElement("li"); item.className = "dev-row tablet-row"; item.dataset.deviceId = entry.id;
                    const pick = document.createElement("button"); pick.type = "button"; pick.className = "dev-pick tablet-pick"; pick.dataset.deviceId = entry.id;
                    const identity = document.createElement("span"); identity.className = "dev-identity";
                    const number = document.createElement("span"); number.className = "dev-number";
                    const name = document.createElement("span"); name.className = "dev-label";
                    const meta = document.createElement("span"); meta.className = "dev-meta";
                    identity.append(number, name); pick.append(identity, meta); item.append(pick);
                    pick.addEventListener("click", () => selectDevice(entry.id, { reveal: true }));
                    const add = document.createElement("button"); add.type = "button"; add.className = "btn btn-sm dev-action"; add.textContent = "Place";
                    add.addEventListener("click", async () => {
                        selectDevice(entry.id);
                        if (await showTab("show", { persist: true })) {
                            if (state.draft.kind === "physical" && !validPair(entry.id)) announce("Confirm the model or save measurements in Arrange before placing this tablet.");
                            else addSelectedDevice();
                        }
                    });
                    const identify = document.createElement("button"); identify.type = "button"; identify.className = "btn roster-identify"; identify.textContent = "Identify";
                    identify.addEventListener("click", () => identifyTablet(entry.id));
                    item.append(add, identify); row = { item, pick, number, name, meta, add, identify }; deviceRows.set(entry.id, row);
                }
                const online = isOnline(entry.id), current = state.operatorConfig && window.OperatorState.tabletState(state.operatorConfig, entry.id, performance.now());
                const status = current ? current.text : online ? "Connected · not on the wall" : "Offline";
                row.number.textContent = numberTag(entry.id);
                row.name.textContent = entry.label;
                row.meta.textContent = current && current.showing ? "" : status;
                row.item.dataset.status = current ? current.status : online ? "online" : "offline";
                row.pick.setAttribute("aria-label", numberedLabel(entry.id) + ", " + status);
                row.identify.setAttribute("aria-label", "Identify " + numberedLabel(entry.id));
                row.identify.disabled = !canIdentify(entry.id);
                row.add.hidden = !!(entry.slot || entry.placement); row.add.disabled = state.busy;
                if (el.deviceList.children[index] !== row.item) el.deviceList.insertBefore(row.item, el.deviceList.children[index] || null);
            }
            syncDeviceRows();
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
                if (el.btnCopySelectedId) el.btnCopySelectedId.hidden = true;
                return;
            }

            const profile = latestProfile(id);
            const label = deviceLabel(id, profile);
            el.inspectorEmpty.hidden = true;
            const slot = selectedSlot();

            if (state.draft && state.draft.kind === "logical") {
                el.inspectorBody.hidden = true; el.inspectorMissing.hidden = false;
                el.btnAddSlot.disabled = !!state.draft.placements[id]; el.slotMissingText.textContent = state.draft.placements[id] ? "Edit this tablet with the relative arrangement fields below." : "Place this tablet in the relative arrangement, then drag or edit its dimensions."; return;
            }

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
            el.selectedTitle.textContent = numberedLabel(id, profile);
            el.selectedId.textContent = id;
            if (el.btnCopySelectedId) {
                el.btnCopySelectedId.hidden = false;
                el.btnCopySelectedId.dataset.deviceId = id;
                el.btnCopySelectedId.textContent = "Copy full id";
            }

            const participating = slot.participating !== false;
            el.selectedState.textContent = participating ? "Included in show" : "Excluded from show";
            el.selectedState.dataset.kind = participating ? "ok" : "warn";

            setInputValue(el.slotCenterX, formatNumber(slot.center_x_mm, 2));
            setInputValue(el.slotCenterY, formatNumber(slot.center_y_mm, 2));
            setInputValue(el.slotAngle, formatNumber(slot.mount_angle, 2));
            setInputValue(el.slotNudgeX, formatNumber(slot.nudge_x_mm, 2));
            setInputValue(el.slotNudgeY, formatNumber(slot.nudge_y_mm, 2));

            const pinnedProfile = profileFor(id, slot.profile_revision);
            const metrics = pinnedProfile ? bodyMetrics(pinnedProfile) : null;
            const notes = metrics ? ["Body " + formatNumber(metrics.bodyW, 1) + " × "
                + formatNumber(metrics.bodyH, 1) + " mm; active "
                + formatNumber(metrics.activeW, 1) + " × " + formatNumber(metrics.activeH, 1) + " mm."]
                : ["Pinned profile r" + slot.profile_revision + " is unavailable. No substitute dimensions are assumed."];
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
            if (state.tabName !== "show" || state.viewLive || state.previewContent || state.gridPreview || state.busy) return;
            if (state.draft && state.draft.kind === "logical") {
                const id = state.selectedId;
                if (!state.draft.placements[id]) return;
                mutateDraft(draft => { draft.placements[id].x += deltaX; draft.placements[id].y += deltaY; });
                return;
            }
            const slot = selectedSlot();
            if (!slot || state.busy || state.gridPreview || !canManualEdit()) return;
            mutateDraft(draft => {
                const target = draft.slots[state.selectedId];
                target.nudge_x_mm = roundTo(finiteOr(target.nudge_x_mm, 0) + deltaX, 3);
                target.nudge_y_mm = roundTo(finiteOr(target.nudge_y_mm, 0) + deltaY, 3);
            });
            announce("Nudge " + formatNumber(slot.nudge_x_mm, 2) + ", "
                + formatNumber(slot.nudge_y_mm, 2) + " mm.");
        }

        function rotateSelected() {
            if (state.draft && state.draft.kind === "logical") {
                const id = state.selectedId;
                if (!state.draft.placements[id]) return;
                mutateDraft(draft => { draft.placements[id] = window.OperatorState.rotateLogical(draft.placements[id]); });
                return;
            }
            const slot = selectedSlot();
            if (!slot || state.busy || state.gridPreview || !canManualEdit()) return;
            mutateDraft(draft => {
                const target = draft.slots[state.selectedId], angle = finiteOr(target.mount_angle, 0) + 90;
                target.mount_angle = roundTo(((angle % 360) + 360) % 360, 2);
            });
            announce("Mount angle " + formatNumber(slot.mount_angle, 1) + "°.");
        }

        function deleteSelectedSlot() {
            const id = state.selectedId;
            if (!id || !selectedSlot() || state.busy || state.gridPreview) return;
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
            if (!id || state.busy || !state.draft) return;
            if (state.draft.kind === "logical") {
                if (state.draft.placements[id]) return;
                const viewport = (state.roster[id] || {}).viewport;
                const width = viewport && viewport.height > 0 ? Math.max(1, Math.round(100 * viewport.width / viewport.height)) : 100;
                mutateDraft(draft => { draft.placements[id] = { x: Math.max(0, ...Object.values(draft.placements).map(p => p.x + p.w)), y: 0,
                    w: width, h: 100, bezel: { top: 0, right: 0, bottom: 0, left: 0 } }; });
                renderDeviceList(); return;
            }
            if (state.draft.slots[id]) return;
            const pair = validPair(id);
            if (!pair) {
                showError("This tablet needs a profile and a calibration for that profile revision before it can be added.");
                return;
            }

            if (!state.draft || state.draft.kind !== "physical" || state.gridPreview) return;
            const position = window.PhysicalSizing.nextPosition(state.draft.slots, profileFor, pair.profile, state.draft.bounds);
            if (position.error) { showError(position.error); return; }
            const mount = document.getElementById("grid-common-mount").value;
            if (mount === "") { showError("Declare the mounted top edge in Arrange before adding a measured tablet. Browser rotation does not establish the mounting."); return; }
            const centerX = position.x, centerY = position.y;

            const changed = mutateDraft(function (draft) {
                draft.slots[id] = {
                    center_x_mm: roundTo(centerX, 2),
                    center_y_mm: roundTo(centerY, 2),
                    mount_angle: Number(mount),
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

        return { addSelectedDevice, deleteSelectedSlot, endDrag, nudgeSelected, onPointerCancel, onPointerDown, onPointerMove, onPointerUp, renderDeviceHealth, renderDeviceList, renderStage, rotateSelected, selectDevice, syncInspector };
    }
};
