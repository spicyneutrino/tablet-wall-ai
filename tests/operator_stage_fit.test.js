"use strict";
const assert = require("node:assert/strict");
const { fit, draw } = require("../frontend/controller/operator-stage.js");

class Element {
    constructor(tagName = "g", attributes = {}) {
        this.tagName = tagName;
        this.attrs = new Map(Object.entries(attributes));
        this.children = [];
        this.style = { setProperty() {} };
        this.dataset = {};
        this.textContent = "";
    }
    get attributes() { return [...this.attrs].map(([name, value]) => ({ name, value })); }
    setAttribute(name, value) { this.attrs.set(name, String(value)); }
    getAttribute(name) { return this.attrs.get(name) || null; }
    hasAttribute(name) { return this.attrs.has(name); }
    removeAttribute(name) { this.attrs.delete(name); }
    append(...nodes) { nodes.forEach(node => this.insertBefore(node, null)); }
    insertBefore(node, before) {
        if (node.parentElement) node.remove();
        this.children.splice(before ? this.children.indexOf(before) : this.children.length, 0, node);
        node.parentElement = this;
    }
    remove() { this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1); }
    closest() { return null; }
    querySelectorAll() { return []; }
}
const events = {}, observers = [], frames = [];
const win = {
    innerHeight: 900,
    getComputedStyle: node => node.computed,
    addEventListener: (name, callback) => { events[name] = callback; },
    requestAnimationFrame: callback => { frames.push(callback); return frames.length; },
    ResizeObserver: class {
        constructor(callback) { this.callback = callback; observers.push(this); }
        observe(node) { this.node = node; }
        disconnect() { this.node = null; }
    }
};
const bar = { computed: { position: "fixed", marginTop: "8px" }, getClientRects: () => [1],
    getBoundingClientRect: () => ({ top: 788, bottom: 844, height: 56 }) };
const navigation = { ...bar, computed: { position: "fixed", marginTop: "0px" },
    getBoundingClientRect: () => ({ top: 844, bottom: 900, height: 56 }) };
const doc = { defaultView: win, body: { dataset: { task: "images", outputDirty: "false" } },
    querySelector: selector => selector === ".image-actions" ? bar : navigation,
    createElementNS: (_, tag) => new Element(tag), getElementById: () => null };
const parent = { clientWidth: 1000, computed: { paddingLeft: "16px", paddingRight: "16px" } };
const field = { parentElement: parent, style: {},
    computed: { borderLeftWidth: "1px", borderRightWidth: "1px", borderTopWidth: "1px", borderBottomWidth: "1px" },
    getClientRects: () => [1], getBoundingClientRect: () => ({ top: 200 }) };
const svg = { ownerDocument: doc, viewBox: { baseVal: { width: 720, height: 370 } }, style: {},
    closest: () => field, querySelectorAll: () => labels };
const label = new Element("text");
label.dataset = { width: "667", height: "354", x: "0", y: "0", label: "Screen 1" };
let rotation = 0;
label.getScreenCTM = () => {
    const scale = parseFloat(svg.style.inlineSize) / 720 * 0.35;
    return { a: scale * Math.cos(rotation), b: scale * Math.sin(rotation) };
};
const labels = [label];
let result = fit(svg);
assert.equal(result.width, 966, "available width excludes parent padding and field border");
assert.equal(parseFloat(field.style.inlineSize), 968, "field shrink-wraps the SVG and its border");
assert.equal(result.width / result.height, 720 / 370);
assert.equal(Number(label.getAttribute("font-size")) * Math.hypot(label.getScreenCTM().a, label.getScreenCTM().b), 12);
assert.equal(Number(label.getAttribute("stroke-width")), 0, "the solid label chip replaces the glyph halo");

win.innerHeight = 600;
navigation.getClientRects = () => [];
result = fit(svg);
assert.equal(result.height, 382, "height accounts for field top, bottom margin and borders");
assert.equal(result.width, 382 * 720 / 370, "height-limited walls retain their aspect ratio");
doc.body.dataset.outputDirty = "true";
bar.getBoundingClientRect = () => ({ top: 500, bottom: 556, height: 56 });
result = fit(svg);
assert.equal(result.height, 274, "preview reserves the visible fixed action bar and gap");
doc.body.dataset.outputDirty = "false";
assert.equal(fit(svg).height, 382, "applied state regains the action bar budget");
bar.computed.position = "static";
doc.body.dataset.outputDirty = "true";
assert.equal(fit(svg).height, 382, "desktop actions in another column do not consume stage height");

const idleActions = { getClientRects: () => [1], getBoundingClientRect: () => ({ bottom: 264 }),
    closest: () => ({ computed: { paddingBottom: "16px" }, getBoundingClientRect: () => ({ top: 100 }) }) };
doc.querySelector = selector => selector === ".image-actions" ? bar : selector === "#image-idle-actions" ? idleActions : navigation;
win.innerWidth = 390;
doc.body.dataset.outputDirty = "false";
assert.equal(fit(svg).height, 186, "the phone wall leaves room for the explicit image-change actions");
win.innerWidth = 1440;
assert.equal(fit(svg).height, 382, "desktop actions retain their separate column");

rotation = Math.PI / 3;
fit(svg);
assert.ok(Math.abs(Number(label.getAttribute("font-size")) * Math.hypot(label.getScreenCTM().a, label.getScreenCTM().b) - 12) < 1e-10);
parent.clientWidth = 70;
fit(svg);
assert.equal(label.style.display, "none", "panels too small for 10px text omit their visual label");
parent.clientWidth = 1000;
events.resize();
frames.shift()();
assert.equal(label.style.display, "", "resize restores readable labels");
const relocated = { ...parent, clientWidth: 400 };
field.parentElement = relocated;
result = fit(svg);
assert.equal(observers[0].node, relocated, "a fit after relocation observes the new stage host");
assert.equal(result.width, 366);
win.innerHeight = 180;
result = fit(svg);
assert.equal(result.height, 120, "an exhausted viewport keeps a usable field with page scrolling");

global.document = doc;
for (const [width, height] of [[2000, 1000], [1000, 2000], [8000, 200]]) {
    const target = new Element("svg");
    const layout = { kind: "logical", width, height, placements: {
        a: { x: 20, y: 30, w: 100, h: 80, bezel: { left: 4, top: 2, right: 3, bottom: 5 } }
    } };
    const before = structuredClone(layout);
    const stage = draw({ svg: target, layout, content: null, labelFor: () => "Screen 1", statusFor: () => ({ status: "offline", text: "Offline" }) });
    assert.equal(stage.offX, 10);
    assert.equal(stage.offY, 10);
    assert.equal(stage.scale * width, 700);
    assert.equal(stage.height, 20 + 700 * height / width);
    assert.deepEqual(layout, before, "rendering preserves bezels, placements and empty logical bounds");
}
delete global.document;
console.log("Stage geometry, measured fit, relocation, action budgets and screen-space labels passed");
