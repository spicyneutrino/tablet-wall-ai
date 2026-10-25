# Advisor memo: review-fix plan (GPT-6.1 Sol, 2026-10-25)

Requested through Codex-Work, model `gpt-6.1-sol`, reasoning effort `high`,
service tier `default` (normal, not fast). This is the full returned memo.
It reviewed `docs/planning/tablet-wall-roadmap-2026-10-23/work/review-fixes-plan.md`
against `/tmp/tablet-wall-codex-work-review-2026-10-25/review.md` at
`96a7862`. The operator accepted the Phase 3 choices on 2026-10-25.

> Verdict: **approve with changes**. The plan addresses F1–F4 without requiring
> an architecture change, but needs the following amendments before
> implementation. Reviewed against HEAD `96a7862`; no files changed or servers
> started.
>
> - **F2 cancellation must be explicit.** Specify that the terminal transition
>   advances session version, invalidates pending leases and armed callbacks,
>   and emits one hold transition from both socket-fault and stale-sample cap
>   paths. `_recovery_failure()` currently does not advance version. The
>   client’s generic playback handler currently ignores lineage, so adding
>   lineage fields alone is insufficient. Reject stale terminal frames after
>   Retry or a new session. Capture the transition’s frame before asynchronous
>   fan-out; do not serialize later mutated session state.
>
> - **F3/F4 durable tests need an owner.** C describes disposable checks and
>   says their durable copy belongs in Phase 2D, but D’s list omits Pause and
>   playlist editing. Add them explicitly. Also change “a new browser case
>   must fail at baseline” to require each defect reproduction to fail there.
>   Existing correct behavior, such as final-item recovery, should remain a
>   passing regression case.
>
> The wire shape is sufficient with these qualifications:
>
> - **F1:** Top-level `recovery_id`, present only on recovery prepares,
>   adequately distinguishes recovery. Keep preparation/version/connection
>   matching authoritative for commits; commits need no additional recovery
>   marker. Validate the marker and position before interrupting playback.
>   Reject a present invalid marker rather than treating it as ordinary
>   preparation. Remove the nested `media.recovery_id` compatibility fixture
>   unless a real supported producer requires it. Test both serializers and
>   retain an ordinary `start_media_ms: 0` compatibility case.
> - **F4:** `live: {current, displayed, pending}` plus the session’s
>   `playlist_revision` is adequate. Define nullable entries, asset ID versus
>   descriptor, and still/video duration semantics. Preserve existing
>   top-level occurrence and preparation fields. Migrate every live label,
>   pending fact and dwell calculation, with no fallback through the editable
>   playlist. Resolve names by authoritative asset ID. Increment saved
>   revision only after successful conditional save, and capture it at Start.
>   Test legacy missing revisions and rejected saves.
> - These are additive protocol changes, but terminal-hold semantics differ
>   for cached clients. Require a coordinated client reload or an explicit
>   compatibility gate before claiming the repair operational.
>
> The terminal `playback` blocked/failed frame can preserve the picture and
> Stop. It must clear still timers and pending/armed video work, freeze the
> active element, and retain playback ownership so wall/render updates cannot
> repaint static content. Stop must subsequently restore the latest persisted
> scene. Keep hold idempotent and fan-out isolated through existing writers.
> Preserve strict Retry’s reset to attempt 1 and online Start-again behavior.
> Test delayed callbacks and a failing writer.
>
> The Phase 3 defaults are coherent proposals, but **require explicit operator
> acceptance before coding**. An advisor cannot approve those product choices
> on the user’s behalf.
>
> Automatic reconnect should trigger one group recovery for a returning
> frozen-cohort member during eligible video playback, consume one attempt,
> cancel routine preparation, and require fresh connection evidence. Joining
> an existing recovery must consume no additional attempt or reset its
> deadline. Define coalescing across recovery completion, not merely a
> two-second timer. Exclude paused/blocked/failed/final sessions. Crucially,
> `_commit()` marks the last item final immediately, so this default also
> excludes reconnect during an actively playing last video. Accept that
> consequence explicitly.
>
> Start-time exclusions can remain session-only, named, static, outside
> readiness and synchronized counts, with unchanged bounds and no live
> command. Distinguish original slot requirements, exclusions and effective
> cohort in diagnostics. Resume must retain the frozen selection.
>
> Phase 2 is insufficient until it durably covers:
>
> - Consecutive videos, single-video loop, routine preparation while
>   armed/active, zero-position recovery, and recovery followed by an actual
>   video cut.
> - Strict/online caps through fault and stale-sample paths, cohort freeze, no
>   fourth prepare, late callbacks, Retry/Start-again and Stop.
> - Pause summary, stable dwell, healthy polling, Resume and Stop.
> - Draft edit/reorder/save during playback and recovery, controller reload,
>   and a subsequent Start using the saved revision.
>
> All require real visibility/progression assertions and unexpected
> page-error failures.
>
> Keep A→B→C as integration order, but freeze contracts before parallel work
> and release only the combined repair. Serialize A/E edits to `PROTOCOL.md`;
> assign `evidence.py` solely to E and client comment fixes to B. Rebase
> exclusions onto reconnect before implementing shared server paths.
