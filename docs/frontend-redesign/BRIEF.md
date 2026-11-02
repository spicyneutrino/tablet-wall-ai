# Tablet wall frontend redesign

The user wants one complete, intuitive interface for adding/removing tablets,
arranging and controlling the wall, and adding/selecting images. The current
logical/physical vocabulary and separate controllers expose implementation
choices. Preserve safe tested behavior while giving the operator one clear path.

Use REFERENCE-DESIGN.md as visual guidance, not a portfolio layout to copy.
Warm technical minimalism, purposeful spacing, sentence case, restrained accents
and precise diagrams should support the live wall as the primary visual object.
Create a design philosophy and PNG study under the canvas-design skill.

## Requested sequence

1. Independent current-product reviews from Claude Code Opus 5.5 Medium and
   Codex Work GPT 6.1 Sol High, including rendered flows and feature proposals.
2. Codex Work GPT 6.1 Sol XHigh synthesizes both into a full redesign plan and
   architecture, comparing at least two structurally distinct interaction models.
3. Codex Work GPT 6.1 Sol High implementation in isolated owned scopes.
4. Actual desktop/mobile and keyboard checks with simulated tablet clients,
   image upload/selection, saved arrangements, failures and reconnects.
5. Independent review, inspect diffs, commit and track the redesign in git/gh.

## Starting constraints

Base 89a2c31. Application acceptance is pinned to29148ec; intervening changes
are documentation only. See docs/tablet-wall-readiness/VERIFICATION.md and
reviews/FINAL-SOFTWARE-REVIEW.md. Prior issue7programme and19hardware remain open.
PR21 carries the existing readiness work and is not merged or deployed.

Use one operator surface. Retain logical and measured backend representations
if needed; users should choose understandable outcomes, with calibration and
technical details revealed when relevant. Preserve revision guards, draft
preview/apply/cancel, actual current-render status, safe lifecycle/snapshot repair,
calibration uncertainty and security admission. Never disguise unsupported
operations. In-app image addition must respect the current upload/security
profile; evaluate a safe supported operator path rather than exposing uploads
on tablet ingress. Video stays experimental, not part of the primary workflow.

No live data, asset library, browser sessions, hotspot/firewall, service or real
tablet mutations. Use new private data, unused loopback ports, disposable browser
contexts and synthetic images. Real hardware acceptance stays unrun. No merge,
deployment or credential changes. No framework rewrite without demonstrated need.
All workers are aware they are not alone and must preserve others' edits.
