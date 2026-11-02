"use strict";
window.OperatorContent = {
    create({ state, api, ingestConfig, renderStage, announce, showConflict, resolveOutput = async () => true, refreshConnection }) {
        const $ = id => document.getElementById(id);
        let images = [], selected = null, fit = "cover", selectionDirty = false, loading = false, busy = false, inventoryReady = false;
        let previous = null, xhr = null, inventoryVersion = 0, selectionVersion = 0, baseEtag = null, savedScene = null, uploadUncertain = false;
        const gallery = new Map();
        let messageError = false, shownRevision = null;
        const message = (text, error = false) => { shownRevision = null; messageError = error; $("image-message").textContent = text; };
        function renderShownStatus() {
            if (!shownRevision) return;
            const config = state.operatorConfig;
            let text;
            if (!config || state.rosterError || state.etagState !== "current") text = "Content applied. Tablet status is stale; refresh status to check display.";
            else if (config.generation !== shownRevision.generation || config.revision !== shownRevision.revision) {
                text = "Wall content or arrangement changed after this command. Review current wall status.";
            } else {
                const evidence = window.OperatorState.aggregate(config, performance.now());
                const states = evidence.states;
                const label = shownRevision.image ? "Image" : "Content";
                if (!evidence.total) text = label + " applied. No participating tablets are on the wall.";
                else if (states.some(item => item.status === "failed")) text = label + " applied. A tablet reported a display failure; review tablet status.";
                else if (states.some(item => item.status === "offline" || item.status === "unknown" && !item.online)) text = label + " applied. A tablet is offline or missing; review tablet status.";
                else if (states.some(item => item.status === "stale")) text = label + " applied. Tablet display confirmation is stale.";
                else if (states.some(item => ["blocked", "hidden", "unsupported", "unsupported_client", "unsupported_content"].includes(item.status))) text = label + " applied. A tablet cannot confirm display; review tablet status.";
                else if (states.every(item => item.status === "displayed")) text = label + " applied. Current tablet reports confirm display.";
                else text = label + " applied. Waiting for current tablet reports.";
            }
            $("image-message").textContent = text;
        }
        function contextual(id, visible) {
            const control = $(id);
            if (!visible && !control.hidden && document.activeElement === control) ($("image-select").disabled ? $("image-search") : $("image-select")).focus();
            control.hidden = !visible;
        }
        const sceneInput = content => content.type === "image"
            ? { type: "image", asset: content.asset, fit: content.fit || "cover", ...(content.background ? { background: content.background } : {}) }
            : { type: content.type };
        function selectedContent() {
            if (savedScene && savedScene.content.type !== "image") return savedScene.content;
            const image = images.find(item => item.id === selected);
            return image ? { type: "image", asset: image.id, url: image.url, intrinsicWidth: image.width,
                intrinsicHeight: image.height, fit, background: savedScene && savedScene.content.background || "#0b1120" } : null;
        }
        function select(id, nextFit = fit) {
            if (!selectionDirty) baseEtag = state.etag;
            selected = id; fit = nextFit; savedScene = null; selectionDirty = true; selectionVersion += 1;
            state.viewLive = false; render(); renderStage();
        }
        async function choose(id, nextFit = fit) {
            const version = selectionVersion;
            if (!await resolveOutput("Preview this image", "image") || version !== selectionVersion) { render(); return false; }
            select(id, nextFit); return true;
        }
        function renderGallery() {
            const list = $("image-gallery");
            if (!list || typeof document.createElement !== "function") return;
            const search = $("image-search").value.toLocaleLowerCase();
            for (const [id, row] of gallery) if (!images.some(image => image.id === id)) { row.item.remove(); gallery.delete(id); }
            images.forEach(image => {
                let row = gallery.get(image.id);
                if (!row) {
                    const item = document.createElement("li"); item.className = "image-choice"; item.dataset.assetId = image.id;
                    const button = document.createElement("button"); button.type = "button"; button.className = "image-choice-button";
                    const thumbnail = document.createElement("img"); thumbnail.alt = ""; thumbnail.loading = "lazy";
                    const name = document.createElement("span"), dimensions = document.createElement("span");
                    name.className = "image-choice-name"; dimensions.className = "image-choice-dimensions";
                    button.append(thumbnail, name, dimensions); item.append(button); list.append(item);
                    button.addEventListener("click", () => choose(image.id));
                    thumbnail.addEventListener("error", () => { item.dataset.thumbnail = "unavailable"; thumbnail.hidden = true; });
                    row = { item, button, thumbnail, name, dimensions }; gallery.set(image.id, row);
                }
                row.item.hidden = !image.name.toLocaleLowerCase().includes(search);
                row.item.dataset.selected = String(image.id === selected);
                row.button.setAttribute("aria-pressed", String(image.id === selected)); row.button.disabled = busy;
                row.button.setAttribute("aria-label", "Preview " + image.name);
                if (row.thumbnail.getAttribute("src") !== image.thumbnail_url) row.thumbnail.src = image.thumbnail_url;
                const thumbnailScale = Math.min(160 / image.width, 160 / image.height);
                row.thumbnail.width = Math.max(1, Math.round(image.width * thumbnailScale)); row.thumbnail.height = Math.max(1, Math.round(image.height * thumbnailScale));
                row.name.textContent = image.name; row.dimensions.textContent = image.width + " × " + image.height + " px";
            });
        }
        function render() {
            const content = state.scene && state.scene.content || {};
            const active = images.find(item => item.id === content.asset);
            state.activeImageUnavailableId = inventoryReady && content.type === "image" && !active ? content.asset : null;
            $("active-image").textContent = content.type === "image"
                ? "Applied image · " + (active ? active.name : content.name || content.asset) + " · " + (content.fit === "contain" ? "Show whole image" : "Fill wall")
                    + (content.available === false || content.availability === "unavailable" || state.activeImageUnavailableId ? " · Unavailable. Choose a replacement image below." : "")
                : content.type === "color" ? "Applied content · Tablet colours" : content.type === "calibration" ? "Applied content · Calibration pattern" : "No content reported";
            if (!selectionDirty && content.type === "image") { selected = content.asset; fit = content.fit || "cover"; }
            const selector = $("image-select"), image = images.find(item => item.id === selected);
            const key = JSON.stringify([images.map(item => [item.id, item.name]), !image && selected]);
            if (selector.dataset.key !== key) {
                selector.replaceChildren(new Option(images.length ? "Choose an image" : "No images in the library", ""));
                images.forEach(item => selector.add(new Option(item.name + " · " + item.width + " × " + item.height, item.id)));
                if (selected && !image) selector.add(new Option("Unavailable selected image", selected));
                selector.dataset.key = key;
            }
            selector.value = selected || ""; $("image-fit").value = fit;
            selector.disabled = loading || busy; $("image-fit").disabled = busy;
            $("show-calibration").disabled = state.layoutKind !== "logical" || busy;
            for (const id of ["show-colours", "pattern-grid", "pattern-black"]) $(id).disabled = busy;
            $("show-image").disabled = busy || loading || !selectedContent() || !state.etag || state.etagState !== "current";
            contextual("image-rebuild", selectionDirty); contextual("image-discard", selectionDirty);
            contextual("restore-image", !!previous);
            $("image-rebuild").disabled = !selectionDirty || busy; $("image-discard").disabled = !selectionDirty || busy;
            $("show-image").textContent = savedScene ? "Show saved scene" : "Show image";
            $("restore-image").disabled = busy || !previous || state.etagState !== "current";
            $("refresh-images").disabled = loading;
            const chosen = selectedContent();
            $("image-details").textContent = image ? image.name + " · " + image.width + " × " + image.height + " source px"
                : selected ? "Selected image is unavailable. Refresh the library or choose a replacement. Your selection and geometry are retained." : "Choose or add an image, review its preview, then Show image.";
            const thumbnail = $("image-thumbnail"); thumbnail.hidden = !image;
            if (image && thumbnail.getAttribute("src") !== image.thumbnail_url) thumbnail.src = image.thumbnail_url;
            const transform = chosen && state.base && window.OperatorState.fitTransform(state.base, chosen);
            $("image-fit-note").textContent = transform ? (fit === "cover" ? "Fill crops about " + Math.round(transform.cropX * 100) + "% of the source width and " + Math.round(transform.cropY * 100) + "% of its height."
                : "Show whole image adds bars where the wall and image shapes differ.") + " One wall-wide transform. Bezels and gaps hide image areas." : "";
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
                message(images.length + (images.length === 1 ? " image available." : " images available.") + " Selection previews locally. Show image applies it.");
            } catch (error) {
                if (version === inventoryVersion) message("Image library unavailable. " + error.message + " Use Refresh images to retry. Your selection is retained.", true);
            } finally { if (version === inventoryVersion) { loading = false; render(); renderStage(); } }
        }
        async function show(content, { guard = baseEtag || state.etag, scene = null } = {}) {
            const submitted = selectionVersion;
            if (!content || busy || !await resolveOutput("Show this content", "image")) return;
            const before = state.scene && state.scene.content;
            busy = true; render();
            try {
                const result = scene
                    ? await api("POST", "/api/v3/scenes/" + encodeURIComponent(scene.name) + "/recall", undefined, { ifMatch: guard })
                    : await api("PUT", "/api/v3/scene", { content: sceneInput(content) }, { ifMatch: guard });
                previous = before ? sceneInput(before) : previous;
                if (selectionVersion === submitted) { selectionDirty = false; savedScene = null; baseEtag = null; }
                ingestConfig(result, { preserveDraft: true });
                if (messageError !== true) {
                    messageError = false;
                    shownRevision = result && result.generation !== undefined && result.revision !== undefined
                        ? { generation: result.generation, revision: result.revision, image: content.type === "image" } : null;
                    if (shownRevision) renderShownStatus();
                    else message((content.type === "image" ? "Image" : "Content") + " applied. Waiting for current tablet reports.");
                }
                announce("Content applied. Current tablet reports confirm display separately.");
                return true;
            } catch (error) {
                if (error.status === 412) showConflict("The wall changed. Your image choice is retained with its original guard. Review current state before rebuilding this preview.");
                message("Could not show this content. " + error.message + " Your selection and geometry are retained.", "show");
                return false;
            } finally { busy = false; render(); renderStage(); }
        }
        function upload(event) {
            event.preventDefault();
            const file = $("upload-file").files[0];
            if (!file || xhr || uploadUncertain || (state.capabilities || {}).uploads !== true) return;
            const selectionAtUpload = selectionVersion;
            const request = xhr = new XMLHttpRequest();
            $("upload-progress").hidden = false; $("upload-progress").value = 0;
            $("upload-message").textContent = "Uploading " + file.name + "…"; render();
            request.open("POST", "/uploads?name=" + encodeURIComponent(file.name)); request.timeout = 120000;
            request.setRequestHeader("Content-Type", file.type || "application/octet-stream");
            request.upload.onprogress = event => { if (event.lengthComputable) $("upload-progress").value = event.loaded / event.total * 100; };
            request.upload.onload = () => { $("upload-message").textContent = "Transfer complete. Checking and preparing the image…"; $("upload-progress").removeAttribute("value"); };
            const uncertain = () => {
                inventoryVersion += 1; loading = false; uploadUncertain = true;
                $("upload-message").textContent = "Upload completion is uncertain. Refresh images and check the library before retrying. Nothing was shown automatically.";
            };
            request.onload = async () => {
                let result; try { result = JSON.parse(request.responseText); } catch (_) { result = {}; }
                const success = request.status >= 200 && request.status < 300;
                const id = result && result.asset && (result.asset.id || result.asset.asset_id);
                if (request.status >= 500 || request.status === 0 || success && (typeof id !== "string" || !id)) {
                    uncertain();
                } else if (success) {
                    inventoryVersion += 1;
                    const selectedUpload = selectionVersion === selectionAtUpload && await choose(id);
                    $("upload-message").textContent = selectedUpload ? "Image added and selected. Review Fit / Fill, then Show image. Nothing was shown automatically."
                        : "Image added to the library. Your newer choice is retained. Nothing was shown automatically.";
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
            catch (error) { message("Could not check image-addition availability. " + error.message, true); }
            finally { $("images-check-connection").disabled = false; render(); }
        });
        $("image-select").addEventListener("change", event => choose(event.target.value));
        $("image-fit").addEventListener("change", event => choose(selected, event.target.value));
        $("image-search").addEventListener("input", renderGallery);
        $("refresh-images").addEventListener("click", refresh);
        $("show-image").addEventListener("click", () => show(selectedContent(), { scene: savedScene, guard: baseEtag || state.etag }));
        $("restore-image").addEventListener("click", async () => { if (await resolveOutput("Restore previous content")) await show(previous, { guard: state.etag }); });
        $("show-colours").addEventListener("click", async () => { if (await resolveOutput("Show tablet colours")) await show({ type: "color" }, { guard: state.etag }); });
        $("show-calibration").addEventListener("click", async () => { if (await resolveOutput("Show a calibration pattern")) await show({ type: "calibration" }, { guard: state.etag }); });
        $("upload-form").addEventListener("submit", upload);
        $("image-thumbnail").addEventListener("error", () => message("Thumbnail unavailable. Refresh the library or choose another image. This is separate from tablet paint status.", true));
        for (const pattern of ["grid", "black"]) $("pattern-" + pattern).addEventListener("click", async () => {
            if (!await resolveOutput("Show a check pattern")) return;
            try {
                const image = await api("POST", "/api/v3/test-pattern", { pattern }, { etag: true });
                if (!image || !image.id) throw new Error("Pattern metadata was not returned.");
                inventoryVersion += 1; loading = false;
                images = images.filter(item => item.id !== image.id).concat(image); inventoryReady = true;
                await show({ type: "image", asset: image.id, fit: "contain" }, { guard: state.etag });
            } catch (error) { message("Pattern unavailable. " + error.message + " Choose a prepared grid or black image from the library.", true); }
        });
        return { render, refresh, dirty: () => selectionDirty,
            showSelected: () => show(selectedContent(), { scene: savedScene, guard: baseEtag || state.etag }),
            previewScene(entry, guard) {
                savedScene = { ...entry }; selected = entry.content.asset || null; fit = entry.content.fit || "cover";
                baseEtag = guard; selectionDirty = true; selectionVersion += 1; state.viewLive = false; render(); renderStage();
            },
            discard() { selectionDirty = false; savedScene = null; baseEtag = null; state.previewContent = null; render(); renderStage(); },
            rebuild() { baseEtag = state.etag; state.draftConflict = false; render(); },
            destroy() { if (xhr) xhr.abort(); } };
    }
};
