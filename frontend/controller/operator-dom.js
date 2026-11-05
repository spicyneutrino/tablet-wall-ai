"use strict";
(function (root) {
    const $ = id => document.getElementById(id);

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

    const dom = { $, setTextIfChanged, clearChildren, appendText };
    if (typeof module !== "undefined" && module.exports) module.exports = dom;
    else root.OperatorDom = dom;
})(typeof window !== "undefined" ? window : globalThis);
