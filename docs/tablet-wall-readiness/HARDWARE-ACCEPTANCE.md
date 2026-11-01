# Real-tablet acceptance

Status: **not run for the consolidated implementation**. Existing user-reported
2×2 and 1×4 image demonstrations used the logical layout path. They do not
establish measured-layout seam accuracy, sleep recovery, or unattended operation.

Use the supplied iPad and Google tablet measurements. A matching browser screen
signature is a model suggestion, not proof of hardware identity. Record each
device's persistent ID, operator name, actual model, browser version, orientation,
display mode, power settings, and assigned measurement revision. The temporary
on-screen number can change and is not its identity.

Before a trial, save a named return arrangement and verify a backup. Test against
an isolated installation first. Do not overwrite the working wall or its data to
collect evidence.

| Check | Required observation | Status |
| --- | --- | --- |
| Join and identify | Each real tablet appears once; Identify flashes the intended tablet; a reload retains its identity. | Not run |
| Model and viewport | Confirm the suggested model; note estimated measurements and uncertainty; changing zoom, orientation, or display mode cannot silently reuse an invalid mapping. | Not run |
| Measured 2×2 | Apply the numbered preset, use the diagnostic grid, photograph the arrangement, and measure horizontal/vertical discontinuities at each seam. Record values, including failures. | Not run |
| Measured 1×4 | Apply the row preset and repeat the seam observations. Confirm physical mount direction separately from browser orientation. | Not run |
| Fit and fill | Show an image with a marked border and corner labels. Fit shows all source edges; Fill crops as previewed. Black bars, bezels, and uncovered regions match the preview. | Not run |
| Mixed devices | A line or circle crossing an iPad/Google seam has consistent physical scale within the recorded uncertainty. | Not run |
| Saved arrangements | Save both arrangements, restart the trial app, recall each, and verify content and placements. | Not run |
| Replacement | In the isolated trial, replace a cleared browser identity; active and saved arrangements resolve to the intended replacement without overlapping another tablet. | Not run |
| Image failure | Interrupt an image load; the correct tablet reports failure, a stale result cannot mark the next image healthy, and Retry recovers. | Not run |
| Network and restart | Disconnect/reconnect one tablet and restart the trial backend. Record recovery time and every tap or browser reopen needed. | Not run |
| Authentication | On an authenticated trial, sign in from a tablet, expire/sign out the session, and verify a clear recovery path. Tablet ingress continues to deny operator controls. | Not run |
| Screen sleep and sustained run | Test the actual OS sleep/wake settings and a powered still-image run of a duration chosen for the intended use. Record start/end, interruptions, resource observations, and interventions. | Not run |

For each row, attach the application commit, configuration/measurement revisions,
date, evidence paths, observed result, and pass/fail decision. State the tolerance
before judging seam measurements; the current model uncertainty is provisional.
Do not infer a tolerance pass from a photograph alone.

A browser paint report confirms an application rendering result. It cannot prove
that a panel is lit, aligned, or visible to a person. Video and optical
synchronization are outside this images-only acceptance gate.
