"use strict";

/* Physical stage rendering, selection, pointer editing and slot inspector. */
window.PhysicalStage = {
    create: function (dependencies) {
        const {
            DRAG_THRESHOLD_PX, WAKE_LOCK_TEXT, afterDraftChange, announce, bodyMetrics, calibrationFor, calibrationStatus, clearMsg, clone, compactView, deviceEntries, deviceLabel, deviceNumber, deviceRows, el, finiteOr, formatNumber, isOnline, latestProfile, mutateDraft, numberedLabel, populateDeviceCard, profileFor, pushUndo, roundTo, selectedSlot, setInputValue, shortId, showError, showTab, state, syncTabDots, validPair
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

        function renderStage() {
            if (!state.draft) { el.stageScale.textContent = "Waiting for the wall."; return; }
            const layout = state.gridPreview ? state.gridPreview.layout : state.draft;
            const config = state.operatorConfig || { layout: state.base, scene: state.scene, runtime: { devices: state.roster }, revision: state.revision, generation: state.generation };
            let content = state.previewContent || state.scene && state.scene.content;
            if (content && content.asset && content.asset === state.activeImageUnavailableId) content = Object.assign({}, content, { available: false });
            state.stage = window.OperatorStage.draw({ svg: el.stageSvg, layout,
                content, profileFor,
                labelFor: id => numberedLabel(id, latestProfile(id)),
                statusFor: id => window.OperatorState.tabletState(config, id, Date.now()),
                selectedId: state.selectedId, runtime: config.runtime,
                resolutionNode: document.getElementById("stage-resolution") });
            const bounds = window.OperatorState.bounds(layout);
            el.stageScale.textContent = (state.gridPreview ? "Grid preview · " : state.previewContent ? "Image selection preview · " : "Committed content / layout draft · ")
                + formatNumber(bounds.width, 1) + " × " + formatNumber(bounds.height, 1)
                + (layout.kind === "physical" ? " mm" : " logical units") + ". Preview is not tablet output confirmation.";
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
            if (state.busy || state.gridPreview) return;
            if (event.button !== 0 && event.pointerType === "mouse") return;
            const group = event.target && event.target.closest
                ? event.target.closest(".slot") : null;
            if (!group) return;
            const id = group.dataset.deviceId;
            if (!id || !state.draft) return;
            if (state.draft.kind === "logical") { selectDevice(id, { reveal: false }); return; }
            if (!state.draft.slots[id]) return;

            selectDevice(id, { reveal: false });
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

        function revealInspector() {
            if (state.drag || compactView()) return;
            if (!el.inspectorBody || el.inspectorBody.hidden) return;
            showTab("tablet", { persist: true });
            const card = el.inspectorBody.closest(".inspector") || el.inspectorBody;
            if (card && typeof card.scrollIntoView === "function") {
                let behavior = "smooth";
                if (typeof window.matchMedia === "function"
                        && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
                    behavior = "auto";
                }
                try { card.scrollIntoView({ block: "start", behavior: behavior }); }
                catch (error) { card.scrollIntoView(); }
            }
            if (el.selectedTitle) {
                try { el.selectedTitle.focus({ preventScroll: true }); }
                catch (error) { el.selectedTitle.focus(); }
            }
        }

        function selectDevice(id, options) {
            if (!id || state.busy) return;
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
                syncTabDots();
            } else {
                syncDeviceRows();
                syncInspector();
            }
            showTab("tablet", { persist: true });
            if (options && options.reveal) revealInspector();
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
            el.deviceEmpty.hidden = deviceRows.size > 0;
            renderDeviceHealth();
        }

        function renderDeviceHealth() {
            if (window.OperatorState && state.operatorConfig) {
                const result = window.OperatorState.aggregate(state.operatorConfig, Date.now());
                const stale = !!state.rosterError;
                const facts = result.states.reduce((all, item) => {
                    if (!item.showing) all[item.status] = (all[item.status] || 0) + 1;
                    return all;
                }, {});
                el.wallHealth.textContent = (stale ? "Status stale · " : "") + (result.total
                    ? (stale ? "Current image confirmation unavailable" : result.showing + " of " + result.total + " showing")
                        + (Object.keys(facts).length ? " · " + Object.entries(facts).map(([key, count]) => count + " " + key.replaceAll("_", " ")).join(" · ") : "")
                    : "No tablets on the wall");
                el.btnWallHealth.dataset.kind = stale || result.states.some(item => !["displayed", "offline", "excluded"].includes(item.status)) ? "warn" : "info";
                if (state.scene && state.scene.content.type !== "image" && result.total) el.wallHealth.textContent = result.total + " tablets on the wall · no still image selected";
                const online = Object.values(state.roster).filter(device => device.online).length;
                el.deviceCount.textContent = online + " online · " + Object.keys(state.roster).length + " registered";
                el.rosterStatus.textContent = stale ? "Status stale. " + state.rosterError + ". Refresh status to retry."
                    : "Live status and slow reconciliation. Last checked " + new Date(state.rosterCheckedAt).toLocaleTimeString() + ".";
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
                el.rosterStatus.textContent = stale
                    ? "Tablet status could not refresh. " + (stamp ? "Last checked " + stamp + ". Showing last known status." : "No status has been loaded.")
                    : stamp ? "Tablet status checked at " + stamp + ". Refresh to check again."
                        : "Tablet status has not been checked.";
                el.rosterStatus.dataset.kind = stale ? "warn" : "info";
                el.rosterStatus.title = state.rosterError || state.rosterCheckedAt || "";
            }
        }

        function renderDeviceList() {
            const focused = document.activeElement;
            const focusedRow = focused && focused.closest && focused.closest(".dev-row");
            const focusedId = focusedRow ? focusedRow.dataset.deviceId : null;
            const focusedAction = focused && focused.classList && focused.classList.contains("dev-action");

            el.deviceList.textContent = "";
            deviceRows.clear();
            const entries = deviceEntries();

            entries.forEach(function (entry) {
                const online = isOnline(entry.id);
                const number = deviceNumber(entry.id);
                const item = document.createElement("li");
                item.className = "dev-row";
                item.dataset.deviceId = entry.id;
                item.dataset.selected = entry.id === state.selectedId ? "true" : "false";

                const pick = document.createElement("button");
                pick.type = "button";
                pick.className = "dev-pick";
                pick.dataset.deviceId = entry.id;
                pick.setAttribute("aria-pressed", entry.id === state.selectedId ? "true" : "false");

                const identity = document.createElement("span");
                identity.className = "dev-identity";

                const dot = document.createElement("span");
                dot.className = "dev-dot";
                dot.dataset.online = online ? "true" : "false";
                dot.setAttribute("aria-hidden", "true");
                dot.title = online ? "Online" : "Offline";
                identity.appendChild(dot);

                const numberNode = document.createElement("span");
                numberNode.className = "dev-number";
                numberNode.textContent = number === null ? "#–" : "#" + number;
                identity.appendChild(numberNode);

                const label = document.createElement("span");
                label.className = "dev-label";
                label.textContent = entry.label;
                identity.appendChild(label);

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
                sizeText.textContent = entry.placement ? formatNumber(entry.placement.w, 1) + " × " + formatNumber(entry.placement.h, 1) + " logical units" : entry.profile
                    ? formatNumber(entry.profile.active_width_mm, 1) + " × "
                        + formatNumber(entry.profile.active_height_mm, 1) + " mm"
                    : "size unknown";
                meta.appendChild(sizeText);

                const profileText = document.createElement("span");
                profileText.textContent = state.layoutKind === "logical" ? "unit-based layout" : entry.profile
                    ? "profile r" + entry.profile.revision : "no profile";
                meta.appendChild(profileText);

                const status = state.operatorConfig && window.OperatorState
                    ? { text: window.OperatorState.tabletState(state.operatorConfig, entry.id, Date.now()).text, kind: "info" }
                    : calibrationStatus(entry.profile, entry.calibration);
                const calText = document.createElement("span");
                calText.className = "dev-cal";
                calText.dataset.kind = status.kind;
                calText.textContent = status.text;
                meta.appendChild(calText);

                const record = state.roster[entry.id];
                const wakeLock = record && typeof record.wake_lock === "string"
                    ? record.wake_lock : null;
                if (wakeLock && wakeLock !== "held") {
                    const wake = document.createElement("span");
                    wake.className = "dev-wake";
                    wake.dataset.kind = wakeLock;
                    wake.textContent = "OS-managed screen wake · " + wakeLock;
                    if (wakeLock === "unsupported") {
                        wake.title = "Wake lock is optional on HTTP. Verify OS screen timeout and power settings.";
                    } else {
                        wake.title = "Screen wake is OS-managed. Keep this tablet on power and verify its screen timeout. Image confirmation is separate.";
                    }
                    meta.appendChild(wake);
                }

                pick.setAttribute("aria-label", numberedLabel(entry.id, entry.profile)
                    + ", " + (online ? "online" : "offline")
                    + ", device " + shortId(entry.id)
                    + ", " + (entry.profile
                        ? formatNumber(entry.profile.active_width_mm, 1) + " by "
                            + formatNumber(entry.profile.active_height_mm, 1) + " millimetres active"
                        : "size unknown")
                    + ", " + (entry.profile ? "profile revision " + entry.profile.revision : "no profile")
                    + ", " + status.text
                    + (wakeLock && wakeLock !== "held"
                        ? ", " + (WAKE_LOCK_TEXT[wakeLock] || wakeLock) : "")
                    + (entry.id === state.selectedId ? ", selected" : ""));

                pick.appendChild(identity);
                pick.appendChild(flag);
                pick.appendChild(meta);
                pick.addEventListener("click", function () {
                    selectDevice(entry.id, { reveal: true });
                });

                item.appendChild(pick);

                if (entry.slot || entry.placement) {
                    const onWall = document.createElement("span");
                    onWall.className = "dev-slot";
                    onWall.textContent = "On wall";
                    item.appendChild(onWall);
                } else {
                    const pair = state.draft && state.draft.kind === "physical" && validPair(entry.id);
                    const add = document.createElement("button");
                    add.type = "button";
                    add.className = "btn btn-sm dev-action";
                    add.textContent = "Add";
                    add.disabled = !pair;
                    add.title = pair
                        ? "Add this tablet to the wall"
                        : "Use Layout & size in Wall for logical tablets, or confirm measurements before a measured Add.";
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
                    const target = focusedAction ? row.item.querySelector(".dev-action") || row.pick : row.pick;
                    try { target.focus({ preventScroll: true }); }
                    catch (error) { target.focus(); }
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
                if (el.btnCopySelectedId) el.btnCopySelectedId.hidden = true;
                return;
            }

            const profile = latestProfile(id);
            const label = deviceLabel(id, profile);
            el.inspectorEmpty.hidden = true;
            const slot = selectedSlot();

            if (state.draft && state.draft.kind === "logical") {
                el.inspectorBody.hidden = true; el.inspectorMissing.hidden = false;
                el.btnAddSlot.disabled = true; el.slotMissingText.textContent = "Logical dimensions stay in logical units. Use Layout & size in Wall; advanced geometry remains in the compatibility editor."; return;
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
            el.selectedState.textContent = participating ? "On the wall" : "Not participating";
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
            const slot = selectedSlot();
            if (!slot || state.busy || state.gridPreview) return;
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
            if (!slot || state.busy || state.gridPreview) return;
            const before = clone(state.draft);
            const angle = finiteOr(slot.mount_angle, 0) + 90;
            slot.mount_angle = roundTo(((angle % 360) + 360) % 360, 2);
            pushUndo(before);
            afterDraftChange();
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
            if (!id || state.busy || !state.draft || state.draft.kind !== "physical") return;
            if (state.draft.slots[id]) return;
            const pair = validPair(id);
            if (!pair) {
                showError("This tablet needs a profile and a calibration for that profile revision before it can be added.");
                return;
            }

            if (!state.draft || state.draft.kind !== "physical" || state.gridPreview) return;
            const position = window.PhysicalSizing.nextPosition(state.draft.slots, profileFor, pair.profile, state.draft.bounds);
            if (position.error) { showError(position.error); return; }
            const centerX = position.x, centerY = position.y;

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

        return { addSelectedDevice, deleteSelectedSlot, endDrag, nudgeSelected, onPointerCancel, onPointerDown, onPointerMove, onPointerUp, renderDeviceHealth, renderDeviceList, renderStage, rotateSelected, selectDevice, syncInspector };
    }
};
