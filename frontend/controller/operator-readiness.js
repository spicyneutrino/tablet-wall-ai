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

    /* Server-check facts come only from readiness; live tablet counts use the
     * current configuration. Missing fields stay unknown rather than consulting
     * guessed aliases such as "status" or "wifi_name". */
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
                    : "This URL is not a login or pairing credential.";
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
            ["Layout", layoutText],
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
            ["Connected tablets", body && Number.isFinite(devices.online) && Number.isFinite(devices.total)
                ? devices.online + " connected of " + devices.total + " registered tablets"
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
            status = "Server checks could not be read: " + error + ". Refresh to try again.";
            kind = "err";
        } else if (malformed) {
            status = "The server checks response did not include the expected fields. Refresh server checks to retry.";
            kind = "warn";
        } else if (body === null) {
            status = "Reading server checks…";
            kind = "info";
        } else if (errors.length) {
            status = "Server checks reported" + (at ? " at " + at : "") + " with " + errors.length + " issue" + (errors.length === 1 ? "" : "s") + " below.";
            kind = "warn";
        } else {
            status = "Checked" + (at ? " at " + at : "") + ".";
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
        const { $, setTextIfChanged } = typeof module !== "undefined" && module.exports ? require("./operator-dom.js") : root.OperatorDom;

        let data = null, fetchedAt = null, failure = null, qrFailed = false, loading = false, qrRetry = 0;

        function factList(element, pairs, key) {
            if (element.dataset.key === key) return;
            element.replaceChildren();
            pairs.forEach(([term, value]) => {
                const dt = document.createElement("dt"), dd = document.createElement("dd");
                if (term === "Security trust") dd.className = "callout callout-warning";
                dt.textContent = term;
                dd.textContent = typeof value === "object" ? JSON.stringify(value) : value;
                element.append(dt, dd);
            });
            element.dataset.key = key;
        }

        function render() {
            const model = view(data, { error: failure, fetchedAt: fetchedAt });
            const status = $("readiness-status");
            setTextIfChanged(status, model.status.text);
            status.dataset.kind = model.status.kind;

            $("tablet-url").textContent = model.url.href || "";
            $("tablet-join-line").hidden = $("join-network").hidden = !model.url.copyable;
            $("tablet-url-note").textContent = /loopback/.test(model.url.note) ? "Reachable from this computer only." : model.url.note;
            if ($("tablet-join-guidance")) $("tablet-join-guidance").textContent = model.url.note;

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
                : "The QR encodes only the join address, not a credential.";

            const overview = new Set(["Wi-Fi", "Security trust"]);
            const backup = new Set(["Backup manifest", "Backup proof", "Restore rehearsal", "Backup scope"]);
            const facts = model.facts.filter(([name, value]) => overview.has(name) && !(name === "Wi-Fi" && String(value).startsWith("Not reported"))).map(([name, value]) => [name,
                name === "Security trust" && String(value).startsWith("Trusted local hotspot") ? "Trusted local hotspot only" : value]);
            const backupFacts = model.facts.filter(([name]) => backup.has(name));
            const details = model.facts.filter(([name]) => !overview.has(name) && !backup.has(name))
                .map(([name, value]) => [name === "Image content" ? "Content at last check" : name, value]);
            factList($("operator-readiness-facts"), facts, JSON.stringify(facts));
            factList($("operator-readiness-backup"), backupFacts, JSON.stringify(backupFacts));
            const guidance = model.facts.filter(([name]) => overview.has(name));
            factList($("operator-readiness-details"), [...details, ...guidance], JSON.stringify([...details, ...guidance]));
            factList($("operator-readiness-paths"), model.paths, JSON.stringify(model.paths));

            const errors = $("readiness-errors");
            errors.hidden = !model.errors.length;
            errors.textContent = model.errors.length
                ? "Tablet joining is unavailable. " + model.errors.join(" · ")
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

            $("readiness-refreshed").hidden = !failure || fetchedAt === null;
            $("readiness-refreshed").textContent = fetchedAt === null
                ? "Not read from the server yet."
                : "Last successful read at " + new Date(fetchedAt).toLocaleTimeString() + ".";
            const refresh = $("btn-readiness-refresh");
            refresh.disabled = loading;
            refresh.setAttribute("aria-label", loading ? "Refreshing server checks…" : failure ? "Retry server checks" : "Refresh server checks");
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
            const copied = await copyText(model.url.href);
            $("readiness-message").textContent = copied ? "Tablet address copied." : "Copy failed. Select and copy the text address.";
            $("copy-tablet-url").textContent = copied ? "Copied" : "Copy";
            $("copy-tablet-url").setAttribute("aria-label", copied ? "Copied tablet address" : "Copy tablet address");
            $("copy-tablet-url").addEventListener("blur", () => {
                $("copy-tablet-url").textContent = "Copy";
                $("copy-tablet-url").setAttribute("aria-label", "Copy tablet address");
            }, { once: true });
        });

        return { render, load, refresh: load };
    }

    const exported = { view, create, READINESS_PATH };
    if (typeof module !== "undefined" && module.exports) module.exports = exported;
    else root.OperatorReadiness = exported;
}(typeof window !== "undefined" ? window : globalThis));
