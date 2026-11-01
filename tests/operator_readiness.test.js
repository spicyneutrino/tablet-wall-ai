"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function element(id) {
    return {
        id: id, hidden: false, disabled: false, textContent: "", value: "", innerHTML: "",
        dataset: {}, attrs: {}, children: [], listeners: {},
        setAttribute(key, value) { this.attrs[key] = String(value); },
        getAttribute(key) { return Object.prototype.hasOwnProperty.call(this.attrs, key) ? this.attrs[key] : null; },
        removeAttribute(key) { delete this.attrs[key]; },
        replaceChildren() { this.children = []; },
        append(...nodes) { this.children.push(...nodes); },
        addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); },
        click() { (this.listeners.click || []).forEach(handler => handler({})); }
    };
}

function harness() {
    const ids = ["operator-readiness", "readiness-status", "readiness-errors", "tablet-url",
        "copy-tablet-url", "tablet-url-note", "tablet-qr-figure", "tablet-qr", "tablet-qr-note",
        "tablet-qr-error", "btn-readiness-qr-retry", "readiness-refreshed", "btn-readiness-refresh",
        "operator-readiness-facts", "readiness-paths", "operator-readiness-paths", "readiness-advice",
        "operator-readiness-advice", "readiness-message"];
    const nodes = {};
    ids.forEach(id => { nodes[id] = element(id); });
    const document = {
        getElementById: id => nodes[id] || null,
        createElement: tag => element(tag)
    };
    const calls = [], pending = [];
    const state = {};
    const copied = [];
    let copyResult = true;
    const context = vm.createContext({ window: {}, document: document, URL: URL, Date: Date, JSON: JSON });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-readiness.js"), "utf8"), context);
    const model = context.window.OperatorReadiness;
    const instance = model.create({
        state: state,
        api: (method, path) => {
            calls.push([method, path]);
            return new Promise((resolve, reject) => pending.push({ resolve: resolve, reject: reject }));
        },
        copyText: async text => { copied.push(text); return copyResult; }
    });
    return { model, instance, state, calls, pending, nodes, copied,
        setCopyResult: value => { copyResult = value; } };
}

const full = {
    tablet_url: "http://192.168.50.1:8080/client/",
    join_qr_url: "/api/v3/join-qr",
    wifi: { name: "Wall-Net", known: true },
    security: { transport: "http", authentication: "disabled", uploads: false,
        trust: "Trusted local hotspot. Registration is open." },
    content: { type: "image", available: true,
        summary: "A still image is selected and its bytes are available." },
    wall: { schema: 3, generation: "gen-7", revision: 7, layout: "physical" },
    devices: { online: 1, total: 2 },
    storage: { readable: true, database: "/data/wall.db", assets: "/data/assets",
        media: "/data/media", backup_dir: "/data/backups" },
    backup: { last_manifest_at: "2026-11-01T10:00:00Z", recorded: true, scope: "Referenced content only." },
    restore_rehearsal: { completed_utc: "2026-10-30T09:00:00Z", recorded: true },
    advice: ["The server cannot wake a tablet."],
    errors: []
};

function factsText(nodes) {
    return nodes["operator-readiness-facts"].children.map(node => node.textContent).join(" | ");
}

(async () => {
    /* Pure view contracts: real fields only, unknown stays unknown. */
    const h = harness(); const { view } = h.model;

    const known = view(full, { fetchedAt: Date.parse("2026-11-01T12:00:00Z") });
    assert.equal(known.url.href, "http://192.168.50.1:8080/client/");
    assert.equal(known.url.copyable, true);
    assert.equal(known.qr.state, "ready");
    assert.equal(known.qr.href, "/api/v3/join-qr");
    assert.equal(known.status.kind, "ok");
    assert.match(known.status.text, /does not prove a tablet is displaying the wall/);
    const joined = known.facts.map(pair => pair.join(" = ")).join(" | ");
    for (const expected of ["Wall-Net", "Measured millimetres (physical)", "revision 7",
        "generation gen-7", "schema 3", "HTTP", "None. Trusted local hotspot only.",
        "Disabled; use the configured image folder", "Trusted local hotspot",
        "A still image is selected", "1 online of 2 registered", "Readable",
        "2026-11-01T10:00:00Z — a snapshot was recorded on disk",
        "does not prove this snapshot restores", "2026-10-30T09:00:00Z — recorded",
        "Referenced content only.", "Only current matching paint reports count"]) {
        assert.ok(joined.includes(expected), "missing " + expected);
    }
    assert.equal(known.errors.length, 0);
    assert.deepEqual(known.advice, ["The server cannot wake a tablet."]);
    assert.equal(known.paths.length, 4);
    assert.equal(known.paths[0][1], "/data/wall.db");

    const absent = view(null);
    assert.equal(absent.status.kind, "info");
    assert.equal(absent.url.copyable, false);
    assert.equal(absent.qr.state, "absent");
    assert.ok(absent.facts.every(pair => !/Enabled|Readable|online of/.test(String(pair[1]))),
        "an unread body cannot claim readiness");

    const malformed = view({ status: "Ready", wifi_name: "Old-Net", security_mode: "disabled",
        backup_verified_at: "2026-01-01T00:00:00Z" });
    assert.equal(malformed.status.kind, "warn");
    assert.equal(malformed.url.copyable, false);
    assert.equal(malformed.qr.state, "absent");
    assert.ok(!JSON.stringify(malformed).includes("Old-Net"), "guessed aliases must be ignored");
    assert.ok(!JSON.stringify(malformed).includes("2026-01-01"), "guessed aliases must be ignored");

    const legacyMode = view({ tablet_url: null, join_qr_url: null,
        security: { transport: "http", authentication: "disabled", uploads: "disabled" } });
    assert.ok(legacyMode.facts.map(pair => pair.join(" = ")).join(" | ")
        .includes("Disabled; use the configured image folder"),
        "the documented uploads string mode renders as disabled");
    const loopbackMode = view({ security: { uploads: "loopback" } });
    assert.ok(loopbackMode.facts.map(pair => pair.join(" = ")).join(" | ")
        .includes("Enabled on the loopback path"));

    const unrecorded = view({ backup: { recorded: false }, restore_rehearsal: { recorded: false } });
    const unrecordedText = unrecorded.facts.map(pair => pair.join(" = ")).join(" | ");
    assert.ok(unrecordedText.includes("No backup snapshot is recorded"));
    assert.ok(unrecordedText.includes("No restore rehearsal recorded. A backup is not proven restorable."));
    assert.ok(unrecordedText.includes("Not verified. A manifest is a record on disk, not proof that the wall restores."));

    const badUrl = view({ tablet_url: "javascript:alert(1)", join_qr_url: "/api/v3/join-qr" });
    assert.equal(badUrl.url.copyable, false);
    assert.equal(badUrl.qr.state, "absent");
    assert.match(badUrl.url.note, /not a usable http or https origin/);

    const loopback = view({ tablet_url: "http://127.0.0.1:8000/client/", join_qr_url: "/api/v3/join-qr" });
    assert.match(loopback.url.note, /loopback address/);

    const externalQr = view({ tablet_url: "http://192.168.50.1:8080/client/",
        join_qr_url: "https://evil.example/qr" });
    assert.equal(externalQr.qr.state, "unusable");
    assert.equal(externalQr.qr.href, null);
    assert.match(externalQr.url.note, /not a same-origin path/);

    /* Rendered reading: the real endpoint is fetched, not /operator-config. */
    const page = harness();
    page.instance.render();
    assert.equal(page.nodes["readiness-status"].dataset.kind, "info");
    assert.equal(page.nodes["btn-readiness-refresh"].textContent, "Refresh readiness");

    const loading = page.instance.load();
    assert.deepEqual(page.calls, [["GET", "/api/v3/readiness"]], "readiness must read its own endpoint");
    assert.equal(page.nodes["btn-readiness-refresh"].disabled, true);
    assert.equal(page.nodes["btn-readiness-refresh"].textContent, "Refreshing…");
    assert.equal(await page.instance.load(), false, "an in-flight read is not duplicated");
    assert.equal(page.calls.length, 1);
    page.pending.shift().resolve(JSON.parse(JSON.stringify(full)));
    assert.equal(await loading, true);

    assert.equal(page.nodes["tablet-url"].value, "http://192.168.50.1:8080/client/");
    assert.equal(page.nodes["copy-tablet-url"].disabled, false);
    assert.equal(page.nodes["tablet-qr-figure"].hidden, false);
    assert.equal(page.nodes["tablet-qr"].attrs.src, "/api/v3/join-qr");
    assert.equal(page.nodes["readiness-errors"].hidden, true);
    assert.equal(page.nodes["operator-readiness-advice"].children.length, 1);
    assert.ok(page.nodes["readiness-refreshed"].textContent.startsWith("Last successful read at "));
    assert.ok(factsText(page.nodes).includes("Wall-Net"));
    assert.equal(page.nodes["readiness-status"].dataset.kind, "ok");
    assert.equal(page.state.readiness.wifi.name, "Wall-Net");
    assert.equal(typeof page.state.readinessFetchedAt, "number");

    /* A config snapshot replacing state.readiness must not blank the card. */
    const renderedKey = page.nodes["operator-readiness-facts"].dataset.key;
    page.state.readiness = {};
    page.instance.render();
    assert.ok(factsText(page.nodes).includes("Wall-Net"), "config snapshots cannot erase fetched readiness");
    assert.equal(page.nodes["operator-readiness-facts"].dataset.key, renderedKey);

    /* QR lifecycle: a failed image is reported, retry refetches and restores it. */
    page.nodes["tablet-qr"].listeners.error[0]();
    assert.equal(page.nodes["tablet-qr-error"].hidden, false);
    page.nodes["btn-readiness-qr-retry"].click();
    assert.equal(page.nodes["tablet-qr-error"].hidden, true);
    assert.equal(page.calls.length, 2, "retrying the QR also refreshes readiness");
    page.pending.shift().resolve(JSON.parse(JSON.stringify(full)));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(page.nodes["tablet-qr"].attrs.src, "/api/v3/join-qr");

    /* Explicit retry after a failed read keeps the last good data but says so. */
    const failed = harness();
    const read = failed.instance.load();
    failed.pending.shift().reject(new Error("403 forbidden"));
    assert.equal(await read, false);
    assert.equal(failed.nodes["readiness-status"].dataset.kind, "err");
    assert.match(failed.nodes["readiness-status"].textContent, /403 forbidden/);
    assert.match(failed.nodes["readiness-status"].textContent, /Retry readiness/);
    assert.equal(failed.nodes["btn-readiness-refresh"].textContent, "Retry readiness");
    assert.equal(failed.nodes["btn-readiness-refresh"].disabled, false);
    assert.equal(failed.nodes["tablet-url"].value, "Tablet address not configured");

    const retried = failed.instance.load();
    failed.pending.shift().resolve(JSON.parse(JSON.stringify(full)));
    assert.equal(await retried, true);
    assert.equal(failed.nodes["readiness-status"].dataset.kind, "ok");
    assert.equal(failed.nodes["btn-readiness-refresh"].textContent, "Refresh readiness");

    /* A body with none of the documented fields is an error, not "ready". */
    const wrong = harness();
    const wrongRead = wrong.instance.load();
    wrong.pending.shift().resolve({ status: "Ready", ready: true });
    assert.equal(await wrongRead, false);
    assert.equal(wrong.nodes["readiness-status"].dataset.kind, "err");
    assert.match(wrong.nodes["readiness-status"].textContent, /did not include the expected fields/);
    assert.equal(wrong.state.readiness, undefined);

    /* Server-reported problems are visible text. */
    const issues = harness();
    const issueRead = issues.instance.load();
    issues.pending.shift().resolve({ tablet_url: null, join_qr_url: null, errors: ["TABLET_WALL_TABLET_ORIGIN is not configured"] });
    assert.equal(await issueRead, true);
    assert.equal(issues.nodes["readiness-errors"].hidden, false);
    assert.match(issues.nodes["readiness-errors"].textContent, /TABLET_WALL_TABLET_ORIGIN is not configured/);
    assert.equal(issues.nodes["readiness-status"].dataset.kind, "warn");
    assert.match(issues.nodes["readiness-status"].textContent, /with 1 issue below/);

    /* Copy uses the validated address. */
    failed.nodes["copy-tablet-url"].click();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(failed.copied, ["http://192.168.50.1:8080/client/"]);
    assert.equal(failed.nodes["readiness-message"].textContent, "Tablet address copied.");

    console.log("Operator readiness real-schema, unknown/error, QR, refresh and config-snapshot contracts passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
