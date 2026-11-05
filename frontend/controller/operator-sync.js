"use strict";
window.OperatorSync = {
    create({ api, ingestConfig, state, renderAll, showConflict, isDirty, onStatus = () => {} }) {
        const fence = state.readFence;
        let socket = null, reconnectTimer = null, reconcileTimer = null, stopped = false, fetching = false, queued = false;
        const status = onStatus;
        function receive(config) {
            ingestConfig(config, { preserveDraft: true, remote: true });
        }
        async function reconcile(force = false) {
            if (stopped) return;
            if (fetching) { queued = true; return; }
            if (state.busy && !force) { queued = true; return; }
            fetching = true; queued = false;
            const ticket = fence.start();
            try {
                const config = await api("GET", "/api/v3/config");
                if (!fence.accept(ticket)) return;
                if (!config.runtime || !config.runtime.devices) {
                    const roster = await api("GET", "/devices");
                    if (!fence.accept(ticket)) return;
                    state.roster = roster;
                }
                receive(config); state.rosterError = null;
                state.rosterCheckedAt = new Date().toISOString();
                status(socket && socket.readyState === WebSocket.OPEN ? "Live operator updates connected. Slow reconciliation is active." : "Socket unavailable. Showing reconciled status; live updates may be delayed.");
            } catch (error) {
                state.rosterError = error.message;
                status("Status stale. " + error.message + " Retry Refresh."); renderAll();
            } finally { fetching = false; if (queued && !stopped && !state.busy) { queued = false; reconcile(); } }
        }
        function connect() {
            if (stopped) return;
            const url = new URL("/ws/controller?protocol=3", window.location.href);
            url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
            socket = new WebSocket(url.href);
            socket.onopen = () => status("Connected. Waiting for authoritative snapshot…");
            socket.onmessage = event => {
                let frame;
                try { frame = JSON.parse(event.data); } catch (_) { status("Invalid operator update. Refresh status to reconcile."); return; }
                fence.event();
                if (frame.type === "snapshot" && frame.config) {
                    if (!frame.config.runtime && Array.isArray(frame.devices)) state.roster = Object.fromEntries(frame.devices.map(device => [device.id || device.device_id, device]));
                    receive(frame.config); state.rosterCheckedAt = new Date().toISOString(); state.rosterError = null;
                    status("Live operator updates connected. Last snapshot " + new Date().toLocaleTimeString() + ".");
                } else if (frame.type === "config_updated") {
                    if (!state.busy && frame.etag !== state.etag) { state.etagState = "stale"; renderAll(); }
                    if (isDirty() && frame.etag && frame.etag !== state.etag) showConflict("The server changed while this draft was being edited. Keep the draft and reload when ready.");
                    reconcile();
                } else if (["device_online", "device_offline", "device_removed", "device_updated", "device_status"].includes(frame.type)) {
                    if (fetching) queued = true;
                    const device = frame.device, id = frame.device_id || frame.id || device && (device.id || device.device_id);
                    if (id) {
                        if (["device_online", "device_offline", "device_removed"].includes(frame.type)) {
                            state.connectionVersions ||= {};
                            state.connectionVersions[id] = (state.connectionVersions[id] || 0) + 1;
                        }
                        if (frame.type === "device_removed") delete state.roster[id];
                        else if (device) state.roster[id] = Object.assign({}, state.roster[id], device, frame.status || {});
                        else if (frame.status) state.roster[id] = Object.assign({}, state.roster[id], frame.status);
                        else if (frame.type === "device_offline" && state.roster[id]) state.roster[id] = Object.assign({}, state.roster[id], { online: false });
                        if ((device && device.render || frame.status && frame.status.render) && state.roster[id]) {
                            state.roster[id] = window.OperatorState.observeDevice(state.roster[id], performance.now());
                        }
                        state.rosterCheckedAt = new Date().toISOString(); state.rosterError = null;
                        if (state.operatorConfig) state.operatorConfig = Object.assign({}, state.operatorConfig, { runtime: Object.assign({}, state.operatorConfig.runtime, { devices: state.roster }) });
                        renderAll();
                    }
                }
            };
            socket.onclose = () => {
                if (stopped) return;
                state.rosterError = "Operator socket disconnected"; status("Live updates disconnected. Reconnecting; status may be stale."); renderAll();
                reconcile(); reconnectTimer = setTimeout(connect, 3000);
            };
            socket.onerror = () => status("Operator socket failed. Slow reconciliation remains available.");
        }
        function start() {
            connect(); reconcile();
            reconcileTimer = setInterval(() => { if (document.visibilityState !== "hidden") reconcile(); }, 15000);
        }
        function destroy() { stopped = true; clearTimeout(reconnectTimer); clearInterval(reconcileTimer); if (socket) socket.close(); }
        return { start, reconcile, destroy, invalidate: () => fence.event() };
    }
};
