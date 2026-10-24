# Stages 3-5 contract (R3 remainder, R4 native video, R5 field readiness)

Source of truth for the data shapes the parallel work shares. Scope is software
only. Optical, physical suspend, iOS decode and soak gates stay MISSING and
must be reported that way. Roadmap (read only, untracked in the main checkout):
`/var/home/oak/Codes/projects/tablet-wall-ai/docs/planning/tablet-wall-roadmap-2026-10-23/ROADMAP.md`.

## Rules for every worker

- Never bind port 8000, run `make dev`/`make run`, or touch `tablet-wall.db`
  in any checkout. Tests use temp DB/media dirs and free ports only.
- Use `/var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python` from the
  worktree. Run `python -m pytest -q`, `node tests/client_image.test.js`,
  `node tests/client_view.test.js` before reporting. Report real counts.
- Stay inside the files you own. Report any shared-file change you need
  (`main.py`, `client.js`, `PROTOCOL.md`) as a minimal hunk, kept additive.
- Do not push. Commit on your worktree branch with a conventional message.

## Video asset descriptor (additive to the v2 still descriptor)

Stills omit `kind` (or `kind = "still"`). A ready video asset adds:

| field | type | notes |
| --- | --- | --- |
| `kind` | `"video"` | |
| `mime` | `"video/mp4"` | |
| `url` | string | ranged, same-origin object URL |
| `bytes` | int | <= 250 MiB |
| `durationMs` | int | <= 600000 |
| `intrinsicWidth`, `intrinsicHeight` | int | coded display size after rotation metadata |
| `codec` | string | RFC 6381, e.g. `avc1.42C01F` |
| `profile`, `level` | string | e.g. `Constrained Baseline`, `3.1` |
| `pixelFormat` | string | must be `yuv420p` |
| `frameRate` | number | |
| `bitrate` | int | bits per second, from container |
| `faststart` | bool | true after ingest (moov before mdat) |
| `audio` | bool | audio tracks are allowed but ignored (muted) |
| `poster` | thumbnail object or null | same shape as a still `thumbnail` |

Ingest accepts only H.264 (Constrained Baseline/Main/High up to level 4.1)
in MP4/MOV with `yuv420p`, at most 1920x1080 and 60 fps. A faststart remux is
lossless (`-c copy -movflags +faststart`). Anything else is rejected with an
actionable reason. No transcoding. ffprobe/ffmpeg run with fixed argv,
`-protocol_whitelist file`, no shell, inside the existing worker's time and
memory bounds.

## Playlist item and session policy

- A playlist item is `{asset, dwell_ms}`. For a video item the server sets
  `dwell_ms = durationMs`; the validator accepts it up to 600000 even though
  stills cap dwell lower only by their own rule.
- `session.policy` is `"online"` (default, current behavior) or `"strict"`.
  Strict never commits with a missing frozen-cohort member. If the cohort is
  not ready by the preparation deadline the session goes to state `blocked`
  with `blocked_reason` and the missed members, and the operator must Retry
  (new version) or Stop. Online keeps the bounded hold and miss records.
- Loops are occurrences. Native `loop` is never set on the element.

## Frames (protocol 3, additive)

- `prepare` for a video asset adds `media: {kind: "video", duration_ms,
  buffer_goal_ms, start_lead_ms, prepare_timeout_ms}`. Defaults: goal 5000,
  lead 1000, timeout 30000.
- `ready` from a client adds `video: {metadata: bool, seeked: bool,
  buffered_ahead_ms: int, play_ok: "yes"|"needs_gesture"|"no", rvfc: bool}`.
  The server counts a video lease ready only when `metadata`, `seeked`,
  `play_ok == "yes"` and `buffered_ahead_ms >= min(goal, remaining)`.
- `commit` for video adds `start_media_ms` (0 for a fresh occurrence).
- Client to server `video_sample: {session_id, version, occurrence,
  media_ms, target_ms, drift_ms, rate, source: "rvfc"|"time"}` at most once
  per second. The server keeps the latest sample per lease and surfaces it
  in `playback_status`. Drift = observed media time minus compensated target.
- Client correction: deadband 50 ms; rate 0.98..1.02 proportional inside
  50..250 ms; a single local seek above 250 ms, at most one per 5 s. A
  superseded version cancels every timer, rate change and seek.

## Diagnostics (R5, additive HTTP)

`GET /diagnostics` (operator surface only; not on the tablet origin) returns
`{media: {quota_bytes, used_bytes, free_bytes, reserve_bytes, objects, assets,
orphans}, db: {schema, bytes}, backup: {last_manifest_at|null}, clients:
{online, total}, wake_lock: reported per client in the roster as
`wake_lock: "held"|"released"|"unsupported"|"insecure"|"denied"`}`.

## Ownership by worker

| worker | owns |
| --- | --- |
| model | `tabletwall/playback.py`, `tabletwall/hub.py`, `tabletwall/writer.py`, tests for them |
| harness | `simulator/**` |
| video-server | `tabletwall/media*.py`, new `tabletwall/video.py`, `tabletwall/persist.py` (only for video schema), media routes in `main.py`, video backup closure, tests |
| field | `deploy/**`, `GET /diagnostics`, wake-lock + origin-rebinding in `client.js`, tests |
| video-client (wave B) | `client.js`, `view.js`, `controller.js` playback panel, `PROTOCOL.md` video section, client tests |
