"use strict";
(function (root) {
    const model = typeof module !== "undefined" && module.exports ? require("./operator-state.js") : root.OperatorState;
    function membership() {
        const members = {};
        let frozen = false;
        return {
            observe(roster, layout, { refreshSaved = false } = {}) {
                const entries = model.entries(layout);
                for (const id of new Set([...Object.keys(roster), ...Object.keys(entries)])) {
                    const device = roster[id] || {}, saved = layout.placements && layout.placements[id];
                    const member = members[id] ||= { included: !!entries[id], membershipSource: "automatic",
                        size: saved ? { w: saved.w, h: saved.h } : { w: 100, h: 100 }, sizeSource: saved ? "saved" : "fallback" };
                    if (!frozen && member.membershipSource === "automatic" && device.online) member.included = true;
                    if (refreshSaved && saved && member.sizeSource === "saved") member.size = { w: saved.w, h: saved.h };
                    const viewport = device.viewport;
                    if (!frozen && ["fallback", "viewport"].includes(member.sizeSource) && device.online
                            && viewport && viewport.width > 0 && viewport.height > 0) {
                        member.size = { w: Math.max(1, Math.round(100 * viewport.width / viewport.height)), h: 100 };
                        member.sizeSource = "viewport";
                    }
                }
            },
            commit(layout) {
                for (const [id, p] of Object.entries(layout.placements || {})) if (members[id]) {
                    members[id].size = { w: p.w, h: p.h }; members[id].sizeSource = "saved";
                }
            },
            include(id, included) { frozen = true; members[id].included = included; members[id].membershipSource = "operator"; },
            size(id, size) { members[id].size = { ...size }; members[id].sizeSource = "operator"; },
            freeze() { frozen = true; },
            view() { return model.clone(members); }
        };
    }
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
    function create({ state, api, labelFor, validPair, profileFor, calibrationFor, ingestConfig, renderStage, syncDraftUi, isDirty, announce, showConflict, modelBusy = () => false, modelReview = () => null, identifyTablet = () => {}, canIdentify = () => false }) {
        const $ = id => document.getElementById(id);
        let order = [], selected = new Set(), sizes = {}, angles = {}, storedAngles = {}, rows = new Map(), busy = false, initialized = false;
        let previewCommand = null, inputVersion = 0, releaseRows = new Map();
        let members = membership(), edited = false, baseEtag = null;
        const text = value => { $("grid-message").textContent = order.reduce((line, id) => line.split(id).join(labelFor(id)), value); };
        function invalidate() {
            if (!edited) baseEtag = state.etag;
            edited = true;
            state.viewLive = false;
            inputVersion += 1;
            state.gridPreview = null; previewCommand = null;
            text("");
            syncDraftUi(); updateButtons(); renderStage();
        }
        const presets = [["grid-2x2", true], ["grid-1x4", false]];
        function preset(twoRows) {
            const count = selected.size, r = twoRows && count > 1 ? 2 : 1, c = Math.max(1, Math.ceil(count / r));
            return { r, c, holes: r * c > count, label: r + " × " + c };
        }
        function releases() { return Object.keys(model.entries(state.base)).filter(id => !selected.has(id)); }
        function move(id, delta) {
            members.freeze();
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
            const manualDirty = !state.gridPreview && isDirty();
            for (const id of ["grid-kind", "grid-rows", "grid-columns", "grid-gap", "grid-padding", "grid-orientation", "grid-sizing", "grid-holes", "grid-2x2", "grid-1x4", "grid-common-mount", "group-confirm"]) if ($(id)) $(id).disabled = manualDirty || state.busy;
            if ($("group-confirm")) $("group-confirm").disabled ||= modelBusy();
            order.forEach((id, index) => {
                const row = rows.get(id);
                row.earlier.disabled = index === 0 || manualDirty; row.later.disabled = index === order.length - 1 || manualDirty;
                row.check.disabled = manualDirty; row.angle.disabled = manualDirty;
                row.identify.disabled = !canIdentify(id);
                if (row.logical.querySelectorAll) row.logical.querySelectorAll("input").forEach(input => { input.disabled = manualDirty; });
                row.label.textContent = labelFor(id) + (state.roster[id] && state.roster[id].online ? " · online" : " · offline reservation");
                row.logical.hidden = $("grid-kind").value !== "logical";
                row.mount.hidden = $("grid-kind").value !== "physical";
                row.pins.hidden = row.mount.hidden;
                row.item.className = "tablet-order-row";
                const slot = state.gridPreview && state.gridPreview.layout.slots && state.gridPreview.layout.slots[id]
                    || state.base.slots && state.base.slots[id];
                const pair = validPair(id);
                const profile = slot ? profileFor(id, slot.profile_revision) : pair && pair.profile;
                const calibration = slot ? calibrationFor(id, slot.calibration_revision) : pair && pair.calibration;
                row.pins.textContent = profile && calibration ? "Active screen " + Number(profile.active_width_mm.toFixed(1)) + " × " + Number(profile.active_height_mm.toFixed(1)) + " mm · "
                    + (/model|approximate/i.test(profile.provenance + " " + calibration.method) ? "approximate " : "")
                    + "±" + Number(calibration.uncertainty_mm.toFixed(1)) + " mm" : "Pinned physical measurements are unavailable. Confirm a model or save measurements before previewing.";
            });
            for (const [id, twoRows] of presets) {
                const { label, holes } = preset(twoRows);
                $(id).textContent = label; $(id).setAttribute("aria-label", label + " grid" + (holes ? ", one empty cell" : ""));
            }
            const stale = !!baseEtag && baseEtag !== state.etag;
            $("grid-preview").disabled = busy || !!state.gridPreview && !stale;
            $("grid-preview").hidden = !!state.gridPreview && !stale;
            $("grid-rebuild").hidden = !edited || !stale;
            const ids = order.filter(id => selected.has(id));
            const physical = $("grid-kind").value === "physical";
            const required = releases().length || modelReview() || physical && ids.some(id => {
                const pair = validPair(id), slot = state.base.slots?.[id];
                return !pair || !slot && angles[id] === "" && $("grid-common-mount").value === ""
                    || slot && pair && (slot.profile_revision !== pair.profile.revision || slot.calibration_revision !== pair.calibration.revision);
            });
            const names = ids.map(labelFor);
            const subjects = names.every(name => /^Tablet \d+$/.test(name)) ? "Tablets " + names.map(name => name.slice(7)).join(", ") : names.join(", ");
            $("arrange-membership-summary").textContent = !ids.length ? "Choose tablets"
                : required ? subjects + " · review tablet sizes and mounting"
                    : "Tablet order and measurements";
            if (required) $("arrange-membership").open = true;
            $("arrange-membership").dataset.required = String(!!required);
        }
        function render() {
            if (!state.base) return;
            if (!initialized) { $("grid-kind").value = state.layoutKind; initialized = true; }
            const ids = new Set([...Object.keys(state.roster), ...Object.keys(model.entries(state.base))]);
            members.observe(state.roster, state.base, { refreshSaved: !edited });
            const defaults = members.view();
            const additions = [...ids].filter(id => !rows.has(id)).sort((a, b) => model.compareIds(state.roster, state.deviceLabels || {}, a, b));
            additions.forEach(id => {
                order.push(id);
                if (defaults[id].included) selected.add(id);
                sizes[id] = defaults[id].size;
                const slot = state.base.slots && state.base.slots[id]; angles[id] = ""; storedAngles[id] = slot ? String(slot.mount_angle) : "";
                const item = document.createElement("li");
                const choice = document.createElement("label"); choice.className = "check-label";
                const check = document.createElement("input"); check.type = "checkbox"; check.checked = selected.has(id);
                const label = document.createElement("span"); choice.append(check, label); item.append(choice);
                check.addEventListener("change", () => { members.include(id, check.checked); if (check.checked) selected.add(id); else selected.delete(id); invalidate(); render(); });
                const logical = document.createElement("details"); logical.className = "tablet-size-details";
                const sizeSummary = document.createElement("summary"); logical.append(sizeSummary);
                for (const [key, name] of [["w", "Width (relative units)"], ["h", "Height (relative units)"]]) {
                    const wrap = document.createElement("label"); wrap.className = "field"; wrap.textContent = name;
                    const input = document.createElement("input"); input.className = "inp"; input.type = "number"; input.min = "1"; input.step = "1"; input.value = sizes[id][key];
                    input.setAttribute("aria-label", name + " for " + labelFor(id));
                    input.dataset.field = key;
                    input.addEventListener("input", () => { sizes[id][key] = input.value === "" ? NaN : Number(input.value); members.size(id, sizes[id]); invalidate(); });
                    wrap.append(input); logical.append(wrap);
                }
                item.append(logical);
                const pins = document.createElement("p"); pins.className = "hint"; item.append(pins);
                const mount = document.createElement("label"); mount.className = "field"; mount.textContent = "Explicit mount angle";
                const angle = document.createElement("select"); angle.className = "inp"; angle.setAttribute("aria-label", "Mount angle for " + labelFor(id));
                [["", "Use explicitly declared common mount"], ["0", "0°"], ["90", "90°"], ["180", "180°"], ["270", "270°"]].forEach(([value, name]) => angle.add(new Option(name, value)));
                angle.value = angles[id]; angle.addEventListener("change", () => { angles[id] = angle.value; invalidate(); }); mount.append(angle); item.append(mount);
                const actions = document.createElement("div"); actions.className = "operator-actions";
                const earlier = document.createElement("button"), later = document.createElement("button");
                const include = document.createElement("button"); include.type = "button"; include.className = "btn btn-sm"; include.textContent = "Include";
                include.setAttribute("aria-label", "Include " + labelFor(id));
                include.addEventListener("click", () => { members.include(id, true); selected.add(id); invalidate(); render(); }); actions.append(include);
                for (const [button, delta, name] of [[earlier, -1, "Move earlier"], [later, 1, "Move later"]]) {
                    button.type = "button"; button.className = "btn btn-sm"; button.textContent = name; button.setAttribute("aria-label", name + ", " + labelFor(id)); button.addEventListener("click", () => move(id, delta)); actions.append(button);
                }
                const identify = document.createElement("button"); identify.type = "button"; identify.className = "btn btn-sm"; identify.textContent = "Identify";
                identify.setAttribute("aria-label", "Identify " + labelFor(id));
                identify.addEventListener("click", () => identifyTablet(id)); actions.append(identify);
                item.append(actions); rows.set(id, { item, label, check, logical, sizeSummary, mount, angle, pins, earlier, later, include, identify }); $("grid-order").append(item);
            });
            for (const id of ids) {
                const row = rows.get(id), member = defaults[id];
                if (member.included) selected.add(id); else selected.delete(id);
                row.check.checked = member.included;
                if (!edited) storedAngles[id] = state.base.slots?.[id] ? String(state.base.slots[id].mount_angle) : "";
                if (row.angle.options) {
                    row.angle.options[0].textContent = storedAngles[id] === "" ? "Use common mount" : "Common mount, else " + storedAngles[id] + "°";
                    row.angle.options[0].title = "Keep the declared common mount when set; otherwise keep this tablet’s stored angle.";
                }
                row.sizeSummary.textContent = member.size.w + " × " + member.size.h + " relative units · " + member.sizeSource;
                row.include.hidden = member.included || !(state.roster[id] || {}).online;
                sizes[id] = member.size;
                row.item.dataset.deviceId = id;
                row.item.dataset.membershipSource = member.membershipSource;
                row.item.dataset.sizeSource = member.sizeSource;
                row.item.dataset.available = String(!member.included && !!(state.roster[id] || {}).online);
                if (row.logical.querySelectorAll) for (const input of row.logical.querySelectorAll("input")) {
                    if (document.activeElement !== input) input.value = member.size[input.dataset.field];
                }
            }
            order.filter(id => !ids.has(id)).forEach(id => { rows.get(id).item.remove(); rows.delete(id); selected.delete(id); });
            order = order.filter(id => ids.has(id));
            if (additions.length) {
                if (!edited) order.sort((a, b) => model.compareIds(state.roster, state.deviceLabels || {}, a, b));
                order.forEach(id => $("grid-order").append(rows.get(id).item));
            }
            const released = releases(), box = $("grid-releases");
            for (const id of releaseRows.keys()) if (!released.includes(id)) releaseRows.delete(id);
            const releaseLabels = released.map(id => {
                if (!releaseRows.has(id)) {
                    const label = document.createElement("label"); label.className = "check-label";
                    const check = document.createElement("input"); check.type = "checkbox"; check.dataset.release = id;
                    label.append(check, document.createTextNode(" Release " + labelFor(id) + " from the active arrangement"));
                    releaseRows.set(id, label);
                }
                return releaseRows.get(id);
            });
            if (releaseLabels.length !== box.children.length || releaseLabels.some((label, index) => box.children[index] !== label)) box.replaceChildren(...releaseLabels);
            updateButtons();
            const subjects = $("group-subjects"), groupModel = $("group-model");
            if ($("group-model-title")) $("group-model-title").closest("section").hidden = $("grid-kind").value !== "physical";
            if ($("grid-common-mount")) $("grid-common-mount").closest("label").hidden = $("grid-kind").value !== "physical";
            const review = modelReview();
            if (subjects) subjects.textContent = review ? "Unresolved hardware confirmation · " + review.ids.map(labelFor).join(" · ")
                : order.filter(id => selected.has(id)).map(labelFor).join(" · ") || "Select the tablets whose hardware you checked.";
            if ($("group-confirm")) $("group-confirm").textContent = review ? "Review and confirm unresolved tablets" : "Confirm model for selected tablets";
            if ($("group-new-review")) $("group-new-review").hidden = !review;
            if (groupModel) {
                const key = JSON.stringify(state.tabletModels);
                if (groupModel.dataset.key !== key) {
                    const value = groupModel.value;
                    groupModel.replaceChildren(new Option("Choose the model you checked", ""));
                    Object.entries(state.tabletModels || {}).forEach(([id, item]) => groupModel.add(new Option(item.label, id)));
                    groupModel.value = value; groupModel.dataset.key = key;
                }
            }
        }
        async function preview() {
            if (busy || !state.base) return;
            if (!state.gridPreview && isDirty()) { text("Apply or cancel the manual draft before building a grid."); return; }
            members.freeze();
            if (baseEtag && baseEtag !== state.etag) { text("The wall changed while these inputs were being edited. Rebuild preview explicitly to use the current wall, or discard."); return; }
            invalidate();
            const released = releases();
            if (released.some(id => !Array.from($("grid-releases").querySelectorAll("input")).some(input => input.dataset.release === id && input.checked))) {
                text("Explicitly acknowledge every released active tablet, including offline reservations."); return;
            }
            try {
                const kind = $("grid-kind").value, ids = order.filter(id => selected.has(id));
                if ($("grid-orientation").value === "auto" && ids.some(id => !state.roster[id] || !state.roster[id].online)) throw new Error("Auto orientation needs a fresh online viewport. Choose Preserve for offline reservations.");
                const common = $("grid-common-mount") ? $("grid-common-mount").value : "";
                const submittedAngles = Object.fromEntries(ids.map(id => [id, angles[id] !== "" ? angles[id] : common !== "" ? common : storedAngles[id]]));
                if (kind === "physical" && ids.some(id => submittedAngles[id] === "")) throw new Error("Declare the mounted top edge for every new measured tablet. 90° and 270° are distinct physical directions.");
                const revisions = {};
                ids.forEach(id => { const slot = state.base.slots && state.base.slots[id], pair = validPair(id);
                    if (slot) revisions[id] = { profile_revision: slot.profile_revision, calibration_revision: slot.calibration_revision };
                    else if (pair) revisions[id] = { profile_revision: pair.profile.revision, calibration_revision: pair.calibration.revision };
                });
                const number = id => $(id).value.trim() === "" ? NaN : Number($(id).value);
                previewCommand = command({ kind, ids, rows: number("grid-rows"), columns: number("grid-columns"), gap: number("grid-gap"), padding: number("grid-padding"), sizing: $("grid-sizing").value,
                    orientation: kind === "physical" ? "preserve" : $("grid-orientation").value, holes: $("grid-holes").checked, releases: released, sizes, revisions, angles: submittedAngles });
                busy = true; $("grid-preview").disabled = true;
                const etag = baseEtag || state.etag, version = inputVersion;
                const result = await api("POST", "/api/v3/grid/preview", previewCommand, { ifMatch: etag });
                if (version !== inputVersion || !result.layout || !result.guards || result.base_etag !== etag || state.etag !== etag || state.etagState !== "current") throw new Error("Preview inputs changed. Reload and preview again.");
                state.gridPreview = result;
                previewCommand = Object.assign({}, previewCommand, { guards: result.guards });
                const wall = model.bounds(result.layout);
                text(result.order.length + (result.order.length === 1 ? " tablet · " : " tablets · ") + previewCommand.rows + " row" + (previewCommand.rows === 1 ? "" : "s") + " × " + previewCommand.columns
                    + " column" + (previewCommand.columns === 1 ? "" : "s") + " · wall " + Number(wall.width.toFixed(1)) + " × " + Number(wall.height.toFixed(1)) + (kind === "physical" ? " mm" : " logical units")
                    + " · gap " + previewCommand.gap + (kind === "physical" ? " mm" : " logical units") + ". "
                    + { preserve: "Mounting and stored sizes preserved.", portrait: "Portrait orientation.", landscape: "Landscape orientation.", auto: "Orientation from current viewports and confirmed models." }[previewCommand.orientation]
                    + (result.warnings || []).map(warning => " " + warning[0].toUpperCase() + warning.slice(1).replace(/[.!?\s]+$/, "") + ".").join("")
                    + (result.previous_kind !== kind ? " Apply will request a named safety copy of the current arrangement." : ""));
                updateButtons(); syncDraftUi(); renderStage();
                if ($("arrange-membership").dataset.required === "false") $("arrange-membership").open = false;
                $("btn-apply").focus({ preventScroll: true });
            } catch (error) { text("Cannot preview arrangement. " + error.message + " The committed wall is unchanged."); }
            finally { busy = false; updateButtons(); }
        }
        async function apply() {
            if (!state.gridPreview || !previewCommand || busy) return;
            const restoreFocus = document.activeElement === $("btn-apply");
            const preview = state.gridPreview;
            if (preview.previous_kind !== preview.layout.kind && !window.confirm("Replace the " + preview.previous_kind + " arrangement with " + preview.layout.kind + "? The server must save a named safety copy. Content stays unchanged.")) return;
            busy = true;
            const version = inputVersion, submittedCommand = previewCommand;
            try {
                const result = await api("POST", "/api/v3/grid", submittedCommand, { ifMatch: preview.base_etag });
                if (version === inputVersion) {
                    state.gridPreview = null; previewCommand = null; edited = false; baseEtag = null;
                    members.commit(result.layout);
                    order.forEach(id => { angles[id] = ""; rows.get(id).angle.value = ""; });
                    if ($("grid-common-mount")) $("grid-common-mount").value = "";
                }
                ingestConfig(result, { preserveDraft: version !== inputVersion });
                text(result.previous_layout_saved ? "Previous arrangement saved as “" + result.previous_layout_saved + "”." : ""); announce("Arrangement applied.");
            } catch (error) { if (error.status === 412) showConflict("The grid preview is stale. Your preview is retained. Reload and preview again."); text("Apply failed. " + error.message + " The preview is retained."); }
            finally {
                busy = false; updateButtons(); syncDraftUi();
                if (restoreFocus && $("btn-apply").disabled) {
                    const target = $("grid-preview");
                    if (target && (typeof target.getClientRects !== "function" || target.getClientRects().length) && !target.disabled) target.focus({ preventScroll: true });
                }
            }
        }
        for (const id of ["grid-kind", "grid-rows", "grid-columns", "grid-gap", "grid-padding", "grid-orientation", "grid-sizing", "grid-holes"]) $(id).addEventListener("change", () => { invalidate(); updateButtons(); });
        for (const [id, twoRows] of presets) $(id).addEventListener("click", () => {
            const { r, c, holes } = preset(twoRows);
            $("grid-rows").value = r; $("grid-columns").value = c; $("grid-holes").checked = holes;
            invalidate(); text(r + " row" + (r === 1 ? "" : "s") + " × " + c + " column" + (c === 1 ? "" : "s")
                + " selected" + (holes ? " with an empty trailing cell" : "") + " · not previewed");
        });
        $("grid-preview").addEventListener("click", preview);
        function reset() {
            inputVersion += 1;
            text("");
            state.gridPreview = null; previewCommand = null; edited = false; baseEtag = null;
            rows.forEach(row => row.item.remove()); rows.clear(); releaseRows.clear(); order = []; selected.clear(); sizes = {}; angles = {}; storedAngles = {}; members = membership(); initialized = false;
            if ($("grid-common-mount")) $("grid-common-mount").value = "";
            render(); syncDraftUi(); renderStage();
        }
        if ($("grid-common-mount")) $("grid-common-mount").addEventListener("change", invalidate);
        if ($("grid-rebuild")) $("grid-rebuild").addEventListener("click", () => {
            if (!window.confirm("Keep these tablet choices and rebuild against the current wall? Review the new proposal before applying.")) return;
            state.draftConflict = false; baseEtag = state.etag; state.gridPreview = null;
            preview();
        });
        return { render, apply, cancel: reset, reset, dirty: () => edited,
            selectedIds: () => order.filter(id => selected.has(id)),
            freezeSelection: () => members.freeze(),
            exclude(id) { if (members.view()[id]) { members.include(id, false); selected.delete(id); render(); } },
            modelSetupComplete(expected) { if (!expected || state.etag !== expected) return false; baseEtag = expected; return true; } };
    }
    const api = { command, membership, create };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorGrid = api;
}(typeof window !== "undefined" ? window : globalThis));
