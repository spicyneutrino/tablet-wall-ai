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
The upload package alone does not establish those results. No live
deployment, real tablet, hotspot/firewall, optical continuity, sleep, TLS or video
acceptance is claimed.
