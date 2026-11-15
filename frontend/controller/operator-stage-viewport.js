"use strict";
(function (root) {
    const stage = typeof module !== "undefined" && module.exports ? require("./operator-stage.js") : root.OperatorStage;
    function measureWell(svg, { field, well, tally }) {
        const win = svg.ownerDocument.defaultView;
        if (!well.getClientRects().length) return null;
        const wellStyle = win.getComputedStyle(well), fieldStyle = win.getComputedStyle(field);
        const gap = parseFloat(win.getComputedStyle(field.parentElement).rowGap) || 0;
        const contentWidth = well.clientWidth - parseFloat(wellStyle.paddingLeft) - parseFloat(wellStyle.paddingRight);
        const contentHeight = well.clientHeight - parseFloat(wellStyle.paddingTop) - parseFloat(wellStyle.paddingBottom)
            - (tally ? tally.getBoundingClientRect().height + gap : 0);
        const borderWidth = parseFloat(fieldStyle.borderLeftWidth) + parseFloat(fieldStyle.borderRightWidth);
        const borderHeight = parseFloat(fieldStyle.borderTopWidth) + parseFloat(fieldStyle.borderBottomWidth);
        const availableWidth = Math.max(0, contentWidth), availableHeight = Math.max(0, contentHeight - borderHeight);
        if (availableWidth <= 0) return null;
        const width = Math.max(0, availableWidth - borderWidth);
        return { width, height: availableHeight, borderWidth, borderHeight, availableWidth, availableHeight, scrollHeight: availableHeight };
    }
    function create({ svg, field, observe = field.parentElement, measure, onResize = () => {} }) {
        const win = svg.ownerDocument.defaultView;
        let frame = 0;
        const schedule = () => {
            onResize();
            if (!frame) frame = win.requestAnimationFrame(() => { frame = 0; fit(); });
        };
        const observer = new win.ResizeObserver(schedule);
        observer.observe(observe);
        win.addEventListener("resize", schedule);
        function fit() {
            if (svg.classList.contains("is-dragging")) return null;
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
    const api = { measureWell, create };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorStageViewport = api;
}(typeof window !== "undefined" ? window : globalThis));
