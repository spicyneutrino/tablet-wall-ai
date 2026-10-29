"use strict";

/* Selection, local history, tiling and pointer editing share one editor state. */
window.ControllerStage = {
    create: function (dependencies) {
        const {
            DEVICE_TYPE_NAMES, PRESETS, SNAPSHOTS, aspectDelta, aspectOf, beginSnapshotRecall, clearPlacement, compareIds, cssEscape, deviceCaps, devices, editor, el, fmtAspect, fmtDelta, fmtNumber, focusTile, forgetDevice, isAspectMismatch, logStatus, normalizeColor, paintTileScreen, pct, placementProblem, placementShapeMismatch, renderWall, renderWallMap, requestJson, savePlacement, savedPlacement, seenLabel, setDeviceColor, shortId, stage, tiles, updateStageReadout, viewportAspect, visibleRect, wallReady, runtime
        } = dependencies;
        const SNAP_THRESHOLD_PX = 9;

        function isMobile() {
            return typeof window.matchMedia === "function" &&
                window.matchMedia("(max-width: 900px)").matches;
        }

        function clonePlacement(placement) {
            return placement ? JSON.parse(JSON.stringify(placement)) : null;
        }

        function clonePlacements() {
            return JSON.parse(JSON.stringify((runtime.wall && runtime.wall.placements) || {}));
        }

        function samePlacementMap(a, b) {
            return JSON.stringify(a || {}) === JSON.stringify(b || {});
        }

        /** The wire model uses whole wall units, even though the UI may compute
         *  fractions while fitting a grid. Round once, at the boundary. */
        function roundPlacement(placement) {
            if (!placement) return null;
            const bezel = placement.bezel || {};
            return {
                x: Math.round(Number(placement.x) || 0),
                y: Math.round(Number(placement.y) || 0),
                w: Math.max(1, Math.round(Number(placement.w) || 1)),
                h: Math.max(1, Math.round(Number(placement.h) || 1)),
                bezel: {
                    top: Math.max(0, Math.round(Number(bezel.top) || 0)),
                    right: Math.max(0, Math.round(Number(bezel.right) || 0)),
                    bottom: Math.max(0, Math.round(Number(bezel.bottom) || 0)),
                    left: Math.max(0, Math.round(Number(bezel.left) || 0))
                }
            };
        }

        function intersects(a, b) {
            return a.x < b.x + b.w && a.x + a.w > b.x &&
                a.y < b.y + b.h && a.y + a.h > b.y;
        }

        function setContextMode(mode, options) {
            if (!["tablet", "content", "layout"].includes(mode)) return;
            editor.contextMode = mode;
            if (stage.context) stage.context.dataset.mode = mode;
            for (const tab of stage.contextTabs) {
                tab.setAttribute("aria-pressed", String(tab.dataset.contextTab === mode));
            }
            applyPaneVisibility();
            if (mode === "tablet") renderSelection();
            if (mode === "layout") renderLayoutShortcuts();
            if (options && options.focus) {
                const target = mode === "tablet" ? stage.paneTablet :
                    mode === "content" ? stage.paneContent : stage.paneLayout;
                if (target && target.scrollIntoView) target.scrollIntoView({ block: "nearest" });
            }
        }

        function setMobileTask(task) {
            if (!["wall", "tablets", "content", "saved"].includes(task)) return;
            editor.mobileTask = task;
            if (stage.app) stage.app.dataset.task = task;
            for (const tab of stage.mobileTabs) {
                tab.setAttribute("aria-pressed", String(tab.dataset.task === task));
            }
            if (task === "wall") editor.contextMode = "tablet";
            if (task === "content") editor.contextMode = "content";
            if (task === "saved") editor.contextMode = "layout";
            if (stage.context) stage.context.dataset.mode = editor.contextMode;
            for (const tab of stage.contextTabs) {
                tab.setAttribute("aria-pressed", String(tab.dataset.contextTab === editor.contextMode));
            }
            applyPaneVisibility();
            if (task === "wall") {
                renderSelection();
                setTimeout(renderWallMap, 0);
            }
            if (task === "content") setContextMode("content");
            if (task === "saved") {
                renderLayoutShortcuts();
                if (editor.tilePreviewPlan) setTimeout(renderWallMap, 0);
            }
            if (task === "tablets") {
                for (const tile of tiles.values()) {
                    const device = devices.get(tile.el.dataset.id);
                    if (device) paintTileScreen(tile, device);
                }
            }
        }

        function applyPaneVisibility() {
            if (!stage.paneTablet || !stage.paneContent || !stage.paneLayout) return;
            if (isMobile()) {
                stage.paneTablet.hidden = editor.mobileTask !== "wall";
                stage.paneContent.hidden = editor.mobileTask !== "content";
                stage.paneLayout.hidden = editor.mobileTask !== "saved";
                return;
            }
            stage.paneTablet.hidden = editor.contextMode !== "tablet";
            stage.paneContent.hidden = editor.contextMode !== "content";
            stage.paneLayout.hidden = editor.contextMode !== "layout";
        }

        function renderTilesSelection() {
            for (const [id, tile] of tiles) {
                const selected = id === editor.selectedId;
                tile.el.dataset.selected = String(selected);
                tile.el.setAttribute("aria-selected", String(selected));
            }
        }

        function selectDevice(id, options) {
            const opts = options || {};
            if (!devices.has(id)) {
                editor.selectedId = null;
                renderTilesSelection();
                renderSelection();
                return;
            }
            if (editor.selectedId !== id) {
                editor.inspForgetPending = false;
                if (editor.inspForgetTimer) clearTimeout(editor.inspForgetTimer);
            }
            editor.selectedId = id;
            if (isMobile() && editor.mobileTask !== "wall" && !opts.keepTask) {
                setMobileTask("wall");
            }
            if (!opts.keepContext) setContextMode("tablet");
            renderTilesSelection();
            if (opts.rebuildMap !== false) {
                renderWallMap();
            } else if (stage.mapFrame) {
                for (const node of stage.mapFrame.querySelectorAll(".map-pl")) {
                    node.dataset.selected = String(node.dataset.id === id);
                }
            }
            renderSelection();
            if (opts.focusTile !== false && !isMobile()) {
                const tile = tiles.get(id);
                if (tile && tile.el.scrollIntoView) {
                    tile.el.scrollIntoView({ block: "nearest" });
                }
            }
            if (isMobile() && opts.revealInspector !== false && stage.inspector) {
                setTimeout(function () {
                    stage.inspector.scrollIntoView({ block: "start", behavior: "smooth" });
                }, 0);
            }
        }

        function defaultPlacementFor(device) {
            const wallW = runtime.wall && runtime.wall.width > 0 ? runtime.wall.width : 1000;
            const wallH = runtime.wall && runtime.wall.height > 0 ? runtime.wall.height : 500;
            const aspect = viewportAspect(device) || 1;
            let w = Math.max(80, Math.round(wallW / 3));
            w = Math.min(w, wallW);
            const visibleW = Math.max(20, w);
            let h = Math.round(visibleW / aspect);
            h = Math.min(Math.max(20, h), wallH);
            return {
                x: 0,
                y: 0,
                w: w,
                h: h,
                bezel: { top: 0, right: 0, bottom: 0, left: 0 }
            };
        }

        function readInspectorPlacement() {
            const values = {
                x: Number(stage.inspX.value),
                y: Number(stage.inspY.value),
                w: Number(stage.inspW.value),
                h: Number(stage.inspH.value),
                "bezel-top": Number(stage.inspBezelTop.value),
                "bezel-right": Number(stage.inspBezelRight.value),
                "bezel-bottom": Number(stage.inspBezelBottom.value),
                "bezel-left": Number(stage.inspBezelLeft.value)
            };
            for (const key of Object.keys(values)) {
                if (!Number.isFinite(values[key])) {
                    return { error: "Every position field needs a number." };
                }
            }
            if (values["bezel-top"] < 0 || values["bezel-right"] < 0 ||
                    values["bezel-bottom"] < 0 || values["bezel-left"] < 0) {
                return { error: "Bezel offsets cannot be negative." };
            }
            const placement = {
                x: values.x,
                y: values.y,
                w: values.w,
                h: values.h,
                bezel: {
                    top: values["bezel-top"],
                    right: values["bezel-right"],
                    bottom: values["bezel-bottom"],
                    left: values["bezel-left"]
                }
            };
            const rounded = roundPlacement(placement);
            const problem = placementProblem(rounded);
            if (problem) return { error: problem.charAt(0).toUpperCase() + problem.slice(1) + "." };
            return { placement: rounded };
        }

        function setInspectorFields(placement, includeBezel) {
            if (!placement) return;
            stage.inspX.value = fmtNumber(placement.x);
            stage.inspY.value = fmtNumber(placement.y);
            stage.inspW.value = fmtNumber(placement.w);
            stage.inspH.value = fmtNumber(placement.h);
            if (includeBezel !== false) {
                stage.inspBezelTop.value = fmtNumber(placement.bezel.top);
                stage.inspBezelRight.value = fmtNumber(placement.bezel.right);
                stage.inspBezelBottom.value = fmtNumber(placement.bezel.bottom);
                stage.inspBezelLeft.value = fmtNumber(placement.bezel.left);
                stage.inspBezelSummary.textContent =
                    fmtNumber(placement.bezel.top) + " / " +
                    fmtNumber(placement.bezel.right) + " / " +
                    fmtNumber(placement.bezel.bottom) + " / " +
                    fmtNumber(placement.bezel.left);
            }
            updateInspectorShape();
        }

        function updateInspectorShape() {
            if (!stage.inspShape) return;
            const device = editor.selectedId ? devices.get(editor.selectedId) : null;
            if (!device) {
                stage.inspShape.textContent = "";
                stage.inspWarning.hidden = true;
                return;
            }
            const read = readInspectorPlacement();
            if (read.error) {
                stage.inspShape.textContent = read.error;
                stage.inspWarning.hidden = true;
                return;
            }
            const placement = read.placement;
            const visible = visibleRect(placement);
            const visAspect = aspectOf(visible.w, visible.h);
            const devAspect = viewportAspect(device);
            const delta = aspectDelta(visAspect, devAspect);
            stage.inspShape.textContent =
                "Visible " + fmtNumber(visible.w) + " × " + fmtNumber(visible.h) +
                ". Screen shape " + (devAspect === null ? "-" : fmtAspect(devAspect)) +
                ". Visible shape " + fmtAspect(visAspect) +
                ". " + (delta === null ? "" : fmtDelta(delta) + " off.");
            const mismatch = isAspectMismatch(delta);
            stage.inspWarning.hidden = !mismatch;
            if (mismatch) {
                stage.inspWarningText.textContent =
                    "The visible area is " + fmtAspect(visAspect) +
                    " but the screen is " + fmtAspect(devAspect) +
                    ". The picture will crop.";
                const target = matchHeightFor(placement, device);
                stage.inspMatch.title = target === null
                    ? "Match the visible area to the screen shape"
                    : "Set height to " + fmtNumber(target) + " wall units";
            }
            if (stage.inspMatch) {
                stage.inspMatch.disabled = devAspect === null;
            }
        }

        function matchHeightFor(placement, device) {
            const aspect = viewportAspect(device);
            if (!aspect) return null;
            const visibleW = placement.w - placement.bezel.left - placement.bezel.right;
            if (!(visibleW > 0)) return null;
            return Math.round((visibleW / aspect + placement.bezel.top + placement.bezel.bottom) * 100) / 100;
        }

        function renderSelection() {
            if (!stage.inspector || !stage.inspectorEmpty) return;
            if (!editor.selectedId || !devices.has(editor.selectedId)) {
                editor.selectedId = editor.selectedId && devices.has(editor.selectedId) ? editor.selectedId : null;
                stage.inspectorEmpty.hidden = false;
                stage.inspector.hidden = true;
                updateStageReadout();
                return;
            }
            const device = devices.get(editor.selectedId);
            const saved = savedPlacement(editor.selectedId);
            const placement = saved || defaultPlacementFor(device);
            const editing = stage.inspector.contains(document.activeElement) &&
                document.activeElement &&
                document.activeElement.matches &&
                document.activeElement.matches("input, select");

            stage.inspectorEmpty.hidden = true;
            stage.inspector.hidden = false;
            stage.inspId.textContent = shortId(editor.selectedId);
            const number = Number(device.number);
            stage.inspEyebrow.textContent = Number.isInteger(number) && number > 0
                ? "Tablet #" + number
                : "Tablet";
            stage.inspMeta.textContent =
                (DEVICE_TYPE_NAMES[(device.type || "").toLowerCase()] || device.type || "Tablet") +
                (device.width != null && device.height != null
                    ? ", " + device.width + " × " + device.height + " px"
                    : ", screen size not reported");
            stage.inspStateOnline.textContent = device.online === true ? "Online" : "Offline";
            stage.inspStatePlacement.textContent = saved ? "On the wall" : "Not placed";

            if (!editing) setInspectorFields(placement);
            stage.inspRemove.hidden = !saved;
            stage.inspRemoveBottom.hidden = !saved;
            if (stage.inspRemoveArea) stage.inspRemoveArea.hidden = !saved;
            stage.inspPlace.hidden = !!saved;
            for (const button of document.querySelectorAll("[data-nudge]")) {
                button.disabled = !saved || !wallReady();
            }
            stage.inspSave.textContent = saved ? "Save position" : "Place at these coordinates";
            stage.inspSave.disabled = !wallReady();
            stage.inspPlace.disabled = !wallReady();
            stage.inspRemove.disabled = !saved;
            stage.inspRemoveBottom.disabled = !saved;
            for (const input of [stage.inspX, stage.inspY, stage.inspW, stage.inspH,
                stage.inspBezelTop, stage.inspBezelRight, stage.inspBezelBottom,
                stage.inspBezelLeft]) {
                if (input) input.disabled = !wallReady();
            }

            const color = normalizeColor(device.color);
            stage.inspColor.value = color || "#000000";
            stage.inspColorText.textContent = color || "Not set";
            stage.inspColourSummary.textContent = color || "Not set";
            for (const button of stage.inspPalette.querySelectorAll("[data-insp-color]")) {
                button.setAttribute("aria-pressed", String(button.dataset.inspColor === color));
            }

            stage.inspDetailId.textContent = editor.selectedId;
            stage.inspDetailType.textContent = DEVICE_TYPE_NAMES[(device.type || "").toLowerCase()] || device.type || "-";
            stage.inspDetailScreen.textContent =
                device.width != null && device.height != null
                    ? device.width + " × " + device.height + " px" : "-";
            const caps = deviceCaps(device);
            stage.inspDetailImage.textContent = caps.known
                ? (caps.image ? "Supported" : "Unsupported") : "Unknown";
            stage.inspDetailSeen.textContent = seenLabel(device);
            stage.inspDetailPlacement.textContent = saved
                ? fmtNumber(saved.x) + ", " + fmtNumber(saved.y) + " · " +
                  fmtNumber(saved.w) + " × " + fmtNumber(saved.h)
                : "Not placed";

            stage.inspForget.disabled = device.online === true;
            stage.inspForget.textContent = editor.inspForgetPending ? "Confirm forget" : "Forget tablet";
            stage.inspForgetHint.textContent = device.online === true
                ? "Disconnect the tablet before forgetting it."
                : "Removes the device and its saved position.";
            if (!editor.inspForgetPending) stage.inspForget.dataset.pending = "false";

            updateInspectorShape();
            updateStageReadout();
        }

        function setTilePlacementInputs(deviceId, placement) {
            const tile = tiles.get(deviceId);
            if (!tile) return;
            if (tile.placeInputs.x) tile.placeInputs.x.value = String(placement.x);
            if (tile.placeInputs.y) tile.placeInputs.y.value = String(placement.y);
            if (tile.placeInputs.w) tile.placeInputs.w.value = String(placement.w);
            if (tile.placeInputs.h) tile.placeInputs.h.value = String(placement.h);
            if (tile.placeInputs["bezel-top"]) tile.placeInputs["bezel-top"].value = String(placement.bezel.top);
            if (tile.placeInputs["bezel-right"]) tile.placeInputs["bezel-right"].value = String(placement.bezel.right);
            if (tile.placeInputs["bezel-bottom"]) tile.placeInputs["bezel-bottom"].value = String(placement.bezel.bottom);
            if (tile.placeInputs["bezel-left"]) tile.placeInputs["bezel-left"].value = String(placement.bezel.left);
            tile.placeDirty = false;
        }

        async function commitPlacement(deviceId, placement, label) {
            if (!runtime.wall || !devices.has(deviceId)) return false;
            const before = clonePlacements();
            const rounded = roundPlacement(placement);
            setTilePlacementInputs(deviceId, rounded);
            const ok = await savePlacement(deviceId);
            if (!ok) {
                renderSelection();
                renderWallMap();
                return false;
            }
            const after = clonePlacements();
            pushStageHistory(before, after, label || "Moved " + shortId(deviceId));
            renderSelection();
            renderStageHistory();
            if (isMobile()) setMobileTask("wall");
            return true;
        }

        async function removeSelected() {
            if (!editor.selectedId || !savedPlacement(editor.selectedId) || !runtime.wall) return;
            const id = editor.selectedId;
            const before = clonePlacements();
            const ok = await clearPlacement(id);
            if (!ok) return;
            pushStageHistory(before, clonePlacements(), "Removed " + shortId(id) + " from the wall");
            renderSelection();
            renderStageHistory();
            if (stage.inspPlace && stage.inspPlace.focus) stage.inspPlace.focus();
        }

        function firstFreePlacement(device) {
            if (!wallReady()) return null;
            const p = defaultPlacementFor(device);
            if (p.w > runtime.wall.width || p.h > runtime.wall.height) return null;
            const step = Math.max(10, Math.round(Math.min(p.w, p.h) / 24));
            for (let y = 0; y <= runtime.wall.height - p.h + 0.001; y += step) {
                for (let x = 0; x <= runtime.wall.width - p.w + 0.001; x += step) {
                    const candidate = {
                        x: Math.round(x * 100) / 100,
                        y: Math.round(y * 100) / 100,
                        w: p.w,
                        h: p.h,
                        bezel: { top: 0, right: 0, bottom: 0, left: 0 }
                    };
                    let clash = false;
                    for (const other of Object.values(runtime.wall.placements)) {
                        if (intersects(candidate, other)) {
                            clash = true;
                            break;
                        }
                    }
                    if (!clash) return candidate;
                }
            }
            return null;
        }

        async function placeSelectedFirstFree() {
            if (!editor.selectedId || !devices.has(editor.selectedId)) return;
            if (savedPlacement(editor.selectedId)) {
                selectDevice(editor.selectedId);
                return;
            }
            const placement = firstFreePlacement(devices.get(editor.selectedId));
            if (!placement) {
                stage.inspError.hidden = false;
                stage.inspError.textContent = "No free area is large enough. Drag the tablet onto the wall or enter its position.";
                stage.inspError.focus();
                return;
            }
            const ok = await commitPlacement(editor.selectedId, placement, "Placed " + shortId(editor.selectedId));
            if (ok && stage.inspRemove) stage.inspRemove.focus();
        }

        async function saveInspector() {
            if (!editor.selectedId || !wallReady()) return;
            const read = readInspectorPlacement();
            if (read.error) {
                stage.inspError.hidden = false;
                stage.inspError.textContent = read.error;
                stage.inspError.focus();
                return;
            }
            stage.inspError.hidden = true;
            const placement = read.placement;
            await commitPlacement(
                editor.selectedId,
                placement,
                (savedPlacement(editor.selectedId) ? "Moved " : "Placed ") + shortId(editor.selectedId)
            );
        }

        function matchSelectedShape() {
            if (!editor.selectedId) return;
            const device = devices.get(editor.selectedId);
            const read = readInspectorPlacement();
            if (read.error) return;
            const target = matchHeightFor(read.placement, device);
            if (target === null) return;
            stage.inspH.value = fmtNumber(target);
            updateInspectorShape();
            if (savedPlacement(editor.selectedId)) {
                saveInspector();
            } else {
                stage.inspH.focus();
            }
        }

        function onInspectorDimensionInput(event) {
            if (!stage.inspLock.checked || !editor.selectedId) return;
            const device = devices.get(editor.selectedId);
            const aspect = viewportAspect(device);
            if (!aspect) return;
            const bezel = {
                top: Number(stage.inspBezelTop.value) || 0,
                right: Number(stage.inspBezelRight.value) || 0,
                bottom: Number(stage.inspBezelBottom.value) || 0,
                left: Number(stage.inspBezelLeft.value) || 0
            };
            if (event.target === stage.inspW) {
                const w = Number(stage.inspW.value);
                const visibleW = w - bezel.left - bezel.right;
                if (visibleW > 0) {
                    stage.inspH.value = fmtNumber(visibleW / aspect + bezel.top + bezel.bottom);
                }
            } else if (event.target === stage.inspH) {
                const h = Number(stage.inspH.value);
                const visibleH = h - bezel.top - bezel.bottom;
                if (visibleH > 0) {
                    stage.inspW.value = fmtNumber(visibleH * aspect + bezel.left + bezel.right);
                }
            }
            updateInspectorShape();
        }

        function pendingNudgePlacement() {
            if (!editor.selectedId || !runtime.wall || !runtime.wall.placements[editor.selectedId]) return null;
            if (editor.pendingNudge && editor.pendingNudge.id === editor.selectedId) return clonePlacement(editor.pendingNudge.placement);
            return clonePlacement(runtime.wall.placements[editor.selectedId]);
        }

        function nudgeSelected(dx, dy) {
            const placement = pendingNudgePlacement();
            if (!placement || !runtime.wall) return;
            const step = Number(stage.inspStep && stage.inspStep.value) || 20;
            placement.x = placement.x + dx * step;
            placement.y = placement.y + dy * step;
            placement.x = Math.max(0, Math.min(runtime.wall.width - placement.w, placement.x));
            placement.y = Math.max(0, Math.min(runtime.wall.height - placement.h, placement.y));
            editor.pendingNudge = { id: editor.selectedId, placement: clonePlacement(placement) };
            setInspectorFields(placement, false);
            stage.inspShape.textContent = "Moving " + shortId(editor.selectedId) + " to " + fmtNumber(placement.x) + ", " + fmtNumber(placement.y) + ".";
            updateStageReadout();
            const box = stage.mapFrame && stage.mapFrame.querySelector('.map-pl[data-id="' + cssEscape(editor.selectedId) + '"]');
            if (box) {
                box.style.left = pct(placement.x, runtime.wall.width);
                box.style.top = pct(placement.y, runtime.wall.height);
            }
            if (editor.stageNudgeTimer) clearTimeout(editor.stageNudgeTimer);
            editor.stageNudgeTimer = setTimeout(flushNudge, 320);
        }

        async function flushNudge() {
            if (!editor.pendingNudge) return;
            const pending = editor.pendingNudge;
            editor.pendingNudge = null;
            const before = clonePlacements();
            setTilePlacementInputs(pending.id, pending.placement);
            const ok = await savePlacement(pending.id);
            if (ok) {
                pushStageHistory(before, clonePlacements(), "Moved " + shortId(pending.id));
                if (editor.selectedId === pending.id) renderSelection();
                renderStageHistory();
            } else {
                renderSelection();
            }
        }

        function renderStageHistory() {
            if (!stage.btnUndoStage) return;
            stage.btnUndoStage.disabled = editor.stageUndo.length === 0;
            stage.btnRedoStage.disabled = editor.stageRedo.length === 0;
            if (stage.statusUndo) stage.statusUndo.hidden = editor.stageUndo.length === 0;
        }

        function pushStageHistory(before, after, label) {
            if (samePlacementMap(before, after)) return;
            editor.stageUndo.push({ before: before, after: after, label: label });
            if (editor.stageUndo.length > 40) editor.stageUndo.shift();
            editor.stageRedo = [];
            editor.stageHistoryGeneration = runtime.wall ? runtime.wall.generation : null;
            renderStageHistory();
        }

        async function applyPlacementMap(target) {
            if (!runtime.wall) return false;
            const current = clonePlacements();
            const ids = new Set(Object.keys(current).concat(Object.keys(target || {})));
            try {
                for (const id of ids) {
                    const desired = target ? target[id] : null;
                    const existing = current[id];
                    if (desired && JSON.stringify(desired) === JSON.stringify(existing)) continue;
                    if (desired) {
                        await requestJson("PUT", "/devices/" + encodeURIComponent(id) + "/placement", desired);
                        runtime.wall.placements[id] = clonePlacement(desired);
                    } else if (existing) {
                        await requestJson("DELETE", "/devices/" + encodeURIComponent(id) + "/placement");
                        delete runtime.wall.placements[id];
                    }
                }
                renderWall();
                return true;
            } catch (err) {
                logStatus("Could not restore the placement: " + err.message, "err");
                renderWall();
                return false;
            }
        }

        async function undoStage() {
            if (!editor.stageUndo.length || editor.tileApplying) return;
            const entry = editor.stageUndo.pop();
            const ok = await applyPlacementMap(entry.before);
            if (ok) {
                editor.stageRedo.push(entry);
                logStatus("Undone: " + entry.label + ".", "info");
            } else {
                editor.stageUndo.push(entry);
            }
            renderStageHistory();
            renderSelection();
        }

        async function redoStage() {
            if (!editor.stageRedo.length || editor.tileApplying) return;
            const entry = editor.stageRedo.pop();
            const ok = await applyPlacementMap(entry.after);
            if (ok) {
                editor.stageUndo.push(entry);
                logStatus("Redone: " + entry.label + ".", "info");
            } else {
                editor.stageRedo.push(entry);
            }
            renderStageHistory();
            renderSelection();
        }

        function renderLayoutShortcuts() {
            if (!stage.layoutShortcuts) return;
            stage.layoutShortcuts.textContent = "";
            const items = SNAPSHOTS.layout.items || [];
            if (!SNAPSHOTS.layout.loaded) {
                const p = document.createElement("p");
                p.className = "meta";
                p.textContent = "Open Layout to read saved layouts.";
                stage.layoutShortcuts.appendChild(p);
                return;
            }
            if (items.length === 0) {
                const p = document.createElement("p");
                p.className = "meta";
                p.textContent = "Nothing saved yet.";
                stage.layoutShortcuts.appendChild(p);
                return;
            }
            for (const item of items.slice(0, 4)) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "layout-shortcut";
                const mini = document.createElement("span");
                mini.className = "layout-mini";
                mini.setAttribute("aria-hidden", "true");
                for (let i = 0; i < 4; i += 1) mini.appendChild(document.createElement("i"));
                const info = document.createElement("span");
                const name = document.createElement("strong");
                name.textContent = item.name;
                const meta = document.createElement("small");
                meta.textContent = "Recalls wall size and positions";
                info.appendChild(name);
                info.appendChild(meta);
                button.appendChild(mini);
                button.appendChild(info);
                button.addEventListener("click", function () {
                    setContextMode("layout");
                    if (isMobile()) setMobileTask("saved");
                    beginSnapshotRecall("layout", item.name);
                });
                stage.layoutShortcuts.appendChild(button);
            }
        }

        /* -------------------------- tiling -------------------------- */

        function tileScopeIds(scope) {
            if (scope === "placed") {
                return Object.keys(runtime.wall.placements).filter(function (id) { return devices.has(id); });
            }
            if (scope === "all") {
                return Array.from(devices.keys());
            }
            return Array.from(devices.values())
                .filter(function (device) { return device.online === true; })
                .map(function (device) { return device.device_id; });
        }

        function orderedTileIds(ids, order) {
            if (order === "id") return ids.slice().sort(compareIds);
            const rank = new Map(runtime.tileOrder.map(function (id, i) { return [id, i]; }));
            return ids.slice().sort(function (a, b) {
                const ra = rank.has(a) ? rank.get(a) : 9999;
                const rb = rank.has(b) ? rank.get(b) : 9999;
                return ra === rb ? compareIds(a, b) : ra - rb;
            });
        }

        function fitPlacementInCell(device, cellX, cellY, cellW, cellH, bezel) {
            const b = bezel || { top: 0, right: 0, bottom: 0, left: 0 };
            const aspect = viewportAspect(device);
            if (!aspect) {
                return roundPlacement({ x: cellX, y: cellY, w: cellW, h: cellH, bezel: b });
            }
            const availW = cellW - b.left - b.right;
            const availH = cellH - b.top - b.bottom;
            if (!(availW > 0) || !(availH > 0)) {
                return roundPlacement({ x: cellX, y: cellY, w: Math.max(1, cellW), h: Math.max(1, cellH), bezel: b });
            }
            let visibleW = availW;
            let visibleH = visibleW / aspect;
            if (visibleH > availH) {
                visibleH = availH;
                visibleW = visibleH * aspect;
            }
            const w = visibleW + b.left + b.right;
            const h = visibleH + b.top + b.bottom;
            return roundPlacement({
                x: cellX + (cellW - w) / 2,
                y: cellY + (cellH - h) / 2,
                w: w,
                h: h,
                bezel: b
            });
        }

        function buildTilePlan() {
            const plan = {
                ids: [],
                cells: [],
                placements: {},
                errors: [],
                mismatches: 0,
                cols: 0,
                rows: 0,
                gap: 0,
                cw: 0,
                ch: 0,
                shape: "keep"
            };
            if (!wallReady()) {
                plan.errors.push("The wall size is not known yet.");
                return plan;
            }
            const cols = Math.max(1, Math.round(Number(stage.tileColumns.value) || 0));
            const rows = Math.max(1, Math.round(Number(stage.tileRows.value) || 0));
            const gap = Math.max(0, Number(stage.tileGap.value) || 0);
            const shape = stage.tileShape.value === "fill" ? "fill" : "keep";
            plan.cols = cols;
            plan.rows = rows;
            plan.gap = gap;
            plan.shape = shape;
            plan.cw = (runtime.wall.width - (cols - 1) * gap) / cols;
            plan.ch = (runtime.wall.height - (rows - 1) * gap) / rows;
            if (!(plan.cw > 0) || !(plan.ch > 0)) {
                plan.errors.push("The gap is too large for this wall.");
            }
            plan.ids = orderedTileIds(tileScopeIds(stage.tileScope.value), stage.tileOrder.value);
            if (plan.ids.length === 0) plan.errors.push("No tablets match this scope.");
            if (plan.ids.length > cols * rows) {
                plan.errors.push(plan.ids.length + " tablets do not fit in " + cols + " × " + rows + " cells.");
            }
            return finishTilePlan(plan);
        }

        function finishTilePlan(plan) {
            plan.cells = [];
            plan.placements = {};
            plan.mismatches = 0;
            plan.errors = [];
            if (!wallReady()) {
                plan.errors = ["The wall size is not known yet."];
                return plan;
            }
            if (!(plan.cw > 0) || !(plan.ch > 0)) {
                plan.errors = ["The gap is too large for this wall."];
                return plan;
            }
            const capacity = plan.cols * plan.rows;
            if (plan.ids.length === 0) plan.errors = ["No tablets match this scope."];
            if (plan.ids.length > capacity) {
                plan.errors.push(plan.ids.length + " tablets do not fit in " + plan.cols + " × " + plan.rows + " cells.");
            }
            const limit = Math.min(plan.ids.length, capacity);
            for (let i = 0; i < limit; i += 1) {
                const id = plan.ids[i];
                const device = devices.get(id);
                const col = i % plan.cols;
                const row = Math.floor(i / plan.cols);
                const cellX = col * (plan.cw + plan.gap);
                const cellY = row * (plan.ch + plan.gap);
                const existing = savedPlacement(id);
                const bezel = existing ? clonePlacement(existing.bezel) : { top: 0, right: 0, bottom: 0, left: 0 };
                const placement = plan.shape === "keep"
                    ? fitPlacementInCell(device, cellX, cellY, plan.cw, plan.ch, bezel)
                    : roundPlacement({ x: cellX, y: cellY, w: plan.cw, h: plan.ch, bezel: bezel });
                plan.placements[id] = placement;
                const problem = placementProblem(placement);
                if (problem) plan.errors.push(shortId(id) + ": " + problem + ".");
                if (placementShapeMismatch(placement, device)) plan.mismatches += 1;
                let conflict = false;
                const scope = new Set(plan.ids);
                for (const otherId of Object.keys(runtime.wall.placements)) {
                    if (scope.has(otherId)) continue;
                    if (intersects(placement, runtime.wall.placements[otherId])) {
                        conflict = true;
                        plan.errors.push(
                            "Saved spot " + shortId(otherId) + " intersects " + shortId(id) +
                            ". Move or release it first."
                        );
                    }
                }
                plan.cells.push({ id: id, placement: placement, index: i, conflict: conflict });
            }
            return plan;
        }

        function recomputeTilePreview() {
            if (!editor.tilePreviewPlan) return;
            finishTilePlan(editor.tilePreviewPlan);
            renderTilePreviewOnWall();
            renderTileResult();
        }

        function startTilePreview() {
            if (!wallReady()) {
                stage.tileResult.textContent = "The wall size is not known yet.";
                return;
            }
            editor.tilePreviewPlan = buildTilePlan();
            editor.tilePreviewSelected = [];
            stage.tilePreviewBtn.hidden = true;
            stage.tileCancel.hidden = false;
            stage.tileApply.hidden = false;
            stage.tileWriteNote.hidden = false;
            if (stage.app) stage.app.dataset.previewing = "true";
            renderTilePreviewOnWall();
            renderTileResult();
            setContextMode("layout");
            if (isMobile()) setMobileTask("saved");
            if (stage.tileSection && stage.tileSection.scrollIntoView) {
                stage.tileSection.scrollIntoView({ block: "nearest" });
            }
        }

        function cancelTilePreview() {
            editor.tilePreviewPlan = null;
            editor.tilePreviewSelected = [];
            if (stage.tileLayer) {
                stage.tileLayer.textContent = "";
                stage.tileLayer.hidden = true;
            }
            if (stage.mapFrame) stage.mapFrame.dataset.previewing = "false";
            if (stage.tilePreviewBtn) stage.tilePreviewBtn.hidden = false;
            if (stage.tileCancel) stage.tileCancel.hidden = true;
            if (stage.tileApply) {
                stage.tileApply.hidden = true;
                stage.tileApply.disabled = false;
                stage.tileApply.textContent = "Apply tiling";
            }
            if (stage.tileWriteNote) stage.tileWriteNote.hidden = true;
            if (stage.tileResult) stage.tileResult.textContent = "";
            if (stage.app) stage.app.dataset.previewing = "false";
        }

        function renderTilePreviewOnWall() {
            if (!stage.tileLayer) return;
            stage.tileLayer.textContent = "";
            if (!editor.tilePreviewPlan || !wallReady()) {
                stage.tileLayer.hidden = true;
                if (stage.mapFrame) stage.mapFrame.dataset.previewing = "false";
                return;
            }
            stage.tileLayer.hidden = false;
            if (stage.mapFrame) stage.mapFrame.dataset.previewing = "true";
            for (const cell of editor.tilePreviewPlan.cells) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "tile-cell";
                button.dataset.index = String(cell.index);
                button.style.left = pct(cell.placement.x, runtime.wall.width);
                button.style.top = pct(cell.placement.y, runtime.wall.height);
                button.style.width = pct(cell.placement.w, runtime.wall.width);
                button.style.height = pct(cell.placement.h, runtime.wall.height);
                if (cell.conflict) button.dataset.conflict = "true";
                button.setAttribute("aria-pressed", String(editor.tilePreviewSelected.indexOf(cell.index) !== -1));
                button.setAttribute("aria-label",
                    "Cell " + (cell.index + 1) + ", tablet " + shortId(cell.id));
                const num = document.createElement("span");
                num.className = "cell-number";
                num.textContent = String(cell.index + 1);
                const id = document.createElement("span");
                id.className = "cell-id";
                id.textContent = shortId(cell.id);
                button.appendChild(num);
                button.appendChild(id);
                button.addEventListener("click", function () {
                    toggleTileCell(cell.index);
                });
                stage.tileLayer.appendChild(button);
            }
            renderTileResult();
        }

        function toggleTileCell(index) {
            if (!editor.tilePreviewPlan) return;
            const at = editor.tilePreviewSelected.indexOf(index);
            if (at !== -1) {
                editor.tilePreviewSelected.splice(at, 1);
            } else {
                editor.tilePreviewSelected.push(index);
            }
            if (editor.tilePreviewSelected.length === 2) {
                const a = editor.tilePreviewSelected[0];
                const b = editor.tilePreviewSelected[1];
                if (editor.tilePreviewPlan.ids[a] !== undefined && editor.tilePreviewPlan.ids[b] !== undefined) {
                    const swap = editor.tilePreviewPlan.ids[a];
                    editor.tilePreviewPlan.ids[a] = editor.tilePreviewPlan.ids[b];
                    editor.tilePreviewPlan.ids[b] = swap;
                }
                editor.tilePreviewSelected = [];
                recomputeTilePreview();
                return;
            }
            renderTilePreviewOnWall();
        }

        function renderTileResult() {
            if (!stage.tileResult) return;
            if (!editor.tilePreviewPlan) {
                stage.tileResult.textContent = "";
                stage.tileResult.classList.remove("blocked");
                return;
            }
            const plan = editor.tilePreviewPlan;
            stage.tileApply.disabled = plan.errors.length > 0 || editor.tileApplying;
            stage.tileApply.textContent = editor.tileApplying ? "Applying tiling" : "Apply tiling";
            if (plan.errors.length) {
                stage.tileResult.classList.add("blocked");
                stage.tileResult.textContent = "Apply blocked. " + plan.errors.join(" ");
                return;
            }
            stage.tileResult.classList.remove("blocked");
            stage.tileResult.textContent =
                plan.cells.length + " tablets in " + plan.cols + " × " + plan.rows +
                " cells. " + fmtNumber(plan.cw) + " × " + fmtNumber(plan.ch) +
                " units per cell. " + plan.mismatches +
                (plan.mismatches === 1 ? " screen shape differs." : " screen shapes differ.");
        }

        async function putPlacement(deviceId, placement) {
            await requestJson(
                "PUT",
                "/devices/" + encodeURIComponent(deviceId) + "/placement",
                placement
            );
        }

        async function applyTilePreview() {
            if (!editor.tilePreviewPlan || editor.tilePreviewPlan.errors.length || editor.tileApplying) return;
            const plan = editor.tilePreviewPlan;
            const before = clonePlacements();
            editor.tileApplying = true;
            stage.tileApply.disabled = true;
            stage.tileApply.textContent = "Applying tiling";
            let applied = 0;
            let failure = null;
            for (const cell of plan.cells) {
                try {
                    await putPlacement(cell.id, cell.placement);
                    if (runtime.wall) runtime.wall.placements[cell.id] = clonePlacement(cell.placement);
                    applied += 1;
                    stage.tileResult.textContent =
                        "Applying tiling: " + applied + " of " + plan.cells.length + ".";
                } catch (err) {
                    failure = err;
                    break;
                }
            }
            editor.tileApplying = false;
            if (applied > 0) {
                pushStageHistory(before, clonePlacements(), "Tiled " + applied + (applied === 1 ? " tablet" : " tablets"));
            }
            cancelTilePreview();
            renderWall();
            if (failure) {
                logStatus(
                    "Tiling stopped after " + applied + " of " + plan.cells.length +
                    " tablets: " + failure.message + ". Completed changes can be undone.",
                    "err"
                );
                stage.tileResult.classList.add("blocked");
                stage.tileResult.textContent =
                    "Applied " + applied + " of " + plan.cells.length +
                    ". " + failure.message + ". Completed changes can be undone.";
            } else {
                logStatus("Tiled " + applied + (applied === 1 ? " tablet." : " tablets."), "ok");
            }
            if (isMobile()) setMobileTask("wall");
            renderStageHistory();
        }

        /* ----------------------- stage pointer input ----------------------- */

        function snapAxis(value, size, candidates, threshold) {
            let best = value;
            let bestDistance = threshold + 1;
            for (const candidate of candidates) {
                const distance = Math.abs(value - candidate);
                if (distance < bestDistance) {
                    bestDistance = distance;
                    best = candidate;
                }
            }
            return bestDistance <= threshold ? best : value;
        }

        function snapPlacement(placement, mode, id, disableSnap) {
            if (!runtime.wall) return placement;
            if (disableSnap) {
                placement.x = Math.max(0, Math.min(runtime.wall.width - placement.w, placement.x));
                placement.y = Math.max(0, Math.min(runtime.wall.height - placement.h, placement.y));
                return roundPlacement(placement);
            }
            if (!stage.snapToggle || !stage.snapToggle.checked) return placement;
            const step = Number(stage.snapStep.value) || 0;
            const pxPerX = stage.mapFrame.clientWidth / runtime.wall.width;
            const pxPerY = stage.mapFrame.clientHeight / runtime.wall.height;
            const thresholdX = SNAP_THRESHOLD_PX / (pxPerX || 1);
            const thresholdY = SNAP_THRESHOLD_PX / (pxPerY || 1);
            if (step > 0) {
                placement.x = Math.round(placement.x / step) * step;
                placement.y = Math.round(placement.y / step) * step;
                if (mode === "resize") {
                    placement.w = Math.round(placement.w / step) * step;
                    placement.h = Math.round(placement.h / step) * step;
                }
            }
            const xCandidates = [0, runtime.wall.width - placement.w];
            const yCandidates = [0, runtime.wall.height - placement.h];
            for (const otherId of Object.keys(runtime.wall.placements)) {
                if (otherId === id) continue;
                const other = runtime.wall.placements[otherId];
                xCandidates.push(other.x, other.x + other.w - placement.w,
                    other.x + other.w, other.x - placement.w);
                yCandidates.push(other.y, other.y + other.h - placement.h,
                    other.y + other.h, other.y - placement.h);
            }
            if (mode === "move") {
                placement.x = snapAxis(placement.x, placement.w, xCandidates, thresholdX);
                placement.y = snapAxis(placement.y, placement.h, yCandidates, thresholdY);
            }
            placement.x = Math.max(0, Math.min(runtime.wall.width - placement.w, placement.x));
            placement.y = Math.max(0, Math.min(runtime.wall.height - placement.h, placement.y));
            if (mode === "resize") {
                placement.w = Math.max(10, Math.min(runtime.wall.width - placement.x, placement.w));
                placement.h = Math.max(10, Math.min(runtime.wall.height - placement.y, placement.h));
            }
            return roundPlacement(placement);
        }

        function startStageDrag(event, id, box, mode, corner) {
            if (!runtime.wall || !runtime.wall.placements[id] || event.button !== 0 || isMobile()) return;
            if (mode === "move" && event.target.closest(".map-handle")) return;
            event.preventDefault();
            event.stopPropagation();
            if (editor.stageDrag) cancelStageDrag();
            selectDevice(id, { rebuildMap: false, keepTask: true });
            const frameRect = stage.mapFrame.getBoundingClientRect();
            if (!(frameRect.width > 0) || !(frameRect.height > 0)) return;
            const pxX = frameRect.width / runtime.wall.width;
            const pxY = frameRect.height / runtime.wall.height;
            editor.stageDrag = {
                id: id,
                box: box,
                mode: mode,
                corner: corner || null,
                pointerId: event.pointerId,
                startClientX: event.clientX,
                startClientY: event.clientY,
                start: clonePlacement(runtime.wall.placements[id]),
                placement: clonePlacement(runtime.wall.placements[id]),
                pxX: pxX,
                pxY: pxY,
                moved: false,
                moveHandler: null,
                upHandler: null,
                cancelHandler: null
            };
            box.dataset.dragging = "true";
            box.setPointerCapture(event.pointerId);

            editor.stageDrag.moveHandler = function (moveEvent) {
                if (!editor.stageDrag) return;
                const dx = (moveEvent.clientX - editor.stageDrag.startClientX) / editor.stageDrag.pxX;
                const dy = (moveEvent.clientY - editor.stageDrag.startClientY) / editor.stageDrag.pxY;
                if (Math.abs(dx) > 1 || Math.abs(dy) > 1) editor.stageDrag.moved = true;
                let p = clonePlacement(editor.stageDrag.start);
                if (editor.stageDrag.mode === "move") {
                    p.x = editor.stageDrag.start.x + dx;
                    p.y = editor.stageDrag.start.y + dy;
                } else {
                    const min = 10;
                    if (editor.stageDrag.corner.indexOf("e") !== -1) p.w = Math.max(min, editor.stageDrag.start.w + dx);
                    if (editor.stageDrag.corner.indexOf("s") !== -1) p.h = Math.max(min, editor.stageDrag.start.h + dy);
                    if (editor.stageDrag.corner.indexOf("w") !== -1) {
                        p.w = Math.max(min, editor.stageDrag.start.w - dx);
                        p.x = editor.stageDrag.start.x + (editor.stageDrag.start.w - p.w);
                    }
                    if (editor.stageDrag.corner.indexOf("n") !== -1) {
                        p.h = Math.max(min, editor.stageDrag.start.h - dy);
                        p.y = editor.stageDrag.start.y + (editor.stageDrag.start.h - p.h);
                    }
                }
                p = snapPlacement(p, editor.stageDrag.mode, editor.stageDrag.id, moveEvent.altKey);
                editor.stageDrag.placement = p;
                editor.stageDrag.moved = true;
                box.style.left = pct(p.x, runtime.wall.width);
                box.style.top = pct(p.y, runtime.wall.height);
                box.style.width = pct(p.w, runtime.wall.width);
                box.style.height = pct(p.h, runtime.wall.height);
                setInspectorFields(p, false);
                updateStageReadout();
                stage.stageReadout.textContent =
                    shortId(editor.stageDrag.id) + "  X " + fmtNumber(p.x) + "  Y " + fmtNumber(p.y) +
                    "  W " + fmtNumber(p.w) + "  H " + fmtNumber(p.h);
            };

            editor.stageDrag.upHandler = function (upEvent) {
                const drag = editor.stageDrag;
                if (!drag) return;
                const overRail = document.elementFromPoint(upEvent.clientX, upEvent.clientY);
                const remove = drag.mode === "move" && overRail &&
                    overRail.closest && overRail.closest(".roster");
                endStageDrag(remove);
            };

            editor.stageDrag.cancelHandler = function () {
                cancelStageDrag();
            };

            window.addEventListener("pointermove", editor.stageDrag.moveHandler);
            window.addEventListener("pointerup", editor.stageDrag.upHandler);
            window.addEventListener("pointercancel", editor.stageDrag.cancelHandler);
        }

        function endStageDrag(remove) {
            if (!editor.stageDrag) return;
            const drag = editor.stageDrag;
            window.removeEventListener("pointermove", drag.moveHandler);
            window.removeEventListener("pointerup", drag.upHandler);
            window.removeEventListener("pointercancel", drag.cancelHandler);
            try { drag.box.releasePointerCapture(drag.pointerId); } catch (_err) { /* already released */ }
            drag.box.dataset.dragging = "false";
            editor.stageDrag = null;
            if (!drag.moved) {
                renderWallMap();
                return;
            }
            editor.stageJustDragged = true;
            setTimeout(function () { editor.stageJustDragged = false; }, 0);
            if (remove) {
                removeSelectedFor(drag.id);
                return;
            }
            commitPlacement(
                drag.id,
                drag.placement,
                (drag.mode === "move" ? "Moved " : "Resized ") + shortId(drag.id)
            );
        }

        function cancelStageDrag() {
            if (!editor.stageDrag) return;
            const drag = editor.stageDrag;
            window.removeEventListener("pointermove", drag.moveHandler);
            window.removeEventListener("pointerup", drag.upHandler);
            window.removeEventListener("pointercancel", drag.cancelHandler);
            try { drag.box.releasePointerCapture(drag.pointerId); } catch (_err) { /* already released */ }
            drag.box.dataset.dragging = "false";
            editor.stageDrag = null;
            renderWallMap();
            logStatus("Movement cancelled.", "info");
        }

        async function removeSelectedFor(id) {
            const previous = editor.selectedId;
            editor.selectedId = id;
            await removeSelected();
            if (!devices.has(id)) editor.selectedId = previous && devices.has(previous) ? previous : null;
            renderSelection();
        }

        function dropDeviceOnWall(deviceId, clientX, clientY) {
            if (!wallReady() || !devices.has(deviceId)) return;
            const rect = stage.mapFrame.getBoundingClientRect();
            if (!(rect.width > 0) || !(rect.height > 0)) return;
            const p = defaultPlacementFor(devices.get(deviceId));
            p.x = (clientX - rect.left) / rect.width * runtime.wall.width - p.w / 2;
            p.y = (clientY - rect.top) / rect.height * runtime.wall.height - p.h / 2;
            p.x = Math.max(0, Math.min(runtime.wall.width - p.w, p.x));
            p.y = Math.max(0, Math.min(runtime.wall.height - p.h, p.y));
            p.x = Math.round(p.x);
            p.y = Math.round(p.y);
            selectDevice(deviceId, { keepTask: true });
            commitPlacement(deviceId, p, "Placed " + shortId(deviceId));
        }

        /* -------------------------- boot the stage -------------------------- */

        function buildInspectorPalette() {
            if (!stage.inspPalette) return;
            stage.inspPalette.textContent = "";
            for (const preset of PRESETS) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "swatch";
                button.dataset.inspColor = preset.color;
                button.style.background = preset.color;
                button.title = preset.name + " " + preset.color;
                button.setAttribute("aria-label", preset.name + " " + preset.color);
                button.setAttribute("aria-pressed", "false");
                button.addEventListener("click", function () {
                    if (!editor.selectedId) return;
                    setDeviceColor(editor.selectedId, preset.color).then(renderSelection);
                });
                stage.inspPalette.appendChild(button);
            }
        }

        function fillStepOptions(select) {
            if (!select) return;
            select.textContent = "";
            for (const value of [1, 10, 20, 50, 100]) {
                const option = document.createElement("option");
                option.value = String(value);
                option.textContent = String(value);
                if (value === 20) option.selected = true;
                select.appendChild(option);
            }
        }

        function bindStageEvents() {
            for (const tab of stage.contextTabs) {
                tab.addEventListener("click", function () {
                    setContextMode(tab.dataset.contextTab);
                });
            }
            for (const tab of stage.mobileTabs) {
                tab.addEventListener("click", function () {
                    setMobileTask(tab.dataset.task);
                });
            }
            const placementForm = document.getElementById("placement-form");
            if (placementForm) {
                placementForm.addEventListener("submit", function (event) {
                    event.preventDefault();
                    saveInspector();
                });
            }
            if (stage.inspRemove) stage.inspRemove.addEventListener("click", removeSelected);
            if (stage.inspRemoveBottom) stage.inspRemoveBottom.addEventListener("click", removeSelected);
            if (stage.inspPlace) stage.inspPlace.addEventListener("click", placeSelectedFirstFree);
            if (stage.inspMatch) stage.inspMatch.addEventListener("click", matchSelectedShape);
            if (stage.inspW) stage.inspW.addEventListener("input", onInspectorDimensionInput);
            if (stage.inspH) stage.inspH.addEventListener("input", onInspectorDimensionInput);
            for (const input of [stage.inspBezelTop, stage.inspBezelRight,
                stage.inspBezelBottom, stage.inspBezelLeft]) {
                if (input) input.addEventListener("input", updateInspectorShape);
            }
            if (stage.inspector) {
                stage.inspector.addEventListener("input", function () {
                    if (stage.inspError) stage.inspError.hidden = true;
                });
            }
            if (stage.inspColor) {
                stage.inspColor.addEventListener("change", function () {
                    if (!editor.selectedId) return;
                    setDeviceColor(editor.selectedId, stage.inspColor.value).then(renderSelection);
                });
            }
            if (stage.inspForget) {
                stage.inspForget.addEventListener("click", async function () {
                    if (!editor.selectedId) return;
                    if (editor.inspForgetPending) {
                        const id = editor.selectedId;
                        editor.inspForgetPending = false;
                        if (editor.inspForgetTimer) clearTimeout(editor.inspForgetTimer);
                        await forgetDevice(id);
                        if (!devices.has(id)) editor.selectedId = null;
                        renderSelection();
                        return;
                    }
                    editor.inspForgetPending = true;
                    stage.inspForget.textContent = "Confirm forget";
                    stage.inspForget.dataset.pending = "true";
                    if (editor.inspForgetTimer) clearTimeout(editor.inspForgetTimer);
                    editor.inspForgetTimer = setTimeout(function () {
                        editor.inspForgetPending = false;
                        renderSelection();
                    }, 4000);
                });
            }
            for (const button of document.querySelectorAll("[data-nudge]")) {
                button.addEventListener("click", function () {
                    const parts = (button.dataset.nudge || "").split(",");
                    nudgeSelected(Number(parts[0]) || 0, Number(parts[1]) || 0);
                });
            }
            const syncSteps = function (value) {
                if (stage.inspStep && stage.inspStep.value !== value) stage.inspStep.value = value;
                if (stage.inspStepDesktop && stage.inspStepDesktop.value !== value) stage.inspStepDesktop.value = value;
            };
            if (stage.inspStep) stage.inspStep.addEventListener("change", function () { syncSteps(stage.inspStep.value); });
            if (stage.inspStepDesktop) stage.inspStepDesktop.addEventListener("change", function () { syncSteps(stage.inspStepDesktop.value); });
            if (stage.btnUndoStage) stage.btnUndoStage.addEventListener("click", undoStage);
            if (stage.btnRedoStage) stage.btnRedoStage.addEventListener("click", redoStage);
            if (stage.statusUndo) stage.statusUndo.addEventListener("click", undoStage);
            if (stage.btnChangeContent) {
                stage.btnChangeContent.addEventListener("click", function () {
                    setContextMode("content");
                    if (isMobile()) setMobileTask("content");
                });
            }
            if (stage.btnManageLayouts) {
                stage.btnManageLayouts.addEventListener("click", function () {
                    setContextMode("layout");
                    if (isMobile()) setMobileTask("saved");
                });
            }
            if (stage.btnReviewChecks) {
                stage.btnReviewChecks.addEventListener("click", function () {
                    if (!el.alerts) return;
                    el.alerts.hidden = false;
                    if (el.alerts.scrollIntoView) el.alerts.scrollIntoView({ block: "nearest" });
                    const first = el.alerts.querySelector(".alert:not([hidden])");
                    if (first && first.focus) first.focus();
                });
            }
            if (stage.btnTile) {
                stage.btnTile.addEventListener("click", function () {
                    setContextMode("layout");
                    if (isMobile()) setMobileTask("saved");
                    startTilePreview();
                });
            }
            if (stage.tilePreviewBtn) stage.tilePreviewBtn.addEventListener("click", startTilePreview);
            if (stage.tileCancel) stage.tileCancel.addEventListener("click", cancelTilePreview);
            if (stage.tileApply) stage.tileApply.addEventListener("click", applyTilePreview);
            for (const field of [stage.tileColumns, stage.tileRows, stage.tileGap, stage.tileOrder, stage.tileScope]) {
                if (!field) continue;
                field.addEventListener("change", function () {
                    if (editor.tilePreviewPlan) startTilePreview();
                });
            }
            if (stage.tileShape) {
                stage.tileShape.addEventListener("change", function () {
                    if (stage.tileHelp) {
                        stage.tileHelp.textContent = stage.tileShape.value === "keep"
                            ? "Each footprint fits inside its cell. Visible shape matches its screen."
                            : "Each footprint fills its cell. Bezels stay fixed; shapes may differ.";
                    }
                    if (editor.tilePreviewPlan) startTilePreview();
                });
            }
            if (stage.btnZoomWall) {
                stage.btnZoomWall.addEventListener("click", function () {
                    if (!stage.wallScroll) return;
                    const zoomed = stage.wallScroll.classList.toggle("zoomed");
                    stage.btnZoomWall.textContent = zoomed ? "Fit" : "2x zoom";
                    stage.btnZoomWall.setAttribute("aria-pressed", String(zoomed));
                    setTimeout(renderWallMap, 0);
                });
            }
            if (stage.btnKeys && stage.keysDialog) {
                stage.btnKeys.addEventListener("click", function () {
                    if (typeof stage.keysDialog.showModal === "function") stage.keysDialog.showModal();
                    else stage.keysDialog.hidden = false;
                });
            }
            if (stage.keysClose) {
                stage.keysClose.addEventListener("click", function () {
                    if (stage.keysDialog) stage.keysDialog.close();
                });
            }
            if (stage.mapFrame) {
                stage.mapFrame.addEventListener("dragover", function (event) {
                    event.preventDefault();
                    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
                    stage.mapFrame.classList.add("drop-ready");
                });
                stage.mapFrame.addEventListener("dragleave", function () {
                    stage.mapFrame.classList.remove("drop-ready");
                });
                stage.mapFrame.addEventListener("drop", function (event) {
                    event.preventDefault();
                    stage.mapFrame.classList.remove("drop-ready");
                    const id = event.dataTransfer ? event.dataTransfer.getData("text/plain") : "";
                    if (id) dropDeviceOnWall(id, event.clientX, event.clientY);
                });
            }
            document.addEventListener("keydown", function (event) {
                const target = event.target;
                const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
                const editing = tag === "input" || tag === "textarea" || tag === "select" ||
                    (target && target.isContentEditable);
                if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && !editing) {
                    event.preventDefault();
                    if (event.shiftKey) redoStage();
                    else undoStage();
                    return;
                }
                if (event.key === "Escape") {
                    if (stage.keysDialog && stage.keysDialog.open) {
                        stage.keysDialog.close();
                        return;
                    }
                    if (editor.tilePreviewPlan) {
                        cancelTilePreview();
                        return;
                    }
                    if (editor.stageDrag) {
                        cancelStageDrag();
                        return;
                    }
                }
                if (!editing && (event.key === "Delete" || event.key === "Backspace") && editor.selectedId) {
                    event.preventDefault();
                    removeSelected();
                }
            });
            window.addEventListener("resize", function () {
                applyPaneVisibility();
            });
        }

        function initStage() {
            if (!stage.app) return;
            buildInspectorPalette();
            fillStepOptions(stage.inspStep);
            fillStepOptions(stage.inspStepDesktop);
            bindStageEvents();
            stage.app.dataset.task = "wall";
            stage.context.dataset.mode = "tablet";
            applyPaneVisibility();
            renderSelection();
            renderStageHistory();
            renderLayoutShortcuts();
        }

        return { cancelStageDrag, initStage, nudgeSelected, removeSelected, renderLayoutShortcuts, renderSelection, renderStageHistory, renderTilePreviewOnWall, selectDevice, startStageDrag };
    }
};
