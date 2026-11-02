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

Visual styling, compatibility entry retirement, combined in-app upload checks, the portable four-client journey,
responsive and accessibility verification, and independent final review remain
open. The upload package alone does not establish any of those results. No live
deployment, real tablet, hotspot/firewall, optical continuity, sleep, TLS or video
acceptance is claimed.
