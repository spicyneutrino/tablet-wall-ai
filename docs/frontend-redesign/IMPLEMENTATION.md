# Redesign implementation status

The accepted design is in [PLAN.md](PLAN.md), with ownership and interfaces in
[ARCHITECTURE.md](ARCHITECTURE.md). This record separates integrated work from
unfinished implementation and acceptance.

## Integrated operator upload option

Commit `5d5e1e9` integrates implementation commit
`3fe966643faae874eba1802b6e24f3c1cfb94ad6`. The launcher accepts
`make hotspot ARGS='--operator-uploads'` for one launch. Uploads remain disabled
by default. The option is not persisted in launcher settings.

The backend remains bound to loopback. Upload admission still requires the exact
operator Origin, a loopback transport peer, and no forwarded headers. The tablet
listener's allowlist is unchanged. No backend HTTP schema or frontend files
changed in this implementation package.

Root reviewed all seven changed files and reran the focused checks on the
integrated branch:

```sh
rtk proxy .venv/bin/python -m pytest -q tests/test_hotspot.py tests/test_ingress.py tests/test_media.py tests/test_media_worker.py tests/test_uploads.py tests/test_operator_images.py tests/test_deployment_guards.py tests/test_deployment_hosts.py tests/test_security.py
```

Result: **265 passed**, one Starlette deprecation warning, in 19.39 seconds.
This includes the generated-Caddy ingress test. Worker verification also passed
production Ruff and mypy, with 47 Python source files checked.

The worker's canonical private proof used Caddy 2.11.4. Root inspected its
manifest and verified that the four recorded source hashes match the integrated
files, denied requests left database and media hashes unchanged, and both proof
ports were closed. The recorded request statuses were 12 responses at 200, one
at 201, 135 at 403, and one redirect at 308. Of the refusals, 124 were on the
tablet listener. Direct JPEG upload published immutable bytes while leaving the
scene, layout and configuration ETag unchanged. Registration, device WebSocket
welcome and immutable image serving remained available to tablets.

Evidence on the development machine:

- Worker report: `/tmp/tablet-wall-upload-proof-s9kicx2c/REPORT.md`.
- Canonical manifest: `/tmp/tablet-wall-upload-proof-s9kicx2c/ingress-isolated-final/test_generated_hotspot_ingress0/ingress-manifest.json`.

These temporary paths are evidence locations, not portable repository fixtures.
The test in `tests/test_ingress.py` reproduces the generated-ingress proof.

Two execution incidents are retained. Unexpected source edits appeared during
the worker's initial read-only inspection. Root preserved a patch and hashes,
then explicitly handed the edits to the worker; their original writer was not
identified. The worker repaired the resulting indentation error. Separately,
an older ingress test wrote the shared Caddy autosave file before its test
directories were isolated. The worker reported that side effect and did not
attempt to restore an unknown prior value. The corrected rerun used private XDG
directories and left the shared file timestamp unchanged.

## Integrated functional workspace

The functional HTML/JavaScript worker resumed its preserved checkout after a
provider usage limit and committed `bc2e888518ebc4a1f610c7c7511315ae33c002a9`.
Root integrated it as `5f3e415`. One session now owns configuration and transport;
keyed tablet forms retain edits; Tablets, Arrange, Images, Saved and Settings
share one stage. Apply arrangement and Show image remain separate commands.
The worker also migrated custom logical editing, saved scenes, colours and
lifecycle controls into the primary workspace.

Root reran all **24 Node test files** successfully, then ran the private
four-client first-wall script against the integrated application. Its six checks
passed, including registration before socket readiness, automatic inclusion of
all four late joins without a console reload, and four current image reports.
Evidence is `/tmp/tablet-wall-functional-M8ZZSj/render-cm9zz4pu`. The script uses
the shipped client and console, synthetic images and private loopback storage.
Its 16 scripted console actions include one fixture-only status refresh and do
not establish a human usability benchmark.

The worker's source-matched five browser runs passed 103 assertions across
journey, conflict/lifecycle, model-batch, first-wall and disabled-upload scenarios.
Repeated startup checks are included in that count. The full handoff, limits,
styling hooks and evidence locations are at
`/tmp/tablet-wall-functional-M8ZZSj/HANDOFF.md`. Those runs precede integration
of the separate upload launcher package. They are partial acceptance, not a final
redesign verdict.

## Acceptance still pending

The styling package `12dc9872b76815b2c5edf7cf0f0f713f19f46fbb` is integrated as
`f64d89a`. Three coherent stylesheets and a licensed local Schibsted Grotesk font
replace the old primary stylesheet pair. Root inspected the desktop/phone
screenshots and the stylesheet diff. The style worker's frozen-base evidence is
at `/tmp/tablet-wall-style-sc14k38j/HANDOFF.md`; its 113 visual, 60 journey, 24
contrast/recovery and 32 keyboard-flow assertions precede root's command fixes.
These counts include repeated setup checks and are not a completeness score.

Root then addressed the style handoff's two readability findings, tracked in
[issue 26](https://github.com/spicyneutrino/tablet-wall-ai/issues/26). Calibration
recovery now uses accessible, reflowing DOM text fitted to the visual viewport;
valid mapping removes the panel. Stage labels use 14px names and 12px status text,
actual font measurements and backings bounded to their tablet width, including
quarter-turn geometry. Compact labels retain full accessible names and statuses.

The combined private proof at
`/tmp/tablet-wall-root-visual-hq4gye7b/render-w0rpplhb` passed **40 checks** for
contrast, 1440/390/320 label geometry, both tablet recovery orientations, 200%
text emulation and restoration to four current image reports. A separate run at
`render-1v_qc1c7` passed the complete **60-check** image/custom-geometry/Saved/
lifecycle parity journey against the integrated styles and root fixes. Both
record no page errors and stopped browsers/servers. The deliberate invalid Saved
name in the contrast proof remains a labelled expected 422. Root inspected the
new recovery screenshots and the combined desktop wall. Native operator zoom,
assistive technology and real hardware remain unrun.

The independent functional review of `9fc7d6a` found three P2 defects, tracked in
[issue 25](https://github.com/spicyneutrino/tablet-wall-ai/issues/25): durable HTTP
5xx responses did not engage the uncertainty lock; history actions could bypass
image-draft ownership and resolution handled only one incompatible draft; a
refused grid preview still created grid state that blocked manual editing.
The report is `/tmp/tablet-wall-independent-review-vL9MSs/REPORT.md`. Its verdict
is **ISSUES**, with no architectural objection to the reconciled ownership.

Root corrected these paths and verified the corrections with **25 Node test
files** and two private actual-client browser runs, passing **22** and **12**
checks respectively. The browser checks forward a real committed name save before
injecting a 500, prove that a second write cannot reach transport until refresh,
keep image intent through a Ctrl+Y attempt outside Arrange, and verify that a
refused grid preview leaves later manual geometry edits matching the stage.
Both runs also cover normal image/lifecycle behavior and report no page errors;
the injected 500 remains a labelled expected network error. Their manifests
record closed browsers, absent server processes and closed ports.

Evidence is under `/tmp/tablet-wall-root-fixes-ykmb5uck/`, specifically
`browser-1793618572275231565` and `browser-1793618516884081586`. An earlier root
assertion incorrectly treated image-preview tiles as arrangement-preview tiles;
that failed probe is retained and excluded from the passing totals. A separate
select-key probe initially attempted focus while the model field was hidden.
Waiting for visibility kept Home in the native select, so that observation did
not justify a product keyboard change. Root's correction checks do not substitute
for independent final review of the corrected, styled application.

The default compatibility entry is now retired after the combined 60-check
parity journey. `/controller/` and `/controller/index.html` open the same primary
workspace as `/controller/physical.html`, preserving query and fragment state.
The entry retains a styled manual link when automatic navigation is blocked or
JavaScript is off. The former editor and its guarded behavior remain at
`experimental.html`, linked only inside the explicit Experimental controls.
Its scripts and stylesheet remain because that limited consumer still exists;
no normal navigation offers a second editor.

Empty-wall onboarding now waits for authoritative configuration, replaces the
empty diagram with readable joining guidance, and hides tablet actions until a
tablet is selected. Its next action changes to Arrange when connected tablets
are available. Entry proof at `/tmp/tablet-wall-entry-final-8yc2lnva` passed
**34 checks** across the three URLs at desktop/phone sizes, one controller socket
per page, empty-state presentation, and a 320px JavaScript-disabled fallback.
Source identity is recorded after the run and before commit. The fresh four-client
first-wall rerun at `/tmp/tablet-wall-functional-M8ZZSj/render-a53vwsex` passed all
six checks after these changes. Root inspected the phone and fallback screenshots.

Static/API and WAN-isolated offline checks passed **37 Python tests**. The
offline crawler follows the local font and both supported operator entries; it
does not mistake embedded URLs in binary font metadata for executable network
dependencies. Ruff passed for the three affected Python test/probe files. Both
entry runs closed their browsers and servers; the final run records a closed
port. Earlier mistyped temporary script paths started no server, and a rerun
against an existing artifact directory was refused before startup. They are not
counted as passing checks.

The portable four-client journey, final combined responsive/accessibility
verification, and independent final review remain open.

At clean `508aecc`, the isolated broad check passed **1,814 Python tests**, all
**26 Node test files**, production Ruff and mypy across **47 source files**.
The Python run reported three existing deprecation warnings. Logs, JUnit and
command outcomes are at `/tmp/tablet-wall-final-checks-9atz56sk`. The entire run
used private XDG directories and removed inherited wall storage settings.

A later first-preview probe found that the newly hidden empty diagram was
measured before its preview visibility changed, briefly shrinking labels to
11.55px. Root moved the workspace projection before stage measurement. The fresh
run `/tmp/tablet-wall-first-preview-depdf7ef/render-e8vyktsv` passed seven checks,
including immediate 14px labels and four current image reports. The failed
pre-fix run is retained in the same parent directory. Controller module checks
passed after this one-line JavaScript correction; the broad Python result above
predates it and is not presented as a new run on the corrected tree.
The upload package alone does not establish those results. No live
deployment, real tablet, hotspot/firewall, optical continuity, sleep, TLS or video
acceptance is claimed.

## Portable acceptance integration

The QA driver's commits `8d5bfa2` and `4676c12` are integrated as `de4311c` and
`68d6347`. They preserve actual shipped-client journeys, source/driver hashes,
failure artifacts and cleanup. The worker's full run on its older unstyled
application recorded 443 result rows with 63 failures. Corrected-driver recovery
and parity reruns reached their end with four remaining favicon failures across
130 rows. These are retained failing results, not acceptance of the current app.
The detailed handoff is `/tmp/tablet-wall-D-HANDOFF.md`.

Root fixed the client favicon request with an explicit same-origin SVG and one
exact GET/HEAD static path in the tablet allowlist. CSP and operator-route denial
are unchanged. The composed-Caddy proof passed on the updated allowlist; its
copied manifest is at
`/tmp/tablet-wall-favicon-ingress-tys6crky/ingress-manifest.json`. The icon returned
200, all 135 denial responses remained 403, denied requests left database/media
hashes unchanged, and both proof ports closed. Source and allowlist hashes match
the correction. The combined deployment/ingress/driver selection passed
**66 Python tests**, including all nine driver safety/action-count tests.

The current portable first-wall run at
`/tmp/tablet-wall-combined-first-20261102` passed **15 checks** with no page
exceptions, unexpected HTTP failures or console warnings/errors. The driver
still records uncovered mandatory cases and refuses to label its aggregate
acceptance complete. Root is assigning the remaining software variants and a
fresh independent review; native assistive technology, native zoom and hardware
limits remain explicit. No aggregate redesign PASS is claimed here.


## Independent review and upload reconciliation correction

The independent final application review of clean `295cb61` verified the three
previous command/draft findings closed. It passed 296 focused Python tests, all
26 then-existing Node test files, 15 protocol cases and 88 positive assertions
across four private rendered journeys. Its verdict remained ISSUES because the
separate upload XHR path treated a real publication followed by HTTP 503 as a
known refusal, enabling another submission. It also proved that favicon HEAD
was denied despite the intended GET/HEAD contract. The full report is
`/tmp/tablet-wall-final-independent-3tap37yn/REPORT.md`.

Root tracked these findings in issue #27 and corrected the upload outcome at
its transport boundary. HTTP 5xx, status zero and successful responses without
a readable asset identity now retain upload uncertainty. They invalidate older
inventory reads; only a subsequent successful inventory refresh unlocks retry.
Known validation/admission refusals keep their specific guidance. The wall is
never changed by uploading. The favicon has a separate exact GET/HEAD matcher;
other client methods and suffix paths remain denied.

The new Node regression first failed on the misleading refusal, then passed
for seven ambiguous receipt variants, old reads, failed refreshes, successful
reconciliation and six known refusal statuses. All **27 Node test files** pass.
The actual browser proof forwarded real JPEG bytes to publication, replaced its
response with 503, and passed **12 checks**, including blocked duplicate sends,
failed/successful inventory refreshes, unreadable 201 handling, unchanged wall
content and phone width. There were no page exceptions; the two HTTP 503 errors
were deliberate response injections. Root inspected the desktop/phone evidence.

Focused deployment and ingress checks pass **57 Python tests** with one existing
deprecation warning. The generated Caddy proof returns 200 for icon GET/HEAD and
403 for POST, suffix HEAD and other client-file HEAD. Both backend/proxy ports
closed, and denied requests left stored state unchanged. Ruff and whitespace
checks pass. The initial test run retained a stale seven-proxy count assertion;
that test was updated for the eighth explicitly credential-stripping matcher.
The initial 56-pass/one-failure log remains alongside the passing rerun.

Evidence is at `/tmp/tablet-wall-upload-fix-6eadvom6/`, including `node.json`,
`pytest-rerun.xml`, `pytest-rerun.log`, the generated ingress manifest and
`browser-1793637082624971442`. The browser manifest records modified-source
hashes, its driver hash, stopped browser/server and closed port. These are
root correction checks, not an independent approval of the correction or a
complete portable acceptance pass. The separate matrix expansion remains open.


## Expanded portable acceptance integration

The QA worker kept application bytes frozen at `295cb61`, then committed
`7a37975`, `6470f24` and `f93f99b`. Root integrated those driver-only changes as
`492fa75`, `4325679` and `da643b3`. They add isolated pointer/snap, model-batch,
authority/paint, upload, lifecycle, keyboard, visual-state and entry/recovery
cases. Source-matched external ingress proof is read-only. Native browser zoom,
operating-system IME, screen-reader and hardware limits remain explicit.

The worker's completed frozen run reached all 38 scenarios without interruption.
It recorded **844 of 853 assertion rows passing**, with eight failed upload
uncertainty assertions and one invalid-scene focus failure. Repeated startup
and health rows are included in these counts. No page exceptions or unexpected
console/network errors were recorded. This is a retained failing baseline,
not acceptance of root's newer application. Report and cleanup evidence are at
`/tmp/tablet-wall-acceptance-6470f24-all/REPORT.md` and `cleanup-audit.json`.
The final worker driver passed 16 focused tests and Ruff.

After integration, root reproduced the empty-scene keyboard failure with the
portable `native-keyboard` scenario. The existing validation now focuses Scene
name after refusing an empty submission, matching arrangement validation. The
fresh rerun passed **18 checks**, including sequential native Tab, both reorder
boundaries, modal containment and Escape return. The original failure remains at
`/tmp/tablet-wall-root-scene-focus-before-20261102`; correction evidence is at
`/tmp/tablet-wall-root-scene-focus-after-20261102`. Issue #28 tracks the defect.

The narrow task navigation now sizes buttons by their labels and wraps whole
buttons when space requires it. This removes the isolated final-letter wrap in
Settings at 320px while preserving enlarged-text reflow. Root's responsive
verification and combined all-scenario acceptance are recorded separately after
completion. All 27 Node test files still pass. Full aggregate acceptance is
intentionally false while the documented native/hardware gates remain unrun;
software completion is reported independently from those limits.


The focused root responsive rerun passed **279 checks**, including normal 320px,
200% text/CSS-zoom emulation, desktop/phone boundaries, contrast and font fallback.
Root inspected the 320px viewport and confirmed Settings stays on one line.
Evidence is at `/tmp/tablet-wall-root-nav-responsive-20261102`. The integrated
portable driver safety selection passes **16 Python tests** with one existing
deprecation warning; Ruff passes on all seven driver/test files. These focused
runs record the modified source hashes. The following complete run uses a clean
committed application and is the final software acceptance candidate.


## Complete candidate software matrix

The clean `3994d21` candidate completed all **38 software scenarios and 853
assertion rows**, with no interruptions, failed product assertions, page
exceptions or unexpected console/network failures. `software_complete` and
`pass` are true; `acceptance_complete` remains false for the native/hardware
limits. The runner's exit 1 is intentional. The matching external generated
Caddy proof is verified. See [VERIFICATION.md](VERIFICATION.md) for scope and
reproduction commands.

Root audited exact loaded driver copies, candidate hashes and cleanup across
all runs. All **39 server launches, 206 contexts and 461 recorded browser PIDs**
were stopped/closed, private data removed, and no owned port or process remained.
The audit and script are retained in
`/tmp/tablet-wall-combined-final-20261102/root-cleanup-audit.json` and
`root-audit.py`. Root inspected current combined desktop, 320px and enlarged
client recovery screenshots.

The corrected broad test wrapper passes **1,830 Python tests**, all **27 Node
files**, production Ruff and mypy. Its first attempt hid installed Playwright
browsers with private XDG cache and failed seven launches; that log is retained.
The passing rerun exposes the existing browser cache without changing display
settings or installing anything. Full logs are at
`/tmp/tablet-wall-final-suite-krq8zc44/`. Application/scenario bytes were unchanged;
one report-description file was modified while the rerun completed.

The final review quota interruption leaves terminal independent approval open.
Two software coverage descriptions were clarified afterward so PASS labels do
not include unrun native IME/AT or browser zoom. Original results and executed
driver copies remain untouched; `coverage-label-clarification.json` records
identical scenario membership/statuses and retained environment limits. Three
focused proof/report tests and Ruff pass after that reporting-only change.


## Final independent software approval

The fresh Codex Work Sol High reviewer completed its terminal review at exact
`819141e0b7f78c70ba6b460b579658166de448ef` with **PASS for the FINAL SCOPED
SOFTWARE GATE**, no new proven product findings. It independently audited root's
38-scenario/853-row aggregate, application and loaded-driver identity, all 206
trace archives, scoped fault classification and cleanup. Fresh reviewer checks
passed **312 Python tests, all 27 Node files and 217 rendered rows across 11
scenarios**. These counts repeat feature coverage rather than adding distinct
requirements to the complete matrix.

The report and cleanup evidence are at
`/tmp/tablet-wall-final-review-819141e-8fff4omp/REPORT.md` and
`cleanup-audit.json`. The reviewer verified that the approved candidate's only
differences from fully executed `3994d21` are documentation and two reporting
labels; application, scenarios and assertions are unchanged. All owned reviewer
resources are closed and its checkout remains unchanged.

This final documentation follow-up records the verdict without changing any
code or test. PR #29 is stacked on readiness PR #21. Software is approved for a
supervised images-only trial; native zoom/IME/AT and real-device/deployment/soak
gates remain unrun. Nothing is merged or deployed by this work. The earlier
quota-interrupted local PASS is retained as partial history, not the basis of
this terminal approval.
