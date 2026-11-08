"use strict";
const assert = require("node:assert/strict");
const { fit, draw } = require("../frontend/controller/operator-stage.js");
const stageModel = require("../frontend/controller/operator-state.js");

class Element {
    constructor(tagName = "g", attributes = {}) {
        this.tagName = tagName;
        this.classList = { contains: () => false };
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
    scrollY: 0,
    matchMedia: query => ({ matches: query === "(orientation: portrait)" ? win.innerWidth < win.innerHeight : win.innerWidth <= 768 || win.innerHeight <= 512 }),
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
const parent = { clientWidth: 1000, computed: { paddingLeft: "16px", paddingRight: "16px" }, getBoundingClientRect: () => ({ bottom: 400 }) };
const field = { parentElement: parent, style: {},
    computed: { borderLeftWidth: "1px", borderRightWidth: "1px", borderTopWidth: "1px", borderBottomWidth: "1px" },
    getClientRects: () => [1], getBoundingClientRect: () => ({ top: 200, bottom: 400 }) };
let dragging = false;
const svg = { classList: { contains: () => dragging }, ownerDocument: doc, viewBox: { baseVal: { width: 720, height: 370 } }, style: {},
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
const dragSize = { ...svg.style };
dragging = true;
assert.equal(fit(svg), null, "stage chrome cannot refit the field during a captured drag");
assert.deepEqual(svg.style, dragSize);
dragging = false;
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
win.scrollY = 100;
field.getBoundingClientRect = () => ({ top: 100, bottom: 300 });
assert.equal(fit(svg).height, 274, "opening a preview while scrolled keeps the unscrolled stage budget");
win.scrollY = 0;
field.getBoundingClientRect = () => ({ top: 200, bottom: 400 });
win.innerWidth = 320;
bar.getBoundingClientRect = () => ({ top: 220, bottom: 556, height: 336 });
assert.equal(fit(svg).height, 966 / (720 / 370), "an inline portrait preview keeps the full-width wall scrollable");
assert.equal(doc.body.dataset.imageActionsInline, "true");
win.innerWidth = 1440;
bar.getBoundingClientRect = () => ({ top: 500, bottom: 556, height: 56 });
doc.body.dataset.outputDirty = "false";
assert.equal(fit(svg).height, 382, "applied state regains the action bar budget");
bar.computed.position = "static";
doc.body.dataset.outputDirty = "true";
assert.equal(fit(svg).height, 382, "desktop actions in another column do not consume stage height");

win.innerWidth = 390;
doc.body.dataset.outputDirty = "false";
assert.equal(fit(svg).height, 966 / (720 / 370), "the portrait wall remains full width below the Library");
parent.getBoundingClientRect = () => ({ bottom: 448 });
assert.equal(fit(svg).height, 966 / (720 / 370), "wrapped notes do not shrink the scrollable portrait artwork");
parent.getBoundingClientRect = () => ({ bottom: 400 });
doc.body.dataset.task = "images";
doc.querySelector = selector => selector === ".image-actions" ? bar : navigation;
win.innerWidth = 1440;
assert.equal(fit(svg).height, 382, "desktop actions retain their separate column");

win.innerHeight = 1200;
field.computed.width = "968px";
field.getBoundingClientRect = () => ({ top: 400, bottom: 800, width: 1936 });
assert.equal(fit(svg).height, 382, "CSS zoom converts viewport measurements into the field's layout units");
win.innerHeight = 600;
delete field.computed.width;
field.getBoundingClientRect = () => ({ top: 200, bottom: 400 });
rotation = Math.PI / 3;
fit(svg);
assert.ok(Math.abs(Number(label.getAttribute("font-size")) * Math.hypot(label.getScreenCTM().a, label.getScreenCTM().b) - 12) < 1e-10);
parent.clientWidth = 170;
label.dataset.label = "Tablet 2";
fit(svg);
assert.equal(label.textContent, "2", "compact labels keep the distinguishing tablet number");
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

win.innerHeight = 600;
doc.getElementById = () => ({ getClientRects: () => [1] });
result = fit(svg);
assert.equal(result.width, 366, "enlarged-text navigation keeps a full-width scrollable wall");
assert.ok(Math.abs(result.height - result.width * 370 / 720) < 1e-10);
doc.getElementById = () => null;

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
{
    const cover = stageModel.fitTransform({ kind: "logical", width: 200, height: 200 },
        { intrinsicWidth: 1600, intrinsicHeight: 1000, fit: "cover" });
    assert.equal(cover.cropX, 0.375, "1600x1000 on a 200x200 wall crops 37.5% of source width");
    assert.equal(cover.cropY, 0, "the fitted source height is fully visible");
    const contain = stageModel.fitTransform({ kind: "logical", width: 200, height: 200 },
        { intrinsicWidth: 1600, intrinsicHeight: 1000, fit: "contain" });
    assert.equal(1 - contain.width / 200, 0, "Fit leaves no wall width uncovered");
    assert.equal(1 - contain.height / 200, 0.375, "Fit leaves 37.5% of wall height uncovered");
    const aspects = { wide: [1600, 1000], tall: [1000, 1600], square: [1000, 1000] };
    const walls = { wide: [200, 100], tall: [100, 200], square: [200, 200] };
    for (const [sourceName, [sourceWidth, sourceHeight]] of Object.entries(aspects)) {
        for (const [wallName, [wallWidth, wallHeight]] of Object.entries(walls)) {
            for (const fitMode of ["cover", "contain"]) {
                const transform = stageModel.fitTransform({ kind: "logical", width: wallWidth, height: wallHeight },
                    { intrinsicWidth: sourceWidth, intrinsicHeight: sourceHeight, fit: fitMode });
                assert.ok(transform, sourceName + " source in a " + wallName + " wall with " + fitMode);
                const cropX = transform.cropX, cropY = transform.cropY;
                const uncoveredX = 1 - transform.width / wallWidth, uncoveredY = 1 - transform.height / wallHeight;
                if (fitMode === "cover") {
                    assert.ok(cropX >= 0 && cropY >= 0 && (cropX === 0 || cropY === 0),
                        "Fill crops at most one source axis: " + sourceName + "/" + wallName);
                } else {
                    assert.ok(uncoveredX >= 0 && uncoveredY >= 0 && (uncoveredX === 0 || uncoveredY === 0),
                        "Fit leaves bands on at most one wall axis: " + sourceName + "/" + wallName);
                }
            }
        }
    }
    for (const invalid of [undefined, null, 0, -1, NaN, Infinity, "1600", true]) {
        assert.equal(stageModel.fitTransform({ kind: "logical", width: 200, height: 200 },
            { intrinsicWidth: invalid, intrinsicHeight: 1000, fit: "cover" }), null,
        "missing or invalid source dimensions never produce a zero estimate");
        assert.equal(stageModel.fitTransform({ kind: "physical", bounds: { x: 0, y: 0, width: invalid, height: 200 } },
            { intrinsicWidth: 1600, intrinsicHeight: 1000, fit: "cover" }), null,
        "missing or invalid wall bounds never produce a zero estimate");
    }
    const imageTarget = new Element("svg");
    draw({ svg: imageTarget, layout: { kind: "logical", width: 200, height: 200, placements: {} },
        content: { type: "image", asset: "a", url: "/assets/a", fit: "cover", intrinsicWidth: 1600,
            intrinsicHeight: 1000, background: "#0b1120" }, labelFor: () => "",
        statusFor: () => ({ status: "offline", text: "Offline" }) });
    const images = [];
    const collect = parent => parent.children.forEach(child => { if (child.tagName === "image") images.push(child); collect(child); });
    collect(imageTarget);
    assert.equal(images.length, 2, "the context preview and visible wall share the image element");
    for (const image of images) {
        assert.equal(Number(image.getAttribute("x")), -60, "the centered cover image starts left of the wall");
        assert.equal(Number(image.getAttribute("y")), 0, "the centered cover image starts at the wall top");
        assert.equal(Number(image.getAttribute("width")), 320, "the cover image is 320 logical units wide");
        assert.equal(Number(image.getAttribute("height")), 200, "the cover image fills the wall height");
    }
}
const roster = { z: { number: 1 }, a: { number: 2 }, m: { number: 3 } };
const target = new Element("svg");
const options = { svg: target, layout: { kind: "logical", width: 300, height: 100, placements:
    Object.fromEntries(["m", "a", "z"].map((id, index) => [id, { x: index * 100, y: 0, w: 100, h: 100 }])) },
    labelFor: id => id, statusFor: () => ({ status: "offline", text: "Offline" }),
    compareIds: (a, b) => require("../frontend/controller/operator-state.js").compareIds(roster, {}, a, b) };
const slots = node => node.children.flatMap(child => child.getAttribute("data-device-id") ? [child] : slots(child));
for (const selectedId of ["a", "z", "m"]) {
    draw({ ...options, selectedId });
    assert.deepEqual(slots(target).map(slot => slot.getAttribute("data-device-id")), ["z", "a", "m"],
        "stage tab order follows tablet numbers regardless of placement order or selection");
}
delete global.document;
console.log("Stage geometry, measured fit, relocation, action budgets and screen-space labels passed");
