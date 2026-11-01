"use strict";
window.OperatorContent = {
    create({ state, api, ingestConfig, renderStage, announce, showConflict, isDirty }) {
        const $ = id => document.getElementById(id);
        let images = [], selected = null, fit = "cover", selectionDirty = false, loading = false, busy = false, inventoryReady = false;
        let previous = null, uploadAllowed = null, xhr = null, uploadChecked = false;
        const message = text => { $("image-message").textContent = text; };
        const sceneInput = content => content.type === "image"
            ? Object.assign({ type: "image", asset: content.asset, fit: content.fit || "cover" }, content.background && state.operatorConfig && state.operatorConfig.operator_state_version === 1 ? { background: content.background } : {})
            : { type: content.type };
        function selectedContent() {
            const image = images.find(item => item.id === selected);
            return image ? { type: "image", asset: image.id, url: image.url, intrinsicWidth: image.width,
                intrinsicHeight: image.height, fit, background: "#0b1120" } : null;
        }
        function render() {
            const content = state.scene && state.scene.content || {};
            const active = images.find(item => item.id === content.asset);
            state.activeImageUnavailableId = inventoryReady && content.type === "image" && !active ? content.asset : null;
            $("active-image").textContent = content.type === "image"
                ? (active ? active.name : content.name || content.asset) + " · " + (content.fit === "contain" ? "Fit whole image" : "Fill")
                    + " · " + content.intrinsicWidth + " × " + content.intrinsicHeight + " px"
                    + (content.available === false || content.availability === "unavailable" || state.activeImageUnavailableId ? " · Unavailable. Restore the file or select another image." : "")
                : content.type === "color" ? "Tablet colours" : content.type === "calibration" ? "Logical calibration pattern" : "Content not reported";
            if (!selectionDirty && content.type === "image") { selected = content.asset; fit = content.fit || "cover"; }
            const selector = $("image-select");
            const key = JSON.stringify(images.map(item => [item.id, item.name]));
            if (selector.dataset.key !== key) {
                selector.replaceChildren(new Option(images.length ? "Choose a still image" : "No images in the library", ""));
                images.forEach(item => selector.add(new Option(item.name + " · " + item.width + " × " + item.height + " · " + item.source, item.id)));
                selector.dataset.key = key;
            }
            selector.value = selected || "";
            $("image-fit").value = fit;
            $("image-fit").disabled = busy;
            $("show-calibration").disabled = state.layoutKind !== "logical" || busy;
            for (const id of ["show-colours", "pattern-grid", "pattern-black"]) $(id).disabled = busy;
            selector.disabled = loading || busy;
            $("show-image").disabled = busy || loading || !selectedContent() || !state.etag || state.etagState !== "current";
            $("restore-image").disabled = busy || !previous || state.etagState !== "current";
            $("refresh-images").disabled = loading;
            const chosen = selectedContent();
            const image = images.find(item => item.id === selected);
            $("image-details").textContent = image ? image.source + " · " + image.width + " × " + image.height + " source px" : "Choose an image, then Show on wall. Refresh after copying files to the library.";
            const thumbnail = $("image-thumbnail");
            thumbnail.hidden = !image;
            if (image && thumbnail.getAttribute("src") !== image.thumbnail_url) thumbnail.src = image.thumbnail_url;
            const transform = chosen && state.draft && window.OperatorState.fitTransform(state.gridPreview ? state.gridPreview.layout : state.draft, chosen);
            $("image-fit-note").textContent = transform ? (fit === "cover"
                ? "Fill crops " + Math.round(transform.cropX * 100) + "% of the source width and " + Math.round(transform.cropY * 100) + "% of its height outside the wall."
                : "Fit keeps the entire source inside the wall bounds and adds bars.")
                + " Bezels and gaps still hide image areas. This is one wall-wide transform." : "";
            $("upload-form").hidden = uploadAllowed !== true;
            $("upload-instruction").hidden = uploadAllowed === true;
            const caps = state.capabilities || {};
            $("upload-instruction").textContent = uploadAllowed === false
                ? "Uploads are off. Copy a PNG or JPEG to " + (caps.asset_directory || caps.asset_dir || "the server’s configured image folder (TABLET_WALL_ASSET_DIR)") + ", then Refresh images."
                : "Upload availability is not reported. You can copy a PNG or JPEG to the server’s configured image folder, then Refresh images.";
            state.previewContent = selectionDirty ? chosen : null;
        }
        async function refresh() {
            if (loading) return;
            loading = true; message("Loading still images…"); render();
            try {
                const result = await api("GET", "/api/v3/images");
                if (!Array.isArray(result.images)) throw new Error("Image inventory was not returned.");
                images = result.images; inventoryReady = true;
                message(images.length ? images.length + " still images available. Selection previews here; Show on wall applies it."
                    : "No still images yet. Copy an image to the configured folder or upload when enabled, then Refresh images.");
            } catch (error) {
                message("Image library unavailable. " + error.message + " Retry with Refresh images. The active scene is unchanged.");
            } finally { loading = false; render(); renderStage(); }
        }
        async function show(content) {
            if (!content || busy) return;
            busy = true; render();
            const before = state.scene && state.scene.content;
            try {
                const result = await api("PUT", "/api/v3/scene", { content: sceneInput(content) }, { etag: true });
                previous = before ? sceneInput(before) : previous;
                selectionDirty = false;
                ingestConfig(result, { preserveDraft: true });
                message("Scene applied. Check tablet image confirmations below the stage."); announce("Scene applied.");
            } catch (error) {
                if (error.status === 412) showConflict("The scene changed. Your image selection is retained. Reload and review before showing it.");
                message("Could not show this image. " + error.message + " The selection is retained.");
            } finally { busy = false; render(); renderStage(); }
        }
        async function detectUploads() {
            const capability = (state.capabilities || {}).uploads;
            if (typeof capability === "boolean") { uploadAllowed = capability; render(); return; }
            if (uploadChecked || !state.configLoaded) return;
            uploadChecked = true;
            try { await api("GET", "/media"); uploadAllowed = true; }
            catch (error) { uploadAllowed = error.status === 403 ? false : null; }
            render();
        }
        function upload(event) {
            event.preventDefault();
            const file = $("upload-file").files[0];
            if (!file || xhr || uploadAllowed !== true) return;
            xhr = new XMLHttpRequest();
            const request = xhr;
            $("upload-submit").disabled = true;
            $("upload-progress").hidden = false;
            $("upload-progress").value = 0;
            $("upload-message").textContent = "Uploading " + file.name + "…";
            request.open("POST", "/uploads?name=" + encodeURIComponent(file.name));
            request.timeout = 120000;
            request.setRequestHeader("Content-Type", file.type || "application/octet-stream");
            request.upload.onprogress = event => {
                if (event.lengthComputable) $("upload-progress").value = event.loaded / event.total * 100;
            };
            request.upload.onload = () => { $("upload-message").textContent = "Upload sent. Server is checking and preparing the image…"; $("upload-progress").removeAttribute("value"); };
            request.onload = async () => {
                let result;
                try { result = JSON.parse(request.responseText); } catch (_) { result = {}; }
                if (request.status >= 200 && request.status < 300) {
                    $("upload-message").textContent = "Image uploaded. Choose it, then Show on wall.";
                    if (result.asset) { selected = result.asset.id || result.asset.asset_id; selectionDirty = true; }
                    await refresh();
                } else $("upload-message").textContent = "Upload rejected. " + (typeof result.detail === "string" ? result.detail : "Check the file and retry (HTTP " + request.status + ").");
            };
            request.onerror = () => { $("upload-message").textContent = "Upload failed. Check the connection and retry."; };
            request.ontimeout = () => { $("upload-message").textContent = "Upload timed out. Refresh images before retrying."; };
            request.onloadend = () => { xhr = null; $("upload-submit").disabled = false; $("upload-progress").hidden = true; };
            request.send(file);
        }
        $("image-select").addEventListener("change", event => { selected = event.target.value; selectionDirty = true; render(); renderStage(); });
        $("image-fit").addEventListener("change", event => { fit = event.target.value; selectionDirty = true; render(); renderStage(); });
        $("refresh-images").addEventListener("click", refresh);
        $("show-image").addEventListener("click", () => show(selectedContent()));
        $("restore-image").addEventListener("click", () => show(previous));
        $("show-colours").addEventListener("click", () => show({ type: "color" }));
        $("show-calibration").addEventListener("click", () => show({ type: "calibration" }));
        $("upload-form").addEventListener("submit", upload);
        $("image-thumbnail").addEventListener("error", () => message("Image preview unavailable. Restore the file or choose another image, then Refresh images."));
        for (const pattern of ["grid", "black"]) $("pattern-" + pattern).addEventListener("click", async () => {
            if (isDirty()) { message("Apply or cancel the layout draft first. Patterns use committed bounds."); return; }
            try {
                const image = await api("POST", "/api/v3/test-pattern", { pattern }, { etag: true });
                if (!image || !image.id) throw new Error("Pattern image metadata was not returned.");
                images = images.filter(item => item.id !== image.id).concat(image);
                await show({ type: "image", asset: image.id, fit: "contain" });
            } catch (error) { message("Pattern unavailable on this server. " + error.message + " Choose a prepared grid or opaque black image from the library."); }
        });
        return { render, refresh, detectUploads, dirty: () => selectionDirty,
            discard() { selectionDirty = false; state.previewContent = null; },
            destroy() { if (xhr) xhr.abort(); } };
    }
};
