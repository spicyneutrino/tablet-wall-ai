# Image tablet wall — readiness roadmap and acceptance contract

**Document status:** Open. Implementation in progress. No hardware claim is made
anywhere in this document.
**Baseline for current-state claims:** `981b2db` (`style: remove ingress test
trailing blank line`), integration branch `work/tablet-wall-readiness`. The
branch advanced to `18afa5c` while this document was being written; §4.4 records
the observed state at each point.
**Assessed product baseline:** `0ff56e3` (`feat: add measured tablet setup and
adaptive wall sizing`), the commit all four source reviews examined.
**Owner of this file:** roadmap/acceptance only. Architecture is normative in
[ARCHITECTURE.md](ARCHITECTURE.md); operator UX and hazards are normative in
[UX-AND-RISKS.md](UX-AND-RISKS.md). Source-report snapshots are in
[reviews/](reviews/).
**Last substantive revision:** 2026-11-01.

---

## 0. What this document is, and what it is not

This is the single combined plan produced from four independent readiness
assessments. It does four jobs:

1. States what the product actually does today, with evidence labels.
2. Defines the target operator journey and the data/technical contracts that
   support it.
3. Converts **every** recommendation in the four reports into a disposition:
   a delivery work package, a hardware-validation obligation, or an explicitly
   deferred/rejected item with a reason.
4. Defines testable acceptance per work package and the evidence needed to
   close it, keeping *software complete* and *hardware proven* separate.

It is not:

- a promise that the physical path works on glass;
- a replacement for the eight hardware gates in
  [`docs/validation/HARDWARE-VALIDATION.md`](../validation/HARDWARE-VALIDATION.md),
  which remain **MISSING**;
- a licence to optimise, rewrite, or add speculative subsystems;
- a claim that video, optical synchronisation, mirror, independent-screen, or
  cloud operation is implemented.

### 0.1 Source precedence

The four snapshots are evidence and proposals, not authority. This document is
authority for *what will be accepted*. When a report disagrees with re-checked
source or an executed check, source/check wins. §11.9 records the resolution of
each material contradiction; §12 records what is deferred or rejected.

### 0.2 Scope boundary for this programme

- In scope: one continuous still image across a small wall of browser tablets
  (2×2 or 1×4), set up and recovered by a non-developer, image-first.
- Out of scope for this milestone: video and timed playback as dependable
  features; mirror; independent per-tablet content; cloud or remote access;
  multi-user roles; distributed backends; AI generation; optical
  synchronisation; more tablet models than the installed fleet needs.
- Operational boundary: no live database writes, firewall changes, network
  changes, or service installation during implementation. All runtime checks
  use temporary data, loopback, and private browser sessions. Hardware runs are
  separate, operator-authorized events.

---

## 1. Evidence labels and status vocabulary

Every factual claim below carries one or more labels.

| Label | Meaning | How it may be used |
| --- | --- | --- |
| `[S]` | Source-confirmed at the stated HEAD, with a file reference. | May justify a design decision. Not proof of runtime behaviour. |
| `[T]` | Executable test evidence, with the exact command and result. | Proves the tested contract only. Never proves hardware. |
| `[P]` | Isolated in-process API probe with a temporary database, assets, and media directory. | Proves the observed response/state path. Not a browser or device. |
| `[Sim]` | Simulated browser session on loopback (headless Chromium or equivalent). | Proves rendered software behaviour for that viewport. Not Safari, not a tablet. |
| `[U]` | User-reported physical observation. | Accepted as reported; configuration-specific; not re-verified here. |
| `[H]` | Hypothesis or outside knowledge, unverified in this repository. | May motivate a test. Must never be presented as fact. |
| `[D]` | Decision recorded by this roadmap. | Binding until superseded by a logged decision. |
| `[N]` | Non-goal / rejected for this milestone. | Do not implement without reopening the decision. |

**Status vocabulary.** These are the only statuses a work package may carry.

| Status | Meaning |
| --- | --- |
| `Open` | No accepted implementation. |
| `Open — merged, acceptance pending` | Code is merged to the integration branch, but at least one required acceptance check (often rendered or hardware evidence) is not recorded. The GitHub issue stays open. |
| `Software complete` | All software acceptance checks in this document pass and are recorded in `VERIFICATION.md`. Hardware checks may still be open. |
| `Hardware verified` | The named physical configuration passed the named hardware checks, with signed evidence. Software alone can never produce this status. |
| `Deferred` | Deliberately not in this milestone; revisit trigger recorded in §12. |
| `Rejected` | Will not be built for the stated reason unless the premise changes. |

A package is never marked `Software complete` because tests exist; it is marked
so when *its* acceptance checks are recorded with commands and results. A
GitHub issue is never closed on a simulation, a test count, or another
package's evidence.

---

## 2. Verdict and definition of done

### 2.1 Verdict

**Ready for a supervised, images-only demonstration in the demonstrated logical
layout on known tablets. Not yet ready for dependable unattended operation, and
not yet evidenced on the physical-layout path.**

All four reviews converge on this. The core loop — tablet opens URL, registers,
receives a number, is placed, shows its slice of one wall-wide image — works in
the operator's own trials `[U]`, in the test suite `[T]`, and in simulation
`[Sim]`. The gaps are truthfulness, lifecycle, arrangement determinism,
calibration provenance, recovery, and operational rehearsal. They are
integration gaps, not a reason to rewrite the geometry or persistence core.

### 2.2 Two finish lines

| Finish line | Requires | Does not require |
| --- | --- | --- |
| **Software complete** | TWR-01 … TWR-16 accepted as specified, or explicitly deferred with a recorded decision (TWR-15); TWR-14 browser acceptance recorded; no open review or red-team blocker. | Any tablet. |
| **Milestone complete** | Software complete **and** TWR-17 hardware record signed for the stated devices, modes, and durations; failures retained. | Video, optical sync, unattended 24/7 claim beyond the measured soak. |

**Definition of done for the milestone.** An operator who has never read the
source can start the supported profile, join four tablets, name and identify
them, apply a 2×2 or 1×4 arrangement in number order, show one image with a
truthful crop preview, see per-tablet paint truth, recover a sleeping or
reconnecting tablet, remove or forget a tablet, switch arrangements without
losing either, and restore from a verified backup — and the hardware record
shows that this happened on the actual iPads and Pixel Cs, with every failure
and manual action written down.

### 2.3 Explicit non-claims at completion

Even when the milestone is complete, this document does **not** claim:

- sub-2 mm seams outside the measured uncertainty;
- that a paint acknowledgement proves a lit panel or a person seeing it;
- video, audio, optical onset, or synchronised playback;
- mirror or independent-screen modes;
- unattended operation beyond the defined soak;
- security on an untrusted network unless TWR-15 is complete for that profile;
- remote wake, remote unlock, or wake lock on hardware that does not support it.

---

## 3. Preserved measured inputs — do not recalibrate by fiat

These values are inputs to the geometry and to every acceptance judgement. No
software work package may silently replace, "correct", or re-derive them. New
measurements are additive, revision-pinned records; they never overwrite
history.

| Input | Value / state | Evidence | Rule |
| --- | --- | --- | --- |
| iPad Air 2 model profile | Active panel 146.75 × 196.0 mm; bezels L/R 10.52 mm, T/B 21.1 mm; panel 768×1024 CSS @ DPR 2; portrait angle 0°; 0.187725 mm/CSS; **3.0 mm provisional uncertainty** | `[S]` `tabletwall/tablet_models.py:8-11`; `[U]` used in operator trials | Reuse as-is. A new ruler result creates a new calibration revision, not an edit. |
| Pixel C model profile | Active panel 147.0 × 210.0 mm; bezels 15.2 mm all sides; panel 900×1280 CSS @ DPR 2; portrait angle 270°; 0.16195 mm/CSS; **3.0 mm provisional uncertainty** | `[S]` `tabletwall/tablet_models.py:12-15`; `[U]` | Reuse as-is. The 90°/270° mapping is unverified on glass until TWR-17. |
| Saved logical wall | Four tablets in one row, 320 × 60 logical units | `[U]`, as reported to all reviews | Preserve as a named return point before any physical experiment. |
| Current content | 2000 × 745 image, cover fit | `[U]` | Preserve. Do not change fit as part of an unrelated package. |
| User hardware trials | 2×2 and 1×4 usable images in logical mode | `[U]` | Evidence for logical spanning only. Not evidence for the physical path. |
| Seam target | ≤ 2 mm beyond the intended hidden gap, plus stated uncertainty | `[S]` `docs/validation/ACCEPTANCE.md` | Do not relax. Record the achieved value even when it misses. |
| Recovery target | Content correct within 10 s of connectivity restoration; 20 trials for the formal gate | `[S]` `ACCEPTANCE.md`, `HARDWARE-VALIDATION.md` | A 5-trial rehearsal is a rehearsal, not the gate. |
| Soak target | At least 2 h media soak; overnight still soak if unattended | `[S]` `HARDWARE-VALIDATION.md` | Duration and failures are recorded, not summarised away. |
| Ruler span | Current overlay caps a line at 200 CSS px; controller default span 200 | `[S]` `frontend/client/ruler.js:33-34`, `frontend/controller/physical.html:352-355` | TWR-12 adds longer spans. It must not retroactively rewrite existing calibrations. |
| Hardware gates | All eight **MISSING** | `[S]` `docs/validation/HARDWARE-VALIDATION.md:3` | Only signed physical evidence changes a gate. |

**Consistency rule.** When a supply measurement (panel dimensions) and a ruler
measurement disagree, show both, state the derived mm/CSS and the estimated
error, and require an operator choice. Do not average silently and do not let
one overwrite the other `[D]`.

---

## 4. Current state at `981b2db`

### 4.1 What landed between the assessed baseline and the document baseline

| Commit | Change | Evidence | Remaining acceptance |
| --- | --- | --- | --- |
| `5a9cc29` | Logical controller recognises protocol 3 `image` capability instead of treating protocol 3 as unknown. Chip text is now **“Image capable”**, not the “Shows images” wording proposed by the Opus report. | `[S]` `frontend/controller/controller.js:1357,1456`; `[T]` `tests/controller_image_capability.test.js` (50 roster combinations) and ten JS suites, per `VERIFICATION.md` | Rendered check still belongs to TWR-14. Capability is not paint truth. |
| `ef99cb8` | Protocol documentation states protocol 2 or 3 plus the `image` capability. | `[S]` `PROTOCOL.md` | None beyond keeping docs aligned. |
| `abb9c42` | Physical render frames are fenced by advertised image capability; no image descriptor or plan is sent to a non-image device. | `[T]` three cases failed before, then `tests/test_v3.py` 12 passed and wall/hub 99 passed, per `VERIFICATION.md` | No physical screen observed. |
| `15e21f6` | Diagnostics use independent operator-read admission, so they work with uploads disabled; the tablet allowlist gains only the exact app auth entry points (`GET/POST /auth/login`, `POST /auth/logout`). | `[S]` `tabletwall/routes/diagnostics.py:85-105`, `deploy/tablet-routes.caddy:50-72`; `[T]` ingress/field/deployment suites | Auth expiry behaviour on a real tablet remains TWR-07/TWR-17. |
| `981b2db` | Style-only test cleanup. | `[S]` diff is one blank line | None. |

`[T]` The programme's Python baseline at `0ff56e3` was **1,177 passed**, three
deprecation warnings, 109.30 s (`VERIFICATION.md`). It is inherited evidence,
not re-run for this document. The two landed fixes have their own focused
records.

### 4.2 Capabilities that are real today and must be retained

These are not proposals. They are load-bearing and a consolidation that loses
them is a regression.

1. **Persist-before-notify.** A wall change is written from a detached proposal
   to SQLite before memory is updated and before controllers are notified
   (`[S]` `main.py:445-479`). A failed save leaves disk, memory, and subscribers
   agreeing.
2. **Single-owner runtime.** A worker lock refuses a second process on the same
   database (`[S]` `tabletwall/workers.py:12-28`). Startup forces a new
   generation so clients resynchronise (`[S]` `main.py:150-165`).
3. **Separated concepts.** Layout, scene, revision, and generation are distinct;
   layouts and scenes save and recall independently (`[S]` `tabletwall/state.py`).
   Physical slots pin profile and calibration revisions, so editing a
   measurement does not rewrite an old layout (`[S]` `tabletwall/displays.py`).
4. **Explicit geometry.** Wall/body/panel/CSS/backing/normalised spaces with
   fixture-tested transforms (`[S]` `tabletwall/geometry.py`; `[T]`
   `tests/test_geometry.py`, `tests/client_view.test.js`).
5. **Measured models and revisions.** Supplied iPad Air 2 and Pixel C profiles,
   model snapshots, explicit/manual override, model-aware rebind (`[S]`
   `tabletwall/tablet_models.py`).
6. **Asset integrity and caching.** Content-addressed IDs, hash verification on
   read, immutable byte caching, explicit failure panels instead of a silent
   blank wall (`[S]` `tabletwall/routes/assets.py`, `frontend/client/client.js`).
7. **Bounded sockets.** Per-socket writers with frame/byte budgets, deadlines,
   ordered control frames, and snapshot coalescing (`[S]` `tabletwall/writer.py`).
8. **A real ingress boundary.** Tablet-only route allowlist, loopback operator
   listener, exact-origin request fence, uploads off by default, bounded
   registration, and startup route denial checks (`[S]` `deploy/tablet-routes.caddy`,
   `deploy/hotspot.py`).
9. **Operational artifacts with honest caveats.** Verified backup/restore tool,
   service template, kiosk guidance, and hardware gates explicitly marked
   MISSING (`[S]` `deploy/backup.py`, `deploy/OPERATIONS.md`,
   `docs/validation/HARDWARE-VALIDATION.md`).
10. **Client care.** Bounded fetch/decode attempts, stale-result discard,
    bitmap/object-URL release, local retry, reconnect backoff, wake-lock
    reporting, and accessible controller markup (`[S]` `frontend/client/client.js`).

### 4.3 Current gaps that block dependable use

Each gap is a consolidation of claims that survived re-checking. IDs are stable
for tracking.

| ID | Gap | Evidence | Consequence |
| --- | --- | --- | --- |
| C1 | `GET /api/v3/config` has no `scene`, and a physical wall cannot be read truthfully by the console that edits it. A legacy v2 controller receives a synthetic 2000×1000 colour wall; `PUT /scene` on a physical wall returns colour while the stored scene is the image. | `[S]` `main.py:1867-1902`, `tabletwall/state.py:280-298`; `[P]` confirmed by Sol and DeepSeek probes | The only page able to select a still misreports what is showing. A persisted still is confusable with a playlist frame. |
| C2 | The physical console has no still-image, colour, or test-pattern control; its Content tab is playlist-only. | `[S]` `frontend/controller/physical.html:465-523` | Showing a still on a measured wall requires the legacy page before Apply, or the experimental slideshow engine. |
| C3 | Only `cover` is accepted. | `[S]` `tabletwall/protocol.py:61-62`; `[P]` `contain` returns 422 | Posters and 4:3 images lose edges on a 1×4 wall with no product-level alternative. |
| C4 | No crop, bezel, gap, or source-resolution preview. | `[S]` stage draws placements, not the image crop; Thumbnail is the only hint `[Sim]` Opus | Operators cannot see what will be lost before the audience sees it. |
| C5 | Online means a socket with recent contact, not a painted image. No static render acknowledgement exists. | `[S]` heartbeat path; no `render_ack` in protocol or server | A failed decode, stale revision, or half-open socket looks healthy until the 15 s timeout. |
| C6 | The client reconnects only on socket close; heartbeat checks do not force a reconnect; `visibilitychange` only touches wake lock and playback. | `[S]` `frontend/client/client.js:2352-2369,2426-2450,4426-4438` | A page frozen by the OS can resume on a stale image until manual reload. `[H]` until TWR-17 observes it. |
| C7 | An expired auth session has no visible recovery path: registration throws on a non-OK response and retry loops. | `[S]` `frontend/client/client.js:467-498,4468-4503`; 12 h cookie `tabletwall/auth.py:20,194` | With auth enabled, a wall can sit on “Offline · retrying” indefinitely. |
| C8 | `DELETE /devices/{id}` is fenced to logical layouts; physical mode has no Forget. The physical device list unions roster, profile, and layout identities. | `[S]` `main.py:1029-1031`; `[P]` 409 in physical mode | Stale or replaced identities cannot be retired from a measured wall; a slot delete can leave the tablet in the list. |
| C9 | Rebind moves the active placement but saved layouts keep the old UUID; there is no impact preview or transactional repair. | `[S]` `main.py:1074-1172` and its own docstring | Recalling 2×2 after a replacement resurrects an identity that will never return. |
| C10 | Recalling a logical layout from physical mode commits with no safety copy of the active physical arrangement. | `[S]` `main.py:2079-2091`; compare logical→physical backup at `2055-2058` | One click can lose a tuned 2×2 mount. |
| C11 | Bulk physical arrange sorts by UUID, builds one row, and hard-codes `mount_angle: 0`. | `[S]` `frontend/controller/physical.js:3095-3115` | A 2×2 of landscape tablets is scrambled and wrongly rotated until every tile is fixed by hand. |
| C12 | Two manual adds place the first two tablets at the same coordinates. | `[S]` `frontend/controller/physical-stage.js:737-751` (`count % 3`, offset 0 for both 0 and 1) | Overlap is mistaken for a rendering bug. |
| C13 | Logical Tile defaults to 3 columns × 2 rows, gap 20, “Keep screen shape”, and writes one placement per tablet. | `[S]` `frontend/controller/index.html:463-479`, `controller-stage.js:996-1018`; `[Sim]` Opus measured 667×500 footprints with 167-unit dead bands | First-try gaps and up to four repaints; a mid-way failure leaves a partial layout. |
| C14 | Model matching is a signature hint, but a unique match is applied automatically; uncertainty and inset assumptions are not shown as trust state; non-fullscreen inset is centred by assumption. | `[S]` `tabletwall/tablet_models.py:23-33,123-126`, `main.py:961-971`; `[H]` other iPads share the 768×1024@2 signature | A wrong iPad can silently receive Air 2 scale, and a model plan looks as trustworthy as a ruler plan. |
| C15 | Wall-health summary validates the latest profile/calibration pair, not the revisions pinned by the active slot. | `[S]` `frontend/controller/physical.js:501-519` | A valid pinned slot can show “needs calibration”; an invalid one can show healthy. |
| C16 | No `/healthz`, logs are appended without rotation, the service unit is a placeholder, and backup recency/restore rehearsal is not visible. | `[S]` `deploy/hotspot.py:252`, `deploy/tablet-wall.service.example`; grep finds no `healthz` | Restart, disk growth, and recoverability depend on developer memory. |
| C17 | The physical console polls playback every 1 s and roster/config every 5 s instead of using the v3 controller socket. | `[S]` `frontend/controller/physical.js:3440,2491-2520` | Harmless at four tablets; unnecessary latency and load for a console left open all day. |
| C18 | No physical-path hardware evidence exists. Video/playback code is unvalidated on tablets. | `[U]` trials were logical; `[S]` all eight gates MISSING | “Physical spanning works” and any video claim are currently unsupported. |
| C19 | An empty physical draft can replace a populated logical wall through the default Apply path. | `[S]` server accepts empty `slots`; Opus observed the seeded draft `[Sim]` | One click destroys a working wall; a backup exists but the trap is still real. |
| C20 | The ruler overlay caps each line at 200 CSS px, so a 1 mm error can extrapolate to ~3.8 mm on a 768 px panel. | `[S]` `frontend/client/ruler.js:33-34`; `[H]` arithmetic per DeepSeek | The current method may not reach the 2 mm target; the uncertainty must be visible. |

**Resolved defect claims.** The false protocol-3 “not confirmed” alarm (Opus B1)
is fixed. Diagnostics-with-uploads-disabled (Opus B6, Sol, Terra, DeepSeek) is
fixed. The claim that the current Forget route protects an online device is
**false**: `DELETE /devices/{id}` closes an online socket and removes it. TWR-08
therefore *adds* an offline-only protection as a deliberate contract change; it
does not "keep" an existing one `[S]` `main.py:1029-1073` `[D]`.

### 4.4 Live integration state at drafting (time-stamped, not a milestone claim)

The integration branch moved while this document was being written. A reviewer
must re-run the checks rather than trust this subsection as current.

Observed on 2026-11-01 at `18afa5c`:

| Check | Command | Result |
| --- | --- | --- |
| JavaScript suites | `node --test tests/*.test.js` | Pass, `fail 0` (all suites, ~2.7 s) |
| Protocol-3 capability contract | `node tests/controller_image_capability.test.js` | Pass (50 roster cases) |
| Focused Python | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_v3.py tests/test_tablet_models.py tests/test_ingress.py tests/test_field.py` | **61 passed, 1 failed** |
| Isolated regression | `... tests/test_tablet_models.py -k rotation` | Reproducibly fails |

**The red test.** `tests/test_tablet_models.py::test_rotation_matches_render_and_playback_and_keeps_revision_pin`
asserts that the static render frame's calibration metadata equals the playback
plan's calibration metadata. With the capability fence from `abb9c42`, the test's
device record (which advertises no caps) makes `_render_frame` return
`needs_calibration` with `reason: "tablet does not advertise image support"`,
while `_physical_plan_for` still returns a `valid` calibration. The fence is
applied to the static frame and not to the playback plan.

This is an open integration item, not a reason to revert the fence (the fence is
desired: never send an image descriptor to a non-image client). It is assigned
to **TWR-01**, which must either apply the same capability decision to the
playback plan or make the difference explicit and tested; **TWR-06** must not
use playback readiness as a substitute for static render evidence.

**Rule:** this document does not call the branch green while this test is red.
TWR-01's acceptance requires the focused suites to pass and the static/playback
capability decision to be recorded. If a later commit fixes it, record the commit
and result here or in `VERIFICATION.md`; do not delete the failure history.

**Resolution at `3f9beee`.** The rotation fixture now explicitly represents an
image-capable endpoint. `_physical_plan_for` remains a geometry helper; the
actual prepared-image send boundary now refuses devices without `image`, just
as static delivery does. Its new regression cases failed before the guard and
pass afterward. The v3, model, and playback HTTP suites passed together
(52 tests). This preserves the rotation/revision-pin assertions and does not
establish usable playback or video.

---

## 5. Target operator journey

The journey is image-first. Every step must be possible from one operator
surface; nothing requires knowing which of two applications owns a concept.
Acceptance for the whole journey is TWR-14; individual steps are owned by the
packages named.

| Step | Today | Target | Owning package |
| --- | --- | --- | --- |
| **1. Start** | `make hotspot` in a terminal; address printed; no QR, no readiness block. | Supported profile starts (or documented boot unit), console shows tablet origin, Wi-Fi name, readiness, data paths, backup age, and the active layout/scene. | TWR-13 (with TWR-03 read model) |
| **2. Join** | Type the URL; device appears as `#N`; registration is open; model may be auto-applied. | Scan a QR or copy the exact URL. Tablet shows a large number and join state. Console offers “New tablet #N — confirm model or measure”. | TWR-13 (QR), TWR-11 (model confirmation), TWR-08 (label) |
| **3. Identify and name** | Logical calibration scene or a local HUD only. | Identify draws a bounded large number/name over the current image and returns to it. A durable human label is stored; `#N` remains a lease/diagnostic. | TWR-08 |
| **4. Arrange** | Six overlapping verbs; UUID order; 3×2 gap 20 default; sequential writes. | Choose 2×2 or 1×4 (rows × columns), number order, edge-to-edge bodies, explicit orientation, preview, one Apply, one revision. Offline reservations stay visible and intentional. | TWR-10 |
| **5. Show** | Physical console cannot select a still. Legacy page reports a synthetic wall. | One Content surface: Images / Colour / Test pattern. Choose Fill or Fit whole image. Preview the source, screen coverage, bezels, gaps, and crop. Apply once. | TWR-03, TWR-04, TWR-05 |
| **6. Confirm** | Online is treated as healthy. | Each tablet says loading, showing rev N, failed (reason), hidden, blocked, or stale; a header reads “N of M showing”. Only matching current acknowledgements count. | TWR-06 |
| **7. Switch** | Saved layouts exist but cross-kind recall can discard the other arrangement. | Save “Four square” / “Four wide”. Recall previews participating devices and crop change. Every cross-kind switch writes a named return point in the same commit or refuses. | TWR-09, TWR-10 |
| **8. Recover** | Offline/failed/blocked are not distinguished; no retry; no resume probe; 401 loops. | One card, one cause, one next action: Retry image, Reconnect, Confirm model, Rotate, Replace identity, Sign in again. Resume and network return trigger re-registration. | TWR-06, TWR-07 |
| **9. Remove or forget** | Physical mode cannot forget; “delete from wall” is not roster removal. | Separate verbs: Remove from wall (keeps tablet and saved layouts), Forget (offline roster removal with impact preview), Revoke (security, only with pairing). | TWR-08 |
| **10. Stop / hand over** | Ctrl+C; blanking exists only as colour content; backup is a separate CLI. | Blank the wall without losing state; a known exit path from kiosk; verified backup and a written start/stop/restore procedure. | TWR-04 (blank), TWR-13 (procedure) |

**Journey invariant `[D]`:** the tablet is an output. No editing control is
added to the wall client. Setup, Identify, and retry are transient operator
commands; they never become saved content modes.

---

## 6. Data model and technical contracts

Field-level detail is normative in [ARCHITECTURE.md](ARCHITECTURE.md). This
section states the model the roadmap accepts and the rules a reviewer can test.

### 6.1 Domain vocabulary

| Concept | Meaning | Key rule |
| --- | --- | --- |
| **Browser identity** | Origin-scoped UUID stored by the tablet browser. Today it is the layout key. | It is an identity key, not a credential. Origin change loses it. |
| **Installed tablet** | A durable installation concept independent of the browser UUID. | **Future** (Architecture option B). Not in this milestone; rebind repairs snapshots explicitly instead. |
| **Display number** | Leased small integer (`#N`) used for ordering and human matching. | Recyclable after an offline interval; never presented as a permanent ID. |
| **Label** | Optional durable human name (“Upper left”), ≤ 80 characters, duplicate-allowed. | Survives restart and reconnect; registration cannot overwrite it. |
| **Layout** | Logical (unit dimensions, placements) or physical (mm bounds, slots with pinned revisions). | Kind is explicit; both remain supported. No guessed unit→mm conversion. |
| **Slot / placement** | One tablet's position, size/mount, and participation in the active layout. | Physical slots pin profile and calibration revisions. |
| **Arrangement / saved layout** | A named snapshot of one layout kind. | Recall is previewable; cross-kind recall requires a safety copy. |
| **Scene** | What the wall shows: colour, logical calibration, or image with fit/background. | Separate from layout and from playback. One commit path. |
| **Fit** | `cover` (Fill, default) or `contain` (Fit whole image), global to the wall. | Never per-tablet; a per-tablet fit destroys continuity. |
| **Render evidence** | Bounded acknowledgement that one connection attempted/ completed a paint for one token. | Proves application intent, not photons. Never inferred from presence. |
| **Mapping status** | Why a tablet can or cannot receive a correct frame (ready, unplaced, needs calibration, viewport mismatch, zoom changed, unsupported content/client). | Derived from pinned revisions and live viewport; never from the latest profile. |
| **Presentation owner** | `static` or experimental `playback`. | Static image is the product; playback is opt-in and visually secondary. |

### 6.2 Type sketch (accepted shape)

```text
Layout = LogicalLayout | PhysicalLayout

LogicalLayout  = { kind:"logical", width:Int>0, height:Int>0,
                   placements:Map<UUID,Placement>, sizing:Sizing }
Placement      = { device_id:UUID, x:Int, y:Int, w:Int>0, h:Int>0,
                   bezel:{left,right,top,bottom:Int>=0} }

PhysicalLayout = { kind:"physical", bounds:{x,y,width>0,height>0},
                   slots:Map<UUID,Slot>, sizing:Sizing }
Slot           = { center_x_mm, center_y_mm:Finite,
                   mount_angle:FiniteDegrees,
                   nudge_x_mm, nudge_y_mm:Finite,
                   profile_revision:Int>0, calibration_revision:Int>0,
                   participating:Bool }

Sizing  = { mode:"fixed"|"tablets", padding:Finite>=0 }
Scene   = { layout:"active", content:Color|Calibration|Image }
Image   = { type:"image", asset:AssetID, fit:"cover"|"contain",
            background:HexRGB, intrinsicWidth:Int>0, intrinsicHeight:Int>0 }

OperatorConfig = { schema:2, operator_state_version:1, generation, revision,
                   etag, layout, scene, displays, calibrations,
                   referenced_displays, referenced_calibrations,
                   tablet_models, tablet_assignments,
                   device_labels, snapshots, capabilities, runtime }

DeviceStatus   = { online, last_seen, protocol, caps, number, label,
                   viewport, wake_lock, mapping:MappingStatus,
                   render:RenderStatus, identify:IdentifyStatus|null }

RenderToken    = { connection_id, generation, revision, render_seq,
                   mapping_revision, asset:AssetID|null }
RenderAck      = { type:"render_ack", token, report_seq,
                   status:"loading"|"displayed"|"failed"|"hidden"|
                          "blocked"|"unplaced"|"unsupported",
                   reason:null|"fetch"|"decode"|"size"|"surface"|
                          "transform"|"calibration"|"viewport"|"zoom"|
                          "no_slot"|"capability"|"auth"|"playback",
                   viewport, visible:Bool }

GridCommand    = { kind, device_ids[], rows, columns, gap, padding,
                   sizing, orientation:"preserve"|"auto"|"portrait"|"landscape",
                   mount_angles?, logical_sizes?, physical_revisions?,
                   allow_empty_cells, release_unselected[], guards? }
```

`[D]` `schema: 2` remains the storage/config marker. `operator_state_version: 1`
is an additive contract marker. Protocol major 3, database schema version 3,
and operator-state version are three different values and must not be conflated.

### 6.3 Commit and readback rules

1. **Proposal → validate → persist → apply memory → notify.** No notification
   before the durable commit. A failed write is a 5xx with no partial memory or
   successful notification (`[S]` existing `_commit_wall`).
2. **Readback has no side effects.** Building a config response must not call
   `_render_frame` or advance `render_seq`. Read cached expected metadata or a
   pure mapping helper `[D]`.
3. **ETag discipline.** New mutations require `If-Match`. Missing is 428; stale
   or failed preview guard is 412; invalid field/asset/revision is 422; absent
   entity is 404; live conflict is 409 with structured `detail`
   `{code, message, conflicts}`. The durable ETag covers generation, revision,
   layout, scene, relevant profile/calibration records, assignments, labels,
   and saved-snapshot digests — not heartbeats, sockets, numbers, or current
   time.
4. **No await after the last guard.** Re-check ETag and live guards after any
   asset/decode await, immediately before the synchronous transaction.
5. **One write per operator intent.** A grid apply writes one layout, bumps the
   revision once, and broadcasts once. No per-tablet placement loop.
6. **Cross-kind safety.** Applying or recalling across logical/physical writes a
   named return point in the same transaction. If the return point cannot be
   written, the switch is refused.
7. **Draft semantics.** Preview is pure; Apply is atomic; Cancel changes
   nothing. A dirty draft survives polling with its old ETag and a visible
   conflict message.
8. **Compatibility.** Legacy logical documents without `kind` project as
   logical. Missing sizing projects as fixed/0; missing fit projects as cover;
   missing background uses the current renderer's background colour, copied as a
   literal. Missing bytes keep ID/dimensions and project unavailable — never a
   colour scene.

### 6.4 Operator endpoint contract (accepted subset)

| Endpoint | Contract | Package |
| --- | --- | --- |
| `GET /api/v3/config` | Authoritative operator read: layout kind, projected scene, devices, labels, snapshots, capabilities, runtime, ETag. | TWR-03 |
| `PUT /api/v3/scene` | Validate/normalise asset and fit; commit content once; stop experimental playback; broadcast static state; return config. | TWR-03/04 |
| `PUT /api/v3/layout` | Existing physical body; validate and commit through the common replacement function. | TWR-03/10 |
| `PUT /api/v3/logical-layout` | Atomic whole logical draft; kind remains explicit. | TWR-10 |
| `POST /api/v3/grid/preview` | Pure preview: layout, order, warnings, input guards, base ETag. No writes or sends. | TWR-10 |
| `POST /api/v3/grid` | Revalidate and commit the previewed grid once. | TWR-10 |
| `POST /api/v3/layouts/{name}/recall` and `POST /api/v3/logical-layouts/{name}/recall` | Recall with the common safety-copy path. | TWR-09 |
| `GET/PUT/DELETE /api/v3/scenes[/{name}]` | Scene snapshots with ETag guards and digest readback. | TWR-09 |
| `PATCH /api/v3/devices/{id}` | Durable `label` only. No layout/content change. | TWR-08 |
| `POST /api/v3/devices/{id}/identify` | Transient bounded overlay; no scene or revision change. | TWR-08 |
| `POST /api/v3/devices/{id}/retry-image` | Fresh render token for the same content; no wall revision. | TWR-06 |
| `POST /api/v3/devices/{id}/reconnect` | Close the owned socket normally; identity preserved. | TWR-07 |
| `POST /api/v3/devices/{id}/rebind/preview` | Read-only impact, conflicts, revision maps, label/number outcome. | TWR-09 |
| `POST /api/v3/devices/{id}/rebind` | Apply exactly the previewed selection in one transaction. | TWR-09 |
| `DELETE /api/v3/devices/{id}` | Offline-only Forget with impact guards; never deletes measurement history or saved layouts implicitly. | TWR-08 |
| `GET /healthz` | Readiness only: schema, generation/revision, counts, storage readable. Operator-admitted. | TWR-13 |
| `GET /diagnostics` | Storage/integrity detail, independent of upload admission. | TWR-02 (landed) |

The compatibility `DELETE /devices/{id}` must adopt the new Forget semantics
explicitly, with updated tests, rather than retaining a second lifecycle
meaning `[D]`.

### 6.5 Render-evidence contract

- Additive caps `render_ack`, `identify`, `image_contain` on protocol 3. Keep
  `image` basic. Old clients stay compatible but report `unknown`/`unsupported`,
  never “healthy”.
- Every static instruction carries `RenderToken`; `render_seq` advances on every
  instruction and retry. `connection_id` is the server's per-socket UUID in the
  v3 welcome — an identity fence, not a secret.
- Accept an ack only if: the sending socket still owns the device and matches
  `connection_id`; the full token matches the latest expectation, including
  asset/null; generation and revision are current; `report_seq` is strictly
  increasing; the report is ≤ 4096 bytes; enums and numbers are valid.
- `displayed` requires a ready mapping, image capability, positive surface,
  matching validated viewport, `visible: true`, and no active experimental
  presentation. A decoded cache entry alone is not `displayed`; paint plus a
  subsequent animation-frame callback owning the token is.
- Evidence is process-local, bounded, cleared on disconnect/replacement/
  Forget/rebind, never persisted in roster metadata. Nothing older than the
  15 s heartbeat timeout counts as current.
- Aggregate “N of M showing” counts only current matching acknowledgements for
  expected participating placed devices, including offline reservations. Zero
  participants means “No tablets on the wall”.
- A client-only zoom/visibility guard can make a report less healthy; it cannot
  override a server mapping fence.
- Attempting to display `image` to a client without the capability is
  `unsupported`, never green.

### 6.6 Grid contract

- `2×2` means two rows and two columns. `1×4` means one row and four columns.
  `4×1` is a vertical stack and is not a primary preset.
- The submitted `device_ids` array is the sole order of record, laid out
  left-to-right, top-to-bottom. The UI pre-sorts by valid number, then label,
  then UUID, and offers Move earlier/later. The server must not resort by UUID
  or by a number lease that changed after preview.
- Require exactly `rows × columns` devices unless `allow_empty_cells` is
  explicit. Reject duplicate/unknown IDs, empty selection, excess capacity,
  non-integral logical sizes, and insufficient cells.
- IDs in the current arrangement but absent from the command must appear in
  `release_unselected`, or the command returns 409 naming the reservations that
  would be lost. Selected offline reservations are included with stored sizes
  and revisions. Auto-orientation of an offline tablet is refused.
- Physical mode uses measured bodies including bezels; `gap` is extra space
  between bodies. Gap zero already includes adjacent bezels; never add them
  again. Preserve nudges and participation.
- Mount angle, panel orientation, browser orientation, and launch mode are four
  distinct inputs. Auto-orientation needs a fresh viewport and a confirmed model
  or explicit mount information. Manual calibrations never imply a wall mount.
- Mixed body sizes may leave honest holes; preview them. Only equal,
  aspect-matched bodies in a complete grid can promise full rectangular
  coverage.
- An empty physical draft cannot replace a populated logical wall through the
  default Apply. Clear wall is a separate explicitly confirmed operation.

### 6.7 Identity and rebind contract

- `label` is durable, normalised (outer whitespace trimmed, 80-character cap,
  control characters rejected, empty clears to null), duplicate-allowed, and
  rendered via text nodes.
- Identify is a transient command with `command_id`, target `connection_id`,
  server send time, deadline, duration (default 5000 ms, bounds 1000–10000 ms),
  label, and current number. A newer Identify replaces the old one; it is not
  replayed after reconnect; expiry reveals the latest scene.
- Remove from wall changes only the active arrangement. Saved layouts and the
  roster remain. Offline placements are reservations and have the same action.
- Forget requires the owned socket to be absent (not merely an old heartbeat),
  shows an impact preview, removes the roster entry and active entry if
  confirmed, releases the number/label, and returns the saved-layout names that
  still reference the old UUID. It keeps snapshots and measurement history
  intact as visible reservations. **Forget is not revocation.**
- Rebind declares `same_hardware` or `different_hardware`. Never copy
  measurements from a different physical tablet on a model-name guess. The
  preview lists affected active and saved layouts, conflicts, and revision
  maps; apply is one transaction; rollback on any failure.
- A stable installed-tablet registry (Architecture B) is deferred until repeated
  rebind cost is measured. This milestone keeps UUID keys and explicit repair.

### 6.8 Fit and crop contract

- `cover` (Fill) stays the default for a calibrated wall. `contain` (Fit whole
  image) shows every source edge and uses an explicit letterbox background.
- Fit is global. The same fit drives scene validation, persistence, static
  rendering, future playback plans, and preview. Never fit per tablet.
- The preview shows: the uncropped source, the wall rectangle, bright tablet
  faces, hatched bezels/gaps, and the part of the source that is off-wall versus
  merely hidden behind hardware. Those are different losses and must be
  distinguished in text, not only colour.
- A focal point for Fill is deferred until basic Fill/Fit works.
- `contain` adds bars; it does not remove bezel occlusion. Say so.

### 6.9 Capability and versioning

- Protocol 3 advertises capabilities explicitly. Capability is necessary, not
  sufficient: it says the client can attempt an image, not that it painted one.
- Server-side rendering must not send an image descriptor or plan to a client
  without `image`. That fence is implemented (`abb9c42`) and must remain.
- Unknown capability is `unknown`, never “not capable” and never “healthy”.
- Operator state is additive; absent fields project documented defaults.

### 6.10 What is deliberately not modelled

No persistent mode state machine for Identify/setup/blank; no per-tablet content
assignment; no scene graph; no plugin system; no second content store; no
distributed presence. These add failure modes without serving the four-tablet
image wall `[D]`.

---

## 7. Security, trust, power, and privacy constraints

### 7.1 Supported profiles

| Profile | Shape | Capabilities | Prohibitions |
| --- | --- | --- | --- |
| **A. Supervised hotspot (HTTP)** | `make hotspot`; tablet ingress on the hotspot; operator on loopback | Open registration, register, socket, client files, assets; uploads off; diagnostics operator-only; start-up ingress denial checks | No wake lock (insecure context); no uploads; no phone controller over the hotspot; not safe on shared/venue Wi-Fi; do not call it authenticated |
| **B. HTTPS / kiosk reference** | Two-origin Caddy with operator auth and CA trust | Auth, secure context, possible wake lock on capable browsers `[H]` | Origin change resets identities; needs trust installation and rebind planning; not validated on the installed tablets yet |
| **C. Untrusted / shared LAN** | Not supported by profile A | Requires TWR-15 (approved join + per-device credentials + revocation) and rate limits | Must not be run on an untrusted network before TWR-15 |

`[D]` The demo uses **A** only. The HTTPS migration is chosen deliberately, not
as an incidental step, because changing origin wipes browser identity and
(saved layouts are keyed by it).

### 7.2 What is and is not authentication

- A browser UUID is an identity key, not a credential. A peer that knows it can
  claim the device socket (last-socket-wins).
- The exact-origin check is a request fence (CSRF-class), not authentication.
- The optional app shared secret protects all routes when enabled; the reference
  two-origin proxy authenticates the operator separately. Combining them without
  an integration test for registration, assets, and WebSockets is prohibited.
- The tablet route allowlist limits *routes*, not *who* may call them.
- Served image bytes are readable by any admitted tablet on the tablet network.
  State that plainly; do not upload private material to a shared hotspot.
- `#N` and a visible label are not credentials and never become one.

### 7.3 Paired admission (TWR-15) — conditional, not default

Trigger conditions, any one of which justifies the work:

1. the wall runs on a network where peers are not fully trusted;
2. an operator other than the owner can reach the hotspot;
3. a lost/stolen tablet must be prevented from reclaiming its slot;
4. the deployment moves to HTTPS with a stable origin and a real device
   credential is practical.

Contract outline: short-lived join approval; server-issued per-tablet credential
stored outside URLs and logs; reconnect without a human; explicit reauthorization
after storage loss; revocation that cannot be undone by replay; request and
connection limits; pairing over TLS (or an explicit, written acceptance of the
plain-HTTP boundary). If none of the triggers applies, TWR-15 stays `Deferred`
and profile A stays honest about being unauthenticated.

### 7.4 Auth expiry recovery (TWR-07)

- A wall must not depend on a 12-hour operator cookie for its lifetime.
- Until durable device credentials exist, an expired session must produce a
  visible “Sign in again” action or navigation — never indefinite silent retry.
- The tablet allowlist now serves the exact login entry points (`15e21f6`).
  Verify redirect behaviour with auth enabled in an isolated profile.
- Do not put credentials in URLs, logs, screenshots, or the repository.

### 7.5 Ingress and operator boundary

- Keep the tablet listener allowlist and the loopback operator listener.
- Keep the startup checks that prove operator routes answer 403 on the tablet
  port and the WebSocket upgrade works; extend them for new routes.
- Verify from a *separate* tablet-network peer that the backend and operator
  ports are unreachable. A local curl is not that check.
- Firewall rules opened by the launcher are recorded and removed on exit or the
  next start. Preserve that ownership logic.
- Do not install services, change firewall rules, or alter live networking
  during implementation. Those are operator actions in TWR-17.

### 7.6 Page and API hygiene

- Add conservative headers to controller/client pages: a tested
  `Content-Security-Policy` (`default-src 'self'`, `frame-ancestors 'none'`),
  `X-Content-Type-Options: nosniff`, and a referrer policy. Test against local
  scripts, blob images, SVG, and WebSockets; do not copy a generic policy.
- Keep secrets outside the checkout with restricted permissions.
- Protect backup destinations; a backup contains the database and referenced
  images. A manifest records hashes, not paths.
- Dependency review and rate limiting at the proxy are normal maintenance.
  Application-level rate limiting is deferred until the threat model requires it
  (TWR-15), because a home-grown limiter adds a failure mode first.

### 7.7 Privacy

No telemetry, cloud sync, remote access, or diagnostics upload. Diagnostics are
local reads. Backups stay local unless the operator moves them. Evidence
artifacts (screenshots, logs, photos) may contain the displayed image and device
names; treat them as private to the installation.

### 7.8 Power, sleep, and kiosk reality

| Capability | Reality | Consequence |
| --- | --- | --- |
| Screen Wake Lock | Requires a secure context; profile A reports `insecure`. `[H]` iPadOS 15.8 Safari predates the API, so HTTPS may not help the Air 2. | Do not promise wake lock. Use OS settings and Guided Access / developer “stay awake while charging”. |
| Remote wake/unlock | A web page cannot power on or unlock a tablet. | Recovery instructions must be physical. A black image is blanking, not power control. |
| Fullscreen | Requires a tablet gesture; may not survive reload. | Provide a first-run prompt/instructions; do not make fullscreen a correctness dependency. |
| Background/foreground | OS may freeze the page and the socket may die without a close event. | TWR-07 adds resume probes; TWR-17 observes what a real iPad/Pixel C does. |
| Auto-lock | OS-controlled. | Operator checklist: longest timeout or never while charging; Guided Access; fixed brightness. |

`[D]` No package may claim “keeps the wall awake” from web code alone.

---

## 8. Efficiency and capacity policy

### 8.1 Rule

**Measure before optimising.** No optimisation merges without (a) a recorded
baseline, (b) a named bottleneck it addresses, and (c) a before/after comparison
under the same conditions. No latency, throughput, memory, battery, or capacity
number may be invented.

### 8.2 What to measure (TWR-16)

| Metric | Method | Why |
| --- | --- | --- |
| Time to painted per tablet | Render-ack receipt time minus instruction send, p50/p95, for 1 and 4 tablets | Distinguishes network, decode, and paint cost; gates any rendition work. |
| Writes/broadcasts per operator intent | Count commits and broadcasts for a 2×2 grid apply | Confirms the atomic path replaced the 4-write loop. |
| Controller request rate | Count HTTP requests for 5 minutes idle, socket vs polling | Decides whether polling replacement is justified. |
| Payload bytes per wall change | Snapshot size and asset bytes delivered | Detects accidental re-downloads; assets are immutable and cached. |
| Asset inventory cost | Time a library listing with a representative library | Decides whether hash scanning matters at this scale. |
| Log growth | Bytes/day under an idle wall | Justifies rotation policy. |
| Decode/memory on old tablets | Device probe where available; otherwise record as unmeasured | `[H]` 2 GB iPads may struggle with large sources. |

### 8.3 Known costs, with dispositions

| Observation | Evidence | Disposition |
| --- | --- | --- |
| Four sequential placement writes → four revisions/broadcasts | `[Sim]` Opus | TWR-10 makes it one write. |
| Every tablet downloads and decodes the full source; a 2.7 MiB 4000×3000 sample exists | `[Sim]` Opus; `[S]` decode path | Measure first (TWR-16). Per-slice/per-device renditions deferred. |
| Synchronous SQLite reads per v3 device during broadcast | `[S]` `hub.py` | Unmeasured at 4–20 tablets. Do not optimise. |
| ETag rebuild/hash on each v3 write | `[S]` `main.py:1905-1917` | Unmeasured. Do not optimise. |
| Console polls 1 s/5 s | `[S]` `physical.js` | TWR-16 measures; replace with the v3 socket only if the measurement supports it. |
| Sequential broadcast sends | `[S]` `hub.py:126` | Unmeasured. Instrument send failures/durations before changing concurrency. |
| Curated inventory scans/hashes files | `[S]` `assets.py:161` | Measure at realistic library size; prefer managed media later, never weaken byte verification. |
| Playback loop swallows exceptions | `[S]` `main.py:2503` | TWR-13 adds bounded logging/fault visibility while preserving isolation. |

### 8.4 Forbidden without new evidence

- A second mutable cache or a “measurement snapshot cache”.
- Database server, WAL tuning, or multi-worker state.
- Pre-sliced renditions, a transcoder, or a media pipeline.
- Canvas/WebGL rewrites.
- Capacity claims above the tested fleet.

Capacity target remains 4–20 tablets as a trial target, not a proven envelope.
Hotspot capacity on the intended hardware is unmeasured `[H]`.

---

## 9. Phases and work packages

Seventeen bounded packages across six phases. A package may span features; it is
the unit of review and evidence. Status is `Open` unless stated. No package may
be marked complete by another package's evidence.

Dependency graph in words: P0 truth baseline → P1 console/content → P2
per-tablet truth → P3 identity/arrangements → P4 calibration trust → P5
operability/security/UI acceptance → P6 hardware evidence. TWR-16 depends on
TWR-06/10/14 for its measurements. TWR-15 is conditional.

### Phase P0 — Truth baseline

#### TWR-01 — Protocol 3 capability truth · Issue [#8](https://github.com/spicyneutrino/tablet-wall-ai/issues/8)

**Status:** Open — merged, acceptance pending.
**Depends:** none.
**Purpose:** Stop treating an image-capable protocol-3 tablet as unknown or
incapable, without implying that it painted anything.
**In scope:** logical capability check; physical capability fence; protocol
documentation; cap chip wording.
**Out of scope:** render acknowledgement (TWR-06); any claim of paint health.
**Acceptance:**
- A1. Four protocol-3 `image`-capable online tablets produce no “Placed, not
  confirmed” alarm and no “unknown” chip. `[T]` `tests/controller_image_capability.test.js`
  plus the rendered case in TWR-14.
- A2. Protocol 1, protocol 2 without `image`, and missing-caps cases still warn
  or read unknown appropriately.
- A3. A physical plan/descriptor is never sent to a non-image device.
  `[T]` `tests/test_v3.py` capability cases.
- A4. Documentation states protocol 2 or 3 plus `image`.
- A5. Static frames and playback plans use the same capability decision, or the
  difference is explicit and tested. `[T]`
  `tests/test_tablet_models.py::test_rotation_matches_render_and_playback_and_keeps_revision_pin`
  passes at the accepted commit; see §4.4 for the red state observed during
  drafting.
**Evidence:** commit `5a9cc29`, `ef99cb8`, `abb9c42`; test output; TWR-14
screenshot of a four-tablet roster.
**Deviation to record:** implemented chip text is “Image capable”, not the
report's “Shows images”. Acceptance is behavioural, not the label.

#### TWR-02 — Diagnostics admission and tablet sign-in routes · Issue [#9](https://github.com/spicyneutrino/tablet-wall-ai/issues/9)

**Status:** Open — merged, acceptance pending.
**Depends:** none.
**Purpose:** Make operator diagnostics work in the supported upload-disabled
profile, and let a tablet reach the login page without widening the operator
surface.
**In scope:** independent operator-read admission; exact auth entry points on
the tablet allowlist; denial tests.
**Out of scope:** durable device credentials (TWR-15); client 401 UX (TWR-07).
**Acceptance:**
- A1. `GET /diagnostics` succeeds for a loopback operator with uploads
  disabled; the tablet listener is refused. `[T]` field/ingress/deployment
  suites.
- A2. The tablet allowlist admits only the exact login/logout routes and strips
  the internal operator credential.
- A3. A direct login visit returns to `/client/`.
- A4. Existing operator-route denials and WebSocket upgrade checks still pass.
**Evidence:** `15e21f6`; focused test counts; a rendered “Field check” result in
TWR-14.

### Phase P1 — One truthful image console

#### TWR-03 — Authoritative operator state · Issue [#10](https://github.com/spicyneutrino/tablet-wall-ai/issues/10)

**Status:** Open.
**Depends:** TWR-01, TWR-02.
**Purpose:** Make one response tell the truth for both layout kinds: what is
active, what image and fit are showing, which revision is committed, and what
each tablet's mapping/render state is.
**In scope:** `operator_state_version: 1`; scene projection; labels; snapshots;
capabilities; runtime status; durable ETag; v3 socket parity; legacy defaults.
**Out of scope:** mm-only migration; a second state object; persisted render
evidence.
**Acceptance:**
- A1. With a physical wall active, config reports `kind:"physical"`, the real
  slots, the real scene asset/fit, and the committed revision. No synthetic
  2000×1000 wall appears as current truth. `[T]` API test; `[P]` probe.
- A2. `PUT /api/v3/scene` on a physical wall returns the same scene it committed.
  A subsequent config GET agrees. The legacy `PUT /scene` refuses physical
  mode with an upgrade conflict and no mutation; it never returns a colour
  substitute after committing an image.
- A3. A legacy v2 controller receives an explicit compatibility view or an
  explicit upgrade state — never a plausible but false wall.
- A4. Readback does not advance `render_seq` or mutate state. `[T]` call twice,
  compare.
- A5. ETag changes for durable changes (layout, scene, label, saved snapshot) and
  not for heartbeats, sockets, numbers, or time. `[T]` table-driven cases.
- A6. Missing legacy fields project the documented defaults.
**Evidence:** focused API tests; probe transcript; rendered header showing
layout kind, scene, and revision.

#### TWR-04 — Still-image control, library, and legacy fence · Issue [#10](https://github.com/spicyneutrino/tablet-wall-ai/issues/10)

**Status:** Open.
**Depends:** TWR-03.
**Purpose:** Let the primary console show a still image, a colour, or a test
pattern without the experimental playlist, and stop the legacy page from
pretending to be the layout editor.
**In scope:** image/colour/test-pattern selection; active-content card; curated
plus admitted managed library browsing; honest upload state; hotspot copy-path
message; “Blank wall”; experimental playback moved behind an explicit switch;
legacy banner/redirect for physical layouts.
**Out of scope:** library delete/rename (deferred); uploads in hotspot mode;
playback expansion; visual redesign.
**Acceptance:**
- A1. On a physical wall, choose image A then B in one console; the console names
  B with its crop; tablets receive B; reload shows B. `[Sim]` four headless
  clients + desktop controller.
- A2. Colour and Blank wall change content and restore the prior image without
  losing layout.
- A3. With uploads disabled, the console shows the copy-to-directory instruction
  and no upload form; with uploads enabled on the operator path, upload
  progress/rejection is visible.
- A4. Experimental playback is not in the top bar and starts only after an
  explicit switch plus a second confirmation.
- A5. The legacy page on a physical wall shows a hard banner or redirects; it
  cannot silently display a different scene.
- A6. Missing asset bytes show unavailable, not colour.
**Evidence:** browser screenshots (desktop and phone), network log, API tests for
scene validation.

#### TWR-05 — Whole-image fit and truthful crop preview · Issue [#11](https://github.com/spicyneutrino/tablet-wall-ai/issues/11)

**Status:** Open.
**Depends:** TWR-03, TWR-04.
**Purpose:** Make loss visible and intentional before Apply.
**In scope:** `contain` through validation, persistence, static client, physical
plans, preview; global fit; letterbox background; source coverage, bezel/gap
hatching, off-wall versus occluded distinction; source-pixels-per-tablet
estimate; orientation/shape warning.
**Out of scope:** per-tablet fit; focal point; per-slice renditions; automatic
rendition generation.
**Acceptance:**
- A1. A marked-border source keeps its border under Fit on a 1×4 wall; Fill
  crops predictably. `[Sim]` + geometry test.
- A2. `contain` is accepted by the API, persisted, survived by restart, and
  rendered identically by client and preview.
- A3. Preview geometry matches the client's slice within 1 logical unit (or
  0.5 mm physical) in a fixture test. `[T]`
- A4. Preview distinguishes off-wall crop from bezel/gap occlusion in text and
  visual treatment, not colour alone.
- A5. A 2000 px source across four tablets shows a visible resolution estimate
  and warning; the arithmetic matches the displayed value.
- A6. Changing layout preserves the chosen fit; changing fit does not change
  layout.
**Evidence:** geometry/preview tests; desktop and phone screenshots; a four-client
simulation showing Fit bars and Fill crop.

### Phase P2 — Per-tablet truth and recovery

#### TWR-06 — Static render evidence and targeted retry · Issue [#12](https://github.com/spicyneutrino/tablet-wall-ai/issues/12)

**Status:** Open.
**Depends:** TWR-03, TWR-04.
**Purpose:** Replace “online therefore healthy” with bounded evidence of what
each tablet attempted and painted.
**In scope:** `render_ack` cap and token; bounded process-local evidence;
stale-report rejection; per-tablet states; header count; retry image; capability
and mapping fences.
**Out of scope:** optical proof; playback readiness reuse; persisted evidence;
any “the person sees it” claim.
**Acceptance:**
- A1. Inject a fetch/decode failure on one tablet; its card names the device and
  the failure reason; it is not counted in “N of M showing”.
- A2. A delayed completion for an old token cannot make the new image look
  healthy. `[T]` stale-ack case.
- A3. `displayed` requires a painted frame plus the animation-frame token check;
  a decoded cache entry alone reports loading. `[T]` client contract test.
- A4. A hidden page reports hidden; on resume it must repaint before green.
- A5. Evidence older than 15 s is stale/unknown, not current. Time is monotonic.
- A6. Retry issues a fresh token, temporarily clears green, and does not bump the
  wall revision or change content.
- A7. A protocol-3 client without `render_ack` reads unknown, not failed and not
  healthy.
- A8. “N of M” denominator includes expected participating placed devices,
  including offline reservations; zero participants reads “No tablets on the
  wall”.
**Evidence:** unit/API tests for token acceptance and rejection; browser test
with four simulated clients, one failed and one offline; screenshot.

#### TWR-07 — Client recovery watchdog and auth-expiry recovery · Issue [#12](https://github.com/spicyneutrino/tablet-wall-ai/issues/12)

**Status:** Open.
**Depends:** TWR-06 (status surface), TWR-02 (login route).
**Purpose:** Make the wall return by itself after a freeze, network return, or
expired session — or tell the operator exactly what manual action is required.
**In scope:** `visibilitychange`/`pageshow`/`online` probes; missed-heartbeat or
stale-socket watchdog; re-registration; viewport resend; visible 401 action;
preserve 4409 takeover semantics; reconnect command.
**Out of scope:** durable device credentials (TWR-15); remote wake.
**Acceptance:**
- A1. Hide/suspend a simulated tablet, drop its socket, restore: it
  re-registers and shows the current slice within 10 s without a manual reload.
  `[Sim]`; real-device outcome deferred to TWR-17.
- A2. A half-open socket with no close event is detected by the watchdog and
  reconnected.
- A3. An expired session produces a visible sign-in action; the client does not
  loop silently.
- A4. A newer tab takes over; the old tab does not steal the identity back in a
  loop.
- A5. Reconnect preserves UUID, label, number, and placement.
- A6. Resume does not replay a stale Identify overlay or a stale render token.
**Evidence:** browser simulation with forced offline/online and forced 401;
recorded time-to-correct; no hardware claim.

### Phase P3 — Identity and arrangements

#### TWR-08 — Labels, Identify, Remove, and Forget · Issue [#13](https://github.com/spicyneutrino/tablet-wall-ai/issues/13)

**Status:** Open.
**Depends:** TWR-03, TWR-06.
**Purpose:** Make a physical installation manageable by name and make the
lifecycle verbs honest.
**In scope:** durable label; rename; transient Identify with expiry; Remove from
wall; offline-only Forget with impact preview and saved-reference reporting;
physical-mode Forget; roster list based on durable entries, not a profile union;
advanced access to measurement history.
**Out of scope:** credential revocation (TWR-15); stable installed-tablet
registry; automatic destructive cleanup.
**Acceptance:**
- A1. Rename a tablet; the label survives restart and reconnect and appears on
  the tablet overlay and in saved-layout references.
- A2. Identify shows the correct number/name on the target within 1 s `[Sim]`,
  leaves content and revision unchanged, and clears on expiry/disconnect.
- A3. Remove from wall frees the slot and keeps the tablet and saved layouts.
- A4. Forget works while a physical wall is active for an offline tablet, after a
  confirmation that names affected references; it does not silently delete
  measurement history or saved snapshots.
- A5. Forget of an online tablet is refused with a clear reason (new deliberate
  guard), and the normal sweeper can close a stale socket first.
- A6. A forgotten tablet's historical measurements do not recreate an active
  card; they stay reachable in advanced details.
**Evidence:** API/lifecycle tests including rollback; browser screenshots of the
confirmation; simulation of Identify timing.

#### TWR-09 — Rebind preview, saved-layout repair, and cross-kind safety copies · Issue [#13](https://github.com/spicyneutrino/tablet-wall-ai/issues/13)

**Status:** Open.
**Depends:** TWR-08.
**Purpose:** Make replacement and cross-kind switching non-destructive.
**In scope:** rebind preview; same/different hardware declaration; transactional
repair of explicitly selected saved layouts; revision maps; conflict reporting;
rollback; safety copy for every cross-kind apply/recall in both directions;
refuse when the copy cannot be written; name the return point in the
confirmation.
**Out of scope:** stable slot identity migration; automatic rewriting of
unselected snapshots; silent measurement coercion.
**Acceptance:**
- A1. Rebind preview lists affected active and saved arrangements, conflicts,
  label/number outcome, and revision maps; it writes nothing.
- A2. Apply changes roster, histories, active placement, and selected snapshots
  in one transaction; any failure leaves all unchanged. `[T]` injected failure.
- A3. After a same-hardware rebind, recalling the saved 2×2 and 1×4 places the
  new identity in the intended slots; the old identity is not resurrected.
- A4. A different-hardware rebind refuses to copy measurements on a name guess.
- A5. Logical→physical and physical→logical apply/recall each create a named
  return point in the same commit; if it cannot be created, the operation is
  refused.
- A6. The response/confirmation names the generated return point; an automatic
  copy is labelled as such, not disguised as an operator layout.
**Evidence:** transaction tests; recall-after-rebind test; browser confirmation
screenshot.

#### TWR-10 — Atomic numbered 2×2 and 1×4 arrangements · Issue [#14](https://github.com/spicyneutrino/tablet-wall-ai/issues/14)

**Status:** Open.
**Depends:** TWR-03, TWR-08.
**Purpose:** Make the advertised quick path actually quick, deterministic, and
seamless.
**In scope:** explicit 2×2 and 1×4 presets (rows × columns); number/label order
with reorder controls; orientation choices and mount/rotation separation;
edge-to-edge packing with bezels; one atomic write; preview/apply/cancel;
preserve offline reservations intentionally; release guard; fix first-two-add
overlap; sensible defaults (four tablets → 2×2, gap 0, fit tablets); empty-draft
guard; participation toggle; remove the legacy sequential tiling path from the
primary flow.
**Out of scope:** 4×1 as a primary preset; automatic flipping without operator
confirmation; whole-draft undo across a rebasing fit (documented limitation).
**Acceptance:**
- A1. Four connected model-assigned tablets apply a 2×2 in number order with one
  revision increment and one broadcast. `[T]` + `[Sim]`.
- A2. A 1×4 applies in number order as one row; orientation matches the explicit
  choice, and mount angle is not hard-coded to 0.
- A3. Sum of widths plus gaps equals the wall width for the tested preset; no
  uncovered band and no shape-mismatch warning for equal aspect-matched bodies.
  `[T]` geometry.
- A4. Two manual adds never overlap; four manual adds form a sensible grid.
- A5. Preview changes nothing; Apply failure leaves the prior arrangement
  intact; Cancel changes nothing.
- A6. Unselected placed tablets require explicit release; the 409 names them.
- A7. An empty physical draft cannot replace a populated wall without a separate
  confirmed clear-wall action.
- A8. Offline reservations are preserved and explained; auto-orientation of an
  offline tablet is refused.
- A9. Keyboard/numeric alternatives exist for reorder and nudge; no drag-only
  action. `[Sim]` + TWR-14.
**Evidence:** grid preview/commit tests; four-client simulation; before/after
revision and broadcast counts; screenshots.

### Phase P4 — Calibration trust

#### TWR-11 — Calibration provenance, pinned health, and wall-sized test grid · Issue [#15](https://github.com/spicyneutrino/tablet-wall-ai/issues/15)

**Status:** Open.
**Depends:** TWR-03, TWR-06, TWR-10.
**Purpose:** Let the operator tell a model guess from a ruler measurement, and
make the health summary describe the *active plan*.
**In scope:** model/manual/unknown provenance; ± uncertainty; assumed inset and
launch mode; live viewport and orientation mismatch warnings; pinned revisions
in health and mapping status; explicit model confirmation (suggestion only);
non-destructive wall-sized test grid generated for committed bounds and served
as an ordinary image; separate logical calibration scene.
**Out of scope:** more built-in models; auto-flip; photo seam checking; new
measurements as a prerequisite.
**Acceptance:**
- A1. A new signature match shows “Looks like X. Confirm?” and does not receive
  physical scale until confirmed. `[T]` model tests updated.
- A2. Every tablet shows provenance: model (approximate, ±3 mm), manual
  (measured, with value), or unknown. A model plan never renders as plain “ok”.
- A3. Health/mapping uses the slot's pinned profile and calibration, not the
  latest pair; a newer saved profile does not mark a valid pinned slot as
  needing calibration. `[T]` fixture.
- A4. A viewport/orientation/zoom/launch-mode mismatch produces a specific fence
  and a practical recovery action; it does not silently render a wrong plan.
- A5. The test grid can be shown on a physical wall without a shell copy step;
  it uses the committed bounds and 50 mm intervals.
- A6. The logical calibration scene remains logical-only and is not offered as a
  physical frame.
**Evidence:** model/health tests; screenshot of provenance labels; generated
grid asset and its dimensions; no hardware precision claim.

#### TWR-12 — Longer ruler spans and scale-consistency check · Issue [#15](https://github.com/spicyneutrino/tablet-wall-ai/issues/15)

**Status:** Open.
**Depends:** TWR-11.
**Purpose:** Reduce extrapolation error and stop supply/ruler disagreement from
being hidden.
**In scope:** ruler spans up to the usable width/height or multiple spans;
display of derived mm/CSS and estimated panel error before save; consistency
check between supplied panel dimensions and ruler scale that shows both and
requires an operator decision.
**Out of scope:** retroactive recalibration; automatic replacement of the
supplied models; claiming the 2 mm target is met by arithmetic.
**Acceptance:**
- A1. A full-span (or multi-span) measurement is possible; the UI shows span,
  derived mm/CSS, and estimated error before save. `[T]` ruler unit cases.
- A2. Saving creates a new calibration revision; existing revisions and saved
  layouts that pin them are unchanged. `[T]`.
- A3. A disagreement between supplied and ruler scale is presented as two values
  with consequences; nothing is averaged or overwritten silently.
- A4. The default 200 px span remains available but is labelled as
  short-span/higher-extrapolation.
**Evidence:** ruler tests; screenshot of the measurement panel; a recorded
example showing the derived value and uncertainty.

### Phase P5 — Operability, security, and UI acceptance

#### TWR-13 — Readiness, QR onboarding, health, logging, startup, backup, and runbook · Issue [#17](https://github.com/spicyneutrino/tablet-wall-ai/issues/17)

**Status:** Open.
**Depends:** TWR-02, TWR-07, TWR-09.
**Purpose:** Turn a developer demo into a rehearsed operator procedure.
**In scope:** startup preflight with explicit data paths, interface/origin,
security mode, content availability, and actionable failures; tablet URL + QR +
copy; Wi-Fi name; `/healthz`; backup recency and last successful restore
rehearsal; bounded/rotated logs; documented systemd user unit and
NetworkManager autoconnect (tooling and instructions, not a live install);
verified backup + restore drill packaged as an operator procedure; backup scope
choice (Wall recovery vs full library) with an explicit warning that unused
uploads are excluded; kiosk/power checklist per OS; page security headers;
playback exception visibility; a one-page startup/health/recovery runbook.
**Out of scope:** installing services or changing firewall/network during
implementation; off-host scheduling as a mandatory live service; phone access
over the hotspot.
**Acceptance:**
- A1. A clean isolated start prints/shows the exact tablet URL, QR, Wi-Fi name,
  data paths, security mode, and whether content is available. `[T]`/`[Sim]`.
- A2. `/healthz` reports schema, generation/revision, device counts, and storage
  readability; it does not leak paths or secrets.
- A3. Logs are size-bounded or rotated; a 24 h simulated append does not grow
  without limit. `[T]` policy test or documented rotation config.
- A4. The runbook lets a fresh operator start, verify health, blank the wall,
  stop, back up, and restore to new paths. `[Sim]` dry run; real reboot deferred
  to TWR-17.
- A5. Backup guidance states that only referenced content is included and names
  what is excluded.
- A6. Headers are present on controller/client pages and a CSP test proves local
  scripts, blob images, and WebSockets still work. `[T]`.
- A7. The kiosk checklist covers iPadOS Guided Access/auto-lock and Android
  stay-awake/auto-lock, and does not promise remote wake or wake lock.
**Evidence:** preflight output; `/healthz` response; header test; runbook dry-run
notes; screenshot of the readiness card.

#### TWR-14 — Unified image-first console and browser acceptance · Issue [#18](https://github.com/spicyneutrino/tablet-wall-ai/issues/18)

**Status:** Open.
**Depends:** TWR-03 … TWR-13 (parity).
**Purpose:** One operator surface, image-first, verified in a browser at desktop
and phone widths, by keyboard, with experimental video visually subordinate.
**In scope:** four task tabs (Wall, Tablets, Content, System), with Layout &
size inside Wall;
physical console as the operator home; logical console as a labelled
compatibility editor; still image parity before retiring anything; playback
demoted; consistent vocabulary; accessible names, focus, live regions, numeric
alternatives; mobile task navigation; empty/error/loading states; isolated
browser acceptance for the full journey.
**Out of scope:** deleting the legacy page/CSS before parity; a visual redesign
for its own sake; phone-over-hotspot access.
**Acceptance:**
- A1. The full journey (start→join→identify→arrange→show→confirm→switch→recover
  →remove/forget→stop) is completed in one console without using the legacy page
  for a still image. `[Sim]` desktop 1600×1000 and phone 390×844.
- A2. Join, arrange, show, fail/retry, replace, remove, forget, and diagnostics
  work on the phone layout without horizontal overflow; primary action and
  preview stay visible.
- A3. Keyboard-only operation covers reorder, nudge, apply/cancel, tab
  navigation, and dialogs; focus is preserved after polls, roster changes, and
  delete; errors are announced.
- A4. Long labels, 200% zoom, enlarged text, and reduced motion do not clip the
  primary action or hide status.
- A5. Health uses text/icon as well as colour; contrast and accessible names are
  checked, not asserted.
- A6. No console/network errors in a clean run; a failing request produces a
  readable message and a recovery action.
- A7. Experimental playback is behind an explicit switch and cannot be mistaken
  for the image path.
- A8. Screenshots and a short recording are attached; independent review and
  red-team findings are resolved before software completion.
**Evidence:** the artifact bundle defined in §12.5.

#### TWR-15 — Approved joining and revocation · Issue [#16](https://github.com/spicyneutrino/tablet-wall-ai/issues/16)

**Status:** Open — conditional. Remains `Deferred` unless a §7.3 trigger applies.
**Depends:** TWR-08, TWR-09.
**Purpose:** Prevent a peer that knows a UUID from claiming an installed tablet
when the network is not fully trusted.
**In scope (if triggered):** short-lived join approval; per-tablet credential;
automatic reconnect; explicit reauthorization; revocation; limits; negative
matrix; wording that distinguishes pairing from QR/join.
**Out of scope:** RBAC, user accounts, cloud identity, pretending plain HTTP
pairing is confidential.
**Acceptance (if triggered):**
- A1. A non-approved tablet cannot register or claim an installed slot.
- A2. An approved tablet reconnects across restart/network without a human.
- A3. A revoked credential cannot reclaim the slot, even with a known UUID.
- A4. Credentials never appear in URLs, logs, or screenshots.
- A5. Request/connection limits are enforced at the chosen boundary.
- A6. The negative matrix is recorded for the actual deployment profile.
**If not triggered:** record the decision and the accepted residual risk; do not
claim device authentication in the UI or docs.
**Evidence (if triggered):** the negative matrix for the chosen profile, a
credential-free log sample, and the recorded trigger/decision.

#### TWR-16 — Measured efficiency baseline · Issue [#20](https://github.com/spicyneutrino/tablet-wall-ai/issues/20)

**Status:** Open. Tracking issue filed before measurement work begins.
**Depends:** TWR-06, TWR-10, TWR-14.
**Purpose:** Replace guesses with measurements and prevent speculative
optimisation.
**In scope:** the metrics in §8.2 under a defined, recorded setup; a short
report; a decision per metric (act / do not act / measure again).
**Out of scope:** any optimisation without a baseline; capacity marketing.
**Acceptance:**
- A1. Time-to-painted p50/p95 is recorded for 1 and 4 simulated tablets, with
  method and conditions.
- A2. A 2×2 apply is shown to produce one revision/broadcast (regression check).
- A3. Five-minute idle request counts are recorded for the console; the polling
  decision cites them.
- A4. Log growth per idle day is recorded.
- A5. Each known cost in §8.3 has a disposition; none is “optimised” without a
  before/after.
- A6. No invented hardware capacity or battery number appears in the report.
**Evidence:** raw measurement files/commands and a short markdown report linked
from `VERIFICATION.md`.

### Phase P6 — Hardware evidence

#### TWR-17 — Real-tablet image-wall acceptance and recovery record · Issue [#19](https://github.com/spicyneutrino/tablet-wall-ai/issues/19)

**Status:** Open. Hardware only.
**Depends:** TWR-03 … TWR-13, TWR-14; TWR-15 before any untrusted-network claim.
**Purpose:** Establish what the actual iPads and Pixel Cs do, including failure
and manual intervention.
**In scope:** the checklist in §12.6 on the supplied devices; physical 2×2 and
1×4; seams with uncertainty; rotation/zoom/fullscreen; sleep/wake; Wi-Fi loss;
server restart; host reboot rehearsal on the chosen profile; verified restore;
2 h still soak; ingress from a second peer; kiosk/power behaviour; photos and
logs.
**Out of scope:** video/optical gates; millimetre claims beyond uncertainty;
unattended claims beyond the recorded soak.
**Acceptance:** every checklist row is `pass`, `fail`, or `not run` with a
reason; failures are retained; the evidence report carries the application SHA,
device/OS/browser versions, origin, modes, and durations. A test count is not a
substitute.
**Evidence:** `docs/validation/` report using `EVIDENCE-SCHEMA.md`; photos;
signed operator row; `hardware_claim` only for the tested configuration.

---

## 10. Status board and GitHub map

All issues are **OPEN**. “Merged” describes code on the integration branch, not
acceptance.

| TWR | Issue | Title | Status | Software | Hardware |
| --- | --- | --- | --- | --- | --- |
| — | [#7](https://github.com/spicyneutrino/tablet-wall-ai/issues/7) | Programme epic | Open | — | — |
| TWR-01 | [#8](https://github.com/spicyneutrino/tablet-wall-ai/issues/8) | Protocol 3 capability truth | Open — merged, acceptance pending | Partial (rendered case open; §4.4 regression resolved at `3f9beee`) | Not applicable |
| TWR-02 | [#9](https://github.com/spicyneutrino/tablet-wall-ai/issues/9) | Diagnostics and sign-in routes | Open — merged, acceptance pending | Partial (browser case open) | Auth expiry in TWR-17 |
| TWR-03 | [#10](https://github.com/spicyneutrino/tablet-wall-ai/issues/10) | Authoritative operator state | Open | No | Not applicable |
| TWR-04 | [#10](https://github.com/spicyneutrino/tablet-wall-ai/issues/10) | Still control, library, legacy fence | Open | No | Not applicable |
| TWR-05 | [#11](https://github.com/spicyneutrino/tablet-wall-ai/issues/11) | Whole-image fit and crop preview | Open | No | Fit appearance in TWR-17 |
| TWR-06 | [#12](https://github.com/spicyneutrino/tablet-wall-ai/issues/12) | Render evidence and retry | Open | No | Paint truth in TWR-17 |
| TWR-07 | [#12](https://github.com/spicyneutrino/tablet-wall-ai/issues/12) | Recovery watchdog and auth expiry | Open | No | Sleep/Wi-Fi in TWR-17 |
| TWR-08 | [#13](https://github.com/spicyneutrino/tablet-wall-ai/issues/13) | Labels, Identify, Remove, Forget | Open | No | Identify/forget in TWR-17 |
| TWR-09 | [#13](https://github.com/spicyneutrino/tablet-wall-ai/issues/13) | Rebind repair and cross-kind safety | Open | No | Rebind/restore in TWR-17 |
| TWR-10 | [#14](https://github.com/spicyneutrino/tablet-wall-ai/issues/14) | Atomic 2×2 and 1×4 presets | Open | No | Physical 2×2/1×4 in TWR-17 |
| TWR-11 | [#15](https://github.com/spicyneutrino/tablet-wall-ai/issues/15) | Calibration trust and test grid | Open | No | Seam/scale in TWR-17 |
| TWR-12 | [#15](https://github.com/spicyneutrino/tablet-wall-ai/issues/15) | Longer ruler and consistency | Open | No | Ruler work in TWR-17 |
| TWR-13 | [#17](https://github.com/spicyneutrino/tablet-wall-ai/issues/17) | Readiness, health, backup, runbook | Open | No | Reboot/restore in TWR-17 |
| TWR-14 | [#18](https://github.com/spicyneutrino/tablet-wall-ai/issues/18) | Unified console and browser acceptance | Open | No | Phone/keyboard real device optional |
| TWR-15 | [#16](https://github.com/spicyneutrino/tablet-wall-ai/issues/16) | Approved joining and revocation | Open — conditional | No | Only if triggered |
| TWR-16 | [#20](https://github.com/spicyneutrino/tablet-wall-ai/issues/20) | Measured efficiency baseline | Open | No | No |
| TWR-17 | [#19](https://github.com/spicyneutrino/tablet-wall-ai/issues/19) | Real-tablet acceptance | Open | — | **Required** |

**No package is complete.** Two packages have merged code with open acceptance.
Everything else has no accepted implementation.

---

## 11. Disposition register — every recommendation

Abbreviations for sources: **O** = Opus snapshot, **S** = Sol, **T** = Terra,
**D** = DeepSeek. A row may cite several when the reports agree. “Delivery”
means a TWR package owns it; “Hardware” means it can only be settled by physical
evidence; “Deferred/Rejected” points to §12.

### 11.1 Truth, console, and content

| ID | Recommendation | Sources | Disposition | Rationale |
| --- | --- | --- | --- | --- |
| R01 | One authoritative state showing layout kind, scene, content identity, revision | S1, D B1, T1 | **Delivery TWR-03** | Without it one page edits what it cannot read. |
| R02 | Physical console selects still image/colour and shows active content | S1, D B1, O B4, T4 | **Delivery TWR-04** | Removes the “select image before applying” trap. |
| R03 | Legacy page must not show a synthetic wall; banner/redirect | S1, D B1 | **Delivery TWR-04** | A plausible false wall is worse than an error. |
| R04 | Put `scene` in v3 config payload | D B1, S1 | **Delivery TWR-03** | Additive, small, testable. |
| R05 | Merge curated + managed images into one library with provenance, thumbnails, and search | S, D, T | **Delivery TWR-04** | Curated path is required in the upload-disabled profile. |
| R06 | Honest upload state: progress, duplicate detection, rejection reasons | S, D, T | **Delivery TWR-04** (only when uploads enabled) | Avoids advertising a disabled feature and explains refusals. |
| R07 | Hide the upload block in hotspot mode; show copy-to-directory path | O, D | **Delivery TWR-04** | Matches actual capability. |
| R08 | Global Fill (cover) and Fit whole image (contain) | O B7, S2, T2, D | **Delivery TWR-05** | Product-level fit choice, one wall-wide decision. |
| R09 | Letterbox colour for Fit | O, S, D | **Delivery TWR-05** | Required for a readable poster on a wide wall. |
| R10 | Crop/bezel/gap/source preview before Apply | O B7, S2, T2, D R4 | **Delivery TWR-05** | Makes loss intentional; no new geometry engine. |
| R11 | Distinguish off-wall crop from bezel/gap occlusion | S2 | **Delivery TWR-05** | Different losses, different remedies. |
| R12 | Source-pixels-per-tablet / upscale warning | D R4 | **Delivery TWR-05** | Arithmetic is certain; perceived quality is not. |
| R13 | Focal point for Fill | S, O | **Deferred (§12)** | After simple Fill/Fit works; adds a control and persistence field. |
| R14 | Test pattern generated for committed wall bounds | S, D, T | **Delivery TWR-11** | Removes the shell-copy-refresh dance. |
| R15 | Keep logical calibration scene separate/logical-only | D, O | **Delivery TWR-11** | It cannot render on a physical wall; conflating them misleads. |
| R16 | Blank wall / blackout as a deliberate action | D, S | **Delivery TWR-04** | End-of-day and diagnostic need; not “sleep” or “power off”. |

### 11.2 Per-tablet truth and recovery

| ID | Recommendation | Sources | Disposition | Rationale |
| --- | --- | --- | --- | --- |
| R17 | Bounded static render acknowledgement keyed by connection/token | O B2, S3, T3, D | **Delivery TWR-06** | The only honest basis for “showing”. |
| R18 | Distinguish offline, unplaced, blocked, loading, failed, hidden, stale, displayed | S3, T3, D | **Delivery TWR-06** | One badge from transport + content state. |
| R19 | Reject stale/late acknowledgements | S3, D | **Delivery TWR-06** | Prevents an old paint from greening a new image. |
| R20 | Per-tablet Retry image and Reconnect | S3, T3, D | **Delivery TWR-06/07** | Targeted recovery beats a reload. |
| R21 | “N of M showing” header count | O B2, S3 | **Delivery TWR-06** | Aggregate truth with an explicit denominator. |
| R22 | Presence must never imply image health | O B2, S3, T3 | **Delivery TWR-06** | Core non-claim. |
| R23 | Reconnect on visibility/pageshow/online; stale-socket watchdog | D R3, S3 | **Delivery TWR-07** | A frozen OS page may never fire close. |
| R24 | Expired auth shows a visible sign-in action | D B6, S | **Delivery TWR-07** | A wall must not loop silently after 12 h. |
| R25 | Durable per-device credential for an always-on wall | D B6, S7 | **Delivery TWR-15** (conditional) | Correct concept, but a security decision tied to the threat model. |
| R26 | Tablet HUD shows last accepted revision/time and plan provenance | D, O, T | **Delivery TWR-06/08** | Lets a person at the wall detect staleness. |
| R27 | Wake-lock state reported honestly | O, S, T, D | **Delivery TWR-13** (wording/checklist); device outcome TWR-17 | Web cannot guarantee wake on the Air 2. |
| R28 | Remote wake/unlock | none claim it | **Rejected** | Not a browser capability. |

### 11.3 Identity, lifecycle, arrangements

| ID | Recommendation | Sources | Disposition | Rationale |
| --- | --- | --- | --- | --- |
| R29 | Durable human label separate from `#N` | O, S, T, D | **Delivery TWR-08** | Numbers are leases, not installation IDs. |
| R30 | Transient Identify overlay, expiry, no scene change | O, S, T, D | **Delivery TWR-08** | Fast physical-to-console matching. |
| R31 | Separate Remove from wall / Forget / Revoke | O, S, T, D | **Delivery TWR-08** (Revoke in TWR-15) | Destructive actions must say what they keep. |
| R32 | Forget allowed in physical mode | O B4, D B3, S4 | **Delivery TWR-08** | Lifecycle cannot depend on layout kind. |
| R33 | Forget impact preview and saved-layout reference reporting | S4, D, T | **Delivery TWR-08** | Prevent surprise resurrection on recall. |
| R34 | Offline-only Forget protection | D (claims existing), S | **Delivery TWR-08 — corrected** | No such protection exists today; the package adds it deliberately. |
| R35 | Rebind in the primary UI with same/different hardware declaration | O, S, T, D | **Delivery TWR-09** | Replacement is a hardware judgement, not a name guess. |
| R36 | Rebind repairs explicitly selected saved layouts transactionally | O B5, S5, T4, D #11 | **Delivery TWR-09** | Saved 2×2/1×4 are the reason rebind matters. |
| R37 | Rebind preview, conflicts, revision maps, rollback | S, T, D | **Delivery TWR-09** | Hard-to-reverse operation needs a dry run. |
| R38 | Stable installed-tablet registry independent of browser UUID | S, D | **Deferred (§12)** | Larger migration; explicit repair is enough until measured pain. |
| R39 | Atomic 2×2 and 1×4 presets in number order | O B3, S5, T5, D B4 | **Delivery TWR-10** | The advertised workflow must be one action. |
| R40 | Explicit orientation; mount angle not hard-coded | O B3, S, T, D | **Delivery TWR-10** | Four independent facts: panel, mount, browser, launch mode. |
| R41 | Edge-to-edge packing, bezels as gaps, fit wall to tablets | O, S, T, D | **Delivery TWR-10** | Removes dead bands. |
| R42 | Sensible defaults (4 tablets → 2×2, gap 0, fit tablets) | O, D | **Delivery TWR-10** | First try should look right. |
| R43 | Fix first-two manual-add overlap | D B4 | **Delivery TWR-10** | Observable bug. |
| R44 | One atomic write, no per-tablet placement loop | O B3, D B4 | **Delivery TWR-10** | One revision, one repaint, no partial wall. |
| R45 | Offline reservations preserved intentionally, visible | S, T | **Delivery TWR-10** | A sleeping tablet keeps its spot. |
| R46 | Empty physical draft cannot silently replace a wall | O B4, S, T | **Delivery TWR-10** | Destructive default. |
| R47 | Cross-kind apply/recall writes a named safety copy | D B2, S, T, O | **Delivery TWR-09** | Prevents data loss in the exact switching workflow. |
| R48 | Safe whole-draft undo across fit-to-tablets rebase | T | **Deferred (§12)** | Needs design; document the limitation rather than fake undo. |
| R49 | Participation/include toggle per slot | D | **Delivery TWR-10** | Existing field, no UI; parks a broken tablet without losing its slot. |
| R50 | Saved presentation combining layout + content | S | **Deferred (§12)** | Keep layout, scene, playback separate for now. |
| R51 | Export/import arrangements and metadata | S | **Deferred (§12)** | Identity/measurement remapping is the hard part; not needed for demo. |

### 11.4 Calibration and measurement

| ID | Recommendation | Sources | Disposition | Rationale |
| --- | --- | --- | --- | --- |
| R52 | Show model/manual/unknown provenance and ± uncertainty | O, S, T, D | **Delivery TWR-11** | An estimate must not look measured. |
| R53 | Confirm detected model; never silently assign scale | O, S, T, D | **Delivery TWR-11** | Signature is a hint, not a hardware credential. |
| R54 | Show assumed inset, launch mode, pinned revisions | S, D, T | **Delivery TWR-11** | Explains systematic tab-mode offsets. |
| R55 | Warn on live viewport/orientation/zoom mismatch | O, S, T, D | **Delivery TWR-11** | Fixes the observed portrait-in-landscape case. |
| R56 | Health summary uses pinned slot revisions | D R5 | **Delivery TWR-11** | Current summary contradicts the render plan. |
| R57 | Wall-sized diagnostic grid | S, D, T | **Delivery TWR-11** | One-click continuity check. |
| R58 | Longer ruler spans / multi-span with derived error | D R2 | **Delivery TWR-12** | 200 px extrapolation can swamp the 2 mm target. |
| R59 | Consistency check between supplied panel and ruler scale | D, T | **Delivery TWR-12** | Show disagreement; never silently replace. |
| R60 | Auto-flip orientation without confirmation | O (as a caution) | **Deferred/Rejected** | Warn first; auto-flip can surprise. |
| R61 | More built-in tablet models | O, S | **Deferred (§12)** | Do not build a catalogue before installed devices work. |
| R62 | Photo-based seam check | O | **Deferred (§12)** | Research-grade; not needed to operate. |
| R63 | New ruler measurements before the demo | O, D, T, S | **Rejected as a prerequisite** | Supplied measurements plus uncertainty are the accepted inputs. |

### 11.5 Operations, onboarding, and documentation

| ID | Recommendation | Sources | Disposition | Rationale |
| --- | --- | --- | --- | --- |
| R64 | Readiness/preflight with data paths, origin, security mode, content, failures | S, T, D | **Delivery TWR-13** | Turns startup into a diagnosis. |
| R65 | QR code + copyable exact tablet URL + local-address warning | O, S, T, D | **Delivery TWR-13** | Typing a URL on a tablet is the slowest join step. |
| R66 | Wi-Fi name and join instructions in the console | O, T | **Delivery TWR-13** | Removes a document lookup. |
| R67 | `/healthz` readiness endpoint | S, D | **Delivery TWR-13** | Distinguishes process alive from storage/content ready. |
| R68 | Diagnostics independent of uploads | O, S, T, D | **Delivery TWR-02 (landed)** | Already implemented; keep and verify. |
| R69 | Bounded/rotated logs | S, T, D | **Delivery TWR-13** | A 24/7 wall must not fill the disk. |
| R70 | Startup service unit / autostart and NetworkManager autoconnect | O, S, T, D | **Delivery TWR-13** (instructions/tooling) | Host/service installation is an operator action, not this run. |
| R71 | Scheduled verified backup + visible recency | O, S, T, D | **Delivery TWR-13** (documented timer, no live install) | Recoverability, with an explicit retention decision. |
| R72 | Restore rehearsal, backup recency, and an explicit Wall-recovery vs full-library scope choice | S, T, D | **Delivery TWR-13** software procedure; real drill in TWR-17 | Only referenced content is copied; the operator must choose knowingly. |
| R73 | Kiosk/power checklist per OS | O, S, T, D | **Delivery TWR-13** | Web cannot enforce OS sleep. |
| R74 | One-page startup/health/recovery runbook | T, S, D | **Delivery TWR-13** | Reduces dependence on developer memory. |
| R75 | Phone controller over the hotspot with PIN | O | **Deferred (§12)** | New exposure; mobile layout of the loopback console is in TWR-14. |
| R76 | Operational change history (who changed what) | S | **Deferred (§12)** | Useful, not required; adds identity/privacy scope. |
| R77 | Library delete/rename with used-by checks | S, D | **Deferred (§12)** | Risk of reference breakage; not needed for the demo. |
| R78 | Scheduled arrangements/content | O, S | **Deferred (§12)** | Requires soak and unattended confidence first. |
| R79 | PWA manifest / install prompt | S, D | **Deferred (§12)** | Test on real browsers first; not a kiosk substitute. |

### 11.6 Security and trust

| ID | Recommendation | Sources | Disposition | Rationale |
| --- | --- | --- | --- | --- |
| R80 | Keep tablet allowlist, loopback operator, origin fence | all | **Keep (no change)** | Load-bearing; verified by tests. |
| R81 | Do not call the HTTP hotspot authenticated; state limits | all | **Delivery TWR-13 wording** | Honesty is a security control. |
| R82 | Approved join + per-device credential + revocation | S7, D B6, T9, O | **Delivery TWR-15** (conditional) | Correct for untrusted peers; overkill on a private hotspot. |
| R83 | Rate limiting at the proxy | S, D | **Deferred with TWR-15** | Premature on loopback/trusted hotspot; belongs with exposure. |
| R84 | Security headers / tested CSP on app pages | S, D | **Delivery TWR-13** | Cheap, low-risk, currently absent. |
| R85 | Secrets and CA private key outside checkout; protected backups | S, T | **Delivery TWR-13 docs** | Operational hygiene. |
| R86 | Separate app shared secret from two-origin proxy auth | S | **Keep + document** | Do not combine without an integration test. |
| R87 | Registration flood / 512 eviction risk | O | **Delivery TWR-15 rationale**, otherwise documented | Low risk on a private hotspot; pairing closes it. |
| R88 | Device UUID is not a credential; last-socket-wins | S, T, D | **Documented non-claim** | Must not be contradicted by UI wording. |
| R89 | UUID/visual label as credential | none | **Rejected** | False security. |

### 11.7 Efficiency and architecture

| ID | Recommendation | Sources | Disposition | Rationale |
| --- | --- | --- | --- | --- |
| R90 | Measure time-to-painted/decode before renditions | O, S, D | **Delivery TWR-16** | No basis for a rendition pipeline yet. |
| R91 | Avoid four commits/broadcasts per grid | O, D | **Delivery TWR-10** | Counted behaviour. |
| R92 | Replace 1 s/5 s polling with the v3 socket | D R7, S | **Delivery TWR-16 → only if measured** | Measure first; polling is harmless at four tablets. |
| R93 | Do not optimise SQLite reads/ETag at this scale | O, S | **Rejected as premature** | Unmeasured; writer queues isolate slow sockets. |
| R94 | Per-device slice renditions / pre-slicing | O, D, S | **Deferred (§12)** | Multiplies storage/invalidation; quality unmeasured. |
| R95 | WAL/busy timeout/database server | D | **Deferred (§12)** | Only if `database is locked` is observed. |
| R96 | Multi-worker or distributed backend | all | **Rejected** | Breaks single-owner presence; no demonstrated need. |
| R97 | Framework rewrite / new frontend | all | **Rejected** | Adds failure modes without addressing gaps. |
| R98 | One stylesheet / delete legacy CSS | O | **Deferred until TWR-14 parity** | Cosmetic weight, not a blocker; deletion after consolidation. |
| R99 | Instrument sequential broadcasts/send failures | T | **Delivery TWR-16** | Unmeasured; instrument before concurrency changes. |
| R100 | Playback loop exception visibility | S | **Delivery TWR-13** | Silent loop can hide recurring faults. |
| R101 | 15–20 tablet capacity work | O, D | **Deferred (§12)** | Trial target, not a proven envelope. |

### 11.8 Validation and scope

| ID | Recommendation | Sources | Disposition | Rationale |
| --- | --- | --- | --- | --- |
| R102 | Images-only hardware demonstration with existing models | O, S, T, D | **Hardware TWR-17** | The only way to settle physical claims. |
| R103 | Save current logical wall + verified backup before physical work | S, D, T | **Hardware TWR-17 preparation** | Preserve the demonstrated configuration. |
| R104 | Seam/scale/rotation/sleep/Wi-Fi/restart/soak record | all | **Hardware TWR-17** | Test counts cannot substitute. |
| R105 | Eight hardware gates | repository | **Hardware, unchanged** | Remain MISSING until signed. |
| R106 | Video/optical validation programme | all | **Deferred (§12)** | Not part of the image milestone. |
| R107 | Mirror mode and independent mode | all | **Deferred (§12)** | After spanning image and recovery are dependable. |
| R108 | Cloud/remote access, RBAC, AI generation | all | **Rejected/Deferred** | Adds undebuggable failure modes; no user need. |
| R109 | Full browser/simulation acceptance evidence | S, D | **Delivery TWR-14** | Required before software completion. |
| R110 | Independent review and red-team of the consolidated change | programme | **Required in TWR-14/TWR-17 evidence** | Self-review is not acceptance. |
| R111 | Strict image-cut preparation for coordinated still changes (not optical sync) | S | **Deferred (§12)** | Static reliability first; the existing prepare/commit work can be adapted later. |
| R112 | Immutable revision-keyed measurement snapshot cache | S | **Deferred (§12)** | Only worth it if layout switching is measured slow. |
| R113 | Tablet offline content cache | T | **Deferred (§12)** | Needs an explicit stale-content and trust policy. |
| R114 | Battery telemetry | T | **Deferred (§12)** | Platform-dependent; not a browser capability to assume. |
| R115 | Tablet install/setup overlay: viewport, DPR, orientation, mode, wake state, ruler link | D | **Delivery TWR-11** (labels in TWR-08) | Diagnoses the assumptions that make a plan approximate. |
| R116 | First-run fullscreen prompt and iOS Add to Home Screen guidance | O | **Delivery TWR-13** | Launch mode affects inset and storage persistence; instructions, not enforcement. |
| R117 | Tablet abnormal-state banner (“Not on the wall”, “Rotate”, “Waiting”, “Lost connection”) | O | **Delivery TWR-06/07** | Calm when healthy, specific when not; the server must receive the same state. |

### 11.9 Contradiction resolutions

These are the material disagreements between reports, or between a report and
re-checked source. Each resolution is binding for this milestone.

| # | Disagreement | Resolution | Why |
| --- | --- | --- | --- |
| X1 | Opus: make the millimetre (physical) layout the only model, migrate logical layouts, delete legacy routes. Sol/Terra/DeepSeek: one *console*, but keep both layout kinds. | **Keep both layout kinds. Unify the operator read/command surface.** A single mm stage for everything is rejected for this delivery. | A default 0.17 mm/px cannot recover a real scale from the demonstrated 320×60-unit wall. Forced migration risks the only physically demonstrated configuration. |
| X2 | Opus lists 4×1 as a preset; UX decision restricts presets to 2×2 and 1×4. | **2×2 and 1×4 are the only primary presets.** 4×1 is custom rows/columns. | “1×4” means one row; “4×1” means a vertical stack. Mixing the notation is how the original bug survived. |
| X3 | Opus: delete the legacy controller after consolidation. Sol: retire only after parity. Terra: reuse the physical editor rather than a new state model. | **Physical console becomes the operator home; the logical page remains a labelled compatibility editor until TWR-14 parity, then deletion is an open decision (OD5).** | The physical page still cannot select a still (C2); deleting first would remove the only working path. |
| X4 | DeepSeek says to keep the existing “cannot forget an online device” protection. Source shows no such protection: `DELETE` closes an online socket. | **TWR-08 adds an offline-only Forget guard deliberately.** The compatibility route adopts it explicitly. | Re-checked source beats the report. Keeping two lifecycle meanings by accident is worse than changing one on purpose. |
| X5 | Opus: registration approval is a “useful next”. Sol: approved join is must-have rank 7. Terra/DeepSeek: pairing depends on the threat model. | **TWR-15 is conditional on the §7.3 triggers.** Profile A stays explicitly unauthenticated. | On a private hotspot, pairing adds a credential lifecycle (and plain-HTTP limits) without closing a realistic threat. |
| X6 | DeepSeek: durable per-device credential now because a 12 h session is hostile. Terra: credentials are a threat-model decision. | **Visible expiry recovery now (TWR-07); durable device credential in conditional TWR-15.** | The immediate failure is silent retry, not the absence of pairing. Fix the visible failure first. |
| X7 | Opus: do not optimise the SQLite/ETag paths. DeepSeek: replace 1 s/5 s polling with the v3 socket. Sol/Terra: measure before changing. | **TWR-16 measures; polling replacement only if the measurement supports it.** Other hotspots stay unoptimised. | No reviewer measured a bottleneck; a rewrite of working paths is risk without evidence. |
| X8 | Opus: freeze playback/video behind a flag. Sol: keep tests green but stop extending. Terra/DeepSeek: experimental until real-device evidence. | **Keep code and tests, demote the UI behind an explicit switch, add bounded fault logging, accept no video claim.** | All four agree on non-claim; keeping tests prevents rot, demoting prevents misreading the product. |
| X9 | Verdict tension: Opus “ready for supervised demo” vs DeepSeek “not ready for physical primary”. | **Demo-ready in the demonstrated *logical* layout; the physical path is unproven until TWR-17.** | Both are true for different configurations; the roadmap names the configuration. |
| X10 | Ruler: Opus treats it as an advanced path; DeepSeek shows the 200 px cap can amplify error ~3.8×. | **Keep the ruler, add longer/multi-span measurement and derived error (TWR-12); do not make new measurements a prerequisite.** | Improves the method without invalidating the supplied models or delaying the demo. |
| X11 | Stable installed-tablet registry: Sol says new concepts that earn their cost; DeepSeek suggests later simplification; Architecture defers model B. | **Deferred. Keep browser UUID keys with explicit rebind repair.** | Schema, backup, and migration cost now exceeds the measured rebind pain. Revisit trigger in §12. |
| X12 | Backup scope: Opus says backups exist; Sol/Terra/DeepSeek warn that only referenced content is copied. | **Document the scope explicitly, show recency and last restore rehearsal, and keep cross-kind safety copies.** | An operator must not assume unused uploads survive a restore. |
| X13 | “One controller” scope: Opus means one *layout model*; Sol/Terra/DeepSeek mean one *operator surface*. | **One surface (TWR-14), two layout kinds (TWR-03/10).** | Conflating surface and model is what produced the two-console split. |
| X14 | Photo-based seam check: Opus calls it optional future; others do not require it. | **Deferred.** | Ruler + generated grid answer the current question; photo analysis is research-grade. |

---

## 12. Deferred and rejected work

Each item states why, and what would reopen it. Nothing here is secretly
implemented; if code exists (playback/video), it stays experimental and visually
secondary.

| Item | Status | Reason | Reopen trigger |
| --- | --- | --- | --- |
| Mirror mode (every tablet shows the whole image) | Deferred | A separate content mode; complicates span geometry and status semantics | Spanning image is dependable in TWR-17 and a real signage use case appears |
| Independent per-tablet images | Deferred | Needs per-device content assignment, precedence, and recovery rules | A real operator need after span is stable |
| Video / timed playback as dependable feature | Deferred, experimental only | No real-tablet decode/suspend/onset evidence; tests are software-only | Separate compatibility/resource/optical programme with mixed devices |
| Optical synchronisation / 100-event onset gate | Deferred | Belongs to video; a still image needs no shared clock | A timed medium is actually being deployed |
| Per-device slice renditions / pre-slicing | Deferred | Multiplies storage and invalidation; no measured sharpness failure | TWR-16 shows decode/quality is the limiting factor |
| Per-tablet adaptive renditions | Deferred | Same as above; naive resize can break geometry/quality | Measured time-to-painted or memory pressure |
| Cloud sync / remote internet access | Rejected | New trust boundary and operational surface; wall is local | A genuinely remote operator requirement, with a security design |
| Multi-user accounts / RBAC | Rejected | One operator, one laptop; adds identity scope | Multiple independent operators with different permissions |
| Distributed / multi-worker backend | Rejected | Separate presence and sockets diverge; single-owner model is correct | A scale that SQLite/one event loop cannot serve, with evidence |
| Framework rewrite / new frontend stack | Rejected | Does not address the demonstrated integration gaps | Never for this milestone |
| AI image generation / auto-layout guessing | Rejected | Not part of showing a curated image; unpredictable | Explicit product decision with a quality story |
| Per-tablet focal crop points | Deferred | Current need is one global image; focal point after Fill/Fit | Operators need art-directed crops often |
| Stable installed-tablet registry (Architecture B) | Deferred | Schema/migration/backup cost; explicit rebind repair is smaller now | Repeated rebind repair becomes the dominant lifecycle cost |
| Saved presentation (layout+content as one object) | Deferred | Collapses separate semantics too early | Operators routinely want one-click “show this on that arrangement” |
| Whole-draft undo across fit-to-tablets rebase | Deferred | Bounds rebase makes naive undo lie; needs design | A concrete undo requirement after presets land |
| Scheduled arrangements / unattended shows | Deferred | Needs soak, recovery confidence, and an ownership model | TWR-17 soak passes and a scheduled use case exists |
| Export/import of arrangements/metadata | Deferred | Identity and measurement remapping is the hard part | Fleet transfer or disaster-recovery requirement |
| Library delete/rename/GC | Deferred | Reference integrity across scenes/layouts/playlists; destructive | Library curation becomes an operator complaint; implement with used-by preview |
| Operational change history | Deferred | Useful but adds identity/privacy and storage scope | Multi-operator deployment or audit requirement |
| Phone controller over the hotspot | Deferred | New exposure; needs PIN/session design | Operator genuinely needs to walk the wall; TWR-15 exists |
| PWA manifest / install prompt | Deferred | Browser/kiosk behaviour unverified; not a substitute for OS settings | A tested browser needs it for launch persistence |
| HTTPS migration of the demo fleet, including a guided CA install | Deferred | Origin change wipes identities; decide before calibrating a fleet | Deployment profile B is chosen and rebind repair (TWR-09) is accepted |
| More built-in tablet models | Deferred | Catalogue without installed-device evidence | A new physical tablet enters the fleet |
| Photo-based seam check | Deferred | Research-grade tooling; ruler/grid is sufficient now | Seam work becomes frequent and manual measurement is the bottleneck |
| Auto-flip orientation | Rejected for now | Surprise physical rotation; warn and require confirmation | Operators ask for it after using warnings |
| Strict image-cut preparation / coordinated still changes | Deferred | Static reliability and recovery must be proven first; must not be marketed as optical sync | Still-image switching and render truth are dependable, and cuts are needed |
| Immutable revision-keyed measurement snapshot cache | Deferred | Another mutable cache is a failure surface without evidence | Profiling of TWR-16 shows physical plan assembly or config reads are the bottleneck |
| Tablet offline content cache | Deferred | No stale-content or trust policy yet; a cached wrong image is worse than an honest failure | A real offline requirement with a written stale policy |
| Battery telemetry | Deferred | Platform-specific and not available to a normal web page; no user need yet | A device-management requirement with a measured method |
| Rate limiting / login throttling now | Deferred | Loopback/trusted hotspot; home-grown limiter adds failure | Any untrusted-network exposure (TWR-15) |
| Dependency-review automation | Deferred to maintenance | No runtime dependency change in this milestone | New dependency or a security policy requirement |
| “Keep awake” promise from web code | Rejected | Not a browser capability on the target devices | Never |

---

## 13. Verification plan

### 13.1 Gate ladder

Every package climbs the same ladder. A higher gate never substitutes for a
lower one, and a lower one never substitutes for hardware.

1. **Static:** source review against this contract; `ruff`, `mypy`.
2. **Focused unit/integration:** the package's named tests.
3. **Full Python suite:** no regression from the 1,177-test baseline (or a
   documented, justified change to the baseline).
4. **JavaScript suites:** all `tests/*.test.js`.
5. **Isolated API/security negative matrix:** temporary DB/assets/media,
   loopback only.
6. **Isolated browser acceptance:** desktop and phone viewports, real Chromium,
   no live data.
7. **Independent review / red team:** findings resolved or explicitly accepted.
8. **Hardware:** only TWR-17, only on the named devices/configurations.

A red focused test at the starting HEAD is recorded in §4.4. It blocks
`Software complete` until fixed or formally re-baselined with a written reason;
the failure is never deleted from the record.

### 13.2 Exact commands

Run from the repository root. The `.venv` is the project environment; `uv run`
is acceptable when it resolves to the same environment.

```bash
# Baseline / full software gate
.venv/bin/python -m pytest -q -p no:cacheprovider
node --test tests/*.test.js

# Lint and types
.venv/bin/ruff check main.py tabletwall deploy
.venv/bin/mypy

# Focused examples used by the packages
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_v3.py tests/test_wall.py
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_deployment_guards.py tests/test_ingress.py tests/test_field.py
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_tablet_models.py tests/test_calibration_guard.py tests/test_roster_persistence.py
node tests/controller_image_capability.test.js
node tests/physical_sizing.test.js
node tests/client_image.test.js
```

Isolated server for API/browser checks (never the live database):

```bash
export TABLET_WALL_DB=/tmp/opencode/tw-qa/db.sqlite3
export TABLET_WALL_ASSET_DIR=/tmp/opencode/tw-qa/assets
export TABLET_WALL_MEDIA_DIR=/tmp/opencode/tw-qa/media
mkdir -p /tmp/opencode/tw-qa/{assets,media}
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 18766
```

Record the exact command, result count, duration, and HEAD for every entry in
`VERIFICATION.md`. Do not paste a test count without the command that produced
it.

### 13.3 Software acceptance matrix (TWR-14)

| Area | Cases |
| --- | --- |
| Join/onboarding | URL/QR, new tablet card, model confirmation, no model, duplicate join, offline join |
| Identity | rename, long/Unicode/empty label, Identify timing and expiry, remove, forget offline/online, rebind same/different hardware |
| Arrange | 2×2, 1×4, custom rows/cols, reorder by keyboard, offline reservation, release guard, empty draft, failure rollback |
| Show | image selection, Fill, Fit, colour, blank, test pattern, missing asset, oversized source warning |
| Confirm | all displaying, one failed, one stale, one hidden, one offline, unsupported client, zero participants |
| Switch | save both arrangements, recall each, cross-kind both ways, missing tablet, dirty draft conflict |
| Recover | retry image, reconnect, resume probe, network drop, 401 sign-in, takeover |
| Content | curated with uploads off, managed with uploads on, rejection reason, unavailable asset |
| Diagnostics | Field check with uploads off, `/healthz`, integrity verify |
| Accessibility | keyboard-only, focus after poll/delete, 200% zoom, reduced motion, text+icon health, long labels |
| Errors | 412/422/409/428/5xx surfaces, empty states, network failure |

### 13.4 API/security negative matrix

Record request, expected status, observed status, and evidence for at least:

| Case | Expected |
| --- | --- |
| Tablet port → operator routes (`/wall`, `/devices`, `/scene`, config) | 403 |
| Tablet port → `/auth/login` | 200 (documented entry point) |
| Tablet port → diagnostics | 403 |
| Operator loopback → diagnostics with uploads disabled | 200 |
| Direct backend port from a second peer | unreachable / refused |
| Mutation without `If-Match` | 428 |
| Mutation with stale ETag | 412 |
| Invalid asset/revision/geometry | 422 |
| Unknown device/snapshot | 404 |
| Release guard / live conflict | 409 with structured detail |
| Cross-origin state-changing request | rejected by origin fence |
| Oversized registration/report body | rejected, bounded |
| Revoked credential (if TWR-15) | cannot claim slot |
| WebSocket takeover | old socket closed with 4409, no loop |

### 13.5 Artifact requirements

Every package's evidence bundle contains:

- application SHA and branch;
- exact commands and results (stdout summary, not a claim);
- test file names and counts;
- for browser work: viewport sizes, device scale, screenshots (desktop and
  phone), console/network log excerpts, and the isolated data paths;
- for API work: probe transcript with request and response status;
- for each failure: the failure retained, not just the eventual pass;
- a one-line statement of what the evidence does **not** prove.

Artifacts live under a temporary path for the run and are referenced from
`VERIFICATION.md`; do not commit large binaries to the repository. Do not
include credentials, cookies, or private images in evidence.

### 13.6 Hardware validation plan (TWR-17)

Preparation:

1. Verified backup of the database, curated assets, and media; record the SHA.
2. Save the current logical 4×1 wall under a named layout; do not rely only on
   the automatic “Before physical” copy.
3. Confirm each tablet's model; do not proceed on an unconfirmed model.
4. Choose an image with labelled corners, diagonals, circles, and fine lines
   generated for the committed bounds; then a real poster/photo.
5. Record model, OS/browser, origin, launch mode, orientation, viewport, zoom,
   pinned profile/calibration revision.
6. If possible, measure one tablet with a full-span ruler; otherwise label the
   run approximate and do not claim 2 mm.

Run and record:

| # | Check | Pass condition |
| --- | --- | --- |
| H1 | Logical 4×1 baseline | Known image displays as before; no regression |
| H2 | Physical 2×2 with supplied models | Correct quadrants, no swap/upside-down, within 10 s |
| H3 | Physical 1×4 | Correct row order; orientation as intended |
| H4 | Seams | Record displacement per edge with uncertainty; compare with 2 mm target honestly |
| H5 | Scale | 50 mm interval measured on each model; record deviation |
| H6 | Rotation/zoom/fullscreen | Fence or correct re-render; no silent wrong plan |
| H7 | Image failure/retry | Failure named; retry recovers; old token cannot green the new image |
| H8 | Wi-Fi drop/restore | Correct within 10 s per trial; formal gate needs 20 trials |
| H9 | Sleep/wake | Record whether tap/unlock/reload/reopen is required |
| H10 | Server restart | All tablets resync without manual reload, or failure recorded |
| H11 | Host reboot rehearsal | Service returns on the chosen profile; content/layout intact |
| H12 | Cross-kind switch | Both arrangements recoverable; safety copy named |
| H13 | Rebind + recall | Saved 2×2 and 1×4 use the new identity; old one not resurrected |
| H14 | Forget/remove | Roster and slots behave as documented; history preserved |
| H15 | Restore to new paths | Referenced content, layout, devices intact; unused uploads explicitly absent |
| H16 | Ingress from second peer | Operator and direct backend unreachable |
| H17 | 2 h still soak | No unplanned stall, lost member, stale paint, or unexplained restart |
| H18 | Kiosk/power | Documented OS settings; exit path known |

Exit rule: write a `docs/validation/` report using `EVIDENCE-SCHEMA.md`, retain
failures, and mark gates only for what was actually measured. Video and optical
gates remain **MISSING**.

### 13.7 Completion rules

- A package's `Software complete` requires its acceptance rows recorded with
  commands, plus TWR-14 browser evidence where the package has a UI surface.
- `Hardware verified` requires a signed TWR-17 record for the named devices and
  configurations. No aggregate “the wall works” claim from a single model.
- An issue closes only when its acceptance is recorded. A merged commit is not
  closure.
- Any acceptance wording changed during implementation (for example “Image
  capable” instead of “Shows images”) must be recorded here or in the package's
  evidence, not silently reinterpreted.

---

## 14. Risks, assumptions, and open decisions

| # | Risk / assumption | Impact | Mitigation / owner |
| --- | --- | --- | --- |
| K1 | Physical path may reveal geometry errors that fixtures miss | High | TWR-17 before any accuracy claim; preserve failures |
| K2 | Model signature collision misassigns a tablet | Medium | TWR-11 confirmation; no scale without confirmation |
| K3 | Browser inset assumption is systematically wrong in tab mode | Medium | Show assumption; prefer fullscreen/standalone for measured runs; TWR-17 |
| K4 | Air 2 cannot keep a page awake on iPadOS 15.8 | High for unattended | OS checklist; no web promise; record actual behaviour |
| K5 | Physical-mode consolidation introduces a second source of truth | High | TWR-03 single read model; no mm-only migration |
| K6 | Rebind repair is complex and can corrupt snapshots | High | Preview + one transaction + rollback tests (TWR-09) |
| K7 | Render evidence is mistaken for optical proof | Medium | Explicit non-claim in UI and docs; TWR-06 |
| K8 | Ruler method cannot reach 2 mm | Medium | TWR-12 longer spans; record achieved value |
| K9 | Auth enablement makes the wall worse than no auth | Medium | TWR-07 visible recovery; TWR-15 only when justified |
| K10 | Consolidation deletes a capability before parity | High | TWR-14 parity gate; keep legacy as labelled compatibility |
| K11 | Test count is treated as hardware evidence | High | Status vocabulary; TWR-17 gate |
| K12 | Efficiency evidence is omitted | Low | Issue #20 tracks the required reproducible measurements |
| K13 | Programme expands into video/mirror/cloud | High | §12 non-goals; reopen only with a written decision |

Open decisions recorded here rather than assumed:

- **OD1.** Final origin (HTTP hotspot vs HTTPS) for the installed fleet. Decide
  before calibrating a fleet; rebind repair must be accepted first.
- **OD2.** Whether TWR-15 is triggered for the actual network. Record the threat
  model and residual risk either way.
- **OD3.** Soak duration for “unattended” in this installation (2 h minimum;
  overnight if truly unattended).
- **OD4.** Backup retention and destination. Documented in TWR-13; the operator
  chooses the disk.
- **OD5.** Whether the legacy logical console is eventually deleted after TWR-14
  parity. Not decided now; deletion is not required for the milestone.

---

## 15. Provenance and how to update this document

- The four source reports are copied verbatim to [reviews/](reviews/) with
  SHA-256 hashes and provenance notes. They were not edited.
- The Opus snapshot is an **earlier report** (2026-10-31, filename
  “opus-5.5-existing-report”); it is treated as a pre-existing assessment, not a
  same-run peer. Its claims were re-checked where a decision depends on them.
  See [reviews/README.md](reviews/README.md).
- Current-state claims use `981b2db`; product claims from the reviews use
  `0ff56e3`. Do not conflate them.
- Update rules: change a package's acceptance only with a logged decision;
  never mark hardware verified from software; never delete a failure from the
  evidence trail; keep deferred items in §12 until a written reopen decision.
- Related documents: [ARCHITECTURE.md](ARCHITECTURE.md),
  [UX-AND-RISKS.md](UX-AND-RISKS.md), [TRACKING.md](TRACKING.md),
  [VERIFICATION.md](VERIFICATION.md), [DECISIONS.tsv](DECISIONS.tsv),
  [`docs/validation/`](../validation/).

---

## Appendix A — Core deliverable coverage

The user-visible deliverables that motivated this milestone, mapped to the
package that owns them. “Evidence” names what must exist before the deliverable
is claimed.

| # | Deliverable | Owner | Software evidence | Hardware evidence |
| --- | --- | --- | --- | --- |
| 1 | Accurate authoritative state and still images in the physical controller | TWR-03/04 | Config + scene tests; four-client simulation | Physical image display in TWR-17 |
| 2 | Contain/cover fit and truthful crop preview | TWR-05 | Geometry/preview tests; screenshots | Appearance/crop in TWR-17 |
| 3 | Static render health and protocol-3 warnings | TWR-01/06 | Capability + render-ack tests; failure injection | Real paint/sleep behaviour |
| 4 | Atomic 2×2/1×4 grid, number order, orientation | TWR-10 | One-revision test; four-client simulation | Physical 2×2/1×4 |
| 5 | Labels, Identify, Remove, Forget, rebind with saved configs | TWR-08/09 | Lifecycle + transaction tests; Identify timing | Identify/rebind/forget on devices |
| 6 | Cross-kind backups | TWR-09 | Both-direction safety-copy tests; refusal case | Restore/recall in TWR-17 |
| 7 | Calibration trust consistency and test grid | TWR-11 | Pinned-health tests; grid asset; screenshots | Scale/seam record |
| 8 | Longer ruler | TWR-12 | Span/error tests; screenshot | Ruler measurement on devices |
| 9 | Diagnostics without uploads | TWR-02 | Field/ingress tests | Optional field check |
| 10 | Auth login and expiry recovery | TWR-02/07 | Allowlist + 401 UX tests | Auth-expiry observation |
| 11 | Client reconnect watchdog | TWR-07 | Forced offline/suspend simulation | Sleep/Wi-Fi outcomes |
| 12 | Readiness/QR onboarding | TWR-13 | Preflight/QR unit + screenshot | Join flow in TWR-17 |
| 13 | Practical unified image-first controller, experimental video tucked away | TWR-14 (with 03–13) | Full browser journey, desktop/phone/keyboard | Optional device pass |
| 14 | Operator backup/startup/health/logging instructions | TWR-13 | Runbook dry run; `/healthz`; headers | Reboot/restore rehearsal |
| 15 | Security paired admission when the threat model justifies it | TWR-15 | Conditional negative matrix | Only if triggered |
| 16 | Efficiency measured before optimisation | TWR-16 | Recorded metrics and decisions | Device decode/memory if available |

## Appendix B — Package dependency summary

Read as “left side must be accepted before right side starts”, except where a
package explicitly permits parallel work.

| Package | Depends on |
| --- | --- |
| TWR-01 | — |
| TWR-02 | — |
| TWR-03 | TWR-01, TWR-02 |
| TWR-04 | TWR-03 |
| TWR-05 | TWR-03, TWR-04 |
| TWR-06 | TWR-03, TWR-04 |
| TWR-07 | TWR-06 (status surface), TWR-02 (login route) |
| TWR-08 | TWR-03, TWR-06 |
| TWR-09 | TWR-08 |
| TWR-10 | TWR-03, TWR-08 |
| TWR-11 | TWR-03, TWR-06, TWR-10 |
| TWR-12 | TWR-11 |
| TWR-13 | TWR-02, TWR-07, TWR-09 |
| TWR-14 | TWR-03 … TWR-13 (parity) |
| TWR-15 | TWR-08, TWR-09; conditional on §7.3 |
| TWR-16 | TWR-06, TWR-10, TWR-14 |
| TWR-17 | TWR-03 … TWR-13, TWR-14; TWR-15 before any untrusted-network claim |

Branches that may run in parallel without violating the graph: TWR-05 with
TWR-06 after TWR-04; TWR-08 with TWR-11 after TWR-03/06; TWR-13 with TWR-12
after TWR-09. TWR-15 and TWR-16 are not on the critical path to TWR-17's
hardware record, but neither may be simulated by other evidence.

## Appendix C — Glossary

| Term | Definition |
| --- | --- |
| **Physical / measured wall** | Layout in millimetres using pinned panel/bezel measurements. |
| **Logical wall** | Layout in abstract units using placements; the demonstrated mode. |
| **Fill** | `cover`: fill the wall bounds, cropping the source. Default. |
| **Fit whole image** | `contain`: show every source edge, adding bars. |
| **Arrangement** | A named saved layout snapshot. |
| **Presentation** | The active combination of layout and scene shown now (not a saved object in this milestone). |
| **Render acknowledgement** | A client report that it attempted/completed a paint for a token. |
| **Mapping status** | Why a device can/cannot receive a correct frame. |
| **Safety copy** | A generated named layout saved in the same commit before a destructive/cross-kind switch. |
| **Forget** | Remove an offline roster entry; keeps measurement history and saved snapshots as reservations. |
| **Revoke** | Invalidate a device credential (only with pairing). |
| **Hardware gate** | A signed physical acceptance row; cannot be closed by software. |
