"use strict";
(function (root) {
    const { setTextIfChanged } = typeof module !== "undefined" && module.exports
        ? require("./operator-dom.js") : root.OperatorDom;

    function liveViewportText(viewport) {
        return viewport
            ? "Selected tablet: " + viewport.width + " × " + viewport.height + " CSS px · DPR " + viewport.dpr + " · " + viewport.orientation + "° · " + viewport.mode
            : "Waiting for the selected tablet’s online viewport at 100% zoom. Advanced manual entry is available.";
    }

    function updateLiveViewport(node, viewport) {
        setTextIfChanged(node, liveViewportText(viewport));
    }

    function createPayloads({ fields: el, num, ValidationError = Error, markInvalid = () => {} }) {
        function requirePositive(label, input) {
            const value = num(input.value);
            if (value === null || value <= 0) {
                markInvalid(input, true);
                throw new ValidationError(label + " must be a positive number.");
            }
            markInvalid(input, false);
            return value;
        }

        function requireNonNegative(label, input) {
            const value = num(input.value);
            if (value === null || value < 0) {
                markInvalid(input, true);
                throw new ValidationError(label + " must be a non-negative number.");
            }
            markInvalid(input, false);
            return value;
        }

        function requireFinite(label, input) {
            const value = num(input.value);
            if (value === null) {
                markInvalid(input, true);
                throw new ValidationError(label + " must be a number.");
            }
            markInvalid(input, false);
            return value;
        }

        function requireInteger(label, input, minimum) {
            const value = num(input.value);
            if (value === null || !Number.isInteger(value) || value < minimum) {
                markInvalid(input, true);
                throw new ValidationError(label + " must be an integer of at least " + minimum + ".");
            }
            markInvalid(input, false);
            return value;
        }

        function requireText(label, input, minimum, maximum) {
            const value = input.value.trim();
            if (value.length < minimum || value.length > maximum) {
                markInvalid(input, true);
                throw new ValidationError(label + " must be " + minimum + " to " + maximum + " characters.");
            }
            markInvalid(input, false);
            return value;
        }

        function buildProfileBody() {
            const panelWidthRaw = el.profilePixelWidth.value.trim();
            const panelHeightRaw = el.profilePixelHeight.value.trim();
            let panelPixels = null;
            if (panelWidthRaw || panelHeightRaw) {
                const width = requirePositive("Panel pixel width", el.profilePixelWidth);
                const height = requirePositive("Panel pixel height", el.profilePixelHeight);
                if (!Number.isInteger(width) || !Number.isInteger(height)) {
                    markInvalid(el.profilePixelWidth, true);
                    markInvalid(el.profilePixelHeight, true);
                    throw new ValidationError("Panel pixel dimensions must be whole numbers.");
                }
                panelPixels = { width: width, height: height };
            }
            return {
                active_width_mm: requirePositive("Active width", el.profileActiveWidth),
                active_height_mm: requirePositive("Active height", el.profileActiveHeight),
                bezels: {
                    left: requireNonNegative("Left bezel", el.profileBezelLeft),
                    top: requireNonNegative("Top bezel", el.profileBezelTop),
                    right: requireNonNegative("Right bezel", el.profileBezelRight),
                    bottom: requireNonNegative("Bottom bezel", el.profileBezelBottom)
                },
                panel_pixels: panelPixels,
                label: requireText("Label", el.profileLabel, 1, 80),
                provenance: requireText("Provenance", el.profileProvenance, 1, 40)
            };
        }

        function buildCalibrationBody() {
            if (!el.calOrientation.value || !["tab", "fullscreen", "standalone"].includes(el.calMode.value)) {
                throw new ValidationError("Choose the tablet orientation and mode.");
            }
            const orientation = Number(el.calOrientation.value);
            if ([0, 90, 180, 270].indexOf(orientation) === -1) {
                throw new ValidationError("Orientation must be 0, 90, 180 or 270 degrees.");
            }
            const quarter = Number(el.calQuarterTurn.value);
            if ([0, 1, 2, 3].indexOf(quarter) === -1) {
                throw new ValidationError("Quarter turn must be 0, 1, 2 or 3.");
            }
            const anchor = el.calAnchorEdge.value;
            if (["top-left", "top-right", "bottom-left", "bottom-right"].indexOf(anchor) === -1) {
                throw new ValidationError("Anchor edge is not supported.");
            }
            return {
                profile_revision: requireInteger("Profile revision", el.calProfileRevision, 1),
                viewport_width: requirePositive("Viewport width", el.calViewportWidth),
                viewport_height: requirePositive("Viewport height", el.calViewportHeight),
                dpr: requirePositive("Device pixel ratio", el.calDpr),
                orientation: orientation,
                mode: el.calMode.value,
                quarter_turn: quarter,
                panel_offset_mm: [
                    requireFinite("Panel offset X", el.calOffsetX),
                    requireFinite("Panel offset Y", el.calOffsetY)
                ],
                mm_per_css: [
                    requirePositive("mm per CSS pixel X", el.calMmCssX),
                    requirePositive("mm per CSS pixel Y", el.calMmCssY)
                ],
                anchor_edge: anchor,
                uncertainty_mm: requireNonNegative("Uncertainty", el.calUncertainty),
                ...(el.calMethod.value.trim() === "ruler-measured" ? { viewport_guard: true } : {}),
                method: requireText("Method", el.calMethod, 1, 80)
            };
        }

        return { buildProfileBody, buildCalibrationBody, requireInteger, requireNonNegative };
    }

    function create({ elements: el, physicalCalibration, refresh, state, num, markInvalid, ValidationError, deviceLabel, formatNumber, setInputValue, setSelectValue, api, syncTabDots, setMsg, errorDetail, profileFor, latestProfile, latestCalibration, numberedLabel, calibrationStatus, bodyMetrics, tabletForms, clearMsg, clearError, announce, resolveOutput, setBusy, handleWriteError }) {
        const { buildProfileBody, buildCalibrationBody, requireInteger, requireNonNegative } = createPayloads({ fields: el, num, ValidationError, markInvalid });
        function profileDefaults(profile, id = state.selectedId) {
            return {
                label: profile ? profile.label : deviceLabel(id, profile),
                provenance: profile ? profile.provenance : "manual",
                activeWidth: profile ? profile.active_width_mm : "",
                activeHeight: profile ? profile.active_height_mm : "",
                bezels: profile && profile.bezels ? profile.bezels : {
                    left: 0, top: 0, right: 0, bottom: 0
                },
                panelPixels: profile && profile.panel_pixels ? profile.panel_pixels : null
            };
        }

        function profileFieldValues(profile, id = state.selectedId) {
            const values = profileDefaults(profile, id);
            return {
                "profile-active-width": formatNumber(values.activeWidth, 3), "profile-active-height": formatNumber(values.activeHeight, 3),
                "profile-bezel-top": formatNumber(values.bezels.top, 3), "profile-bezel-right": formatNumber(values.bezels.right, 3),
                "profile-bezel-bottom": formatNumber(values.bezels.bottom, 3), "profile-bezel-left": formatNumber(values.bezels.left, 3),
                "profile-label": values.label, "profile-provenance": values.provenance,
                "profile-pixel-width": values.panelPixels ? formatNumber(values.panelPixels.width, 0) : "",
                "profile-pixel-height": values.panelPixels ? formatNumber(values.panelPixels.height, 0) : ""
            };
        }

        function fillProfileForm(profile) {
            for (const [id, value] of Object.entries(profileFieldValues(profile))) setInputValue(document.getElementById(id), value);
            state.profileDirty = false;
        }

        function fillViewport(viewport) {
            setInputValue(el.calViewportWidth, viewport ? viewport.width : "");
            setInputValue(el.calViewportHeight, viewport ? viewport.height : "");
            setInputValue(el.calDpr, viewport ? viewport.dpr : "");
            el.calOrientation.value = viewport ? String(viewport.orientation) : "";
            el.calMode.value = viewport ? viewport.mode : "";
        }

        function calibrationFieldValues(calibration, profile, id = state.selectedId) {
            const v = physicalCalibration.selectedViewport(state.roster, id);
            const c = calibration;
            return {
                "cal-profile-revision": c ? formatNumber(c.profile_revision, 0) : profile ? formatNumber(profile.revision, 0) : "",
                "cal-viewport-width": c ? formatNumber(c.viewport_width, 3) : v ? String(v.width) : "",
                "cal-viewport-height": c ? formatNumber(c.viewport_height, 3) : v ? String(v.height) : "",
                "cal-dpr": c ? formatNumber(c.dpr, 4) : v ? String(v.dpr) : "",
                "cal-orientation": c ? String(c.orientation) : v ? String(v.orientation) : "",
                "cal-mode": c ? c.mode : v ? v.mode : "", "cal-quarter-turn": c ? String(c.quarter_turn) : "0",
                "cal-anchor-edge": c ? c.anchor_edge : "top-left",
                "cal-offset-x": c ? formatNumber(c.panel_offset_mm[0], 3) : "", "cal-offset-y": c ? formatNumber(c.panel_offset_mm[1], 3) : "",
                "cal-mm-css-x": c ? formatNumber(c.mm_per_css[0], 6) : "", "cal-mm-css-y": c ? formatNumber(c.mm_per_css[1], 6) : "",
                "cal-uncertainty": c ? formatNumber(c.uncertainty_mm, 3) : "", "cal-method": c ? c.method : "manual"
            };
        }

        function fillCalibrationForm(calibration, profile) {
            for (const [id, value] of Object.entries(calibrationFieldValues(calibration, profile))) {
                const input = document.getElementById(id);
                if (input.tagName === "SELECT") setSelectValue(input, value); else setInputValue(input, value);
            }
            state.calDirty = false;
        }

        const rulerReview = new physicalCalibration.RulerReview();

        function rulerInputs() {
            const measurements = {};
            ["x", "y"].forEach(function (axis) {
                measurements[axis] = {
                    mm: document.getElementById("cal-ruler-mm-" + axis).value,
                    px: document.getElementById("cal-ruler-span-" + axis).value,
                    error: document.getElementById("cal-ruler-error-" + axis).value
                };
            });
            return measurements;
        }

        function rulerContext() {
            const viewport = physicalCalibration.selectedViewport(state.roster, state.selectedId);
            const revision = Number(el.calProfileRevision.value);
            const profile = profileFor(state.selectedId, revision);
            if (!profile) throw new Error("The selected profile revision is unavailable. Reload the tablet measurements.");
            const bodies = physicalCalibration.rulerCheckBodies(state.selectedId, revision,
                Number(el.calQuarterTurn.value), viewport, rulerInputs());
            return { viewport: viewport, bodies: bodies, key: JSON.stringify({ bodies: bodies, viewport: viewport, profile: profile }) };
        }

        function rulerSaveBlocked() {
            const measurements = rulerInputs();
            if (rulerReview.status === "idle" && !measurements.x.mm && !measurements.y.mm
                && el.calMethod.value.trim() !== "ruler-measured") return false;
            try { return !rulerReview.canSave(rulerContext().key); }
            catch (_) { return true; }
        }

        function invalidateRuler() {
            rulerReview.invalidate();
            document.getElementById("cal-ruler-decision").hidden = true;
            if (rulerReview.status === "stale") {
                const preview = document.getElementById("cal-ruler-preview");
                preview.hidden = false;
                preview.textContent = "Measurement or mapping changed. Check the current ruler measurements again before saving.";
            }
            el.btnCalibrationSave.disabled = state.busy || rulerSaveBlocked();
        }

        async function checkRuler() {
            if (state.busy || rulerReview.status === "checking") return;
            let context;
            try {
                context = rulerContext();
                rulerReview.begin(context.key);
                rememberFields("calibration");
                syncTabDots();
                const preview = document.getElementById("cal-ruler-preview");
                preview.hidden = false;
                preview.textContent = "Checking both CSS axes. Nothing has been saved.";
                document.getElementById("cal-ruler-decision").hidden = true;
                renderCalibrationHelper();
                const results = await Promise.all(context.bodies.map(function (body) {
                    return api("POST", "/api/v3/calibration-check", body);
                }));
                if (rulerContext().key !== context.key || !rulerReview.accept(context.key, results)) return;
                preview.textContent = "";
                results.forEach(function (result) {
                    const section = document.createElement("section");
                    const heading = document.createElement("h4");
                    heading.textContent = result.axis.toUpperCase() + " CSS axis maps to native panel "
                        + result.profile.native_axis + " at quarter turn " + result.profile.quarter_turn;
                    section.appendChild(heading);
                    const derived = result.derived;
                    const comparison = result.comparison;
                    [
                        "Full labelled span " + result.inputs.span_px + " CSS px. Measured "
                            + result.inputs.span_mm + " ± " + result.inputs.span_error_mm + " mm.",
                        "Derived " + formatNumber(derived.mm_per_css, 8) + " ± "
                            + formatNumber(derived.mm_per_css_uncertainty, 8) + " mm/CSS. " + derived.quality_label + ".",
                        "Supplied full panel " + result.profile.native_axis + " " + formatNumber(comparison.supplied_mm, 3)
                            + " mm from profile r" + result.profile.revision + ". Ruler-implied usable panel extent "
                            + formatNumber(comparison.implied_mm, 3) + " ± "
                            + formatNumber(result.extrapolated_uncertainty.measured_mm, 3) + " mm.",
                        result.decision.required ? "Disagreement. Choose explicitly below." : "Within the propagated comparison tolerance."
                    ].forEach(function (text) {
                        const p = document.createElement("p");
                        p.textContent = text;
                        section.appendChild(p);
                    });
                    preview.appendChild(section);
                });
                const note = document.createElement("p");
                note.textContent = "Both axes are measured separately. Browser insets can make the usable viewport smaller than the full panel, especially in tab or standalone mode. Review panel offsets below. No values were averaged or saved. Existing layout pins stay unchanged.";
                preview.appendChild(note);
                document.getElementById("cal-ruler-decision").hidden = false;
                preview.focus();
            } catch (error) {
                if (context && rulerReview.key !== context.key) return;
                invalidateRuler();
                setMsg(el.calibrationMsg, errorDetail(error), "err");
            } finally { renderCalibrationHelper(); }
        }

        function decideRuler(choice) {
            if (state.busy) return;
            try {
                const context = rulerContext();
                if (rulerReview.key !== context.key) throw new Error("The tablet or measurement changed. Check again.");
                rulerReview.decide(choice);
                document.getElementById("cal-ruler-decision").hidden = true;
                if (choice === "use_ruler") {
                    fillViewport(context.viewport);
                    const results = rulerReview.results;
                    setInputValue(el.calMmCssX, results[0].derived.mm_per_css);
                    setInputValue(el.calMmCssY, results[1].derived.mm_per_css);
                    setInputValue(el.calUncertainty, Math.max(...results.map(function (result) {
                        return result.extrapolated_uncertainty.measured_mm;
                    })));
                    setInputValue(el.calMethod, "ruler-measured");
                    rememberFields("calibration");
                    setMsg(el.calibrationMsg, "Ruler chosen. Review offsets and Save calibration to create a new revision. Supplied profile and existing layout pins stay unchanged.", "info");
                    renderCalibrationHelper();
                    el.btnCalibrationSave.focus();
                } else if (choice === "keep_supplied") {
                    setMsg(el.calibrationMsg, "Supplied measurements kept. Nothing was written; the profile and existing mapping stay unchanged. No ruler scale will be saved.", "ok");
                    document.getElementById("cal-use-ruler").focus();
                } else {
                    document.getElementById("cal-ruler-mm-x").value = "";
                    document.getElementById("cal-ruler-mm-y").value = "";
                    invalidateRuler();
                    setMsg(el.calibrationMsg, "Measure each line again using its current labelled span, then check both axes.", "info");
                    document.getElementById("cal-ruler-mm-x").focus();
                }
                syncTabDots();
            } catch (error) {
                invalidateRuler();
                setMsg(el.calibrationMsg, errorDetail(error), "err");
            }
            renderCalibrationHelper();
        }

        function renderCalibrationHelper() {
            const v = physicalCalibration.selectedViewport(state.roster, state.selectedId);
            updateLiveViewport(document.getElementById("cal-live-viewport"), v);
            document.getElementById("cal-use-viewport").disabled = !v || state.busy;
            document.getElementById("cal-use-ruler").disabled = !v || state.busy || rulerReview.status === "checking";
            if (rulerReview.key && ["checking", "review", "prepared"].includes(rulerReview.status)) {
                try { if (rulerContext().key !== rulerReview.key) invalidateRuler(); }
                catch (_) { invalidateRuler(); }
            }
            el.btnCalibrationSave.disabled = state.busy || rulerSaveBlocked();
        }

        async function loadRulerAddress() {
            const link = document.getElementById("cal-ruler-link");
            const note = document.getElementById("cal-ruler-address-note");
            try {
                const config = await api("GET", "/operator-config");
                const url = physicalCalibration.rulerUrl(config.tablet_origin);
                if (!url) throw new Error("No tablet origin");
                link.href = url;
                link.textContent = url;
                link.hidden = false;
                document.getElementById("cal-copy-ruler").hidden = false;
                note.textContent = "Open this address on the selected tablet in its existing browser identity.";
            } catch (_) {
                note.textContent = "Set the server’s tablet origin to a tablet-reachable HTTP(S) address. A loopback address works only on this computer.";
            }
        }

        function updateDeviceCardHeadings() {
            const id = state.selectedId;
            const profile = latestProfile(id);
            el.deviceCardName.textContent = id ? numberedLabel(id, profile) : "–";
            const status = calibrationStatus(profile, latestCalibration(id));
            el.deviceCardCal.textContent = status.text;
            el.deviceCardCal.dataset.kind = status.kind;
        }

        function updateCurrentLines() {
            const id = state.selectedId;
            const profile = latestProfile(id);
            const calibration = latestCalibration(id);
            const status = calibrationStatus(profile, calibration);

            if (profile) {
                const metrics = bodyMetrics(profile);
                el.profileCurrent.textContent = "Newest revision " + profile.revision
                    + " · active " + formatNumber(metrics.activeW, 1) + " × "
                    + formatNumber(metrics.activeH, 1) + " mm · body "
                    + formatNumber(metrics.bodyW, 1) + " × "
                    + formatNumber(metrics.bodyH, 1) + " mm.";
                el.profileCurrent.dataset.kind = "ok";
            } else {
                el.profileCurrent.textContent = "No profile saved for this tablet yet.";
                el.profileCurrent.dataset.kind = "warn";
            }

            if (!profile) {
                el.calibrationCurrent.textContent = "Save a profile before saving a calibration.";
                el.calibrationCurrent.dataset.kind = "warn";
            } else if (!calibration) {
                el.calibrationCurrent.textContent = "No calibration saved. Use the tablet ruler or enter measured calibration values manually.";
                el.calibrationCurrent.dataset.kind = "warn";
            } else if (calibration.profile_revision !== profile.revision) {
                el.calibrationCurrent.textContent = "Newest calibration is revision "
                    + calibration.revision + " for profile revision "
                    + calibration.profile_revision + " (stale for newest profile revision "
                    + profile.revision + ").";
                el.calibrationCurrent.dataset.kind = "warn";
            } else {
                el.calibrationCurrent.textContent = "Newest calibration is revision "
                    + calibration.revision + " for profile revision "
                    + calibration.profile_revision + " · " + status.text + ".";
                el.calibrationCurrent.dataset.kind = status.kind;
            }
        }

        function fieldsIn(group) {
            if (group === "model") return [document.getElementById("tablet-model")];
            return Array.from((group === "profile" ? el.profileForm : el.calibrationForm).querySelectorAll("input[id], select[id]"));
        }

        function fieldValues(group) {
            return Object.fromEntries(fieldsIn(group).map(input => [input.id, input.value]));
        }

        function rememberFields(group) {
            const id = state.formDeviceId;
            if (!id) return;
            const saved = tabletForms.get(id, group);
            const values = { ...fieldValues(group), ...(group !== "model" ? { _revision: saved?.baseline._revision || 0 } : {}) };
            const form = tabletForms.edit(id, group, values, state.etag);
            if (group === "profile") state.profileDirty = form.dirty;
            if (group === "calibration") state.calDirty = form.dirty;
            fieldsIn(group).forEach(input => { input.dataset.dirty = String(form.dirty); });
        }

        function retainFields(id, group, defaults) {
            const form = tabletForms.observe(id, group, defaults, state.etag);
            for (const input of fieldsIn(group)) {
                if (document.activeElement !== input && input.value !== form.values[input.id]) input.value = form.values[input.id];
                input.dataset.dirty = String(form.dirty);
            }
            if (group === "profile") state.profileDirty = form.dirty;
            if (group === "calibration") state.calDirty = form.dirty;
            if (form.conflict) setMsg(group === "calibration" ? el.calibrationMsg : el.profileMsg,
                "These saved measurements changed elsewhere. Your fields are retained. Discard them to use the current measurements, or compare before saving.", "err");
        }

        function populateDeviceCard() {
            const id = state.selectedId;
            if (!id) {
                el.deviceCardEmpty.hidden = false;
                el.deviceCardBody.hidden = true;
                state.formDeviceId = null;
                return;
            }

            el.deviceCardEmpty.hidden = true;
            el.deviceCardBody.hidden = false;
            const profile = latestProfile(id);
            const calibration = latestCalibration(id);
            const changed = state.formDeviceId !== id;

            if (changed) {
                rulerReview.reset();
                document.getElementById("cal-ruler-preview").hidden = true;
                document.getElementById("cal-ruler-decision").hidden = true;
                document.getElementById("cal-ruler-error-x").value = "";
                document.getElementById("cal-ruler-error-y").value = "";
                document.getElementById("cal-ruler-mm-x").value = "";
                document.getElementById("cal-ruler-mm-y").value = "";
                document.getElementById("cal-ruler-span-x").value = "200";
                document.getElementById("cal-ruler-span-y").value = "200";
            }
            updateDeviceCardHeadings();
            updateCurrentLines();
            const modelSelect = document.getElementById("tablet-model");
            const assignment = state.tabletAssignments[id] || { mode: "auto" };
            if (changed || !modelSelect.options.length) {
                modelSelect.textContent = "";
                [["", "Choose a confirmed model or manual measurements"], ["manual", "Manual measurements"]].concat(
                    Object.keys(state.tabletModels).map(function (key) { return [key, state.tabletModels[key].label]; })
                ).forEach(function (item) {
                    const option = document.createElement("option");
                    option.value = item[0]; option.textContent = item[1]; modelSelect.appendChild(option);
                });
                const defaultModel = assignment.mode === "explicit" ? assignment.model_id : assignment.mode === "manual" ? "manual" : "";
                const form = tabletForms.observe(id, "model", { "tablet-model": defaultModel }, state.etag);
                modelSelect.value = form.values["tablet-model"];
            }
            const record = state.roster[id] || {};
            const matches = (record.model_suggestions || []).filter(function (key) { return state.tabletModels[key]; });
            document.getElementById("tablet-model-status").textContent = matches.length === 1
                ? "Looks like " + state.tabletModels[matches[0]].label + ". Choose that model and Confirm only after checking the hardware. Screen signature is a suggestion, not proof."
                : matches.length ? "Ambiguous screen signature." : "Unknown screen signature.";
            renderCalibrationHelper();

            for (const group of ["profile", "calibration"]) {
                const saved = tabletForms.get(id, group), revision = (group === "profile" ? profile : calibration)?.revision || 0;
                if (changed || !saved || !saved.dirty) {
                    if (group === "profile") fillProfileForm(profile); else fillCalibrationForm(calibration, profile);
                    retainFields(id, group, { ...fieldValues(group), _revision: revision });
                } else retainFields(id, group, { ...saved.baseline, _revision: revision });
            }
            const defaultModel = assignment.mode === "explicit" ? assignment.model_id : assignment.mode === "manual" ? "manual" : "";
            retainFields(id, "model", { "tablet-model": defaultModel });
            state.formDeviceId = id;
        }

        async function saveProfile(event) {
            event.preventDefault();
            if (!state.selectedId || state.busy) return;
            clearMsg(el.profileMsg);
            clearError();

            let body;
            try {
                body = buildProfileBody();
            } catch (error) {
                setMsg(el.profileMsg, errorDetail(error), "err");
                announce(errorDetail(error), "err");
                el.profileForm.querySelector('[aria-invalid="true"]')?.focus();
                return;
            }

            rememberFields("profile");
            const id = state.selectedId, submitted = tabletForms.get(id, "profile");
            if (submitted.conflict) { setMsg(el.profileMsg, "Resolve the changed saved measurements first.", "err"); return; }
            if (!await resolveOutput("Save tablet measurements")) return;
            setBusy(true);
            try {
                const payload = await api(
                    "PUT",
                    "/api/v3/displays/" + encodeURIComponent(id),
                    body,
                    { ifMatch: submitted.baseEtag }
                );
                if (!payload || !payload.display || !payload.etag) {
                    throw new Error("The server returned an incomplete profile.");
                }
                tabletForms.saved(id, "profile", submitted.version, submitted.values, payload.etag);
                await refresh();
                if (state.selectedId === id) {
                    state.formDeviceId = null;
                    populateDeviceCard();
                }
                if (state.selectedId === id) setMsg(el.profileMsg, "Saved profile revision " + payload.display.revision + ".", "ok");
                announce("Saved profile revision " + payload.display.revision + ".", "ok");
            } catch (error) {
                handleWriteError(error, state.selectedId === id ? el.profileMsg : null);
            } finally {
                setBusy(false);
            }
        }

        async function saveCalibration(event) {
            event.preventDefault();
            if (!state.selectedId || state.busy) return;
            clearMsg(el.calibrationMsg);
            clearError();

            let body;
            try {
                if (rulerSaveBlocked()) throw new ValidationError("Check the current ruler measurements and choose Use ruler before saving. Keep supplied writes nothing.");
                body = buildCalibrationBody();
            } catch (error) {
                setMsg(el.calibrationMsg, errorDetail(error), "err");
                announce(errorDetail(error), "err");
                el.calibrationForm.querySelector('[aria-invalid="true"]')?.focus();
                return;
            }

            rememberFields("calibration");
            const id = state.selectedId, submitted = tabletForms.get(id, "calibration");
            if (submitted.conflict) { setMsg(el.calibrationMsg, "Resolve the changed saved measurements first.", "err"); return; }
            if (!await resolveOutput("Save tablet measurements")) return;
            setBusy(true);
            try {
                const payload = await api(
                    "PUT",
                    "/api/v3/calibrations/" + encodeURIComponent(id),
                    body,
                    { ifMatch: submitted.baseEtag }
                );
                if (!payload || !payload.calibration || !payload.etag) {
                    throw new Error("The server returned an incomplete calibration.");
                }
                tabletForms.saved(id, "calibration", submitted.version, submitted.values, payload.etag);
                await refresh();
                if (state.selectedId === id) {
                    state.formDeviceId = null;
                    populateDeviceCard();
                }
                if (state.selectedId === id) setMsg(el.calibrationMsg, "Saved calibration revision "
                    + payload.calibration.revision + " for profile revision "
                    + payload.calibration.profile_revision + ".", "ok");
                announce("Saved calibration revision " + payload.calibration.revision + ".", "ok");
            } catch (error) {
                handleWriteError(error, state.selectedId === id ? el.calibrationMsg : null);
            } finally {
                setBusy(false);
            }
        }

        return { requireNonNegative, requireInteger, profileFieldValues, fillViewport, calibrationFieldValues, rulerSaveBlocked, invalidateRuler, checkRuler, decideRuler, renderCalibrationHelper, loadRulerAddress, rememberFields, populateDeviceCard, saveProfile, saveCalibration };
    }

    const measurements = { create, createPayloads, liveViewportText, updateLiveViewport };
    if (typeof module !== "undefined" && module.exports) module.exports = measurements;
    else root.OperatorMeasurements = measurements;
})(typeof window !== "undefined" ? window : globalThis);
