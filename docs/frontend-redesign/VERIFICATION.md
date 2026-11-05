# Frontend redesign verification

## Operator workflow follow-up

The [operator simplification record](OPERATOR-SIMPLICITY.md) covers the later
workflow changes reviewed at `ff1f4b7`. The results below belong to the earlier
redesign candidates named in each section. They are not reruns of the later
source. PR #29 has since merged into `main`; its earlier stacked status below
is part of the historical record.

## Candidate and scope

The executed application candidate is `3994d2191a7513f80e130efab9764c6b3538678b`
on `work/tablet-wall-frontend-redesign`. The complete browser run used a clean
checkout. Subsequent changes clarify two report labels and documentation; they
change no application, scenario, assertion or coverage status.

The operator now uses one workspace for Tablets, Arrange, Images, Saved and
Settings. `/controller/` forwards there with query and fragment retained. The
old editor is reachable only through explicit Experimental controls. Geometry
and image changes retain separate Apply arrangement and Show image actions.
Saved arrangements remain geometry; saved scenes remain content.

This is images-only software acceptance for a supervised trial. It is not a
physical-wall, unattended-operation, video or accessibility-conformance claim.

## Executed software results

| Check | Result | Evidence on development machine |
| --- | --- | --- |
| Complete actual-client matrix | 38 isolated scenarios, 853 assertion rows, all passing, no interruptions | `/tmp/tablet-wall-combined-final-20261102/results.json` |
| Source and cleanup audit | Pass; matching loaded driver copies and candidate identity in every run; 39 server launches, 206 contexts and 461 recorded browser PIDs checked | Same directory, `root-cleanup-audit.json` and `root-audit.py` |
| Full Python suite | 1,830 passed, three existing deprecation warnings | `/tmp/tablet-wall-final-suite-krq8zc44/pytest-rerun.xml` and `pytest-rerun.log` |
| JavaScript | All 27 Node test files pass | Same directory, `node-rerun.json` |
| Production lint/types | Ruff and mypy pass | Same directory, `ruff-rerun.log`, `mypy-rerun.log`, `results-rerun.json` |
| Exact ingress | Source-matched generated Caddy proof; direct upload 201, 127 tablet denials, icon GET/HEAD 200, forbidden methods/suffixes 403 | `/tmp/tablet-wall-upload-fix-6eadvom6/pytest-rerun/test_generated_hotspot_ingress0/ingress-manifest.json` |
| Report-label clarification | Three focused reporting/proof tests pass; requirement-to-scenario mapping and all statuses unchanged | Complete matrix directory, `coverage-label-clarification.json` |

Assertion counts include repeated startup and health checks. They do not count
unique features or measure human usability. Each client is a separate disposable
browser storage context running the shipped client, with real registration,
sockets, image loading and exact render acknowledgement tokens. Synthetic device
signatures and response-fault injections are labelled fixtures.

The matrix covers joining after the operator opens; explicit model groups;
1×4/2×2 review and apply; pointer/snap/keyboard geometry; Fit/Fill and real PNG/JPEG
uploads; current/stale/failed paint; offline/reconnect and private restart;
keyed field retention; stale authority and guarded commands; saved arrangements
and scenes; exact replacement/Forget guards; native Tab/modal/validation focus;
loading/error/empty/thumbnail states; and desktop/phone text/contrast samples.

The upload deadline case waited for the real 120-second XHR deadline. The
postpublication cases forward real selected bytes to an upstream 201 before
replacing its response with 503 or unreadable 201. They prove that retry stays
blocked until a later successful inventory refresh and that uploads never Show.

The full runner intentionally exits 1 while native/hardware requirements are
open. The recorded fields are `pass: true`, `software_complete: true`, and
`acceptance_complete: false`. Inspect those fields with `mandatory_uncovered`;
do not reinterpret the exit code as a software assertion failure or alter it to
claim hardware acceptance. Reporting-only clarification removes native IME/AT
and native zoom from two software PASS descriptions. Original executed results
and loaded driver bytes are preserved.

## Independent review

The completed independent review at `295cb61` remains ISSUES. It verified the
three earlier command/draft defects closed, then found upload-response ambiguity
and the favicon HEAD gap. Its report is
`/tmp/tablet-wall-final-independent-3tap37yn/REPORT.md`.

The expanded tester's frozen-app run remains 844/853 passing on `6470f24` against
application `295cb61`. Its nine failures are retained in
`/tmp/tablet-wall-acceptance-6470f24-all/REPORT.md`. Root corrected the upload and
icon findings in `37d1edc`, then validation focus and narrow navigation in
`3994d21`; the complete combined matrix above passes those paths.

A reviewer produced a local report for `3994d21` but hit a provider usage
limit before its final handoff. It repeated reused probes after discovering that
Chromium had inherited session XDG settings. That unfinished report at
`/tmp/tablet-wall-review-3994d21-dwisq7sx/REPORT.md` is not substituted for terminal
approval, and its older counts are not promoted to isolated current evidence.

A fresh independent Codex Work Sol High review completed with **PASS for the
FINAL SCOPED SOFTWARE GATE** at exact
`819141e0b7f78c70ba6b460b579658166de448ef`. It found no new proven product issue.
Its fresh verification passed **312 Python tests, all 27 Node files and 217
rendered assertion rows across 11 scenarios**. Separately, it audited every run
of the complete 38-scenario matrix, exact application/loaded-driver identity,
206 trace archives, failure classification and cleanup. These fresh review
counts overlap the full matrix's feature coverage; they are not additive unique
requirements. The review confirmed the candidate differs from executed
`3994d21` only in four documentation files and two report-description strings.

The terminal report is
`/tmp/tablet-wall-final-review-819141e-8fff4omp/REPORT.md`, with source, aggregate
and cleanup audits beside it. All owned reviewer resources closed. The final
follow-up commit records this approval only; it changes no application, driver,
scenario or assertion. Approval covers the images-only workspace for a supervised
trial. Native/hardware gates remain open. PR #29 is stacked on #21, unmerged and
undeployed; no GitHub human approval is implied by the agent review.

## Reproduce safely

Use a new artifact path and a generated-ingress manifest matching the checkout:

```sh
rtk proxy .venv/bin/python simulator/browser/redesign_acceptance.py \
  --artifacts /tmp/tablet-wall-redesign-NEW --scenario all \
  --ingress-proof /absolute/path/to/ingress-manifest.json
```

Never use a live wall database or library. The driver creates private paths,
reserves its loopback listener, refuses existing artifact directories, and stops
owned children in cleanup. For a full test suite with private XDG directories,
set `PLAYWRIGHT_BROWSERS_PATH` to the existing browser installation so cache
isolation does not hide it. This does not authorize browser installation or
attachment to a user profile.

The first broad root test wrapper omitted that browser path and failed seven
launches, with 1,823 tests passing. That log remains at `pytest.log` beside the
passing rerun. The rerun records one report-only file modified during execution;
application bytes and executed scenario logic remained the candidate's bytes.
Three focused tests and Ruff verify the later reporting-label change. No failing
result was edited into a pass.

## Remaining native and hardware gates

- Native browser-menu 200%/400% zoom, operating-system IME and screen-reader
  smoke remain unrun. Text enlargement, CSS zoom and CDP page scaling are
  explicitly emulated evidence. Native Tab/Enter/Escape tests do run.
- Actual tablet mapping, physical panel/model identity, bezel/mount continuity,
  optical accuracy, screen sleep/wake, touch keyboard and nonzero visual-viewport
  panning require real-device trials. Approximate model profiles retain their
  provisional uncertainty.
- Real hotspot/network changes, TLS deployment, host reboot, prolonged soak and
  video remain unverified or outside this redesign. Existing hardware trial
  instructions remain the path for those checks.

Both global browser MCPs lacked their configured binaries. Browser-harness
reported a dead daemon and zero connections. Root inspected the session and
used the authorized private Python Playwright fallback with cached Chromium
143.0.7499.4. DISPLAY/Wayland settings and the user browser were left unchanged.
No live wall data, service, hotspot or firewall was modified during acceptance.
The earlier shared Caddy autosave side effect and its isolation correction remain
recorded in IMPLEMENTATION.md; they are not erased by later isolated passes.
