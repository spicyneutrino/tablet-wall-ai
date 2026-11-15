"use strict";
(function (root) {
    const MODES = Object.freeze(["content", "arrange", "test"]);
    function createState() {
        return Object.freeze({ mode: "content", selectedTablet: null });
    }
    function reduce(state, action) {
        if (action.type === "select-tablet") return Object.freeze({ ...state, selectedTablet: action.id || null });
        if (action.type === "set-mode" && MODES.includes(action.mode)) return Object.freeze({ ...state, mode: action.mode });
        return state;
    }
    function select(state, { image = false, arrangement = false } = {}) {
        return Object.freeze({ ...state,
            inspectorSubject: Object.freeze(state.selectedTablet
                ? { kind: "tablet", id: state.selectedTablet } : { kind: "tools", mode: state.mode }),
            draftOwner: image ? "image" : arrangement ? "arrangement" : "none" });
    }
    function stageEditable(composition, { gridPreview, viewLive, previewContent }) {
        return composition.mode === "arrange" && !gridPreview && !viewLive && !previewContent;
    }
    function selectionNavigation(composition, { reveal = false, stageActivation = false } = {}) {
        const arrange = composition.mode === "arrange";
        return { expandArrange: arrange, reveal: reveal && !(stageActivation && arrange) };
    }
    function createSelectionNavigation({ composition, selectedId, revealTablet, expandArrange }) {
        return async function navigateSelection(id, options = {}) {
            const plan = selectionNavigation(composition(), options);
            if (plan.expandArrange) expandArrange();
            if (!id || !plan.reveal || selectedId() !== id) return false;
            return revealTablet(id, options.trigger);
        };
    }
    const api = { MODES, createState, reduce, select, stageEditable, selectionNavigation, createSelectionNavigation };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorComposition = api;
}(typeof window !== "undefined" ? window : globalThis));
