# Decisions

- Safety. Before any app launch, backed up SQLite with its online backup API and copied media to `/tmp/tablet-wall-ai-backup-20261028-010950`. Tests and browser runs use disposable data paths.
- Workflow. Use independent worktrees for authentication, frontend extraction, robustness, and tooling/deployment. Integrate only reviewed commits with passing checks.
- Scope. Complete at least six rounds with phone, tablet, and desktop browser checks in each. A final review is supplementary and cannot replace these rounds.
- Data. Restart persistence restores safe device metadata as offline; online state must come from live sockets.
- Delivery. Use feature branches and logical PRs; no deploy or merge is authorized.
- Extraction. Moved asset HTTP handlers to `tabletwall/routes/assets.py` unchanged. The module depends on existing asset/media services and has no mutable app context or circular main import. This reduces main.py while preserving patchable service dependencies.
- Extraction. Moved read-only registry and registration-help routes into `tabletwall/routes/devices.py`. Mutation and WebSocket ownership remain together in main.py pending larger extractions. Full tests bracket each extraction.
- Type boundaries. Keep strict optional checks enabled. Narrow parsed origins, image asset IDs, display revisions, and viewport strings at their existing validation boundaries; give playback preparation a distinct variable from clock probe evidence.
