# Image-wall runbook (trusted hotspot trial)

One page from start to a blank wall again, for the supervised HTTP profile:
tablets on a laptop hotspot, the controller on that laptop's loopback. This
page does not describe an unattended server. Commands assume the repository
root and `uv`.

## 1. Before starting

- One tablet at a time is easiest for the first join. Charge the tablets.
- Stop any earlier app on port 8000, and any earlier `make hotspot`.
- Pick a data directory with room for `wall.db`, `assets/`, `media/`, and the
  two logs. The default is `~/.local/share/tablet-wall-ai`.
- Never run this profile on shared or venue Wi-Fi. Registration and device
  sockets are open to hotspot clients, uploads are disabled, and there is no
  app login in the HTTP trial.

## 2. Start

```sh
make hotspot ARGS='--data-dir /absolute/path/to/wall-data'
```

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
3. Open `http://127.0.0.1:<backend-port>/controller/physical.html` on the
   laptop. In **System → Join & readiness**, copy the exact tablet address or
   scan its QR. The QR is a URL shortcut, not pairing; the tablet still
   registers and opens its own socket. A loopback address only works on the
   laptop and is labelled accordingly.
4. Leave the page open. Reloading keeps the tablet identity.

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

Wall console → **Wall → Show a still image**. Pick a library image, check the preview,
then **Show on wall**. Browsing does not change the wall until you apply.

Choose **Fill the wall (crops)** or **Fit whole image (adds bars)** before
showing the image. The stage previews crop, screen coverage and bezel/gap
occlusion. If bytes are missing, the image remains unavailable; select another
image or restore the file and use **Refresh images**. Readiness reports the
same missing bytes as `available: false`.

## 6. Arrange and verify the grid

Open **Wall → Layout & size**. Choose the layout kind, **2 × 2** or **1 × 4**,
and the tablet order and body orientation. The latter preset is one horizontal
row. Use **Preview arrangement**, review it, then **Apply layout**. Cancel
leaves the active wall unchanged. Extra gap defaults to zero.

For measured layouts, confirm each actual tablet model or provide measured
calibration first. Model profiles stay approximate. **Wall → Colours and
continuity checks → Wall-sized grid** generates an image for the committed
physical bounds with 50 mm intervals. Use it to record actual seam/scale
measurements; the generated coordinates do not prove physical accuracy.
**Logical calibration pattern** is available only for logical layouts.

Check **N of M showing** and the tablet cards. A network connection alone does
not count as a current image paint. A failed card offers **Retry image**.

## 7. Blank the wall

Open **Wall → Colours and continuity checks → Black wall**. This shows an
ordinary black image without deleting the layout. **Restore previous content**
returns to the prior scene. **Tablet colours** instead shows each tablet's
assigned diagnostic colour.

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
mkdir -p /absolute/backups

uv run python deploy/backup.py backup \
  --db "$wall_data_dir/wall.db" \
  --assets "$wall_data_dir/assets" \
  --media "$wall_data_dir/media" \
  --dest /absolute/backups/wall-YYYYMMDD

uv run python deploy/backup.py verify --src /absolute/backups/wall-YYYYMMDD
```

Keep the destination off the only disk, and set
`TABLET_WALL_BACKUP_DIR=/absolute/backups` on the service if you want
readiness to show the newest `manifest.json`. That directory is read-only to
the app.

## 10. Restore to new targets

Stop the service first. Restore never overwrites and never records permanent
paths; you repoint the environment afterwards.

```sh
mkdir -p /absolute/restored-YYYYMMDD

uv run python deploy/backup.py restore \
  --src /absolute/backups/wall-YYYYMMDD \
  --db /absolute/restored-YYYYMMDD/wall.db \
  --assets /absolute/restored-YYYYMMDD/assets \
  --media /absolute/restored-YYYYMMDD/media
```

Point `TABLET_WALL_DB`, `TABLET_WALL_ASSET_DIR`, and
`TABLET_WALL_MEDIA_DIR` at the new paths, start the app, and confirm the wall,
saved layouts, images, and tablet re-registration. Keep the old targets until
the restored copy has been used; they are your rollback.

Rehearse the whole cycle on throwaway paths at least once:

```sh
uv run python deploy/drill.py
```

After a real restore, `GET /diagnostics?verify=1` re-hashes ready uploads.
If the drill passed, record the time in
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
