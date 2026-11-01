# Feature acceptance record: TWR-04/05/06/08/09/10/11/13

## Parent correction and passing repeat

The parent fixed both reported UI mismatches. Model suggestions now come from
`runtime.devices[id].model_suggestions`, filtered against the received model
catalogue, rather than repeating the signature algorithm over telemetry omitted
from the runtime projection. The still-image file picker now advertises JPEG
and PNG. Forcing unsupported WebP through the browser automation still tests the
server's readable rejection and unchanged layout.

The portable driver then passed **183 checks, zero failures and zero findings**
at `readiness-program/final-evidence/acceptance-root-fixed/`. Its driver SHA-256
is `d016d76047d45213fd2822486c02e23c53fafdb55983fd436824c0d0ad9c48b0`.
It started at `c3dab2b` with the two production fixes uncommitted; the exact source
edits are recorded in the parent correction commit. The model prompt was visually
inspected, as was successful upload state. A bounded wait now allows the actual
model suggestion to arrive after registration. Unsupported upload advertising is
asserted explicitly. Source and driver changes require the final independent
review before programme software completion. Original evidence and failures are
retained below.

## Original independent run at `0cc4cec`

## What this record is

This is the rerunnable, private-loopback acceptance evidence requested after the
2026-11-01 audit at `0529eaa` found bounded gaps in the rendered assertions. It
does not replace TWR-17 hardware evidence, the independent accessibility review,
the retained 106-check integrated journey, or the measured efficiency baseline.

The driver is `simulator/browser/readiness_acceptance.py`. It is self-contained:
it derives the repository root from its own file, uses `sys.executable` for the
private server and backup tools, strips inherited `TABLET_WALL*` and `WALL_*`
environment variables, allocates free loopback ports, writes only below its
`--artifacts` directory, and stops every server and browser in `finally`.

## Run identity

| Field | Value |
| --- | --- |
| Application under test | `0cc4cecb2b35ea416717f77d207d0ac68efbbe1c` (`t3/readiness-acceptance-audit`) |
| Driver | `simulator/browser/readiness_acceptance.py` |
| Driver SHA-256 | `64fc57b36d28d64d4a12ba1a54a4ea8fae1980d9854793f591cbb61ac3f947d8` |
| Command | `.venv/bin/python simulator/browser/readiness_acceptance.py --artifacts <fresh directory>` |
| Artifact directory | `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-evidence/acceptance-20261101T151304Z` |
| Started / finished (UTC) | `2026-11-01T15:13:04Z` / `2026-11-01T15:13:55Z` |
| Result | **180 passing checks, 1 acceptance failure, 2 findings** |
| Retained failure | TWR-11 A1 rendered model suggestion (product gap, not a harness error) |
| Browser | Playwright Chromium `143.0.7499.4` |
| Tablets | Four Android User-Agent contexts at 900 x 1280 CSS, DPR 2, `screen.orientation.angle` 270; a fifth Android context is the replacement registration |
| Operator | 1600 x 1000, plus a 390 x 844 screenshot of the Fit state |
| Data | Private temporary database, assets, media, backups, and a restored copy on free loopback ports |

The driver and this document were committed after the run. The application code
served in the run is the `0cc4cec` tree; no production source was changed.

## Method

One private Uvicorn process served the checked-out tree over loopback with
temporary data paths. Four real Chromium contexts registered as tablets through
the shipped client, provided real viewports, opened real WebSockets, decoded
real images, and returned real `render_ack` evidence. The operator page was the
shipped `physical.html` with the shipped scripts. Layout, scene and lifecycle changes used the actual UI. Filesystem writes
created test images before startup and exercised the documented backup/restore
tools. The direct legacy write probe was required to be refused without mutation.
No backend fixture stood in for a route.

The screenshots below are in the artifact directory's `screenshots/` directory.
The `results.json` file records every check, the two findings, the application
SHA, the driver SHA, the exact command, the environment, and the limits. The
`transcript.jsonl` file records every server start/stop and every backup,
verify, restore, and restored-boot command with its exit code and stdout/stderr
tails.

There were no operator page exceptions and no tablet page exceptions. The only
failed operator requests were navigation aborts and three connection refusals
while the private server was intentionally stopped for the label restart and the
upload restart. The filtered `failed_requests` list is empty; `failed_requests_raw`
retains all of them.

## Acceptance results

### TWR-04: still-image control, library, and legacy fence

| Item | Result | Evidence |
| --- | --- | --- |
| A1 image A then B, console names B with its crop, tablets receive B, reload shows B | **Pass** | A = `first.png` 2000 x 1400, B = `marked.png` 2000 x 1000. The console named B with `Fit whole image` and the source size, all four tablets confirmed B, and a reload still named B and showed B. Screenshots `06-image-b.png`, `09-fit-*.png`, `10-fill-*.png`. |
| A2 colour, Blank wall, restore prior image without losing layout | **Pass** | The colour scene switched the client to its colour surface; Restore returned to B; Black wall committed and painted a generated image; each step kept the layout object byte-identical. Screenshot `19-runbook-black.png` and the check log. |
| A3 uploads disabled instruction and form state | **Pass** on the disabled startup | `Uploads are off` copy-to-folder instruction shown; `#upload-form` hidden. |
| A3 loopback upload progress, rejection, unchanged layout | **Pass**, with one minor finding | A real 1200 x 800 PNG entered through the actual file input, the progress element became visible, the message named the PNG, and the inventory grew. `text/plain` was rejected with `only image/jpeg, image/png, ...`. Both outcomes left the layout unchanged. Screenshots `16-upload-success.png`, `17-upload-rejected.png`. |
| A4 experimental playback hidden, opt-in, second confirmation | **Pass** | Controls and the top bar transport were hidden before opt-in; the switch revealed the rail controls; Start raised `Start experimental playback? ... not validated`; a dismiss produced no POST to `/api/v3/playback` and the state stayed `stopped`. The visible copy says software evidence only and not validated on tablets. |
| A5 legacy guard on a physical wall | **Pass** | `/controller/` showed the measured-layout, read-only banner, hid the editing workspace, and `PUT /wall` returned 409 `Upgrade controller`. Screenshot `07-legacy-guard.png`. |

The advertised `image/webp` file-picker type is rejected by the server. See the
minor finding below.

### TWR-05: whole-image fit and truthful crop

| Item | Result | Evidence |
| --- | --- | --- |
| A1 marked border under Fit on a 1 x 4 wall; Fill crops predictably | **Pass** | `marked.png` has a 40 px magenta border. Under Fit the client model placed the left and right border bands inside the outer slices, and the sampled screenshots contained the border on tablets 1 and 4 and none on the interior slices. Under Fill the model predicted `Fill crops 0% of the source width and 32% of its height`, the visible text matched that arithmetic, and no slice contained the border. Screenshots `09-fit-*.png`, `10-fill-*.png`. |
| A2 contain accepted, persisted, rendered identically | **Pass** | Scene readback carried `contain`; the console and the three mounted states agreed; the letterbox and interior pixels matched the fit model. |
| A3 preview geometry within one logical unit | Covered by the existing fixture test | `tests/operator_state.test.js` compares the operator transform with `frontend/client/view.js`; this browser run re-used the same shipped transform for its sampling instead of duplicating the fixture. |
| A4 off-wall crop versus bezel/gap occlusion, text and visual treatment | **Pass** | The fit note separates `Bezels and gaps still hide image areas` from the one wall-wide transform; the stage note says `Hatching marks hidden bezels and gaps. Fill may also crop source edges outside the wall.`; the stage legend has separate body and active-panel entries; the SVG carries the `operator-occlusion` hatch pattern and the panel clip. The client transform showed the top and bottom source borders behind the measured bezel, which is occlusion, not a crop. |
| A5 2000 px source resolution estimate and warning | **Pass** | The visible estimate read `≈611 source px across for 1800 output px` for each tablet and `Estimated upscaling up to 2.9×`; both values were recomputed from the shipped `OperatorState.fitTransform` and the committed profiles. Screenshot `08-fit-resolution.png`. |
| A6 changing layout or fit keeps the other | Covered by the grid and image checks in this run | The 1 x 4 and 2 x 2 applies preserved the image; the Fit and Fill changes preserved the arrangement. |

### TWR-06: render evidence and targeted retry

| Item | Result | Evidence |
| --- | --- | --- |
| A1 one induced image failure; card names device and reason; not counted | **Pass** | An aborted asset fetch on tablet 3 produced `3 of 4 showing · 1 failed`; the selected failure card named `#3` and `Image failed · fetch`; Retry returned `4 of 4 showing`. Screenshot `12-image-failure.png`. |
| A8 denominator and empty wall | **Pass** | A fresh startup read `No tablets on the wall.` on the stage and in the header. Closing tablet 4 produced `3 of 4 showing · 1 offline`; reopening it returned `4 of 4 showing`. |

### TWR-08: labels, Identify, lifecycle

| Item | Result | Evidence |
| --- | --- | --- |
| A1 label survives restart and reconnect; appears in list, card, and saved references | **Pass** | `North panel α` survived a real backend restart and socket reconnect, appeared in the tablet list and selected card, and the saved `Portrait row` arrangement still referenced the same identity and recalled with the label. Screenshot `16-upload-success.png` shows the label on the stage. |
| A2 Identify correct number and name within 1 s; revision unchanged; expires | **Pass** | `#identify-number` read `#2`, `#identify-label` read `North panel α`, click-to-visible-overlay was **0.174 s** on loopback, the wall revision did not change, and the overlay cleared on expiry. This is a loopback DOM timing observation, not a hardware claim. Screenshot `13-identify.png`. |
| A3 Remove, A4 Forget, A5 online refusal, A6 history retention | Retained from the 106-check journey | `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101T120950Z/` records Remove, offline Forget after acknowledgement and re-registration. Focused operator/lifecycle tests cover online refusal and history retention. This run did not repeat them. |

### TWR-09: rebind preview and return points

| Item | Result | Evidence |
| --- | --- | --- |
| A1 preview lists affected arrangements, conflicts, label/number, revision maps; writes nothing | **Pass** | The preview read `Preview only.`, named both identities, printed `Profile revision map` and `calibration map`, and printed `Label after` and `number after`. The config revision and layout were unchanged; the roster, replacement registration, and active placement were untouched. Screenshot `14-rebind-preview.png`. |
| A5 both cross-kind directions create a named return point; refusal if it cannot | **Pass** for the created-copy direction | The physical to logical Apply named `Before logical <hex>`; the logical to physical recall announced `Previous arrangement saved as “Before physical <hex>”`. Both names were retrievable from `GET /layouts`. |
| A6 response/confirmation names the generated return point; automatic copy is labelled | **Pass** | The messages and announcement named the generated names; the `Before ...` prefix is self-labelling. Screenshot `15-viewport-fence.png` shows the recall announcement and saved return point. |
| A2 transactional apply, A3 recall after same-hardware rebind, A4 different-hardware refusal | Retained from the 106-check journey and its focused transaction tests | The final journey records replacement preview and apply, then recall of both saved kinds with the new identity. `tests/test_layout_transitions.py` and `tests/test_device_lifecycle.py` record rollback, conflicts, and refusal. |

### TWR-10: atomic 2 x 2 and 1 x 4

| Item | Result | Evidence |
| --- | --- | --- |
| A1 four connected tablets apply 2 x 2 in number order with one revision increment and one broadcast | **Pass** for revision and order; broadcast **referenced** | Revision went 0 to 1 exactly once, and #1..#4 occupied row-major positions. The route-level broadcast result is not re-measured here; `docs/tablet-wall-readiness/EFFICIENCY.md` records the atomic-grid route and the one-broadcast outcome, and the brief directed this run to reference it rather than invent a browser broadcast metric. |
| A2 1 x 4 in number order, one row, explicit orientation, mount angle not hard-coded | **Pass** | The physical 1 x 4 applied in one revision (1 to 2), one measured row, left-to-right #1..#4, with explicit `0°` mount angles and pinned profile and calibration revisions. Screenshot `05-physical-1x4.png`. |
| A5 preview changes nothing; Apply failure leaves the prior arrangement; Cancel changes nothing | Preview and Apply are exercised; failure and Cancel retained from the 106-check journey | The preview was labelled before Apply and the cross-kind confirmation named the safety copy. The portable accessibility runner exercises keyboard Cancel. Focused grid and transition tests cover failed-write rollback; the final journey’s injected failure is an image failure, not a failed layout write. |
| A3 width arithmetic, A4 manual adds, A6 release guard, A7 empty draft, A8 offline reservations, A9 keyboard | Retained from the 106-check journey and focused grid tests | `tests/test_grid.py`, `tests/test_geometry.py`, and the final journey record these cases. |

### TWR-11: calibration provenance, pinned health, test grid

| Item | Result | Evidence |
| --- | --- | --- |
| A1 new signature match shows `Looks like X. Confirm?` before physical scale | **FAIL** | The server reported `model_suggestions: ["google-pixel-c"]` for the new tablet, but the rendered `#tablet-model-status` read `Unknown screen signature.` and the profile and calibration lists were still empty. Confirmations still worked through the explicit model picker, so the rest of the run proceeded. This is a product gap, detailed below. Screenshot `02-model-status.png`. |
| A2 model provenance is approximate, ±3 mm, never plain ok | **Pass** | Every profile recorded `tablet-model`; every model calibration recorded `tablet-model approximate` and `±3.0 mm`; every health record had `ok: false`, `approximate: true`, `confirmed: true`; the card said `No physical accuracy is claimed.` Screenshot `02-model-provenance.png`. |
| A3 pinned slot health uses the pinned pair | **Pass** | Every physical slot mapped with its pinned profile and calibration and reached `ready`; the health records identified the model snapshot rather than substituting the latest pair. |
| A4 viewport/orientation/zoom/launch-mode mismatch fences and recovers | **Pass** | Changing tablet 1 from 900 x 1280 to 1200 x 1300 produced `The live viewport 1200.0x1300.0 CSS px exceeds the model's 900.0x1280.0 native panel` and `Clear browser zoom/scale, use the native screen size, or take a fresh measurement.` The card repeated the fence; restoring 900 x 1280 cleared it and repainted. Screenshot `15-viewport-fence.png`. |
| A5 test grid on a physical wall without a shell copy | **Pass** | Black wall used the same generated-image path; the backup drill later included the generated asset. The 106-check extra run already records the wall-sized 50 mm grid. |
| A6 logical calibration scene remains logical-only | Covered by the existing checks | The logical calibration button is disabled in physical mode; `tests/operator_state.test.js` and the 106-check journey record this. |

### TWR-13: readiness, health, and the recovery runbook

| Item | Result | Evidence |
| --- | --- | --- |
| A4 one fresh-operator sequence start, health, Black wall, stop, backup, verify, restore to new paths, boot restored copy | **Pass** | `transcript.jsonl` records the private start, `/healthz`, the Black wall step, the stop, `deploy/backup.py backup` exit 0, `verify` exit 0, `restore` into new paths exit 0, and the restored boot. The restored copy preserved the scene, arrangement, labels, numbers, and byte-identical generated content. |
| A5 backup includes referenced content and names what is excluded | **Pass** for the referenced generated image | The manifest references the actual Black wall asset and verify exits 0. The managed-media omission behavior is covered by `deploy/drill.py` and `tests/test_backup.py`; this run's snapshot had no unused managed media. |
| A1 preflight, A2 `/healthz` schema and no path leak | **Pass** | `/healthz` answered 200 with `schema`, `generation`, `revision`, `counts`, and `storage_readable`; the body contained neither the asset path nor the data path. |
| A3 log rotation, A6 headers/CSP, A7 kiosk checklist | Covered by existing focused tests | Not repeated here. |

## Original product gap, corrected in parent: TWR-11 A1 suggestion is not rendered

The server has the signature match and exposes it in `runtime.devices[id].model_suggestions`.
The console does not use that field. `frontend/controller/physical.js` renders
`#tablet-model-status` from `state.roster[id].screen_width`, `screen_height`,
`screen_dpr`, and `platform_family`. The `device_updated` frame carries those raw
fields, but the `config_updated` reconcile in `frontend/controller/physical.js`
replaces `state.roster` with the configuration projection, which omits them.
The result is the captured state:

- server: `model_suggestions: ["google-pixel-c"]`
- rendered: `Unknown screen signature.`
- profile and calibration before confirmation: absent

The same result occurred in every fresh acceptance run that reached this check
and in a minimal probe. The explicit model picker still works, which is why the
rest of TWR-11 passes, but the required suggestion-before-confirmation step does
not.

This record did not change production code. A fix should either merge the raw
telemetry from `/devices` or render the suggestion from the server's
`model_suggestions` field, then re-run this driver and update the check to pass.
This is not a hardware result.

## Original minor finding, corrected in parent: webp is advertised but rejected

The file input's `accept` attribute includes `image/webp`
(`frontend/controller/physical.html`), while `POST /uploads` accepts only
`image/jpeg` and `image/png` for stills and returns 415 for `image/webp`. A user
can select a type the server refuses. The rejection is readable and leaves the
layout unchanged. This is a small UI contract mismatch, not a rendering defect.

## Retained failures and prior evidence

- Final run: `acceptance-20261101T151304Z`, 180 passing checks, 1 failure (TWR-11 A1), 2 findings.
- The immediately preceding runs in the same directory retain the same single
  A1 failure. Earlier `acceptance-*` directories retain driver-correction runs
  (selection selector, colour render-state expectation, upload file path,
  playback request filter, legacy guard wait, restore empty-media directory).
  Those corrections changed the driver, not the application.
- The retained 106-check journey is
  `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101T120950Z/`
  with variant `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101T135445Z-mobile/`.
  It still supplies the full journey, rebind apply and recall, Remove and Forget,
  and the phone-width evidence not repeated here.
- The recovery extras are
  `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101T140721Z-recovery-current-token/`.
- The efficiency baseline is `docs/tablet-wall-readiness/EFFICIENCY.md`.

## Limits

- Software loopback only. No physical panel, bezel, seam, optical, sleep, battery,
  or soak measurement is claimed. TWR-17 remains open and `HARDWARE-ACCEPTANCE.md`
  is still all `Not run`.
- No TLS or proxy composition, no installed service, no host reboot, no live wall
  data, and no real firewall or hotspot change.
- The Identify timing is a click-to-visible-overlay observation on a loopback
  Chromium context. It is not a tablet timing claim.
- The model plan remains approximate at ±3 mm. No physical accuracy is claimed,
  even after explicit confirmation.
- Broadcast count is not re-measured. The atomic-grid route and one-broadcast
  result are referenced from the measured efficiency baseline.
- Accessibility (contrast, 200% zoom, keyboard focus retention) is owned by the
  separate accessibility review and is not duplicated in this driver.
- The four tablets are simulated Android Chromium contexts with the Pixel C
  signature. They exercise the shipped client, routes, sockets, and geometry, but
  they are not hardware.

## Exact commands

```bash
# From the repository root, with the project environment:
.venv/bin/python simulator/browser/readiness_acceptance.py \
  --artifacts /var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-evidence/acceptance-20261101T151304Z
```

The driver's transcript records the exact private server and tool commands,
including:

```bash
python -m uvicorn main:app --host 127.0.0.1 --port <free> --no-access-log
python deploy/backup.py backup --db <temp>/wall.db --assets <temp>/assets --media <temp>/media --dest <artifact>/backup/snapshot
python deploy/backup.py verify --src <artifact>/backup/snapshot
python deploy/backup.py restore --src <artifact>/backup/snapshot --db <artifact>/restore/wall.db --assets <artifact>/restore/assets --media <artifact>/restore/media
```

## Closing state

The run recorded 180 passing checks; the only acceptance failure was the TWR-11 A1 prompt. That failure and
the webp mismatch are reported for a production decision. The parent has now fixed A1 and repeated the driver successfully as recorded
at the top of this document. Independent review of that correction remains open. TWR-17 hardware
evidence remains missing.
