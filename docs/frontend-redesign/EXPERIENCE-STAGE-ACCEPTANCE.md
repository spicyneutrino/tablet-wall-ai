# Frozen task-aware stage verification

Observed 2026-11-02 against source **361ec04ae8ece99c014a2bd9b3a54e21b5f1fdce**. This is independent stage software verification, not combined-shell approval. No application, existing test, backend, deployment, or acceptance-driver files were edited.

## Verdict and findings

Approval remains open.

1. **Task presentation redraw is delayed.** After real tab clicks, the SVG retains the preceding task presentation. Images observed `context`, Tablets observed `images`, and Arrange observed `tablets`. After 1300ms reconciliation each becomes correct. Reproduce by applying an arrangement, switching tasks, and reading `#stage-svg.dataset.presentation` immediately. `frontend/controller/physical.js:714` changes task state and calls workspace rendering without drawing the stage. `physical-stage.js:29` derives the presentation only when invoked. Root already identified this integration requirement for the shell owner. Evidence is /tmp/stage-361-browser/results.json, checks named “Immediate task presentation …”. This matters because Images can briefly retain the diagnostic underlay.
2. **One existing Node fixture fails under the new fence.** `tests/controller_modules.test.js:183` expects a physical nudge with no `tabName` supplied. `physical-stage.js:422` now requires `show` (Arrange). Actual browser nudging in Arrange passes. Update that fixture in its owner's worktree; do not weaken the fence. All 29 test files ran, 28 passed.
3. **Actual heterogeneous pinned physical sizes remain open.** The private profile-save experiment correctly retained revision-1 layout pins. Saving a new 150.25mm profile did not silently repin the existing slot. Consequently the assertion named “Actual mixed pinned profiles…” in /tmp/stage-361-mixed/results.json proves negative bounds and scene preservation, not heterogeneous applied sizes. The accompanying pins file establishes this limitation. Renderer-only mixed-size probes passed; they are not accepted hardware or actual-client mixed-profile evidence.

## Proven behavior

| Case | Observed result | Evidence directory under /tmp |
| --- | --- | --- |
| Physical pointer delta, threshold, Escape, reviewed Apply | Delta agrees with screen CTM; cancelled motion restores geometry; Apply preserves every exact profile/calibration pin | stage-361-browser |
| Arrange fence | Images and Tablets Shift-arrow leave geometry clean; current arrangement unchanged; focused Arrange editing works | stage-361-browser |
| Logical resize at 1440×900 and 390×844 | Real handle drag agrees with CTM within rounding tolerance; Escape restores width; mutations remain local | stage-361-logical-r2 |
| Logical keyboard and View live | Shift-arrow adds ten units; View live blocks further keyboard change | stage-361-logical-r2 |
| Explicit mount 90° and 270° | SVG rotation and accepted slot angles agree; pinned revisions retained | stage-361-browser |
| Offline | Closed actual client retains placement; stage hatch and external offline identity appear | stage-361-logical-r2 |
| Current versus old paint | Held native old acknowledgement cannot establish current output; fresh acknowledgement resolves it | stage-361-old-paint |
| Missing live asset | Delete private fixture bytes, reload actual client; scene identity retained and failed evidence exposed; UI upload/Show restores four fresh paints | stage-361-missing-live |
| Negative bounds | UI moves physical centre to −200mm; accepted bounds x=−288.7mm, width=998.3mm; scene and all pins preserved | stage-361-mixed |
| Mixed dimensions, negative bounds, missing profiles | Renderer-only configurations preserve input and expose missing-profile accessible names | stage-361-renderer-r3 |
| Fill/Fit crop invariance | Both fits preserve exact image x/y/width/height across Images, Tablets and Arrange; scene transform remains independent of stage fit | stage-361-renderer-r3 |
| Accessible identities | All four exact tablet numbers occur in SVG button names and external identity rows; external font size ≥14 CSS px | stage-361-browser |
| Images and Arrange drawing | Reconciled Images has no 0.22-opacity underlay; Arrange retains underlay, boundaries, gaps and external diagnostics | stage-361-browser |

The mixed renderer probe uses explicit approximate profiles (147×210mm with 15.2mm bezels and 100×160mm with asymmetric bezels), revision numbers 7/9 and calibration pins 4/6, mounts 90/270, and negative bounds. These are deliberately synthetic renderer inputs, not API-admitted measurements. Missing-profile configuration was renderer-isolated rather than forged into server authority.

Inspected screenshots include the 1440×900 two-by-two review, 390×844 measured-review full page, 1440×900 Images, 390×844 mount-270 viewport, 1440×900 negative-bounds wide wall, and the mixed renderer screenshot. Physical bodies/panels keep proportions; bezels and the large negative-position gap remain visible. Artwork clips to active panels. The phone mount screenshot is scrolled into setup, and does not establish task-entry quality. The existing shell is intentionally outside this review's broad UX scope. The first-preview phone capture can retain older logical geometry before redraw; it is not proof of immediate physical preview fidelity.

## Environment, reruns and artifacts

Read EXPERIENCE-DIRECTION.md, EXPERIENCE-ROADMAP.md, supplied AGENTS instructions, RTK.md, karpathy-guidelines, poteto-mode, browser-harness, frontend-testing-debugging and accessibility-inclusive-design. No additional repository AGENTS.md files were found.

Chrome DevTools failed with “Could not find Google Chrome executable … /opt/google/chrome/chrome.” Playwright MCP expected missing chromium-1252. Harness doctor reported daemon unavailable and zero active connections. Preview status was unavailable; preview_open rejected about:blank as an invalid URL. No user browser was attached, browser installed, or display variable changed.

Authorized fallback used the root project's Python 3.13 virtualenv, Playwright and cached Chromium 143/chromium-1200. Each Rig owned a free loopback port, private XDG roots, database, assets/media and browser contexts. Four shipped /client/ pages registered and reported current tokens. No live data or network configuration was changed.

Exact shell invocations used the following forms (all shell invocations went through rtk):

```sh
rtk proxy bash -c 'for f in tests/*.test.js; do node "$f" > /tmp/stage-361-evidence/$(basename "$f").log 2>&1; echo "$? $f"; done > /tmp/stage-361-evidence/node-results.txt'
rtk proxy python3 -m py_compile /tmp/stage361.py /tmp/stage361-logical.py /tmp/stage361-faults.py /tmp/stage361-renderer.py /tmp/stage361-mixed.py
```

Browser scripts were run through rtk proxy bash with this environment and interpreter prefix:

```sh
PLAYWRIGHT_BROWSERS_PATH=/var/home/oak/.cache/ms-playwright /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python
```

Arguments were /tmp/stage361.py /tmp/stage-361-browser; /tmp/stage361-logical.py /tmp/stage-361-logical-r2; /tmp/stage361-faults.py (outputs old-paint and missing-live directories); /tmp/stage361-renderer.py /tmp/stage-361-renderer-r3; /tmp/stage361-mixed.py /tmp/stage-361-mixed. Scripts reuse Rig and existing scenario helpers. Only the obsolete four-over-art-label assertion is replaced with four exact external identities and minimum font size; other guards remain intact. These bounded external wrappers avoid adding another permanent acceptance framework.

Final successful bounded runs contain 18 logical, 10 old-paint, 10 missing-live, 11 renderer, and 18 negative-bounds checks. The initial physical run contains 38 checks, including three proven presentation failures and a renderer fixture interruption. Initial logical failure used a moving `.last` selector; selecting the exact device fixed the driver and passed all 18 checks. Initial renderer omitted required bounds; the next attempts exposed synthetic image CSP/404 errors. Final renderer uses a same-origin blob image and passes console/network checks. Failed attempts remain in /tmp/stage-361-logical, /tmp/stage-361-renderer and /tmp/stage-361-renderer-r2. These are driver errors, not product findings.

Every Rig records identity.json, evidence.json, results.json, final-config.json, network/console evidence and screenshots. All final successful scenarios have no unexpected page exceptions, console warnings/errors or failed requests. Missing-asset failures are explicitly induced and labelled. The interrupted physical run did not reach its final console aggregate check.

All runs record the same application digest **386f885de1ec493f10c47117b3d7a212de9305f9006361086e5772ce6d5b4110**. Full source file hashes are in each identity.json. Final fetched controller script hashes are in /tmp/stage-361-renderer-r3/loaded-js-hashes.json; all 15 match workspace bytes. These are controller script hashes, not separately captured response-byte hashes for every client script.

External driver SHA-256 values:

```text
fe97cfbbc8b37a86d16d0b7e215b19f0c24b97b619ccc704cff82f8a0b6515a6  /tmp/stage361.py
7fe0960e357d6575884bfa1c7b5b75c248a3f57a2de465ca1450dcc20d5e15b8  /tmp/stage361-logical.py
83e2af57f5906842c2e6cff1ee518b073e273dd6e56eaafd111d48641bc21832  /tmp/stage361-faults.py
93d0607941c9d29197c8bc684e8830b318457b490be63c4b06ea9511978c8824  /tmp/stage361-renderer.py
d0e4bc4716541b1ad10a139924ddc995b179b0ed08719e9374b5d2da7a7cb32e  /tmp/stage361-mixed.py
```

The physical wrapper's recorded file is corrected for future reruns; its original run lacked bounds in the renderer probe. The separate successful renderer run closes that probe error. External artifacts are local and are not portable through this commit.

## Cleanup and limits

All attempted runs' results.json record browser_disconnected=true, remaining_owned_browser_pids=[], private_data_removed=true, port_closed=true, and cleanup errors=[]. Server process-group cleanup is also recorded. No owned browser or server is intentionally left running.

This does not establish combined-shell acceptance, actual heterogeneous pinned-profile client behavior, native optical accuracy, native zoom, assistive technology, physical tablets, TLS, sleep or soak behavior. Reverify the shell redraw integration and existing fixture correction before stage approval, then run the final combined candidate gate.

## Root follow-up

At `6c1afa8`, the physical-nudge fixture explicitly declares the Arrange task. All 29 Node files pass after this correction; the Arrange-only production fence remains intact. The workspace owner has the immediate-redraw requirement. That requirement is still open pending the integrated shell.

A separate actual-client run at `6c1afa8` used the existing `mixed_models` journey before the first measured Apply. The applied slots referenced both 146.75×196mm and 147×210mm panels, each through its exact profile/calibration revision 1. This closes the narrow API-admitted heterogeneous-pins gap. It does not establish four compatible mixed-model clients: the synthetic Android viewport deliberately assigned the iPad model remained `viewport_mismatch`, while the other three were `ready`. The console reported three of four showing and exposed the recovery path.

The external driver `/tmp/tablet-wall-mixed-pins-followup.py` has SHA-256 `8ce4ac0137bf68991eb33c6f41ab37c637971a3210f1af129fbd6398485577f4`. Command:

```sh
rtk proxy env PLAYWRIGHT_BROWSERS_PATH=/var/home/oak/.cache/ms-playwright .venv/bin/python -u /tmp/tablet-wall-mixed-pins-followup.py /tmp/tablet-wall-mixed-pins-root-20261102
```

All 14 checks passed, including distinct pinned dimensions, mapping refusal and console/network checks. The source identity, pins, traces, screenshots and cleanup are under that private artifact directory. Root inspected the desktop and phone mixed-model viewport captures. Those still use the old shell and do not pass the new task-entry composition gate. Browser disconnected, no owned browser PIDs remained, temporary data was removed, port closed and cleanup errors were empty. No live data or hardware was touched.
