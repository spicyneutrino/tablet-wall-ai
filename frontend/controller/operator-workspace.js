"use strict";
window.OperatorWorkspace = {
    create({ state, labelFor, arrangementDirty, arrangementPreview, imageDirty, applyArrangement, showImage, discardArrangement, discardImage,
        commitTask, renderStage, stageNames, onViewChange = () => {}, selectTablet, canCommit }) {
        const { $ } = window.OperatorDom;
        let pending = null, resolving = false;
        const issues = new Map();
        const stage = document.querySelector(".wall-stage"), arrangeTools = document.querySelector(".arrange-tools");
        let stageTask = null, joiningHasTablets = null;
        const anyOnline = () => !state.rosterError && Object.values(state.roster).some(device => device.online);
        async function resolve(reason, except) {
            const nextKind = () => arrangementDirty() && except !== "arrangement" ? "arrangement"
                : imageDirty() && except !== "image" ? "image" : null;
            if (!nextKind()) return true;
            if (resolving) return false;
            resolving = true;
            const dialog = $("draft-resolution"), trigger = document.activeElement;
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
                resolving = false; pending = null; dialog.close();
                if (trigger && trigger.isConnected && !trigger.disabled) trigger.focus({ preventScroll: true });
            }
        }
        for (const choice of ["commit", "discard", "stay"]) $("resolve-" + choice).addEventListener("click", () => { if (pending) pending(choice); });
        $("draft-resolution").addEventListener("cancel", event => { event.preventDefault(); if (pending) pending("stay"); });
        async function open(name, options = {}) {
            if (name === "content" && !await resolve("Open Images", "image")) return false;
            if (name === "show" && !await resolve("Open Arrange", "arrangement")) return false;
            return commitTask(name, options);
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
            const noTablets = !Object.keys(state.roster).length;
            if (joiningHasTablets !== !noTablets) { $("tablet-joining").open = noTablets; joiningHasTablets = !noTablets; }
            $("image-details-disclosure").hidden = $("stage-technical").hidden = arrangeTools.hidden = noTablets;
            if (stageTask !== state.tabName) {
                const host = $("wall-context-" + state.tabName) || $("wall-context-park");
                host.append(stage);
                stageTask = state.tabName;
            }
            const names = stageNames();
            const shownType = state.scene && state.scene.content && state.scene.content.type;
            const label = mode === "live" ? names.unavailable ? "Unavailable image" : names.applied ? state.tabName === "content" ? "Showing" : "Showing " + names.applied
                : !wallEmpty && { color: "Showing tablet colours", calibration: "Showing calibration pattern" }[shownType] || "Nothing shown"
                : "Preview · " + (mode === "image-preview" ? names.pending : "Arrangement");
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
                for (const [id, row] of issues) if (!ids.includes(id)) { row.remove(); issues.delete(id); }
                for (const id of ids) {
                    const evidence = window.OperatorState.tabletState(config, id, performance.now());
                    let row = issues.get(id);
                    if (!row) {
                        row = document.createElement("li"); row.className = "issue-row"; row.dataset.deviceId = id;
                        const button = document.createElement("button"); button.type = "button"; button.className = "btn issue-action";
                        button.addEventListener("click", () => { selectTablet(id); open("tablet", { focus: true, persist: true }); });
                        row.append(button); $("wall-issues").append(row); issues.set(id, row);
                    }
                    row.hidden = evidence.showing || evidence.status === "excluded";
                    const device = state.roster[id] || {}, number = device.number;
                    const name = labelFor ? labelFor(id) : state.deviceLabels[id] || device.label || "Tablet " + (number || "unassigned");
                    row.firstElementChild.textContent = name + " · " + evidence.text + " · Review recovery";
                    row.dataset.status = evidence.status;
                }
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
        return { open, resolve, render, destroy() { if (pending) pending("stay"); $("draft-resolution").close(); } };
    }
};
