"use strict";
window.OperatorWorkspace = {
    create({ state, labelFor, arrangementDirty, arrangementPreview, imageDirty, applyArrangement, showImage, discardArrangement, discardImage,
        commitTask, renderStage, refreshReadiness, refreshStatus, selectTablet, canCommit }) {
        const $ = id => document.getElementById(id);
        let pending = null, resolving = false;
        const issues = new Map();
        const stage = document.querySelector(".wall-stage");
        let stageTask = null;
        let emptyRoster = null;
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
        function render() {
            const arrangement = arrangementDirty(), image = imageDirty();
            if ($("operator-connection")) $("operator-connection").textContent = state.connectionText || "Connecting to the wall…";
            const hasPreview = arrangementPreview();
            const mode = state.viewLive || !hasPreview && !image ? "live" : hasPreview ? "arrangement-preview" : "image-preview";
            document.body.dataset.task = { show: "arrange", tablet: "tablets", content: "images", saved: "saved", system: "settings" }[state.tabName] || "tablets";
            document.body.dataset.stageMode = mode;
            document.body.dataset.connection = state.rosterError ? "stale" : state.configLoaded ? "current" : "loading";
            document.body.dataset.outputDirty = String(arrangement || image);
            if (stageTask !== state.tabName) {
                const host = $("wall-context-" + state.tabName) || $("wall-context-park");
                host.append(stage);
                stageTask = state.tabName;
            }
            const connected = Object.values(state.roster).filter(device => device.online).length;
            $("connected-summary").textContent = state.rosterError ? "Connections stale" : connected + " connected";
            const joining = $("tablet-joining");
            const empty = !Object.keys(state.roster).length;
            if (empty && emptyRoster !== true) joining.open = true;
            else if (!empty && emptyRoster === true && !joining.contains(document.activeElement)) joining.open = false;
            emptyRoster = empty;
            $("stage-mode-label").textContent = { live: "Applied configuration", "arrangement-preview": "Arrangement preview · not applied", "image-preview": "Image preview · not shown" }[mode];
            $("view-live").hidden = mode === "live";
            $("view-preview").hidden = !state.viewLive || !hasPreview && !image;
            const summary = $("arrange-review-summary");
            if (summary) summary.textContent = hasPreview ? "Apply changes geometry only. The applied image stays unchanged."
                : arrangement ? "Grid choices are local. Preview arrangement before applying. The diagram still shows the live wall."
                : "No arrangement changes are pending. Adjust positions or preview a grid to begin.";
            if (!arrangement && document.activeElement === $("btn-cancel")) $("task-arrange").focus({ preventScroll: true });
            $("btn-cancel").hidden = !arrangement;
            $("wall-empty").hidden = !state.configLoaded || hasPreview || !!state.base && Object.keys(window.OperatorState.entries(state.base)).length > 0;
            $("empty-add-tablets").textContent = !state.rosterError && Object.values(state.roster).some(device => device.online) ? "Arrange tablets" : "Add tablets";
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
                    : "No current problems are reported for the participating wall. Image display still requires current matching paint reports.";
            }
            const wifi = state.readiness && state.readiness.wifi;
            $("join-network").textContent = wifi && wifi.known && wifi.name ? "Network · " + wifi.name : "Network name is not reported. Use the same network as the wall server.";
        }
        $("view-live").addEventListener("click", () => { state.viewLive = true; render(); renderStage(); });
        $("view-preview").addEventListener("click", () => { state.viewLive = false; render(); renderStage(); });
        $("empty-add-tablets").addEventListener("click", () => open(!state.rosterError && Object.values(state.roster).some(device => device.online) ? "show" : "tablet", { focus: true, persist: true }));
        $("join-arrange").addEventListener("click", () => open("show", { focus: true, persist: true }));
        $("join-refresh").addEventListener("click", async () => { await Promise.all([refreshReadiness(), refreshStatus()]); render(); });
        $("add-tablets").addEventListener("click", () => {
            $("tablet-joining").open = true;
            $("tablet-joining").querySelector("summary").focus();
        });
        $("add-image").addEventListener("click", () => {
            $("image-addition").open = true;
            ($("upload-form").hidden ? $("image-addition").querySelector("summary") : $("upload-file")).focus();
        });
        return { open, resolve, render, destroy() { if (pending) pending("stay"); $("draft-resolution").close(); } };
    }
};
