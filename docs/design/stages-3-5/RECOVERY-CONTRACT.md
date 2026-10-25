# Bounded group video recovery contract

Scope: strict/online video occurrences only. A still has no media position.
This is software evidence; optical and physical decode remain MISSING.

## Trigger

A recovery starts when one of these is true for a playing video occurrence:

- the client sends `video_fault` after its bounded local recovery is exhausted
  or the browser reports `play_ok: "no"`;
- the server sees a playing device's last accepted sample older than 3000 ms;
- the client reports a committed video stopped with `ended: false`.

Ordinary drift inside 250 ms stays local and never starts a recovery.

```json
{ "type": "video_fault", "session_id": "…", "version": 4,
  "occurrence": {"playlist_revision": 1, "item_index": 2, "loop": 0},
  "position_ms": 2400, "reason": "stalled"|"play_failed"|"buffer_lost" }
```

The frame is accepted only from the current socket, a device in `playing`, the
current occurrence and a fresh session version. `position_ms` is bounded
`0..duration_ms`. A duplicate fault for the same occurrence while recovery is
active is ignored.

## Server state

`Session.recovery` is one record or None:

```
id, occurrence, position_ms, reason, device_id, started_ms, deadline_ms,
attempts, missing, degraded_since_ms
```

`state` becomes `"recovering"`. The pending next item is cancelled; the
current occurrence is re-prepared at `position_ms` with a fresh version and a
fresh common anchor `now + LEAD_MS`. The cohort is frozen and not shrunk.
The recovery preparation uses the normal physical plan and media, plus
`start_media_ms`.

`prepare` for a recovery carries the same occurrence and
`start_media_ms = position_ms`. `ready.video.buffered_ahead_ms` is measured
from that position; the required buffer is
`min(goal, duration_ms - position_ms)`. The commit carries the same
`start_media_ms`. The following boundary is
`commit_effective_ms + (duration_ms - position_ms)`, not the full duration.
A final non-looping occurrence stays final after the recovery commit.

Timeout or a missing required member:
- strict: `blocked`, reason `recovery_timeout`, recovery retained for Retry;
- online: `failed`, reason `recovery_failed`.

Retry from a blocked recovery re-prepares the same occurrence and position with
a new version. At most three recovery attempts per occurrence; the fourth
fault enters the blocked/failed state without another prepare.

Status adds:

```json
"recovery": {
  "id": "…", "occurrence": {...}, "position_ms": 2400,
  "reason": "stalled", "device_id": "<uuid>", "attempts": 1,
  "started_ms": 123, "deadline_ms": 456, "degraded_ms": 789,
  "state": "preparing"|"playing"|"blocked", "missing": ["<uuid>"]
}
```

Stop, a mapping/calibration/layout/rebind change, a clock epoch change and a
socket replacement supersede recovery. Reconnect during recovery sends the
recovery prepare to the replacement socket.

## Client

- On local recovery exhaustion, `play_ok: "no"`, or a committed video that
  stays paused/ended early, send one `video_fault` for the occurrence and
  position. Do not send a second fault until a new commit changes the
  occurrence or position.
- On `playback` state `recovering` (or a `prepare` with `start_media_ms`),
  freeze the active picture, release pending/armed work, and prepare from the
  position. Buffer coverage, probe, commit and samples use the position.
- Keep the previous picture until the recovery commit. Do not paint a
  recovery preparation early.
- On a recovery commit, start at `start_media_ms`; the next natural boundary is
  the remaining duration.
- A recovery that times out shows the normal blocked/failed state; Retry and
  Stop stay available.

## Evidence

Model tests: trigger bounds, duplicate suppression, strict missing, timeout,
retry, attempt cap, remaining-duration boundary, final item, stop/mapping/epoch.

Client tests: fault once, freeze, position-aware coverage, commit at position,
remaining boundary, stale callbacks ignored.

Browser: force one client's play promise to hang, let local recovery exhaust,
observe the server start one recovery, all clients prepare the same position,
one common future commit, the next cut after the remaining duration, and the
degraded interval. Repeat for timeout and final item. Label software only.
