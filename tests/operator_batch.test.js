"use strict";
const assert = require("node:assert/strict");
const { confirmModels } = require("../frontend/controller/operator-devices.js");
(async () => {
    for (const failure of [null, "external-before-third", "external-during-third", "external-after-second", "uncertain-third"]) {
        let etag = "start", writes = 0, reads = 0;
        const guards = [], subjects = ["one", "two", "three", "four"];
        const result = await confirmModels({ ids: subjects, modelId: "actual-model", hardwareDeclared: true, reviewedEtag: "start",
            ingestConfig() {}, currentEtag: () => etag,
            async api(method, path, body, options) {
                if (method === "GET") {
                    reads += 1;
                    if (failure === "external-before-third" && reads === 3) etag = "unrelated-get";
                    return { etag };
                }
                guards.push(options.ifMatch); writes += 1;
                assert.equal(options.ifMatch, etag);
                assert.deepEqual(body, { mode: "explicit", model_id: "actual-model" });
                if (writes === 3 && failure === "external-during-third") throw Object.assign(new Error("external change"), { status: 412 });
                if (writes === 3 && failure === "uncertain-third") throw Object.assign(new Error("connection lost after send"), { status: 0 });
                if (writes === 2 && failure === "external-after-second") {
                    etag = "unrelated-get";
                    return { etag, commandEtag: "returned-2" };
                }
                etag = "returned-" + writes;
                return { etag };
            },
            progress() { subjects.reverse(); }
        });
        if (!failure) {
            assert.deepEqual(result.completed, ["one", "two", "three", "four"], "original captured order survives external selection edits");
            assert.deepEqual(guards, ["start", "returned-1", "returned-2", "returned-3"]);
        } else {
            assert.deepEqual(result.completed, ["one", "two"]);
            assert.equal(result.failed, "three"); assert.deepEqual(result.untouched, ["four"]);
            assert.equal(result.status, failure === "uncertain-third" ? "uncertain" : "conflict");
            assert.ok(!guards.includes("unrelated-get"), "a fresh unrelated GET never authorizes the next write");
        }
    }
    await assert.rejects(() => confirmModels({ ids: ["one"], modelId: "model", hardwareDeclared: false, reviewedEtag: "original" }), /declare/);
    console.log("Sequential model guards, immutable subjects, external conflicts and uncertain partial outcomes passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
