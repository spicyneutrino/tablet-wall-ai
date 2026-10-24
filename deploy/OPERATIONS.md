# Operations reference (Phase 3b — **pending validation**)

These are reference artifacts for running and recovering tablet-wall-ai. They
have **not** been exercised end to end on a real host or with real tablets:
treat every command here as something you rehearse once before trusting it,
and expect to adapt it. Nothing in this repository installs, enables or starts
a service for you.

Companion documents:

- [../README.md](../README.md) — what the software does and does not do
- [README.md](README.md) — the Phase 3a two-origin hotspot reference (how to
  get traffic to the process at all)
- [tablet-wall.service.example](tablet-wall.service.example) — placeholder-only
  systemd unit template
- [KIOSK.md](KIOSK.md) — tablet/OS-side display behaviour and its validation
  gates
- `backup.py` in this directory — backup, verify and restore (see
  [Backups](#backups))

## Two deployment shapes, kept separate

| | **Running Caddy hotspot (today's reference)** | **Eventual server (not designed yet)** |
| --- | --- | --- |
| Where | the operator's laptop, with the laptop's hotspot | an always-on host on a real LAN/VPN or the internet |
| Origins | `https://<hotspot-ip>:8443` and `https://localhost:8444`, no DNS | needs a name, real DNS and certificates you have not chosen yet |
| TLS | Caddy local/internal CA; every tablet must trust that CA **before** the LAN goes offline | likely a public certificate; see [CA trust](#ca-trust-decide-later) |
| Operator reach | loopback only, behind HTTP Basic auth | reachability, auth and firewall decisions all open |
| Supervision | started by hand from a terminal | a service manager, i.e. the example unit above |
| Ingress checks | `deploy/smoke.sh` + manual tablet checks | must be repeated from scratch; hotspot results do not transfer |

Do not carry hotspot settings over to a server by editing the address and
assuming the rest still holds: bindings, TLS, operator exposure and firewall
rules are all part of the trust boundary and change with the shape.

## Placeholders to fill before anything runs

| Placeholder | Meaning | Where |
| --- | --- | --- |
| `/REPLACE/with/checkout/of/tablet-wall-ai` | absolute path to this repository checkout | service example (`WorkingDirectory`, `ExecStart`, `Documentation`) |
| `/REPLACE/with/data-dir` | absolute directory holding the database and curated assets; back this up | service example (`TABLET_WALL_DB`, `TABLET_WALL_ASSET_DIR`) |
| `https://REPLACE-operator-host.example:8444` | exact operator origin as the browser shows it | service example (`TABLET_WALL_OPERATOR_ORIGIN`) |
| `https://REPLACE-tablet-host.example:8443` | exact tablet origin as the browser shows it | service example (`TABLET_WALL_TABLET_ORIGIN`) |
| `WALL_HOTSPOT_IP` | IPv4 of the laptop's hotspot interface | `deploy/run-hotspot.sh`, `deploy/hotspot.Caddyfile` |
| `WALL_OPERATOR_PASSWORD_HASH` | `caddy hash-password` result | `deploy/run-hotspot.sh`, `deploy/hotspot.Caddyfile` |
| `BACKUP_DEST` / restore targets | directories used for snapshots | this document |

Rules: every placeholder must be replaced before use; a leftover
`/REPLACE/...` in a live unit is a failed deploy, not a warning. Keep the two
origins byte-for-byte what the browser sends, including scheme and port.

## Running the service

1. Decide **user unit vs system unit yourself** (see the header of
    [tablet-wall.service.example](tablet-wall.service.example)), copy the file,
    fill in every placeholder, then `daemon-reload` and enable it manually if
    you want it supervised at boot. For a system unit, set a dedicated
    non-root `User=`/`Group=` with access to the checkout and data; otherwise
    systemd defaults to root. A user unit runs as your account. The repository
    never runs those commands.
2. **One process, one worker.** Active wall state, revisions and sockets are
   process-local: two workers or two replicas against the same database would
   diverge and can overwrite each other's state. Do not add `--workers`, do
   not scale this horizontally, and do not point another wall at the same file.
3. **The roster is process-local.** A restart empties the roster; tablets
   re-register and reconnect on their own, and placements whose tablet has not
   come back appear as vacant reservations. Plan restarts for moments when a
   blank roster is acceptable, and re-check the controller afterwards.
4. Logs go to the journal (`journalctl -u tablet-wall.service`, or
   `journalctl --user -u ...`); `Restart=on-failure` covers crashes, not
   wedged processes — confirm the wall still renders after any restart.
5. The backend stays on loopback (`--host 127.0.0.1`); the proxy is the only
   thing meant to be reachable. Re-run the ingress checks from
   [README.md](README.md) after any binding, proxy or origin change.

## Backups

Contract (approved, and what `backup.py` is for):

- a **verified snapshot** of the SQLite database **plus only the referenced
  SHA-256 curated assets and managed upload objects** — unreferenced files in
  the asset directory and unused uploads are not part of the wall and are not
  copied; the captured database marks unused upload rows `unavailable` so a
  restore cannot advertise bytes that were deliberately left out;
- restore only into **new** targets, with the service stopped;
- no force flag, no atomic database/assets cutover, no permanent paths
  recorded anywhere: after a restore *you* point the service at the new paths.

The commands below are `deploy/backup.py`'s real interface (standard library
only, run with the same interpreter as the server). Exit code `0` is success;
`1` is a refusal or a failed verification, printed as one line on stderr; `2`
is a usage error; `130` is an interrupt. There is no force flag.

A snapshot directory holds `manifest.json`, `database/wall.db`, `assets/`
with only the referenced curated files, and `media/objects/` with the
transitive closure of referenced managed uploads (master, display, fallback
and thumbnail). Manifest version 2 records the schema, pipeline, referenced
scope, object/rendition relationships and omitted uploads; version 1
snapshots remain readable and restorable. `backup` verifies its own staging directory
with the same code path as `verify` before publishing it by one rename, so a
snapshot that exists is one that already passed. `restore` verifies first,
writes only new targets, and rolls back only what that run created; it refuses
targets `TABLET_WALL_DB`/`TABLET_WALL_ASSET_DIR` still name, but it cannot see
whether the service is running — stopping it is yours.

Take a snapshot (while the service runs; the tool uses SQLite's online backup
rather than copying a file mid-write):

```sh
uv run python deploy/backup.py backup \
  --db "$TABLET_WALL_DB" \
  --assets "$TABLET_WALL_ASSET_DIR" \
  --media "$TABLET_WALL_MEDIA_DIR" \
  --dest "$BACKUP_DEST"
```

Verify every snapshot when you take it, not when you need it:

```sh
uv run python deploy/backup.py verify --src "$BACKUP_DEST"
```

An unverified snapshot is not a backup. Keep the destination off the machine's
only disk, and copy it somewhere else — remote destination, schedule and
retention window are **open decisions** below.

### Restore drill (rehearse this before you need it)

1. Stop the service: `systemctl stop tablet-wall.service` (or `systemctl
   --user stop ...`). Restore assumes no writer is attached; there is no
   force flag to override this.
2. Choose **new** paths for the database and assets — for example
   `/REPLACE/with/data-dir/restored-YYYYMMDD/{wall.db,assets,media}`. Restore
   refuses to overwrite, so nothing that exists today is touched. A manifest 2
   snapshot that carries managed media needs `--media`:

   ```sh
   uv run python deploy/backup.py restore --src "$BACKUP_DEST" \
     --db /REPLACE/with/data-dir/restored-YYYYMMDD/wall.db \
     --assets /REPLACE/with/data-dir/restored-YYYYMMDD/assets \
     --media /REPLACE/with/data-dir/restored-YYYYMMDD/media
   ```

3. There is no atomic cutover: edit the unit (or environment) to point
   `TABLET_WALL_DB`, `TABLET_WALL_ASSET_DIR` and `TABLET_WALL_MEDIA_DIR` at
   the new paths, then start the service again.
4. Check the wall: active layout and scene recall, curated images resolve,
   tablets re-register, `deploy/smoke.sh` still passes.
5. Record how long the whole drill took; that number is your real recovery
   time.

`deploy/drill.py` rehearses the whole cycle (populate, backup while running,
restore to new targets, boot, compare) on a throwaway instance; see
[README.md](README.md#backup-and-recovery-drill) for what it proves and what
it leaves to a real host. After a real restore, `GET /diagnostics?verify=1`
re-hashes every ready upload.

### Rollback — keep the old targets

Restore never modifies the previous database, asset or media directory, so
rollback is only a repoint: stop the service, set `TABLET_WALL_DB`,
`TABLET_WALL_ASSET_DIR` and `TABLET_WALL_MEDIA_DIR` back to the paths you were
using before, start it
again. **Do not delete, move or "clean up" the old targets** until the new
one has been verified in normal use; they are your rollback, and they are also
the only copy the restore tool will not overwrite.

## CA trust (decide later)

The step-by-step trust checklist (a human task) and origin-migration recipe are
in [README.md](README.md#field-readiness-r5-operations-notes).

The hotspot reference uses Caddy's local certificate authority. Decisions that
are still open: who holds the CA private key, how its **public certificate**
reaches each tablet, what happens when a tablet is replaced, and whether the
eventual server should use a public certificate instead. Until that is
decided, install only the CA public certificate on tablets and treat the key
as a secret; see [KIOSK.md](KIOSK.md#certificate-trust-on-an-offline-lan) and
the [Caddy local HTTPS notes](https://caddyserver.com/docs/automatic-https#local-https).

## Secrets

No secret lives in this repository: not the operator password, not its hash,
not the CA private key, not a netrc, not an environment file. Keep them on
the host with tight permissions (mode 600, owned by the account that needs
them) and keep them out of the unit file too — a committed unit is a commit
history leak.

## Open decisions

- remote backup destination, schedule and retention window;
- CA lifecycle: key custody, rotation, what happens on device replacement;
- user vs system unit, service account, and any hardening flags;
- the server shape: name, DNS, certificates, operator exposure, firewall;
- log rotation and how long journal output is kept.
