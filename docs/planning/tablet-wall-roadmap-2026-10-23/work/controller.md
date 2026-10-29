# Controller worker brief (R4 authoring/status + R5 field card)

Work in your own worktree. Read the plan and contract in the main checkout.
Own `frontend/controller/physical.html`, `physical.js`, `physical.css`,
small library changes in `controller.js`/`index.html`/`controller.css`.

Requirements:
1. Playlist authoring from the media library: poster, name, kind, duration;
   add, remove, move up/down. Stills edit dwell; a video shows clip length.
   Keep a raw-id fallback only if it does not confuse the main path.
2. Upload accepts `video/mp4,video/quicktime`; the library normalization
   keeps `kind` and `durationMs`; a video cannot be applied as a still scene.
3. Playback panel: effective policy (strict default with video), Retry, Stop,
   Pause/Resume, current/pending item, required vs ready/missing members,
   activation failures, buffer goal, deadline, remaining dwell, per-tablet
   drift/rate/source/age. Poll `/api/v3/playback` every 1 s while visible
   (no second socket); keep the last status on a failed poll.
4. R5 field card: `GET /diagnostics` summary (quota, used, db schema/size,
   backup age, clients, wake-lock counts), a rebind form
   (`new id`, `replaces id`, optional number), and wake-lock state in the
   roster. Show 403 as "unavailable while uploads are disabled".
5. Accessibility: labels, 44 px targets, focus, no horizontal overflow at
   390 px, announce meaningful state changes only.
6. Bust the physical page cache with the existing pattern; no new page.

Do not edit server, client or docs. Commit. Report SHA and how you checked
the page (URL, viewport, action).

## Binding round-2 corrections

- Policy selector must be able to omit policy. The server resolves omitted as
  strict when any item is video, else online. Show the effective policy from
  status.
- Show committed-future vs displayed, the anchor, and the strict missing
  members (offline/unsupported included).
- Duration labels 1.0 s to 600 s; ingest rejects under 1 s.
