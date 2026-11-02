"use strict";
(function (root) {
    const model = typeof module !== "undefined" && module.exports ? require("./operator-state.js") : root.OperatorState;
    function freeze(value) {
        if (value && typeof value === "object" && !Object.isFrozen(value)) {
            Object.freeze(value);
            Object.values(value).forEach(freeze);
        }
        return value;
    }
    class ApiError extends Error {
        constructor(status, detail, uncertain = status === 0) { super(detail); this.status = status; this.uncertain = uncertain; }
    }
    function create({ transport = (...args) => fetch(...args), clock = () => performance.now(), syncFactory = root.OperatorSync,
        onConflict = () => {}, isDirty = () => false } = {}) {
        const listeners = new Set();
        const state = { operatorConfig: null, roster: {}, etag: null, etagState: "missing", busy: false,
            rosterError: null, rosterCheckedAt: null, transportText: "Connecting to the wall…", connectionVersions: {}, readFence: model.readFence() };
        let snapshot = null, uncertain = false, adoptionVersion = 0, supported = false;
        function publish(options = {}) {
            snapshot = freeze({ config: state.operatorConfig ? model.clone(state.operatorConfig) : null,
                etag: state.etag, etagState: state.etagState, connectionVersions: { ...state.connectionVersions }, roster: model.clone(state.roster),
                rosterError: state.rosterError, rosterCheckedAt: state.rosterCheckedAt, transportText: state.transportText, uncertain, supported, busy: state.busy });
            listeners.forEach(listener => listener(snapshot, options));
        }
        function ingest(config, options = {}) {
            if (!config || !config.layout || !["logical", "physical", undefined].includes(config.layout.kind)
                    || config.operator_state_version !== undefined && config.operator_state_version !== 1) {
                supported = false; state.etagState = "stale"; publish(); throw new Error("Unsupported wall configuration. Update the console before editing.");
            }
            supported = true;
            state.readFence.event();
            adoptionVersion += 1;
            state.operatorConfig = model.observeConfig(config, clock());
            state.roster = state.operatorConfig.runtime && state.operatorConfig.runtime.devices || state.roster;
            state.operatorConfig = { ...state.operatorConfig, runtime: { ...state.operatorConfig.runtime, devices: state.roster } };
            state.etag = config.etag || null;
            state.etagState = state.etag ? "current" : "missing";
            state.rosterCheckedAt = new Date().toISOString(); state.rosterError = null;
            publish(options);
        }
        async function request(method, path, body, options = {}) {
            const durable = method !== "GET" && !path.endsWith("/preview") && path !== "/api/v3/calibration-check";
            if (durable && !supported) throw new ApiError(409, "Wall configuration is unavailable or unsupported. Refresh status before issuing commands.");
            if (durable && state.busy) throw new ApiError(409, "Another command is in progress. Wait for its result.");
            if (durable && uncertain) throw new ApiError(409, "A command may have completed. Refresh status and review the wall before retrying.");
            const expected = options.ifMatch || (options.etag ? state.etag : null);
            if (options.etag && (!expected || state.etagState !== "current")) throw new ApiError(412, "Refresh the wall before saving. Your local work is retained.");
            const atSend = state.operatorConfig, ticket = state.readFence.start();
            const headers = { Accept: "application/json" };
            if (expected) headers["If-Match"] = expected;
            if (body !== undefined) headers["Content-Type"] = "application/json";
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 10000);
            if (durable) { state.busy = true; publish({ runtime: true }); }
            try {
                let response;
                try { response = await transport(path, { method, headers, signal: controller.signal,
                    ...(body === undefined ? {} : { body: JSON.stringify(body) }) }); }
                catch (error) {
                    if (durable) uncertain = true;
                    throw new ApiError(0, (error.name === "AbortError" ? "Request timed out." : "Connection lost.")
                        + (durable ? " Completion is uncertain. Refresh status and inspect the result before retrying." : " Refresh status to reconnect."));
                }
                let payload;
                try { payload = await response.json(); } catch (_) { payload = null; }
                if (!response.ok) {
                    const detail = payload && payload.detail;
                    const text = typeof detail === "string" ? detail : detail && detail.message || JSON.stringify(detail || "HTTP " + response.status);
                    const friendly = text.replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, id => {
                        const device = state.roster[id] || {};
                        return state.operatorConfig?.device_labels?.[id] || device.label || (device.number ? "Tablet " + device.number : "Unregistered tablet");
                    });
                    if (durable && response.status >= 500) {
                        uncertain = true;
                        throw new ApiError(response.status, friendly + ". Completion is uncertain. Refresh status and inspect the result before retrying.", true);
                    }
                    throw new ApiError(response.status, friendly);
                }
                if (durable) {
                    if (!payload) { uncertain = true; throw new ApiError(0, "The command may have completed, but its response was unreadable. Refresh status and review before retrying."); }
                    state.readFence.event();
                    const current = state.operatorConfig;
                    if (payload && payload.layout && current && current !== atSend && (current.etag === payload.etag || current.etag !== expected)) {
                        sync.reconcile(true);
                        return { ...payload, ...current, commandEtag: payload.etag };
                    }
                } else if (options.fenced === "durable") {
                    if (atSend?.etag !== state.operatorConfig?.etag || state.etagState === "stale") throw new ApiError(409, "Saved wall data changed during this read. Refresh this task.");
                } else if (options.fenced && !state.readFence.current(ticket)) throw new ApiError(409, "A newer update arrived. Refresh this task.");
                return payload;
            } finally {
                clearTimeout(timer);
                if (durable) { state.busy = false; publish({ runtime: true }); }
            }
        }
        const sync = syncFactory.create({ state, api: request, ingestConfig: ingest,
            renderAll: () => publish({ runtime: true }), showConflict: onConflict, isDirty,
            onStatus: text => { state.transportText = text; publish({ runtime: true }); } });
        publish();
        return {
            view: () => snapshot,
            subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
            ingest,
            request,
            async refresh() {
                const version = adoptionVersion;
                let timer, listener;
                const received = new Promise((resolve, reject) => {
                    listener = view => {
                        if (view.rosterError) reject(new ApiError(0, "Status could not be reconciled. " + view.rosterError));
                        else if (adoptionVersion > version) resolve();
                    };
                    listeners.add(listener);
                    timer = setTimeout(() => reject(new ApiError(0, "Waiting for a current wall snapshot timed out. Retry Refresh status.")), 10000);
                });
                try {
                    await Promise.all([sync.reconcile(true), received]);
                    uncertain = false; publish({ runtime: true });
                } finally { clearTimeout(timer); listeners.delete(listener); }
            },
            start: () => sync.start(),
            destroy() { sync.destroy(); listeners.clear(); }
        };
    }
    const api = { create, ApiError };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorSession = api;
}(typeof window !== "undefined" ? window : globalThis));
