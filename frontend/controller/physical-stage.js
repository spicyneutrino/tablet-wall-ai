"use strict";

/* Physical stage rendering, selection, pointer editing and slot inspector. */
function rosterSummary(config, stale) {
    const counts = window.OperatorState.registrationCounts(config);
    if (!counts) return "Tablet status unknown";
    return (stale ? "Status stale · Last known: " : "") + counts.online + " online"
        + (counts.retained ? " · " + counts.retained + (counts.retained === 1 ? " retained wall position" : " retained wall positions") : "");
}
function configureDeviceSheet(deviceSheet, compact) {
    if (!deviceSheet.open) deviceSheet.setAttribute("open", "");
    return compact;
}

window.PhysicalStage = {
    rosterSummary: rosterSummary,
    configureDeviceSheet: configureDeviceSheet,
    create: function (dependencies) {
        const {
            DRAG_THRESHOLD_PX, afterDraftChange, appliedName = () => "", announce, bodyMetrics, calibrationFor, beginManual, canManualEdit, clearMsg, clone, deviceEntries, deviceLabel, deviceNumber, deviceRows, el, finiteOr, formatNumber, isOnline, latestProfile, mutateDraft, numberTag, numberedLabel, populateDeviceCard, profileFor, pushUndo, roundTo, selectedSlot, selectionChanged, navigateSelection = () => {}, fitStage = () => {}, lookup = null, setInputValue, showError, showMode, state, syncTabDots, validPair
        } = dependencies;

        const $ = lookup || (id => typeof document !== "undefined" ? document.getElementById(id) : null);
        function stageEditable() { return window.OperatorState.stageEditable(state); }

        function powerFor(id) {
            return window.OperatorStage && window.OperatorStage.powerReadiness
                ? window.OperatorStage.powerReadiness(state.roster[id], { stale: !!state.rosterError, checkedAt: state.rosterCheckedAt })
                : null;
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

        function renderStage(view = window.OperatorState.stageView(state)) {
            if (!view.layout) { el.stageScale.textContent = "Waiting for the wall."; return; }
            const { layout, content, preview, editable } = view;
            const config = state.operatorConfig || { layout: state.base, scene: state.scene, runtime: { devices: state.roster }, revision: state.revision, generation: state.generation };
            const presentation = { content: "images", test: "images", arrange: "arrange" }[state.mode] || "context";
            state.stage = window.OperatorStage.draw({ svg: el.stageSvg, layout, presentation,
                viewport: state.drag && state.drag.viewport,
                content, profileFor,
                compareIds: (a, b) => window.OperatorState.compareIds(state.roster, state.deviceLabels || {}, a, b),
                labelFor: id => numberedLabel(id, latestProfile(id)),
                statusFor: id => state.rosterError ? { status: "stale", text: "Status stale · refresh the operator connection" } : window.OperatorState.tabletState(config, id, performance.now()),
                powerFor,
                fleet: presentation === "images" ? window.OperatorStage.fleetPower(state.rosterError ? [] : Object.entries(window.OperatorState.entries(state.base))
                    .filter(([, slot]) => slot.participating !== false)
                    .map(([id]) => ({ id, online: !!state.roster[id] && state.roster[id].online === true, power: powerFor(id) }))) : null,
                selectedId: state.selectedId, runtime: config.runtime, preview, editable,
                resolutionNode: $("stage-resolution") });
            const stageKey = $("stage-key");
            if (stageKey) {
                const bounds = window.OperatorState.bounds(layout);
                const placed = window.OperatorStage.panels(layout, profileFor).filter(panel => !panel.missing && panel.slot.participating !== false);
                const area = placed.reduce((sum, panel) => sum + panel.active.width * panel.active.height, 0);
                const share = bounds.width && bounds.height ? Math.min(100, Math.round(area * 100 / (bounds.width * bounds.height))) : 0;
                stageKey.hidden = !(share > 0 && share < 100);
                stageKey.textContent = placed.length + (placed.length === 1 ? " tablet covers " : " tablets cover ") + share + "% of the wall.";
            }
            const summary = $("stage-identities");
            const identities = summary.querySelector("ul");
            const rows = window.OperatorStage.panels(layout, profileFor).map(panel => {
                const status = preview ? "Local preview · not tablet output" : state.rosterError
                    ? "Status stale · refresh the operator connection" : window.OperatorState.tabletState(config, panel.id, performance.now()).text;
                const power = powerFor(panel.id);
                return numberedLabel(panel.id, latestProfile(panel.id)) + (panel.id === state.selectedId ? " · selected" : "") + " · " + status
                    + (power ? " · " + power.short : "") + (panel.missing ? " · pinned profile missing" : "");
            });
            if (identities.textContent !== rows.join("")) {
                identities.replaceChildren(...rows.map(text => { const item = document.createElement("li"); item.textContent = text; return item; }));
            }
            summary.hidden = !rows.length;
            fitStage();
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

        function snapEnabled() {
            const input = typeof document !== "undefined" ? $("logical-snap-enabled") : null;
            return !input || input.checked !== false;
        }

        function snapStep() {
            const input = typeof document !== "undefined" ? $("logical-snap") : null;
            return Math.max(1, Math.round(Number(input && input.value) || 1));
        }

        function viewZoom() {
            const body = typeof document !== "undefined" ? document.body : null;
            return body && body.dataset && body.dataset.viewZoom === "2x" ? "2x" : "fit";
        }

        function stageTransformKey(includeTranslation = true) {
            const matrix = typeof el.stageSvg.getScreenCTM === "function" ? el.stageSvg.getScreenCTM() : null;
            const stage = state.stage || {};
            const numbers = matrix ? [matrix.a, matrix.b, matrix.c, matrix.d] : [];
            if (matrix && includeTranslation) numbers.push(matrix.e, matrix.f);
            return [viewZoom(), el.stageSvg.style && el.stageSvg.style.inlineSize,
                el.stageSvg.style && el.stageSvg.style.blockSize, stage.scale, stage.offX, stage.offY,
                numbers.map(value => Number(value).toFixed(6)).join(",")].join("|");
        }

        function setViewZoom(zoom) {
            const next = zoom === "2x" ? "2x" : "fit";
            if (state.drag) endDrag(false, "view");
            if (typeof document !== "undefined" && document.body && document.body.dataset) {
                document.body.dataset.viewZoom = next;
            }
            renderStage();
            announce(next === "2x" ? "Wall view zoomed to 2x. The arrangement is unchanged." : "Wall view fitted. The arrangement is unchanged.");
            return next;
        }

        function helpText() {
            const kind = state.draft && state.draft.kind;
            return window.OperatorStage && window.OperatorStage.helpText
                ? window.OperatorStage.helpText(true, kind)
                : "Select a tablet and drag it, or use the arrow keys to move it by 1 wall unit (Shift for 10). Escape cancels a drag. Use the numeric fields for exact geometry.";
        }

        function matchStatus() {
            if (!state.draft) return { available: false, reason: "The arrangement has not loaded yet." };
            if (state.draft.kind !== "logical") {
                return { available: false, measured: true, reason: "Measured mode keeps pinned profile and calibration revisions and the declared mounting. Match screen shape is available only in relative units; review measurements instead." };
            }
            if (!stageEditable() || state.busy) {
                return { available: false, reason: "Match screen shape is available while editing an editable arrangement draft." };
            }
            const id = state.selectedId;
            if (!id || !state.draft.placements[id]) return { available: false, reason: "Select a placed tablet before matching its screen shape." };
            return window.PhysicalSizing.freshViewport(state.roster[id], { stale: !!state.rosterError });
        }

        function matchScreenShape() {
            const status = matchStatus();
            if (!status.available) {
                announce(status.reason);
                return { changed: false, reason: status.reason, measured: !!status.measured };
            }
            if (!canManualEdit()) {
                return { changed: false, reason: "Finish or discard the current proposal before matching the screen shape." };
            }
            const id = state.selectedId, slot = state.draft.placements[id];
            const result = window.PhysicalSizing.matchScreenShape(slot, status.viewport);
            if (result.error) {
                announce(result.error);
                return { changed: false, error: result.error };
            }
            if (!result.changed) {
                announce("The active screen already matches the current online viewport shape.");
                return { changed: false };
            }
            const changed = mutateDraft(draft => {
                const target = draft.placements[id];
                target.h = result.placement.h;
                target.y = result.placement.y;
            });
            if (changed) {
                announce("Matched " + deviceLabel(id, latestProfile(id)) + " to the current online viewport shape. The draft is not applied.");
            }
            return { changed: !!changed };
        }

        function onPointerDown(event) {
            if (event.button !== 0 && event.pointerType === "mouse") return;
            const group = event.target && event.target.closest
                ? event.target.closest(".slot") : null;
            if (!group) { if (!state.drag && state.selectedId) clearSelection(); return; }
            const id = group.dataset.deviceId;
            if (!id || !state.draft) return;
            if (!window.OperatorState.entries(state.draft)[id]) return;

            selectDevice(id, { reveal: false });
            if (!stageEditable() || state.busy) {
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
                transformKey: stageTransformKey(),
                geometryKey: stageTransformKey(false),
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

            if (drag.transformKey !== stageTransformKey()) {
                endDrag(false, "view");
                return;
            }

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
                const matrixScale = Math.hypot(drag.screenMatrix.a, drag.screenMatrix.b) || 1;
                const proposed = drag.mode === "resize"
                    ? { ...slot, w: before.w + deltaX, h: before.h + deltaY }
                    : { ...slot, x: before.x + deltaX, y: before.y + deltaY };
                const next = window.PhysicalSizing.snapLogical(proposed, state.draft, {
                    id: drag.id, mode: drag.mode, step: snapStep(),
                    enabled: snapEnabled() && !event.altKey,
                    threshold: window.PhysicalSizing.edgeThreshold(
                        window.PhysicalSizing.LOGICAL_EDGE_THRESHOLD_PX, matrixScale * drag.scale)
                });
                slot.x = next.x; slot.y = next.y; slot.w = next.w; slot.h = next.h;
            } else {
                slot.center_x_mm = roundTo(finiteOr(before.center_x_mm, 0) + deltaX, 2);
                slot.center_y_mm = roundTo(finiteOr(before.center_y_mm, 0) + deltaY, 2);
            }
            event.preventDefault();
            afterDraftChange();
            if (state.drag === drag) {
                if (drag.geometryKey === stageTransformKey(false)) drag.transformKey = stageTransformKey();
                else endDrag(false, "view");
            }
        }

        function endDrag(commit, reason) {
            const drag = state.drag;
            if (!drag) return;
            if (commit && drag.transformKey !== stageTransformKey()) {
                commit = false;
                reason = "view";
            }
            state.drag = null;
            el.stageSvg.classList.remove("is-dragging");
            try {
                if (el.stageSvg.hasPointerCapture(drag.pointerId)) {
                    el.stageSvg.releasePointerCapture(drag.pointerId);
                }
            } catch (error) { /* capture already gone */ }

            if (!drag.moved) {
                if (commit) revealInspector();
                return;
            }
            if (!commit) {
                state.draft = drag.preDraft;
                afterDraftChange();
                announce(reason === "view" ? "Move cancelled because the wall view changed." : "Move cancelled.");
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

        const deviceSheet = typeof document !== "undefined" ? $("device-sheet") : null;
        function focusNode(node) {
            if (!node || node.isConnected === false || node.disabled) return false;
            if (typeof node.getClientRects === "function" && !node.getClientRects().length) return false;
            try { node.focus({ preventScroll: true }); }
            catch (error) { node.focus(); }
            return true;
        }
        function focusSheetFallback() {
            for (const id of ["issues-title", "add-tablet", "tab-content"]) {
                const node = $(id);
                if (node && focusNode(node)) return;
            }
        }
        function originVisible(trigger) {
            return !!trigger && trigger.isConnected !== false && !trigger.disabled
                && (typeof trigger.getClientRects !== "function" || trigger.getClientRects().length > 0);
        }
        function revealSheet(id, trigger) {
            if (state.selectedId !== id) return false;
            state.sheetTrigger = trigger || document.activeElement;
            const heading = $("tablet-action-name");
            if (!focusNode(heading)) return false;
            if (typeof heading.scrollIntoView === "function") heading.scrollIntoView({ block: "nearest" });
            return true;
        }
        function revealInspector() {
            if (state.drag) return;
            navigateSelection(state.selectedId, { reveal: true, stageActivation: true, trigger: document.activeElement });
        }
        if (deviceSheet && deviceSheet.addEventListener) {
            configureDeviceSheet(deviceSheet);
            window.addEventListener("resize", () => { if (state.drag) endDrag(false, "view"); });
            $("device-sheet-close")?.addEventListener("click", clearSelection);
        }

        function selectDevice(id, options) {
            if (!id) return;
            if (state.selectedId !== id) {
                if (state.drag) endDrag(false, "subject");
                state.stageTap = null;
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
            return navigateSelection(id, options);
        }

        function clearSelection() {
            if (!state.selectedId) return;
            if (state.drag) endDrag(false, "subject");
            state.stageTap = null;
            state.selectedId = null;
            clearMsg(el.profileMsg);
            clearMsg(el.calibrationMsg);
            syncDeviceRows();
            syncInspector();
            renderStage();
            populateDeviceCard();
            syncTabDots();
            selectionChanged();
            const trigger = state.sheetTrigger;
            state.sheetTrigger = null;
            if (trigger?.closest?.("#stage-svg")) {
                el.stageSvg.closest(".stage-scroll").focus({ preventScroll: true });
            } else if (originVisible(trigger)) trigger.focus({ preventScroll: true });
            else focusSheetFallback();
        }

        function syncDeviceRows() {
            deviceRows.forEach(function (row, id) {
                const selected = id === state.selectedId;
                row.item.dataset.selected = selected ? "true" : "false";
                row.pick.setAttribute("aria-pressed", selected ? "true" : "false");
                row.chip.dataset.selected = selected ? "true" : "false";
                row.chipPick.setAttribute("aria-pressed", selected ? "true" : "false");
            });
            renderDeviceCount();
        }

        function renderDeviceCount() {
            renderDeviceHealth();
        }

        function renderDeviceHealth() {
            if (window.OperatorState && state.operatorConfig) {
                const result = window.OperatorState.aggregate(state.operatorConfig, performance.now());
                const stale = !!state.rosterError;
                const counts = window.OperatorState.registrationCounts(state.operatorConfig);
                const empty = counts && counts.online ? counts.online + " online · none on the wall" : "No tablets on the wall";
                const content = state.operatorConfig.scene && state.operatorConfig.scene.content || {};
                const noun = window.OperatorState.shownSubject(content);
                const paint = result.total
                    ? (stale ? "Current " + noun + " evidence unavailable" : result.showing + " of " + result.total + " showing " + (/^wall-pattern-/.test(appliedName()) ? "Test pattern" : appliedName() || "the current " + noun))
                    : empty;
                const unreachable = stale && /Connection lost|Failed to fetch|NetworkError|Load failed|aborted|timed out/i.test(state.rosterError);
                el.wallHealth.textContent = unreachable ? "Server unreachable · tablets keep their last image" : (stale ? "Status stale · " : "") + paint;
                el.btnWallHealth.dataset.state = unreachable ? "unreachable" : "";
                el.btnWallHealth.dataset.kind = unreachable ? "err" : !stale && result.states.some(item => ["failed", "blocked", "invalid_mapping"].includes(item.status)) ? "err" : stale || result.states.some(item => !["displayed", "offline", "excluded"].includes(item.status)) ? "warn"
                    : result.total && result.showing === result.total ? "ok" : "info";
                if ($("wall-health-short")) $("wall-health-short").textContent = unreachable ? "Server unreachable" : (stale ? "Stale " : "") + (result.total ? result.showing + "/" + result.total : counts?.online ? counts.online + " online" : "No wall");
                el.btnWallHealth.setAttribute("aria-label", unreachable ? el.wallHealth.textContent : (stale ? "Status stale. " : "") + (result.total ? result.showing + "/" + result.total + ". " + result.showing + " of " + result.total + " tablets showing the current " + noun + "." : empty + "."));
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
            for (const [id, row] of deviceRows) if (!ids.has(id)) { row.item.remove(); row.chip.remove(); deviceRows.delete(id); }
            const onlinePowers = entries.filter(entry => isOnline(entry.id)).map(entry => powerFor(entry.id));
            const powerCounts = new Map();
            if (!state.rosterError) for (const power of onlinePowers) {
                if (power && !power.stale) powerCounts.set(power.state, (powerCounts.get(power.state) || 0) + 1);
            }
            const commonPower = [...powerCounts].find(([, count]) => count > onlinePowers.length / 2)?.[0] || null;
            const fleetNote = $("tablet-fleet-power");
            if (fleetNote) {
                fleetNote.hidden = !commonPower || commonPower === "held";
                fleetNote.textContent = commonPower ? (powerCounts.get(commonPower) === onlinePowers.length ? "All online tablets report" : powerCounts.get(commonPower) + " of " + onlinePowers.length + " online tablets report") + " wake lock " + commonPower + "." : "";
                fleetNote.dataset.state = commonPower || "";
            }
            const differentScreens = entries.some(entry => powerFor(entry.id)?.state !== commonPower || powerFor(entry.id)?.stale);
            el.deviceList.dataset.screens = String(differentScreens);
            const screenColumn = $("screen-column");
            if (screenColumn) screenColumn.hidden = !differentScreens;
            for (const [index, entry] of entries.entries()) {
                let row = deviceRows.get(entry.id);
                if (!row) {
                    const item = document.createElement("li"); item.className = "dev-row tablet-row"; item.dataset.deviceId = entry.id;
                    const pick = document.createElement("button"); pick.type = "button"; pick.className = "dev-pick tablet-pick"; pick.dataset.deviceId = entry.id;
                    const identity = document.createElement("span"); identity.className = "dev-identity";
                    const number = document.createElement("span"); number.className = "dev-number";
                    const name = document.createElement("span"); name.className = "dev-label";
                    const meta = document.createElement("span"); meta.className = "dev-meta";
                    const facts = {};
                    for (const fact of ["connection", "image", "power"]) {
                        const node = document.createElement("span"); node.className = "dev-fact"; node.dataset.fact = fact;
                        if (Object.keys(facts).length) {
                            const separator = document.createElement("span"); separator.className = "sr-only";
                            separator.textContent = " · "; meta.append(separator);
                        }
                        facts[fact] = node; meta.append(node);
                    }
                    identity.append(number, name); pick.append(identity, meta); item.append(pick);
                    pick.addEventListener("click", () => selectDevice(entry.id, { reveal: true }));
                    const add = document.createElement("button"); add.type = "button"; add.className = "btn btn-sm dev-action"; add.textContent = "Place";
                    add.addEventListener("click", async () => {
                        selectDevice(entry.id);
                        if (await showMode("arrange")) {
                            if (state.draft.kind === "physical" && !validPair(entry.id)) announce("Confirm the model or save measurements in Arrange before placing this tablet.");
                            else addSelectedDevice();
                        }
                    });
                    item.append(add);
                    const chip = document.createElement("li"); chip.className = "roster-chip"; chip.dataset.deviceId = entry.id;
                    const chipPick = document.createElement("button"); chipPick.type = "button"; chipPick.className = "roster-pick"; chipPick.dataset.deviceId = entry.id;
                    const chipNumber = document.createElement("span"); chipNumber.className = "dev-number";
                    const glyph = document.createElement("span"); glyph.className = "roster-glyph"; glyph.setAttribute("aria-hidden", "true");
                    const word = document.createElement("span"); word.className = "roster-word";
                    const chipName = document.createElement("span"); chipName.className = "dev-label sr-only";
                    chipPick.append(chipNumber, glyph, word, chipName); chip.append(chipPick);
                    chipPick.addEventListener("click", () => { if (state.selectedId === entry.id) clearSelection(); else selectDevice(entry.id, { reveal: true, trigger: chipPick }); });
                    row = { item, pick, number, name, meta, facts, add, chip, chipPick, chipNumber, glyph, word, chipName }; deviceRows.set(entry.id, row);
                }
                const online = isOnline(entry.id), current = state.operatorConfig && !state.rosterError
                    && window.OperatorState.tabletState(state.operatorConfig, entry.id, performance.now());
                const status = state.rosterError ? "Status stale · refresh the operator connection"
                    : current ? current.text : online ? "Connected · not on the wall" : "Offline";
                const power = powerFor(entry.id);
                const device = state.roster[entry.id];
                const seen = device && device.last_seen ? Date.parse(device.last_seen) : NaN;
                const connection = state.rosterError ? "Status stale"
                    : online ? "Connected"
                    : Number.isFinite(seen) ? "Offline · last seen " + new Date(seen).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                    : "Offline";
                row.number.textContent = numberTag(entry.id);
                row.name.textContent = entry.label;
                row.facts.connection.textContent = connection;
                row.facts.connection.className = "dev-fact sr-only";
                const roster = window.OperatorState.rosterStatus(current || { status: online ? "unknown" : "offline", online }, { stale: !!state.rosterError });
                row.facts.image.textContent = roster.word;
                row.facts.power.textContent = power ? power.short : "";
                row.facts.power.title = power ? power.label : "";
                row.facts.power.className = "dev-fact" + (commonPower && power?.state === commonPower && !power.stale ? " sr-only" : "");
                row.item.dataset.status = state.rosterError ? "stale" : current ? current.status : online ? "online" : "offline";
                row.chip.dataset.status = roster.key; row.chip.dataset.tone = roster.tone;
                row.chip.dataset.powerState = power ? power.state : "unknown";
                row.chipNumber.textContent = String(deviceNumber(entry.id) || numberTag(entry.id).replace(/^#/, ""));
                row.glyph.textContent = roster.tone === "failure" ? "▲" : roster.tone === "progress" ? "○" : roster.tone === "quiet" ? "–" : "●";
                row.word.textContent = roster.key === "connected" ? "" : roster.word;
                const named = entry.label !== "Tablet " + deviceNumber(entry.id);
                row.chipName.className = "dev-label" + (named && entry.label.length <= 12 ? "" : " sr-only");
                row.chipName.textContent = entry.label;
                row.chipPick.title = numberedLabel(entry.id) + " · " + roster.word;
                row.chipPick.setAttribute("aria-label", numberedLabel(entry.id) + ", " + roster.word + (power && !(commonPower && power.state === commonPower && !power.stale) ? ". " + power.label : ""));
                row.item.dataset.powerState = power ? power.state : "unknown";
                row.item.dataset.powerWarning = String(!!power && power.warning);
                row.item.dataset.powerStale = String(!!power && power.stale);
                row.pick.setAttribute("aria-label", numberedLabel(entry.id) + ", " + connection + ", " + status + (power ? ". " + power.label : ""));
                row.add.hidden = !!(entry.slot || entry.placement); row.add.disabled = state.busy;
                if (el.deviceList.children[index] !== row.item) el.deviceList.insertBefore(row.item, el.deviceList.children[index] || null);
                const chips = $("roster");
                if (chips && chips.children[index] !== row.chip) chips.insertBefore(row.chip, chips.children[index] || null);
            }
            syncDeviceRows();
        }

        /* ---------------------------------------------------------------- *
         * Inspector
         * ---------------------------------------------------------------- */

        function syncInspector() {
            const id = state.selectedId;
            if (!id) {
                if (el.selectedTitle) el.selectedTitle.hidden = true;
                el.inspectorEmpty.hidden = false;
                el.inspectorBody.hidden = true;
                el.inspectorMissing.hidden = true;
                if (el.btnCopySelectedId) el.btnCopySelectedId.hidden = true;
                return;
            }

            const profile = latestProfile(id);
            if (el.selectedTitle) { el.selectedTitle.hidden = false; el.selectedTitle.textContent = numberedLabel(id, profile); }
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
            const power = powerFor(id);
            if (power) notes.push(power.label + ". Browser report; manual OS settings still apply.");
            el.selectedNote.textContent = notes.join(" ");

            el.btnRotate.disabled = state.busy;
            el.btnDeleteSlot.disabled = state.busy;
            el.btnNudgeXMinus.disabled = state.busy;
            el.btnNudgeXPlus.disabled = state.busy;
            el.btnNudgeYMinus.disabled = state.busy;
            el.btnNudgeYPlus.disabled = state.busy;
        }

        function nudgeSelected(deltaX, deltaY) {
            if (!stageEditable() || state.busy) return;
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
            const mount = $("grid-common-mount").value;
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

        return { clearSelection, addSelectedDevice, deleteSelectedSlot, endDrag, geometryHelp: helpText, matchScreenShape, matchStatus, nudgeSelected, onPointerCancel, onPointerDown, onPointerMove, onPointerUp, renderDeviceHealth, renderDeviceList, renderStage, revealSheet, rotateSelected, selectDevice, setViewZoom, syncInspector, viewZoom };
    }
};
