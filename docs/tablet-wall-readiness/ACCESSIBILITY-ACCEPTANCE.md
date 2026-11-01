# TWR-14 accessibility acceptance

## Parent correction and repeat

The parent corrected both focus defects below. Tablet actions restore the
previous usable control after busy rendering, or the selected tablet row when
that control is no longer available. Saved-layout deletion moves focus to a
surviving neighbouring row action, or to the name field when the list is empty.
Focus already moved to another control is retained.

The unchanged runner then passed **82 of 82 checks**, including both previously
failing focus checks, at
`readiness-program/final-qa/20261101-accessibility-root-fixed/`. No unexpected
console/network errors remained; private data was removed and owned processes
stopped. Minimum sampled contrast remains 4.5174534575546:1. The run started at
`a3ae097` with the two focus changes uncommitted; those exact source edits are
recorded in the parent correction commit. Independent recheck of that commit
remains required. Original failures and limits are retained below.

## Original independent run at `b8a07fa`

TWR-14 A3 remains open. The actual application loses keyboard focus after two
successful destructive actions. A4 and the bounded A5 checks pass in the
recorded desktop and phone matrix. This is software evidence, not a WCAG
conformance claim or a screen-reader certification.

## Proven defects

1. **P2, Remove from wall loses focus.** Select a participating tablet in
   Tablets, focus Remove from wall, press Enter, and accept the native
   confirmation. The real layout update succeeds, but `document.activeElement`
   becomes `BODY`. `operator-devices.js` runs the action through `run`, which
   renders busy controls disabled. After removal, the selected tablet's Remove
   control remains disabled because it has no slot. There is no focus transfer
   to the retained tablet selector or action heading. Evidence is the
   `focus after remove` check and `remove-focus.png`.
2. **P2, Delete saved arrangement loses focus.** Save a committed arrangement,
   focus its Delete button, press Enter, and accept the native confirmation.
   The DELETE succeeds and the row disappears, leaving focus on `BODY`.
   `physical.js` clears/rebuilds the saved list in `renderSavedLayouts` after
   `deleteLayout`; neither path assigns a surviving focus target. Evidence is
   `focus after snapshot delete` and `delete-focus.png`.

Both findings reproduce across multiple private runs on application
`b8a07fa40ecfb111b55458859f8c4172f85f2d9e`, which includes the `0cc4cec` reorder
boundary correction and the `f2a8c5f` canonical-pattern correction. The runner
returns nonzero for these failures. Production files were not patched. Branch is
`t3/twr14-accessibility-acceptance`.

The final run records **80 passing checks and two failing checks**. The
minimum measured text contrast is **4.5174534575546:1** across the sampled
normal-text states. Error, warning, info and success colours are represented.
The exact driver SHA-256 is
`df74e74d72f7918068e5acd7d47ebe0e047a56ef7e2641a5056ab32f19d92ae9`.

## Acceptance map

| Requirement | Actual probe and result |
| --- | --- |
| A3 reorder | Enter on Move earlier from second to first and Move later from penultimate to last retains an enabled direction button. Pass. |
| A3 nudge/apply/cancel | Real measured arrangement, ArrowRight on selected stage slot creates a draft; Enter on Cancel clears it. Logical Preview/Cancel and Enter on Apply commit through real routes. Cross-kind Apply explicitly accepts the native confirmation. Pass. |
| A3 tabs/dialogs | ArrowRight changes the selected task tab. Native Remove, Delete, model and cross-kind confirmations are accepted by a registered dialog handler. Pass for these dialogs. |
| A3 reconcile/roster | Focused label input survives a 16-second wait covering the 15-second reconciliation interval and an actual fifth-client registration. Pass. |
| A3 delete | Remove and snapshot Delete lose focus. Fail as described above. |
| A3 announced errors | Invalid grid rows and invalid calibration viewport generate real text in existing polite live regions. DOM announcement wiring is checked; no speech-output claim. |
| A4 | 1600×1000 and 390×844, separately normal size, CSS zoom 2, and root font size 200%. Each real Wall, Tablets and System tab is inspected separately. Apply, health and visible selected action name retain nonzero boxes and no horizontal clipping; document has no horizontal overflow. Long Unicode label is saved through the actual UI. Pass. Phone requires normal vertical scrolling. |
| A4 reduced motion | Operator context uses `reduced_motion=reduce`; media query is verified and screenshots capture that state. No physical motion or vestibular-user study is claimed. |
| A5 contrast | Enabled primary action, health warning, chip, hints, status, readiness and actual calibration error text are sampled from computed styles. RGBA backgrounds are composited from the white canvas through every ancestor; text alpha is composited against that result. Every supported sample must reach 4.5:1, or 3:1 for large text. Background images or ancestor opacity cause a failure rather than an invented ratio. |
| A5 names/state | Visible native controls, ARIA buttons and tabs are checked for visible text, associated labels or ARIA naming references across tabs, with no unnamed controls found. Health includes readable state and action text. This is a bounded naming check, not exhaustive accessible-name algorithm validation. |
| Console/network | No unexpected operator console warnings/errors, page exceptions, failed requests or HTTP errors in the completed acceptance run. All application routes and sockets are real; no route stubs. |

Disabled controls, decorative `aria-hidden` content and SVG strokes are excluded
from text-contrast thresholds. Raster images, stage imagery, focus-ring contrast,
and every possible server error/state are outside this text sample. System's
missing-private-assets refresh is retained as an observation; it reports
readiness successfully and is not claimed as an error-state test.

## Runner and evidence

The portable runner is `simulator/browser/operator_accessibility.py`. It derives
the repository root from its file, starts Uvicorn with `sys.executable`, removes
inherited `TABLET_WALL*` and `WALL*` variables, chooses an unused loopback port,
and uses a temporary database, assets, media and backups. Four private Chromium
contexts run the shipped tablet client at 1024×768 CSS px and DPR 2. Operator
screenshots use DPR 1. A fifth private client tests roster changes and is then
forgotten through the UI. Model dimensions remain approximate software inputs.

Each `--artifacts` directory must be new. Browser closure and server termination
run in `finally`; an exit stack stops the server before temporary-data cleanup; server shutdown escalates to kill after ten seconds. Each
state wait is bounded to 25 seconds, the intentional reconciliation wait is
16 seconds, and browser operations have a five-second timeout. Data directories
are removed. The final artifact records `private_data_removed: true`; the
recorded Uvicorn PID was checked absent after completion. Earlier owned
temporary directories left by the cleanup-order race were also removed. No live installation, external services, pushes or production
edits are involved.

Command used from the worktree root:

```sh
rtk proxy /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python simulator/browser/operator_accessibility.py --artifacts /var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101-accessibility-final-evidence
```

Use any environment containing the application's dependencies and Playwright;
the runner contains no hardcoded interpreter, browser executable or checkout.
The named interpreter above supplies this workspace's installed dependencies.

Artifacts are in
`/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101-accessibility-final-evidence/`.
`results.json` records exact app SHA, driver SHA-256, command, isolated data path,
individual checks, failures, contrast foreground/background samples, console and
network records. PNGs retain desktop/phone normal, zoom, root-text, enabled Apply,
and error states, plus the two deletion failures. The earlier complete runs are retained in `20261101-accessibility-complete`
and `20261101-accessibility-cleanup-verified`.
Earlier runs remain under
`/tmp/twr-accessibility-{first,second,third,fourth,fifth}` and durable sibling
directories `20261101-accessibility-final`, `20261101-accessibility-dpr2`, and
`20261101-accessibility-acceptance`. These include driver errors from an incorrect
logical confirmation expectation, wrong selected-name target, trailing label
whitespace, and Preserve orientation without existing physical mounts. They
are not counted as additional product defects. The earlier complete run also
revealed a harness cleanup-order race that could recreate temporary files
before server termination. The final runner stops the server before removing
data and records the removal result.

Browser-harness doctor found Chrome running but no daemon or active connection.
Chrome DevTools MCP reported missing `/opt/google/chrome/chrome`. Playwright MCP
reported missing `chromium-1252/chrome-linux64/chrome`. The explicitly authorized
private Python Playwright fallback supplied all rendered evidence. Desktop and
phone screenshots were visually inspected; the phone zoom view wraps into a
long vertically scrolling page without horizontal overflow.

Focused validation uses `python -m ruff check
simulator/browser/operator_accessibility.py`, `python -m py_compile
simulator/browser/operator_accessibility.py`, and the actual runner. The first
two pass; the browser runner intentionally exits 1 while either focus defect
remains. The runner uses programmatic focus before keyboard activation to target
each control; this is not a claim of an uninterrupted Tab-only full journey.
Hardware accuracy, OS sleep, radios, optical synchronisation, assistive-technology
speech output and full WCAG coverage remain unverified. Feature/upload/restore
acceptance belongs to the separate feature runner.
