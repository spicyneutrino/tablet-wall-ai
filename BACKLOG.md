# Audit backlog

Severity order is broken, confusing, missing, polish. Check an item only with recorded verification.

## Round 1, baseline and architecture

- [ ] B01 [missing] Opt-in environment token authentication for HTTP and WebSockets, with browser access and security tests.
- [ ] B02 [broken] Static mounts fail outside the repository working directory.
- [ ] B03 [confusing] Curated images are repeatedly decoded on inventory and lookup. Add a safe measured cache.
- [ ] B04 [missing] Device metadata and colors disappear on restart. Persist safe values and restore as offline.
- [ ] B05 [broken] Concurrent workers can diverge. Enforce single ownership or warn effectively.
- [ ] B06 [missing] Audit rendered operator UX at phone, tablet, desktop with console and network capture.
- [ ] B07 [missing] Rank at least ten operator improvements and implement the highest value feasible additions.
- [ ] B08 [missing] Measure Python coverage and test weak failure, security, restart, and reconnect paths.
- [ ] B09 [confusing] Extract cohesive routes from main.py, one extraction per green commit.
- [ ] B10 [confusing] Extract modules from both controller scripts, one extraction per green commit.
- [ ] B11 [missing] Add ruff and typechecker development dependencies and passing make targets.
- [ ] B12 [confusing] Service template placeholders need validation and accurate documentation.
- [ ] B13 [confusing] Review all 59 untracked files; commit project documents and ignore local artifacts.

## Operator feature ranking

| Rank | Improvement | Value | Effort | Decision |
| --- | --- | --- | --- | --- |
| 1 | Device health overview | High | Low | Implement based on current roster/diagnostics |
| 2 | Downloadable diagnostics | High | Low | Implement |
| 3 | Layout undo | High | Medium | Audit current editor and implement safe local undo if absent |
| 4 | Bulk device actions | High | Medium | Audit existing all-device actions before adding |
| 5 | One-flow backup and restore | High | Medium | Verify existing deploy/backup.py database/media flow |
| 6 | Clear reconnect status and recovery | High | Low | Audit and fix observed gaps |
| 7 | Keyboard tab navigation | High | Low | Audit and fix observed gaps |
| 8 | Empty state next actions | Medium | Low | Audit and fix observed gaps |
| 9 | Search/filter device roster | Medium | Medium | Polish follow-up unless audit shows operational blocker |
| 10 | Saved layout comparison preview | Medium | High | Polish follow-up |
| 11 | Event history timeline | Medium | High | Polish follow-up |
| 12 | Scheduled scenes | Medium | High | Polish follow-up |

## Exit gates

- [ ] At least six completed audit rounds.
- [ ] Last two rounds find no new broken, confusing, or missing issues.
- [ ] No unchecked issues above polish.
- [ ] make test, make lint, make typecheck pass.
- [ ] All intended files committed; remaining files intentionally ignored.
