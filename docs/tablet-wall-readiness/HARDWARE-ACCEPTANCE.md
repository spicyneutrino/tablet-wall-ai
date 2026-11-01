# Real-tablet image-wall acceptance

Status: **not run for the consolidated implementation**. Existing user-reported
logical 2×2 and 1×4 demonstrations do not establish measured-layout seam accuracy,
OS recovery or sustained operation. This is the canonical TWR-17 checklist.
[ROADMAP §13.6](ROADMAP.md#136-hardware-validation-plan-twr-17) links here.

## Prepare a separate trial

Use the supplied iPad Air 2 and Pixel C profiles with provisional 3 mm model
uncertainty. Confirm actual models; a matching screen signature is a suggestion.
A new ruler measurement is optional. Without one, label the trial approximate.
Do not infer a 2 mm seam result from generated coordinates or photographs alone.

1. Run the integration branch `work/tablet-wall-readiness`, rather than `main`.
   Record `git rev-parse HEAD`, `git branch --show-current` and
   `git status --porcelain`. Application `29148ec` passed software acceptance;
   later commits may contain preparation documentation. Keep the exact trial SHA.
2. Save the existing arrangement under a name. Make and verify a snapshot using
   [runbook §9](../../deploy/IMAGE-WALL-RUNBOOK.md#9-back-up). Record the snapshot
   directory, database SHA-256, revision and content scope printed by `verify`.
   Stop only the installation being backed up as its procedure requires. Do not
   point a trial at the working database.
3. Restore that snapshot to **new paths** using
   [runbook §10](../../deploy/IMAGE-WALL-RUNBOOK.md#10-restore-to-new-targets).
   Referenced images are restored; unused library files are not. Copy any extra
   chosen poster into the trial assets directory before startup if needed.
4. Start the restored copy with explicit data and configuration paths. Choose
   unused ports. This example uses 18000 for the operator and 18080 for tablets.
   The manual command changes the trial's runtime firewall opening; run it only
   when the operator is ready for the hardware trial. It is not a software QA command.

```sh
snapshot=/absolute/backups/verified-wall-snapshot
trial_root=$(mktemp -d /var/tmp/tablet-wall-trial.XXXXXX)
mkdir "$trial_root/data"
uv run python deploy/backup.py verify --src "$snapshot"
uv run python deploy/backup.py restore --src "$snapshot" \
  --db "$trial_root/data/wall.db" --assets "$trial_root/data/assets" \
  --media "$trial_root/data/media"
uv run python -m deploy.hotspot --data-dir "$trial_root/data" \
  --config "$trial_root/hotspot.json" --backend-port 18000 --tablet-port 18080
```

Stop if verify or restore fails; do not continue to the launcher.
The new directory is under `/var/tmp` so the host-reboot observation does not
rely on `/tmp` surviving a reboot. Retain the exact path outside the shell.
The launcher requires an existing active hotspot and its documented prerequisites.
Do not change the working launcher's saved configuration. Copy the exact printed
origins, SSID, interface and data paths into the record. Different ports create a
new browser origin and therefore new tablet identities. Use those trial identities;
do not clear or rebind the working installation. Existing reservations from the
snapshot remain visible until intentionally replaced in the trial copy.

For H11 after reboot, ensure the hotspot is active, recording any action
needed to re-enable it. Set `trial_root` to the **same recorded directory** and
run only the launcher command again. Do not run `mktemp`, restore the old
snapshot again, or recreate the trial data. Those actions would test a different
installation or discard the arrangements changed during the trial.

Open the printed operator URL ending in `/controller/physical.html`. On each
trial tablet, open the printed `/client/` address. Confirm the actual model,
identify/name each tablet and copy its full persistent ID from its card. Capture
OS/browser versions, orientation, launch mode, viewport/zoom, pinned profile and
calibration revisions, and OS power settings. Arrange the logical 1×4 baseline
in the trial copy, then save it before applying measured layouts.

Use **Wall → Colours and continuity checks → Wall-sized grid** after committing
a measured layout. The image has 50 mm intervals and labelled corners. Also use
a marked-border image and a real poster. Declare seam/scale targets and measurement
uncertainty before measuring. The 2 mm seam target is separate from the provisional
3 mm model uncertainty; passing one must not be assumed from the other.

## Canonical checklist

Every row starts **Not run**. Record pass, fail or not run with a reason. A failure
remains in the record after a successful retry; record the retry separately.

| ID | Check | Required observation |
| --- | --- | --- |
| H1 | Logical 1×4 baseline | Known image displays as before; record the trial-origin identities and saved arrangement. |
| H2 | Measured 2×2 | Correct quadrants, no swapped/upside-down panel, current image within 10 s of Apply. |
| H3 | Measured 1×4 | Correct row order and physical mount direction. |
| H4 | Seams | Measure displacement at every horizontal/vertical edge, state measurement uncertainty and compare with the declared 2 mm target. Preserve failures or inconclusive results. |
| H5 | Scale | Measure a 50 mm interval on each model and record deviation and uncertainty against the declared target. |
| H6 | Rotation, zoom and fullscreen | Correct re-render or visible mapping fence; no silent wrong plan. Record browser launch-mode assumptions. |
| H7 | Image failure and Retry | The intended tablet fails visibly, the controller names it, Retry recovers, and stale reports do not confirm the next image. |
| H8 | Wi-Fi loss and restoration | Twenty real trials. Independently time connectivity restoration to the correct current image, within 10 s per trial. Record taps/reloads and all failures. Transport reconnection alone is insufficient. |
| H9 | Sleep and wake | Record sleep settings and whether tap, unlock, reload or reopen is required; record time to correct image. |
| H10 | Backend restart | All tablets resync without manual reload, or retain the failure and every intervention. |
| H11 | Host reboot | For profile A, reboot then manually relaunch the same explicit trial command and record the intervention; content/layout must return. Automatic service recovery is not claimed. Test an installed service only under a separate documented profile. |
| H12 | Cross-kind switch and recall | Logical and measured arrangements remain recoverable, including the named safety copy. |
| H13 | Replacement and saved recall | In the trial copy, replace a lost identity; saved 2×2 and 1×4 use the intended replacement and do not resurrect the old ID. |
| H14 | Remove and Forget | Slots, offline roster and retained history behave as documented; record saved reservations. |
| H15 | Restore to new paths | Referenced image bytes, arrangements, labels and device identities survive; record that unused library content is excluded. |
| H16 | Second-peer ingress | From another hotspot peer, operator routes on the tablet listener return 403 and the direct backend port is unreachable. Record exact URLs and results. |
| H17 | Powered two-hour still | Record start/end, actual duration, power/thermal conditions and every interruption. No unexplained stall, stale image, lost member or restart. |
| H18 | Kiosk and power controls | Actual OS settings recorded, screen stays usable under the observed conditions, and the exit path is known. |
| HW-JOIN | Join and Identify | Every real tablet appears once; Identify flashes its intended number/name; reload retains the trial identity. |
| HW-FIT | Fit and Fill | Marked source borders/corners and observed bars, crop, bezels and gaps match the preview across the wall. |
| HW-AUTH | Authenticated deployment only | Record a real tablet sign-in/expiry/recovery and denied operator ingress. For profile A mark not run with “Unauthenticated HTTP profile”; do not imply auth passed. |

The previous checklist's **Model and viewport** check is retained in preparation,
the device entries and H6. Its **Mixed devices** check is retained in H4 and H5:
include each actual iPad/Google boundary in seam measurements and both models in
scale measurements. State the scope explicitly if a trial lacks mixed models.

## Record connectivity separately from image recovery

The existing [network trial harness](../../deploy/network_trials.py) observes an
outage before measuring origin reachability and the named tablet's roster entry.
Run it on the operator laptop against the loopback operator origin, not the
restricted tablet listener. Its twenty-trial output can support H8 transport
evidence, but it does not inspect the current image or a panel.

```sh
uv run python deploy/network_trials.py --artifacts /absolute/new-network-evidence \
  --base-url http://127.0.0.1:18000 --tablet-device-id ACTUAL_TRIAL_UUID \
  --restored-stdin --case "declared-case-label" \
  --ap "actual AP and firmware" --wan "actual WAN state"
```

After the harness observes each outage, enter an independently observed UTC
restoration marker as `ISO-8601 | case | note`. See
[network timing procedure](../validation/SOAK-AND-NETWORK.md) for marker semantics.
Alongside each transport result, record restoration-to-correct-image time and its
observation method. A screen recording with a visible independent timer is one
option. Include clock/timing uncertainty. Before running, declare the cases and
allocation in `run.wifi_trial_plan`. H8 needs at least twenty actual trials in
total across that declared cohort and case plan, with every participating model
represented. The harness produces twenty trials per invocation for one named
identity; two invocations produce forty entries, not twenty. Keep every entry
and failure. More trials do not remove failed ones. A dry browser run never
counts toward this total.

## Check ingress from a second peer

For the example ports, substitute the hotspot address printed by the launcher.
Run these from another peer on that hotspot, not from the operator laptop:

```sh
curl --connect-timeout 3 --max-time 5 -o /dev/null -w '%{http_code}\n' \
  http://HOTSPOT_ADDRESS:18080/api/v3/config
curl --connect-timeout 3 --max-time 5 -o /dev/null -w '%{http_code}\n' \
  http://HOTSPOT_ADDRESS:18080/diagnostics
curl --connect-timeout 3 --max-time 5 -o /dev/null -w '%{http_code}\n' \
  http://HOTSPOT_ADDRESS:18000/healthz
```

The first two must return 403. The third must fail to connect or time out, with
no HTTP response. Any HTTP response from the direct backend fails H16. Keep the
peer's command output, exit codes, network identity and the launcher's origins.

## Trial record contract

Copy [the JSON template](TWR-17-TRIAL-RECORD.template.json) outside the repository.
It uses `tablet-wall-twr17-trial/1`, an **operator record**, rather than the
kit's `tablet-wall-validation-evidence/1` schema. The latter remains appropriate
for individual harness results attached to rows. Do not pass the aggregate trial
record to `tools/validation/evidence.py` or relabel a harness report as a trial.
No new executable is needed to begin recording observations.

- Keep the exact 21 row IDs and their requirements. `status` is `pass`, `fail`
  or `not run`. Give a reason for every fail/not-run row. An inconclusive
  measurement stays not run with the reason and observed values preserved.
- Fill exact application/docs SHA, branch/dirty state, operator, UTC timestamps,
  chosen profile, real origins, trial data path and isolation details. Do not
  replace actual SHA with the software-review SHA if the trial uses another commit.
- Record backup verify exit code 0, its database hash/revision/content scope,
  and every actual device's full ID, model, OS/browser, mode, revisions and power settings.
- Fill declared targets and uncertainty before measurements. Zero is a valid
  measured displacement; unknown is `null`. Do not fill unknowns with zero.
- For each performed row, fill `observed` using the shape below, with
  `notes`, `manual_actions` and any `measurements`. Keep `observed: null` until
  an observation exists. Preserve observations from an inconclusive attempt even
  when its disposition remains not run. Record evidence paths with SHA-256
  hashes. `evidence` entries are objects with `path` and `sha256`.
  Use `sha256sum /absolute/path/to/evidence` for each file. Keep private photos,
  captures, logs and image files outside git and exclude credentials.
- For H8, `trial_results` contains at least twenty entries in total with trial number,
  restoration time, correct-image time/duration, timing uncertainty, device ID,
  manual actions and result, plus linked raw transport/visual evidence. Its count
  is the array length; there is no separate `trials` field to disagree with it.
- For H17, set `duration_seconds` from observed start/end, at least 7200 for a
  two-hour pass. Record gaps, not just start/end pictures.
- `record_state` remains `draft` while fields are missing. Set it to `recorded`
  only after every row has a disposition and the operator signs the attestation.
  “Recorded” means observations are complete, including failures and not-run rows.
  It does not mean the wall passed.
- Keep `hardware_claim: false` and `hardware_gate_status: MISSING` in this record.
  A later scoped acceptance decision must cite the signed record, measured results,
  devices, conditions and unresolved rows before TWR-17 can be closed. No tool or
  template promotes the milestone automatically.

Before H8, fill `run.wifi_trial_plan.cases` with the declared case labels.
Each entry in `run.wifi_trial_plan.allocations` has this shape. The plan is
metadata, not an observation; keep H8's `observed` null until a trial is performed.
Planned counts do not count as completed trials.

```json
{
  "device_id": null,
  "case": null,
  "planned_trials": null
}
```

Use this shape for each entry added to `devices`. All example values are
unknown; copy the shape for each actual participant and fill observed facts.
`orientation_degrees` is browser orientation, while `mount_quarter_turn` is the
committed physical mounting choice. Neither is inferred from the other.

```json
{
  "label": null,
  "device_id": null,
  "model": null,
  "os": null,
  "browser": null,
  "launch_mode": null,
  "orientation_degrees": null,
  "mount_quarter_turn": null,
  "viewport_css": {"width": null, "height": null},
  "zoom": null,
  "profile_id": null,
  "profile_revision": null,
  "calibration_revision": null,
  "power_settings": null
}
```

Use this generic shape for a performed row's `observed` value. `measurements`
stays empty for checks without millimetre measurements:

```json
{
  "notes": null,
  "manual_actions": [],
  "measurements": []
}
```

For H4 and H5, add actual measurement entries to that array using this shape.
Use one per edge in H4 and per model/axis in H5. `device_ids` contains the full
participating IDs, `location` identifies the actual seam or screen interval,
and `quantity` is `seam displacement` or `scale interval`. `axis` is `x` or `y`.
Use actual signed values where relevant and the declared target. A zero
measurement is valid; unknown values remain null and do not justify pass.
Do not add this empty entry to an observation without an actual measurement.

```json
{
  "device_ids": [],
  "location": null,
  "quantity": null,
  "axis": null,
  "target_mm": null,
  "observed_mm": null,
  "uncertainty_mm": null
}
```

Use this shape for each H8 `trial_results` entry. Replace unknown values only
with actual observations, and retain the evidence for a failed trial:

```json
{
  "trial": 1,
  "case": null,
  "device_id": null,
  "restored_utc": null,
  "correct_image_utc": null,
  "seconds_to_correct_image": null,
  "timing_uncertainty_seconds": null,
  "manual_actions": [],
  "status": "not run",
  "reason": "No physical observation recorded.",
  "evidence": []
}
```

Video, optical synchronisation, pairing, shared-network security and unattended
operation beyond the actual soak remain unclaimed. A paint acknowledgement proves
an application rendering result, not that a physical panel is lit or aligned.
