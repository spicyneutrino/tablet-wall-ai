# Task-led controller status

Implementation, regression verification, and independent review are complete for the supervised, images-only controller. This is not a merge, deployment, or hardware approval.

The reviewed candidate is `608e9230047087f910f7cf5d4d67cd7908e099f8`. Its application SHA-256 is `3c3f853e9fdd47b1b17e236961d9c7baff9887ab03e12af10e025bccb98626c6`, matching the application exercised by the integrated regression runs.

## Implemented experience

- **Images** starts with a searchable thumbnail library. The selected image, Fit or Fill choice, and Show action stay together. Add image exposes the existing upload capability and its launch restrictions.
- **Tablets** starts with the roster and Identify actions. Joining help remains available through Add tablets. Names, placement, removal, Forget, and replacement use their existing guarded owners.
- **Arrange** starts with shape and membership, followed by the spatial preview and Apply review. Required model, mounting, calibration, and release decisions expand for review. Custom editing follows the ordinary arrangement flow.
- **Saved** distinguishes arrangements from scenes and uses actual geometry or available image thumbnails. **Settings** leads with readiness and defers destructive actions.
- One shared canvas moves between tasks. Its aspect follows the wall bounds. Tablet names and statuses no longer cover the artwork. Geometry editing is limited to Arrange.
- Applied output and local previews remain distinct. Apply arrangement changes geometry. Show image changes content. Current tablet reports remain separate from server acceptance.

The [selected direction](EXPERIENCE-DIRECTION.md), [workspace implementation](EXPERIENCE-IMPLEMENTATION.md), and [stage verification](EXPERIENCE-STAGE-ACCEPTANCE.md) record the design and behavioral details.

## Verified software

The [integrated acceptance report](EXPERIENCE-INTEGRATED-ACCEPTANCE.md) records:

- 38 behavioral scenarios with 855 passing checks.
- 1,830 passing Python tests and 75 passing Node tests across 30 files.
- 108 workspace checks and 44 experience observations.
- 96 loaded script-response hashes matching source.
- Passing scoped Ruff, mypy, and private generated-ingress checks.

The runs cover separate previews and commits, stale responses, uncertain writes, keyed forms, saved recall, lifecycle review, uploads, keyboard interaction, and current render evidence. Root independently checked the scenario totals, response-hash records, and application identity. The [final independent review](EXPERIENCE-FINAL-REVIEW.md) approved both the functional and experience gates after six fresh jobs with 137 passing checks. No proven P1 or P2 issue remained.

## Remaining limits

Phone measured Apply requires scrolling. Expanded hardware review is longer than the selected concept's healthy example. The independent reviewer accepted these tradeoffs after verifying that one Page Down exposes review and Apply without opening advanced details.

Cached Chromium repeatedly failed during some enlarged-text full-page captures. The final responsive evidence uses explicitly labelled viewport captures while retaining the behavioral assertions. Failed attempts remain recorded. Full-page capture reliability is not verified.

Native browser zoom, IME, screen readers and other assistive technology, real tablets, optical continuity, sleep, real hotspot or TLS operation, and prolonged unattended use remain unverified by this redesign. Video remains experimental.

Changes are on `work/tablet-wall-frontend-redesign`, associated with [PR #29](https://github.com/spicyneutrino/tablet-wall-ai/pull/29). The PR remains stacked on the readiness branch. No merge or deployment is included in this delivery.
