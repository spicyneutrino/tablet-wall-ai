"use strict";
(function (root) {
    const READINESS_PATH = "/api/v3/readiness";

    const LAYOUT_LABEL = {
        physical: "Measured millimetres (physical)",
        logical: "Logical units"
    };

    function stringOrNull(value) {
        return typeof value === "string" && value.trim() ? value : null;
    }

    function objectOrEmpty(value) {
        return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    }

    function stringList(value) {
        return Array.isArray(value) ? value.filter(item => typeof item === "string" && item.trim()) : [];
    }

    function clock(value) {
        return value === null || value === undefined ? null : new Date(value).toLocaleTimeString();
    }

    /* The server's readiness body is the only source of these facts. A field the
     * server did not send stays unknown; guessed aliases such as "status" or
     * "wifi_name" are deliberately not consulted. */
    const SCHEMA_KEYS = ["tablet_url", "join_qr_url", "wifi", "security", "content",
        "wall", "devices", "storage", "backup", "restore_rehearsal", "advice", "errors"];

    function view(data, options) {
        const settings = options || {};
        const raw = data && typeof data === "object" && !Array.isArray(data) ? data : null;
        const malformed = raw !== null && !SCHEMA_KEYS.some(key =>
            Object.prototype.hasOwnProperty.call(raw, key));
        const body = malformed ? null : raw;
        const wifi = objectOrEmpty(body && body.wifi);
        const security = objectOrEmpty(body && body.security);
        const content = objectOrEmpty(body && body.content);
        const wall = objectOrEmpty(body && body.wall);
        const devices = objectOrEmpty(body && body.devices);
        const storage = objectOrEmpty(body && body.storage);
        const backup = objectOrEmpty(body && body.backup);
        const rehearsal = objectOrEmpty(body && body.restore_rehearsal);
        const errors = stringList(body && body.errors);
        const advice = stringList(body && body.advice);

        let href = null, copyable = false, note;
        const rawUrl = stringOrNull(body && body.tablet_url);
        if (rawUrl === null) {
            note = malformed
                ? "The readiness response did not include a tablet address."
                : body === null
                    ? "Readiness has not been read yet, so the tablet address is unknown."
                    : "No tablet address is configured. Set the server's tablet origin, then refresh.";
        } else {
            try {
                const address = new URL(rawUrl);
                const host = address.hostname.toLowerCase().replace(/\.+$/, "");
                if (!["http:", "https:"].includes(address.protocol) || address.username || address.password) {
                    throw new Error("unusable origin");
                }
                href = address.href;
                copyable = true;
                note = ["localhost", "[::1]"].includes(host) || /^127\./.test(host)
                    ? "This is a loopback address. It opens only on this computer. Configure a tablet-reachable origin before joining."
                    : "Open this address on each tablet on the same Wi-Fi. This URL is not a login or pairing credential.";
            } catch (_) {
                note = "The server reported a tablet address that is not a usable http or https origin. Fix the tablet origin, then refresh.";
            }
        }

        const rawQr = stringOrNull(body && body.join_qr_url);
        let qrPath = false;
        if (rawQr !== null && rawQr.startsWith("/")) {
            const origin = settings.operatorOrigin || root.location && root.location.origin;
            try { qrPath = !!origin && new URL(rawQr, origin).origin === origin; }
            catch (_) { qrPath = false; }
        }
        const qr = {
            href: copyable && qrPath ? rawQr : null,
            state: !copyable || rawQr === null ? "absent" : qrPath ? "ready" : "unusable"
        };
        if (qr.state === "unusable") {
            note += " The join QR address is not a same-origin path, so it is not shown.";
        }

        const layout = body && stringOrNull(wall.layout);
        const layoutText = layout ? LAYOUT_LABEL[layout] || "Not reported: unrecognised layout " + JSON.stringify(layout)
            : body === null ? "Unknown: live wall state unavailable." : "Not reported";
        const wallParts = [];
        if (layoutText) wallParts.push(layoutText);
        if (body && wall.revision !== null && wall.revision !== undefined) wallParts.push("revision " + wall.revision);
        if (body && stringOrNull(wall.generation)) wallParts.push("generation " + stringOrNull(wall.generation));
        if (body && wall.schema !== null && wall.schema !== undefined) wallParts.push("schema " + wall.schema);
        const wallText = wallParts.length ? wallParts.join(" · ") : "Unknown: live wall state unavailable.";

        const transport = body && stringOrNull(security.transport);
        const authentication = body && stringOrNull(security.authentication);
        const uploads = body ? security.uploads : undefined;
        const uploadsText = uploads === "loopback" || uploads === "proxy"
            ? "Enabled on the " + uploads + " path"
            : uploads === "disabled"
                ? "Disabled; use the configured image folder"
                : "Not reported";
        const trust = body && stringOrNull(security.trust);

        let backupText;
        if (body === null || backup.recorded === undefined) backupText = "Not reported";
        else if (backup.recorded === true) {
            const at = stringOrNull(backup.last_manifest_at);
            backupText = at ? at + " — a snapshot was recorded on disk" : "A snapshot is recorded; its timestamp was not reported";
        } else backupText = "No backup snapshot is recorded";

        let rehearsalText;
        if (body === null || rehearsal.recorded === undefined) rehearsalText = "Not reported";
        else if (rehearsal.recorded === true) {
            const at = stringOrNull(rehearsal.completed_utc);
            rehearsalText = at ? at + " — recorded" : "A rehearsal is recorded; its timestamp was not reported";
        } else rehearsalText = "No restore rehearsal recorded. A backup is not proven restorable.";

        const backupProof = rehearsal.recorded === true
            ? "A rehearsal is recorded, but it does not prove this snapshot restores. Verification is not reported."
            : "Not verified. A manifest is a record on disk, not proof that the wall restores.";

        const facts = [
            ["Wi-Fi", wifi.known === true && stringOrNull(wifi.name)
                ? stringOrNull(wifi.name)
                : "Not reported. Join the same network as the wall server."],
            ["Layout", wallText],
            ["Security transport", transport ? transport.toUpperCase() : "Not reported"],
            ["Authentication", authentication === "disabled"
                ? "None. Trusted local hotspot only."
                : authentication === "shared-secret"
                    ? "Shared secret. Not a per-tablet identity."
                    : "Not reported"],
            ["Uploads", uploadsText],
            ["Security trust", trust || "Not reported"],
            ["Image content", content.summary
                ? content.summary + (stringOrNull(content.type) ? " (" + content.type + ")" : "")
                : "Not reported"],
            ["Tablets", body && Number.isFinite(devices.online) && Number.isFinite(devices.total)
                ? devices.online + " online of " + devices.total + " registered"
                : "Not reported"],
            ["Storage", body && storage.readable === true ? "Readable"
                : body && storage.readable === false ? "Not readable or the database is unavailable" : "Not reported"],
            ["Backup manifest", backupText],
            ["Backup proof", backupProof],
            ["Restore rehearsal", rehearsalText],
            ["Backup scope", stringOrNull(backup.scope) || "Not reported. Assume only referenced content is included."],
            ["Image confirmation", "Only current matching paint reports count. Online transport does not prove image display or that the OS screen is lit."]
        ];

        const paths = [
            ["Database", stringOrNull(storage.database) || "Not reported"],
            ["Curated assets", stringOrNull(storage.assets) || "Not reported"],
            ["Uploaded media", stringOrNull(storage.media) || "Not reported"],
            ["Backup directory", stringOrNull(storage.backup_dir) || "Not reported"]
        ];

        const error = stringOrNull(settings.error);
        const at = clock(settings.fetchedAt);
        let status, kind;
        if (error) {
            status = "Readiness could not be read: " + error + ". Retry readiness to check again.";
            kind = "err";
        } else if (malformed) {
            status = "The readiness response did not include the expected fields. Refresh readiness to retry.";
            kind = "warn";
        } else if (body === null) {
            status = "Reading server readiness…";
            kind = "info";
        } else if (errors.length) {
            status = "Readiness reported" + (at ? " at " + at : "") + " with " + errors.length + " issue" + (errors.length === 1 ? "" : "s") + " below.";
            kind = "warn";
        } else {
            status = "Readiness reported" + (at ? " at " + at : "") + ". This is server state only; it does not prove a tablet is displaying the wall.";
            kind = "ok";
        }

        return {
            url: { href: href, copyable: copyable, note: note },
            qr: qr,
            status: { text: status, kind: kind },
            facts: facts,
            paths: paths,
            errors: errors,
            advice: advice
        };
    }

    function create({ state, api, copyText }) {
        const $ = id => document.getElementById(id);
        $("operator-readiness").innerHTML = `<section class="card" aria-labelledby="readiness-title"><h2 id="readiness-title">Join &amp; readiness</h2>
            <p id="readiness-status" role="status" aria-live="polite">Reading server readiness…</p>
            <p id="readiness-errors" role="alert" hidden></p>
            <label class="field" for="tablet-url">Tablet address<input class="inp" id="tablet-url" readonly value="Tablet address not configured"></label>
            <button class="btn" type="button" id="copy-tablet-url" disabled>Copy tablet URL</button><p id="tablet-url-note"></p>
            <figure id="tablet-qr-figure" hidden><img id="tablet-qr" alt="QR code for the configured tablet address"><figcaption id="tablet-qr-note">Scan to open the tablet page. The QR encodes only the join address, not a credential.</figcaption></figure>
            <p id="tablet-qr-error" role="alert" hidden>QR image failed to load. The text address above still works. <button class="btn" type="button" id="btn-readiness-qr-retry">Retry QR</button></p>
            <p class="hint" id="readiness-refreshed">Not read yet.</p>
            <button class="btn" type="button" id="btn-readiness-refresh">Refresh readiness</button>
            <dl id="operator-readiness-facts" class="operator-facts"></dl>
            <details id="readiness-paths"><summary>Data paths</summary><dl class="operator-facts" id="operator-readiness-paths"></dl></details>
            <details id="readiness-advice"><summary>What this server cannot do</summary><ul id="operator-readiness-advice"></ul></details>
            <p id="readiness-message" role="status" aria-live="polite"></p></section>`;
        let data = null, fetchedAt = null, failure = null, qrFailed = false, loading = false, qrRetry = 0;

        function factList(element, pairs, key) {
            if (element.dataset.key === key) return;
            element.replaceChildren();
            pairs.forEach(([term, value]) => {
                const dt = document.createElement("dt"), dd = document.createElement("dd");
                dt.textContent = term;
                dd.textContent = typeof value === "object" ? JSON.stringify(value) : value;
                element.append(dt, dd);
            });
            element.dataset.key = key;
        }

        function render() {
            const model = view(data, { error: failure, fetchedAt: fetchedAt });
            const status = $("readiness-status");
            status.textContent = model.status.text;
            status.dataset.kind = model.status.kind;

            const url = $("tablet-url");
            url.value = model.url.href || "Tablet address not configured";
            $("copy-tablet-url").disabled = !model.url.copyable;
            $("tablet-url-note").textContent = model.url.note;

            const figure = $("tablet-qr-figure"), image = $("tablet-qr"), qrError = $("tablet-qr-error");
            figure.hidden = !model.qr.href;
            qrError.hidden = !(qrFailed && model.qr.href);
            const qrSrc = model.qr.href && model.qr.href + (model.qr.href.includes("?") ? "&" : "?")
                + "tablet_url=" + encodeURIComponent(model.url.href) + "&retry=" + qrRetry;
            if (qrSrc && image.getAttribute("src") !== qrSrc && !qrFailed) {
                image.hidden = true;
                image.setAttribute("src", qrSrc);
            }
            if (!model.qr.href) { qrFailed = false; image.removeAttribute("src"); }
            $("tablet-qr-note").textContent = model.qr.state === "unusable"
                ? "The server did not provide a usable same-origin QR address. Use the text address."
                : "Scan to open the tablet page. The QR encodes only the join address, not a credential.";

            factList($("operator-readiness-facts"), model.facts, JSON.stringify(model.facts));
            factList($("operator-readiness-paths"), model.paths, JSON.stringify(model.paths));

            const errors = $("readiness-errors");
            errors.hidden = !model.errors.length;
            errors.textContent = model.errors.length
                ? "Server reported: " + model.errors.join(" · ")
                : "";

            const advice = $("readiness-advice");
            advice.hidden = !model.advice.length;
            if (advice.dataset.key !== JSON.stringify(model.advice)) {
                const list = $("operator-readiness-advice");
                list.replaceChildren();
                model.advice.forEach(item => {
                    const li = document.createElement("li");
                    li.textContent = item;
                    list.append(li);
                });
                advice.dataset.key = JSON.stringify(model.advice);
            }

            $("readiness-refreshed").textContent = fetchedAt === null
                ? "Not read from the server yet."
                : "Last successful read at " + new Date(fetchedAt).toLocaleTimeString() + ".";
            const refresh = $("btn-readiness-refresh");
            refresh.disabled = loading;
            refresh.textContent = loading ? "Refreshing…" : failure ? "Retry readiness" : "Refresh readiness";
            return model;
        }

        async function load() {
            if (loading) return false;
            loading = true;
            render();
            try {
                const result = await api("GET", READINESS_PATH);
                if (!result || typeof result !== "object" || Array.isArray(result)) {
                    throw new Error("the server returned an empty readiness body");
                }
                if (!SCHEMA_KEYS.some(key => Object.prototype.hasOwnProperty.call(result, key))) {
                    throw new Error("the readiness response did not include the expected fields");
                }
                data = result;
                fetchedAt = Date.now();
                failure = null;
                qrFailed = false;
                state.readiness = data;
                state.readinessFetchedAt = fetchedAt;
            } catch (error) {
                failure = error && error.message ? error.message : "request failed";
            } finally {
                loading = false;
                render();
            }
            return failure === null;
        }

        $("btn-readiness-refresh").addEventListener("click", load);
        $("btn-readiness-qr-retry").addEventListener("click", function () {
            qrFailed = false;
            qrRetry += 1;
            const image = $("tablet-qr");
            image.removeAttribute("src");
            render();
            load();
        });
        $("tablet-qr").addEventListener("error", function () {
            qrFailed = true;
            render();
        });
        $("tablet-qr").addEventListener("load", function () {
            const image = $("tablet-qr");
            if (image.currentSrc === image.src) image.hidden = false;
        });
        $("copy-tablet-url").addEventListener("click", async function () {
            const model = view(data, { error: failure, fetchedAt: fetchedAt });
            $("readiness-message").textContent = await copyText(model.url.href)
                ? "Tablet address copied."
                : "Copy failed. Select and copy the text address.";
        });

        return { render, load, refresh: load };
    }

    const exported = { view, create, READINESS_PATH };
    if (typeof module !== "undefined" && module.exports) module.exports = exported;
    else root.OperatorReadiness = exported;
}(typeof window !== "undefined" ? window : globalThis));
