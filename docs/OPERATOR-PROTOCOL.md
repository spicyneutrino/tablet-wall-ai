# Still-image operator protocol

This describes the integrated image-wall extension to [PROTOCOL.md](../PROTOCOL.md).
It does not establish real-tablet accuracy or acceptance of experimental playback.

## Authoritative state

`GET /api/v3/config` and a protocol-3 controller's first `snapshot.config`
carry `operator_state_version: 1`. The response contains the actual tagged
`layout`, `scene`, `revision`, `generation`, and `etag`, plus these projections:

| Field | Meaning |
| --- | --- |
| `device_labels` | Durable operator labels keyed by device ID |
| `snapshots.layouts`, `snapshots.scenes` | Saved names, raw snapshot digests, kinds, and validity |
| `capabilities` | Supported layout kinds, fits, operator actions, uploads, diagnostics, and login support |
| `runtime.devices` | Current transport, viewport, mapping, render, and Identify observations |
| `runtime.presentation` | Whether static content or experimental playback owns the display |
| `referenced_displays`, `referenced_calibrations` | Exact revisions pinned by active physical slots |

Runtime observations and content availability do not change the durable ETag.
Layout, scene, labels, saved snapshots, and measurement history do. Readback
does not issue render instructions. A missing image file retains its asset
identity and reports `available: false`.

Writes and guarded previews require the latest config ETag in `If-Match`.
After a 412, fetch state and review the change again. Static scene/layout
changes commit before notifications and stop experimental presentation ownership.
Cross-kind layout replacement creates a named return point in the same
transaction and reports `previous_layout_saved`.

## Tablet observations

Protocol-3 welcomes include an opaque `connection_id`. Image-capable clients
can advertise `render_ack`, `identify`, and `image_contain`. Older clients
without paint acknowledgements remain unconfirmed.

Every static `render` instruction carries a token with `connection_id`,
`generation`, `revision`, `render_seq`, `mapping_revision`, and `asset`.
The client echoes it in `render_ack`, with a positive increasing `report_seq`,
`status`, nullable `reason`, `viewport`, and boolean `visible`. The viewport
contains CSS `width`/`height`, `dpr`, `orientation`, launch `mode`, and
`visual_scale`.

Reports are limited to 4,096 encoded bytes. Ownership, token, sequence,
capabilities, and validated viewport must agree. An image reports `displayed`
after drawing and a current-token animation-frame check, not merely decoding.
Evidence expires after 15 seconds using the server's monotonic clock.

The operator projection uses these canonical fields, without compatibility aliases:

| Projection | Fields |
| --- | --- |
| `mapping` | `state`, `reason`, `revision`, `profile_revision`, `calibration_revision`, `health`, `viewport` |
| `render` | `state`, `current`, `expected_token`, `accepted_token`, `accepted_status`, `received_at`, `age_ms`, `reason` |
| `identify` | Nullable command metadata with `state`, `active`, and `remaining_ms` |

Only matching current paint evidence counts toward image display. An offline,
hidden, stale, failed, unsupported, or identifying tablet does not count.
The denominator includes participating placements and offline reservations.
Browser evidence does not prove that an OS screen is lit or that seams align.

Use `age_ms` plus locally elapsed monotonic time. `received_at` is a server
monotonic reading, not a wall-clock timestamp. Fresh evidence for one tablet
must not reset another tablet's evidence age.

## Operator commands

| Route | Behavior |
| --- | --- |
| `PATCH /api/v3/devices/{id}` | Save `{"label": "..."}` or clear it with null |
| `GET /api/v3/devices/{id}/impact` | Read active placement, affected saved references, and history presence |
| `DELETE /api/v3/devices/{id}/placement` | Remove the placement while retaining registration and snapshots |
| `DELETE /api/v3/devices/{id}` | Offline-only Forget; explicitly acknowledge active removal and retain saved references/history |
| `POST /api/v3/devices/{id}/rebind/preview` | Preview replacement of `replaces`, declared same/different hardware, and exact selected snapshot digests |
| `POST /api/v3/devices/{id}/rebind` | Apply that replacement transactionally, including the explicit `new_connection_id` guard |
| `POST /api/v3/devices/{id}/identify` | Temporarily show number/label; optional `duration_ms`; no durable revision change |
| `POST /api/v3/devices/{id}/retry-image` | Send a fresh render token; retain content and wall revision |
| `POST /api/v3/devices/{id}/reconnect` | Close the current socket so the same browser identity reconnects |
| `POST /api/v3/grid/preview` | Build a detached ordered proposal; no state change |
| `POST /api/v3/grid` | Recheck ETag and connection/viewport guards, then apply one arrangement atomically |
| `POST /api/v3/test-pattern` | Publish and select `{"pattern":"grid"}` or `{"pattern":"black"}` as an ordinary image |
| `POST /api/v3/calibration-check` | Check prospective ruler arithmetic without saving |
| `GET /healthz` | Minimal admitted operator health, without paths or secrets |
| `GET /api/v3/readiness` | Admitted operator URL, storage, content, security, and recorded backup/rehearsal information |
| `GET /api/v3/join-qr` | Offline-generated PNG encoding the configured tablet URL, without a credential |

Logical layouts and scenes have v3 list/save/delete/recall routes alongside
physical snapshots. Saving a new calibration does not move existing layout pins.
Same-hardware replacement repairs only the explicitly selected saved layouts.
Different hardware cannot inherit physical measurements by name or model guess.

Grid commands explicitly provide kind, ordered `device_ids`, rows, columns,
gap, padding, sizing, orientation, empty-cell consent, and released reservations.
Physical grids pin profile/calibration revisions; logical sizes remain logical
units. Apply includes the preview's connection/viewport `guards`. Preview is
not an Apply, and offline telemetry cannot supply a new logical size.

Ruler checks name a device, exact profile revision, native quarter turn, CSS
axis, labelled pixel span, measured millimetres, estimated error, and usable
viewport dimensions. The response shows both supplied and derived dimensions
and propagated uncertainty. The UI requires an explicit choice before saving a
ruler result. Keep supplied writes nothing. Nonzero manual offsets remain
visible and prevent a full-panel coverage claim, even in fullscreen.

## Deployment boundaries

Operator reads are admitted independently of uploads. Mutations and guarded
previews also use the existing operator Origin fence. When either deployment
origin is configured, HTTP and WebSocket Host headers must name a configured
host or loopback address. Invalid hosts receive HTTP 400 or a refused socket.
Unconfigured development retains its previous host behavior.

A physical wall refuses legacy layout/scene edits. A newly connecting legacy
controller is closed with 4426 rather than receiving a synthetic logical wall.

The supported HTTP hotspot profile is trusted and unauthenticated. Its Caddy
listener admits only tablet routes; operator controls stay on loopback.
Known-UUID takeover remains a residual risk. The join QR is a URL shortcut,
not device pairing. Shared-secret/TLS reference deployment and real hardware
acceptance have separate requirements.
