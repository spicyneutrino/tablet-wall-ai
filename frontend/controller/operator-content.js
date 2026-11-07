"use strict";
window.OperatorContent = {
    create({ state, api, ingestConfig, renderStage, announce, showConflict, resolveOutput = async () => true, refreshConnection }) {
        const { $ } = window.OperatorDom;
        let images = [], selected = null, fit = "cover", background = "#0b1120", selectionDirty = false, loading = false, busy = false, inventoryReady = false;
        let previous = null, xhr = null, inventoryVersion = 0, selectionVersion = 0, baseEtag = null, savedScene = null, uploadUncertain = false;
        const gallery = new Map();
        let retainMessage = false;
        const shownRevisions = new Map();
        const message = (text, retain = false, kind = "info", target = "image-message") => { shownRevisions.delete(target); if (target === "image-message") retainMessage = retain; $(target).dataset.kind = kind; $(target).textContent = text; };
        function renderShownStatus() {
            for (const [target, revision] of shownRevisions) {
                const config = state.operatorConfig, label = revision.image ? "Image" : "Content";
                let text, kind = "ok";
                if (!config || state.rosterError || state.etagState !== "current") {
                    kind = "warn";
                    text = label + " applied. Tablet reports may be stale; refresh status in the header or Issues.";
                } else if (config.generation !== revision.generation || config.revision !== revision.revision && (!revision.content || !revision.layout
                        || JSON.stringify(config.scene?.content) !== revision.content || JSON.stringify(config.layout) !== revision.layout)) {
                    kind = "warn";
                    text = "Wall content or arrangement changed after this command. Review current state. Open Images and Arrange before relying on this command.";
                } else {
                    text = "";
                }
                $(target).dataset.kind = kind;
                $(target).textContent = text;
            }
        }

        function contextual(id, visible) {
            const control = $(id);
            if (!visible && !control.hidden && document.activeElement === control) $("image-search").focus();
            control.hidden = !visible;
        }
        const normalizedBackground = value => typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value)
            ? value.toLowerCase() : "#0b1120";
        const sceneInput = content => content.type === "image"
            ? { type: "image", asset: content.asset, fit: content.fit || "cover", background: normalizedBackground(content.background) }
            : { type: content.type };
        function selectedContent() {
            if (savedScene && savedScene.content.type !== "image") return savedScene.content;
            const image = images.find(item => item.id === selected);
            return image ? { type: "image", asset: image.id, url: image.url, intrinsicWidth: image.width,
                intrinsicHeight: image.height, fit, background } : null;
        }
        function select(id, nextFit = fit, nextBackground = background) {
            if (!selectionDirty) baseEtag = state.etag;
            if (!selectionDirty || id !== selected) {
                const applied = state.scene && state.scene.content;
                if (applied && applied.type === "image" && applied.asset === id) {
                    nextFit = applied.fit || "cover";
                    nextBackground = applied.background;
                } else nextBackground = "#0b1120";
            }
            selected = id; fit = nextFit; background = normalizedBackground(nextBackground); savedScene = null;
            selectionDirty = true; selectionVersion += 1;
            state.viewLive = false; if (!retainMessage) message(""); render(); renderStage();
        }
        async function choose(id, nextFit = fit) {
            if (!id) return false;
            const version = selectionVersion;
            if (!await resolveOutput("Preview this image", "image") || version !== selectionVersion) { render(); return false; }
            select(id, nextFit); return true;
        }
        function visibleGalleryButtons() {
            const list = $("image-gallery");
            if (!list || !list.children) return [];
            const buttons = [];
            for (const item of Array.from(list.children)) {
                const button = galleryButton(item);
                if (button && !item.hidden && !button.hidden && !button.disabled) buttons.push(button);
            }
            return buttons;
        }
        function galleryButton(item) {
            return item && (item.children && item.children[0] || item.firstElementChild) || null;
        }
        function galleryRows(buttons) {
            const rows = [];
            for (const button of buttons) {
                const rect = button.getBoundingClientRect();
                let row = rows.find(candidate => Math.abs(candidate.top - rect.top) < 4);
                if (!row) { row = { top: rect.top, items: [] }; rows.push(row); }
                row.items.push({ button, rect });
            }
            rows.sort((a, b) => a.top - b.top);
            for (const row of rows) row.items.sort((a, b) => a.rect.left - b.rect.left);
            return rows;
        }
        function adjacentButton(button, offset, rows) {
            for (const row of rows) {
                const index = row.items.findIndex(item => item.button === button);
                if (index >= 0) return row.items[index + offset] ? row.items[index + offset].button : null;
            }
            return null;
        }
        function nextRowButton(button, offset, rows) {
            const index = rows.findIndex(row => row.items.some(item => item.button === button));
            if (index < 0) return null;
            const row = rows[index + offset];
            if (!row || !row.items.length) return null;
            const rect = button.getBoundingClientRect();
            const middle = rect.left + rect.width / 2;
            return row.items.reduce((best, item) => {
                const distance = Math.abs(item.rect.left - rect.left);
                const center = Math.abs(item.rect.left + item.rect.width / 2 - middle);
                return !best || distance < best.distance || (distance === best.distance && center < best.center)
                    ? { button: item.button, distance, center } : best;
            }, null).button;
        }
        function focusTarget(button) {
            button.focus({ preventScroll: true });
            let container = button.parentElement;
            while (container) {
                const style = window.getComputedStyle(container);
                const scrollX = /(auto|scroll)/.test(style.overflowX) && container.scrollWidth > container.clientWidth;
                const scrollY = /(auto|scroll)/.test(style.overflowY) && container.scrollHeight > container.clientHeight;
                if (scrollX || scrollY) {
                    const target = button.getBoundingClientRect();
                    const box = container.getBoundingClientRect();
                    if (scrollY) {
                        if (target.top < box.top) container.scrollTop -= box.top - target.top;
                        else if (target.bottom > box.bottom) container.scrollTop += target.bottom - box.bottom;
                    }
                    if (scrollX) {
                        if (target.left < box.left) container.scrollLeft -= box.left - target.left;
                        else if (target.right > box.right) container.scrollLeft += target.right - box.right;
                    }
                    return;
                }
                container = container.parentElement;
            }
            button.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
        function setGalleryTabStop(preferred) {
            const list = $("image-gallery");
            if (list && list.children) for (const item of Array.from(list.children)) {
                const button = galleryButton(item);
                if (button) button.tabIndex = -1;
            }
            const buttons = visibleGalleryButtons();
            if (!buttons.length) return;
            const active = preferred && buttons.includes(preferred) ? preferred : buttons[0];
            active.tabIndex = 0;
        }
        function renderGallery() {
            const list = $("image-gallery");
            if (!list || typeof document.createElement !== "function") return;
            const focusedBefore = typeof document.activeElement !== "undefined" ? document.activeElement : null;
            const focusedWasGallery = Boolean(focusedBefore
                && Array.from(list.children).some(item => galleryButton(item) === focusedBefore));
            const search = $("image-search").value.toLocaleLowerCase();
            for (const [id, row] of gallery) if (!images.some(image => image.id === id)) { row.item.remove(); gallery.delete(id); }
            images.forEach(image => {
                let row = gallery.get(image.id);
                if (!row) {
                    const item = document.createElement("li"); item.className = "image-choice"; item.dataset.assetId = image.id;
                    const button = document.createElement("button"); button.type = "button"; button.className = "image-choice-button";
                    const thumbnail = document.createElement("img"); thumbnail.alt = ""; thumbnail.loading = "lazy";
                    const name = document.createElement("span");
                    name.className = "image-choice-name";
                    const appliedNote = document.createElement("span"); appliedNote.className = "sr-only";
                    button.append(thumbnail, name); item.append(button, appliedNote); list.append(item);
                    button.addEventListener("click", () => choose(image.id));
                    thumbnail.addEventListener("error", () => { item.dataset.thumbnail = "unavailable"; thumbnail.hidden = true; });
                    row = { item, button, thumbnail, name, appliedNote }; gallery.set(image.id, row);
                }
                row.item.hidden = !image.name.toLocaleLowerCase().includes(search);
                const inspected = selectionDirty && image.id === selected;
                row.button.setAttribute("aria-pressed", String(inspected)); row.button.disabled = busy;
                const applied = Boolean(state.scene && state.scene.content.type === "image" && state.scene.content.asset === image.id);
                row.item.dataset.applied = String(applied);
                row.button.setAttribute("aria-label", "Preview " + image.name);
                row.button.title = image.name;
                row.appliedNote.textContent = applied ? "Applied configuration. This image is the saved wall content; tablet reports are separate." : "";
                if (applied) {
                    if (!row.appliedNote.id) row.appliedNote.id = "image-applied-" + image.id.replace(/[^a-zA-Z0-9_-]/g, "_");
                    row.button.setAttribute("aria-describedby", row.appliedNote.id);
                } else row.button.removeAttribute("aria-describedby");
                if (row.thumbnail.getAttribute("src") !== image.thumbnail_url) row.thumbnail.src = image.thumbnail_url;
                const thumbnailScale = Math.min(160 / image.width, 160 / image.height);
                row.thumbnail.width = Math.max(1, Math.round(image.width * thumbnailScale)); row.thumbnail.height = Math.max(1, Math.round(image.height * thumbnailScale));
                row.name.textContent = image.name;
            });
            $("image-search-empty").hidden = !search || images.some(image => image.name.toLocaleLowerCase().includes(search));
            const focused = typeof document.activeElement !== "undefined" ? document.activeElement : null;
            const buttons = visibleGalleryButtons();
            const selectedRow = selected && gallery.get(selected);
            const fallback = focused && buttons.includes(focused) ? focused : null;
            const selectedButton = selectedRow && !selectedRow.item.hidden && !selectedRow.button.disabled ? selectedRow.button : null;
            setGalleryTabStop(fallback || selectedButton);
            if (focusedWasGallery) {
                const shown = buttons.includes(focused) && !focused.hidden
                    && !(focused.parentElement && focused.parentElement.hidden);
                if (!shown) {
                    const next = buttons[0];
                    if (next) { focusTarget(next); setGalleryTabStop(next); }
                    else {
                        const searchField = $("image-search");
                        if (searchField && typeof searchField.focus === "function") searchField.focus({ preventScroll: true });
                        setGalleryTabStop(null);
                    }
                }
            }
        }
        function appliedUnavailable() {
            const content = state.scene && state.scene.content || {};
            return content.type === "image" && Boolean(content.available === false || content.availability === "unavailable" || state.activeImageUnavailableId);
        }
        function appliedName() {
            const content = state.scene && state.scene.content || {};
            if (content.type !== "image") return null;
            const active = images.find(item => item.id === content.asset);
            return active ? active.name : content.name || "Image";
        }
        function pendingName() {
            const image = images.find(item => item.id === selected);
            return image ? image.name : savedScene ? savedScene.name || "Saved content" : selected ? "Unavailable image" : "Saved content";
        }
        function render() {
            const content = state.scene && state.scene.content || {};
            const active = images.find(item => item.id === content.asset);
            state.activeImageUnavailableId = inventoryReady && content.type === "image" && !active ? content.asset : null;


            const image = images.find(item => item.id === selected);
            $("selected-image-controls").dataset.assetId = selectionDirty ? selected || "" : "";
            $("image-fit").value = fit;
            $("image-fit").disabled = busy || !selectionDirty || !selected;
            $("image-fit-field").hidden = selectionDirty && !selected;
            $("show-calibration").disabled = state.layoutKind !== "logical" || busy;
            for (const id of ["show-colours", "pattern-grid", "pattern-black"]) $(id).disabled = busy;
            $("show-image").disabled = busy || loading || !selectionDirty || !selectedContent() || !state.etag || state.etagState !== "current";
            contextual("image-rebuild", selectionDirty && baseEtag !== state.etag); contextual("image-discard", selectionDirty);
            contextual("restore-image", !!previous);
            $("image-rebuild").disabled = !selectionDirty || busy; $("image-discard").disabled = !selectionDirty || busy;
            $("show-image").textContent = state.viewLive ? "Show " + pendingName() : savedScene ? "Show saved content" : "Show image";
            $("restore-image").disabled = busy || !previous || state.etagState !== "current";
            $("refresh-images").disabled = loading;
            const chosen = selectedContent();
            $("image-title").textContent = selectionDirty ? pendingName()
                : appliedUnavailable() ? "Unavailable image" : active ? active.name : content.type === "image" ? content.name || "Image" : "Nothing shown";
            $("image-details").textContent = selectionDirty && selected && !image
                ? "Selected image unavailable. Refresh images or choose a replacement." : "";
            $("image-preview-controls").hidden = !selectionDirty;
            $("edit-current-image").hidden = selectionDirty || !active;
            const source = selectionDirty ? image : active;
            $("image-source-details").textContent = source ? source.width + " × " + source.height + " source px"
                : !selectionDirty && content.type === "image" ? content.asset : "";
            const thumbnail = $("image-thumbnail"); thumbnail.hidden = !source;
            if (source && thumbnail.getAttribute("src") !== source.url) thumbnail.src = source.url;
            const allowed = (state.capabilities || {}).uploads;
            $("images-check-connection").hidden = typeof allowed === "boolean";
            $("upload-form").hidden = allowed !== true;
            $("upload-instruction").hidden = allowed === true;
            $("upload-instruction").textContent = allowed === false
                ? "Adding images is turned off for this launch. An operator can launch with --operator-uploads for uploads on this computer only. A PNG or JPEG in the configured image folder also appears after Refresh images."
                : "Image-addition capability is unknown. Check the connection and Refresh status. No upload is enabled by the browser.";
            $("upload-submit").disabled = !!xhr || uploadUncertain;
            state.previewContent = selectionDirty ? chosen || { type: "image", asset: selected, available: false } : null;
            renderGallery();
            renderShownStatus();
        }
        async function refresh() {
            const version = ++inventoryVersion;
            loading = true; message("Reading the image library…"); render();
            try {
                const result = await api("GET", "/api/v3/images");
                if (version !== inventoryVersion) return;
                if (!Array.isArray(result.images)) throw new Error("Image inventory was not returned.");
                images = result.images; inventoryReady = true; uploadUncertain = false;
                message(images.length ? "" : "No images available.");
            } catch (error) {
                if (version === inventoryVersion) message("Image library unavailable. " + error.message.replace(/[.!?\s]+$/, "") + ". Use Refresh images to retry.", true, "err");
            } finally { if (version === inventoryVersion) { loading = false; render(); renderStage(); } }
        }
        async function show(content, { guard = baseEtag || state.etag, scene = null, feedback = "image-message" } = {}) {
            const trigger = document.activeElement;
            const submitted = selectionVersion;
            if (!content || busy || !await resolveOutput("Show this content", "image")) return;
            const before = state.scene && state.scene.content;
            busy = true; render();
            try {
                const result = scene
                    ? await api("POST", "/api/v3/scenes/" + encodeURIComponent(scene.name) + "/recall", undefined, { ifMatch: guard })
                    : await api("PUT", "/api/v3/scene", { content: sceneInput(content) }, { ifMatch: guard });
                previous = before ? sceneInput(before) : previous;
                if (selectionVersion === submitted) { selectionDirty = false; selected = null; savedScene = null; baseEtag = null; }
                ingestConfig(result, { preserveDraft: true });
                if (feedback !== "image-message" || !retainMessage) {
                    if (result && result.generation !== undefined && result.revision !== undefined) {
                        shownRevisions.set(feedback, { generation: result.generation, revision: result.revision, image: content.type === "image",
                            content: JSON.stringify(result.scene?.content), layout: JSON.stringify(result.layout) });
                        renderShownStatus();
                    } else message("", false, "info", feedback);
                }
                announce("Content applied.");
                return true;
            } catch (error) {
                if (error.status === 412) showConflict("The wall changed. Your image choice is retained with its original guard. Review current state before rebuilding this preview.");
                message("Could not show this content. " + error.message.replace(/[.!?\s]+$/, "") + ". Use Refresh images to retry.", false, "err", feedback);
                return false;
            } finally {
                busy = false; render(); renderStage();
                const lost = trigger && (trigger.hidden || trigger.disabled || !trigger.isConnected
                    || (typeof trigger.getClientRects === "function" && !trigger.getClientRects().length));
                if (lost) {
                    const search = $("image-search");
                    if (search && typeof search.focus === "function") search.focus({ preventScroll: true });
                }
            }
        }
        function upload(event) {
            event.preventDefault();
            const file = $("upload-file").files[0];
            if (!file || xhr || uploadUncertain || (state.capabilities || {}).uploads !== true) return;
            const selectionAtUpload = selectionVersion;
            const request = xhr = new XMLHttpRequest();
            $("upload-progress").hidden = false; $("upload-progress").value = 0;
            $("upload-message").dataset.kind = "info"; $("upload-message").textContent = "Uploading " + file.name + "…"; render();
            request.open("POST", "/uploads?name=" + encodeURIComponent(file.name)); request.timeout = 120000;
            request.setRequestHeader("Content-Type", file.type || "application/octet-stream");
            request.upload.onprogress = event => { if (event.lengthComputable) $("upload-progress").value = event.loaded / event.total * 100; };
            request.upload.onload = () => { $("upload-message").textContent = "Transfer complete. Checking and preparing the image…"; $("upload-progress").removeAttribute("value"); };
            const uncertain = () => {
                inventoryVersion += 1; loading = false; uploadUncertain = true; $("upload-message").dataset.kind = "warn";
                $("upload-message").textContent = "Upload completion is uncertain. Refresh images and check the library before retrying. Nothing was shown automatically.";
            };
            request.onload = async () => {
                let result; try { result = JSON.parse(request.responseText); } catch (_) { result = {}; }
                const success = request.status >= 200 && request.status < 300;
                $("upload-message").dataset.kind = success ? "ok" : "err";
                const id = result && result.asset && (result.asset.id || result.asset.asset_id);
                if (request.status >= 500 || request.status === 0 || success && (typeof id !== "string" || !id)) {
                    uncertain();
                } else if (success) {
                    inventoryVersion += 1;
                    const selectedUpload = selectionVersion === selectionAtUpload && await choose(id);
                    $("upload-message").textContent = selectedUpload ? "Image added and selected. Review Fit / Fill, then Show image. Nothing was shown automatically."
                        : "Image added to the library. Nothing was shown automatically.";
                    await refresh();
                } else $("upload-message").textContent = "Image addition refused. " + (result && (typeof result.detail === "string" ? result.detail : result.detail && result.detail.message) || "HTTP " + request.status) + ". Check the file or launch admission, then retry.";
            };
            request.onerror = uncertain; request.ontimeout = uncertain;
            request.onloadend = () => { xhr = null; $("upload-progress").hidden = true; render(); };
            request.send(file);
        }
        $("images-check-connection").addEventListener("click", async () => {
            $("images-check-connection").disabled = true;
            try { await refreshConnection(); await refresh(); }
            catch (error) { message("Could not check image-addition availability. " + error.message.replace(/[.!?\s]+$/, "") + ". Use Check image-addition connection to retry.", true, "err"); }
            finally { $("images-check-connection").disabled = false; render(); }
        });
        $("image-fit").addEventListener("change", event => {
            if (!selectionDirty || !selected) { event.target.value = fit; return; }
            choose(selected, event.target.value);
        });
        $("image-search").addEventListener("input", renderGallery);
        $("image-gallery").addEventListener("keydown", event => {
            const buttons = visibleGalleryButtons();
            const current = typeof document.activeElement !== "undefined" ? document.activeElement : null;
            if (!buttons.length || !buttons.includes(current)) return;
            const rows = galleryRows(buttons);
            let next = null;
            if (event.key === "Home") next = buttons[0];
            else if (event.key === "End") next = buttons[buttons.length - 1];
            else if (event.key === "ArrowLeft") next = adjacentButton(current, -1, rows);
            else if (event.key === "ArrowRight") next = adjacentButton(current, 1, rows);
            else if (event.key === "ArrowUp") next = nextRowButton(current, -1, rows);
            else if (event.key === "ArrowDown") next = nextRowButton(current, 1, rows);
            else return;
            if (rows.length === 1 && (event.key === "ArrowUp" || event.key === "ArrowDown")) return;
            event.preventDefault();
            if (!next || next === current) return;
            focusTarget(next);
            setGalleryTabStop(next);
        });
        $("edit-current-image").addEventListener("click", () => {
            const content = state.scene && state.scene.content;
            if (content && content.type === "image") return choose(content.asset, content.fit || "cover");
        });
        $("refresh-images").addEventListener("click", refresh);
        $("show-image").addEventListener("click", () => show(selectedContent(), { scene: savedScene, guard: baseEtag || state.etag }));
        $("restore-image").addEventListener("click", async () => { if (await resolveOutput("Restore previous content")) await show(previous, { guard: state.etag }); });
        $("show-colours").addEventListener("click", async () => { if (await resolveOutput("Show tablet colours")) await show({ type: "color" }, { guard: state.etag, feedback: "pattern-message" }); });
        $("show-calibration").addEventListener("click", async () => { if (await resolveOutput("Show a calibration pattern")) await show({ type: "calibration" }, { guard: state.etag, feedback: "pattern-message" }); });
        $("upload-form").addEventListener("submit", upload);
        $("image-thumbnail").addEventListener("error", () => message("Thumbnail unavailable. Refresh the library or choose another image. This is separate from tablet paint status.", true, "err"));
        for (const pattern of ["grid", "black"]) $("pattern-" + pattern).addEventListener("click", async () => {
            if (!await resolveOutput("Show a check pattern")) return;
            try {
                const image = await api("POST", "/api/v3/test-pattern", { pattern }, { etag: true });
                if (!image || !image.id) throw new Error("Pattern metadata was not returned.");
                inventoryVersion += 1; loading = false;
                images = images.filter(item => item.id !== image.id).concat(image); inventoryReady = true;
                await show({ type: "image", asset: image.id, fit: "contain" }, { guard: state.etag, feedback: "pattern-message" });
            } catch (error) { message("Pattern unavailable. " + error.message.replace(/[.!?\s]+$/, "") + ". Choose a prepared grid or black image from the library.", true, "err", "pattern-message"); }
        });
        return { render, refresh, dirty: () => selectionDirty,
            stageNames: () => ({ applied: appliedName(), pending: pendingName(), unavailable: appliedUnavailable() }),
            imageFor: id => images.find(image => image.id === id),
            showSelected: () => show(selectedContent(), { scene: savedScene, guard: baseEtag || state.etag }),
            previewScene(entry, guard) {
                savedScene = { ...entry }; selected = entry.content.asset || null; fit = entry.content.fit || "cover";
                background = normalizedBackground(entry.content.background);
                baseEtag = guard; selectionDirty = true; selectionVersion += 1; state.viewLive = false; render(); renderStage();
            },
            viewChanged: render,
            discard() { selectionDirty = false; selected = null; savedScene = null; baseEtag = null; state.previewContent = null; if (!retainMessage) message(images.length ? "" : "No images available."); render(); renderStage(); },
            rebuild() { baseEtag = state.etag; state.draftConflict = false; render(); },
            destroy() { if (xhr) xhr.abort(); } };
    }
};
