"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(require.resolve("../frontend/client/ruler.js"), "utf8");
function ruler(width = 1024, height = 768, top = 280) {
    const ids = {};
    const listeners = { document: {}, window: {}, visual: {} };
    const node = () => ({ style: {}, children: [], hidden: false, textContent: "", scrollTop: 0,
        listeners: {}, value: "long", setAttribute() {}, focus() { this.focused = true; },
        addEventListener(type, fn) { this.listeners[type] = fn; },
        appendChild(child) { this.children.push(child); child.parentNode = this; },
        removeChild(child) { this.children.splice(this.children.indexOf(child), 1); },
        getBoundingClientRect() { return { top, width: width - 40 }; },
        set innerHTML(value) {
            this.children = [];
            for (const match of value.matchAll(/id="([^"]+)"/g)) ids[match[1]] = node();
        },
        querySelector() { return instructions; },
    });
    const instructions = node();
    const body = node();
    const add = bucket => (type, fn) => { listeners[bucket][type] = fn; };
    const remove = bucket => type => { delete listeners[bucket][type]; };
    const window = { innerWidth: width, innerHeight: height, location: { search: "?calibrate=1" },
        visualViewport: { scale: 1, addEventListener: add("visual"), removeEventListener: remove("visual") },
        addEventListener: add("window"), removeEventListener: remove("window") };
    let updateIdentity;
    vm.runInNewContext(source, { window, document: { body, createElement: node,
        getElementById: id => ids[id] || null, addEventListener: add("document"), removeEventListener: remove("document") },
        MutationObserver: class { constructor(fn) { updateIdentity = fn; } observe() {} disconnect() {} } });
    return { ids, window, listeners, body, updateIdentity: () => updateIdentity(), setTop(value) { top = value; } };
}

for (const [width, height, top] of [[1440, 1000, 270], [768, 1024, 270], [390, 844, 380]]) {
    test("long ruler fits both endpoint targets within usable " + width + "x" + height, () => {
        const h = ruler(width, height, top);
        const w = parseInt(h.ids["ruler-horizontal"].style.width);
        const v = parseInt(h.ids["ruler-vertical"].style.height);
        assert.ok(w > 200 && v > 200);
        assert.ok(20 + 8 + w + 2 <= width);
        assert.ok(top + 86 + v + 2 <= height);
        assert.equal(h.ids["ruler-horizontal-label"].textContent, `Horizontal: 0 to ${w} CSS px`);
        assert.equal(h.ids["ruler-vertical-label"].textContent, `Vertical: 0 to ${v} CSS px`);
        assert.match(h.ids["ruler-horizontal"].children.at(-1).style.cssText, new RegExp("left:" + (w - 2) + "px"));
    });
}

test("short-span retains a labelled 200 CSS px option and fits smaller viewports", () => {
    const h = ruler(); h.ids["ruler-span"].value = "short";
    h.ids["ruler-span"].listeners.change();
    assert.equal(h.ids["ruler-horizontal"].style.width, "200px");
    assert.equal(h.ids["ruler-vertical"].style.height, "200px");
    assert.match(source, /short-span \/ higher extrapolation/);
    const narrow = ruler(220, 600, 300); narrow.ids["ruler-span"].value = "short";
    narrow.ids["ruler-span"].listeners.change();
    assert.equal(narrow.ids["ruler-horizontal"].style.width, "160px");
});

test("zoom hides the targets, fullscreen redraws actual lengths and close removes handlers and overlay", () => {
    const h = ruler();
    h.window.visualViewport.scale = 2; h.listeners.visual.resize();
    assert.equal(h.ids["ruler-horizontal"].hidden, true);
    assert.equal(h.ids["ruler-vertical"].hidden, true);
    assert.match(h.ids["ruler-zoom"].textContent, /100%/);
    h.window.visualViewport.scale = 1; h.window.innerHeight = 900;
    h.listeners.document.fullscreenchange();
    assert.equal(h.ids["ruler-vertical"].hidden, false);
    assert.equal(h.ids["ruler-vertical"].style.height, "500px");
    assert.equal(h.ids["ruler-title"].focused, true);
    h.ids["ruler-close"].listeners.click();
    assert.equal(h.body.children.length, 0);
    assert.equal(h.listeners.document.fullscreenchange, undefined);
    assert.equal(h.listeners.window.resize, undefined);
});


test("a late welcome identity resizes both spans when the header grows", () => {
    const h = ruler(768, 1024, 237);
    const original = parseInt(h.ids["ruler-vertical"].style.height);
    h.setTop(279); h.updateIdentity();
    assert.equal(parseInt(h.ids["ruler-vertical"].style.height), original - 42);
});
