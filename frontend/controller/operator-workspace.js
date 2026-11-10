"use strict";
window.OperatorWorkspace = {
    containModalFocus(event, dialog = event.currentTarget) {
        if (event.key !== "Tab" || event.defaultPrevented || !dialog.matches(":modal")) return;
        const controls = [...dialog.querySelectorAll("button, input, select, textarea, a[href], summary, [tabindex]")]
            .filter(node => node.tabIndex >= 0 && !node.matches(":disabled") && node.getClientRects().length
                && window.getComputedStyle(node).visibility === "visible"
                && !node.closest("details:not([open]) > :not(summary)"));
        const index = controls.indexOf(document.activeElement);
        if (!controls.length || index < 0 || (event.shiftKey ? index === 0 : index === controls.length - 1)) {
            event.preventDefault();
            (controls.length ? controls[event.shiftKey ? controls.length - 1 : 0] : dialog).focus();
        }
    },
    create({ state, labelFor, arrangementDirty, arrangementPreview, imageDirty, applyArrangement, showImage, discardArrangement, discardImage,
        commitTask, renderStage, stageNames, onViewChange = () => {}, selectTablet, canCommit }) {
        const { $, setTextIfChanged } = window.OperatorDom;
        let pending = null, resolving = false, issueRequest = 0;
        const issues = new Map(), rosterRows = new Map(), stripRows = new Map();
        const stage = document.querySelector(".wall-stage"), arrangeTools = document.querySelector(".arrange-tools");
        const powerFor = id => {
            const project = window.OperatorStage && window.OperatorStage.powerReadiness;
            return project && state.roster ? project(state.roster[id], { stale: !!state.rosterError, checkedAt: state.rosterCheckedAt }) : null;
        };
        const powerText = power => power && (power.warning || power.stale || power.state === "unknown") ? power.label : "";
        const chooserButton = $("image-chooser-summary"), chooserBody = $("image-chooser-body");
        const chooserQuery = typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 48.01rem)") : null;
        let stageTask = null, joiningHasTablets = null, chooserHadFocus = false;
        function setChooser(open, moveFocus) {
            if (!chooserBody || !chooserButton) return;
            chooserBody.hidden = !open;
            chooserButton.setAttribute("aria-expanded", String(open));
            if (moveFocus) (open ? $("image-search") : chooserButton).focus({ preventScroll: true });
        }
        if (chooserQuery && chooserButton && chooserBody) {
            if (typeof chooserQuery.addEventListener === "function") chooserQuery.addEventListener("change", () => {
                if (chooserQuery.matches) {
                    setChooser(true, chooserHadFocus || document.activeElement === chooserButton);
                    chooserHadFocus = false;
                }
            });
            setChooser(chooserQuery.matches || !chooserBody.hidden, false);
            chooserButton.addEventListener("focus", () => { chooserHadFocus = true; });
            chooserButton.addEventListener("blur", () => { if (!chooserQuery.matches) chooserHadFocus = false; });
            chooserButton.addEventListener("click", () => setChooser(chooserBody.hidden, true));
        }
        function focusGallery() {
            setChooser(true, false);
            const gallery = $("image-gallery");
            const target = gallery.querySelector("button[tabindex=\"0\"]") || gallery;
            gallery.scrollIntoView({ block: "start" });
            target.focus({ preventScroll: true });
        }
        if ($("jump-to-library")) $("jump-to-library").addEventListener("click", focusGallery);
        if ($("first-wall-join-action")) $("first-wall-join-action").addEventListener("click", () => {
            $("tablet-joining").open = true;
            $("tablet-joining").querySelector("summary").focus();
        });
        if ($("first-wall-arrange-action")) $("first-wall-arrange-action").addEventListener("click", async () => {
            if (await open("show")) $("grid-2x2").focus();
        });
        if ($("first-wall-image-action")) $("first-wall-image-action").addEventListener("click", async () => {
            if (await open("content")) focusGallery();
        });
        const anyOnline = () => !state.rosterError && Object.values(state.roster).some(device => device.online);
        const shortEvidence = evidence => String(evidence.text || "").split(" · ")[0] || "Needs review";
        const positionTag = id => {
            const number = (state.roster[id] || {}).number;
            return Number.isInteger(number) && number > 0 ? "#" + number : "";
        };
        const orderedIds = ids => ids.slice().sort((a, b) => typeof window.OperatorState.compareIds === "function"
            ? window.OperatorState.compareIds(state.roster, state.deviceLabels || {}, a, b) : a.localeCompare(b));
        function revealRow(id, trigger) {
            return revealIssue(id, trigger && trigger.closest ? trigger.closest("li") : trigger, trigger);
        }
        function renderExceptionRail(ids, evidence) {
            const attention = ids.filter(id => window.OperatorState.needsAttention(evidence.get(id)));
            const ordered = orderedIds(attention).concat(orderedIds(ids.filter(id => !window.OperatorState.needsAttention(evidence.get(id)))));
            const fleet = window.OperatorStage && window.OperatorStage.fleetPower(state.rosterError ? [] : ids
                .filter(id => window.OperatorState.entries(state.operatorConfig.layout)[id].participating !== false)
                .map(id => ({ id, online: !!state.roster[id] && state.roster[id].online === true, power: powerFor(id) })));
            const wantedStrip = attention.slice(0, 4);
            const strip = $("exception-strip"), roster = $("exception-roster");
            if (strip) {
                for (const [id, row] of stripRows) if (!wantedStrip.includes(id)) { row.remove(); stripRows.delete(id); }
                wantedStrip.forEach((id, index) => {
                    const item = evidence.get(id);
                    let row = stripRows.get(id);
                    if (!row) {
                        row = document.createElement("li");
                        row.button = document.createElement("button");
                        row.button.type = "button";
                        row.button.className = "chip exception-chip";
                        row.button.addEventListener("click", () => revealRow(id, row.button));
                        row.append(row.button);
                        stripRows.set(id, row);
                    }
                    const tag = positionTag(id), name = labelFor ? labelFor(id) : id;
                    row.dataset.status = item.status;
                    row.button.dataset.deviceId = id;
                    setTextIfChanged(row.button, (tag ? tag + " " : "") + shortEvidence(item));
                    row.button.setAttribute("aria-label", name + ", " + item.text + ". Review recovery.");
                    if (strip.children[index] !== row) strip.insertBefore(row, strip.children[index] || null);
                });
            }
            const focused = roster && roster.contains(document.activeElement) ? document.activeElement : null;
            if (roster) {
                for (const [id, row] of rosterRows) if (!ordered.includes(id)) { row.remove(); rosterRows.delete(id); }
                ordered.forEach((id, index) => {
                    const item = evidence.get(id);
                    let row = rosterRows.get(id);
                    if (!row) {
                        row = document.createElement("li");
                        row.className = "exception-item";
                        row.button = document.createElement("button");
                        row.button.type = "button";
                        row.button.className = "exception-review";
                        row.number = document.createElement("span"); row.number.className = "exception-number";
                        row.name = document.createElement("span"); row.name.className = "exception-name";
                        row.state = document.createElement("span"); row.state.className = "exception-state";
                        row.power = document.createElement("span"); row.power.className = "exception-power";
                        row.power.hidden = true;
                        row.button.append(row.number, row.name, row.state, row.power);
                        row.button.addEventListener("click", () => revealRow(id, row.button));
                        row.append(row.button);
                        rosterRows.set(id, row);
                    }
                    const tag = positionTag(id), name = labelFor ? labelFor(id) : id;
                    const power = powerFor(id), powerLabel = powerText(power);
                    row.dataset.deviceId = id; row.dataset.status = item.status;
                    row.dataset.powerState = powerLabel ? power.state : "";
                    row.button.dataset.deviceId = id;
                    setTextIfChanged(row.number, tag || "–");
                    setTextIfChanged(row.name, name);
                    setTextIfChanged(row.state, item.text);
                    setTextIfChanged(row.power, powerLabel);
                    row.power.hidden = !powerLabel || !!(fleet && state.roster[id] && state.roster[id].online && power.state === fleet.state);
                    row.button.setAttribute("aria-label", name + ", " + item.text
                        + (powerLabel ? ", " + powerLabel : "") + ". Review recovery.");
                    if (roster.children[index] !== row) roster.insertBefore(row, roster.children[index] || null);
                });
            }
            if (focused && focused.isConnected && document.activeElement !== focused) focused.focus({ preventScroll: true });
            if (focused && roster && roster.contains(focused) && typeof focused.getBoundingClientRect === "function") {
                const rowBox = focused.getBoundingClientRect(), box = roster.getBoundingClientRect();
                if (rowBox.top < box.top) roster.scrollTop -= box.top - rowBox.top;
                else if (rowBox.bottom > box.bottom) roster.scrollTop += rowBox.bottom - box.bottom;
            }
            if ($("exception-count")) $("exception-count").textContent = attention.length
                ? attention.length + (attention.length === 1 ? " needs attention" : " need attention") : "No attention";
            if ($("position-count")) $("position-count").textContent = ids.length + (ids.length === 1 ? " position" : " positions");
            if ($("attention-heading")) {
                $("attention-heading").hidden = !attention.length;
                $("attention-heading").textContent = "Needs attention (" + attention.length + ")";
            }
            if ($("exception-empty")) $("exception-empty").hidden = !!ids.length;
            if ($("wall-status-summary")) setTextIfChanged($("wall-status-summary"), attention.length
                ? attention.length + (attention.length === 1 ? " needs attention" : " need attention") : "No attention");
            if ($("wall-power-summary")) {
                setTextIfChanged($("wall-power-summary"), fleet
                    ? "Screen wake lock: all " + fleet.count + " online tablets report " + fleet.label + ". Browser report, not proof the screen is lit." : "");
                $("wall-power-summary").hidden = !fleet;
            }
            return attention;
        }
        async function resolve(reason, except) {
            const nextKind = () => arrangementDirty() && except !== "arrangement" ? "arrangement"
                : imageDirty() && except !== "image" ? "image" : null;
            if (!nextKind()) return true;
            if (resolving) return false;
            resolving = true;
            const dialog = $("draft-resolution"), trigger = document.activeElement;
            const containFocus = event => window.OperatorWorkspace.containModalFocus(event, dialog);
            document.addEventListener("keydown", containFocus);
            try {
                for (let kind = nextKind(); kind; kind = nextKind()) {
                    $("draft-resolution-text").textContent = reason + ". " + (kind === "arrangement"
                        ? "Your arrangement preview has not been applied. Applying changes geometry only."
                        : "Your image preview has not been shown. Showing changes content only.");
                    $("resolve-commit").textContent = kind === "arrangement" ? "Apply arrangement" : "Show image";
                    $("resolve-commit").disabled = !canCommit(kind);
                    dialog.showModal();
                    const choice = await new Promise(done => { pending = done; });
                    pending = null; dialog.close();
                    if (choice === "stay") return false;
                    if (choice === "discard") {
                        if (kind === "arrangement") discardArrangement(); else discardImage();
                        renderStage();
                    } else if (kind === "arrangement") await applyArrangement(); else await showImage();
                    if (kind === "arrangement" ? arrangementDirty() : imageDirty()) return false;
                }
                return true;
            } finally {
                document.removeEventListener("keydown", containFocus);
                resolving = false; pending = null; dialog.close();
                for (const node of [trigger, $("compact-task-select"), $("tab-" + state.tabName), $("btn-wall-health")]) {
                    if (node && node.isConnected && !node.disabled && node.getClientRects().length
                            && window.getComputedStyle(node).visibility === "visible") {
                        node.focus({ preventScroll: true });
                        break;
                    }
                }
            }
        }
        for (const choice of ["commit", "discard", "stay"]) $("resolve-" + choice).addEventListener("click", () => { if (pending) pending(choice); });
        $("draft-resolution").addEventListener("keydown", window.OperatorWorkspace.containModalFocus);
        $("draft-resolution").addEventListener("close", () => { if (!$("draft-resolution").open && pending) pending("stay"); });
        $("draft-resolution").addEventListener("cancel", event => { event.preventDefault(); if (pending) pending("stay"); });
        async function open(name, options = {}) {
            if (name === "content" && !await resolve("Open Images", "image")) return false;
            if (name === "show" && !await resolve("Open Arrange", "arrangement")) return false;
            return commitTask(name, options);
        }
        function issuePresent(id) {
            const config = state.operatorConfig;
            return !!config && !!window.OperatorState.entries(config.layout)[id];
        }
        function revealIssue(id, row, trigger) {
            const request = ++issueRequest;
            return Promise.resolve(open("tablet", { persist: true })).then(opened => {
                if (!opened || request !== issueRequest) return false;
                if (!row || row.isConnected === false || !issuePresent(id)) return false;
                selectTablet(id, { reveal: true, taskOpened: true, trigger: trigger || row.firstElementChild });
                return true;
            });
        }
        function render(view = window.OperatorState.stageView(state)) {
            const arrangement = arrangementDirty(), image = imageDirty();
            if ($("operator-connection")) $("operator-connection").textContent = state.connectionText || "Connecting to the wall…";
            const hasPreview = arrangementPreview();
            const mode = view.mode;
            document.body.dataset.task = { show: "arrange", tablet: "tablets", content: "images", saved: "saved", system: "settings" }[state.tabName] || "tablets";
            document.body.dataset.stageMode = mode;
            $("compact-task-select").value = state.tabName;
            document.body.dataset.connection = state.rosterError ? "stale" : state.configLoaded ? "current" : "loading";
            document.body.dataset.outputDirty = String(arrangement || image);
            const wallEmpty = !state.base || !Object.keys(window.OperatorState.entries(state.base)).length;
            if ($("wall-context-tablet")) $("wall-context-tablet").hidden = !wallEmpty;
            if ($("first-wall-steps")) {
                $("first-wall-steps").hidden = !wallEmpty;
                const online = state.rosterError ? 0 : Object.values(state.roster).filter(device => device.online).length;
                setTextIfChanged($("first-wall-join-status"), online ? online + " tablets online" : "No tablets yet");
                setTextIfChanged($("first-wall-arrange-status"), "Not arranged yet");
                setTextIfChanged($("first-wall-image-status"), "No image shown yet");
                $("first-wall-join").dataset.done = String(online > 0);
                $("first-wall-arrange").dataset.done = String(!wallEmpty);
                $("first-wall-image").dataset.done = String(!!(state.scene && state.scene.content && state.scene.content.type === "image"));
            }
            const noTablets = !Object.keys(state.roster).length;
            if (joiningHasTablets !== !noTablets) { $("tablet-joining").open = noTablets; joiningHasTablets = !noTablets; }
            $("image-details-disclosure").hidden = $("presentation-checks").hidden = $("stage-technical").hidden = arrangeTools.hidden = noTablets;
            if (stageTask !== state.tabName) {
                const host = $("wall-context-" + state.tabName) || $("wall-context-park");
                host.append(stage);
                stageTask = state.tabName;
            }
            const names = stageNames();
            if ($("commit-draft-name")) setTextIfChanged($("commit-draft-name"), "Draft: " + (image && names.pending || "None"));
            if ($("commit-applied-name")) setTextIfChanged($("commit-applied-name"), "On wall: " + (names.unavailable ? "Unavailable image" : names.applied || "No image"));
            const shownType = state.scene && state.scene.content && state.scene.content.type;
            const label = mode === "live" ? names.unavailable ? "Unavailable image" : names.applied ? state.tabName === "content" ? "Showing" : "Showing " + names.applied
                : !wallEmpty && { color: "Showing tablet colours", calibration: "Showing calibration pattern" }[shownType] || "Nothing shown"
                : "Preview · " + (mode === "image-preview" ? names.pending : "Arrangement");
            if ($("stage-applied-chip")) {
                $("stage-applied-chip").hidden = !names.applied && !names.unavailable;
                $("stage-applied-chip").textContent = names.unavailable ? "Applied: unavailable" : names.applied ? "Applied: " + names.applied : "";
            }
            if ($("stage-draft-chip")) {
                $("stage-draft-chip").hidden = !image || !names.pending;
                $("stage-draft-chip").textContent = image && names.pending ? "Draft: " + names.pending : "";
            }
            if ($("draft-state")) {
                $("draft-state").textContent = image ? "Draft · not on wall"
                    : state.scene && state.scene.content ? "Applied content" : "No image selected";
            }
            document.body.dataset.stageIdentity = !names.unavailable && (!!names.applied || image) ? "chips" : "text";
            if ($("wall-checked")) {
                const checked = state.rosterCheckedAt ? Date.parse(state.rosterCheckedAt) : NaN;
                $("wall-checked").hidden = !Number.isFinite(checked);
                $("wall-checked").textContent = Number.isFinite(checked)
                    ? "Checked " + new Date(checked).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
            }
            if ($("stage-mode-label").textContent !== label) $("stage-mode-label").textContent = label;
            $("stage-mode").hidden = state.tabName === "content" && mode === "live" && label === $("image-title").textContent;
            const description = { live: "", "arrangement-preview": "Arrangement preview, not applied", "image-preview": "Image preview, not shown" }[mode];
            if ($("stage-mode-description").textContent !== description) $("stage-mode-description").textContent = description;
            $("view-toggle").hidden = mode === "live" && (!state.viewLive || !hasPreview && !image);
            $("view-toggle").textContent = state.viewLive ? "View preview" : "View applied";
            $("btn-cancel").hidden = !arrangement;
            $("wall-empty").hidden = state.tabName !== "content" || !state.configLoaded || hasPreview || !wallEmpty;
            $("empty-add-tablets").textContent = anyOnline() ? "Arrange tablets" : "Add tablets";
            const config = state.operatorConfig;
            if (config) {
                const ids = Object.keys(window.OperatorState.entries(config.layout));
                const evidence = new Map(ids.map(id => [id, window.OperatorState.tabletState(config, id, performance.now())]));
                for (const [id, row] of issues) if (!ids.includes(id)) { row.remove(); issues.delete(id); }
                for (const id of ids) {
                    const item = evidence.get(id);
                    let row = issues.get(id);
                    if (!row) {
                        row = document.createElement("li"); row.className = "issue-row"; row.dataset.deviceId = id;
                        const button = document.createElement("button"); button.type = "button"; button.className = "btn issue-action";
                        button.addEventListener("click", () => revealIssue(id, row, button));
                        row.append(button); $("wall-issues").append(row); issues.set(id, row);
                    }
                    row.hidden = !window.OperatorState.needsAttention(item);
                    const device = state.roster[id] || {}, number = device.number;
                    const name = labelFor ? labelFor(id) : state.deviceLabels[id] || device.label || "Tablet " + (number || "unassigned");
                    row.firstElementChild.textContent = name + " · " + item.text + " · Review recovery";
                    row.dataset.status = item.status;
                }
                renderExceptionRail(ids, evidence);
            }
            if ($("issues-empty")) {
                const visibleIssues = [...issues.values()].filter(row => !row.hidden).length;
                $("issues-empty").hidden = !!visibleIssues;
                $("issues-empty").textContent = state.rosterError ? "Status is stale. Use Refresh status to check the wall."
                    : !issues.size ? "No active positions yet. Arrange the connected tablets to begin."
                    : "No current issues.";
            }
            const wifi = state.readiness && state.readiness.wifi;
            $("join-network").textContent = wifi && wifi.known && wifi.name ? "Network · " + wifi.name : "Network name is not reported. Use the same network as the wall server.";
        }
        $("compact-task-select").addEventListener("change", async event => {
            await open(event.target.value, { focus: false, persist: true });
            event.target.value = state.tabName;
        });
        $("view-toggle").addEventListener("click", () => {
            const toggle = $("view-toggle"), search = $("image-search"), restore = document.activeElement === toggle;
            state.viewLive = !state.viewLive; onViewChange(); render(); renderStage();
            if (restore && toggle.hidden && (typeof search.getClientRects !== "function" || search.getClientRects().length)) search.focus({ preventScroll: true });
        });
        $("empty-add-tablets").addEventListener("click", () => open(anyOnline() ? "show" : "tablet", { focus: true, persist: true }));
        $("add-image").addEventListener("click", () => {
            $("image-addition").open = true;
            ($("upload-form").hidden ? $("image-addition").querySelector("summary") : $("upload-file")).focus();
        });
        return { open, resolve, render, revealIssue, destroy() { if (pending) pending("stay"); $("draft-resolution").close(); } };
    }
};
