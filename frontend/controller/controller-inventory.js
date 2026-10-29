"use strict";

/* Curated assets, managed uploads, selection and image scene commands. */
window.ControllerInventory = {
    create: function (dependencies) {
        const {
            PROTOCOL, aspectOf, clockStamp, compareIds, contentLabel, el, fmtAspect, inventory, logStatus, normalizeWall, renderWall, renderWallContent, renderWallMap, requestJson, wallReady, runtime
        } = dependencies;

        function activeImageId() {
            if (!runtime.wall || runtime.wall.contentType !== "image" || !runtime.wall.content) return null;
            const asset = runtime.wall.content.asset;
            return typeof asset === "string" && asset !== "" ? asset : null;
        }

        function assetById(id) {
            if (typeof id !== "string" || id === "") return null;
            for (const asset of inventory.assets) {
                if (asset.id === id) return asset;
            }
            for (const asset of inventory.mediaAssets) {
                if (asset.id === id) return asset;
            }
            return null;
        }

        /**
         * Whether the active image is provably absent from the inventory.
         *
         * This needs a successful read to mean anything: an inventory that was
         * never loaded is "unknown", never "missing", so a server without the
         * route cannot make this page claim the wall is broken.
         */
        function activeAssetMissing() {
            const id = activeImageId();
            // A failed refresh leaves a stale list for browsing, not evidence
            // that a currently active asset is missing from the server now.
            if (!id || !inventory.assetsLoaded || inventory.assetsError) return false;
            if (assetById(id) !== null) return false;
            // With uploads disabled there is no managed list to consult, so the
            // curated inventory is the only evidence this page can use.
            if (inventory.mediaState === "forbidden") return true;
            return inventory.mediaState === "ready" && !inventory.mediaError;
        }

        /** Asset ids are `sha256:<64 hex>` — the prefix is constant, so the
         *  readable part is the digest's first 8 hex digits. */
        function shortAsset(id) {
            const value = String(id);
            const body = value.indexOf("sha256:") === 0 ? value.slice(7) : value;
            return body.slice(0, 8);
        }

        function fmtBytes(n) {
            if (n === null || !Number.isFinite(n) || n < 0) return "-";
            if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MiB";
            if (n >= 1024) return (n / 1024).toFixed(1) + " KiB";
            return n + " B";
        }

        /** 1.0 s .. 600 s: one decimal below ten seconds, whole seconds above. */
        function fmtDuration(ms) {
            if (ms === null || !Number.isFinite(ms) || ms <= 0) return "-";
            const seconds = ms / 1000;
            return (seconds < 10 ? seconds.toFixed(1) : String(Math.round(seconds))) + " s";
        }

        /* ------------------------------------------------------------------ *
         * Inventory parsing
         *
         * PROTOCOL.md fixes which fields `GET /assets` lists (id, display name,
         * MIME type, intrinsic dimensions, byte size, same-origin URL) but not
         * the container or the casing, so the reader takes a bare array, an
         * object holding one, or a map keyed by id, and looks each field up
         * under its camelCase and snake_case spellings. An entry with no
         * identifiable id is skipped rather than rendered as a blank row.
         * ------------------------------------------------------------------ */

        function pickString(raw, keys) {
            for (const key of keys) {
                const value = raw[key];
                if (typeof value === "string" && value !== "") return value;
            }
            return null;
        }

        function pickNumber(raw, keys) {
            for (const key of keys) {
                const value = raw[key];
                if (value === null || value === undefined || value === "") continue;
                const n = Number(value);
                if (Number.isFinite(n)) return n;
            }
            return null;
        }

        const ASSET_ID_KEYS = ["id", "asset", "asset_id", "assetId"];

        function normalizeAsset(raw, fallbackId) {
            if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
            let id = pickString(raw, ASSET_ID_KEYS);
            if (!id && typeof fallbackId === "string" && fallbackId !== "") id = fallbackId;
            if (!id) return null;
            // A bare 64-hex digest is the same identity as its prefixed form.
            if (/^[0-9a-fA-F]{64}$/.test(id)) id = "sha256:" + id.toLowerCase();

            const width = pickNumber(raw, ["width", "intrinsicWidth", "intrinsic_width"]);
            const height = pickNumber(raw, ["height", "intrinsicHeight", "intrinsic_height"]);
            const bytes = pickNumber(raw, ["bytes", "byteSize", "byte_size", "size"]);
            const mime = pickString(raw, ["mime", "mimeType", "mime_type",
                "content_type", "contentType"]) || "";
            const rawKind = pickString(raw, ["kind", "assetKind", "asset_kind"]);
            const kind = rawKind === "video" || mime.indexOf("video/") === 0 ? "video" : "still";
            const duration = pickNumber(raw, ["durationMs", "duration_ms", "duration"]);
            const thumbRaw = raw.thumbnail;
            const thumbnail = thumbRaw && typeof thumbRaw === "object" && !Array.isArray(thumbRaw)
                ? pickString(thumbRaw, ["url", "href"])
                : null;
            const posterRaw = raw.poster;
            const poster = posterRaw && typeof posterRaw === "object" && !Array.isArray(posterRaw)
                ? pickString(posterRaw, ["url", "href"])
                : thumbnail;

            return {
                id: id,
                name: pickString(raw, ["name", "display_name", "displayName",
                    "filename", "file_name"]) || id,
                mime: mime,
                kind: kind,
                durationMs: kind === "video" && duration !== null && duration > 0
                    ? Math.round(duration) : null,
                width: width !== null && width > 0 ? Math.round(width) : null,
                height: height !== null && height > 0 ? Math.round(height) : null,
                bytes: bytes !== null && bytes >= 0 ? bytes : null,
                url: pickString(raw, ["url", "href"]),
                thumbnail: thumbnail,
                poster: poster
            };
        }

        /** The inventory as a sorted array, or null when the payload is not one
         *  in any shape this page recognises (the caller reports that honestly
         *  instead of showing an empty list that looks like "no files"). */
        function normalizeAssets(payload) {
            let entries = null; // [raw, fallbackId] pairs
            if (Array.isArray(payload)) {
                entries = payload.map(function (raw) { return [raw, null]; });
            } else if (payload && typeof payload === "object") {
                let container = null;
                for (const key of ["assets", "items", "files"]) {
                    if (Array.isArray(payload[key])) {
                        container = payload[key];
                        break;
                    }
                }
                if (container) {
                    entries = container.map(function (raw) { return [raw, null]; });
                } else {
                    const keys = Object.keys(payload);
                    const allObjects = keys.length > 0 && keys.every(function (key) {
                        const value = payload[key];
                        return value && typeof value === "object" && !Array.isArray(value);
                    });
                    if (allObjects) {
                        entries = keys.map(function (key) { return [payload[key], key]; });
                    }
                }
            }
            if (!entries) return null;

            const seen = new Set();
            const out = [];
            for (const entry of entries) {
                const asset = normalizeAsset(entry[0], entry[1]);
                if (!asset || seen.has(asset.id)) continue;
                seen.add(asset.id);
                out.push(asset);
            }
            out.sort(function (a, b) {
                const an = a.name.toLowerCase();
                const bn = b.name.toLowerCase();
                if (an !== bn) return an < bn ? -1 : 1;
                return compareIds(a.id, b.id);
            });
            return out;
        }

        /**
         * GET /assets — one read at boot (quietly) and on demand afterwards.
         * A failed refresh keeps the last good list and says why it is stale;
         * the selection is dropped only if the asset it named is really gone.
         */
        async function refreshAssets(quiet) {
            if (inventory.assetsLoading) return;
            inventory.assetsLoading = true;
            inventory.assetsError = null;
            if (el.btnAssetsRefresh) {
                el.btnAssetsRefresh.disabled = true;
                el.btnAssetsRefresh.textContent = "Loading…";
            }
            renderAssetList();

            try {
                const data = await requestJson("GET", "/assets");
                const list = normalizeAssets(data);
                if (list === null) {
                    throw new Error("the answer was not an asset inventory");
                }
                inventory.assets = list;
                inventory.assetsLoaded = true;
                inventory.assetsStamp = clockStamp();

                // A refresh can retire the selection: say so once, alongside the
                // inventory result, rather than burying it under the next line.
                let cleared = false;
                if (inventory.selectedAsset && !assetById(inventory.selectedAsset)) {
                    inventory.selectedAsset = null;
                    cleared = true;
                }
                if (!quiet) {
                    logStatus(
                        "Asset inventory: " + inventory.assets.length + " file(s), read " +
                            inventory.assetsStamp + (cleared
                                ? " · the selected asset is no longer in it, selection cleared"
                                : ""),
                        "ok"
                    );
                } else if (cleared) {
                    logStatus(
                        "The selected image is no longer in the list, so the selection was cleared.",
                        "info"
                    );
                }
            } catch (err) {
                inventory.assetsError = err.message;
                logStatus(
                    quiet
                        ? "No asset inventory from this server (" + err.message +
                            "). Press Refresh inventory if still images are enabled."
                        : "Asset inventory unavailable: " + err.message,
                    quiet ? "info" : "err"
                );
            } finally {
                inventory.assetsLoading = false;
                if (el.btnAssetsRefresh) {
                    el.btnAssetsRefresh.disabled = false;
                    el.btnAssetsRefresh.textContent = "Refresh list";
                }
                renderImagePanel();
                if (runtime.wall) renderWallMap();
            }
        }

        /* ------------------------------------------------------------------ *
         * Managed library (GET /media) and uploads (POST /uploads)
         *
         * Uploads land in the same descriptor shape as the curated inventory,
         * so selection, preview and "Show on wall" are shared. The library is
         * kept apart only so the curated list keeps its own read and wording.
         * ------------------------------------------------------------------ */

        async function refreshMedia(quiet) {
            if (inventory.mediaLoading) return false;
            inventory.mediaLoading = true;
            inventory.mediaError = null;

            let ok = false;
            try {
                const data = await requestJson("GET", "/media");
                const list = normalizeAssets(data);
                if (list === null) {
                    throw new Error("the answer was not a file library");
                }
                inventory.mediaAssets = list;
                inventory.mediaState = "ready";
                ok = true;
                if (inventory.selectedAsset && assetById(inventory.selectedAsset) === null) {
                    inventory.selectedAsset = null;
                }
                if (!quiet) {
                    logStatus(
                        "Uploaded library: " + list.length +
                            (list.length === 1 ? " file." : " files."),
                        "ok"
                    );
                }
            } catch (err) {
                if (err.status === 403) {
                    inventory.mediaState = "forbidden";
                    if (!quiet) logStatus("Uploads are disabled on this server.", "info");
                } else {
                    inventory.mediaState = "error";
                    inventory.mediaError = err.message;
                    if (!quiet) logStatus("Uploaded library unavailable: " + err.message, "err");
                }
            } finally {
                inventory.mediaLoading = false;
                renderImagePanel();
                if (runtime.wall) renderWallMap();
            }
            return ok;
        }

        function renderMediaPanel() {
            renderUploadControls();
            renderMediaLibrary();
        }

        function renderMediaLibrary() {
            const wrap = el.mediaLibrary;
            const list = el.mediaList;
            if (!wrap || !list) return;

            wrap.hidden = inventory.mediaState === "forbidden";
            if (inventory.mediaState === "forbidden") return;

            if (el.mediaCount) {
                el.mediaCount.textContent = inventory.mediaState === "pending"
                    ? ""
                    : inventory.mediaAssets.length + (inventory.mediaAssets.length === 1 ? " file" : " files");
            }

            list.textContent = "";
            for (const asset of inventory.mediaAssets) {
                list.appendChild(buildMediaRow(asset));
            }
            list.hidden = inventory.mediaAssets.length === 0;

            let note = "";
            let kind = "info";
            if (inventory.mediaState === "pending") {
                note = "Reading the uploaded library…";
            } else if (inventory.mediaState === "error") {
                kind = "err";
                note = "Uploaded library unavailable: " + (inventory.mediaError || "unknown error") +
                    (inventory.mediaAssets.length > 0 ? ". Showing the files read earlier." : "");
            } else if (inventory.mediaAssets.length === 0) {
                note = "No uploaded files yet.";
            }
            if (el.mediaNote) {
                el.mediaNote.hidden = note === "";
                el.mediaNote.dataset.kind = kind;
                el.mediaNote.textContent = note;
            }
        }

        function buildMediaRow(asset) {
            const item = document.createElement("li");
            item.className = "media-item";

            const row = document.createElement("button");
            row.type = "button";
            row.className = "media-row";
            row.dataset.media = asset.id;
            row.dataset.kind = asset.kind;
            row.setAttribute("aria-pressed", String(inventory.selectedAsset === asset.id));
            row.title = asset.id + (asset.mime ? " · " + asset.mime : "")
                + (asset.kind === "video" ? " · video: playlist only" : "");

            let thumb;
            const thumbUrl = asset.poster || asset.thumbnail;
            if (thumbUrl) {
                thumb = document.createElement("img");
                thumb.className = "media-thumb";
                thumb.src = thumbUrl;
                thumb.alt = "";
                thumb.loading = "lazy";
            } else {
                thumb = document.createElement("span");
                thumb.className = "media-thumb media-thumb-none";
                thumb.setAttribute("aria-hidden", "true");
            }

            const name = document.createElement("span");
            name.className = "media-name";
            name.textContent = asset.name;

            const kind = document.createElement("span");
            kind.className = "media-kind";
            kind.textContent = asset.kind === "video"
                ? "Video" + (asset.durationMs !== null ? " · " + fmtDuration(asset.durationMs) : "")
                : "Still";

            const size = document.createElement("span");
            size.className = "media-size";
            size.textContent = fmtBytes(asset.bytes);

            row.append(thumb, name, kind, size);
            item.appendChild(row);
            return item;
        }

        function renderUploadControls() {
            if (!el.uploadBlock) return;
            el.uploadBlock.hidden = inventory.mediaState === "forbidden";
            if (!el.uploadFile || !el.btnUpload) return;
            el.uploadFile.disabled = inventory.uploadBusy;
            el.btnUpload.disabled = inventory.uploadBusy || selectedUploadFile() === null;
            el.btnUpload.textContent = !inventory.uploadBusy
                ? "Upload"
                : inventory.uploadStage === "processing" ? "Processing…" : "Uploading…";
        }

        function selectedUploadFile() {
            if (!el.uploadFile || !el.uploadFile.files) return null;
            return el.uploadFile.files.length > 0 ? el.uploadFile.files[0] : null;
        }

        function setUploadStatus(text, kind) {
            const node = el.uploadStatus;
            if (!node) return;
            node.dataset.kind = kind || "info";
            node.textContent = text || "";
        }

        function setUploadProgress(percent) {
            const node = el.uploadProgress;
            if (!node) return;
            node.hidden = false;
            if (percent === null) {
                node.removeAttribute("value");
                node.setAttribute("aria-valuetext", "Processing");
                return;
            }
            node.max = 100;
            node.value = percent;
            node.setAttribute("aria-valuetext", percent + "%");
        }

        function hideUploadProgress() {
            const node = el.uploadProgress;
            if (!node) return;
            node.hidden = true;
            node.removeAttribute("aria-valuetext");
            node.value = 0;
        }

        function startUpload() {
            if (inventory.uploadBusy) return;
            const file = selectedUploadFile();
            if (!file) {
                setUploadStatus("Choose an image or video file first.", "err");
                return;
            }

            inventory.uploadBusy = true;
            inventory.uploadStage = "uploading";
            setUploadStatus("Uploading… 0%", "busy");
            setUploadProgress(0);
            renderUploadControls();

            const xhr = new XMLHttpRequest();
            inventory.uploadXhr = xhr;
            xhr.open("POST", "/uploads?name=" + encodeURIComponent(file.name));
            xhr.setRequestHeader("Content-Type", file.type);

            xhr.upload.addEventListener("progress", function (event) {
                if (inventory.uploadXhr !== xhr || inventory.uploadStage !== "uploading") return;
                if (!event.lengthComputable || !(event.total > 0)) {
                    setUploadStatus("Uploading…", "busy");
                    return;
                }
                const percent = Math.min(100, Math.max(0,
                    Math.round((event.loaded / event.total) * 100)));
                setUploadProgress(percent);
                setUploadStatus("Uploading… " + percent + "%", "busy");
            });

            xhr.upload.addEventListener("load", function () {
                if (inventory.uploadXhr !== xhr || inventory.uploadStage !== "uploading") return;
                inventory.uploadStage = "processing";
                setUploadProgress(null);
                setUploadStatus("Processing…", "busy");
                renderUploadControls();
            });

            xhr.addEventListener("load", function () {
                if (inventory.uploadXhr !== xhr) return;
                let asset = null;
                let failure = null;
                if (xhr.status === 201) {
                    asset = normalizeAsset(uploadAssetPayload(xhr));
                    if (!asset) failure = "the server returned no usable image";
                } else {
                    failure = uploadFailureText(xhr);
                }
                finishUpload();
                if (failure !== null) {
                    setUploadStatus("Upload failed: " + failure, "err");
                    logStatus("Upload failed: " + failure, "err");
                    return;
                }
                uploadedAsset(asset);
            });

            xhr.addEventListener("error", function () {
                if (inventory.uploadXhr !== xhr) return;
                finishUpload();
                setUploadStatus("Upload failed: the server could not be reached.", "err");
                logStatus("Upload failed: the server could not be reached.", "err");
            });

            xhr.addEventListener("abort", function () {
                if (inventory.uploadXhr !== xhr) return;
                finishUpload();
                setUploadStatus("Upload cancelled.", "info");
            });

            xhr.send(file);
        }

        function finishUpload() {
            inventory.uploadXhr = null;
            inventory.uploadBusy = false;
            inventory.uploadStage = null;
            hideUploadProgress();
            renderUploadControls();
        }

        function uploadAssetPayload(xhr) {
            try {
                const data = JSON.parse(xhr.responseText);
                return data && typeof data === "object" ? data.asset : null;
            } catch (_err) {
                return null;
            }
        }

        function uploadFailureText(xhr) {
            let detail = "";
            try {
                const data = JSON.parse(xhr.responseText);
                if (data && typeof data.detail === "string") detail = data.detail;
            } catch (_err) {
                /* non-JSON body: fall through to the status line */
            }
            return detail !== "" ? detail : "HTTP " + xhr.status;
        }

        function uploadedAsset(asset) {
            inventory.mediaAssets = inventory.mediaAssets.filter(function (item) { return item.id !== asset.id; });
            inventory.mediaAssets.push(asset);
            inventory.mediaState = "ready";
            inventory.mediaError = null;
            if (asset.kind !== "video") inventory.selectedAsset = asset.id;
            if (el.uploadFile) el.uploadFile.value = "";
            if (el.uploadFileName) el.uploadFileName.textContent = "No file chosen";
            renderImagePanel();
            if (asset.kind === "video") {
                setUploadStatus("Ready: " + asset.name + " (video)", "ok");
                logStatus(
                    "Uploaded " + asset.name + ". Add it to the playlist on the physical page.",
                    "ok"
                );
            } else {
                setUploadStatus("Ready: " + asset.name, "ok");
                logStatus("Uploaded " + asset.name + ". Press Show on wall to display it.", "ok");
            }
            refreshMedia(true);
        }

        function renderImagePanel() {
            if (!el.imagePanel) return;
            renderActiveImage();
            renderAssetList();
            renderMediaPanel();
            renderMissingAsset();
            updateImageControls();
        }

        /** The active scene image, exactly as the server described it — the id,
         *  its name when the inventory knows it, the persisted intrinsic size and
         *  the fit. Nothing is inferred that the payload did not carry. */
        function renderActiveImage() {
            const node = el.imageActive;
            const text = el.imageActiveText;
            if (!node || !text) return;

            if (!runtime.wall) {
                node.dataset.state = "none";
                node.title = "";
                text.textContent = "Waiting for the server";
                return;
            }
            if (runtime.wall.contentType !== "image") {
                node.dataset.state = "other";
                node.title = "";
                text.textContent = contentLabel(runtime.wall.contentType);
                return;
            }

            const content = runtime.wall.content || {};
            const id = typeof content.asset === "string" ? content.asset : "";
            if (!id) {
                node.dataset.state = "missing";
                node.title = "";
                text.textContent = "An image with no file named";
                return;
            }

            const asset = assetById(id);
            const bits = [asset && asset.name ? asset.name : "Image " + shortAsset(id)];

            const rawW = content.intrinsicWidth !== undefined
                ? content.intrinsicWidth : (asset ? asset.width : null);
            const rawH = content.intrinsicHeight !== undefined
                ? content.intrinsicHeight : (asset ? asset.height : null);
            const width = Number(rawW);
            const height = Number(rawH);
            if (Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0) {
                bits.push(Math.round(width) + "×" + Math.round(height));
            }
            if (typeof content.fit === "string" && content.fit !== "") {
                bits.push(content.fit === "cover" ? "fills the wall" : "fit " + content.fit);
            }

            const missing = activeAssetMissing();
            if (missing) bits.push("not in the image list");
            else if (inventory.assetsError || inventory.mediaError) bits.push("image list may be out of date");
            else if (!inventory.assetsLoaded || inventory.mediaState === "pending") bits.push("image list not loaded yet");

            node.dataset.state = missing ? "missing" : "image";
            node.title = id;
            if (el.contentNow) el.contentNow.textContent = bits[0];
            text.textContent = bits.join(", ");
        }

        function renderAssetList() {
            const list = el.assetList;
            if (!list) return;

            // The note carries loading / stale / error; the count carries the
            // last successful read, so a failed refresh never looks like a
            // fresh one and a stale list never looks current.
            if (el.imageNote) {
                let note = "";
                let kind = "info";
                if (inventory.assetsLoading) {
                    note = "Reading the asset inventory…";
                } else if (inventory.assetsError) {
                    kind = "err";
                    note = "Inventory unavailable: " + inventory.assetsError +
                        (inventory.assetsLoaded
                            ? ". Showing the list read at " + inventory.assetsStamp + "."
                            : ".");
                }
                el.imageNote.hidden = note === "";
                el.imageNote.dataset.kind = kind;
                el.imageNote.textContent = note;
            }

            if (el.imageCount) {
                el.imageCount.textContent = inventory.assetsLoaded
                    ? inventory.assets.length + (inventory.assets.length === 1 ? " asset" : " assets") +
                        (inventory.assetsStamp ? " · read " + inventory.assetsStamp : "")
                    : "";
            }

            const activeId = activeImageId();
            list.textContent = "";
            for (const asset of inventory.assets) {
                list.appendChild(buildAssetRow(asset, asset.id === activeId));
            }
            list.hidden = inventory.assets.length === 0;

            if (el.imageEmpty) {
                let empty = "";
                if (inventory.assets.length === 0) {
                    if (inventory.assetsLoaded) {
                        empty = "No images found. Put JPEG or PNG files in the " +
                            "server's image folder, then press Refresh list.";
                    } else if (!inventory.assetsLoading && !inventory.assetsError) {
                        empty = "The image list has not loaded yet. Press Refresh list.";
                    }
                }
                el.imageEmpty.hidden = empty === "";
                el.imageEmpty.textContent = empty;
            }
        }

        function buildAssetRow(asset, isActive) {
            const item = document.createElement("li");
            item.className = "asset-item";

            const row = document.createElement("button");
            row.type = "button";
            row.className = "asset-row";
            row.dataset.asset = asset.id;
            row.setAttribute("aria-pressed", String(inventory.selectedAsset === asset.id));
            row.title = asset.id + (asset.mime ? " · " + asset.mime : "");

            const name = document.createElement("span");
            name.className = "asset-name";
            name.textContent = asset.name;

            const dims = document.createElement("span");
            dims.className = "asset-dims mono";
            dims.textContent =
                asset.width !== null && asset.height !== null
                    ? asset.width + "×" + asset.height
                    : "-";

            const ar = document.createElement("span");
            ar.className = "asset-ar mono";
            ar.textContent =
                asset.width !== null && asset.height !== null
                    ? "ar " + fmtAspect(aspectOf(asset.width, asset.height))
                    : "ar -";

            const size = document.createElement("span");
            size.className = "asset-bytes mono";
            size.textContent = fmtBytes(asset.bytes);

            const id = document.createElement("span");
            id.className = "asset-id mono";
            id.textContent = shortAsset(asset.id);
            id.title = asset.id;

            const flag = document.createElement("span");
            flag.className = "asset-flag";
            flag.textContent = "On the wall";
            flag.hidden = !isActive;

            row.append(name, dims, ar, size, id, flag);
            item.appendChild(row);
            return item;
        }

        function selectAsset(id) {
            const asset = assetById(id);
            if (!asset) return;
            if (asset.kind === "video") {
                logStatus(
                    "Video files play from the playlist on the physical page; they cannot be shown as a still scene.",
                    "info"
                );
                return;
            }
            if (inventory.selectedAsset === asset.id) {
                inventory.selectedAsset = null;
                logStatus("Asset selection cleared.", "info");
            } else {
                inventory.selectedAsset = asset.id;
                logStatus(
                    "Selected " + asset.name + ". Press Show on wall to put it on the wall.",
                    "info"
                );
            }
            renderAssetList();
            renderMediaLibrary();
            updateImageControls();
        }

        /**
         * The active asset is in the scene but not in the inventory: the wall is
         * rendering an explicit error state (PROTOCOL.md keeps the id until an
         * operator acts), so this block names it and offers the three ways out —
         * a replacement asset, colour, or calibration.
         */
        function renderMissingAsset() {
            const box = el.imageMissing;
            if (!box) return;
            const id = activeImageId();
            if (!id || !activeAssetMissing()) {
                box.hidden = true;
                return;
            }
            box.hidden = false;
            box.dataset.kind = runtime.wall && runtime.wall.contentType === "image" ? "bad" : "warn";

            if (el.imageMissingTitle) {
                el.imageMissingTitle.textContent =
                    "Active image " + shortAsset(id) + " is not in the inventory";
            }
            if (el.imageMissingText) {
                el.imageMissingText.textContent =
                    "The file was removed, replaced, or it failed validation, so the wall " +
                    "renders an error instead of the picture. The id stays in the scene " +
                    "until you act: pick a replacement below, or put the wall back on " +
                    "colour or calibration.";
                el.imageMissingText.title = id;
            }
            if (el.btnMissingPick) {
                const hasAssets = inventory.assets.length > 0 ||
                    (inventory.mediaState === "ready" && inventory.mediaAssets.length > 0);
                el.btnMissingPick.textContent =
                    hasAssets ? "Pick a replacement" : "Refresh the image list";
                el.btnMissingPick.dataset.mode = hasAssets ? "pick" : "refresh";
            }
            for (const button of box.querySelectorAll("button[data-content-action]")) {
                button.disabled = runtime.pendingContent !== null;
            }
        }

        function updateImageControls() {
            const active = activeImageId();

            if (el.imageSel) {
                if (!inventory.selectedAsset) {
                    el.imageSel.textContent = active ? "No replacement selected" : "No image selected";
                    el.imageSel.title = "";
                } else {
                    const asset = assetById(inventory.selectedAsset);
                    const bits = [asset ? asset.name : shortAsset(inventory.selectedAsset)];
                    if (asset && asset.width !== null && asset.height !== null) {
                        bits.push(asset.width + "×" + asset.height);
                    }
                    if (active && inventory.selectedAsset === active) bits.push("already on the wall");
                    el.imageSel.textContent = bits.join(", ");
                    el.imageSel.title = inventory.selectedAsset;
                }
            }

            if (el.btnImageApply) {
                const applying = runtime.pendingContent === "image";
                const same = !!inventory.selectedAsset && inventory.selectedAsset === active;
                const selected = inventory.selectedAsset ? assetById(inventory.selectedAsset) : null;
                const isVideo = !!selected && selected.kind === "video";
                const canApply =
                    wallReady() && !!inventory.selectedAsset && !same && !isVideo && runtime.pendingContent === null;
                el.btnImageApply.disabled = !canApply;
                el.btnImageApply.textContent = applying
                    ? "Applying…"
                    : isVideo ? "Video: playlist only" : same ? "Already on the wall" : "Show on wall";
                el.btnImageApply.title = isVideo
                    ? "A video plays from the playlist on the physical page."
                    : !inventory.selectedAsset
                        ? "Pick an image first. Nothing is sent without a selection."
                        : same
                            ? "This image is already on the wall."
                            : "Show this image across the whole wall";
            }

            // The preview follows the selection only: the wall's own copy of the
            // image is the wall's business, and an asset with no URL in the
            // inventory gets no guessed one.
            if (el.imagePreview && el.imagePreviewImg && el.imagePreviewNote) {
                const active = activeImageId();
                const asset = inventory.selectedAsset ? assetById(inventory.selectedAsset) :
                    (active ? assetById(active) : null);
                const url = asset ? asset.url : null;
                const onWallPreview = !inventory.selectedAsset && !!active && !!asset;
                if (asset && url) {
                    if (el.imagePreviewImg.getAttribute("src") !== url) {
                        el.imagePreview.dataset.failed = "false";
                        el.imagePreviewImg.src = url;
                        el.imagePreviewImg.alt = "Preview of " + asset.name;
                    }
                    const failed = el.imagePreview.dataset.failed === "true";
                    el.imagePreview.hidden = failed;
                    el.imagePreviewNote.hidden = !failed && !onWallPreview;
                    el.imagePreviewNote.textContent = failed
                        ? "The preview did not load. Refresh the list to try again."
                        : onWallPreview
                            ? "This is the image on the wall. Pick another to replace it."
                            : "";
                } else {
                    if (el.imagePreviewImg.getAttribute("src")) {
                        el.imagePreviewImg.removeAttribute("src");
                        el.imagePreviewImg.alt = "";
                    }
                    el.imagePreview.hidden = true;
                    el.imagePreviewNote.hidden = false;
                    el.imagePreviewNote.textContent = asset
                        ? "This image has no preview."
                        : "Pick an image from the list.";
                }
            }
        }

        /**
         * `PUT /scene` with the selected asset — the only place an image scene
         * is written, and it refuses to run without a selection.
         */
        async function applyImageScene() {
            if (!runtime.wall) return;
            const asset = inventory.selectedAsset;
            if (!asset) {
                logStatus("Pick an image from the list first.", "err");
                return;
            }
            const entry = assetById(asset);
            if (entry && entry.kind === "video") {
                logStatus(
                    "A video plays from the playlist on the physical page; it cannot be applied as a still scene.",
                    "err"
                );
                return;
            }
            if (asset === activeImageId()) return;
            if (runtime.pendingContent !== null) return; // one scene save at a time

            runtime.pendingContent = "image";
            renderWallContent("image");
            updateImageControls();

            try {
                const data = await requestJson("PUT", "/scene", {
                    content: { type: "image", asset: asset, fit: "cover" }
                });
                const next = normalizeWall(data);
                if (!next || next.width <= 0 || next.height <= 0) {
                    logStatus(
                        "Image request returned no usable wall state. Waiting for a wall update to confirm it.",
                        "err"
                    );
                    return;
                }
                runtime.wall = next;
                runtime.contentView = "image";
                logStatus(
                    "Showing the image on the wall (revision " + runtime.wall.revision + ").",
                    "ok"
                );
            } catch (err) {
                logStatus("Could not show the image: " + err.message, "err");
            } finally {
                runtime.pendingContent = null;
                renderWall();
            }
        }

        /** Recovery from a missing asset: put the inventory under the cursor so
         *  the replacement is one click away. */
        function focusAssetPicker() {
            runtime.contentView = "image";
            if (runtime.wall) renderWallContent(runtime.wall.contentType);
            const hasManaged = inventory.mediaState === "ready" && inventory.mediaAssets.length > 0;
            if (inventory.assets.length === 0 && !hasManaged) {
                refreshAssets(false).then(focusFirstAsset);
                return;
            }
            focusFirstAsset();
            logStatus("Pick an image, then press Show on wall.", "info");
        }

        function focusFirstAsset() {
            const first =
                (el.assetList && el.assetList.querySelector("button[data-asset]")) ||
                (el.mediaList && el.mediaList.querySelector("button[data-media]"));
            if (!first) return;
            if (typeof first.scrollIntoView === "function") {
                first.scrollIntoView({ block: "nearest" });
            }
            first.focus();
        }

        /* ------------------------------------------------------------------ *
         * Image coverage — who can and cannot show a still image
         * ------------------------------------------------------------------ */

        return { activeImageId, applyImageScene, assetById, focusAssetPicker, refreshAssets, refreshMedia, renderImagePanel, renderUploadControls, selectAsset, selectedUploadFile, setUploadStatus, shortAsset, startUpload, updateImageControls, model: { normalizeAsset, normalizeAssets } };
    }
};
