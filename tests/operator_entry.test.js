"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(require.resolve("../frontend/controller/operator-entry.js"), "utf8");
for (const path of ["/controller/", "/controller/index.html"]) {
    for (const blocked of [false, true]) {
        let ready, destination;
        const nodes = { "entry-link": {}, "entry-status": {} };
        const location = new URL("http://127.0.0.1:18000" + path + "?view=wall#stage-title");
        location.replace = url => { if (blocked) throw new Error("Navigation denied"); destination = url; };
        vm.runInNewContext(source, { URL, window: { location }, document: { readyState: "loading",
            addEventListener(_event, handler) { ready = handler; }, getElementById: id => nodes[id] } });
        assert.equal(destination, undefined, "navigation waits for the fallback content");
        ready();
        const expected = "http://127.0.0.1:18000/controller/physical.html?view=wall#stage-title";
        assert.equal(nodes["entry-link"].href, expected, "fallback stays on the same origin and preserves local state");
        if (blocked) assert.match(nodes["entry-status"].textContent, /blocked.*Open wall workspace/);
        else assert.equal(destination, expected);
    }
}
console.log("Controller entry forwards to one workspace and retains a usable fallback");
