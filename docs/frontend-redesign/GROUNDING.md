# Existing behavior and redesign constraints

Source `1288dd1`, independent Sol High review. This is grounding for synthesis,
not an accepted redesign plan. The Opus review is still independent and pending.

## How a wall change reaches a screen

The backend owns durable arrangements, scene, measurement revisions, labels and
snapshots. `/api/v3/config` projects them with runtime registration/mapping/render
facts. Its durable ETag excludes heartbeats, but registration and saved-data
changes can invalidate a reviewed command even without new wall geometry.

In the current browser, `physical.js` composes shared state and the operator
modules. Image selection and arrangement editing are local intent. A scene write
sends asset identity and global fit with `If-Match`; a reviewed grid write carries
its original guards. The server validates, persists a detached proposal, then
broadcasts. Tablets report rendering with connection/generation/revision/asset and
mapping tokens. Only fresh matching evidence contributes to the live count.
The stage can preview local intent, but must never count it as applied or shown.

This separation is important even if revision and ETag identifiers disappear
from the main interface. One local Apply-everything button must not imply atomic
image/arrangement persistence when the backend has separate commands.

## What users encounter

The primary `/controller/physical.html` can operate logical and measured grids,
images, saved arrangements and lifecycle actions. `/controller/` is a separate
compatibility editor with some logical custom geometry, bezel and scene controls.
The primary page loads two large inherited CSS files and exposes task controls
in a narrow rail. On a phone, the stage precedes the navigation and recovery work.

The root inspected the independent desktop and phone screenshots. The preview is
the useful visual centre; technical header facts, duplicated vocabulary, long
forms and separated upload/selection make basic tasks harder to discover.
Do not remove advanced functionality merely to make the first viewport shorter.

## Proven defects to include

Issue #23 records the independently reproduced defects: unsaved label loss after
changing selected tablet, and final-tablet removal failing with an unavailable
Clear wall instruction. Use retained per-device form drafts or an explicit
leave decision, and the existing guarded lifecycle removal command. Review the
related calibration dirty flags rather than assuming they are safe.

## Preserve

- One authoritative config/session, guarded writes and retained conflicts.
- Separate live wall, arrangement preview and image preview.
- Global Fit/Fill, unavailable bytes, selection/upload/show separation.
- Correct action targets, current paint evidence and offline reservations.
- Remove versus offline Forget versus same/different-hardware replacement.
- Saved layout/history repair, exact revision pins and cross-kind return points.
- Model confirmation, inset/zoom/rotation guards and visible uncertainty.
- Keyboard/numeric alternatives, focus retention and responsive controls.
- Existing advanced behavior, deliberately migrated before retiring old entry points.

## Image addition is an operator capability

The user explicitly requires image addition from the application. The hotspot
currently disables uploads even for the loopback operator, although it already
has loopback/proxy admission. The synthesized plan must provide a supported,
operator-only image-addition path while keeping tablet ingress closed. A disabled
button and filesystem instructions alone do not fulfill the requested workflow.
Do not expose a browser switch that relaxes server admission or require the root
to modify the live deployment. Existing unsupported profiles must remain honest.

## Design study

VISUAL-PHILOSOPHY.md applies the user-invoked canvas-design skill. The original
PNG study is stored at
`/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/visual-study/joined-fields.png`.
It is an abstract continuity/material study, not the final interface or a new
reference constraint. Root inspected it and refined clipping/field extent.
The application should follow the supplied reference's Grotesk typography;
the study's serif is an artistic choice, not an app component requirement.

## Evidence

Full Sol report, screenshots and source identities are in
`/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/reviews/sol-high-1288dd1/`.
The report includes a real four-client journey, replacement/conflict probes and
two UI alternatives. Its harness failures remain documented; it is not a full
all-green acceptance run. No real-device or deployment result follows.
