"use strict";
(function (root) {
    const stage = typeof module !== "undefined" && module.exports ? require("./operator-stage.js") : root.OperatorStage;
    function measureLegacyHost(svg, { field, ...elements }) {
        const doc = svg.ownerDocument, win = doc.defaultView;
        const parentStyle = win.getComputedStyle(field.parentElement), fieldStyle = win.getComputedStyle(field);
        const availableWidth = field.parentElement.clientWidth - parseFloat(parentStyle.paddingLeft) - parseFloat(parentStyle.paddingRight);
        if (availableWidth <= 0 || !field.getClientRects().length) return null;
        const compact = win.matchMedia("(max-width: 48rem), (max-height: 32rem) and (orientation: landscape)").matches;
        const fieldRect = field.getBoundingClientRect();
        const zoom = fieldRect.width / parseFloat(fieldStyle.width) || 1;
        const fieldTop = (fieldRect.top + win.scrollY + (elements.workspace?.scrollTop || 0)) / zoom;
        let bottom = win.innerHeight / zoom;
        const navigation = elements.navigation;
        const actionBar = doc.body.dataset.task !== "arrange" && elements.actionBar;
        for (const bar of [navigation, doc.body.dataset.outputDirty === "true" && actionBar]) {
            if (!bar || !bar.getClientRects().length) continue;
            const rect = bar.getBoundingClientRect();
            if (bar === actionBar) {
                const inline = compact && bottom - fieldTop - rect.height / zoom - 16 < 120 / zoom;
                doc.body.dataset.imageActionsInline = String(inline);
                if (inline) continue;
            }
            const style = win.getComputedStyle(bar);
            if ((bar === navigation || style.position === "fixed") && rect.bottom / zoom > bottom / 2) bottom = Math.min(bottom, rect.top / zoom - (parseFloat(style.marginTop) || 0));
        }
        const taskSelector = elements.taskSelector;
        const reflow = taskSelector && taskSelector.getClientRects().length;
        const commitShelf = doc.body.dataset.task === "images" && !compact && !reflow && elements.commitShelf;
        if (commitShelf && commitShelf.getClientRects().length) {
            const summary = elements.summary;
            bottom -= (commitShelf.getBoundingClientRect().height + (summary?.getBoundingClientRect().height || 0) + 40) / zoom;
        }
        const borderWidth = parseFloat(fieldStyle.borderLeftWidth) + parseFloat(fieldStyle.borderRightWidth);
        const borderHeight = parseFloat(fieldStyle.borderTopWidth) + parseFloat(fieldStyle.borderBottomWidth);
        const aspect = svg.viewBox.baseVal.width / svg.viewBox.baseVal.height;
        const width = Math.max(0, availableWidth - borderWidth);
        const availableHeight = bottom - fieldTop - 16 - borderHeight;
        // A short viewport keeps a usable field and falls back to page scrolling.
        const topInset = navigation && win.getComputedStyle(navigation).position === "sticky" ? navigation.getBoundingClientRect().height / zoom : 0;
        const imagePortrait = compact && doc.body.dataset.task === "images" && win.matchMedia("(orientation: portrait)").matches;
        const height = imagePortrait ? width / aspect : reflow ? Math.min(width / aspect, Math.max(120 / zoom, bottom - topInset - 16))
            : Math.min(width / aspect, Math.max(120 / zoom, availableHeight));
        return { width, height, borderWidth, borderHeight, availableWidth, availableHeight,
            scrollHeight: Math.max(120 / zoom, availableHeight) };
    }
    function create({ svg, field, measure, onResize = () => {} }) {
        const win = svg.ownerDocument.defaultView;
        let parent = null, frame = 0;
        const schedule = () => {
            onResize();
            if (!frame) frame = win.requestAnimationFrame(() => { frame = 0; fit(); });
        };
        const observer = new win.ResizeObserver(schedule);
        win.addEventListener("resize", schedule);
        function fit() {
            if (svg.classList.contains("is-dragging")) return null;
            if (parent !== field.parentElement) {
                observer.disconnect(); parent = field.parentElement;
                observer.observe(parent);
            }
            if (!svg.viewBox.baseVal.width) return null;
            const available = measure();
            return available ? stage.fit(svg, available, { field }) : null;
        }
        function destroy() {
            observer.disconnect();
            win.removeEventListener("resize", schedule);
            if (frame) win.cancelAnimationFrame(frame);
        }
        return { fit, resize: schedule, destroy };
    }
    const api = { measureLegacyHost, create };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorStageViewport = api;
}(typeof window !== "undefined" ? window : globalThis));
