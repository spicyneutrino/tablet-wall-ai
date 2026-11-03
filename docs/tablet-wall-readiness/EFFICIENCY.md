# TWR-16 measured efficiency baseline

**Status:** baseline recorded; no optimisation applied.
**Application revision measured:** `8c3356a5d043196f7fc384ce9fbf9ac463775832`.
**Measured:** 2026-11-01, 10:52–10:57 UTC.
**Scope:** software only. Desktop headless Chromium on loopback. No physical
tablet, battery, memory, thermal, optical, or capacity claim.

This report answers §8.2 and dispositions every cost in §8.3. It does not
change the source tree, the polling path, or any product behaviour.

## 1. What was measured

The shipped `frontend/client/client.js` rendered an images-only logical wall in
four independent Chromium pages. The server was an isolated `uvicorn`
single-worker process on a private loopback port with a temporary database,
asset directory, media directory, and log. Four real curated PNGs were copied
into that temporary root; the primary image was the existing 4000×3000,
2,792,004-byte flyer. The four-tablet condition used four browser contexts in
one Chromium process, so its CPU is shared — this is a software baseline, not a
fleet model.

A runtime wrapper was imported into the same temporary server process. It did
not edit `main.py` or any source. It recorded, on one process monotonic clock:

- `render_status.expect` (device instruction enqueue);
- Starlette `WebSocket.send_json` when the frame was a `render` instruction
  (instruction sent);
- Starlette `WebSocket.receive` when the message was a `render_ack`
  (ack receipt, after the client's draw and `requestAnimationFrame`);
- `render_status.accept` with its accepted/rejected result (accepted current
  token, exclusively);
- `main._broadcast_wall` calls.

Only an **accepted `render_ack` with `status: "displayed"` whose token matches
the `render` instruction's connection, generation, revision, render sequence,
mapping revision, and asset** is a latency sample. An HTTP 200 on the scene
write is not a sample. After every timed change the run also read
`/api/v3/config` and verified `runtime.devices[id].render.current == true` for
every target tablet.

### Conditions

| Condition | Definition |
| --- | --- |
| Cold | Page reloaded after `Network.clearBrowserCache`; scene was colour first, so the image was fetched from the server and decoded before the first paint. |
| Warm | Same page immediately after the cold paint; the scene stayed image, so the client retained the decoded picture and this path only drew and reported. No asset request or decode occurred (confirmed by the byte counter). |

Five rounds were run. Round order alternated 1-tablet then 4-tablet on odd
rounds and 4-tablet then 1-tablet on even rounds, so drift and warm-up did not
favour one size.

### Environment

| Field | Value |
| --- | --- |
| Host | Linux 7.2.7, x86_64, 32 CPUs (`nproc`) |
| Load average at end of run | 0.41 / 0.77 / 1.19 (1/5/15 min) |
| Python | 3.13.13 (`.venv`) |
| Browser | Playwright Chromium 143.0.7499.4, cached `chromium-1200` |
| Playwright | 1.57.0 |
| Server | `uvicorn` single worker, access log enabled (matching `deploy/hotspot.py`), `--fd` loopback socket |
| Client viewport | 600×800 CSS px, DPR 1, protocol 3, `render_ack` negotiated |
| Wall | logical, 600×800 per tablet; 1×1 or 1×4, gap/padding 0 |
| Image | `EXLENT_Cohort_3_Flyer_Temp.png`, 4000×3000, 2,792,004 bytes, `fit: cover` |
| Library | 4 real PNGs, 8,540,433 bytes total |

The MCP desktop browser was not used; Chrome binaries for it are known
missing. The run used the isolated cached Playwright Chromium fallback.

## 2. Time to painted

Server-observed: instruction sent → client's accepted displayed ack receipt.
Nearest-rank percentiles across the five interleaved rounds.

| Tablets | Condition | Samples | p50 (ms) | p95 (ms) | Range (ms) | Errors |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| 1 | cold | 5 | 118.007 | 127.106 | 95.102–127.106 | 0 |
| 1 | warm | 5 | 3.609 | 5.082 | 3.281–5.082 | 0 |
| 4 | cold, per tablet | 20 | 123.423 | 140.720 | 112.136–140.779 | 0 |
| 4 | cold, fleet from first send | 5 | 129.262 | 141.047 | 117.663–141.047 | 0 |
| 4 | warm, per tablet | 20 | 3.650 | 4.224 | 2.918–4.299 | 0 |
| 4 | warm, fleet from first send | 5 | 4.232 | 4.380 | 4.078–4.380 | 0 |

Every timed change produced one accepted displayed ack per target tablet; zero
displayed acks were rejected; every post-change `render.current` check was
true. Cold round medians vary (1 tablet 95.1–127.1 ms; 4 tablets per round
112.5–139.9 ms), so the p95 with five rounds is coarse and the run-to-run range
matters more than a small median gap.

**Interpretation, with its limit.** The cold path carries the asset fetch and
the full 4000×3000 decode; the warm path draws the retained picture. The
four-tablet cold p50 is 5.4 ms above the one-tablet p50, but the distributions
overlap and all four contexts share one Chromium process and one host CPU.
This run therefore does **not** isolate a per-tablet scaling cost, and it is
not a capacity claim.

## 3. Payload per wall change

Medians over the five rounds. Bytes are per change, summed across the target
tablets for the 4-tablet row.

| Tablets | Condition | Asset requests | Asset bytes | Render instruction bytes | Config snapshot bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | cold | 1 | 2,792,004 | 1,001 | 7,579 |
| 1 | warm | 0 | 0 | 1,001 | 7,578 |
| 4 | cold | 4 | 11,168,016 | 4,016 | 8,017 |
| 4 | warm | 0 | 0 | 4,016 | 8,017 |

The cold result confirms the known cost: each tablet fetches the full source
once for a new image on a page that has no cached copy. It does not show an
accidental re-download in the warm path; there, zero asset requests were made.
The config snapshot is about 7.5–8.0 KB regardless of the one-versus-four wall
size in this setup.

## 4. Writes and broadcasts for a 2×2 apply

Using four registered tablets:

| Check | Result |
| --- | --- |
| Layout before / after | revision 44 → 45 |
| Revision delta | 1 |
| `_broadcast_wall` calls in the apply window | 1 |
| Placements in applied layout | 4 |
| Placements in preview | 4 |

The existing route integration test
`tests/test_operator_backend.py::test_grid_one_revision_order_and_viewport_guards`
also passed (1×2, two devices, one revision and one broadcast). Raw pytest
output is in the evidence directory (`regression-grid-test.txt`).

## 5. Five-minute idle operator console

The primary console `/controller/physical.html` was open at 1440×1000, visible
and focused for the whole window (`document.visibilityState == "visible"`,
`document.hasFocus() == true` at start and end). Four tablets stayed connected
and idle. Background timer throttling was disabled in the browser launch so the
console ran as a foreground console.

| Measurement | 300 s window |
| --- | ---: |
| Boot requests before the window | 23 |
| Idle HTTP requests | 20 |
| Idle HTTP GET | 20 |
| Idle HTTP paths | `/api/v3/config` ×20 |
| Idle HTTP rate | 4/min (≈15 s reconcile) |
| Idle WS frames received | 244 |
| Idle WS bytes received | 880,499 |
| Idle WS frames sent | 0 |

On this static wall (experimental playback off) the console did **not** poll
every 1 s or 5 s. It used the v3 operator socket plus a 15 s config
reconciliation. The 244 WS frames are consistent with four tablets' 5 s
render/status heartbeats being broadcast as device updates; this run counted
frames, not their cause. The socket traffic is about 0.88 MB per five minutes,
roughly six times the HTTP request bytes (20 × ~7.5 KB ≈ 150 KB). Replacing
polling with a socket would not remove the dominant idle traffic, and polling
itself is only four requests per minute. **Do not act on the polling
replacement.**

This measurement is five minutes, not a day. A console left open all day may
see different timers, visibility, or throttling; measure again before any
long-run claim.

## 6. Log growth with access logging enabled

The launcher in `deploy/hotspot.py` runs `uvicorn` with its default access log,
so this run used `--access-log`. During the 300 s idle window the server log
grew from 34,930 to 36,230 bytes: **1,300 bytes**.

| Figure | Value |
| --- | ---: |
| Measured growth, 300 s | 1,300 B |
| **Five-minute projection, labelled** | **374,396.6 B/day (≈366 KiB/day)** |
| Rotation active-file cap | 1,000,000 B |
| Rotation archives | 2 |
| Retained bytes per log at cap | 3,000,000 B |
| Projected first rotation, idle only | ≈2.7 days |
| Projected full retention, idle only | ≈8 days |

This is a **5-minute projection**, not a measured idle day. It counts the
backend access log only; Caddy, journald, startup, restarts, and any operator
activity are outside it. It shows rotation is already sized to bound an idle
wall; no change is proposed from this projection.

## 7. Curated asset inventory cost

Four real PNGs (8,540,433 bytes total) in the temporary asset directory.

| Measurement | Result |
| --- | ---: |
| `GET /assets`, loopback HTTP, n=20 | p50 57.132 ms, p95 59.422 ms, range 13.880–59.840 ms |
| `assets.list_assets()` in the separate profile, n=30 | p50 5.752 ms, p95 6.469 ms |
| Assets returned | 4 |

The HTTP path is about ten times the in-process function here; it includes the
sync route's threadpool dispatch, loopback client, and serialization, and this
run did not isolate those. The limiter in the function is named in §8: repeated
SHA-256 over the whole curated library. At this library size a listing is well
under 1% of a 15 s console reconcile, but a larger library is unmeasured.

## 8. Separate profile: config, SQLite, broadcast, send

This is a separate single-process `cProfile` run with a temporary database and
fake device sockets. It is **not** a wall-latency run. `cProfile` inflates CPU;
the numbers only name a limiter.

| Operation | n | p50 (ms) | p95 (ms) |
| --- | ---: | ---: | ---: |
| `_config_payload()` | 30 | 7.887 | 9.254 |
| `_config_etag()` | 30 | 8.381 | 8.911 |
| `assets.list_assets()` | 30 | 5.752 | 6.469 |
| `persist.load_layouts()` (SQLite) | 30 | 0.187 | 0.232 |
| `persist.load_scenes()` (SQLite) | 30 | 0.183 | 0.194 |
| `hub._broadcast_wall()` with 4 fake writers | 30 | 0.065 | 0.109 |

`cProfile` top cumulative (0.747 s total for the mixed loop): `assets._load`
0.534 s, `assets.refresh` 0.531 s, `_config_payload` 0.522 s, and
`_hashlib.openssl_sha256` 0.419 s. The named limiter for config and inventory is
the repeated full-library SHA-256 plus directory scan, not SQLite (about
0.18 ms per read). The broadcast row covers frame projection and enqueue only;
it excludes the real socket write and JSON transport, so it is not a network
claim. Event-loop cost and actual send latency were not isolated; the
send-to-ack measurement in §2 includes them.

## 9. Dispositions for every §8.3 cost

| §8.3 cost | Disposition | Rationale |
| --- | --- | --- |
| Four sequential placement writes → four revisions/broadcasts | **Do not act (regression holds)** | 2×2 apply produced exactly one revision and one `_broadcast_wall`; the existing route test also passes. |
| Every tablet downloads and decodes the full source; 2.7 MiB 4000×3000 sample exists | **Do not act; measure again on real tablets** | Cold is 118 ms p50 for 1 tablet and 123 ms p50 per tablet for 4; warm draw is 3.6–3.7 ms. Every cold tablet fetched 2.79 MB. No measured sharpness or decode failure justifies renditions; the real-device decode/memory path is unmeasured. |
| Synchronous SQLite reads per v3 device during broadcast | **Do not act** | Profile: `load_layouts` 0.187 ms and `load_scenes` 0.183 ms p50; not the limiter at four tablets. Measure again above the tested fleet. |
| ETag rebuild/hash on each v3 write | **Do not act** | `_config_etag` p50 8.381 ms, dominated by full-library SHA-256; it is not on the paint path. Measure again with a larger library. |
| Console polls 1 s/5 s | **Do not act** | The measured primary console makes 20 HTTP config requests per 5 min (15 s reconcile) and receives 244 WS frames / 0.88 MB. The 1 s/5 s polling pattern was not observed on this console; the socket already carries the larger idle traffic. Polling replacement is unsupported by the measurement. |
| Sequential broadcast sends | **Do not act; instrumented** | Every timed change recorded an instruction send and an accepted ack; no send failures. Four-tablet fleet p95 is 141 ms versus per-tablet p95 140.7 ms. The shared browser process confounds a send-concurrency conclusion; measure again with independent devices. |
| Curated inventory scans/hashes files | **Measure again; do not act now** | Four assets / 8.54 MB: `GET /assets` p50 57 ms, server function 5.75 ms. This is not a wall bottleneck at this size, but the library is small. Never weaken byte verification. |
| Playback loop swallows exceptions | **Do not act (out of scope)** | TWR-13 owns bounded playback fault logging. This run did not exercise playback. |

No row is marked “optimised”; no code changed.

## 10. Limits and non-claims

- Desktop headless Chromium, loopback, one host. Not an iPad, Pixel C, Safari,
  tablet decoder, or battery measurement.
- Four tablet pages are four contexts in one Chromium process, not four
  devices. The 4-tablet cold distribution shares one CPU and one browser.
- An accepted displayed ack is the client's claim after decode/draw and a
  `requestAnimationFrame`; the run did not read back canvas pixels in the timed
  loop.
- p95 with five rounds is coarse. Raw per-round values are in `report.json`.
- The idle console window is 300 s. The daily log figure is a labelled
  5-minute projection; the console request rate is not a daily measurement.
- Access logging is enabled, but Caddy and systemd-journald growth are not
  measured.
- Profile rows come from a separate `cProfile` process and are not comparable
  to §2 wall latency.
- No hardware capacity, battery, memory, thermal, or “20 tablets” claim is
  made.

## 11. Reproduce

From the repository root:

```bash
cd /var/home/oak/.t3/worktrees/tablet-wall-ai/t3-1a233855
uv sync --group dev --group browser

# Existing route regression: one revision / one broadcast on apply.
.venv/bin/python -m pytest -q \
  tests/test_operator_backend.py::test_grid_one_revision_order_and_viewport_guards

# Focused baseline arithmetic/byte-attribution test.
.venv/bin/python -m pytest -q simulator/browser/test_image_efficiency.py

# Full run; --artifacts must be a new directory outside the checkout.
.venv/bin/python -m simulator.browser.image_efficiency \
  --artifacts /var/home/oak/.local/share/tablet-wall-ai/readiness-program/efficiency/<new-run>/benchmark \
  --rounds 5 --idle-seconds 300 --profile
```

The server, temporary database, assets, browser, and pages are created and
stopped by the script. The run does not touch live wall data, the running
installation, firewall, hotspot, or a public origin. It binds an unused
loopback port.

## 12. Evidence

Raw evidence is outside the checkout:

`/var/home/oak/.local/share/tablet-wall-ai/readiness-program/efficiency/twr16-final2-20261101T105202Z/`

| File | Content |
| --- | --- |
| `benchmark/report.json` | Full records: per-round samples, ledger slices, payloads, 2×2 result, idle events, profile |
| `benchmark/summary.json` | Condensed environment, summaries, 2×2, inventory, idle, profile |
| `benchmark/profile.json` | Separate cProfile operations and top cumulative table |
| `benchmark/console-idle.json` | Every idle console request and WS frame |
| `benchmark/server.log` | Server access log used for the 1,300 B growth measurement |
| `regression-grid-test.txt` | Existing route integration test output (1 passed) |
| `benchmark.stdout`, `benchmark.stderr` | Exact invocation output |

The application tree at measurement time was `8c3356a` plus only these new
files: `simulator/browser/image_efficiency.py`,
`simulator/browser/test_image_efficiency.py`, and this report. No tracked source
file was modified. Linking this report from `VERIFICATION.md` is left to the
integrating task because this task owns only the new files above.
