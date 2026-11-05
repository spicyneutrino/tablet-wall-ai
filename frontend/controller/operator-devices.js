"use strict";
(function (root) {
    async function confirmModels({ ids, modelId, hardwareDeclared, reviewedEtag, api, ingestConfig, currentEtag, progress = () => {}, readAuthority = () => api("GET", "/api/v3/config", undefined, { fenced: true }) }) {
        if (!hardwareDeclared || !ids.length || new Set(ids).size !== ids.length || !modelId || !reviewedEtag) throw new Error("Review the exact tablets, select a model, and declare that you checked their hardware.");
        const captured = ids.slice(), completed = [];
        let expected = reviewedEtag;
        for (let index = 0; index < captured.length; index += 1) {
            const id = captured[index];
            try {
                const config = await readAuthority();
                if (config.etag !== expected) throw Object.assign(new Error("The wall changed outside this model confirmation. Review the remaining tablets."), { status: 412 });
                ingestConfig(config, { preserveDraft: true });
                if (currentEtag() !== expected) throw Object.assign(new Error("Newer authority arrived before assignment."), { status: 412 });
                const result = await api("PUT", "/api/v3/tablet-assignments/" + encodeURIComponent(id), { mode: "explicit", model_id: modelId }, { ifMatch: expected });
                if (!result || !result.etag) throw Object.assign(new Error("Assignment may have completed, but no next guard was returned."), { uncertain: true });
                expected = result.commandEtag || result.etag; completed.push(id);
                progress({ completed: completed.slice(), untouched: captured.slice(index + 1) });
            } catch (error) {
                return { status: error.uncertain || error.status === 0 ? "uncertain" : error.status === 412 ? "conflict" : "failed",
                    completed, failed: id, untouched: captured.slice(index + 1), reason: error.message, expectedEtag: expected };
            }
        }
        return { status: "completed", completed, untouched: [], expectedEtag: expected };
    }
    function create({ state, api, labelFor, profileFor, calibrationFor, ingestConfig, refreshRoster, showConflict, announce, tabletForms, resolveOutput = async () => true, removedFromWall = () => {}, selectTablet, openArrange, renderRoster = () => {} }) {
        const $ = id => document.getElementById(id);

        let selectedId = null, impact = null, replacement = null, busy = false, snapshotsKey = "", replaceVersion = 0;
        const results = new Map();
        let nameReview = null;
        const message = text => { $("tablet-action-message").textContent = text; };
        const path = (id, suffix = "") => "/api/v3/devices/" + encodeURIComponent(id) + suffix;
        function config() { return state.operatorConfig || { layout: state.base, scene: state.scene, runtime: { devices: state.roster }, revision: state.revision, generation: state.generation }; }
        function clearPlans() { nameReview = null; $("tablet-name-review").hidden = true; impact = null; replacement = null; $("tablet-forget-impact").hidden = true; $("replace-apply").disabled = true; $("replace-cancel").disabled = true; }
        function render() {
            renderRoster();
            const id = state.selectedId;
            const device = state.roster[id];
            $("operator-device-actions").hidden = !id;
            if (impact && (impact.etag !== state.etag || state.roster[impact.id]?.online)) {
                impact = null; $("tablet-forget-confirm").disabled = true;
                $("tablet-forget-text").textContent = "This Forget review is stale or the tablet reconnected. Review fresh offline impact before confirming.";
            }
            if (replacement && (replacement.preview.base_etag !== state.etag || state.rosterError || state.roster[replacement.id]?.online
                    || !state.roster[replacement.target]?.online || (state.connectionVersions[replacement.target] || 0) !== replacement.connectionVersion)) {
                replacement = null; $("replace-apply").disabled = true;
                $("replace-summary").textContent = "The wall, saved references or replacement connection changed. Preview replacement again before confirming.";
            }
            const active = window.OperatorState.entries(state.base)[id];
            if (id !== selectedId) {
                selectedId = id; clearPlans(); snapshotsKey = "";
                const form = tabletForms.observe(id, "name", { name: (state.deviceLabels || {})[id] || device && device.label || "" }, state.etag);
                $("tablet-label").value = form.values.name;
                message(results.get(id) || "");
                $("replace-target").value = ""; $("replace-hardware").value = "";
            }
            if (id) {
                const form = tabletForms.observe(id, "name", { name: (state.deviceLabels || {})[id] || device && device.label || "" }, state.etag);
                if (document.activeElement !== $("tablet-label")) $("tablet-label").value = form.values.name;
                $("tablet-label-form").dataset.dirty = String(form.dirty);
                $("tablet-label-form").dataset.deviceId = id;
                $("tablet-label-review").hidden = !form.dirty;
                $("tablet-label-discard").hidden = !form.dirty;
                if (form.conflict) message("This tablet’s saved name changed elsewhere. Your name is retained. Discard to use the current name, or review before saving.");
            }
            $("tablet-action-name").textContent = id ? labelFor(id) : "Select a tablet in the list or stage.";
            const evidence = id ? window.OperatorState.tabletState(config(), id, performance.now()) : null;
            if (impact || replacement) $("tablet-lifecycle").open = true;
            $("tablet-evidence").hidden = !evidence || evidence.status === "unplaced";
            $("tablet-evidence").textContent = evidence && evidence.status !== "unplaced" ? evidence.text : "";
            $("tablet-recovery").textContent = !id ? "" : evidence.status === "unplaced"
                ? "Not placed yet. The wall cannot address this tablet until it is placed in Arrange."
                : !device || !device.online
                ? "On the tablet, check power, keep its screen awake, join the wall network and reopen the tablet page in its existing browser. The server cannot wake a powered-off or sleeping tablet."
                : evidence.status === "hidden" ? "Bring the tablet page to the foreground and keep it open. A hidden page cannot confirm the current image."
                : evidence.status === "identifying" ? "The Identify overlay temporarily covers the image. Wait for it to clear before relying on current image proof."
                : ["unsupported_client", "unsupported_content", "unsupported"].includes(evidence.status) ? "Reopen the current tablet page in its existing browser and check browser support. The operator cannot remotely install or wake the tablet."
                : evidence.status === "failed" ? "The tablet reported a failed image. Check the image availability, then retry it."
                : ["blocked", "invalid", "stale_calibration", "needs_calibration", "needs_profile", "viewport_mismatch", "zoom_changed", "missing_profile", "missing_calibration", "invalid_mapping"].includes(evidence.status) ? "Return the tablet to its calibrated rotation, 100% zoom and launch mode, or review its measurements."
                : evidence.status === "unplaced" ? "Connected and available. Place this tablet in Arrange." : "Current matching reports are separate from connection status. Reconnect keeps this browser identity.";
            $("tablet-recovery").hidden = !!evidence?.showing;
            const tabletOnline = !!device && device.online === true;
            for (const action of ["tablet-identify", "tablet-retry-image", "tablet-reconnect"]) {
                const button = $(action);
                if (button) button.hidden = !tabletOnline;
            }
            $("open-tablet-measurements").hidden = !["blocked", "invalid", "stale_calibration", "needs_calibration", "needs_profile", "viewport_mismatch", "zoom_changed", "missing_profile", "missing_calibration", "invalid_mapping"].includes(evidence?.status);
            $("tablet-arrange").hidden = !id || evidence?.status !== "unplaced";
            const oldIds = Object.keys(state.roster).filter(key => key !== id && !state.roster[key].online);
            $("replacement-offer").hidden = !device || !device.online || !!active || !oldIds.length;
            const oldSelect = $("replacement-old"), oldKey = oldIds.map(key => key + labelFor(key)).join("|");
            if (oldSelect.dataset.key !== oldKey) {
                const value = oldSelect.value; oldSelect.replaceChildren(new Option("Choose old tablet", ""));
                oldIds.forEach(key => oldSelect.add(new Option(labelFor(key), key))); oldSelect.value = value; oldSelect.dataset.key = oldKey;
            }
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
                button.disabled = action === "identify" ? !canIdentify(id) : !device || !device.online || busy;
                button.title = !device || !device.online ? "Unavailable while offline" : action === "identify" && !(device.caps || []).includes("identify") ? "This client does not advertise Identify" : action === "identify" && state.etagState !== "current" ? "Refresh status before Identify" : "";
            }
            $("tablet-forget-confirm").disabled = busy || !impact;
            $("replace-apply").disabled = busy || !replacement;
            $("replace-cancel").disabled = busy || !replacement;
            $("replace-preview").disabled ||= !!device && device.online === true;
            $("tablet-remove").disabled ||= !active;
            $("tablet-forget-preview").disabled ||= !!device && device.online === true;
            $("tablet-forget-preview").title = device && device.online ? "Forget requires the tablet socket to be offline. Remove from wall keeps the registration." : "Review active slot and saved references before Forget.";
            $("tablet-participation-label").hidden = !slot;
            if (slot && state.draft.slots[id] && document.activeElement !== $("tablet-participation")) $("tablet-participation").checked = state.draft.slots[id].participating !== false;
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
                    const references = layout && layout.etag === snapshot.etag && window.OperatorState.entries(layout.layout)[id];
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
        async function run(work, id = selectedId) {
            if (busy) return;
            const focused = document.activeElement;
            busy = true; render();
            try { await work(); }
            catch (error) { if (error.status === 412) showConflict("Tablet action inputs changed. Review and preview again."); const text = "Action for " + labelFor(id) + (error.uncertain ? " may have completed. " : " failed. ") + error.message + (error.uncertain ? "" : " Review the problem, then retry.");
                results.set(id, text); if (id === selectedId) message(text); }
            finally {
                busy = false; render();
                if (focused && focused !== document.body && document.activeElement === document.body) {
                    const target = focused.isConnected && !focused.disabled && focused.getClientRects().length
                        ? focused : document.querySelector('.dev-pick[aria-pressed="true"]');
                    if (target) target.focus();
                }
            }
        }
        $("tablet-arrange").addEventListener("click", () => { if (selectedId) openArrange(); });
        $("replacement-open").addEventListener("click", () => {
            const newId = selectedId, oldId = $("replacement-old").value;
            if (!newId || !oldId || !state.roster[newId]?.online || state.roster[oldId]?.online) { message("Choose an offline registration to replace with this connected tablet."); return; }
            selectTablet(oldId);
            $("replace-target").value = newId;
            $("replace-target").dispatchEvent(new Event("change", { bubbles: true }));
            $("replace-target").closest("details").open = true;
            $("replace-hardware").focus();
        });
        $("tablet-label-review").addEventListener("click", () => {
            const id = selectedId, submitted = tabletForms.get(id, "name");
            if (!id || !submitted) return;
            run(async () => {
                await refreshRoster();
                if (id !== selectedId || submitted.version !== tabletForms.get(id, "name").version) return;
                const remote = { name: state.deviceLabels[id] || state.roster[id]?.label || "" };
                nameReview = { id, version: submitted.version, remote, etag: state.etag };
                $("tablet-name-comparison").textContent = "Saved before · " + (submitted.baseline.name || "Default name")
                    + ". Current saved · " + (remote.name || "Default name") + ". Your proposed name · " + (submitted.values.name || "Default name") + ".";
                $("tablet-name-review").hidden = false; $("tablet-name-keep").focus();
            }, id);
        });
        $("tablet-name-keep").addEventListener("click", () => {
            const review = nameReview;
            if (!review || review.id !== selectedId || review.etag !== state.etag || !tabletForms.review(review.id, "name", review.version, review.remote, review.etag)) {
                message("The name or wall changed after this comparison. Review the current name again."); return;
            }
            $("tablet-name-review").hidden = true; nameReview = null;
            message("Your name is retained against the reviewed saved value. Save name is a separate command."); render();
        });
        $("tablet-label").addEventListener("input", () => {
            nameReview = null; $("tablet-name-review").hidden = true;
            const form = tabletForms.edit(selectedId, "name", { name: $("tablet-label").value }, state.etag);
            $("tablet-label-form").dataset.dirty = String(form.dirty);
            $("tablet-label-review").hidden = !form.dirty;
            $("tablet-label-discard").hidden = !form.dirty;
        });
        $("tablet-label-discard").addEventListener("click", () => {
            const id = selectedId;
            nameReview = null; $("tablet-name-review").hidden = true;
            tabletForms.discard(id, "name");
            const form = tabletForms.observe(id, "name", { name: (state.deviceLabels || {})[id] || "" }, state.etag);
            $("tablet-label").value = form.values.name; $("tablet-label").focus(); render();
        });
        $("tablet-label-form").addEventListener("submit", async event => {
            event.preventDefault();
            const id = selectedId, submitted = tabletForms.get(id, "name");
            if (!id || !submitted) return;
            if (!await resolveOutput("Save a tablet name")) return;
            if (submitted.conflict) { message("The saved name changed elsewhere. Discard or compare your edit before saving."); return; }
            run(async () => {
                const result = await api("PATCH", path(id), { label: submitted.values.name.trim() || null }, { ifMatch: submitted.baseEtag });
                tabletForms.saved(id, "name", submitted.version, submitted.values, result.etag);
                ingestConfig(result, { preserveDraft: true });
                const text = "Name saved for " + labelFor(id) + ".";
                results.set(id, text); if (selectedId === id) message(text);
            }, id);
        });
        const canIdentify = id => !busy && !!state.roster[id]?.online
            && (state.roster[id].caps || []).includes("identify") && state.etagState === "current";
        function identify(id) {
            if (!canIdentify(id)) {
                const text = "Identify unavailable for " + labelFor(id) + ". Refresh status and check that the tablet is online and supports Identify.";
                results.set(id, text); if (selectedId === id) message(text); announce(text);
                return;
            }
            return run(async () => {
                await api("POST", path(id, "/identify"), { duration_ms: 5000 }, { etag: true });
                const text = "Identify requested for " + labelFor(id) + ". Delivery is unconfirmed until the tablet reports it.";
                results.set(id, text); if (selectedId === id) message(text); announce(text);
                await refreshRoster();
            }, id);
        }
        $("tablet-identify").addEventListener("click", () => identify(selectedId));
        for (const action of ["retry-image", "reconnect"]) $("tablet-" + action).addEventListener("click", () => {
            const id = selectedId;
            run(async () => { await api("POST", path(id, "/" + action), undefined, { etag: true });
                const text = action === "retry-image" ? "Image retry requested. Waiting for a fresh paint confirmation." : "Reconnect requested. The tablet keeps its identity.";
                results.set(id, text); if (selectedId === id) message(text);
                await refreshRoster(); });
        });
        $("tablet-participation").addEventListener("change", () => {
            if (state.draft && state.draft.slots[selectedId]) state.onParticipation(selectedId, $("tablet-participation").checked);
        });
        $("tablet-remove").addEventListener("click", async () => {
            const id = selectedId;
            if (!await resolveOutput("Remove " + labelFor(id) + " from the wall")) return;
            if (!window.confirm("Remove " + labelFor(id) + " from the active wall? Registration, measurements and saved arrangements stay.")) return;
            run(async () => {
                const result = await api("POST", path(id, "/remove"), undefined, { etag: true });
                ingestConfig(result); removedFromWall(id); if (selectedId === id) message("Removed active slot. Registration and saved arrangements retained.");
            }, id);
        });
        $("tablet-forget-preview").addEventListener("click", async () => {
            const id = selectedId;
            if (!await resolveOutput("Review offline Forget")) return;
            if (tabletForms.dirty(id)) { message("Save or discard this tablet’s unsaved name and measurement fields before Forget. They are retained."); return; }
            run(async () => {
                const result = await api("GET", path(id, "/impact"), undefined, { fenced: true });
                if (id !== selectedId || result.online || !result.etag || result.etag !== state.etag) throw new Error("Tablet state changed. Forget requires an offline socket and current impact ETag.");
                impact = { id, ...result }; $("tablet-forget-impact").hidden = false; $("tablet-forget-confirm").disabled = false;
                $("tablet-forget-active").checked = false; $("tablet-forget-active").disabled = !result.active_entry;
                $("tablet-forget-text").textContent = "Forget " + labelFor(id) + "? This releases its label and leased number. " + (result.active_entry ? "An active slot must also be explicitly removed. " : "")
                    + "Saved reservations remain in " + ((result.saved_layouts || []).map(item => typeof item === "string" ? item : item.name).join(", ") || "no reported saved arrangements")
                    + ". Measurement history is retained. Reopening the old browser can register again. Forget is not revocation.";
            }, id);
        });
        $("tablet-forget-confirm").addEventListener("click", () => {
            if (!impact) return;
            const plan = impact, subject = labelFor(impact.id);
            if (plan.active_entry && !$("tablet-forget-active").checked) { message("Explicitly acknowledge removal of the active slot before Forget."); return; }
            run(async () => { const result = await api("DELETE", path(plan.id), { remove_active: $("tablet-forget-active").checked, saved_layouts: "keep" }, { ifMatch: plan.etag });
                if (selectedId === plan.id) clearPlans(); ingestConfig(result); await refreshRoster(); if (selectedId === plan.id) message("Tablet forgotten. Saved reservations and measurements retained."); announce("Forgot " + subject + ". Saved reservations and measurements are retained."); });
        });
        $("tablet-forget-cancel").addEventListener("click", () => { clearPlans(); $("tablet-forget-preview").focus(); });
        $("replace-cancel").addEventListener("click", () => {
            replacement = null; replaceVersion += 1; $("replace-apply").disabled = true; $("replace-cancel").disabled = true;
            $("replace-summary").textContent = "Replacement preview discarded. No tablet or saved arrangement was changed.";
            $("replace-preview").focus();
        });
        for (const id of ["replace-target", "replace-hardware", "replace-active", "replace-label", "replace-number"]) $(id).addEventListener("change", () => { replacement = null; replaceVersion += 1; $("replace-apply").disabled = true; });
        $("replace-preview").addEventListener("click", async () => {
            const id = selectedId, target = $("replace-target").value;
            if (!target || !$("replace-hardware").value) { message("Choose a replacement registration and explicitly declare the hardware relationship."); return; }
            const inputVersion = replaceVersion;
            if (!await resolveOutput("Review tablet replacement")) return;
            if (id !== selectedId || inputVersion !== replaceVersion) return;
            if (tabletForms.dirty(id) || tabletForms.dirty(target)) { message("Save or discard unsaved fields for the old and replacement tablets before replacement. Their values are retained."); return; }
            const body = { replaces: id, hardware: $("replace-hardware").value, active: $("replace-active").checked,
                saved_layouts: Array.from($("replace-saved").querySelectorAll("input:checked")).map(input => ({ name: input.dataset.name, etag: input.dataset.etag })), transfer_label: $("replace-label").checked };
            if ($("replace-number").value !== "") body.number = Number($("replace-number").value);
            run(async () => {
                const etag = state.etag, version = replaceVersion, connectionVersion = state.connectionVersions[target] || 0;
                const preview = await api("POST", path(target, "/rebind/preview"), body, { ifMatch: etag });
                if (version !== replaceVersion || id !== selectedId || state.etag !== etag || preview.base_etag !== etag || (state.connectionVersions[target] || 0) !== connectionVersion || (preview.conflicts || []).length) throw new Error("Replacement conflicts. " + JSON.stringify(preview.conflicts || []));
                replacement = { id, target, body, preview, connectionVersion };
                $("replace-summary").textContent = "Preview only. Replace " + labelFor(id) + " with " + labelFor(target) + ". "
                    + (body.hardware === "same_hardware" ? "Same hardware, new browser identity. " : "Different hardware; physical measurements are not inherited. ")
                    + (preview.affected_active ? "Update the active arrangement. " : "Keep the active arrangement. ")
                    + "Selected saved arrangements · " + (body.saved_layouts.map(item => item.name).join(", ") || "none")
                    + ". Untouched reservations · " + ((preview.untouched_saved || []).map(item => item.name).join(", ") || "none")
                    + ". Name after replacement · " + (preview.label_after || "default name") + "; number · " + (preview.number_after || "unassigned") + ".";
                $("replace-technical").textContent = JSON.stringify({ old_id: id, new_id: target, reviewed_etag: preview.base_etag,
                    new_connection_id: preview.new_connection_id, profile_revision_map: preview.profile_revision_map,
                    calibration_revision_map: preview.calibration_revision_map }, null, 2);
                $("replace-apply").disabled = false;
            }, id);
        });
        $("replace-apply").addEventListener("click", () => {
            if (!replacement) return;
            const plan = replacement;
            run(async () => {
                const result = await api("POST", path(plan.target, "/rebind"), Object.assign({}, plan.body, { new_connection_id: plan.preview.new_connection_id }), { ifMatch: plan.preview.base_etag });
                if (selectedId === plan.id) clearPlans(); ingestConfig(result); await refreshRoster(); if (selectedId === plan.id) message("Replacement applied to the active arrangement and exactly the selected saved arrangements."); announce("Tablet replacement applied.");
            });
        });
        return { render, identify, canIdentify };
    }
    const exported = { confirmModels, create };
    if (typeof module !== "undefined" && module.exports) module.exports = exported;
    else root.OperatorDevices = exported;
}(typeof window !== "undefined" ? window : globalThis));
