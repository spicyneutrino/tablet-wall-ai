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
        commitMode, renderStage, stageNames, onViewChange = () => {}, selectTablet, canCommit, clearSelection = () => {}, lookup = window.OperatorDom.$, arrangeElement = null }) {
        const $ = lookup;
        const { setTextIfChanged } = window.OperatorDom;
        let pending = null, resolving = false, issueRequest = 0, joinOpen = false;
        const issues = new Map(), problemRows = new Map();
        const arrangeTools = arrangeElement || document.querySelector(".arrange-tools");
        const modeTab = { content: "tab-content", arrange: "tab-show", test: "tab-test" };
        const patternName = /^wall-pattern-/;
        const phone = window.matchMedia && window.matchMedia("(max-width: 47.99rem)");
        const onPhoneChange = () => render();
        if (phone) phone.addEventListener("change", onPhoneChange);
        const toolbar = document.querySelector(".stage-toolbar");
        const roster = $("roster");
        function fitRoster() {
            const mode = toolbar.querySelector(".mode-switch"), tools = toolbar.querySelector(".toolbar-tools");
            const strip = toolbar.querySelector(".roster-strip"), add = $("add-tablet");
            const gap = node => parseFloat(window.getComputedStyle(node).columnGap) || 0;
            const chips = [...roster.children];
            const chipsWidth = chips.reduce((width, chip) => width + chip.getBoundingClientRect().width, 0)
                + Math.max(0, chips.length - 1) * gap(roster);
            const required = mode.getBoundingClientRect().width + tools.getBoundingClientRect().width
                + chipsWidth + add.getBoundingClientRect().width + gap(strip) + 2 * gap(toolbar);
            toolbar.dataset.rosterRow = String(chips.length > 6 || required > toolbar.clientWidth);
        }
        const rosterObserver = window.ResizeObserver && new window.ResizeObserver(fitRoster);
        if (rosterObserver) {
            for (const node of [toolbar, roster, toolbar.querySelector(".mode-switch"), toolbar.querySelector(".toolbar-tools")]) rosterObserver.observe(node);
        }
        let joiningHasTablets = null;
        function focusGallery() {
            const gallery = $("image-gallery");
            const target = [gallery.querySelector("button[tabindex=\"0\"]"), $("image-search"), $("add-image")]
                .find(node => node && !node.disabled && (typeof node.getClientRects !== "function" || node.getClientRects().length));
            if (target) {
                target.scrollIntoView({ block: "nearest" });
                target.focus({ preventScroll: true });
            }
        }
        function joinCard() {
            const view = window.OperatorState.stageView(state);
            const empty = !state.base || !Object.keys(window.OperatorState.entries(state.base)).length;
            return empty && !Object.keys(state.roster).length && state.configLoaded && view.mode === "live";
        }
        function setupProgress() {
            const empty = !state.base || !Object.keys(window.OperatorState.entries(state.base)).length;
            const online = Object.values(state.roster).filter(device => device.online).length;
            const done = [online > 0, !empty, !!(state.scene && state.scene.content && state.scene.content.type === "image")];
            const current = done.indexOf(false);
            return { empty, online, done, current, complete: current === -1 };
        }
        function land() {
            if (!state.configLoaded || state.mode !== "content" || state.selectedId || arrangementDirty() || imageDirty()) return Promise.resolve(false);
            return setupProgress().current === 1 ? open("arrange") : Promise.resolve(false);
        }
        function openJoin(focus) {
            joinOpen = !joinCard(); render();
            const target = $("copy-tablet-url");
            if (focus && target && target.getClientRects().length) target.focus({ preventScroll: true });
        }
        function closeJoin() {
            if (!joinOpen) return false;
            joinOpen = false; render();
            const trigger = $("add-tablet");
            if (trigger.getClientRects().length) trigger.focus({ preventScroll: true });
            return true;
        }
        if ($("first-wall-join-action")) $("first-wall-join-action").addEventListener("click", () => openJoin(true));
        if ($("first-wall-arrange-action")) $("first-wall-arrange-action").addEventListener("click", async () => {
            clearSelection();
            if (await open("arrange")) $("grid-preview").focus();
        });
        if ($("first-wall-image-action")) $("first-wall-image-action").addEventListener("click", async () => {
            clearSelection();
            if (await open("content")) focusGallery();
        });
        document.addEventListener("click", event => {
            if (joinOpen && !event.target.closest("#join-strip, #add-tablet, #first-wall-join-action")) { joinOpen = false; render(); }
        });
        function revealRow(id, trigger) {
            return revealIssue(id, trigger && trigger.closest ? trigger.closest("li") : trigger, trigger);
        }
        function renderProblems(ids, evidence) {
            const attention = ids.filter(id => window.OperatorState.needsAttention(evidence.get(id)));
            const failures = state.rosterError ? [] : ids.filter(id => window.OperatorState.rosterStatus(evidence.get(id)).tone === "failure");
            const strip = $("exception-strip");
            const limit = phone && phone.matches ? 1 : 2;
            const shown = failures.slice(0, limit);
            const wanted = shown.concat(failures.length > limit ? ["+more"] : []);
            for (const [id, row] of problemRows) if (!wanted.includes(id)) { row.remove(); problemRows.delete(id); }
            wanted.forEach((id, index) => {
                let row = problemRows.get(id);
                if (!row) {
                    row = document.createElement("li");
                    row.button = document.createElement("button");
                    row.button.type = "button";
                    row.button.className = "problem-chip";
                    row.button.addEventListener("click", () => {
                        if (id === "+more" && phone && phone.matches) {
                            if (document.body.dataset.view !== "tablets") $("nav-tablets").click();
                        }
                        else revealRow(row.button.dataset.problemDevice, row.button);
                    });
                    row.append(row.button);
                    problemRows.set(id, row);
                }
                if (id === "+more") {
                    const rest = failures.slice(limit);
                    row.dataset.status = "more";
                    row.button.dataset.problemDevice = rest[0];
                    setTextIfChanged(row.button, "+" + rest.length);
                    row.button.setAttribute("aria-label", rest.length + (phone && phone.matches ? " more tablets need attention. Open Tablets to review all." : " more tablets need attention. Review the first."));
                } else {
                    const item = evidence.get(id), word = window.OperatorState.rosterStatus(item).word.toLowerCase();
                    const name = labelFor ? labelFor(id) : id;
                    row.dataset.status = window.OperatorState.rosterStatus(item).key;
                    row.button.dataset.problemDevice = id;
                    setTextIfChanged(row.button, "▲ " + name + " " + word);
                    row.button.setAttribute("aria-label", name + ", " + item.text + ". Review recovery.");
                }
                if (strip.children[index] !== row) strip.insertBefore(row, strip.children[index] || null);
            });
            if ($("issues-description")) setTextIfChanged($("issues-description"), attention.length + " current content report issue" + (attention.length === 1 ? "" : "s"));
            $("btn-wall-health").dataset.issues = String(attention.length);
            if ($("wall-status-summary")) setTextIfChanged($("wall-status-summary"), "Content report issues: " + attention.length);
            return attention;
        }
        const powerFor = id => {
            const project = window.OperatorStage && window.OperatorStage.powerReadiness;
            return project && state.roster ? project(state.roster[id], { stale: !!state.rosterError, checkedAt: state.rosterCheckedAt }) : null;
        };
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
                    $("resolve-stay").focus();
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
                for (const node of [trigger, $(modeTab[state.mode]), $("btn-server")]) {
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
            if (name === "content" && !await resolve("Open Content", "image")) return false;
            if (name === "arrange" && !await resolve("Open Arrange", "arrangement")) return false;
            return commitMode(name, options);
        }
        function issuePresent(id) {
            const config = state.operatorConfig;
            return !!config && !!window.OperatorState.entries(config.layout)[id];
        }
        function revealIssue(id, row, trigger) {
            const request = ++issueRequest;
            if (request !== issueRequest || !row || row.isConnected === false || !issuePresent(id)) return Promise.resolve(false);
            return Promise.resolve(selectTablet(id, { reveal: true, trigger: trigger || row.firstElementChild })).then(() => true);
        }
        function syncPrimary(commit, stripVisible) {
            const sheet = $("device-sheet");
            const ready = id => { const node = $(id); return !!node && !node.hidden && node.dataset.ready !== "false" && (id !== "tablet-label-save" || node.dataset.ready === "true"); };
            let owner = commit === "image" ? "show-image" : commit === "arrangement" ? "btn-apply" : commit === "test" ? "restore-image" : null;
            if (!owner && stripVisible) {
                const step = ["first-wall-join", "first-wall-arrange", "first-wall-image"].find(id => $(id) && $(id).dataset.state === "current");
                owner = step ? step + "-action" : null;
                if (step === "first-wall-arrange" && state.mode === "arrange" && !state.selectedId) owner = "grid-preview";
            }
            if (!owner && sheet && !sheet.hidden) owner = ["tablet-arrange", "tablet-label-save"].find(ready) || null;
            for (const id of ["show-image", "btn-apply", "restore-image", "grid-preview", "first-wall-join-action", "first-wall-arrange-action", "first-wall-image-action", "tablet-arrange", "tablet-label-save"]) {
                if ($(id)) $(id).classList.toggle("btn-primary", id === owner);
            }
        }
        function render(view = window.OperatorState.stageView(state)) {
            if (rosterObserver) fitRoster();
            const arrangement = arrangementDirty(), image = imageDirty();
            if ($("operator-connection")) $("operator-connection").textContent = state.connectionText || "Connecting to the wall…";
            const hasPreview = arrangementPreview();
            const mode = view.mode, body = document.body;
            if ($("tally-preview")) setTextIfChanged($("tally-preview"), mode === "image-preview" ? "Image preview · not on wall" : "Arrangement preview · not applied");
            const subject = state.selectedId ? "tablet" : "tools";
            if ($("mode-title")) setTextIfChanged($("mode-title"), { content: "Content", arrange: "Arrange", test: "Test" }[state.mode]);
            body.dataset.mode = state.mode;
            body.dataset.stageMode = mode;
            body.dataset.subject = subject;
            body.dataset.connection = state.rosterError ? "stale" : state.configLoaded ? "current" : "loading";
            body.dataset.outputDirty = String(arrangement || image);
            for (const item of document.querySelectorAll("#bottom-nav [data-workspace-mode]")) item.setAttribute("aria-pressed", String(body.dataset.view === "tools" && item.dataset.workspaceMode === state.mode));
            if ($("nav-tablets")) $("nav-tablets").setAttribute("aria-pressed", String(body.dataset.view === "tablets"));
            const progress = setupProgress(), wallEmpty = progress.empty;
            if ($("setup-strip")) {
                $("setup-strip").hidden = !state.configLoaded || !!state.rosterError || progress.complete;
                const { online, done, current } = progress;
                const copy = [online ? online + (online === 1 ? " tablet online" : " tablets online") : "No tablets yet",
                    done[1] ? "Wall arranged" : done[0] ? "Not arranged yet" : "After tablets join",
                    done[2] ? "Image shown" : "No image shown yet"];
                ["first-wall-join", "first-wall-arrange", "first-wall-image"].forEach((id, index) => {
                    const step = $(id), stepState = done[index] ? "done" : index === current ? "current" : "blocked";
                    setTextIfChanged($(id + "-status"), copy[index]);
                    setTextIfChanged($(id + "-mark"), done[index] ? "✓" : String(index + 1));
                    step.dataset.done = String(done[index]);
                    step.dataset.state = stepState;
                    step.setAttribute("aria-current", stepState === "current" ? "step" : "false");
                });
            }
            const noTablets = !Object.keys(state.roster).length;
            if ($("first-wall-arrange-action")) $("first-wall-arrange-action").disabled = noTablets;
            if (joiningHasTablets !== !noTablets) { $("tablet-joining").open = noTablets; joiningHasTablets = !noTablets; }
            $("image-details-disclosure").hidden = $("presentation-checks").hidden = $("diagnostic-colours").hidden = $("stage-technical").hidden = arrangeTools.hidden = noTablets;
            $("test-empty").hidden = $("arrange-empty").hidden = !noTablets;
            $("diagnostic-colours").hidden = noTablets || state.mode !== "test";
            const card = joinCard();
            body.dataset.emptyWall = String(card);
            const serverOpen = $("server-drawer").open;
            $("join-strip").hidden = !(card || joinOpen || serverOpen);
            $("join-strip").dataset.presentation = serverOpen ? "drawer" : card ? "card" : "popover";
            $("add-tablet").setAttribute("aria-expanded", String(card || joinOpen));
            const sheet = $("device-sheet");
            if (sheet) sheet.hidden = subject !== "tablet";
            if ($("tablet-back")) {
                setTextIfChanged($("tablet-back"), { content: "‹ Library", arrange: "‹ Wall shape", test: "‹ Test patterns" }[state.mode] || "‹ Tools");
            }
            const rawNames = stageNames();
            const isPattern = patternName.test(rawNames.applied || "");
            const names = { ...rawNames, applied: isPattern ? "Test pattern" : rawNames.applied };
            if ($("commit-draft-name")) setTextIfChanged($("commit-draft-name"), "Draft: " + (image && names.pending || "None"));
            if ($("commit-applied-name")) setTextIfChanged($("commit-applied-name"), "On wall: " + (names.unavailable ? "Unavailable image" : names.applied || "No image"));
            const shownType = state.scene && state.scene.content && state.scene.content.type;
            const testLive = mode === "live" && !wallEmpty && (shownType === "calibration" || isPattern);
            const commit = image ? "image" : arrangement ? "arrangement" : testLive ? "test" : "idle";
            body.dataset.testLive = String(testLive);
            $("commit-bar").dataset.commit = commit;
            const label = mode === "live" ? names.unavailable ? "Unavailable image" : names.applied ? state.mode === "content" ? "Showing" : "Showing " + names.applied
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
            const noImage = !testLive && !names.applied && !names.unavailable;
            body.dataset.noImage = String(noImage);
            const idleLabel = wallEmpty ? "Nothing on the wall" : testLive ? "Test pattern on the wall"
                : noImage ? "No image yet · tablet colours" : "On wall · " + (names.unavailable ? "Unavailable image" : names.applied);
            if ($("draft-state")) {
                setTextIfChanged($("draft-state"), commit === "image" ? "Preview · " + (names.pending || "image") + " · not on wall"
                    : commit === "arrangement" ? "Arrangement preview · not applied" : idleLabel);
            }
            body.dataset.stageIdentity = !names.unavailable && (!!names.applied || image) ? "chips" : "text";
            if ($("wall-checked")) {
                const checked = state.rosterCheckedAt ? Date.parse(state.rosterCheckedAt) : NaN;
                $("wall-checked").hidden = !Number.isFinite(checked);
                $("wall-checked").textContent = Number.isFinite(checked)
                    ? "Checked " + new Date(checked).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
            }
            if ($("stage-mode-label").textContent !== label) $("stage-mode-label").textContent = label;
            $("stage-mode").title = label;
            const description = { live: "", "arrangement-preview": "Arrangement preview, not applied", "image-preview": "Image preview, not shown" }[mode];
            if ($("stage-mode-description").textContent !== description) $("stage-mode-description").textContent = description;
            $("view-toggle").hidden = mode === "live" && (!state.viewLive || !hasPreview && !image);
            $("view-toggle").textContent = state.viewLive ? "Preview" : "On wall";
            $("view-toggle").setAttribute("aria-label", state.viewLive ? "Preview" : "On wall");
            $("btn-cancel").hidden = !arrangement;
            $("wall-empty").hidden = !state.configLoaded || hasPreview || !wallEmpty;
            setTextIfChanged($("empty-title"), noTablets ? "Build your first wall" : Object.keys(state.roster).length + (Object.keys(state.roster).length === 1 ? " tablet waiting to be arranged" : " tablets waiting to be arranged"));
            setTextIfChanged($("empty-hint"), noTablets ? "Open the tablet address on each tablet. They appear here as they join." : "Preview an arrangement to place the joined tablets on the wall.");
            const config = state.operatorConfig;
            if (config) {
                const ids = Object.keys(window.OperatorState.entries(config.layout));
                const evidence = new Map(ids.map(id => {
                    const item = window.OperatorState.tabletState(config, id, performance.now());
                    return [id, state.rosterError && item.status !== "excluded"
                        ? { status: "stale", showing: false, text: "Status stale · Current image evidence unavailable" } : item];
                }));
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
                renderProblems(ids, evidence);
            }
            if ($("wall-issues-panel")) {
                const hasIssues = [...issues.values()].some(row => !row.hidden);
                if (hasIssues !== ($("wall-issues-panel").dataset.hasIssues === "true")) {
                    if (!hasIssues && $("wall-issues-panel").contains(document.activeElement)) $("issues-title").focus({ preventScroll: true });
                    $("wall-issues-panel").open = hasIssues;
                }
                $("wall-issues-panel").dataset.hasIssues = String(hasIssues);
                $("wall-issues-panel").hidden = !hasIssues;
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
            syncPrimary(commit, !$("setup-strip").hidden);
        }
        $("view-toggle").addEventListener("click", () => {
            const toggle = $("view-toggle"), search = $("image-search"), restore = document.activeElement === toggle;
            state.viewLive = !state.viewLive; onViewChange(); render(); renderStage();
            if (restore && toggle.hidden && (typeof search.getClientRects !== "function" || search.getClientRects().length)) search.focus({ preventScroll: true });
        });
        $("add-image").addEventListener("click", () => {
            $("image-addition").open = true;
            ($("upload-form").hidden ? $("image-addition").querySelector("summary") : $("upload-file")).focus();
        });
        return { open, land, resolve, render, revealIssue, closeJoin, toggleJoin: () => joinOpen ? closeJoin() : openJoin(true), destroy() { if (phone) phone.removeEventListener("change", onPhoneChange); if (rosterObserver) rosterObserver.disconnect(); if (pending) pending("stay"); $("draft-resolution").close(); } };
    }
};
