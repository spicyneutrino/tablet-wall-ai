# Audit backlog

Severity order is broken, confusing, missing, polish. Check an item only with recorded verification.

## Round 1, baseline and architecture

- [x] B01 [missing] Opt-in environment token authentication for HTTP and WebSockets, with browser access and security tests.
- [x] B02 [broken] Static mounts fail outside the repository working directory.
- [x] B03 [confusing] Curated images are repeatedly decoded on inventory and lookup. Add a safe measured cache.
- [x] B04 [missing] Device metadata and colors disappear on restart. Persist safe values and restore as offline.
- [x] B05 [broken] Concurrent workers can diverge. Enforce single ownership or warn effectively.
- [x] B06 [missing] Audit rendered operator UX at phone, tablet, desktop with console and network capture.
- [x] B07 [missing] Rank at least ten operator improvements and implement the highest value feasible additions.
- [x] B08 [missing] Measure Python coverage and test weak failure, security, restart, and reconnect paths.
- [x] B09 [confusing] Extract cohesive routes from main.py, one extraction per green commit.
- [x] B10 [confusing] Extract modules from both controller scripts, one extraction per green commit.
- [x] B11 [missing] Add ruff and typechecker development dependencies and passing make targets.
- [x] B12 [confusing] Service template placeholders need validation and accurate documentation.
- [x] B13 [confusing] Review all 59 untracked files; commit project documents and ignore local artifacts.

## Round 2, connected tablet and failure boundaries

- [x] B14 [confusing] Existing annotated Python paths fail the new type gate. Narrow optional values and separate clock evidence from playback preparation variables.
- [x] B15 [confusing] Historical deployment and persistence docs describe pre-media backups and an empty roster after restart. Update them with verified behavior.

## Round 3, reconnect and browser authentication

- [x] B16 [broken] Chromium login with no-referrer emits Origin:null and the secure form correctly rejects it. Set same-origin referrer policy and verify rendered sign-in plus live WebSockets.

## Round 4, security and transaction review

- [x] B17 [broken] Successful authenticated asset responses must forbid shared caching of protected bytes.
- [x] B18 [broken] Roster persistence failure during delete/rebind must not leave wall and roster partially committed.

- [x] B19 [confusing] Heartbeat contact times need bounded durable checkpoints so restored offline ages and number leases are not hours stale.
- [x] B20 [broken] A present JSON null roster must fail validation rather than silently become an empty roster.

## Round 5, authenticated operator flows and health freshness

- [x] B21 [confusing] Physical console swallows roster refresh failure and can keep presenting stale online counts. Show last-known state and a retry action, with a visible health overview.

## Round 6, keyboard, rejected writes, and module failure paths

- [x] B22 [broken] Extracted physical playback references ApiError outside its scope on failure. Pass the constructor explicitly and test 412 retry plus 409 error handling.

## Round 9, integration and repeatable tooling

- [x] B23 [broken] Inventory benchmark endpoint discovery stopped working after APIRouter extraction. Bind the real extracted endpoint and isolate deployment environment before repeating measurement.

## Operator feature ranking

| Rank | Improvement | Value | Effort | Decision |
| --- | --- | --- | --- | --- |
| 1 | Device health overview | High | Low | Implemented above-stage health summary with stale/retry feedback |
| 2 | Downloadable diagnostics | High | Low | Verified existing JSON download in field/controller browser suites |
| 3 | Layout undo | High | Medium | Verified existing physical undo/redo and extracted logical history tests |
| 4 | Bulk device actions | High | Medium | Verified existing all-device colour actions and empty-roster behavior |
| 5 | One-flow backup and restore | High | Medium | Verified 41-check rendered combined restore drill |
| 6 | Clear reconnect status and recovery | High | Low | Verified reconnect, tabs, empty-state guidance; fixed stale health feedback |
| 7 | Keyboard tab navigation | High | Low | Verified reconnect, tabs, empty-state guidance; fixed stale health feedback |
| 8 | Empty state next actions | Medium | Low | Verified reconnect, tabs, empty-state guidance; fixed stale health feedback |
| 9 | Search/filter device roster | Medium | Medium | Polish follow-up unless audit shows operational blocker |
| 10 | Saved layout comparison preview | Medium | High | Polish follow-up |
| 11 | Event history timeline | Medium | High | Polish follow-up |
| 12 | Scheduled scenes | Medium | High | Polish follow-up |

## Exit gates

- [x] At least six completed audit rounds.
- [x] Last two rounds find no new broken, confusing, or missing issues.
- [x] No unchecked issues above polish.
- [x] make test, make lint, make typecheck pass.
- [x] All intended files committed; remaining files intentionally ignored.

## Optional polish

- [ ] P01 [polish] Add roster text search for larger installations; existing selection and counts work at tested fleet sizes.
- [ ] P02 [polish] Add saved-layout comparison previews after operator demand; current named save/recall and undo cover recovery.
- [ ] P03 [polish] Add an event-history timeline after defining retention; diagnostics already exports current evidence.
- [ ] P04 [polish] Add scheduled scenes after defining local clock and recovery expectations; manual playback is available.
