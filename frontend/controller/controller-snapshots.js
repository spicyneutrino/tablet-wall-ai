"use strict";

/* Named layout and scene snapshots, including confirmation and focus state. */
window.ControllerSnapshots = {
    create: function (dependencies) {
        const { snapEl, wallReady, getWall, shortAsset, requestJson, logStatus, adoptWallState, normalizeWall, refreshAssets, renderWall, syncRecalledLayout, renderLayoutShortcuts, compareIds } = dependencies;
    
        const SNAPSHOT_CONFIRM_MS = 8000;
    
        /* The server's name rule, checked here so a bad name never costs a round
         * trip: trimmed, 1–64 characters, an ASCII letter or digit first, then
         * letters, digits, spaces, dot, underscore or hyphen. Case-sensitive —
         * nothing here lowercases, folds or otherwise rewrites what was typed. */
        const SNAPSHOT_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/;
    
        const SNAPSHOTS = {
            layout: {
                base: "/layouts",
                label: "layout",
                title: "Layout",
                saveVerb: "Save layout",
                items: [],
                loaded: false,
                loading: false,
                operation: null,      // "save" | "overwrite" | "recall" | "delete"
                overwrite: null,      // name waiting for the visible second click
                overwriteTimer: null,
                confirm: null,        // { action: "recall" | "delete", name }
                confirmTimer: null
            },
            scene: {
                base: "/scenes",
                label: "scene",
                title: "Scene",
                saveVerb: "Save scene",
                items: [],
                loaded: false,
                loading: false,
                operation: null,
                overwrite: null,
                overwriteTimer: null,
                confirm: null,
                confirmTimer: null
            }
        };
    
        function snapRefs(kind) {
            return snapEl[kind];
        }
    
        function capLabel(snap) {
            return snap.label.charAt(0).toUpperCase() + snap.label.slice(1);
        }
    
        /** Trimmed, in-range, and the exact spelling the operator typed. */
        function validateSnapshotName(raw) {
            const name = String(raw === null || raw === undefined ? "" : raw).trim();
            if (name === "") {
                return { error: "Give the snapshot a name first." };
            }
            if (name.length > 64) {
                return { error: "Names are at most 64 characters. This one is " + name.length + "." };
            }
            if (!SNAPSHOT_NAME_RE.test(name)) {
                return {
                    error: "Names start with a letter or digit and then hold only " +
                        "letters, digits, spaces, dot, underscore or hyphen (1–64 characters)."
                };
            }
            return { name: name };
        }
    
        /** There is nothing to snapshot until the server has told us what is
         *  active — the same gate the wall form uses. */
        function snapSaveAvailable(kind) {
            if (kind === "layout") return wallReady();
            return !!getWall() && !!getWall().content;
        }
    
        /** The panel's own status line: validation, in-flight work, why a read is
         *  stale. The markup gives it `role="status"`, so the text is announced
         *  as well as shown — and it is only ever assigned as text. */
        function setSnapMsg(kind, text, msgKind) {
            const node = snapRefs(kind).msg;
            if (!node) return;
            if (!text) {
                node.hidden = true;
                node.textContent = "";
                return;
            }
            node.hidden = false;
            node.dataset.kind = msgKind || "info";
            node.textContent = text;
        }
    
        /* ------------------------------------------------------------------ *
         * Snapshot list reading + rendering
         * ------------------------------------------------------------------ */
    
        /** One row's second column: what the server listed, and nothing else. */
        function snapshotItemMeta(kind, entry) {
            if (entry.invalid === true) {
                return "INVALID SAVED DATA · delete or replace this snapshot";
            }
            if (kind === "layout") {
                const layout = entry.layout && typeof entry.layout === "object" ? entry.layout : null;
                if (!layout) return "";
                const width = Number(layout.width);
                const height = Number(layout.height);
                const bits = [];
                if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) {
                    bits.push(Math.round(width) + " × " + Math.round(height) + " u");
                }
                const placements = layout.placements && typeof layout.placements === "object"
                    ? Object.keys(layout.placements).length
                    : null;
                if (placements !== null) {
                    bits.push(placements + (placements === 1 ? " placement" : " placements"));
                }
                return bits.join(" · ");
            }
    
            const content = entry.content && typeof entry.content === "object" ? entry.content : null;
            if (!content || typeof content.type !== "string" || content.type === "") {
                return "content not listed";
            }
            // The raw type, never a friendlier one: this page does not claim to
            // render a type it has never heard of.
            const bits = [content.type];
            if (content.type === "image" && typeof content.asset === "string" && content.asset !== "") {
                bits.push(shortAsset(content.asset));
            }
            if (typeof content.fit === "string" && content.fit !== "") bits.push("fit " + content.fit);
            return bits.join(" · ");
        }
    
        /**
         * The payload as a sorted list, or null when it is not a list in any
         * shape this page recognises — the caller reports that instead of
         * showing an empty list that reads as "you have no saved snapshots".
         */
        function normalizeSnapshotList(payload, kind) {
            const snap = SNAPSHOTS[kind];
            let entries = null;
            if (Array.isArray(payload)) {
                entries = payload;
            } else if (payload && typeof payload === "object") {
                for (const key of [snap.base.slice(1), "items", "list"]) {
                    if (Array.isArray(payload[key])) {
                        entries = payload[key];
                        break;
                    }
                }
            }
            if (!entries) return null;
    
            const seen = new Set();
            const out = [];
            for (const raw of entries) {
                if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
                const name = typeof raw.name === "string" ? raw.name : "";
                if (name === "" || seen.has(name)) continue;
                seen.add(name);
                out.push({ name: name, meta: snapshotItemMeta(kind, raw) });
            }
            out.sort(function (a, b) {
                const an = a.name.toLowerCase();
                const bn = b.name.toLowerCase();
                if (an !== bn) return an < bn ? -1 : 1;
                return compareIds(a.name, b.name);
            });
            return out;
        }
    
        function snapshotRow(kind, name) {
            const list = snapRefs(kind).list;
            if (!list) return null;
            for (const row of list.children) {
                if (row.dataset.name === name) return row;
            }
            return null;
        }
    
        /** Back to the row's ordinary action button, so cancelling a confirm
         *  leaves the keyboard operator where they were. */
        function focusSnapshotAction(kind, name, action) {
            const row = snapshotRow(kind, name);
            if (!row) return false;
            const button = row.querySelector(
                '[data-action="' + (action === "delete" ? "snap-delete" : "snap-recall") + '"]'
            );
            if (!button) return false;
            button.focus();
            return true;
        }
    
        function restoreSnapshotFocus(kind, name, action, hadFocus) {
            // Don't steal focus if the operator moved elsewhere while a request
            // was in flight. Rebuilt rows remove the old focused button and send
            // focus to <body>; return it to its equivalent, or to the name field
            // after a successful delete removed the row altogether.
            if (!hadFocus || document.activeElement !== document.body) return;
            if (!focusSnapshotAction(kind, name, action)) {
                const input = snapRefs(kind).name;
                if (input) input.focus();
            }
        }
    
        function buildSnapshotRow(kind, item, busy) {
            const snap = SNAPSHOTS[kind];
            const row = document.createElement("li");
            row.className = "snap-row";
            row.dataset.name = item.name;
    
            const info = document.createElement("span");
            info.className = "snap-info";
            const name = document.createElement("span");
            name.className = "snap-name";
            name.textContent = item.name;
            const meta = document.createElement("span");
            meta.className = "snap-meta mono";
            meta.textContent = item.meta;
            info.append(name, meta);
            row.appendChild(info);
    
            const confirming = !!snap.confirm && snap.confirm.name === item.name;
            if (confirming) {
                const question = document.createElement("span");
                question.className = "snap-q";
                question.textContent = snap.confirm.action === "delete"
                    ? 'Delete "' + item.name + '" for good? The wall itself is not changed.'
                    : "Replace the current layout? Wall size and every tablet position change. " +
                      "What the wall shows stays the same.";
    
                const yes = document.createElement("button");
                yes.type = "button";
                yes.className = "btn btn-danger btn-sm";
                yes.dataset.action = snap.confirm.action === "delete"
                    ? "snap-delete-confirm" : "snap-recall-confirm";
                yes.textContent = snap.confirm.action === "delete" ? "Delete" : "Recall";
                yes.disabled = busy;
    
                const no = document.createElement("button");
                no.type = "button";
                no.className = "btn btn-ghost btn-sm";
                no.dataset.action = "snap-confirm-cancel";
                no.textContent = "Cancel";
                no.disabled = busy;
    
                row.append(question, yes, no);
                return row;
            }
    
            const recall = document.createElement("button");
            recall.type = "button";
            recall.className = "btn btn-sm";
            recall.dataset.action = "snap-recall";
            recall.textContent = "Recall";
            recall.disabled = busy;
            recall.title = kind === "layout"
                ? "Replace the active dimensions and every placement (reservations included). " +
                  "The scene content is preserved."
                : "Apply this content to the layout that is active right now. " +
                  "Dimensions and placements are untouched.";
    
            const del = document.createElement("button");
            del.type = "button";
            del.className = "btn btn-ghost btn-sm";
            del.dataset.action = "snap-delete";
            del.textContent = "Delete";
            del.disabled = busy;
            del.title = 'Remove the saved ' + snap.label + ' "' + item.name +
                '. The active wall keeps everything it has.';
    
            row.append(recall, del);
            return row;
        }
    
        function renderSnapshotList(kind) {
            const snap = SNAPSHOTS[kind];
            const refs = snapRefs(kind);
            // A list that is mid-read is about to be rebuilt, so nothing on it is
            // actionable — including a confirm that would fire into the read.
            const busy = snap.operation !== null || snap.loading;
    
            // A confirmation for a name that has left the list (deleted elsewhere,
            // listed by an older read) is dropped rather than rebuilt on a row
            // that is no longer there.
            if (snap.confirm && !snap.items.some(function (item) { return item.name === snap.confirm.name; })) {
                endSnapshotConfirm(kind);
            }
    
            if (refs.list) {
                refs.list.textContent = "";
                for (const item of snap.items) {
                    refs.list.appendChild(buildSnapshotRow(kind, item, busy));
                }
                refs.list.hidden = snap.items.length === 0;
            }
    
            if (refs.empty) {
                let text = "";
                if (snap.loading) {
                    text = "Reading the saved " + snap.label + "s…";
                } else if (!snap.loaded) {
                    text = "Saved " + snap.label + "s not read yet. Press Refresh.";
                } else if (snap.items.length === 0) {
                    text = "Nothing saved yet. Name the " +
                        (kind === "layout" ? "current arrangement" : "current content") +
                        " above and press " + snap.saveVerb + ".";
                }
                refs.empty.hidden = text === "";
                refs.empty.textContent = text;
            }
        }
    
        function updateSnapshotSaveButton(kind) {
            const snap = SNAPSHOTS[kind];
            const button = snapRefs(kind).save;
            if (!button) return;
            const available = snapSaveAvailable(kind);
            button.disabled = snap.operation !== null || snap.loading || !available;
            button.textContent = snap.operation === "save" ? "Saving…" : snap.saveVerb;
            button.title = available
                ? "Snapshot the server's current " + snap.label + " under the name you type"
                : kind === "layout"
                    ? "No wall state from the server yet. There is nothing to save."
                    : "No scene content from the server yet. There is nothing to save.";
        }
    
        /** Called from `renderWall` on every wall change: it only refreshes the
         *  two save buttons, so a broadcast never steals focus from a list row. */
        function renderSnapshotAvailability() {
            updateSnapshotSaveButton("layout");
            updateSnapshotSaveButton("scene");
        }
    
        function renderSnapshotPanel(kind) {
            const snap = SNAPSHOTS[kind];
            const refs = snapRefs(kind);
            const busy = snap.operation !== null;
    
            if (refs.name) refs.name.disabled = busy || snap.loading;
            updateSnapshotSaveButton(kind);
    
            if (refs.refresh) {
                refs.refresh.disabled = busy || snap.loading;
                refs.refresh.textContent = snap.loading ? "Reading…" : "Refresh";
            }
    
            if (refs.overwrite) {
                refs.overwrite.hidden = !snap.overwrite;
                if (snap.overwrite && refs.overwriteText) {
                    refs.overwriteText.textContent =
                        'A ' + snap.label + ' named "' + snap.overwrite + '" already exists. ' +
                        "replace it? Nothing has been overwritten yet.";
                }
                if (refs.overwriteYes) refs.overwriteYes.disabled = busy;
                if (refs.overwriteNo) refs.overwriteNo.disabled = busy;
            }
    
            renderSnapshotList(kind);
            if (kind === "layout") renderLayoutShortcuts();
        }
    
        /* ------------------------------------------------------------------ *
         * Snapshot commands
         * ------------------------------------------------------------------ */
    
        /** GET the list. A failure keeps the last good rows and says why they
         *  are stale — the same rule the asset inventory follows. */
        async function refreshSnapshots(kind, quiet) {
            const snap = SNAPSHOTS[kind];
            if (snap.loading || snap.operation !== null) return false;
            snap.loading = true;
            renderSnapshotPanel(kind);
    
            let succeeded = false;
            try {
                const data = await requestJson("GET", snap.base);
                const items = normalizeSnapshotList(data, kind);
                if (items === null) {
                    throw new Error("the answer was not a " + snap.label + " list");
                }
                snap.items = items;
                snap.loaded = true;
                succeeded = true;
                setSnapMsg(kind, null);
                if (!quiet) {
                    logStatus(
                        capLabel(snap) + ": " + items.length + " saved " +
                            (items.length === 1 ? snap.label : snap.label + "s") + ".",
                        "ok"
                    );
                }
            } catch (err) {
                setSnapMsg(
                    kind,
                    "Could not read the saved " + snap.label + "s: " + err.message +
                        (snap.loaded ? ". Showing the list read earlier." : ""),
                    "err"
                );
                if (!quiet) logStatus("Saved " + snap.label + "s unavailable: " + err.message, "err");
            } finally {
                snap.loading = false;
                renderSnapshotPanel(kind);
            }
            return succeeded;
        }
    
        /** PUT /{base}/{name} — the server snapshots its own active wall. */
        async function saveSnapshot(kind) {
            const snap = SNAPSHOTS[kind];
            const refs = snapRefs(kind);
            if (snap.operation !== null || snap.loading) return;
    
            const check = validateSnapshotName(refs.name ? refs.name.value : "");
            if (check.error) {
                setSnapMsg(kind, check.error, "err");
                if (refs.name) refs.name.focus();
                return;
            }
            const name = check.name;
    
            snap.operation = "save";
            setSnapMsg(kind, 'Saving ' + snap.label + ' "' + name + '"…', "busy");
            renderSnapshotPanel(kind);
    
            let saved = false;
            let conflict = false;
            try {
                await requestJson("PUT", snap.base + "/" + encodeURIComponent(name));
                saved = true;
            } catch (err) {
                if (err.status === 409) {
                    conflict = true;
                } else if (err.status === 422) {
                    setSnapMsg(kind, 'The server will not take the name "' + name + '": ' + err.message, "err");
                } else {
                    setSnapMsg(kind, "Not saved: " + err.message, "err");
                }
            } finally {
                snap.operation = null;
            }
    
            if (saved) {
                endSnapshotOverwrite(kind); // this name exists now, nothing pending
                if (refs.name) refs.name.value = "";
                setSnapMsg(kind, null);
                logStatus(snap.title + ' "' + name + '" saved.', "ok");
                renderSnapshotPanel(kind);
                await refreshSnapshots(kind, true); // success refreshes the list
                return;
            }
    
            renderSnapshotPanel(kind);
            if (conflict) beginSnapshotOverwrite(kind, name);
        }
    
        /**
         * The server answered 409. Nothing is retried automatically: the operator
         * gets a visible block with its own buttons and focus lands on "Replace
         * it", so the overwrite is a second, deliberate act — and it expires.
         */
        function beginSnapshotOverwrite(kind, name) {
            const snap = SNAPSHOTS[kind];
            endSnapshotOverwrite(kind);
            snap.overwrite = name;
            setSnapMsg(
                kind,
                'A ' + snap.label + ' named "' + name + '" already exists, so nothing was ' +
                    "saved. Press Replace it to overwrite it, or Cancel to keep it and " +
                    "choose another name.",
                "warn"
            );
            renderSnapshotPanel(kind);
    
            const yes = snapRefs(kind).overwriteYes;
            if (yes) yes.focus();
            snap.overwriteTimer = setTimeout(function () {
                snap.overwriteTimer = null;
                if (snap.overwrite !== name) return;
                const hadFocus = snapRefs(kind).overwrite.contains(document.activeElement);
                snap.overwrite = null;
                setSnapMsg(kind, 'Not replaced. "' + name + '" is still the saved one. ' +
                    "Press Save again and confirm to overwrite it.", "info");
                renderSnapshotPanel(kind);
                if (hadFocus && document.activeElement === document.body) {
                    const input = snapRefs(kind).name;
                    if (input) input.focus();
                }
            }, SNAPSHOT_CONFIRM_MS);
        }
    
        function endSnapshotOverwrite(kind) {
            const snap = SNAPSHOTS[kind];
            if (snap.overwriteTimer) clearTimeout(snap.overwriteTimer);
            snap.overwriteTimer = null;
            snap.overwrite = null;
        }
    
        function cancelSnapshotOverwrite(kind) {
            const snap = SNAPSHOTS[kind];
            if (!snap.overwrite) return;
            const name = snap.overwrite;
            endSnapshotOverwrite(kind);
            setSnapMsg(kind, 'Kept the existing "' + name + '". Nothing was overwritten.', "info");
            renderSnapshotPanel(kind);
            const input = snapRefs(kind).name;
            if (input) input.focus();
        }
    
        /** The visible second click: PUT ?replace=true, never sent otherwise. */
        async function replaceSnapshot(kind) {
            const snap = SNAPSHOTS[kind];
            const name = snap.overwrite;
            if (!name || snap.operation !== null || snap.loading) return;
            const hadFocus = snapRefs(kind).overwrite.contains(document.activeElement);
            endSnapshotOverwrite(kind);
    
            snap.operation = "overwrite";
            setSnapMsg(kind, 'Replacing "' + name + '"…', "busy");
            renderSnapshotPanel(kind);
    
            let ok = false;
            try {
                await requestJson(
                    "PUT",
                    snap.base + "/" + encodeURIComponent(name) + "?replace=true"
                );
                ok = true;
            } catch (err) {
                setSnapMsg(kind, "Not replaced: " + err.message, "err");
            } finally {
                snap.operation = null;
            }
    
            if (ok) {
                const refs = snapRefs(kind);
                if (refs.name) refs.name.value = "";
                setSnapMsg(kind, null);
                logStatus(snap.title + ' "' + name + '" replaced.', "ok");
                await refreshSnapshots(kind, true);
            }
            renderSnapshotPanel(kind);
            if (hadFocus && document.activeElement === document.body) {
                const input = snapRefs(kind).name;
                if (input) input.focus();
            }
        }
    
        function endSnapshotConfirm(kind) {
            const snap = SNAPSHOTS[kind];
            if (snap.confirmTimer) clearTimeout(snap.confirmTimer);
            snap.confirmTimer = null;
            snap.confirm = null;
        }
    
        /**
         * Recall is two different risks, so it is two different interactions.
         *
         * A layout recall replaces the active dimensions and every placement —
         * reservations included — so it asks first and spells out what goes. A
         * scene recall only sets content on the layout that is active now: there
         * is nothing to throw away, so it is one click (and the server is what
         * guarantees the arrangement is untouched).
         */
        function beginSnapshotRecall(kind, name) {
            const snap = SNAPSHOTS[kind];
            if (snap.operation !== null || snap.loading) return;
            if (kind === "scene") {
                recallSnapshot(kind, name);
                return;
            }
            if (snap.confirm && (snap.confirm.action !== "recall" || snap.confirm.name !== name)) {
                endSnapshotConfirm(kind);
            }
            snap.confirm = { action: "recall", name: name };
            renderSnapshotPanel(kind);
            if (snap.confirmTimer) clearTimeout(snap.confirmTimer);
            snap.confirmTimer = setTimeout(function () {
                cancelSnapshotConfirm(kind);
            }, SNAPSHOT_CONFIRM_MS);
    
            const row = snapshotRow(kind, name);
            const yes = row && row.querySelector('[data-action="snap-recall-confirm"]');
            if (yes) yes.focus();
        }
    
        function beginSnapshotDelete(kind, name) {
            const snap = SNAPSHOTS[kind];
            if (snap.operation !== null || snap.loading) return;
            if (snap.confirm && (snap.confirm.action !== "delete" || snap.confirm.name !== name)) {
                endSnapshotConfirm(kind);
            }
            snap.confirm = { action: "delete", name: name };
            renderSnapshotPanel(kind);
            if (snap.confirmTimer) clearTimeout(snap.confirmTimer);
            snap.confirmTimer = setTimeout(function () {
                cancelSnapshotConfirm(kind);
            }, SNAPSHOT_CONFIRM_MS);
    
            const row = snapshotRow(kind, name);
            const yes = row && row.querySelector('[data-action="snap-delete-confirm"]');
            if (yes) yes.focus();
        }
    
        function cancelSnapshotConfirm(kind) {
            const snap = SNAPSHOTS[kind];
            if (!snap.confirm) return;
            const { name, action } = snap.confirm;
            const row = snapshotRow(kind, name);
            const hadFocus = !!row && row.contains(document.activeElement);
            endSnapshotConfirm(kind);
            renderSnapshotPanel(kind);
            restoreSnapshotFocus(kind, name, action, hadFocus);
        }
    
        /** POST /{base}/{name}/recall — adopt the wall the server sends back. */
        async function recallSnapshot(kind, name) {
            const snap = SNAPSHOTS[kind];
            if (snap.operation !== null || snap.loading) return;
            const row = snapshotRow(kind, name);
            const hadFocus = !!row && row.contains(document.activeElement);
            endSnapshotConfirm(kind); // the confirm step (layout) is done
    
            snap.operation = "recall";
            setSnapMsg(kind, 'Recalling "' + name + '"…', "busy");
            renderSnapshotPanel(kind);
    
            let failure = null;
            let took = false;
            try {
                const data = await requestJson(
                    "POST",
                    snap.base + "/" + encodeURIComponent(name) + "/recall"
                );
                took = adoptWallState(normalizeWall(data));
            } catch (err) {
                failure = err;
            } finally {
                snap.operation = null;
            }
    
            if (failure) {
                if (failure.status === 404) {
                    // Someone else removed it while our list still showed it.
                    // Re-read first: a successful refresh clears this panel's
                    // message line, so the explanation lands after it.
                    const refreshed = await refreshSnapshots(kind, true);
                    if (refreshed) {
                        setSnapMsg(
                            kind,
                            'The ' + snap.label + ' "' + name + '" is no longer saved. ' +
                                "someone else removed it. The list was refreshed.",
                            "err"
                        );
                    }
                    renderSnapshotPanel(kind);
                    restoreSnapshotFocus(kind, name, "recall", hadFocus);
                    logStatus(
                        snap.title + ' "' + name + '" is no longer saved' +
                            (refreshed ? ". The list was refreshed." : "; list refresh failed."),
                        "err"
                    );
                    return;
                }
                setSnapMsg(
                    kind,
                    (kind === "layout" ? "Layout not recalled: " : "Scene not recalled: ") +
                        failure.message,
                    "err"
                );
                renderSnapshotPanel(kind);
                restoreSnapshotFocus(kind, name, "recall", hadFocus);
                logStatus(snap.title + ' "' + name + '" not recalled: ' + failure.message, "err");
                return;
            }
    
            if (kind === "layout" && took) {
                // The operator asked for the arrangement to be replaced, so any
                // unsaved dimension edits are exactly what just got overwritten.
                syncRecalledLayout();
            }
    
            setSnapMsg(kind, null);
            renderSnapshotPanel(kind);
    
            if (kind === "scene") {
                // The recalled content can name an asset that is no longer in the
                // inventory — that must not block the recall, but it must be seen:
                // re-read the inventory so the missing-asset warning below can tell
                // the truth about what the wall is now showing.
                await refreshAssets(true);
            }
    
            renderWall();
            restoreSnapshotFocus(kind, name, "recall", hadFocus);
            logStatus(
                took
                    ? snap.title + ' "' + name + '" recalled. Revision ' +
                          (getWall() ? getWall().revision : "-") + "."
                    : snap.title + ' "' + name + '" recalled. Waiting for the wall update.',
                took ? "ok" : "info"
            );
        }
    
        /**
         * DELETE /{base}/{name} — the snapshot only. The active wall is not part
         * of this request, so a successful delete never changes what is shown.
         */
        async function deleteSnapshot(kind, name) {
            const snap = SNAPSHOTS[kind];
            if (snap.operation !== null || snap.loading) return;
            const row = snapshotRow(kind, name);
            const hadFocus = !!row && row.contains(document.activeElement);
            endSnapshotConfirm(kind); // the confirm step is done
    
            snap.operation = "delete";
            setSnapMsg(kind, 'Deleting "' + name + '"…', "busy");
            renderSnapshotPanel(kind);
    
            let gone = false;
            let failure = null;
            try {
                await requestJson("DELETE", snap.base + "/" + encodeURIComponent(name));
            } catch (err) {
                if (err.status === 404) gone = true;
                else failure = err;
            } finally {
                snap.operation = null;
            }
    
            if (failure) {
                setSnapMsg(kind, "Not deleted: " + failure.message, "err");
                renderSnapshotPanel(kind);
                restoreSnapshotFocus(kind, name, "delete", hadFocus);
                logStatus(snap.title + ' "' + name + '" not deleted: ' + failure.message, "err");
                return;
            }
    
            // The server confirmed this row is gone (or was already absent).
            // Remove it locally before the follow-up read: a failed refresh must
            // not leave a clickable row that claims it still exists.
            snap.items = snap.items.filter(function (item) { return item.name !== name; });
            renderSnapshotPanel(kind);
            logStatus(
                snap.title + ' "' + name + '" deleted' +
                    (gone ? " (it was already gone)" : "") + ". The wall is unchanged.",
                gone ? "info" : "ok"
            );
            // Re-read before reporting: a successful refresh clears this panel's
            // message line, so "already gone" has to be written after it.
            const refreshed = await refreshSnapshots(kind, true);
            if (refreshed) {
                setSnapMsg(kind, gone ? 'The ' + snap.label + ' "' + name + '" was already gone.' : null, "info");
            }
            renderSnapshotPanel(kind);
            restoreSnapshotFocus(kind, name, "delete", hadFocus);
        }
    
        /* ------------------------------------------------------------------ *
         * Forget — two-step confirmation
         * ------------------------------------------------------------------ */
    
        return { SNAPSHOTS, snapRefs, capLabel, validateSnapshotName, snapSaveAvailable, setSnapMsg, snapshotItemMeta, normalizeSnapshotList, snapshotRow, focusSnapshotAction, restoreSnapshotFocus, buildSnapshotRow, renderSnapshotList, updateSnapshotSaveButton, renderSnapshotAvailability, renderSnapshotPanel, refreshSnapshots, saveSnapshot, beginSnapshotOverwrite, endSnapshotOverwrite, cancelSnapshotOverwrite, replaceSnapshot, endSnapshotConfirm, beginSnapshotRecall, beginSnapshotDelete, cancelSnapshotConfirm, recallSnapshot, deleteSnapshot };
    }
};
