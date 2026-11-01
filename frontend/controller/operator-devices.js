"use strict";
window.OperatorDevices = {
    create({ state, api, labelFor, profileFor, calibrationFor, ingestConfig, refreshRoster, showConflict, isDirty, announce }) {
        const $ = id => document.getElementById(id);
        $("operator-device-actions").innerHTML = `<section class="card" aria-labelledby="tablet-actions-title">
            <h2 id="tablet-actions-title">Tablet actions</h2><p id="tablet-action-name">Select a tablet.</p><p id="tablet-evidence"></p><p class="hint" id="tablet-provenance"></p><button class="btn" id="open-tablet-measurements" type="button">Review measurements / confirm model</button>
            <form id="tablet-label-form"><label class="field" for="tablet-label">Operator label<input class="inp" id="tablet-label" maxlength="80" autocomplete="off"></label><button class="btn" id="tablet-label-save">Save label</button></form>
            <div class="operator-actions"><button class="btn" id="tablet-identify" type="button">Identify for 5 seconds</button><button class="btn" id="tablet-retry-image" type="button">Retry image</button><button class="btn" id="tablet-reconnect" type="button">Reconnect</button></div>
            <p class="hint">Reconnect keeps the tablet identity, label and number. Identify temporarily covers the image.</p>
            <label class="check-label" id="tablet-participation-label"><input type="checkbox" id="tablet-participation"> Include this slot in the show (draft)</label>
            <div class="operator-actions"><button class="btn" id="tablet-remove" type="button">Remove from wall</button><button class="btn btn-danger" id="tablet-forget-preview" type="button">Review offline Forget</button></div>
            <div id="tablet-forget-impact" hidden><p id="tablet-forget-text"></p><label class="check-label"><input type="checkbox" id="tablet-forget-active"> Also remove the active slot</label><button class="btn btn-danger" id="tablet-forget-confirm" type="button">Confirm Forget</button><button class="btn" id="tablet-forget-cancel" type="button">Cancel Forget</button></div>
            <details><summary>Replace this offline browser identity</summary><p>Choose the exact saved arrangements to update. Same hardware copies pinned measurements. Different hardware cannot inherit physical measurements.</p>
                <label class="field" for="replace-target">Replacement registration<select class="inp" id="replace-target"><option value="">Choose new registration</option></select></label>
                <label class="field" for="replace-hardware">Hardware declaration<select class="inp" id="replace-hardware"><option value="">Choose explicitly</option><option value="same_hardware">Same hardware, new browser identity</option><option value="different_hardware">Different hardware</option></select></label>
                <label class="check-label"><input type="checkbox" id="replace-active" checked> Update active arrangement</label><label class="check-label"><input type="checkbox" id="replace-label" checked> Transfer operator label</label>
                <label class="field" for="replace-number">Display number (optional)<input class="inp" id="replace-number" type="number" min="1" max="512" step="1"></label>
                <fieldset id="replace-saved"><legend>Saved arrangements to update</legend></fieldset>
                <button class="btn" type="button" id="replace-preview">Preview replacement</button><p id="replace-summary" role="status" aria-live="polite"></p><button class="btn btn-danger" type="button" id="replace-apply" disabled>Confirm replacement</button>
            </details><p id="tablet-action-message" role="status" aria-live="polite"></p></section>`;
        let selectedId = null, impact = null, replacement = null, busy = false, snapshotsKey = "", replaceVersion = 0, labelBaseline = "";
        const message = text => { $("tablet-action-message").textContent = text; };
        const path = (id, suffix = "") => "/api/v3/devices/" + encodeURIComponent(id) + suffix;
        function config() { return state.operatorConfig || { layout: state.base, scene: state.scene, runtime: { devices: state.roster }, revision: state.revision, generation: state.generation }; }
        function clearPlans() { impact = null; replacement = null; $("tablet-forget-impact").hidden = true; $("replace-apply").disabled = true; }
        function render() {
            const id = state.selectedId;
            const device = state.roster[id];
            const active = window.OperatorState.entries(state.base)[id];
            if (id !== selectedId) {
                selectedId = id; clearPlans(); snapshotsKey = "";
                $("tablet-label").value = (state.deviceLabels || {})[id] || device && device.label || "";
                labelBaseline = $("tablet-label").value;
                $("replace-target").value = ""; $("replace-hardware").value = "";
            }
            $("tablet-action-name").textContent = id ? labelFor(id) : "Select a tablet in the list or stage.";
            $("tablet-evidence").textContent = id ? window.OperatorState.tabletState(config(), id, performance.now()).text : "";
            const mapping = device && device.mapping || {};
            const slot = state.base && state.base.slots && state.base.slots[id];
            const profile = slot && profileFor(id, slot.profile_revision), calibration = slot && calibrationFor(id, slot.calibration_revision);
            const details = [];
            if (slot) {
                details.push("Pinned profile r" + slot.profile_revision + ", calibration r" + slot.calibration_revision + ".");
                if (!profile || !calibration) details.push("Pinned records unavailable. Reload configuration; no substitute measurement is assumed.");
                else {
                    details.push("Panel source “" + profile.provenance + "”; CSS scale method “" + calibration.method + "”, uncertainty ±" + calibration.uncertainty_mm + " mm.");
                    details.push("Calibrated " + calibration.viewport_width + " × " + calibration.viewport_height + " CSS px, DPR " + calibration.dpr + ", browser " + calibration.orientation + "°, " + calibration.mode + "; calibration quarter-turn " + calibration.quarter_turn + ", wall mount " + slot.mount_angle + "°.");
                }
            } else details.push(state.layoutKind === "logical" ? "Logical units. No measured scale is claimed." : "Not in the measured arrangement.");
            const health = mapping.health;
            if (health && slot) {
                details.push(health.provenance.description + ". No physical accuracy is claimed.");
                if (health.viewport.insets) details.push("Browser inset assumption: " + health.viewport.insets.source + ".");
                if (health.comparison.discrepancy) details.push("Scale discrepancy: supplied lit panel "
                    + health.comparison.lit_dimensions_mm.join(" × ") + " mm; predicted "
                    + health.comparison.predicted_mm.join(" × ") + " mm. " + health.comparison.message);
                if (health.actionable_warning) details.push(health.actionable_warning.message + " " + health.actionable_warning.action);
            } else if (slot) details.push("Pinned calibration health is unavailable. Reload before relying on the mapping.");
            if (mapping.reason) details.push(mapping.reason + ". Return to the calibrated rotation, zoom and launch mode, or recalibrate.");
            if (device && device.viewport) details.push("Live viewport " + device.viewport.width + " × " + device.viewport.height + ", " + device.viewport.orientation + "°, " + device.viewport.mode + ", zoom " + (device.viewport.visual_scale === undefined ? "not reported" : device.viewport.visual_scale) + ".");
            $("tablet-provenance").textContent = details.join(" ");
            for (const action of ["tablet-label-save", "tablet-remove", "tablet-forget-preview", "replace-preview"]) $(action).disabled = !id || busy || state.etagState !== "current";
            for (const action of ["identify", "retry-image", "reconnect"]) {
                const button = $("tablet-" + action);
                button.disabled = !device || !device.online || busy || (action === "identify" && !(device.caps || []).includes("identify"));
                button.title = !device || !device.online ? "Unavailable while offline" : action === "identify" && !(device.caps || []).includes("identify") ? "This client does not advertise Identify" : "";
            }
            $("tablet-remove").disabled ||= !active;
            $("tablet-forget-preview").disabled ||= !!device && device.online === true;
            $("tablet-forget-preview").title = device && device.online ? "Forget requires the tablet socket to be offline. Remove from wall keeps the registration." : "Review active slot and saved references before Forget.";
            $("tablet-participation-label").hidden = !slot;
            if (slot && document.activeElement !== $("tablet-participation")) $("tablet-participation").checked = state.draft.slots[id].participating !== false;
            const targets = Object.keys(state.roster).filter(key => key !== id).sort((a, b) => window.OperatorState.compareIds(state.roster, state.deviceLabels || {}, a, b));
            const selector = $("replace-target"), targetKey = targets.map(key => key + labelFor(key)).join("|");
            if (selector.dataset.key !== targetKey) {
                const value = selector.value; selector.replaceChildren(new Option("Choose new registration", ""));
                targets.forEach(key => selector.add(new Option(labelFor(key), key))); selector.value = value; selector.dataset.key = targetKey;
            }
            const snapshots = state.snapshots && state.snapshots.layouts || [];
            const key = JSON.stringify([snapshots, state.savedLayouts]);
            if (snapshotsKey !== key) {
                snapshotsKey = key; replacement = null; $("replace-apply").disabled = true;
                $("replace-saved").replaceChildren();
                const legend = document.createElement("legend"); legend.textContent = "Exact saved arrangements to update"; $("replace-saved").append(legend);
                snapshots.forEach(snapshot => {
                    const layout = state.savedLayouts.find(saved => saved.name === snapshot.name);
                    const references = layout && window.OperatorState.entries(layout.layout)[id];
                    const label = document.createElement("label"); label.className = "check-label";
                    const check = document.createElement("input"); check.type = "checkbox"; check.dataset.name = snapshot.name; check.dataset.etag = snapshot.etag || "";
                    check.checked = !!references && snapshot.valid !== false; check.disabled = snapshot.valid === false || !snapshot.etag;
                    check.addEventListener("change", () => { replacement = null; replaceVersion += 1; $("replace-apply").disabled = true; });
                    label.append(check, document.createTextNode(snapshot.name + " · " + snapshot.kind + (snapshot.valid === false ? " · damaged" : references ? " · references this tablet" : " · reference coverage not reported")));
                    $("replace-saved").append(label);
                });
                if (!snapshots.length) { const note = document.createElement("p"); note.textContent = "Saved arrangement digests are not available. Refresh configuration before replacing saved reservations."; $("replace-saved").append(note); }
            }
        }
        async function run(work) {
            if (busy) return;
            const focused = document.activeElement;
            busy = true; render();
            try { await work(); }
            catch (error) { if (error.status === 412) showConflict("Tablet action inputs changed. Review and preview again."); message("Action unavailable or failed. " + error.message + " Refresh status and retry."); }
            finally {
                busy = false; render();
                if (focused && focused !== document.body && document.activeElement === document.body) {
                    const target = focused.isConnected && !focused.disabled && focused.getClientRects().length
                        ? focused : document.querySelector('.dev-pick[aria-pressed="true"]');
                    if (target) target.focus();
                }
            }
        }
        $("tablet-label-form").addEventListener("submit", event => {
            event.preventDefault(); const id = selectedId, label = $("tablet-label").value.trim();
            run(async () => { const result = await api("PATCH", path(id), { label: label || null }, { etag: true }); if (state.selectedId === id) labelBaseline = label; ingestConfig(result, { preserveDraft: true }); message("Label saved for " + labelFor(id) + "."); });
        });
        for (const action of ["identify", "retry-image", "reconnect"]) $("tablet-" + action).addEventListener("click", () => {
            const id = selectedId;
            run(async () => { await api("POST", path(id, "/" + action), action === "identify" ? { duration_ms: 5000 } : undefined, { etag: true });
                message(action === "identify" ? "Identify requested. Delivery is unconfirmed until the tablet reports it." : action === "retry-image" ? "Image retry requested. Waiting for a fresh paint confirmation." : "Reconnect requested. The tablet keeps its identity.");
                await refreshRoster(); });
        });
        $("tablet-participation").addEventListener("change", () => {
            if (state.draft && state.draft.slots[selectedId]) state.onParticipation(selectedId, $("tablet-participation").checked);
        });
        $("tablet-remove").addEventListener("click", () => {
            const id = selectedId;
            if (isDirty()) { message("Apply or cancel the layout draft first."); return; }
            if (!window.confirm("Remove " + labelFor(id) + " from the active wall? Registration, measurements and saved arrangements stay.")) return;
            run(async () => {
                const layout = window.OperatorState.clone(state.base);
                delete window.OperatorState.entries(layout)[id];
                const body = layout.kind === "physical" ? { bounds: layout.bounds, slots: layout.slots, sizing: layout.sizing }
                    : { width: layout.width, height: layout.height, placements: layout.placements, sizing: layout.sizing };
                const result = await api("PUT", layout.kind === "physical" ? "/api/v3/layout" : "/api/v3/logical-layout", body, { etag: true });
                ingestConfig(result); message("Removed active slot. Registration and saved arrangements retained.");
            });
        });
        $("tablet-forget-preview").addEventListener("click", () => {
            const id = selectedId;
            run(async () => {
                const result = await api("GET", path(id, "/impact"));
                if (id !== selectedId || result.online || !result.etag) throw new Error("Tablet state changed. Forget requires an offline socket and current impact ETag.");
                impact = { id, ...result }; $("tablet-forget-impact").hidden = false;
                $("tablet-forget-active").checked = false; $("tablet-forget-active").disabled = !result.active_entry;
                $("tablet-forget-text").textContent = "Forget " + labelFor(id) + "? This releases its label and leased number. " + (result.active_entry ? "An active slot must also be explicitly removed. " : "")
                    + "Saved reservations remain in " + ((result.saved_layouts || []).map(item => typeof item === "string" ? item : item.name).join(", ") || "no reported saved arrangements")
                    + ". Measurement history is retained. Reopening the old browser can register again. Forget is not revocation.";
            });
        });
        $("tablet-forget-confirm").addEventListener("click", () => {
            if (!impact) return;
            const plan = impact;
            if (plan.active_entry && !$("tablet-forget-active").checked) { message("Explicitly acknowledge removal of the active slot before Forget."); return; }
            run(async () => { const result = await api("DELETE", path(plan.id), { remove_active: $("tablet-forget-active").checked, saved_layouts: "keep" }, { ifMatch: plan.etag });
                clearPlans(); ingestConfig(result); await refreshRoster(); message("Tablet forgotten. Saved reservations and measurements retained."); });
        });
        $("tablet-forget-cancel").addEventListener("click", clearPlans);
        for (const id of ["replace-target", "replace-hardware", "replace-active", "replace-label", "replace-number"]) $(id).addEventListener("change", () => { replacement = null; replaceVersion += 1; $("replace-apply").disabled = true; });
        $("replace-preview").addEventListener("click", () => {
            const id = selectedId, target = $("replace-target").value;
            if (!target || !$("replace-hardware").value) { message("Choose a replacement registration and explicitly declare the hardware relationship."); return; }
            if (isDirty()) { message("Apply or cancel the layout draft before replacement."); return; }
            const body = { replaces: id, hardware: $("replace-hardware").value, active: $("replace-active").checked,
                saved_layouts: Array.from($("replace-saved").querySelectorAll("input:checked")).map(input => ({ name: input.dataset.name, etag: input.dataset.etag })), transfer_label: $("replace-label").checked };
            if ($("replace-number").value !== "") body.number = Number($("replace-number").value);
            run(async () => {
                const etag = state.etag, version = replaceVersion;
                const preview = await api("POST", path(target, "/rebind/preview"), body, { ifMatch: etag });
                if (version !== replaceVersion || id !== selectedId || state.etag !== etag || preview.base_etag !== etag || (preview.conflicts || []).length) throw new Error("Replacement conflicts. " + JSON.stringify(preview.conflicts || []));
                replacement = { id, target, body, preview };
                $("replace-summary").textContent = "Preview only. Replace " + labelFor(id) + " (" + id.slice(0, 8)
                    + ") with " + labelFor(target) + " (" + target.slice(0, 8) + "). Update active: " + preview.affected_active + ". Selected saved arrangements: " + body.saved_layouts.map(item => item.name).join(", ")
                    + ". Untouched saved reservations: " + (preview.untouched_saved || []).map(item => item.name).join(", ")
                    + ". Profile revision map " + JSON.stringify(preview.profile_revision_map) + "; calibration map " + JSON.stringify(preview.calibration_revision_map)
                    + ". Label after: " + (preview.label_after || "none") + "; number after: " + (preview.number_after || "unassigned") + ".";
                $("replace-apply").disabled = false;
            });
        });
        $("replace-apply").addEventListener("click", () => {
            if (!replacement) return;
            const plan = replacement;
            run(async () => {
                const result = await api("POST", path(plan.target, "/rebind"), Object.assign({}, plan.body, { new_connection_id: plan.preview.new_connection_id }), { ifMatch: plan.preview.base_etag });
                clearPlans(); ingestConfig(result); await refreshRoster(); message("Replacement applied to the active arrangement and exactly the selected saved arrangements."); announce("Tablet replacement applied.");
            });
        });
        return { render, dirty: () => !!selectedId && $("tablet-label").value !== labelBaseline,
            discard() { selectedId = null; clearPlans(); } };
    }
};
