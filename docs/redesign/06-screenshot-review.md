# X5 screenshot review

App baselines from `e2e/parity/X5.spec.ts`; mockups from `docs/redesign/mockups/final.html`.
Sheets: `docs/redesign/shots/approval/app-<width>-<theme>.png` and `mock-<width>-<theme>.png`.
Each app sheet was opened next to its matching mock sheet. Rows describe the light pair;
the dark pair shows the same differences with the dark palette. Times, ages and QR codes
are masked in the app baselines, so those areas are solid blocks rather than legible text.

| State | Width | Result |
| --- | --- | --- |
| main | 390 | Preview paints the applied flyer on all four tiles; the mock paints the calibration grid and shows an enabled “Show on wall” CTA. App board rows say “Model not set”; the mock names each model. |
| selected | 390 | Preview paints the flyer on all four tiles instead of the mock’s placeholder gradients. App detail adds a wake-lock-denied advisory and “Screen awake Denied by browser”; the mock shows “iPad Air 2” and “From the model, not measured” with no advisory. |
| arrange | 390 | Preview keeps the flyer and shows numeric X/Y/Width/Height placement fields; the mock shows placeholder gradients, a staggered wall and saved-layout tiles (“2 x 2 grid”, “Your edit”). App header chip reads “4 of 4”, the mock “4 of 4 showing”. |
| measure-model | 390 | App blanks the single measured tablet with dimension lines and selects “Other, enter sizes” in the model field; the mock shows four placeholder tablets and “iPad Air 2 (detected)”. |
| measure-size | 390 | App measures a single blank tablet at 220 × 123.75 mm with 0 mm bezels; the mock shows four tablets at 197.1 × 147.8 mm with 21.5 mm side and 10.9 mm top/bottom bezels. |
| measure-ruler | 390 | App shows one blank tablet with A 260 px / B 200 px and empty ruler inputs; the mock shows four tablets with A 52.4 / B 52.3 filled and a “Ruler gives 197.4 × 148.0 mm” note. |
| measure-review | 390 | App review reads “220 × 123.75 mm (was 200 × 112.5)”, bezels 0 mm, checked by “Supplied measurements”; the mock reads “197.4 × 148.0 mm (was 197.1 × 147.8)”, bezels 21.5/10.9 mm, “Ruler, ±0.5 mm”. |
| firstrun | 390 | App masks the join address and QR as pink blocks; the mock shows an unmasked QR and 192.168.0.2:8080. Source strips differ: app has Calibration grid/Black/Library…/Upload…, mock has Cohort 3 flyer/Calibration grid/Black/Upload…. |
| loading | 390 | Layout and skeletons match; the app source strip shows already-uploaded thumbnails where the mock shows empty skeleton tiles. |
| offline | 390 | Preview paints the flyer with tablet 4 hatched “Offline” instead of the mock’s placeholder gradients. Advisory copy differs (“Wake the tablet and it reconnects by itself” vs “Offline for 12 minutes…”). |
| unreachable | 390 | App preview shows the single physical tablet’s clipped flyer and masks last-report times in the board; the mock shows the full four-tile wall and “Unknown since 10:52”. |
| uncertain | 390 | App preview shows a red/blue two-colour image on two tiles; the mock shows the calibration grid on four tiles. Banner copy differs (“The last change was not confirmed” vs “No tablets got this in time”). |
| conflict | 390 | App shows a two-tile wall with “Your edit 1 tablet moved, 1 reset”; the mock shows a four-tile staggered wall with “Your edit 3 moved, 1 burning” and different conflict totals. |
| server | 390 | App Health facts show “1 of 4 online”, 2 assets/2 objects and a masked “Checked at” time; the mock shows “4 of 4 online”, one verified image and unmasked timings. Preview is one clipped tablet in the app, four placeholder tiles in the mock. |
| data | 390 | App shows “Last manifest not recorded / Restore rehearsal not recorded” and only a “Clear wall…” button; the mock shows “Last snapshot Today 10:42”, contents/rotation rows, “Download backup”, “How to restore” and a “Clear every position?” confirmation. |
| playback | 390 | App playlist has 1 item, “3 s loop” and Loop off; the mock has 3 items, “11 s loop” and Loop on, with ten-, five- and three-second dwell rows. |
| library | 390 | App Library header offers “Search images” and “Refresh images” with two image tiles; the mock has “Back”/“Library” with an “Uploading 1 of 2” progress bar and queued-file rows. |
| main | 820 | Preview paints the applied flyer on all four tiles; the mock paints the calibration grid and shows an enabled “Show on wall” CTA. App board rows say “Model not set”; the mock names each model. |
| selected | 820 | Preview paints the flyer on all four tiles instead of the mock’s placeholder gradients. App detail adds a wake-lock-denied advisory and “Screen awake Denied by browser”; the mock shows “iPad Air 2” and “From the model, not measured” with no advisory. |
| arrange | 820 | Preview keeps the flyer and shows numeric X/Y/Width/Height placement fields; the mock shows placeholder gradients, a staggered wall and saved-layout tiles (“2 x 2 grid”, “Your edit”). App header chip reads “4 of 4”, the mock “4 of 4 showing”. |
| measure-model | 820 | App blanks the single measured tablet with dimension lines and selects “Other, enter sizes” in the model field; the mock shows four placeholder tablets and “iPad Air 2 (detected)”. |
| measure-size | 820 | App measures a single blank tablet at 220 × 123.75 mm with 0 mm bezels; the mock shows four tablets at 197.1 × 147.8 mm with 21.5 mm side and 10.9 mm top/bottom bezels. |
| measure-ruler | 820 | App shows one blank tablet with A 260 px / B 200 px and empty ruler inputs; the mock shows four tablets with A 52.4 / B 52.3 filled and a “Ruler gives 197.4 × 148.0 mm” note. |
| measure-review | 820 | App review reads “220 × 123.75 mm (was 200 × 112.5)”, bezels 0 mm, checked by “Supplied measurements”; the mock reads “197.4 × 148.0 mm (was 197.1 × 147.8)”, bezels 21.5/10.9 mm, “Ruler, ±0.5 mm”. |
| firstrun | 820 | App masks the join address and QR as pink blocks; the mock shows an unmasked QR and 192.168.0.2:8080. Source strips differ: app has Calibration grid/Black/Library…/Upload…, mock has Cohort 3 flyer/Calibration grid/Black/Upload…. |
| loading | 820 | Layout and skeletons match; the app source strip shows already-uploaded thumbnails where the mock shows empty skeleton tiles. |
| offline | 820 | Preview paints the flyer with tablet 4 hatched “Offline” instead of the mock’s placeholder gradients. Advisory copy differs (“Wake the tablet and it reconnects by itself” vs “Offline for 12 minutes…”). |
| unreachable | 820 | App preview shows the single physical tablet’s clipped flyer and masks last-report times in the board; the mock shows the full four-tile wall and “Unknown since 10:52”. |
| uncertain | 820 | App preview shows a red/blue two-colour image on two tiles; the mock shows the calibration grid on four tiles. Banner copy differs (“The last change was not confirmed” vs “No tablets got this in time”). |
| conflict | 820 | App shows a two-tile wall with “Your edit 1 tablet moved, 1 reset”; the mock shows a four-tile staggered wall with “Your edit 3 moved, 1 burning” and different conflict totals. |
| server | 820 | App Health facts show “1 of 4 online”, 2 assets/2 objects and a masked “Checked at” time; the mock shows “4 of 4 online”, one verified image and unmasked timings. Preview is one clipped tablet in the app, four placeholder tiles in the mock. |
| data | 820 | App shows “Last manifest not recorded / Restore rehearsal not recorded” and only a “Clear wall…” button; the mock shows “Last snapshot Today 10:42”, contents/rotation rows, “Download backup”, “How to restore” and a “Clear every position?” confirmation. |
| playback | 820 | App playlist has 1 item, “3 s loop” and Loop off; the mock has 3 items, “11 s loop” and Loop on, with ten-, five- and three-second dwell rows. |
| library | 820 | App Library header offers “Search images” and “Refresh images” with two image tiles; the mock has “Back”/“Library” with an “Uploading 1 of 2” progress bar and queued-file rows. |
| main | 1440 | Preview paints the applied flyer on all four tiles; the mock paints the calibration grid and shows an enabled “Show on wall” CTA. App board rows say “Model not set”; the mock names each model. |
| selected | 1440 | Preview paints the flyer on all four tiles instead of the mock’s placeholder gradients. App detail adds a wake-lock-denied advisory and “Screen awake Denied by browser”; the mock shows “iPad Air 2” and “From the model, not measured” with no advisory. |
| arrange | 1440 | Preview keeps the flyer and shows numeric X/Y/Width/Height placement fields; the mock shows placeholder gradients, a staggered wall and saved-layout tiles (“2 x 2 grid”, “Your edit”). App header chip reads “4 of 4”, the mock “4 of 4 showing”. |
| measure-model | 1440 | App blanks the single measured tablet with dimension lines and selects “Other, enter sizes” in the model field; the mock shows four placeholder tablets and “iPad Air 2 (detected)”. |
| measure-size | 1440 | App measures a single blank tablet at 220 × 123.75 mm with 0 mm bezels; the mock shows four tablets at 197.1 × 147.8 mm with 21.5 mm side and 10.9 mm top/bottom bezels. |
| measure-ruler | 1440 | App shows one blank tablet with A 260 px / B 200 px and empty ruler inputs; the mock shows four tablets with A 52.4 / B 52.3 filled and a “Ruler gives 197.4 × 148.0 mm” note. |
| measure-review | 1440 | App review reads “220 × 123.75 mm (was 200 × 112.5)”, bezels 0 mm, checked by “Supplied measurements”; the mock reads “197.4 × 148.0 mm (was 197.1 × 147.8)”, bezels 21.5/10.9 mm, “Ruler, ±0.5 mm”. |
| firstrun | 1440 | App masks the join address and QR as pink blocks; the mock shows an unmasked QR and 192.168.0.2:8080. Source strips differ: app has Calibration grid/Black/Library…/Upload…, mock has Cohort 3 flyer/Calibration grid/Black/Upload…. |
| loading | 1440 | Layout and skeletons match; the app source strip shows already-uploaded thumbnails where the mock shows empty skeleton tiles. |
| offline | 1440 | Preview paints the flyer with tablet 4 hatched “Offline” instead of the mock’s placeholder gradients. Advisory copy differs (“Wake the tablet and it reconnects by itself” vs “Offline for 12 minutes…”). |
| unreachable | 1440 | App preview shows the single physical tablet’s clipped flyer and masks last-report times in the board; the mock shows the full four-tile wall and “Unknown since 10:52”. |
| uncertain | 1440 | App preview shows a red/blue two-colour image on two tiles; the mock shows the calibration grid on four tiles. Banner copy differs (“The last change was not confirmed” vs “No tablets got this in time”). |
| conflict | 1440 | App shows a two-tile wall with “Your edit 1 tablet moved, 1 reset”; the mock shows a four-tile staggered wall with “Your edit 3 moved, 1 burning” and different conflict totals. |
| server | 1440 | App Health facts show “1 of 4 online”, 2 assets/2 objects and a masked “Checked at” time; the mock shows “4 of 4 online”, one verified image and unmasked timings. Preview is one clipped tablet in the app, four placeholder tiles in the mock. |
| data | 1440 | App shows “Last manifest not recorded / Restore rehearsal not recorded” and only a “Clear wall…” button; the mock shows “Last snapshot Today 10:42”, contents/rotation rows, “Download backup”, “How to restore” and a “Clear every position?” confirmation. |
| playback | 1440 | App playlist has 1 item, “3 s loop” and Loop off; the mock has 3 items, “11 s loop” and Loop on, with ten-, five- and three-second dwell rows. |
| library | 1440 | App Library header offers “Search images” and “Refresh images” with two image tiles; the mock has “Back”/“Library” with an “Uploading 1 of 2” progress bar and queued-file rows. |
