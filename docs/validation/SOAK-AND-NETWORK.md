# Soak and network validation

Status: tooling and dry runs only. `hardware_gate_status` stays `MISSING` for
`soak` and `real-wifi-os`. The two-hour physical media soak, the overnight
still soak and the twenty real Wi-Fi/OS restore trials require the operator,
the tablet fleet and the access point. A desktop Chromium run on one host is a
harness test, not a tablet soak.

Tools:

- `simulator/browser/fleet_soak.py` runs N disposable Chromium clients on one
  disposable server. It reports gate `soak` with evidence kind
  `software-simulation`.
- `deploy/network_trials.py` records twenty restoration trials against an
  operator origin and tablet. Live runs report gate `real-wifi-os` with
  evidence kind `operator-hardware`. Its dry mode reports
  `software-simulation`.
- `simulator/browser/recovery_run.py` remains the network-emulation control
  for one browser client. It is not Wi-Fi evidence.

Every tool writes `report.json` through `tools/validation/evidence.py`. The
schema and the evidence rules are in
[EVIDENCE-SCHEMA.md](EVIDENCE-SCHEMA.md). Artifacts must stay outside the
repository.

## Fleet soak harness

```
uv run --group browser python -m simulator.browser.fleet_soak \
  --artifacts /tmp/opencode/tw-fleet-$(date +%s) \
  --clients 4 --duration 60 --interval 0.5
```

The harness starts one disposable server on a free loopback port and N
calibrated clients on distinct identities. It writes a persisted idle scene,
a looping playlist with one still and one synthetic video, and then samples
until the requested duration ends.

Each sample records:

- the server's `/api/v3/playback` status, including the displayed occurrence,
  video drift, cohort, leases and any recovery record;
- each original member's canvas centre pixel, canvas visibility, page status
  and computed-visible video elements with `currentTime`, `paused` and
  `readyState`;
- new page errors, console warnings/errors, failed requests, HTTP responses
  at or above 400 and non-clean socket closes;
- server `VmRSS` from `/proc/<pid>/status` and `utime + stime` ticks from
  `/proc/<pid>/stat`;
- the achieved elapsed time and the intervals with no sample.

The run performs three deliberate phases:

1. The still/video playlist loops repeatedly. Every displayed occurrence
   change is a boundary event.
2. At about 30 percent of the duration the harness waits for a still, takes
   one client's browser context offline, closes that client's device socket
   with code 4000, restores the context after three seconds, and measures time
   to `connected` and time to a repainted picture. The page must keep its
   stored device identity.
3. At about 65 percent it stops playback, verifies that every client returns
   to the persisted scene, starts playback again, and verifies that every
   client repaints.

A video is advancing only when a computed-visible element is not paused, has
`readyState` at least 2, and its `currentTime` grew between samples. A still
is correct only when the canvas centre pixel matches the expected still colour
within the shared pixel tolerance. Three consecutive bad samples for the same
occurrence record a stall or a stale paint. The sample interval is 0.5 seconds
by default.

The sampling loop pauses during the controlled recovery and the Stop/Start
phase. The report lists those intervals as `unobserved` and classifies the
matching gaps as deliberate. Any other gap above one second fails the
sampling-coverage scenario.

### Dry run record

The committed harness ran on 2026-10-25 with four clients, a 0.5-second
interval and a 60-second duration. It completed 108 samples over 60.346
seconds, observed 22 display changes, 0 video stalls and 0 stale still paints.
All 22 checks and all 6 scenarios passed. The controlled recovery reconnected
in 0.843 seconds and repainted in 2.140 seconds. Stop returned every client to
the persisted scene in 0.115 seconds. Start repainted every client in 1.031
seconds. The only sampling gaps were the two deliberate phases, with an
unexplained maximum gap of 0.0 seconds and a sampling coverage ratio of
0.878. Server RSS moved from 62,864 kB to 63,052 kB, a 188 kB rise, and the
server used 0.84 CPU seconds, or 1.39 percent of one core, over the run. The
report is `complete`, keeps `hardware_gate_status = MISSING`, and recorded no
unexpected page, console, request or socket issue.

The run is a harness test. It validates the sampling, the playlist, the
recovery path, the Stop/Start path and the report. It does not measure a
tablet decoder, thermal limit, panel, radio or physical screen.

### Report and exit codes

Exit `0` means the evidence report is `complete`. Exit `1` means a check or a
scenario failed. Exit `2` means the run aborted with an error. The report
keeps `hardware_gate_status = MISSING` and `hardware_claim = false` in every
case.

The limitations section names the shared host CPU, memory, GPU, display
refresh, clock and NIC. It also names the synthetic video and the missing
two-hour and overnight runs. Do not remove those limitations from a copied
report.

## Required two-hour physical media soak

The harness cannot satisfy this gate. Use real tablets on the installed
origin, with the real access point and the real power and thermal conditions.

Set the acceptance record before the first measurement. Do not adjust a
threshold after seeing the result. At minimum record:

- application commit, branch and dirty state;
- every tablet model, OS version, browser version and device id;
- access point model, firmware, band, channel and WAN state;
- calibration revision and viewport for every tablet;
- playlist contents, video duration and persisted scene asset;
- chargers, ambient temperature and the position of each tablet;
- the operator name, start time and planned end time in UTC;
- the maximum allowed RSS growth and the device temperature limit.

The published thresholds in the roadmap are fixed. This document does not
revise the 10-second connectivity target, the two-hour duration or any optical
threshold.

### Procedure

1. Confirm the kiosk settings from [KIOSK-CHECK.md](KIOSK-CHECK.md). Auto-Lock,
   Guided Access or pinning and any managed-kiosk policy must already be in
   place.
2. Start the production server and open `/client/` on every tablet over the
   installed origin. Confirm there is no certificate warning and every
   tablet's status is `connected`.
3. Load a looping playlist with at least one still and one video. Keep a
   persisted still behind it. Record the exact assets and the calibration
   revision.
4. Start the two-hour clock. Run the controller and the server on mains power.
   Keep the tablets on mains power and on the chosen network.
5. Sample the server every second on the host. Capture RSS and CPU ticks with
   `TABLET_WALL_SOAK_PID` set to the server process:
   ```
   while sleep 1; do
     awk '/VmRSS/{print "rss_kb", $2}' "/proc/$TABLET_WALL_SOAK_PID/status"
     awk '{print "cpu_ticks", $14 + $15}' "/proc/$TABLET_WALL_SOAK_PID/stat"
   done >> /tmp/tw-soak-resources.log
   ```
6. Observe every tablet at least every five minutes. Record the visible
   content, whether the picture is advancing, the reported wake-lock state,
   charging state, temperature and any browser chrome or sleep. Take a photo
   of the whole wall at each check.
7. At a planned moment, perform one controlled connectivity interruption and
   record the restoration timestamp independently. Measure the time until the
   tablet is `connected` and the wall repaints. The target is 10 seconds.
8. If operationally safe, perform one Stop/Start from the controller. Record
   how long each tablet takes to return to the persisted scene and to repaint
   the first item.
9. Let the run reach two hours without restarting the server, the tablets or
   the browser. A restart ends that run and requires a new record. It is not a
   continuation.
10. Stop the resource sampler, screenshot every tablet, collect the browser
    console and the controller roster, and record the exact end time.

### Acceptance

All of these must hold for the whole two hours:

- the achieved duration is at least two hours;
- every tablet remains visible, awake and advancing at every operator check;
- the original cohort is complete and no tablet is replaced or silently
  excluded for an unrecorded reason;
- there are no unplanned page errors, console errors, failed requests or
  socket errors;
- the planned connectivity interruption recovers within 10 seconds;
- the Stop/Start returns every tablet to the persisted scene and then to the
  playlist;
- server RSS stays under the limit set before the run, and CPU does not show
  an unbounded climb;
- no tablet reaches its thermal limit, shuts down or stops charging;
- the report is `complete` and every skipped or unobserved interval is named.

A single failed row blocks that run. Do not average a failed tablet away. Do
not reuse a run across two gate records.

Keep the raw captures and the resource log outside the repository unless the
operator authorizes a bounded sample. Reference their paths and hashes in the
acceptance record.

## Overnight still soak

Run this only when unattended overnight use is required. A still-only playlist
or a persisted still is enough. Video is not part of this soak.

The duration, resource limits and temperature limits must be set before the
run. This document deliberately supplies no defaults, because a safe overnight
limit depends on the tablet, the charger, the enclosure and the room. Write
these values into the acceptance record before starting:

| Setting | Operator value |
| --- | --- |
| Duration and UTC start/end | |
| Sampling interval for host RSS and CPU | |
| Maximum server RSS growth | |
| Maximum average server CPU | |
| Maximum tablet case or battery temperature | |
| Maximum ambient temperature | |
| Allowed reboots or reloads | zero by default |
| Power source and charger per tablet | |
| Network interruption allowance | |

Procedure:

1. Configure the kiosk settings and confirm the still is displayed on every
   tablet. Record a baseline screenshot of each and the starting RSS.
2. Start the overnight clock and begin host sampling at the chosen interval.
   Record tablet temperature every 30 minutes, or more often if the vendor
   guidance requires it.
3. Do not touch, unlock or re-open the tablets. Any interaction is a new run
   unless the operator records it as a planned probe.
4. In the morning, capture the same screenshots, the final RSS, the final CPU
   ticks, the tablet temperatures and the browser lifecycle evidence from
   KIOSK-CHECK.md.
5. Mark the run `incomplete` if the duration, resource limit or temperature
   limit was not fixed before execution. Do not invent a limit afterwards.

Acceptance uses the pre-set limits plus these fixed rules:

- every tablet still shows the persisted still and is awake;
- no unexplained page reload, browser crash or server restart;
- the original cohort is complete;
- no thermal shutdown, charger failure or visible panel damage;
- any planned network interruption recovered within 10 seconds;
- the report names every unobserved interval.

## Network trials

The harness records twenty restorations. The target is 10 seconds from the
independently recorded restoration to both origin reachability and the named
tablet's roster entry becoming online. The trial's `seconds` is the slower of
those two observations. All twenty trials must be recorded and all twenty must
meet the target. One failure blocks the set.

`recovery_run.py` is not this measurement. It drops one Chromium context
offline and restores it on loopback. It remains the client-reconnect control.
It cannot be promoted to Wi-Fi, AP, radio or OS evidence.

### Preconditions

- Run the harness from the operator host on the Wi-Fi path. If the harness
  runs on the server host, the origin may stay reachable through the host's
  own network path while the tablet loses Wi-Fi. The named tablet's roster
  state is then the part that detects the loss. Record which vantage was used.
- The named tablet must already be registered and online in `/devices`.
- The operator host and the restoration recorder must share a synchronized
  clock. The harness compares each supplied timestamp with its own receipt of
  that timestamp, and fails a trial whose difference exceeds 60 seconds.
- Record the AP model and firmware, WAN state, band, channel, tablet model and
  OS, operator and case labels. These are operator metadata, not
  measurements.
- Keep the server, AP and tablet on mains power where possible.

### Live command

```
uv run python deploy/network_trials.py \
  --artifacts /tmp/opencode/tw-network-$(date +%s) \
  --base-url https://192.168.50.1:8443 \
  --tablet-device-id <stable-device-uuid> \
  --ap "living-room AP, firmware X" --wan fibre \
  --band "5 GHz" --channel 36 \
  --tablet "iPad model, iPadOS version" --operator "<name>" \
  --case ap-reboot \
  --restored-marker /tmp/tw-restores.txt
```

The harness first waits for an outage. It counts two consecutive observations
of an unreachable origin or an offline tablet as an outage. It then waits for
the next line in the marker file and measures from that exact timestamp.

Append one line at each restoration. Only the timestamp is required. The
optional case and note fields are separated by `|`:

```
date -u +%Y-%m-%dT%H:%M:%S.%6NZ >> /tmp/tw-restores.txt
2026-10-25T14:03:11.412000Z | wan-loss | uplink restored by hand
```

Use `--restored-stdin` to type or pipe one line per trial instead. Use
`--restored-at` with exactly twenty values for a pre-scheduled run. The harness
still tries to observe the outage before each supplied time. A past timestamp
cannot prove the preceding outage, so that trial is recorded as unobserved
and fails its outage evidence.

For each trial:

1. Start the harness while the tablet is online.
2. Apply the case. Examples are an AP power cycle, an AP channel change, a WAN
   uplink loss with the AP still up, airplane mode on the tablet, and Wi-Fi
   off/on on the tablet.
3. At the moment connectivity returns, append the timestamp or press Enter on
   stdin. Do not wait for the tablet to repaint before recording the moment.
4. Watch the printed trial row. It names the case, the exact restoration time,
   origin seconds, tablet seconds, the slower value and any failure.
5. Observe the tablet. Record whether the page became visible, whether it
   reconnected and whether the wall repainted. The harness cannot see the
   physical screen.

### Cases and the twenty-trial budget

Record the distribution across cases. A set of twenty AP reboots does not
cover WAN loss or a tablet-side airplane-mode toggle. A defensible set names
the cases and counts, for example:

| Case | Example count | What it exercises |
| --- | --- | --- |
| AP reboot or power cycle | 6 | DHCP, bridge and Wi-Fi re-association |
| AP channel change or band steer | 4 | Client re-association without an origin outage |
| WAN uplink loss with AP up | 5 | The tablet keeps Wi-Fi while the origin path fails |
| Tablet airplane mode | 3 | OS network teardown and restore |
| Tablet Wi-Fi off/on | 2 | Interface restart with the AP unchanged |

The counts are examples, not a fixed quota. What matters is that the operator
records the actual case per trial and that all twenty are attempted.

### Distribution and failures

The report includes p50, p95, minimum, maximum, every failure id and the sorted
seconds. A failed trial carries its failure text in the report and in
`trials.json`. Common failures:

- no outage was observed before the restoration;
- the origin did not answer within the observation window;
- the tablet did not return to online in the roster;
- the slower observation exceeded 10 seconds;
- the restoration timestamp disagreed with the harness clock.

Do not delete a slow trial or replace it with a new one. A re-run is a new
twenty-trial set with its own record.

### Dry mode

```
uv run --group browser python deploy/network_trials.py --dry \
  --artifacts /tmp/opencode/tw-network-dry-$(date +%s)
```

The dry mode starts a disposable loopback server, opens `/client/` in
Chromium, switches the browser context offline, closes the device socket,
restores the context, and measures the origin and the client page. It proves
the polling, timestamping, distribution and report path.

The committed dry run completed 20 trials and all 7 checks. No trial failed.
The nearest-rank distribution was p50 0.237 seconds, p95 0.242 seconds,
minimum 0.124 seconds and maximum 0.243 seconds. Every trial observed its
emulated offline interval, dropped the device socket, and recovered both the
loopback origin and the client page.

The dry mode is `software-simulation`. It is not Wi-Fi, an AP, a radio, an OS
or a physical tablet. Its report keeps `hardware_gate_status = MISSING`.

## Evidence files

Each run writes at least:

- `report.json`, the evidence contract report;
- `trials.json` for network runs, or `samples.json`, `timeline.json`,
  `sockets.json`, `issues.json` and `playlist.json` for fleet runs;
- the disposable server log;
- bounded screenshots on a failure or at the end of a fleet run.

The report hashes every artifact it names. Copy artifacts to the operator's
evidence store before deleting a temporary directory. Keep raw camera,
tablet and network captures outside the repository unless a bounded sample is
authorized.

Every report keeps `hardware_gate_status = MISSING`. Kit execution success is
not hardware acceptance.
