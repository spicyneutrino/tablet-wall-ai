"use strict";
(function (root) {
    const modes = { content: "content", show: "arrange" };
    function createState() {
        return Object.freeze({ mode: "content", selectedTablet: null, legacyPanel: null });
    }
    function reduce(state, action) {
        if (action.type === "select-tablet") return Object.freeze({ ...state, selectedTablet: action.id || null });
        if (action.type === "open-panel") return Object.freeze({ ...state,
            mode: modes[action.panel] || state.mode, legacyPanel: action.panel });
        if (action.type === "set-mode") return Object.freeze({ ...state, mode: action.mode, legacyPanel: null });
        return state;
    }
    function select(state, { image = false, arrangement = false } = {}) {
        return Object.freeze({ ...state,
            inspectorSubject: Object.freeze(state.selectedTablet
                ? { kind: "tablet", id: state.selectedTablet } : { kind: "tools", mode: state.mode }),
            draftOwner: image ? "image" : arrangement ? "arrangement" : "none" });
    }
    function legacyState(panel, id) {
        return reduce(reduce(createState(), { type: "open-panel", panel }), { type: "select-tablet", id });
    }
    function stageEditable(composition, { gridPreview, viewLive, previewContent }) {
        return composition.mode === "arrange" && (!composition.legacyPanel || composition.legacyPanel === "show")
            && !gridPreview && !viewLive && !previewContent;
    }
    function selectionNavigation(composition, { reveal = false, stageActivation = false, taskOpened = false } = {}) {
        const arrange = composition.legacyPanel === "show";
        return { expandArrange: arrange, reveal: reveal && !(stageActivation && arrange),
            panel: taskOpened || composition.legacyPanel === "tablet" ? null : "tablet" };
    }
    function createSelectionNavigation({ composition, selectedId, openPanel, revealTablet, expandArrange }) {
        return async function navigateSelection(id, options = {}) {
            const plan = selectionNavigation(composition(), options);
            if (plan.expandArrange) expandArrange();
            if (!id || !plan.reveal) return false;
            const opened = plan.panel ? await openPanel(plan.panel, { persist: true }) : true;
            if (!opened || selectedId() !== id || composition().legacyPanel !== "tablet") return false;
            return revealTablet(id, options.trigger);
        };
    }
    const api = { createState, reduce, select, legacyState, stageEditable, selectionNavigation, createSelectionNavigation };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorComposition = api;
}(typeof window !== "undefined" ? window : globalThis));
