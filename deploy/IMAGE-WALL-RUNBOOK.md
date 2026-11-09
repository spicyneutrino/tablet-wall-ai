# Image-wall runbook (trusted hotspot trial)

One page from start to a blank wall again, for the supervised HTTP profile:
tablets on a laptop hotspot, the controller on that laptop's loopback. This
page does not describe an unattended server. Commands assume the repository
root and `uv`.

For the consolidated implementation's real-tablet acceptance, use the
[isolated trial procedure and canonical checklist](../docs/tablet-wall-readiness/HARDWARE-ACCEPTANCE.md).
It restores a verified snapshot to new paths, selects the integration-branch
commit, uses separate launcher configuration/ports, and records all observations.

This handoff describes software candidate
`efadb0fdc34ae13b21d880004a95a602d9ba33b8`. The software freeze and the
all-MISSING hardware packet are accepted records; they do not establish
hardware acceptance. `rollout_ready` and `deployed` remain `false`.
Native assistive technology, native zoom, IME, real-tablet TLS trust, live
ingress, and all hardware gates remain MISSING.

The [M10-01 author rehearsal record](../../../artifacts/tablet-wall-restoration-2026-11-07/M10-01/attempt-1/result.json)
reports 99/99 checks, 70 focused pytest passes, and a direct synthetic drill.
It records online backup, verification, fresh-target restore, fresh shipped-client
paint, rejection of an old acknowledgement, and old-code recovery using that
code's own pre-upgrade backup. This used generated private fixture data,
not an operator database. Independent acceptance is pending. See its
[commands](../../../artifacts/tablet-wall-restoration-2026-11-07/M10-01/attempt-1/command-transcripts.md),
[recovery instructions](../../../artifacts/tablet-wall-restoration-2026-11-07/M10-01/attempt-1/recovery-instructions.md),
[browser evidence](../../../artifacts/tablet-wall-restoration-2026-11-07/M10-01/attempt-1/browser-evidence.md),
and [hash manifest](../../../artifacts/tablet-wall-restoration-2026-11-07/M10-01/attempt-1/MANIFEST.sha256).
These package-relative links assume `projects/<repository>/` and `artifacts/`
share the review-package root. They are external evidence, not shipped files.

## 1. Before starting

- One tablet at a time is easiest for the first join. Charge the tablets.
- Stop any earlier app on port 8000, and any earlier `make hotspot`.
- Pick a data directory with room for `wall.db`, `assets/`, `media/`, and the
  two logs. The default is `~/.local/share/tablet-wall-ai`.
- Never run this profile on shared or venue Wi-Fi. Registration and device
  sockets are open to hotspot clients, and there is no app login in the HTTP
  trial. Image uploads are disabled by default.

## 2. Start

```sh
make hotspot ARGS='--data-dir /absolute/path/to/wall-data'
```

To add an image from the controller running on this computer, opt in for that
launch:

```sh
make hotspot ARGS='--data-dir /absolute/path/to/wall-data --operator-uploads'
```

With the default data directory, use `make hotspot ARGS='--operator-uploads'`.
The preflight prints **Image uploads: this computer only** when enabled,
or **Image uploads: disabled** with launch help when off.

The flag is not saved in hotspot settings. It enables the backend's existing
loopback upload admission for the exact controller Origin on `127.0.0.1` and
the configured backend port. The upload request must come directly from this
computer; forwarded requests are refused. It does not make the controller
available from a phone on the hotspot. The tablet listener continues to deny
uploads, library routes, controller pages, and operator commands. The UI and
Settings help explain **Adding images is off for this launch** and the launch
command. A browser setting cannot enable uploads. Inherited non-disabled
`TABLET_WALL_UPLOAD_MODE` values are refused, even with the flag. Unset that
variable before using this launch option. The HTTP trial still refuses
`TABLET_WALL_AUTH_TOKEN`; use the separate authenticated HTTPS deployment for
that profile.

This is a trusted single-operator computer profile. A local process can forge
the exact Origin header, so this check is not local-user authentication.
Requests require one exact Origin, a loopback transport peer, and no
`Forwarded` or `X-Forwarded-*` headers. The backend stays bound to `127.0.0.1`.
Testing a phone-sized viewport on this local origin does not admit a remote
phone. Shared or venue Wi-Fi remains unsupported.

The launcher prints a preflight block with the interface, hotspot address,
exact tablet URL, controller URL, Wi-Fi name (or `unknown`), data paths, and
the security mode. Then it prints **Ready** after it checks the client page,
the `/client` redirect, registration validation, a device WebSocket upgrade,
and that operator routes are denied on the tablet listener.

If it fails, the message names the first actionable cause: no active access
point, an occupied port, a missing command, a firewall zone, or a Caddy
validation error. Read `backend.log` and `caddy.log` in the data directory.
Logs rotate at 1,000,000 bytes with two archives each.

## 3. Join a tablet

1. Connect the tablet to the hotspot Wi-Fi name printed by the launcher.
2. Open the exact printed URL, ending in `/client/`. Typing `http://` and a
   bare address is not the same thing.
3. Open the printed `http://127.0.0.1:<backend-port>/controller/` on the
   laptop. Select **Tablets**, then open **Add tablets**. Copy the exact tablet
   address or scan its QR. The QR is a URL shortcut, not pairing; the tablet still
   registers and opens its own socket. A loopback address only works on the
   laptop and is labelled accordingly.
4. Leave the page open. Reloading keeps the tablet identity.

The controller entry opens `physical.html`, preserving the query and fragment.

## 4. Check readiness

The operator card is built from these routes. From the laptop:

```sh
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/api/v3/readiness
```

- `/healthz` is ready only when the database is readable and its schema
  matches. It reports generation, revision, and device counts, never paths.
- `/api/v3/readiness` shows the exact tablet URL, QR route, whether the Wi-Fi
  name was actually configured, the security/upload mode, data paths,
  selected content and whether its bytes resolve, backup recency, the last
  recorded restore rehearsal, and OS wake/fullscreen advice.
- `null` with `known: false` or `recorded: false` means nobody configured or
  recorded that value. It is not a guessed success.

The tablet listener refuses both routes, even with a forged operator header.

## 5. Choose an image

Select **Images**. Pick an image in **Library**, check the preview, then select
**Show image**. Browsing and uploading do not change the displayed content.
To adjust the applied image, select **Adjust image**. Use **View applied**
to compare the current wall with the pending preview. Return to the preview
and select **Show image** only after review. **Discard** clears the preview.
No selection, upload, or comparison automatically shows an image.

Fit bars use the scene background, default `#0b1120`. Adjusting an applied
image or previewing saved content retains its custom background. Selecting
a different library image starts with the default background. There is no
background colour picker in the workspace.

Choose **Fill** to crop or **Fit** to show the whole image with bars before
showing the image. The stage previews crop, screen coverage and bezel/gap
occlusion. If bytes are missing, the image remains unavailable; select another
image or restore the file and select **Refresh** in **Library**.
Open **Image details** to inspect the missing asset identity. Readiness reports
the same missing bytes as `available: false`.

## 6. Arrange and verify the grid

Select **Arrange**. Choose **Relative** or **Measured**, then a grid preset.
Open **Tablets and mounting** to review membership, order, and mounted top
edges. **1 × 4** is one horizontal row with four selected tablets; the label
changes with membership. Editing **Rows** or **Columns** switches to a custom
grid. Select **Allow empty trailing cells** if the grid has more cells than
selected tablets.

Select **Preview arrangement**, review the geometry and warnings, then select
**Apply arrangement**. **Discard arrangement** clears the local draft.
Preview and Discard leave the active wall unchanged. Extra gap defaults to
zero. Use **View applied** to compare without discarding the preview.

Relative positions, dimensions, and bezels use logical wall units. Measured
slots use millimetres and pin profile and calibration revisions. Do not
interpret logical units as millimetres or substitute latest records for pins.
**Fit** and **2x** above the stage change the view only. Alt pauses snapping
for mouse or pen drags. On touch, use the snap checkbox. **Match screen shape**
is relative-only and requires a selected placed tablet with fresh online
status and a positive viewport. Refresh stale status first. Match changes
the draft, which still needs review and Apply.
Use the numeric position, size, and bezel fields for precise edits. If a field
is invalid, correct its reported error before previewing or applying.

For measured layouts, confirm each actual tablet model or provide measured
calibration first. Model profiles stay approximate. In **Settings**, open
**Check patterns**. **Wall-sized grid** generates an image for the committed
physical bounds with 50 mm intervals. Use it to record actual seam/scale
measurements; the generated coordinates do not prove physical accuracy.
**Logical calibration pattern** is available only for logical layouts.

Check **N of M showing** and the tablet cards. A network connection alone does
not count as a current image paint. To retry a failed image, select the tablet
in **Tablets**, open **Recovery**, and select **Retry image** when available.
Offline tablets keep physical recovery guidance instead of unavailable commands.

Read each tablet's power readiness separately from image paint. A held wake
lock is a browser report, not proof the OS will keep the display awake.
Unknown or stale power status cannot establish readiness. Offline recovery
requires checking power, Wi-Fi, and the existing browser on that tablet.

If a command response is lost, use **Refresh status** and inspect the current
wall before retrying. A command may have committed before the connection
failed. A `412` means the preview guard is stale: refresh and rebuild the
preview before applying. A missing guard returns `428`. Do not blindly retry
a write with a new ETag. If upload completion is uncertain, refresh the
library before uploading again. Missing image bytes require restoring those
bytes or choosing another image.

## 7. Blank the wall

Use **Presentation checks** in Images or **Check patterns** in Settings.
These controls change wall content. Logical calibration needs relative
bounds. A wall-sized grid needs committed measured bounds.
Select **Black wall**. This shows an ordinary black image without deleting the layout.
To return to the prior scene, open **Images**, then **Image details**, and select
**Restore previous content**. **Tablet colours** instead shows each tablet's
assigned diagnostic colour. Check the restored asset, fit, background, and
current paint. This restores content, not a database.

## 8. Stop

`Ctrl+C` in the launcher terminal. It terminates both children, removes only
the runtime firewall opening it added, and exits. Logs stay in the data
directory. A firewall opening that already existed is left alone.

## 9. Back up

Use the existing tool; it is the only backup path here. A snapshot contains
the database plus **only referenced** curated assets and uploads. Unused
files in the asset directory and unused uploads are **not** copied, and their
database rows are marked `unavailable` in the snapshot. If you need the whole
library, copy it separately and say so; do not describe a wall-recovery
snapshot as a full library backup.

The launcher's environment belongs to its child processes. In a fresh shell,
set the same data directory supplied to `--data-dir`; the launcher does not
export storage variables into your shell.

```sh
wall_data_dir=/absolute/path/to/wall-data
wall_backup_root=/absolute/backups
wall_snapshot="$wall_backup_root/wall-YYYYMMDD"
mkdir -p "$wall_backup_root" || exit 1

uv run python deploy/backup.py backup \
  --db "$wall_data_dir/wall.db" \
  --assets "$wall_data_dir/assets" \
  --media "$wall_data_dir/media" \
  --dest "$wall_snapshot" || exit 1

uv run python deploy/backup.py verify --src "$wall_snapshot" || exit 1
```

The snapshot destination must be absent; its parent must exist. Never raw-copy
a running SQLite database. The tool uses SQLite online backup. Stop if backup
or verification fails. Keep the destination off the only disk, and set
`TABLET_WALL_BACKUP_DIR=/absolute/backups` on the service if you want
readiness to show the newest `manifest.json`. That directory is read-only to
the app.

## 10. Restore to new targets

Use the verified `wall_snapshot` from section 9. Create only the parent;
leave `wall.db`, `assets`, and `media` absent. Stop the service first. Restore
never overwrites and never records permanent paths; you repoint the environment
afterwards.

```sh
wall_restore_root=/absolute/restored-YYYYMMDD
mkdir -p "$wall_restore_root" || exit 1

uv run python deploy/backup.py restore \
  --src "$wall_snapshot" \
  --db "$wall_restore_root/wall.db" \
  --assets "$wall_restore_root/assets" \
  --media "$wall_restore_root/media" || exit 1
```

Point `TABLET_WALL_DB`, `TABLET_WALL_ASSET_DIR`, and
`TABLET_WALL_MEDIA_DIR` at the new paths, start the app, and confirm the wall,
saved layouts, images, and tablet re-registration. Restored identities start
offline. A new process generation requires fresh client paint; a previous
acknowledgement cannot prove current paint. Keep the old targets until
the restored copy has been used; they are your rollback.

Before a code upgrade, preserve a separate pre-upgrade backup and the exact
old code, dependency environment, launch configuration, origins, and private
secrets needed to run it. A snapshot from this candidate is not proof that
an older binary can read its schema or manifest. Never test an old binary
against the upgraded database.

For data rollback on the same compatible software, stop the candidate and
repoint all three storage paths to the preserved prior targets. For code
rollback, stop the candidate and restore the verified pre-upgrade snapshot
into new paths using a tool compatible with that snapshot, then start the
recorded old code and configuration against those paths. Set `TABLET_WALL_DB`
to the restored `wall.db`, `TABLET_WALL_ASSET_DIR` to restored `assets`, and
`TABLET_WALL_MEDIA_DIR` to restored `media`. With the hotspot launcher, use
the restored parent as `--data-dir`, separate `--config` and ports, and only
one owning process. Keep both sets of
targets. Recheck health, content bytes, saved records, and tablet identities.
Do not merge newer writes into the old database by hand.

Rollback discards changes made since the chosen backup. Record that data loss
explicitly. The fixture rehearsal above does not verify your operator data.
Both procedures still require independent acceptance and an operator-data rehearsal.
Record actual paths, old and new SHAs, tool versions, snapshot hashes,
command exits, diagnostics, and observed losses or incompatibilities.

Rehearse the whole cycle on throwaway paths at least once:

```sh
uv run python deploy/drill.py || exit 1
```

After a real restore, `GET /diagnostics?verify=1` re-hashes ready uploads.
Record a rehearsal marker only after its corresponding rehearsal succeeds.
The synthetic drill alone does not verify your copied operator data or old code.
Record the time in
`$TABLET_WALL_BACKUP_DIR/restore-rehearsal.json` as
`{"completed_utc":"..."}`; readiness shows it only then.

## 11. Secrets and CA are separate

The database backup does not contain the operator password hash, the internal
operator credential, the Caddy local CA private key, or an environment file.
Keep those on the host with mode 600 and back them up separately, or accept
that a host rebuild needs them re-created. Tablets receive only the CA public
certificate. The HTTP trial uses no certificate and no app login.

## 12. Tablet power and kiosk (OS-managed)

- **iPadOS:** Settings → Display & Brightness → Auto-Lock; Guided Access for
  touch confinement. Guided Access does not stop the display sleeping by
  itself; check the session options and keep the exit passcode.
- **Android:** raise the screen timeout, or enable the developer option
  **Stay awake while charging**; use app pinning for touch confinement, with a
  known way out. Manufacturer menus differ.
- The page's Screen Wake Lock is **unavailable on plain HTTP** (`insecure`).
  On HTTPS it is best effort and does not replace the OS timeout.
- The Full screen button needs a tap and does not survive a reload.
- **No remote wake.** This server cannot wake a sleeping or powered-off
  tablet, and no Wake-on-LAN, push, or browser path here does.

See [KIOSK.md](KIOSK.md) for the device checklist and its gates.

Experimental playlist and playback controls require the explicit opt-in in
**Settings → Experimental**. Enabling those controls does not start playback
and does not establish physical video readiness.

## 13. What is tested, and what is not

Tested by the repository's isolated suites:

- direct-loopback operator HTTP hotspot launch, startup ingress checks,
  route denials, readiness/health, join QR encoding, page security headers,
  and bounded log rotation;
- backup/verify/restore to fresh temporary paths via `deploy/drill.py`;
- the HTTPS reference's static guards and ingress tests.

Not tested, and not claimed:

- a real host reboot or service supervision on this profile (TWR-17);
- real iPad/Android sleep, wake, auto-lock, Guided Access/app pinning, or
  Wi-Fi drop/reconnect;
- physical seams, optical timing, or a hardware soak;
- composing the reference two-origin HTTPS proxy (which strips cookies) with
  app shared-secret authentication. Do not describe that combination as
  working until it is actually exercised.

Treat every item in [KIOSK.md](KIOSK.md#real-device-gates-all-required-before-validated)
as open until it is ticked on real hardware.
