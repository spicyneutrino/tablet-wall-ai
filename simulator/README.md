# Virtual tablet simulator

A bounded, **test-only** harness that drives the real FastAPI app with
virtual tablets: 18 devices by default (15–20 supported) registering,
connecting over WebSocket, receiving per-device `wall` frames, reconnecting,
and being measured for placement/tiling/visible-rect seam geometry — against
a temporary database and asset directory, never the operator's data.

**No browser runs in the TestClient mode.** No JavaScript, no canvas, no pixels: a green run
proves what the app *sends* and what geometry *follows from the protocol* —
never what a screen would show. See [Limitations](#limitations-versus-a-real-browser).

The separate [browser runner](#run-the-isolated-browser-experiment) executes
real client JavaScript and checks canvas pixels. Both modes leave production
application code and data unchanged.

## Quick start

From the repository root:

```bash
uv run python simulator/run.py
```

Expected: a per-scenario line, then a summary, exit code `0` — meaning every
check on the wire frames and the geometry passed. That is not a rendering
check; see the limitations below before trusting a green wall.

```
tablet-wall simulator: 22 scenarios, 18 virtual tablets, work dir /tmp/tablet-wall-sim-…
  ok   01_isolation                 11/11 checks   0.05s
  …
  ok   22_sweeper                   8/8 checks   1.81s
scenarios: 23 passed, 0 failed, 0 errored of 23
checks:    1075 passed, 0 failed of 1075
duration:  8.16s
note:      no browser/canvas execution — see the limitations in the report
```

A run is deterministic in structure (stable UUID4s derived from a hash of the
slot number, fixed fleet, fixed wall geometry) and takes about 8–10 s. The
only timing that matters is bounded: every frame wait has a deadline
(`--timeout`, default 5 s), so a regression fails instead of hanging.

## Options

| Flag | Meaning |
| --- | --- |
| `--devices N` | virtual tablets, `15`–`20` (default `18`) |
| `--scenario ID` | run the sequence **up to and including** that id (repeatable); see `--list` |
| `--list` | print scenario ids and exit |
| `--report PATH` | write JSON outside the repository (`-` = stdout). Relative paths resolve from the caller's directory. **Opt-in**: a default run leaves no generated file behind |
| `--no-report` | accepted for compatibility; identical to the default (no report file) |
| `--timeout S` | deadline for any single frame wait (default `5`) |
| `--fail-fast` | stop at the first failing scenario |
| `--keep-work-dir` | keep the temporary database/asset directory |
| `--quiet` | only print the summary |

Exit codes: `0` all checks passed · `1` a check failed, a scenario errored or
never finished, a reader thread leaked, the temporary data survived, or the
repository changed · `2` usage error (bad flag, out-of-range `--devices`,
unknown or ambiguous `--scenario`).

Scenarios build on each other (later ones assume the roster, wall and
sockets earlier ones made), so `--scenario 15` runs `01`…`15` from a clean
app rather than 15 alone. Matching is explicit: an exact id
(`15_auto_tiling`), a longer unambiguous prefix (`15_auto`), or a bare
number mapped onto its zero-padded id (`15`). A prefix that matches
several ids — `2`, which prefixes `20_…`, `21_…` and `22_…` — is rejected
with exit `2` instead of being silently broadened. `--scenario 22` (or no
flag) is the full run.

## What a run exercises

| id | what it proves |
| --- | --- |
| `01_isolation` | database and asset dir are in the temporary work dir; origin fences cleared; fresh DB starts at revision 0 |
| `02_registration` | all tablets register, roster records are complete, `GET /device/{id}`, add/remove a guest |
| `03_registration_validation` | malformed id / version-1 UUID / missing field / wrong type → `422`; re-registration is idempotent |
| `04_controller_snapshot` | a v2 controller's first frame is a snapshot of the roster plus the live wall |
| `05_device_handshake` | `welcome` + immediate `wall` replay for every tablet; `4404` unknown device, `4426` bad protocol, `4400` bad id |
| `06_presence` | a controller opened later sees every tablet online; a **v1** controller gets no `wall` frame (while the v2 one beside it does) |
| `07_colour` | broadcast and single-tablet colour, `delivered` counts, normalisation, `422`/`404` |
| `08_wall_layout` | `PUT /wall` resizes, broadcasts to every fleet tablet, validates dimensions and unknown keys |
| `09_placements` | an explicit placement for every tablet, +1 revision each, per-device frame carries its own rect without `device_id`, the band tiles its rectangle |
| `10_placement_validation` | `404` unknown/malformed device, `422` degenerate rect or bezel, release is idempotent and its `wall` frame follows |
| `11_scene_colour` | content-only scene change; `422` for unknown type, image without asset, asset on colour, unknown key |
| `12_scene_calibration_caps` | calibration reaches capable tablets, others get `color`, generation/placement untouched |
| `13_scene_image` | inventory, content-id = SHA-256 of the bytes, byte re-hashing on serve, headers, per-device image descriptor vs colour downgrade, `422` unknown asset, inventory refresh on add/remove, vanished asset 404s |
| `14_snapshots` | layout/scene save and recall are independent; saves and deletes never bump the revision; recalls do; `409` duplicates, `422` names, `404` unknown; stored scene has no composed `url` |
| `15_auto_tiling` | default `columns` leaves exactly the predictable vacancy; explicit `columns` is an exact partition (sum = union = wall area, zero overlap, zero uncovered); per-device cells match an independent recomputation; seam gaps match hand-derived crops |
| `16_seam_matched` | 4:3 cells for 4:3 tablets → every seam gap and every cover crop is `0` (within 1e-9); unplaced tablets get `placement: null` |
| `17_seam_mismatch` | hand-computed crops for mismatched aspects (87.5 / 37.5 wall units) and a bezel seam of exactly 127.5 units (40 bezel + 87.5 cover crop) |
| `18_revision_generation` | six mixed mutations, +1 revision each, one generation throughout, every tablet and controller receives every revision in order and nothing extra |
| `19_reconnect` | drop → `device_offline` + roster kept + placement intact → reconnect → `welcome`, wall replay at the current revision, `device_online` (never an `offline` first), `last_seen` advanced |
| `20_socket_replacement` | the superseded socket closes with `4409`, the replacement is welcomed and replayed, controllers see only `device_online` |
| `21_restart` | new generation, revision/placements/scene persisted, roster and sockets gone (emulated process death), `4404` until re-registration, clean reconnect |
| `22_sweeper` | a heartbeat moves `last_seen`; a silenced tablet is swept with `4408` (timing constants patched in-process), controllers are told, everyone else stays up, then it reconnects |
| `23_teardown` | every reader thread stopped, temporary DB/assets deleted, **no repository file created, removed or modified** |

## How the geometry is checked

`simulator/geometry.py` re-implements PROTOCOL.md's rules as pure arithmetic —
the visible rect (`footprint − bezel`), the client's centred cover
(`scale`, `ox`, `oy`, and the wall-space window actually drawn), union/overlap
areas for a set of cells, and the gap between two neighbours' displayed
windows. Scenarios then compare those numbers against the wire in three ways:

1. **Independent recomputation** — the auto grid's cells and its uncovered
   area are recalculated from the rounded edge rules here, not read back as
   claims (default fleet: exactly `288000` wall units² left vacant by the
   default `columns`, `0` by an explicit divisor of the fleet size).
2. **Hand-derived constants** — for the default fleet in `400×400` cells:
   a 4:3 tablet crops `50` units vertically, the 16:9 kiosk `87.5` vertically,
   the portrait tablet `50` horizontally; the reported seam gaps must equal
   the sum of the two crops on that axis. Every one of the 27 seam pairs is
   checked, deviation `0.0`.
3. **Invariants** — aspect-matched placements must produce gap `0` and crop
   `0` (within `1e-9`, because a division can leave a `1e-14` residue);
   cells must be pairwise non-overlapping and cover their union exactly.

**The hand-derived numbers are an 18-device oracle.** The `27` seam pairs,
the crop constants, and the `288000`-unit vacancy are true only for the
default `--devices 18` run on the `400×400` grid; any other fleet size
recomputes the grid independently, keeps the invariants, and records a
`seam anchors skipped` note in the report instead of pretending the
constants carry over.

Bezel is part of the answer: the distance between two visible rects adds to
their crop, which is why a 40-unit frame plus an 87.5-unit crop is asserted as
a 127.5-unit gap.

The numbers describe the frames a browser would be handed. Nothing here
executes `frontend/client/client.js`, so these are *not* rendered pixels —
see limitations.

## TestClient and WebSocket concurrency

The harness uses `fastapi.testclient.TestClient` against the real app:

* entering `TestClient` as a context manager gives **one shared blocking
  portal**, so HTTP requests, all fleet device sockets and every controller
  socket run on a single event loop — a broadcast can only reach a socket
  that shares its loop;
* **each socket has one dedicated reader thread** that blocks in
  `receive_json()` and parks frames on an unbounded queue. Scenarios consume
  them from the main thread with deadlines. A slow reader can never stall a
  broadcast (the streams are unbounded), and a reader never waits forever
  (every wait is bounded);
* **the main thread owns the client**: it performs all HTTP and opens/closes
  every socket. Reader threads only receive. Closing a socket unblocks its
  reader with an exception, which the reader turns into a `socket-closed`
  marker frame — a replacement session is attached only after that, so a
  `4409`/`4408` close code is always observed by the socket it belongs to;
* a heartbeat thread keeps every tablet checking in (default 2.5 s against a
  15 s server timeout) so long runs stay healthy, and it re-reads its
  interval every 50 ms so a scenario that shortens it takes effect at once;
* restarting (`21_restart`) cycles the lifespan over the same database and
  explicitly clears the in-memory roster/socket registries, because a real
  restart loses that memory while an in-process lifespan restart would not.

## Safety: no production data

Before anything else the run:

1. sets `TABLET_WALL_DB` and `TABLET_WALL_ASSET_DIR` to a fresh
   `tempfile.mkdtemp()` directory (the defaults, `./tablet-wall.db` and
   `./assets`, are operator data and never become reachable);
2. clears `TABLET_WALL_OPERATOR_ORIGIN` / `TABLET_WALL_TABLET_ORIGIN` so an
   ambient shell cannot change what is exercised;
3. fingerprints every file in the repository (excluding `.git`, `.venv` and
   caches; when `--report` points inside the repository, the report file
   itself) and re-checks the fingerprint after teardown — any created,
   removed or modified file fails the run with exit `1`.

The temporary directory is deleted at the end unless `--keep-work-dir` is
given, and a leftover reader thread is itself a failing check.

## Report

Nothing is written by default. Pass `--report PATH` (or `--report -` for
stdout) to get a report; it holds run metadata (timestamps, duration,
Python version, git head, mode, the temp paths), the fleet, per-scenario
status/duration/checks/notes, the summary counts, the failure list, the
limitations, and the resulting exit code. With `--report -` stdout carries
only the JSON — the progress and summary lines go to stderr.

> If you point `--report` into the repository, the file is generated
> output — do not commit it. The default writes nothing so that no
> generated `simulator/report.json` can be committed by accident.

## Limitations versus a real browser

Repeated in every report:

* **No JavaScript runs.** `frontend/client/client.js` is never executed, so
  canvas drawing, image decode, DOM/layout, device-pixel-ratio and resize
  behaviour are not observed — only the frames and the geometry a browser
  would receive.
* **No pixels.** Seam numbers are arithmetic; "the wall looks aligned" would
  need a screenshot or a real client.
* **In-process ASGI.** No TCP, no uvicorn, no reverse proxy, no TLS: socket
  framing, proxy timeouts and any enforcement in front of the app are outside
  the run.
* **Timing constants are patched in one scenario.** The real 15 s heartbeat
  timeout is not waited for; `22_sweeper` shortens the sweeper's constants in
  the simulator process only.
* **Not a substitute for the pytest suite.** Operator-origin (CSRF) fencing,
  asset validation failures (corrupt/oversized/rotated/symlinked), persistence
  edge cases and backup tooling stay covered by `uv run pytest` (`500` tests).

## Files

| file | role |
| --- | --- |
| `run.py` | CLI, repository fingerprint, scenario loop, report, exit code |
| `harness.py` | environment isolation, the app lifecycle, virtual devices, socket readers, heartbeat |
| `scenarios.py` | the numbered scenarios and the `Ctx` check API |
| `geometry.py` | pure visible-rect / centred-cover / tiling / seam arithmetic |
| `report.py` | check and scenario records, JSON emission |
| `test_simulator_selftest.py` | plumbing self-tests, no app needed — `uv run pytest simulator/test_simulator_selftest.py` |

No report file is written unless `--report` names one.

## Run the isolated browser experiment

T1 adds a separate Python Playwright runner in `simulator/browser/run.py`.
It starts one disposable uvicorn worker over a real loopback TCP socket and
loads the actual `/client/` and `/controller/` scripts. It does not extend
the TestClient simulator.

Prerequisites are Linux with `/proc`, the project's Python environment, and
Playwright's Chromium binaries plus their host libraries. The optional
`browser` dependency group pins Python Playwright to `1.57.0`. Its browser
manifest pins Chromium and Chromium headless shell to revision `1200`,
version `143.0.7499.4`. Install those binaries explicitly before running.
The runner never installs browsers or changes host libraries.

```bash
uv sync --group browser
uv run --group browser playwright install chromium
uv run --group browser python simulator/browser/run.py
```

A default run creates a new artifact directory under `/tmp` and prints its
`report.json` path. To choose a destination, pass `--artifacts /tmp/my-new-run`.
The directory must not exist and must resolve outside the repository.
Existing artifacts are never reused or overwritten. A run normally takes
about 30 seconds. Exit `0` means every check passed, including the bounded
duplicate-identity behavior and the P0 software experiments. Exit `1` means a
check or execution failed. Exit `2` means invalid arguments or an unsafe
artifact destination.

The fixed fleet has two independent same-origin contexts in one Chromium
process and a third endpoint in a separate Chromium process with its own
persistent temporary profile. It uses landscape `800x600` at DPR `1`,
portrait `600x800` at DPR `1.25`, and `801x601` at DPR `1.5`. These are desktop
browser viewport fixtures, not claims about physical tablet models. The
controller uses a fourth independent context.

The runner verifies three distinct IDs, a welcome and wall replay per client,
identity retention after reload, and one open socket per endpoint throughout
a six-second observation window. It also observes real outgoing heartbeats
and server online state. Process IDs establish that the persistent profile
runs in a different browser process.

The negative scenario opens a second page in the first context. Both pages
share the stored ID; the server closes the older socket with `4409`. T2 makes
that close terminal for the losing page: it stops retrying, reports
`replaced`, and shows the takeover control. The check requires exactly one
`4409`, one welcome for the joining page, no reconnect attempt from the loser,
and a visible control. A second phase clicks that control and asserts
ownership moves exactly once, with the previous winner becoming the stopped
page. An automatic replacement storm fails the check.

Pillow creates a deterministic `1600x800` coded PNG in the temporary asset
directory. The runner sets a `1200x800` wall, placements, and an image scene
through the API. It then uses the real controller buttons to show calibration,
select the curated image, and show it on the wall. There is no upload feature
in the current controller. Each client captures 25 edge and interior canvas
pixels before and after reload. Hand-derived inverse maps account for the
200-column global image crop, each placement's cover crop, fractional DPR,
and rounded backing dimensions. The oracle imports no application renderer
or simulator geometry code. Screenshots and DOM measurements record the
visible rectangle, backing size, viewport, visual viewport, DPR, orientation,
and launch mode. Current headless fixtures do not reproduce mobile browser
toolbars or prove a `100lvh` defect.

### P0 evidence matrix

`report.json` carries a `p0` object with one row per required P0 experiment,
each `PASS`, `FAIL`, or `MISSING` with a reason. The runner asserts that every
required row is present, that no software experiment failed, and that every
`MISSING` row names its prerequisite. `p0.status` is `PASS`,
`PASS_WITH_MISSING_HARDWARE`, or `FAIL`.

| Experiment | How it is measured |
| --- | --- |
| `rectangles_tab` | visible `#surface` rectangle equals the viewport; backing equals DPR times the rectangle |
| `rectangles_fullscreen` | a real click on the client's fullscreen control, `fullscreenElement` observed, rectangle and backing re-measured, then restored and compared with tab mode |
| `rectangles_standalone` | `MISSING`: no installed standalone launch was tested |
| `mp4_decode_playback` | a generated 2 s H.264 Constrained Baseline MP4 is served from a temporary loopback HTTP server with single-range support; checks metadata, muted `play()`, advancing media time, decoded-frame counts and callback frames |
| `mp4_seek` | seek to 1.2 s completes within 0.15 s |
| `mp4_clip_rotation` | screenshot pixels prove a clipped region and a quarter-turn transform on an asymmetric band fixture |
| `mp4_loop_gap` | a native loop wrap is observed by requestAnimationFrame sampling; the gap is reported as software sampling, not optical evidence |
| `tablet_sleep_clock`, `host_suspend_clock` | `MISSING`: no device suspend or host suspend was performed |
| `physical_ipad`, `physical_android`, `optical_sync` | `MISSING`: hardware is not attached |
| `two_origin_ingress` | `MISSING`: this runner uses a direct backend, not an ingress proxy |
| `software_*` rows | mirror the identity, reload, persistent-profile, pixel and ownership checks |

The MP4 row proves decode and compositor behavior for the installed desktop
Chromium only. It is not iOS Safari, it does not select a production bitrate
or profile, and the fixture is small enough to be fully buffered. HTTP range
delivery is exercised by the fixture server only as probe plumbing; production
range semantics belong to R4.

The R1 flow runs the real operator UI through upload and show: it writes a
solid-colour JPEG, chooses it with the file input, presses Upload, waits for
`Ready: r1-upload.jpg`, presses Show on wall, and samples the centre of all
three client canvases for that colour. It then uploads a text file, requires
the explicit rejection message, and checks the scene did not change. The
server runs the direct-local admission mode for this disposable origin, so the
flow proves the loopback path, not the authenticated proxy path.

The R2 flow adds one calibrated physical client. It uploads a 400x240 coded
fixture, records a 100x60 mm display and a 300x180 CSS calibration, applies a
200x120 physical layout with a mount-180 slot, and checks the panel-centre
marker against the hand-derived `[-1,0,0,-1,300,260]` transform. It also
checks the neutral area outside the panel clip and then resizes the page past
the measured viewport, requiring the plan to disappear rather than repaint.
That is desktop Chromium software evidence, not a physical seam or optical
measurement.

Reports contain per-page console messages, page errors, HTTP statuses, failed
requests, socket frames, close codes, pixel checks, collision counts, cleanup
evidence, versions, the tested `HEAD`, a hash of the working diff, and evidence
gaps. Unexpected warnings, errors, failed requests, HTTP errors, and socket
errors fail the run. The expected collision closes are scoped to the two
contending pages. PNG snapshots read actual canvas output without changing the
rendering context's readback hints.

No server, database, asset, or media target is accepted as an option. The
runner removes ambient `TABLET_WALL_*` settings from the server environment
and assigns its own temporary DB, asset, and reserved media paths. The current
app does not use the reserved media directory. The loopback socket is bound
before spawning uvicorn and passed by file descriptor, avoiding a port race.
Temporary profiles, browser processes, server, and data are closed in `finally`
paths. The report checks the server was reaped, recorded descendant processes
are gone, and the temporary root was removed. Artifacts remain for review,
including failure reports, server logs, and available failure screenshots.

### R3 software cuts and the suspend step (`--cuts`, `--suspend`)

Both are opt-in; the default run is unchanged (same 106 checks).

```bash
uv run --group browser python simulator/browser/run.py --cuts 100
uv run --group browser python simulator/browser/run.py --suspend
```

`--cuts N` (2 to 1000) adds about `N + 10` seconds (`--suspend` about 15). It opens three more
independent calibrated clients (two contexts in one Chromium process, one
persistent profile in another; 240x160 at DPR 1, 200x150 at 1.25, 220x140 at
1.5; mounts 0, 180, 0), each with its own display, calibration and slot in one
physical layout. A four-item solid-colour loop runs at the shortest legal
dwell, 1000 ms (the run also checks the server refuses 999). The static scene
is a fifth colour, so the first commit is a visible cut. Every committed
occurrence counts as a cut, including the first.

Onset is measured inside each renderer, not by polling. An init script wraps
`CanvasRenderingContext2D.drawImage` and records, per new image on `#surface`,
`performance.timeOrigin + performance.now()` taken before the call, plus the
centre pixel read from a copy afterwards. It also logs the `commit`, `prepare`,
`cancel`, `playback` and `clock_bootstrap` frames with the same clock. Pages
share the host clock, so the stamps compare across renderers. Events are keyed
by the server's occurrence (`loop * items + item_index`), not by asset, so a
repeated asset cannot satisfy a different cut.

Per event the report gives each member's commit receipt, onset, pixel check and
lateness against the planned `effective_server_ms` (mapped onto the page clock
with the host's wall-minus-monotonic offset; it includes clock-estimate error),
the software onset delta (max minus min across the planned cohort, never
pooled), completion, the server's `missed` list and the client-side missing
members. An event is complete only when every cohort member painted the right
colour. A missing commit, a missing paint or a wrong pixel is a failed event.
It stays in the denominator, and the whole-show percentiles treat it as
unbounded (`null`). The healthy-subset p50/p95/max (nearest rank) are reported
apart from the whole show. Degradation windows are runs of consecutive failed,
server-missed or re-anchored events (effective-time gap different from the
dwell). Commits after event `N-1` exist only because the run stops about a
second after the last counted cut; they are reported as
`trailing_commits_not_counted` and are not scored.

Every figure is labelled "software, not optical". It is a `drawImage` call
time on a desktop Chromium, for solid stills, on one host. It excludes
decode-to-glass, compositor, panel scanout and any camera uncertainty. The
optical gate row stays `MISSING` in the report and in `evidence_gaps`; nothing
here is compared against the 100 ms / 250 ms optical gate.

`--suspend` starts a second disposable server through
`simulator/browser/clock_app.py`. That entry only replaces `ServerClock`'s
`sample` adapter (the injected `(BOOTTIME, MONOTONIC)` reader): BOOTTIME gets a
persistent step read from a file the runner owns, MONOTONIC and scheduling are
untouched. A step above the 2 s `SUSPEND_THRESHOLD_MS` looks to
`check_suspend` exactly like a host suspend. With two real clients and a 6 s
dwell, the run first applies a 1.5 s step (a control: nothing may change), then
a 5 s step right after the first cut, while the next preparation is ready and
renewing. It requires a `playback` frame with reason `host suspend` and a new
epoch at both clients, `GET /api/v3/playback` reporting `stopped`, no further
`ready` renewals for the cancelled preparation, no commit and no draw of its
asset until 1.5 s past its planned time. It records what stays visible and accepts either the last
committed still or the persisted scene, never the cancelled cut. Today the
clients keep the last committed still: the abort sends only a stopped frame and
the client clears timers without redrawing the scene (`visible_state` and
`product_note` in the report). A reload shows the persisted scene was
untouched, and a fresh session started after the epoch change carries the new
epoch and paints.

A page-level `performance.now` step cannot do this and the report says so: the
epoch exists only on the server, the client takes `clockEpoch` only from
`clock_bootstrap`, and only `cancel` and `playback` frames stop its pending
work. This is not a physical or host suspend; `physical_suspend` stays
`MISSING`.

Run the focused safety and oracle checks with the browser group installed.
They cover path rejection, environment isolation, independent pixel anchors,
process reaping, signal cancellation during cleanup, partial server launch,
and a real missing-browser failure that still saves a report and cleans up
its server. SIGINT and SIGTERM cancel the runner task while keeping
Playwright's event reader alive until browser shutdown finishes. The
`--cuts` argument check, the clock-adapter step, and the pure event analysis
(`test_evidence.py`: per-event deltas, failed events, unbounded whole-show
percentiles, degradation windows) run without a browser session.

```bash
uv run --group browser pytest -q simulator/browser/test_browser.py simulator/browser/test_evidence.py
```

Every report explicitly marks physical old/new iPad and Android inventory,
MP4 decoding, sleep/wake, optical synchronization, and two-origin ingress as
missing. Independent contexts and processes still share the host scheduler,
GPU, clock, and NIC. Green T1 evidence establishes current desktop Chromium
logical-still behavior only. It does not close any physical-device gate.
