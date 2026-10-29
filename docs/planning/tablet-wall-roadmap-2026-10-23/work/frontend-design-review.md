# Frontend design review (DeepSeek, 2026-10-24)

Source: DeepSeek independent review of the physical editor and tablet video
experience, with Playwright at 1440x1000, 1080x900, 1024x900, 390x844 and
axe 4.12.1, against a disposable server.

## Top 5

1. Rebalance the shell around selection and transport. The aside leads with
   Playback then Selected tablet; Playback is about 700 px idle and 1322 px
   failed, pushing the inspector below the fold in the sticky pane. Under
   1080 px the whole aside falls after Field check; at 390 px the page is
   7957 px. Make Playback a compact strip when idle (state, saved count,
   effective policy, Start), expand it only during a session. Put Selected
   tablet and Profile/calibration under Tablets. Lower the two-column
   breakpoint to about 1000 px and keep a sticky transport bar below it.
   Remove idle Preparation, Tablets, and duplicate facts.
2. Start must use the saved playlist and preflight it. Start is enabled with
   no saved playlist or physical layout and returns 409; a dirty playlist is
   worse, because the panel's count and policy describe the draft while Start
   plays the saved list. Add a preflight line (saved count, first item,
   required/online tablets, policy effect), disable Start with actionable
   text when no saved playlist or physical layout, and label the action
   "Save and start" when the draft is dirty. Remove the persistent "Start
   accepted" box.
3. Make display numbers and liveness the roster spine. The physical page
   shows short UUIDs only; add #N to stage labels, Tablets rows, Selected
   tablet, and Playback members. Add an online dot and count. Warn when a
   tablet reports wake_lock released/denied/insecure; unsupported is normal
   on plain HTTP. Add a five-second client HUD on welcome/reconnect/tap/
   rebind with #N, short id, Connected/Not placed, then fade.
4. Turn rebind into a guided, confirmed operation. Replace raw UUID fields
   with roster pickers (new unplaced registration, old tablet with full id,
   #N, online state), default the number to "keep #N", and confirm the
   transfer, offline requirement, and saved-layout consequence. Add copy
   full id in Selected tablet and a confirmation on the tablet.
5. Give tablet video a real failure interface. Style Enable display as a
   56 px high-contrast pill with "Tap to allow video, tablet #N", focus and
   announce it. Add a "Tap tablet #1" readiness row and a transient "Video
   unavailable, #N" local state. Promote Resume when paused, separate Stop,
   show Retry only when blocked. Move session/version/raw ms/prepare times/
   buffer goal under Details; keep current, next, time left and readiness in
   view. Remove Playback Refresh (polling already) and the idle stopped/
   preparation/no-preparation/footer duplicates.

## Also fix

- Stage head metadata (revision/session/etag) competes with the title; demote
  to one quiet line. Drop one of the three repeated tablet identities.
  Number playlist rows and mark the current item. Rename Playback "Tablets"
  to "Readiness".
- Playback copy: replace protocol wording, fix final-state text ("Stop ends
  playback"), make failed copy match actual Start behavior.
- Field check: "ready" means fetch success, not health. Rename "loaded", add
  warnings for backup age, non-held wake locks, stale diagnostics. Show read
  time and refresh on focus. Hide Verify when forbidden. Explain unsupported
  wake lock once.
- Accessibility: axe contrast failures on "Selected" and "Video" chips
  (4.3:1). Scope the global arrow-key handler to the stage/nudge block so it
  does not move selection while scrolling. Make the mobile Wall control link
  44 px. Keep one transport live region. Rename the aside label.
- States: stale chip on poll failure; "No wall tablets are online" instead of
  "no eligible physical endpoints"; playlist remove undo; empty Tablets note
  links to /client/ with the LAN caveat.

## Keep

Stage as focal object; selection ring, 44 px hits, 3 px drag threshold,
keyboard nudge, Escape cancel, undo/redo; calibration state; inline errors;
skip link, focus ring, 44 px controls.
