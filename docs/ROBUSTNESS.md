# Runtime robustness

Device metadata and the active wall survive a restart. Every restored device starts offline. WebSocket connections, negotiated protocol and capabilities, viewports, playback sessions, clock estimates, and online status never enter the durable roster.

## Device metadata

`schema_meta` contains the versioned JSON document `device_roster.v1`. Its allowed fields are `device_id`, `width`, `height`, `type`, `color`, `number`, and `last_seen`. The display number is optional after its lease expires. Existing databases without this key load an empty roster and keep their wall reservations. The database schema remains version 3 because the existing metadata table already supports this additive document.

A malformed roster refuses startup before the wall generation is rewritten. A present JSON `null` is malformed, distinct from an absent key. Duplicate numbers, invalid UUIDs, unknown fields, invalid dimensions, noncanonical colors, and invalid contact times also refuse startup. The rejected document remains available for repair.

Registration, color changes, removal, and identity replacement commit metadata before notifying controllers or tablets. A synchronous transaction shares one SQLite connection through a `ContextVar`. The connection is local to the current thread and task context. Transaction bodies contain no `await`. Device removal commits its placement and roster changes together. Identity replacement also copies display profiles and calibrations inside that transaction. A failure restores the live wall and the original device dictionaries, preserves sockets, rolls back SQLite, and sends no mutation notification.

Heartbeat contact times remain in memory between checkpoints. One checkpoint every 60 seconds saves the current metadata for all devices, and shutdown takes a final checkpoint. A successful checkpoint bounds contact-time loss after an unexpected crash to one checkpoint interval. Checkpoint failures are logged and retried on the next interval. They cannot promise that bound while storage remains unavailable. The 15-minute display-number lease still expires according to historical contact time. Restored contact times do not establish live presence.

The existing SQLite backup copies the metadata document along with the wall. The backup drill compares restored device metadata and verifies that every tablet starts offline before it re-registers.

## Curated image validation

Every inventory lookup scans the current directory, opens each candidate without following symlinks, checks that the opened descriptor is regular, reads within the byte cap, and hashes the bytes. The cache stores only validated format and dimensions under their SHA-256 and pixel-limit key. It keeps at most 256 entries and retains no file bytes or paths.

A cache hit therefore proves that these exact bytes already passed a full Pillow decode. Renames still undergo extension validation. Deletion, directory changes, corrupt replacements, and symlink swaps remain visible immediately. Preserving file size and modification time cannot reuse validation for different bytes. Serving still rereads and hashes the requested file before responding.

Cold or changed content still pays the full validation cost. Large inventories can evict cached facts and require more decodes. The cache deliberately avoids trusting file metadata, so every lookup still reads and hashes the inventory.

## One worker owns the runtime

The device sockets, playback session, and clock state are process-local. Run Uvicorn with `--workers 1`. Lifespan startup takes a nonblocking exclusive `flock` on `<canonical database path>.runtime.lock` before loading or mutating state. A second process using that database refuses startup with the required worker setting in its error. The lock covers the complete lifespan and releases on normal exit, startup failure, or process death. The lock file remains in place so future processes lock the same inode.

This check applies to Uvicorn CLI workers even when no worker count is present in the environment. With Uvicorn 0.52.4, a real two-worker smoke test observed one successful startup and the second worker refuse ownership. The supervisor then stopped both workers. `/wall` briefly returned HTTP 200 during startup before the server stopped. Run with `--workers 1` to keep the wall available. Processes using separate databases remain separate instances.

The frontend mounts resolve their directories relative to `main.py`. Importing and serving the application from another working directory therefore still serves `/client/` and `/controller/`. Database, media, and curated asset locations retain their explicit environment settings and existing defaults.

## Repeatable inventory measurement

The local benchmark uses four deterministic 1920 by 1080 JPEG files totaling 5,546,176 bytes. It creates temporary database, media, and asset directories and needs no remote service or paid API. Both implementations receive an initial warmup request. Five alternating rounds then make three real `GET /assets` requests per implementation, including route dispatch, inventory serialization, and response validation.

```sh
.venv/bin/python tools/benchmark_asset_inventory.py \
    --baseline-ref 2cd559a557d31d129b36ebcd1329d02b4d2a2a90 --profile
```

Repeated inventory requests were faster on the measured host. The median fell from 66.24 ms to 5.40 ms per request across five rounds. Baseline rounds ranged from 65.92 to 68.39 ms. Cached rounds ranged from 5.23 to 5.57 ms. Each side completed 15 successful responses and 60 current-file reads. Baseline decoded 60 images during timing; the warmed cache decoded none. Every response contained the expected content IDs and dimensions. There were no failed responses.

An untimed profile identified JPEG pixel decoding as the baseline limiter and SHA-256 as the cached limiter. The baseline profile spent about 62 ms in Pillow's pixel decoder, which accounts for the measured time saved. The cached profile spent about 3 ms hashing. Before measurement, the host reported 32 logical CPUs and load averages of 4.37, 4.35, and 3.20. Other work was present, so alternating rounds reduced drift between implementations.

These numbers describe warmed inventory requests in a single process through FastAPI's test client. They do not measure TCP, TLS, tablet rendering, cold startup, or concurrent-user throughput. The [raw measurements](benchmarks/asset-inventory-20261028.json) and [untimed profiles](benchmarks/asset-inventory-20261028-profile.txt) preserve the inputs, work counts, round values, and limiter evidence.
