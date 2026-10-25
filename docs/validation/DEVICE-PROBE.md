# Device decode and suspend probe

Status: the standalone probe and its desktop smoke runner exist and are tested.
`physical-decode-suspend` and `ios-safari` remain **MISSING**. A desktop
Chromium or WebKit run validates the probe page, not a tablet, decoder,
compositor, panel or iOS Safari.

The probe records what the page can observe: play, pause, loop, seek, mute,
media events, `requestVideoFrameCallback` frame timing, buffered/seekable
ranges, dropped-frame counters where the engine exposes them, visibility, page
instance lineage, wake-lock and fullscreen state, and explicitly unavailable
APIs. It cannot see decode-to-glass, a decoder freeze caused below the media
element, or an operating-system low-memory kill.

## Files

| Path | Purpose |
| --- | --- |
| `tools/device_probe/index.html` | Standalone page, controls, embedded contract. |
| `tools/device_probe/probe.js` | Evidence capture and bounded persistence. |
| `simulator/browser/decode_probe.py` | Clip generator, loopback static server and desktop Chromium/WebKit smoke. |
| `tests/test_decode_probe.py` | Contract, clip and pure report checks. |
| `docs/validation/DEVICE-PROBE.md` | This procedure. |

The page is plain HTML and JavaScript. It has no build step, network fetches
other than the media URL, or dependency on application code.

## Desktop smoke

```sh
uv sync --group browser
uv run --group browser python -m simulator.browser.decode_probe \
  --artifacts /tmp/opencode/tw-decode-probe-smoke-1
```

The artifacts directory must be new and outside the repository. The runner:

1. Generates a 10 s, 30 fps, 640×360 H.264 MP4 with a burned-in frame number,
   time in seconds and progress bar. The clip is retained as
   `decode-probe-10s.mp4` and hashed.
2. Serves only `/`, `/index.html`, `/probe.js` and `/clip.mp4` from a free
   loopback port. It does not use port 8000 and does not expose the repository.
   Single-range requests are supported so seeking uses real bytes.
3. Opens the probe in desktop Chromium. Chromium is required.
4. Opens the probe in desktop WebKit when Playwright can launch it. A missing
   WebKit executable, missing host libraries or missing H.264 support is
   recorded as an `unsupported` scenario, not a failure.
5. Exercises fresh play, pause, seek, resume, loop wrap, mute, an operator
   marker and a page reload. It checks reload lineage and bounded storage.
6. Writes probe JSON, console/page-error JSON, screenshots, the clip and
   `report.json`.

Run the smoke twice in separate artifact directories and compare the exact
counts. Both runs must keep `hardware_gate_status = MISSING`. A WebKit skip is
recorded in the `desktop-webkit` scenario; it is not a pass for iOS Safari.

Expected shape with both engines available:

- `checks`: 40/40 (20 per engine at the time of writing).
- `desktop-chromium`: `passed`.
- `desktop-webkit`: `passed` or `unsupported`.
- `ios-safari`: `unsupported`.
- `completion`: `incomplete` because the iOS Safari scenario and physical
  observations are missing.
- `gate`: `physical-decode-suspend`; `evidence_kind`: `desktop-browser`.

A Chromium failure returns a non-zero exit status. WebKit `unsupported` does
not.

## Serve the page for a tablet

The page needs a secure context for Wake Lock and Fullscreen. A trusted HTTPS
origin, or `localhost`, satisfies that; a plain HTTP LAN origin does not.
Serve `index.html`, `probe.js` and a burned-in clip from a trusted origin. Do
not use port 8000 for this kit.

Query parameters:

| Parameter | Meaning |
| --- | --- |
| `src` | Required media URL, absolute or same-origin relative. |
| `source_name` | Source filename retained in the evidence. |
| `source_size` | Source byte count retained in the evidence. |
| `source_sha256` | Source SHA-256 retained in the evidence. Compute it on the host, not in the page. |
| `run` | Stable run id for storage lineage. Use one tab and one browser profile per run. Default `default`. |
| `autoplay=1` | Start muted playback after load. Muted autoplay is still subject to the platform; the play-promise outcome records the result. |
| `loop=1` | Start with looping enabled. |

Example (one URL; line breaks are only for this document):

```
https://probe.example.test/?src=/decode-probe-10s.mp4&source_name=decode-probe-10s.mp4&source_size=<bytes>&source_sha256=<host-computed-sha256>&run=tablet-a-20261025
```

Use a new `run` id for each device/scenario campaign. Changing `run` starts a
new lineage and a new storage namespace. The page supports one active tab per
run id; two tabs sharing one run id can overwrite the same local summary.

## Evidence model

Every load creates a page instance with a UUID and a monotonically increasing
`page.sequence`.

- `sessionStorage` holds the current bounded session snapshot. It survives a
  reload in the same tab.
- `localStorage` holds a bounded ledger of page instances, the last bounded
  summary and the list of unobserved gaps. It survives a low-memory termination
  and a new tab in the same profile.
- Writes happen at least once per second and on `pagehide`,
  `visibilitychange` hidden, `freeze`, markers and control actions.
- Arrays are capped by the embedded contract. When the oldest rows are dropped,
  `persistence.trimmed` records how many and by which category. A non-zero
  count means the earliest rows are no longer in the download.
- Storage errors are recorded as `persistence.session_storage` or
  `persistence.local_storage` errors. The page keeps running in memory, but
  cross-reload evidence is then incomplete.

On a new load, the previous instance's last seen wall time is compared with the
new start. The difference is written to `lineage.unexplained_gaps` with
`cause: null` and `observation: "unobserved"`. The page deliberately does not
label that gap as a reload, suspension, low-memory termination or decoder
freeze. Only an operating-system or browser log, and the operator's notes, can
distinguish those causes.

`unavailable` names every API the page checked and could not use. Absence of a
dropped-frame counter is not zero drops; it is unavailable.

## Fields to retain

Retain the downloaded JSON, not screenshots of the JSON. The important fields
are:

| Area | Fields |
| --- | --- |
| Identity | `page.instance_id`, `page.run_id`, `page.sequence`, `page.previous_instance_id`, `page.navigation`, `page.started_at`, `page.started_monotonic_ms`. |
| Lineage | `lineage.sessions`, `lineage.previous_summary`, `lineage.unexplained_gaps`, `lineage.gaps_trimmed`. |
| Environment | `environment.user_agent`, `environment.platform`, `environment.viewport`, `environment.device_pixel_ratio`, `environment.orientation`, `environment.display_mode`, `environment.secure_context`, `environment.codec_support`, `environment.api_support`. |
| Source | `source.src`, `source.name`, `source.size`, `source.sha256`, `source.media.duration`, `source.media.video_width`, `source.media.video_height`. |
| Play | `play.attempts[].trigger`, `.outcome`, `.elapsed_ms`, `.error`, `.current_time`; `play.last_outcome`. |
| Media events | `media_events[].name`, `.at`, `.mono`, `.current_time`, `.ready_state`, `.buffered`, `.error`. Required event subscriptions are in the page contract; core events must appear in every fresh run. |
| Playback samples | `samples[].current_time`, `.ready_state`, `.buffered`, `.seekable`, `.played`, `.dropped_video_frames`, `.total_video_frames`, `.frames_presented`, `.visibility`, `.wake_lock`, `.fullscreen`. |
| Frame callbacks | `frame_callbacks.count`, `.rows[].metadata.mediaTime`, `.presentedFrames`, `.expectedDisplayTime`, `.width`, `.height`; `.wall_gap_ms`, `.media_gap_ms`, `.presented_delta`, `.gaps`. |
| Counters | `counters.dropped_video_frames`, `.total_video_frames`, `.frame_callbacks`, `.presented_frames`, `.playback_quality`, `.get_video_playback_quality`, webkit counters when present. |
| Page lifecycle | `lifecycle[]` for `pagehide`, `pageshow`, `visibilitychange`, `freeze`, `resume`, `resize`, `orientationchange`, fullscreen changes and play-promise settlement. |
| Control/operator | `actions[]`, `markers[]`, `environment.wake_lock`, `environment.fullscreen`. |
| Persistence | `persistence.flushes`, `.last_flush`, `.trimmed`, `.session_storage`, `.local_storage`. |
| Unsupported | `unavailable`. |

Keep the raw camera file outside the repository and record its path, bytes,
SHA-256, camera frame rate, exposure and rolling-shutter direction in the run
notes. Do not commit personal data, device identifiers or raw captures without
operator authorization.

## Operator procedure

Before each scenario:

1. Record the exact device model, OS build, browser name/version, display
   scaling/DPR, orientation, mount position and clip SHA-256.
2. Confirm the page shows the burned-in frame/time overlay.
3. Download the JSON at the end of the scenario. Name it
   `device-probe-<device>-<scenario>-<timestamp>.json`.
4. Press a marker before and after every externally caused event. Use these
   labels: `fresh-start`, `fresh-playing`, `loop-on`, `loop-wrapped`,
   `seek-5s`, `app-out`, `app-in`, `lock`, `unlock`, `reload-before`,
   `reload-after`, `camera-start`, `camera-stop`, `memory-start`,
   `memory-return`.
5. If an independent camera is running, record which marker on screen
   corresponds to the camera start and end.

### 1. Fresh play

1. Load the probe URL. Do not press Play yet.
2. Press **Mark** with `fresh-start`.
3. Press **Play**.
4. Watch for a visible advancing picture, not only a play button state.
5. Wait at least 30 s. Press **Mark** with `fresh-playing`.
6. Download JSON.

Retain: `play.attempts` for the initial attempt (resolved or rejected with the
error name), `media_events` for `loadstart`, `loadedmetadata`, `canplay`,
`playing`, `current_time` before and after, `frame_callbacks.count`, and
`environment` values. A rejected promise with no visible playback fails the
scenario. A resolved promise without advancing frames also fails.

### 2. Loop

1. Press **Mark** with `loop-on`.
2. Press **Loop** so it reads on.
3. Seek to about 8 s with the slider or the page API.
4. Let playback wrap. Immediately press **Mark** with `loop-wrapped`.
5. Watch for at least one further wrap, then download JSON.

Retain: a `current_time` decrease while `paused` remains false, continuing
`playing`, no terminal `ended` that stops the session, frame callbacks before
and after the wrap, and any `waiting`/`stalled` gap. `mediaTime` may restart at
the loop boundary; record it rather than assuming monotonicity across a loop.

### 3. Seek

1. Pause playback.
2. Seek to about 5 s. Press **Mark** with `seek-5s`.
3. Confirm the burned-in frame/time changes to about 5 s.
4. Resume playback. Wait for frames to advance.
5. Download JSON.

Retain: `media_events` with `seeking` and `seeked`, `current_time` near 5 s,
`ready_state` recovery, `waiting` duration, `play.attempts` for the resume, and
frame callbacks after resume. A pending resume play promise can coexist with
advancing playback on some engines; record the outcome instead of treating the
promise alone as failure.

### 4. App switch

1. Press **Mark** with `app-out`.
2. Open the app switcher or the home screen for about 10 s. Do not kill the
   browser.
3. Return to the probe. Press **Mark** with `app-in`.
4. If playback is paused, press **Play** and record the new attempt outcome.
5. Wait for frames. Download JSON.

Retain: `lifecycle` entries for `visibilitychange`, `pagehide` and `pageshow`
with `persisted`, `samples` before and after the switch, `lineage` on return,
`environment.wake_lock` release state, and the `current_time` gap. A mobile
engine may suspend without firing `pagehide`; record the missing observation
rather than inventing it. A play attempt after return is separate evidence.

### 5. Lock and unlock

1. Press **Mark** with `lock`.
2. Lock the device for at least 30 s. Leave it locked; do not interact.
3. Unlock and return to the probe. Press **Mark** with `unlock`.
4. If playback does not resume, press **Play** and record the outcome.
5. Download JSON.

Retain: `visibilitychange`, `pagehide`/`pageshow`, wake-lock state transitions,
`current_time` before and after, and whether the screen stayed on. A wake-lock
state of `active` before lock and `released` after is expected device behavior,
not a probe failure. Do not claim the device kept the screen awake unless the
screen recording shows it.

### 6. Low-memory reload

This procedure observes a real termination. Do not simulate it by editing
JavaScript or clearing storage.

1. Start fresh play and press **Mark** with `memory-start`.
2. Record the current page instance id and sequence from the page line.
3. Put the browser under memory pressure with other applications or the
   platform's documented memory-pressure tool. Do not use a debugger to remove
   the page.
4. If the page disappears, reopen the same URL with the same `run` id. Press
   **Mark** with `memory-return`.
5. Download JSON. Also retain any operating-system/browser termination log,
   console output or screen recording available.
6. If the page survives, stop and record that no low-memory termination was
   induced. Do not call survival a pass for low-memory behavior.

Retain: `page.sequence` increment, `lineage.unexplained_gaps` with
`cause: null`, `lineage.previous_summary` when a flush survived, and
`persistence` state. Only label the event "low-memory termination" when an OS
or browser log proves it. Otherwise label it "unexplained reload or
termination". The page intentionally leaves the cause blank.

### 7. Page reload

1. Press **Mark** with `reload-before`.
2. Reload the page through the browser UI. Do not clear site data.
3. Wait for playback and frames. Press **Mark** with `reload-after`.
4. Download JSON.

Retain: `page.navigation.type = "reload"`,
`page.navigation.session_storage_present = true`, `page.sequence` one greater
than before, `page.previous_instance_id` equal to the prior instance,
`lineage.previous_summary`, at least one `lineage.unexplained_gaps` entry, and
fresh media events. A sequence that returns to 1 means storage was lost; record
that and do not claim lineage.

### 8. Independent camera recording

The page cannot see the panel. A camera is the independent reference for
decode-to-glass and freeze claims.

1. Mount the camera on a tripod so the whole active area and the burned-in
   overlay are visible. Record the camera model, frame rate, exposure, focus,
   rolling-shutter direction and any dropped camera frames.
2. Include a wall clock or a visible flash in frame. Document how camera time
   maps to page wall time.
3. Press **Mark** with `camera-start`; start the camera.
4. Run the scenario (fresh play, loop, seek, app switch, lock/unlock or
   decoder-freeze attempt). Leave at least 10 s of post-event footage.
5. Press **Mark** with `camera-stop`; stop the camera.
6. Retain the raw camera file outside the repository with its SHA-256, and keep
   the matching probe JSON.

Use the burned-in `FRAME nnnn` and `ss.mmm` overlay to align camera frames with
`frame_callbacks.rows[].metadata.mediaTime` and `current_time`. Do not derive a
decoder freeze from dropped counters alone. A frozen picture with advancing
`currentTime` and no rVFC callbacks is a page-visible stall; the camera shows
whether the glass advanced. A frozen picture with advanced `presentedFrames`
and a moving camera clock points below the page and needs device-lab
instrumentation.

### 9. Operator markers

Press **Mark** immediately before and after every external action. An empty
label is accepted, but use the names above. A marker records page wall time,
monotonic time, `current_time`, `ready_state`, paused state and visibility.
Markers are part of the downloaded JSON. Do not add markers after the fact; if
one is missed, note the gap in the run notes.

## Interpreting the log

- A `waiting` or `stalled` media event alone does not prove a decoder freeze.
  Correlate it with a stopped `current_time`, missing frame callbacks and the
  camera recording.
- `frame_callbacks.gaps` contains callback wall/media-time gaps and sampler
  gaps. The sampler gap note says the interval was observed without a callback;
  it does not assign a cause.
- `lineage.unexplained_gaps` is deliberately cause-free. A low-memory
  termination, a manual reload, a bfcache restore and an OS suspension can all
  produce a gap.
- `unavailable` is part of the result. A missing API is not a pass for that
  API. In particular, missing `playbackQuality` means the engine does not
  expose that legacy object, not that no frames were dropped.
- `persistence.trimmed` above zero means the first rows are gone. Retain the
  counts in the report; do not reconstruct missing rows.
- A pending `play()` promise can coexist with playback on some engines. Record
  the outcome and the visible playback separately.
- A page instance without a `pagehide` or `pageshow` is not proof that the page
  was killed. It means the page did not observe the transition.

## What this kit cannot prove

- Real decoder-freeze induction. The review identifies a device-lab
  prerequisite; this page does not contain a freeze injector and must not fake
  one.
- iOS Safari. Playwright WebKit on Linux is desktop WebKit, not an iOS device
  or Safari media stack.
- Physical decode, suspend, loop, seek, app-switch, lock/unlock, low-memory or
  wake-lock behavior on a tablet.
- An optical result. The clip is synthetic and the burned-in overlay is for
  alignment, not a panel timing measurement.
- That a camera capture is synchronized with page time beyond the documented
  marker and clock mapping.

Until an operator records the required device evidence, keep both
`physical-decode-suspend` and `ios-safari` at **MISSING**. The desktop smoke
report is `desktop-browser` evidence and always leaves the hardware gate
MISSING.

## Tests and artifacts

```sh
uv run pytest -q tests/test_decode_probe.py
uv run pytest -q
```

The test file checks the embedded contract, control/download/reset presence,
bounded-persistence limits, clip generation and the pure report rules. It does
not need Playwright or a browser.

Artifacts for each smoke run: `decode-probe-10s.mp4`,
`probe-desktop-<engine>.json`, `probe-desktop-<engine>-actions.json`,
`console-desktop-<engine>.json`, `probe-desktop-<engine>.png` and `report.json`.
The report records the artifact hashes, browser versions, ffmpeg/ffprobe
versions, repository state, every check, every scenario, failures, skipped and
unobserved work, limitations and `completion`.

## Unresolved

- **Real decoder-freeze induction:** unresolved. It needs a device lab or a
  supported platform fault-injection method. No desktop smoke result can
  substitute.
- **iOS Safari:** unresolved. It needs an operator with an iOS device, a
  supported Safari build, trusted HTTPS and the procedure above.
- **Physical decode/suspend:** unresolved. It needs supported mixed tablets,
  power, time, an operator and the camera procedure.
