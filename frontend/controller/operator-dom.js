"use strict";
(function (root) {
    const $ = id => document.getElementById(id);

    function capture(...roots) {
        const elements = new Map();
        return id => {
            if (elements.has(id)) return elements.get(id);
            for (const region of roots) {
                const node = region.id === id ? region : region.getElementById
                    ? region.getElementById(id) : region.querySelector("#" + id);
                if (node) { elements.set(id, node); return node; }
            }
            return null;
        };
    }

    function readonly(value) {
        if (!value || typeof value !== "object") return value;
        const copy = Array.isArray(value) ? value.map(readonly)
            : Object.fromEntries(Object.entries(value).map(([key, item]) => [key, readonly(item)]));
        return Object.freeze(copy);
    }

    function setTextIfChanged(node, text) {
        if (node && node.textContent !== text) node.textContent = text;
    }

    function clearChildren(node) {
        if (node) node.textContent = "";
    }

    function appendText(parent, tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        node.textContent = text;
        parent.appendChild(node);
        return node;
    }

    const dom = { $, capture, readonly, setTextIfChanged, clearChildren, appendText };
    if (typeof module !== "undefined" && module.exports) module.exports = dom;
    else root.OperatorDom = dom;
})(typeof window !== "undefined" ? window : globalThis);
