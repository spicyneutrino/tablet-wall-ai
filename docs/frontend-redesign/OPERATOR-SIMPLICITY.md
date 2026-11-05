# Operator workflow simplification

The follow-up to the frontend redesign keeps five tasks in one workspace.
`/controller/` opens the workspace. `experimental.html` retains the old logical
editor. The [operator runbook](../../deploy/IMAGE-WALL-RUNBOOK.md) describes the
current steps; the [design reference](../frontend-design/FINAL-DESIGN.md)
describes the interface and its module ownership.

## Current behavior

Images has one library and one composer. Selection, upload, fit changes, and
comparison create or inspect previews. **Show image** applies content without
changing geometry. **Adjust image** starts a preview of the applied image.
An unavailable image keeps its warning and its asset identity in **Image details**.

Arrange keeps presets, membership, preview, review, Apply, and Discard together.
A pressed preset follows tablet membership, including its rows, columns, and
empty-cell policy. Typing into **Rows** or **Columns** releases the preset
before the field loses focus. A later status render preserves the custom input.
The exact-count guard still requires an explicit **Allow empty trailing cells**
choice for a grid with unused cells.

Tablets keeps **Identify** in the selected-tablet inspector and the Arrange
order list. **Add tablets** contains the join address and QR code. Offline
tablets keep physical recovery guidance without an empty **Recovery** disclosure.

Saved separates arrangements from content. **Recall** applies saved geometry
without changing the image. **Preview** beside a content record opens an image
preview for **Show saved content**. Automatic safety copies are labelled as
restore points. Settings contains server checks, measurements, diagnostics,
and experimental playback.

Status refresh preserves an applied-versus-preview comparison while an image
preview exists. An invalidated authority read queues a fresh read while the
current authority remains stale. Guarded writes still use the existing ETags,
generation checks, revision pins, and uncertain-completion locks.

## Verification at the reviewed application commit

At `ff1f4b737df00cb6f54df78fd304c192dd2140af`, the Node run passed 83 tests with
zero failures. A private desktop-and-phone browser journey passed 14 checks
for native typing before blur, live rendering, focus, and explicit Preview.
The corrections journey passed 55 checks. Both browser fixtures recorded
clean console and unexpected-network logs, matching application and driver
hashes, and process cleanup.

All three final Council reviewers independently accepted that same frozen
head with overall judgments above 9 out of 10. Their reviews combined direct
tests and probes with inspection of the supplied browser evidence. They did
not each repeat every browser journey. Scores are reviewer judgments, not
usability measurements or accessibility certification.

The latest application change affects the grid input handler and its Node
regression. The earlier full Python result of 1,828 passes with two skips
predates later JavaScript changes. It is not a Python rerun at `ff1f4b7`.
The [earlier redesign results](VERIFICATION.md) retain their own source scope.

## Reproduce the committed checks

From the repository root, use a new artifact directory:

```sh
uv sync --all-groups
node --test tests/*.test.js
uv run --group browser python simulator/browser/redesign_acceptance.py \
	--scenario corrections --artifacts /tmp/new-operator-corrections
```

The browser journey needs Chromium installed for the locked Playwright version.
It creates private storage and a private loopback server. It never targets a
live wall database. The focused grid regression is
`tests/operator_grid_releases.test.js`.

The 14-check typing fixture was an external review script, not a committed
acceptance scenario. The Node regression preserves the input-before-render
case in the repository. The committed corrections journey covers the broader
interaction checks described above.

## Verification limits

Physical tablet alignment, native IME, browser-menu zoom, real screen readers,
live ingress, and prolonged soak remain unverified by this follow-up. Desktop
Chromium and emulated tablet viewports do not close those gates. Follow the
[hardware acceptance procedure](../tablet-wall-readiness/HARDWARE-ACCEPTANCE.md)
for recorded real-device validation.
