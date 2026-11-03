"use strict";
(function (root) {
    const model = typeof module !== "undefined" && module.exports ? require("./operator-state.js") : root.OperatorState;
    function command({ kind, ids, rows, columns, gap, padding, sizing, orientation, holes, releases, sizes, revisions, angles }) {
        if (!["logical", "physical"].includes(kind)) throw new Error("Choose logical units or measured millimetres.");
        if (![rows, columns].every(n => Number.isInteger(n) && n > 0 && n <= 64)) throw new Error("Rows and columns must be whole numbers from 1 to 64.");
        if (!ids.length || new Set(ids).size !== ids.length) throw new Error("Select at least one tablet, with no duplicate identities.");
        if (ids.length > rows * columns || (!holes && ids.length !== rows * columns)) throw new Error("Select exactly " + (rows * columns) + " tablets or explicitly allow empty trailing cells.");
        if (![gap, padding].every(n => Number.isFinite(n) && n >= 0 && (kind === "physical" || Number.isInteger(n)))) throw new Error("Gap and padding must be nonnegative" + (kind === "logical" ? " whole logical units." : " millimetres."));
        if (!["fixed", "tablets"].includes(sizing) || !["preserve", "auto", "portrait", "landscape"].includes(orientation)) throw new Error("Choose a supported sizing and orientation policy.");
        const result = { kind, device_ids: ids.slice(), rows, columns, gap, padding, sizing, orientation,
            allow_empty_cells: holes, release_unselected: releases.slice() };
        if (kind === "logical") {
            result.logical_sizes = {};
            ids.forEach(id => {
                const size = sizes[id];
                if (!size || ![size.w, size.h].every(n => Number.isInteger(n) && n > 0)) throw new Error("Enter positive whole logical sizes for every selected tablet, including offline reservations.");
                result.logical_sizes[id] = { w: size.w, h: size.h };
            });
        } else {
            result.physical_revisions = {}; result.mount_angles = {};
            ids.forEach(id => {
                if (!revisions[id] || ![revisions[id].profile_revision, revisions[id].calibration_revision].every(n => Number.isInteger(n) && n > 0)) throw new Error("Confirm a model or save measurements for every selected tablet before a measured preview.");
                result.physical_revisions[id] = revisions[id];
                if (angles[id] !== "" && angles[id] !== undefined) {
                    const angle = Number(angles[id]);
                    if (![0, 90, 180, 270].includes(angle)) throw new Error("Grid mount angles must be 0, 90, 180 or 270 degrees.");
                    result.mount_angles[id] = angle;
                }
            });
        }
        return result;
    }
    function create({ state, api, labelFor, validPair, profileFor, calibrationFor, ingestConfig, renderStage, syncDraftUi, isDirty, announce, showConflict }) {
        const $ = id => document.getElementById(id);
        let order = [], selected = new Set(), sizes = {}, angles = {}, rows = new Map(), busy = false, initialized = false;
        let previewCommand = null, inputVersion = 0;
        const text = value => { $("grid-message").textContent = value; };
        function invalidate() {
            inputVersion += 1;
            state.gridPreview = null; previewCommand = null;
            $("grid-cancel").disabled = true;
            syncDraftUi(); renderStage();
        }
        function releases() { return Object.keys(model.entries(state.base)).filter(id => !selected.has(id)); }
        function renderReleases() {
            const box = $("grid-releases");
            box.replaceChildren();
            releases().forEach(id => {
                const label = document.createElement("label"); label.className = "check-label";
                const check = document.createElement("input"); check.type = "checkbox"; check.dataset.release = id;
                label.append(check, document.createTextNode(" Release " + labelFor(id) + " from the active arrangement"));
                box.append(label);
            });
        }
        function move(id, delta) {
            const index = order.indexOf(id), next = index + delta;
            if (next < 0 || next >= order.length) return;
            [order[index], order[next]] = [order[next], order[index]];
            order.forEach(key => $("grid-order").append(rows.get(key).item));
            invalidate(); updateButtons();
            const row = rows.get(id);
            const target = delta < 0 ? row.earlier : row.later;
            const alternate = delta < 0 ? row.later : row.earlier;
            (target.disabled ? alternate : target).focus();
            announce(labelFor(id) + " moved to position " + (next + 1) + ".");
        }
        function updateButtons() {
            order.forEach((id, index) => {
                const row = rows.get(id);
                row.earlier.disabled = index === 0; row.later.disabled = index === order.length - 1;
                row.label.textContent = labelFor(id) + (state.roster[id] && state.roster[id].online ? " · online" : " · offline reservation");
                row.logical.hidden = $("grid-kind").value !== "logical";
                row.mount.hidden = $("grid-kind").value !== "physical";
                row.pins.hidden = row.mount.hidden;
                const slot = state.gridPreview && state.gridPreview.layout.slots && state.gridPreview.layout.slots[id]
                    || state.base.slots && state.base.slots[id];
                const pair = validPair(id);
                const profile = slot ? profileFor(id, slot.profile_revision) : pair && pair.profile;
                const calibration = slot ? calibrationFor(id, slot.calibration_revision) : pair && pair.calibration;
                row.pins.textContent = profile && calibration ? "Profile r" + profile.revision + ", calibration r" + calibration.revision
                    + " · active " + profile.active_width_mm + " × " + profile.active_height_mm + " mm · "
                    + (/model|approximate/i.test(profile.provenance + " " + calibration.method) ? "approximate " : "")
                    + "±" + calibration.uncertainty_mm + " mm" : "Pinned physical measurements are unavailable. Confirm a model or save measurements before previewing.";
            });
            $("grid-kind-note").textContent = $("grid-kind").value === "logical" ? "Sizes are logical units. No millimetre conversion is applied."
                : "Measured layouts require pinned profiles and calibrations. Logical dimensions are never reused as millimetres. A cross-kind Apply requests a named safety copy.";
        }
        function render() {
            if (!state.base) return;
            if (!initialized) { $("grid-kind").value = state.layoutKind; initialized = true; }
            const ids = new Set([...Object.keys(state.roster), ...Object.keys(model.entries(state.base))]);
            const additions = [...ids].filter(id => !rows.has(id)).sort((a, b) => model.compareIds(state.roster, state.deviceLabels || {}, a, b));
            additions.forEach(id => {
                order.push(id);
                if (model.entries(state.base)[id] || state.roster[id] && state.roster[id].online) selected.add(id);
                const saved = state.base.placements && state.base.placements[id];
                const viewport = state.roster[id] && state.roster[id].viewport;
                sizes[id] = saved ? { w: saved.w, h: saved.h } : { w: viewport ? Math.max(1, Math.round(100 * viewport.width / viewport.height)) : 100, h: 100 };
                const slot = state.base.slots && state.base.slots[id]; angles[id] = "";
                const item = document.createElement("li");
                const choice = document.createElement("label"); choice.className = "check-label";
                const check = document.createElement("input"); check.type = "checkbox"; check.checked = selected.has(id);
                const label = document.createElement("span"); choice.append(check, label); item.append(choice);
                check.addEventListener("change", () => { if (check.checked) selected.add(id); else selected.delete(id); invalidate(); renderReleases(); });
                const logical = document.createElement("div"); logical.className = "operator-fields";
                for (const [key, name] of [["w", "Width (logical units)"], ["h", "Height (logical units)"]]) {
                    const wrap = document.createElement("label"); wrap.className = "field"; wrap.textContent = name;
                    const input = document.createElement("input"); input.className = "inp"; input.type = "number"; input.min = "1"; input.step = "1"; input.value = sizes[id][key];
                    input.setAttribute("aria-label", name + " for " + labelFor(id));
                    input.addEventListener("input", () => { sizes[id][key] = input.value === "" ? NaN : Number(input.value); invalidate(); });
                    wrap.append(input); logical.append(wrap);
                }
                item.append(logical);
                const pins = document.createElement("p"); pins.className = "hint"; item.append(pins);
                const mount = document.createElement("label"); mount.className = "field"; mount.textContent = "Explicit mount angle";
                const angle = document.createElement("select"); angle.className = "inp"; angle.setAttribute("aria-label", "Mount angle for " + labelFor(id));
                [["", "Use orientation choice (preserve needs stored angle)"], ["0", "0°"], ["90", "90°"], ["180", "180°"], ["270", "270°"]].forEach(([value, name]) => angle.add(new Option(name, value)));
                angle.value = angles[id]; angle.addEventListener("change", () => { angles[id] = angle.value; invalidate(); }); mount.append(angle); item.append(mount);
                const actions = document.createElement("div"); actions.className = "operator-actions";
                const earlier = document.createElement("button"), later = document.createElement("button");
                for (const [button, delta, name] of [[earlier, -1, "Move earlier"], [later, 1, "Move later"]]) {
                    button.type = "button"; button.className = "btn btn-sm"; button.textContent = name; button.setAttribute("aria-label", name + ", " + labelFor(id)); button.addEventListener("click", () => move(id, delta)); actions.append(button);
                }
                item.append(actions); rows.set(id, { item, label, check, logical, mount, pins, earlier, later }); $("grid-order").append(item);
            });
            order.filter(id => !ids.has(id)).forEach(id => { rows.get(id).item.remove(); rows.delete(id); selected.delete(id); });
            order = order.filter(id => ids.has(id));
            if (additions.length) renderReleases();
            updateButtons();
        }
        async function preview() {
            if (busy || !state.base) return;
            invalidate();
            if (isDirty()) { text("Apply or cancel the manual draft before building a grid."); return; }
            const released = releases();
            if (released.some(id => !Array.from($("grid-releases").querySelectorAll("input")).some(input => input.dataset.release === id && input.checked))) {
                text("Explicitly acknowledge every released active tablet, including offline reservations."); return;
            }
            try {
                const kind = $("grid-kind").value, ids = order.filter(id => selected.has(id));
                if ($("grid-orientation").value === "auto" && ids.some(id => !state.roster[id] || !state.roster[id].online)) throw new Error("Auto orientation needs a fresh online viewport. Choose Preserve for offline reservations.");
                const revisions = {};
                ids.forEach(id => { const slot = state.base.slots && state.base.slots[id], pair = validPair(id);
                    if (slot) revisions[id] = { profile_revision: slot.profile_revision, calibration_revision: slot.calibration_revision };
                    else if (pair) revisions[id] = { profile_revision: pair.profile.revision, calibration_revision: pair.calibration.revision };
                });
                const number = id => $(id).value.trim() === "" ? NaN : Number($(id).value);
                previewCommand = command({ kind, ids, rows: number("grid-rows"), columns: number("grid-columns"), gap: number("grid-gap"), padding: number("grid-padding"), sizing: $("grid-sizing").value,
                    orientation: $("grid-orientation").value, holes: $("grid-holes").checked, releases: released, sizes, revisions, angles });
                busy = true; $("grid-preview").disabled = true;
                const etag = state.etag, version = inputVersion;
                const result = await api("POST", "/api/v3/grid/preview", previewCommand, { ifMatch: etag });
                if (version !== inputVersion || !result.layout || !result.guards || result.base_etag !== etag || state.etag !== etag || state.etagState !== "current") throw new Error("Preview inputs changed. Reload and preview again.");
                state.gridPreview = result;
                previewCommand = Object.assign({}, previewCommand, { guards: result.guards });
                const wall = model.bounds(result.layout);
                text("Preview only. " + result.order.length + " tablets · " + previewCommand.rows + " rows × " + previewCommand.columns
                    + " columns · wall " + wall.width + " × " + wall.height + (kind === "physical" ? " mm" : " logical units")
                    + " · extra gap " + previewCommand.gap + " · orientation " + previewCommand.orientation + ". Order " + result.order.map(labelFor).join(" / ") + ". " + (result.warnings || []).join(" ")
                    + (result.previous_kind !== kind ? " Apply will request a named safety copy of the current arrangement." : "")
                    + " Use Apply layout above the stage to commit once.");
                $("grid-cancel").disabled = false;
                updateButtons(); syncDraftUi(); renderStage();
            } catch (error) { text("Cannot preview arrangement. " + error.message + " The committed wall is unchanged."); }
            finally { busy = false; $("grid-preview").disabled = false; }
        }
        async function apply() {
            if (!state.gridPreview || !previewCommand || busy) return;
            const preview = state.gridPreview;
            if (preview.previous_kind !== preview.layout.kind && !window.confirm("Replace the " + preview.previous_kind + " arrangement with " + preview.layout.kind + "? The server must save a named safety copy. Content stays unchanged.")) return;
            busy = true;
            try {
                const result = await api("POST", "/api/v3/grid", previewCommand, { ifMatch: preview.base_etag });
                state.gridPreview = null; previewCommand = null;
                ingestConfig(result); $("grid-cancel").disabled = true;
                text("Arrangement applied once." + (result.previous_layout_saved ? " Previous arrangement saved as “" + result.previous_layout_saved + "”." : "")); announce("Arrangement applied.");
            } catch (error) { if (error.status === 412) showConflict("The grid preview is stale. Your preview is retained. Reload and preview again."); text("Apply failed. " + error.message + " The preview is retained."); }
            finally { busy = false; syncDraftUi(); }
        }
        for (const id of ["grid-kind", "grid-rows", "grid-columns", "grid-gap", "grid-padding", "grid-orientation", "grid-sizing", "grid-holes"]) $(id).addEventListener("change", () => { invalidate(); updateButtons(); });
        for (const [id, r, c] of [["grid-2x2", 2, 2], ["grid-1x4", 1, 4]]) $(id).addEventListener("click", () => { $("grid-rows").value = r; $("grid-columns").value = c; invalidate(); text(r + " rows × " + c + " columns selected. Review tablet order and Preview arrangement."); });
        $("grid-preview").addEventListener("click", preview);
        $("grid-cancel").addEventListener("click", () => { invalidate(); text("Preview cancelled. The committed wall is unchanged."); });
        return { render, apply, cancel: invalidate };
    }
    const api = { command, create };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorGrid = api;
}(typeof window !== "undefined" ? window : globalThis));
