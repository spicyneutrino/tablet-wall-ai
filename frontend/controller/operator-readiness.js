"use strict";
window.OperatorReadiness = {
    create({ state, api, copyText }) {
        const $ = id => document.getElementById(id);
        $("operator-readiness").innerHTML = `<section class="card" aria-labelledby="readiness-title"><h2 id="readiness-title">Join &amp; readiness</h2>
            <p id="operator-connection" role="status">Connecting to operator updates…</p>
            <label class="field" for="tablet-url">Tablet address<input class="inp" id="tablet-url" readonly value="Address not configured"></label>
            <button class="btn" type="button" id="copy-tablet-url" disabled>Copy tablet URL</button><p id="tablet-url-note"></p>
            <img id="tablet-qr" alt="QR code for the configured tablet address" hidden><p id="tablet-qr-note">QR is not provided by this server. Use the text address.</p>
            <dl id="operator-readiness-facts" class="operator-facts"></dl>
            <details><summary>Power, fullscreen and kiosk setup</summary><p>Keep each tablet on power. Screen sleep and wake are managed by its OS. The server cannot wake, unlock or power a tablet.</p>
                <p>Fullscreen needs a gesture on the tablet. Open the client menu and tap Fullscreen. On iPad, use a consistent Home Screen launch or Guided Access. On Android, verify stay-awake while charging, screen timeout and kiosk settings on the installed OS.</p>
                <p>Wake lock unavailable on HTTP is expected. It does not mean the image failed. OS settings and actual screen brightness require a person at the wall.</p>
            </details><p id="readiness-message" role="status" aria-live="polite"></p></section>`;
        let fallbackOrigin = null, url = null;
        function render() {
            const caps = state.capabilities || {}, readiness = state.readiness || caps.readiness || {};
            const origin = caps.tablet_origin || readiness.tablet_origin || fallbackOrigin;
            try {
                const address = new URL(caps.tablet_url || "/client/", origin);
                const host = address.hostname.toLowerCase().replace(/\.+$/, "");
                if (!["http:", "https:"].includes(address.protocol) || address.username || address.password) throw new Error("Invalid tablet address");
                url = address.href;
                $("tablet-url").value = url; $("copy-tablet-url").disabled = false;
                $("tablet-url-note").textContent = ["localhost", "[::1]"].includes(host) || /^127\./.test(host)
                    ? "This is a loopback address. It opens only on this computer. Configure a tablet-reachable origin before joining."
                    : "Open this address on each tablet on the same Wi-Fi. This URL is not a login or pairing credential.";
            } catch (_) { url = null; $("tablet-url").value = "Tablet address not configured"; $("copy-tablet-url").disabled = true; $("tablet-url-note").textContent = "Configure the server’s tablet origin. The operator address may be reachable only on this laptop."; }
            const qr = caps.tablet_qr_url || readiness.tablet_qr_url;
            $("tablet-qr").hidden = !qr; $("tablet-qr-note").hidden = !!qr;
            if (qr) $("tablet-qr").src = qr;
            const facts = [
                ["Server readiness", readiness.status || "Not reported"], ["Database", readiness.database || readiness.storage || "Not reported"],
                ["Wi-Fi", readiness.wifi_name || caps.wifi_name || "Not reported. Join the same network as the wall server."],
                ["Layout", state.layoutKind === "physical" ? "Measured millimetres" : "Logical units"],
                ["Security mode", caps.security_mode || readiness.security_mode || "Not reported. No authentication claim is made."],
                ["Uploads", typeof caps.uploads === "boolean" ? caps.uploads ? "Enabled on operator path" : "Disabled; use configured image folder" : "Not reported"],
                ["Diagnostics", typeof caps.diagnostics === "boolean" ? caps.diagnostics ? "Available to admitted operator" : "Unavailable on this path" : "Use Refresh diagnostics below to check"],
                ["Data paths", readiness.data_paths ? JSON.stringify(readiness.data_paths) : "Not reported"],
                ["Last verified backup", readiness.backup && (readiness.backup.verified_at || readiness.backup.status) || readiness.backup_verified_at || "Not reported"],
                ["Last restore rehearsal", readiness.restore_verified_at || "Not reported"],
                ["Backup scope", "Wall recovery includes referenced content. Unused uploads require a separate full-library copy."],
                ["Image confirmation", "Only current matching paint reports count. Online transport does not prove image display or that the OS screen is lit."]
            ];
            const list = $("operator-readiness-facts");
            const key = JSON.stringify(facts);
            if (list.dataset.key !== key) {
                list.replaceChildren(); facts.forEach(([term, value]) => {
                    const dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = term; dd.textContent = typeof value === "object" ? JSON.stringify(value) : value; list.append(dt, dd);
                }); list.dataset.key = key;
            }
        }
        async function load() {
            try { const result = await api("GET", "/operator-config"); fallbackOrigin = result.tablet_origin; }
            catch (error) { $("readiness-message").textContent = "Tablet address lookup failed. " + error.message + " Reload configuration to retry."; }
            render();
        }
        $("copy-tablet-url").addEventListener("click", async () => { $("readiness-message").textContent = await copyText(url) ? "Tablet address copied." : "Copy failed. Select and copy the text address."; });
        return { render, load };
    }
};
