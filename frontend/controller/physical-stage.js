"use strict";

/* Physical stage rendering, selection, pointer editing and slot inspector. */
window.PhysicalStage = {
    create: function (dependencies) {
        const {
            DRAG_THRESHOLD_PX, STAGE_H, STAGE_MARGIN, STAGE_W, SVG_NS, WAKE_LOCK_TEXT, afterDraftChange, announce, bodyMetrics, calibrationFor, calibrationStatus, clearMsg, clone, compactView, deviceEntries, deviceLabel, deviceNumber, deviceRows, el, finiteOr, formatNumber, isOnline, latestProfile, mutateDraft, niceStep, numberedLabel, populateDeviceCard, profileFor, pushUndo, renderRebindOptions, roundTo, selectedSlot, setInputValue, shortId, showError, showTab, state, syncTabDots, validPair
        } = dependencies;

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
            const scale = Math.max(1e-9, Math.min(
                (STAGE_W - STAGE_MARGIN * 2) / width,
                (STAGE_H - STAGE_MARGIN * 2) / height
            ));
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
            const countX = Math.min(400, Math.floor(bounds.width / stage.step) + 2);
            for (let index = 0; index < countX; index += 1) {
                const x = startX + index * stage.step;
                const px = stage.offX + x * scale;
                const major = Math.round(x / stage.step) % 5 === 0;
                grid.appendChild(svgNode("line", {
                    x1: px, y1: wallY, x2: px, y2: wallY + wallH,
                    "data-major": major ? "true" : "false"
                }));
            }
            const startY = Math.ceil(bounds.y / stage.step) * stage.step;
            const countY = Math.min(400, Math.floor(bounds.height / stage.step) + 2);
            for (let index = 0; index < countY; index += 1) {
                const y = startY + index * stage.step;
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
            const svgRect = svg.getBoundingClientRect();
            const stagePerCss = svgRect.width > 0 ? STAGE_W / svgRect.width : 1;
            const minimumHit = 44 * stagePerCss;

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
                const label = numberedLabel(id, profile);

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

                const hitWidth = Math.max((metrics.bodyW + 16) * scale, minimumHit);
                const hitHeight = Math.max((metrics.bodyH + 16) * scale, minimumHit);
                group.appendChild(svgNode("rect", {
                    "class": "slot-hit",
                    x: -hitWidth / 2,
                    y: -hitHeight / 2,
                    width: hitWidth,
                    height: hitHeight
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

            if (focusedSlotId && focusedSlotId === state.selectedId) {
                focusStageSlot(focusedSlotId);
            }
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
            let online = 0;
            deviceRows.forEach(function (row, id) {
                if (isOnline(id)) online += 1;
            });
            const total = deviceRows.size;
            el.deviceCount.textContent = total === 0
                ? "0 online" : online + " of " + total + " online";
            el.deviceEmpty.hidden = total > 0;
        }

        function renderDeviceList() {
            const focused = document.activeElement;
            const focusedId = focused && focused.classList
                && focused.classList.contains("dev-pick") ? focused.dataset.deviceId : null;

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

                const record = state.roster[entry.id];
                const wakeLock = record && typeof record.wake_lock === "string"
                    ? record.wake_lock : null;
                if (wakeLock && wakeLock !== "held") {
                    const wake = document.createElement("span");
                    wake.className = "dev-wake";
                    wake.dataset.kind = wakeLock;
                    wake.textContent = WAKE_LOCK_TEXT[wakeLock] || ("Wake lock " + wakeLock);
                    if (wakeLock === "unsupported") {
                        wake.title = "Normal on plain HTTP. The tablet may let its screen sleep.";
                    } else {
                        wake.title = "The screen may sleep during playback. Bring the tablet page to the foreground.";
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
            renderRebindOptions();

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
                if (el.btnCopySelectedId) el.btnCopySelectedId.hidden = true;
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
            const columnOffset = count === 0 ? 0 : column - 1;
            const row = Math.floor(count / 3);
            let centerX = bounds.x + bounds.width / 2
                + columnOffset * (metrics.bodyW + 24);
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

        return { addSelectedDevice, deleteSelectedSlot, endDrag, nudgeSelected, onPointerCancel, onPointerDown, onPointerMove, onPointerUp, renderDeviceList, renderStage, rotateSelected, selectDevice, syncInspector };
    }
};
