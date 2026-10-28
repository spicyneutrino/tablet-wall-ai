# Review decisions and provenance

Final adjudication by Sol, gpt-6.1-sol at max reasoning, 2026-10-23.
This record explains the choices in [ROADMAP.md](ROADMAP.md). It does not imply implementation or final independent approval.

## Inputs and authorship

The original [Opus proposal](opus-proposal.md) and [Opus cross-review](opus-review-sol.md) ran through Cursor on Claude Opus 5.5.
The original [Sol proposal](sol-proposal.md) and [Sol cross-review](sol-review-opus.md) were separate Sol max rounds.
The user first requested Opus final authorship after reciprocal review.
The parent [decision trail](decisions.tsv) records Cursor Opus's final quota failure, the Claude Opus fallback rate-limit failure, and the user's explicit Sol substitution.
The final synthesis and transcript notes are Sol-authored.
Neither failed final attempt is a delivered Opus synthesis or an independent review of these final documents.
The existing reciprocal Opus review remains real evidence about the earlier proposals.

The [orchestration snapshot](orchestration.json) preserves accepted provider/model/options for the four planning/review tasks.
Its `running` values are acceptance-time snapshots, not their final status.
The two inspected Opus thread records now report completed with 171 and 152 items.
Failure provenance for the later final attempts comes from the parent's trail and supplied brief. Those unrelated threads were outside this bounded transcript inspection.
See [OPUS_TRANSCRIPT_NOTES.md](OPUS_TRANSCRIPT_NOTES.md) for exact thread/item identifiers and recovery coverage.

## Attention

- Only the parent ran the reported simulator baseline: 23 scenarios and 1075 checks. This author did not rerun application tests.
- That simulator has no real client JavaScript, TCP, media decode, browser pixels or optical synchronization evidence.
- One online roster client plus one associated station does not establish a correlated hardware identity, OS or mixed-device trial.
- Canvas stretching, old-iOS preload, transformed-video behavior and actual tablet sleep remain experiments.
- Runtime/library introspection and primary specifications support a proposed contract, not deployed ingress or device compatibility.
- Every performance/sync target and new operating limit is provisional. No measured speed, capacity or frame-lock claim is made.
- All 323 Opus activity positions were traversed, but only selected truncated evidence was expanded. This is a bounded task-activity review, not a claim of access to unavailable private thinking.
- There is no final independent Opus review of the trace-based synthesis because both Opus routes were unavailable. Self-checks do not replace that review.

## 1. First release scope

Opus originally required clock/readiness and crossfade playlists for its first useful slice. Sol originally required a calibrated physical editor.
Both reciprocal reviews withdrew those oversized release boundaries.
Current `image` scenes, asset IDs and numeric logical placement already exist, so upload does not need either subsystem.

Choose upload-and-show on the current logical wall, with ownership handling, explicit admission, normalization/index, error recovery and backup/restore.
The release has no clock, physical conversion, crossfade, cookie or remote-reload dependency.
Keep actual rendered flow verification, without making a comprehensive fleet harness prerequisite for the upload backend.
This accepts Opus review B6 and Sol review 8, while rejecting either original first-slice scope.

## 2. Device and controller protocol

Opus review B1 argues that unknown-frame tolerance and capability gating can keep the device at v2, with a v3 controller.
Sol review 1 distinguishes additive optional diagnostics from changed physical/timed semantics and chooses v3 for the latter.
Both reviews reject approximate physical projections and legacy tablets that freeze on an arbitrarily chosen playlist still.

Choose one v3 physical/timed contract for device and controller. Preserve v1/v2 logical/static contracts and ordinary uploaded-still descriptors.
Do not implement equivalent physical/timing behaviors through a second v2-capability path.
This spends one explicit migration to reduce the long-term combinations of meanings inside v2.
Capabilities inside v3 still gate actual features and codec evidence.

Evidence is the abstract-unit, centered-cover contract in [PROTOCOL.md](../../../PROTOCOL.md), `drawWallImage` in [client.js](../../../frontend/client/client.js), and exact-v2 branches in [hub.py](../../../tabletwall/hub.py).
Opus's all-capability option is technically possible. It is discarded here as a maintenance choice, not declared impossible.
The roadmap matrix is mandatory acceptance coverage, including cached devices/controllers, old server, HTTP and stored state.

## 3. HTTP and stored-state compatibility

Opus favors additive tables and a permanently valid legacy placeholder column so an old binary might show unplaced tablets.
Sol favors explicit versioned commands, migration validation and rollback using the old data set.
Neither can retrofit a schema refusal into an already old binary.

Choose schema 1 for media/index additions with unchanged legacy JSON, then schema 2 for typed envelopes and physical records.
The new server validates and migrates active/saved data before startup rewrites generation.
Legacy HTTP stays intact only for logical/static state. Fence every affecting legacy mutation when physical/timed state is active.
Use required v3 resource preconditions, `428` for absence, `412` for stale If-Match and `409` for semantic conflicts.

Do not retain a second placeholder wall as an alleged safe downgrade mechanism.
Downgrade requires the matching pre-migration database/media and backup tool. Starting an old binary on upgraded data is unsupported.
New code refuses future schemas without writes. Old manifest readers already refuse unknown manifest versions.
Test old DB/backup fixtures, invalid active records, saved recall, all mutation aliases and restored live reads.
Sources are `_restore_wall_state`/saved validators in [main.py](../../../main.py), [persist.py](../../../tabletwall/persist.py), and [backup.py](../../../deploy/backup.py).

## 4. Cached builds and reload behavior

Opus moves build detection and remote reload into R1 and recommends one reload on `4426`.
Sol points out that cached code lacking that behavior cannot execute the new handler, and proposes bounded fallback to v2 logical mode.
Both value build visibility and static revalidation.

Choose build diagnostics and a one-time v3-to-v2 logical compatibility negotiation, with all v3 assumptions cleared.
Do not reload automatically just because `4426` repeats.
A later command-capable build may reload once per changed served build, then stop on incompatibility.
Expect manual refresh/origin migration for current cached tablets.
Remote reload remains useful but is deferred from the minimum upload dependency.
Test old-server rollback, mismatched build, repeated 4426 and an old cached script that ignores reload commands.

Current `handleFrame/openSocket` has no reload handler, and [main.py](../../../main.py) already serves static files with `Cache-Control: no-cache`.
Neither build hashes nor a server upgrade can remotely repair a build that never implemented the update path.

## 5. Geometry authority

Opus originally computes the entire CSS transform on the server, then revises to a content-to-panel boundary.
Sol initially leaves composition ownership too open, then accepts authoritative server render plans.
The remaining choice is where live viewport information belongs.

Choose Opus review B2's panel boundary.
The server owns pose, bezels, fixed bounds, sampling and fit. It sends normalized-content-to-native-panel matrices.
The client owns a validated live CSS-to-panel mapping and backing scale, not a second placement/fit engine.
Draft editor math is explicitly secondary and replaced by committed output.

This avoids a server round trip for a viewport adjustment that a calibrated rule already covers, without duplicating world geometry on tablets.
Uncovered adjustments invalidate physical readiness immediately.
Keep separate render/mapping ordering from durable wall revision because `applyWallFrame` currently ignores same-revision corrections.
Require independent hand-derived fixtures, production parity fixtures labelled as such, and a ruler/optical seam trial.

## 6. Physical units, rotations and rectangle experiment

Opus supplies useful body/panel/viewport vocabulary and identifies the possible `100lvh` mismatch.
Sol insists that mount rotation, OS orientation, panel size, viewport offset and DPR remain separate, and challenges a speculative sizing fix.
Opus review acknowledges the mismatch is unobserved but still recommends changing it regardless.

Choose measurement first.
P0 compares the actual visible/stable render rectangle, inner dimensions, backing size, mode and screenshots.
Preserve the existing CSS explanation for preventing a bottom strip until evidence supports a change.
Do not measure hidden `#surface` and treat its zero box as a device viewport.
The [viewport draft](https://drafts.csswg.org/css-values-4/#viewport-relative-lengths) allows the mismatch; it does not establish that it occurred here.

Record active size plus four native-edge bezels and derive body size, avoiding redundant contradictory fields.
Use centered body coordinates and an explicit active-corner translation. The roadmap's `[-47,-32]` example resolves the original center/corner ambiguity.
Track 180-degree orientation changes even when size/DPR do not change.
Ruler-based usable-area mapping is the default. Device specifications are optional estimates with provenance.
Physical acceptance initially covers tested fullscreen/standalone modes; tab mode is qualified.

## 7. Source coordinates, fit and seam policy

Opus proposes a virtual-gap parameter and image transforms, but its original rendition example omits rendition-to-source scaling.
Sol identifies that omission and warns that presence/binding must not resize content bounds.
Both want global content fit independent of device placement.

Choose normalized upright source coordinates for every full-image rendition.
Each rendition normalizes its own pixel dimensions before the canonical panel matrix.
Apply canvas backing scale once; CSS video gets no canvas DPR multiplier.
Require corner, interior and inverse tests with asymmetric bezels, fractional backing scale and cardinal rotations.

Keep fixed bounds and physical hidden gaps by default.
A conversion creates a new physical layout from explicit scale and measurements; no legacy unit relabeling or v2 approximation.
Compact and duplicated seams are worthwhile later for regular groups, with sampling previews.
Do not force a unique compact mapping onto irregular rotated arrangements or encode duplication as negative measured bezels.

## 8. Required cohort and slow-device default

Sol requires every marked slot, including offline reservations, so a dead device can block the show until an operator acts.
Opus freezes online devices, holds briefly, then proceeds for an unattended still wall.
These are different product preferences. Neither follows from a protocol fact.

Choose Online cohort with bounded hold for still playlists, and Strict required slots for video starts and actual-stall recovery.
Offer strict stills and explicit partial video as visible alternatives.
Freeze all placed online endpoints for still preparation, including online endpoints that become unsupported/unready.
Report offline reservations and explicit exclusions continuously.
At the deadline, name missing/late endpoints and preserve their missed events in show statistics.

Use Opus's bounded-hold approach with Sol's connection/preparation leases.
Reject Opus's ability to silently count only capable/healthy devices and reject Sol's strict default for every unattended still show.
No barrier is needed for ordinary static-image Show.
Product feedback can change these defaults. Implementation tests must cover offline, hidden, incompatible, slow and replaced participants.

## 9. Runtime session, occurrences and readiness

Opus originally stores runtime playback inside durable scene state and commits each action through wall revision.
Sol separates the process-local session and version and fences preparations to their connection and exact inputs.
Opus review B4 explicitly adopts that separation.

Choose separate durable configuration and runtime playback version.
Prepare freezes occurrence, objects, geometry, cohort and deadline. Ready is leased temporary evidence.
Commit advances version and explicitly transfers the referenced preparation into a future action.
A different supersession invalidates that work. Status ticks do not write SQLite or advance configuration revision.

Fix both proposals' hold ambiguity with committed per-occurrence cuts and re-anchoring after a hold.
Pause at future Te uses position at Te. Reconnect joins the current snapshot rather than replaying starts.
After commit, failure requires recovery and a degraded interval, not an alleged atomic rollback.
Restart restores timed content paused/preparing, resolving Opus's continuation preference in favor of Sol's safer default.
Use the existing image-attempt fencing and socket ownership as source patterns, then extend model/race tests.

## 10. The half-RTT disagreement

Opus review I3 says half RTT bounds offset at the sample even with asymmetry.
Sol review 4 says it is not a guaranteed future clock-error bound.
The unqualified versions of either statement can mislead.

For consistent four timestamps, causal nonnegative delays and stable equal clock rates, the offset lies between `s2-c3` and `s1-c0`.
The midpoint's error is at most half that sample's RTT.
Application queueing inside the causal paths is delay; bounded timestamp/coarsening errors and rate mismatch expand the interval.
A future estimate needs drift/age allowances and any difference between the raw and applied estimator.
An unrelated half-median RTT does not prove an error bound for a median or slewed estimate.

Choose a simple fresh low-delay sample initially, plus sample age and estimated uncertainty.
Reject inconsistent samples. Expire confidence on sleep, lineage change or unsafe jumps.
Defer rate fitting and slewing until evidence warrants them.
The [NTP timestamp relations](https://www.rfc-editor.org/rfc/rfc5905.html#section-8) support the exchange; the stated causal bound is the final author's explicit mathematical derivation.
Clock offset uncertainty is never labelled display skew. Verify estimator truth with injected clocks, then display behavior optically.

## 11. Suspend, scheduling clocks and signed compensation

Opus verifies Linux suspend behavior and recommends BOOTTIME-minus-MONOTONIC detection.
Sol requires clock/session epoch invalidation and explicit timer-domain conversion.
Both reject reusing persisted monotonic times, but their original restart policies differ.

Choose generation plus clock epoch, suspend detection through the documented Linux clock difference, and fresh paused/preparing runtime state.
Client sleep suspicion expires confidence even if a timestamp remains monotonic.
Actual tablet clock behavior remains a device experiment.
Use relative delays or explicit event-loop conversion and recheck deadlines. Do not pass server milliseconds directly to loop.call_at.

Choose positive `presentLeadMs` to mean dispatch earlier, default zero and optically calibrated relative to the cohort.
Keep it separate from network lead and clock offset. The roadmap fixes the sign with a numerical example.
Video applies compensation once. Callback diagnostics must state whether it was applied.
Sources are [Python clock constants](https://docs.python.org/3.13/library/time.html#time.CLOCK_BOOTTIME), [HR-Time](https://www.w3.org/TR/hr-time-3/) and Opus activity's runtime introspection.

## 12. Upload admission

Sol's original reuse of the Origin fence fails to address its unset state.
Opus's matching-Origin-or-loopback rule can treat an untrusted proxied request as local, and Origin itself is forgeable by a nonbrowser client.
The parent observed a directly reachable hotspot backend; GET success cannot reveal whether its Origin guard was configured.

Choose disabled-by-default uploads with explicit authenticated operator ingress.
Require a configured valid Origin and a private proxy-to-backend operator credential injected only after authentication.
Keep the backend loopback-only and strip/overwrite that header at ingress.
A separate direct-loopback development mode disables forwarded-header interpretation and must not share a public proxy listener.
Neither an arbitrary Origin nor a loopback upstream peer authenticates the requester.

This is stronger than Opus review B5's final admission expression and more explicit than Sol's original.
It does not expand R1 into tablet pairing. Published assets retain the declared trusted-LAN read scope.
Test real two-origin ingress, missing Origin, spoofed forwarding/credential headers, disabled guard, direct LAN and unauthenticated operator requests.
Evidence is `_origin_denial` in [main.py](../../../main.py), the actual [Caddy reference](../../../deploy/hotspot.Caddyfile), and [Caddy header replacement](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#headers).

## 13. Media identity, publication and source limits

Opus offers subprocess normalization/renditions but originally publishes original-byte hashes and retains publicly reachable source objects.
Sol requires hashing normalized bytes and publish-before-ready crash consistency, but copies served limits into source admission.
Both reviews concede those weaknesses.

Choose stripped normalized master/render-object hashes, no retained originals by default, and separate exact IDs for every rendition.
Keep R1 v2 display descriptors unchanged and point them at actual normalized display bytes.
Do not equate the source digest with transformed content or expose a private source through a public hash route.

Use staged bounded subprocess work, object publication/fsync before the ready row, and crash reconciliation.
Choose provisional source admission of 32 MiB/32 MP rather than silently retaining 12 MP or enabling 64 MP.
Test representative phone images and resource peaks before release. Keep normalized served objects within existing limits and smaller device renditions.
Larger rejected photos get a clear reason and resizing path.
This accepts Opus's source/rendition distinction without adopting its unmeasured large defaults.

## 14. Backup scope and closure

Opus argues uploads may have no second copy, so all ready uploads should be backed up.
Sol preserves the existing referenced-only contract and calls full-library export a separate explicit product choice.
The repository's [OPERATIONS.md](../../../deploy/OPERATIONS.md) labels referenced-only snapshots approved.

Choose referenced scope as the unchanged default, with a visible omitted-upload count and later deliberate full-library option.
Do not claim unused uploads are archived.
Include master/rendition metadata and closure from the captured database, protect objects against deletion while copying, and version the manifest.
Because a full DB copy can contain unused ready rows, mark omitted entries unavailable in the exported DB before restore verification.
No restored ready row may name absent bytes.

Correct Sol's earlier overly broad backup criticism: `_collect_references` already recursively traverses nested `asset` keys.
New roots, object edges, managed locations and video checks still need work.
Test actual old/new new-target restore, corruption, concurrent publication/deletion and HTTP reads/rendering from the restored app.
Automatic destructive GC waits for reference/pin correctness.

## 15. Socket ordering and commit integrity

Opus's original priority lanes can let control overtake a prerequisite and still lack bounded total queued bytes.
Sol asks for ordered bounded delivery but initially leaves the concrete queue contract open.
Both reviews identify a source-level welcome-order window during replacement, without claiming a reproduced runtime failure.

Choose one FIFO writer per connection, immutable accepted snapshots and welcome reserved before broadcast publication.
Coalesce only replaceable complete snapshots/status, with active plus future playback state retained.
Bound count and bytes, close on overflow/send timeout, and check ownership during cleanup.
Clock stamping occurs at writer send scheduling but never bypasses initialization.

Also correct Opus's detached-swap description: `_commit_wall` invokes the callback twice.
Keep deterministic callbacks and disk-before-memory/notify failure behavior.
Defer an asynchronous DB writer until measured blocking warrants it.
Tests must include actual TCP slow readers, replacement-plus-broadcast, full queues, superseded preparations and the existing disk-failure cases.

## 16. Prerecorded video

Both plans favor native ranged MP4 before HLS/custom MSE/live.
Opus initially offers large profiles, full-download assurance, native loops and broad rate correction.
Sol starts smaller but initially re-prepares the whole group for one device's moderate drift.
Both reviews revise those choices.

Choose a measured H.264/MP4 candidate profile, native transformed composition, muted playback and observed contiguous buffer coverage.
Use a tested framework range implementation through the real ingress. Prove GET/HEAD/206/416/If-Range and bounded multirange behavior.
Local bounded rate correction and seek precede group recovery for isolated drift.
An actual stall under strict mode schedules group rebuffer; any earlier visual divergence remains reported.
Loops and quality changes are authoritative versioned events, initially allowing a scheduled hold/seek gap.

Full download remains a small-file resource experiment. RAM/storage/copies are not established by encoded size, and removing network reads cannot prevent every stall.
Playback permission is checked on each tablet. A controller gesture is not remote activation.
Poster fallback is an explicit exclusion.
The primary [HTML media standard](https://html.spec.whatwg.org/multipage/media.html#media-elements), [frame-callback draft](https://wicg.github.io/video-rvfc/), [WebKit policy](https://webkit.org/blog/6784/new-video-policies-for-ios/), [Chrome policy](https://developer.chrome.com/blog/autoplay/) and [Starlette docs](https://starlette.dev/responses/#fileresponse) support the API limits.
Actual codec, memory, decode, buffer and correction behavior still require the mixed-device probe.

## 17. Segments and live input

Opus suggests delayed HLS as a later live path and a browser-capture fallback.
Sol insists that live source and delay requirements precede transport choice, and flags unspecified capture chunks and epoch mapping.
Both defer WebCodecs and interactive infrastructure from the uploaded-file product.

Choose native file playback first and a later written decision between delayed HLS and interactive WebRTC.
Segment duration, buffer goal, start countdown and source-to-glass delay remain different controls.
Do not enable arbitrary byte-sliced movies as media segments.
HLS dates need an encoder/server epoch mapping and discontinuity rules.
Prove the producer capture/encode/ingest path rather than naming a capture API as a complete solution.
Native Chrome HLS and old-iOS priming remain unverified and outside the critical path.
Sources are [Apple HLS](https://developer.apple.com/streaming/) and the [Screen Capture draft](https://www.w3.org/TR/screen-capture/).

## 18. Real browser isolation and honest impairments

Opus provides coded pixel checks and separate-process coverage but originally treats ports as storage isolation and host epoch arithmetic as exact truth.
Sol provides application/transport/clock fault separation, while needing the same warning about cross-process clock mapping.
Opus review explicitly withdraws the port-isolation claim.

Choose actual client JS on a disposable real TCP server with isolated DB, media and port.
Each endpoint gets independent context/profile, identity and socket; some use separate processes/profile directories.
Assert a same-origin fleet and retain a deliberate same-context collision case.
Windows or ports alone do not establish full isolation. [Playwright contexts](https://playwright.dev/docs/browser-contexts), [cookie port scope](https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5).

Label TCP delivery shaping, application WS faults, media-body stalls, synthetic clock adapters and synthetic decoder/lifecycle probes separately.
Keep unmodified-clock and actual production-codec integration runs.
Desktop WebKit is not iOS Safari; shared GPU/radio/scheduler remains shared. [Playwright browser limits](https://playwright.dev/docs/browsers#media-codecs).
A desktop result is neither physical proof nor a mathematical lower bound on real error.
Real devices remain necessary for independent radio, clock, decoder and display evidence.

## 19. Synchronization and seam gates

Opus proposes 50 ms p95 and 1 mm seams, originally using too few transitions.
Sol proposes 100 ms p95, 250 ms maximum and 2 mm seams, with at least 100 events and explicit recovery windows.
Opus review I10 adopts gate/stretch pairs.

Choose 100 ms p95, 250 ms worst-event cut gate and 2 mm seam gate initially, with 50 ms and 1 mm stretch goals.
Use at least 100 simultaneous optical cuts, maximum-minus-minimum onset for each event, and whole-show miss/completion counts.
Video needs a ten-minute run, full-run and steady-state values, and every startup/recovery window.
A full-run claim requires continuous evidence; sampled recordings name unobserved intervals.

Retain Opus's numbered flashes, same-panel noise-floor experiment and raw capture preservation.
Add explicit rolling-shutter, scanout, exposure, row-position and detection uncertainty.
Camera interval is sampling resolution, not guaranteed accuracy.
No p95 optical claim comes from sequential screenshots or client clock reports.
Thresholds are product choices to revise openly after data, not claims of measured capability.

## 20. Identity, editor scope and deployment sequencing

Opus initially adds cookies and namespaces early; Sol favors stable local identity, deliberate takeover and durable slot rebinding.
Both reviews defer cookies until storage-loss evidence justifies them.
Opus's richer editor and Sol's complete first slice also overrun the minimum arrangement need.

Choose takeover/rebind, a small SVG draft editor, cardinal rotation, screen-space snapping, numeric/tap/keyboard movement and atomic Apply.
Defer cookies, catalogs, marquee/distribute, free-angle handles and import/export.
Keep the single-pointer alternative and rendered accessibility checks. [W3C dragging guidance](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html).
An HTTPS-origin move requires identity/binding migration and calibration review.

Respect the existing README's physical ingress/kiosk prerequisites before declaring deployment or unattended operation complete.
Software upload/layout work may progress with missing hardware clearly recorded.
This changes requested feature ordering, not the truth of the existing deployment status.
No server, browser, network change, install, application-code edit, commit or PR was performed for this synthesis.

## Decision-trail audit

The parent's trail correctly separates independent proposals, reciprocal reviews, baseline evidence and later final-author substitution.
Its shorthand task names are expanded by the orchestration snapshot and the exact Opus IDs in transcript notes.
Acceptance-time model/options records establish requested routing, not continuous provider availability or hardware results.
Later provider-failure rows explain why final authorship changed, rather than creating a nonexistent Opus final result.

One Opus final-summary statement needs correction.
It says the decision log was left unread, but round-1 position 35 contains its Read command and the first three coordination/evidence rows.
The proposal itself also acknowledges reading the log.
Those rows contain no Sol proposal, and the inspected activity explicitly declines to read Sol's draft at position 139.
The evidence supports a bounded independent planning round with shared parent context, not the stronger claim that the trail was never read.
This discrepancy affects provenance precision, not whether Opus supplied a substantial independent proposal and reciprocal critique.

The final-author trail is recorded here without modifying the parent's TSV.
Sol read the four full archived proposals/reviews, parent evidence/trail/orchestration, both Opus activity pages and selected recovered items.
Sol checked relevant live source and primary docs, chose the contracts above, wrote only the three assigned documents and ran artifact/scope checks.
Throughput checkpoint is not applicable to this documentation synthesis. No implementation throughput or performance was measured.

## Deferrals retained for a reason

All-capability v2 remains a viable alternative if a future requirement makes avoiding a device-major migration more valuable than one explicit contract.
All-ready-library backup remains useful as a deliberate export mode, especially if uploads become an archive.
Automatic slideshow restart continuity can return as an explicit wall-clock policy. It must never revive an old monotonic epoch.
Cookies, tile renditions, WAAPI crossfade, photodiodes, delayed HLS, WebRTC and a dedicated media server each have an evidence trigger in the roadmap.
None is required to deliver the first uploaded still.

## Verification of this deliverable

The three output files are checked for existence, valid fence pairing, local-link targets and declared existing/proposed paths.
The roadmap is kept within the requested approximate 400 to 700 lines.
Protected-file SHA-256 comparison and tracked diff checks verify that archived inputs, existing docs, app code and user-owned files were not edited.
Primary reference retrieval was read-only. A failed legacy Starlette host and timed-out FFmpeg formats page were replaced by their current official documentation endpoints.
The final structural pass found a 683-line roadmap, 48 resolving local links across the three documents, three paired fenced blocks and the ordered T1 through T10 tickets.
It also checked all 20 numbered decisions, the Attention section, final newlines and absence of unresolved placeholders.
All 23 transcript item references and both thread links matched the retrieved live task records.
SHA-256 comparison found all 65 protected files unchanged and exactly the three assigned document additions.
`rtk proxy git diff --exit-code` returned 0 at commit `65a4d5081194c457c74a8c6aae629281a30e634b`.
The four archived proposals/reviews and parent observations byte-matched their supplied temporary copies.
Pure Python checks passed for the documented body/quarter-turn examples, normalized rendition mapping, signed dispatch example and 1000 synthetic causal clock samples.
Those arithmetic checks validate document examples, not a production implementation or a measured clock estimator.
These checks validate the documents and scope only. They do not close browser, deployment, optical or independent-final-review gates.
