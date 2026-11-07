"""Curated still-image assets (PROTOCOL.md "Still images").

Operator-curated JPEG and PNG files in a server-local directory —
``TABLET_WALL_ASSET_DIR`` read at call time (like ``TABLET_WALL_DB``),
defaulting to ``./assets`` — deliberately outside the frontend static mounts.
There is no upload endpoint and no path parameter: files are discovered by
scanning, addressed by the opaque content ID ``sha256:`` plus the lowercase
SHA-256 of their bytes, and read-only. Identical bytes therefore have one
identity, a rename preserves it, and replacing the bytes mints a new one.

Inventory refresh, scene acceptance, and serving scan the directory and hash
current bytes. The readiness probe validates its cached candidate with one
capped read instead, and falls back to a bounded directory scan after a miss.
Decoded format and dimensions are cached by content hash, with a bounded entry
count. A copied file is usable at once, and an ID whose bytes are gone returns
404. File metadata alone never establishes that bytes passed image validation.

Two invariants are worth spelling out because the design hangs off them:

* **Only validated bytes are inventoried.** Top-level, regular, non-symlink
  files only; Pillow must open them as a still JPEG/PNG whose extension
  agrees with the content, within the size and pixel caps, unanimated, in the
  normal EXIF orientation, *and actually decode every pixel*. Anything else —
  including a file that fails for two reasons at once — is absent from the
  inventory, so scene acceptance and serving cannot reach it, and its reason
  is written to the log once (see ``_record_rejection``) rather than the file
  simply vanishing without a trace.
* **Serving re-hashes what it read.** Because the ID *is* the hash of the
  bytes that passed validation, a response whose bytes still hash to the
  requested ID is provably those exact bytes; anything else is a 404. That is
  also what closes the race between scanning and serving: a file replaced in
  between has different bytes, hence a different hash, hence no stale copy
  can go out under the old ID.

Filesystem races are handled by construction rather than by hoping: entries
are opened with ``O_NOFOLLOW``, re-checked with ``fstat`` on the descriptor
that was actually opened, and read capped at one byte over the size limit, so
a path swapped for a symlink, a directory, or a huge file mid-scan is
rejected instead of followed.
"""

import hashlib
import logging
import os
import stat
import time
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from threading import Lock
from typing import Any

from PIL import Image

from tabletwall.protocol import ASSET_ID_PREFIX, _asset_url, _is_asset_id

# Rejections are logged once each (PROTOCOL.md "Still images" keeps invalid
# files out of the inventory; an operator still has to learn *why* their file
# did not appear). Standard library logging only — no framework.
_logger = logging.getLogger(__name__)

DEFAULT_ASSET_DIR = "./assets"

# Validation limits (PROTOCOL.md "Still images"): rejected when *over* the
# limit, so exactly 10 MiB or exactly 12 megapixels still qualify.
MAX_ASSET_BYTES = 10 * 1024 * 1024
MAX_ASSET_PIXELS = 12_000_000

# A cache miss re-scans the directory at most once per this interval, per
# directory. Repeated missing IDs therefore cost one bounded scan per window
# instead of one full scan per readiness read, while renamed or restored bytes
# still become discoverable within the window. The clock is monotonic, so a
# wall-clock change neither extends nor shortens it.
NEGATIVE_REFRESH_SECONDS = 2.0

# Only these formats are inventoried, and only under these extensions: a JPEG
# named ``.png`` is "misleadingly named" and rejected. Matching is
# case-insensitive (``PHOTO.JPG`` is a normal camera name).
_MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png"}
_EXTENSIONS_BY_FORMAT = {"JPEG": (".jpg", ".jpeg"), "PNG": (".png",)}

_EXIF_ORIENTATION = 0x0112
_NORMAL_ORIENTATION = 1

# ``O_NOFOLLOW`` is the symlink half of the race defence: a path swapped for
# a link between listing and opening fails here instead of being followed.
_OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
_READ_CHUNK = 1 << 20


class _Rejected(Exception):
    """A candidate file failed validation; ``reason`` says why.

    Control flow, not a fault: files in the directory are untrusted input,
    and returning ``None`` would have thrown away the one thing an operator
    needs — the reason their curated file is missing from the inventory.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ``(directory, name, reason)`` triples already reported. Every read path
# re-validates the whole directory, so without this one broken file would log
# on each inventory read, each scene acceptance, and each asset serve. The
# key is deliberately *stable* — reasons carry no byte counts or pixel counts
# — so replacing a bad file with another bad file of the same kind stays
# quiet, while a new kind of problem is reported again. Bounded by the
# directory's entries times the reasons below in normal use. Cap the history
# as well, so years of replacing/renaming bad files cannot retain every old
# filename forever; after the cap, a later scan may report an old problem
# again, which is safer than unbounded memory retention.
_rejections_logged: set[tuple[str, str, str]] = set()
_MAX_REJECTION_HISTORY = 2048


def _record_rejection(directory: str, name: str, reason: str) -> None:
    """Log one exclusion of one entry, at most once per file and reason."""
    key = (directory, name, reason)
    if key in _rejections_logged:
        return
    if len(_rejections_logged) >= _MAX_REJECTION_HISTORY:
        _rejections_logged.clear()
    _rejections_logged.add(key)
    _logger.warning("not using %s in %s: %s", name, directory, reason)


@dataclass(frozen=True)
class Asset:
    """One validated, content-addressed asset."""

    id: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    path: str

    def entry(self) -> dict[str, Any]:
        """The inventory wire shape (PROTOCOL.md "Still images")."""
        return {
            "id": self.id,
            "name": self.name,
            "mime": self.mime,
            "intrinsicWidth": self.width,
            "intrinsicHeight": self.height,
            "bytes": self.size,
            "url": _asset_url(self.id),
        }


# The inventory from the most recent scan together with the directory it came
# from: ``(directory, {asset_id: Asset})``. Published as one immutable value,
# so a reader never pairs one directory's inventory with another's and never
# sees a partially built scan. Replaced wholesale, never updated in place.
_inventory_state: tuple[str, dict[str, Asset]] | None = None

# Serializes scans and the negative-refresh decision. A healthy probe does not
# take it: it hashes one cached candidate without enumerating anything.
_scan_lock = Lock()

# ``directory -> monotonic time of the last bounded scan``. Directory-scoped
# so switching ``TABLET_WALL_ASSET_DIR`` neither reuses nor extends another
# directory's cooldown.
_negative_refresh: dict[str, float] = {}
_clock = time.monotonic

# Cache only validation facts, never file paths or bytes. A hash from a new
# capped read is required on every hit, even if stat metadata was preserved.
_decoded: OrderedDict[tuple[str, int], tuple[str, int, int]] = OrderedDict()
_decode_lock = Lock()
_MAX_DECODE_CACHE = 256


def asset_dir() -> str:
    """Where curated files live: ``TABLET_WALL_ASSET_DIR``, else ``./assets``."""
    return os.environ.get("TABLET_WALL_ASSET_DIR") or DEFAULT_ASSET_DIR


def refresh() -> dict[str, Asset]:
    """Re-scan the directory now and replace the cached inventory.

    This is the explicit inventory refresh (startup and ``GET /assets``). It
    clears the directory's negative-refresh cooldown, so an operator who asks
    for a refresh renews the opportunity to discover new bytes instead of
    waiting out a miss window. A directory that does not exist yet is an empty
    inventory (the default ``./assets`` is usually created by the operator
    later); a directory that exists but cannot be scanned raises, because
    silently reporting "no assets" would hide a broken configuration.
    """
    directory = asset_dir()
    with _scan_lock:
        fresh = _scan(directory)
        _negative_refresh.pop(directory, None)
    return fresh


def _scan(directory: str) -> dict[str, Asset]:
    """Scan ``directory`` and publish the inventory atomically.

    Callers hold ``_scan_lock``. Validation is a full read/hash/decode of every
    candidate, exactly as an inventory refresh must be; probes never come here
    unless their cached candidate is missing or invalid.
    """
    global _inventory_state
    fresh: dict[str, Asset] = {}
    for name, path in _candidates(directory):
        try:
            asset = _load(name, path)
        except _Rejected as rejection:
            # Excluded *and* reported: a curated file the operator expects to
            # see must not disappear from the inventory without a trace.
            _record_rejection(directory, name, rejection.reason)
            continue
        # Content identity: two files with the same bytes are one logical
        # asset, and the first name in sort order is its display name.
        fresh.setdefault(asset.id, asset)
    _inventory_state = (directory, fresh)
    return fresh


def current() -> dict[str, Asset]:
    """The inventory from the most recent scan (empty before the first one)."""
    state = _inventory_state
    return dict(state[1]) if state is not None else {}


def list_assets() -> list[dict[str, Any]]:
    """A freshly scanned inventory in the ``GET /assets`` wire shape."""
    inventory = refresh()
    return [
        asset.entry()
        for asset in sorted(inventory.values(), key=lambda entry: entry.name)
    ]


def find(asset_id: str) -> Asset | None:
    """Fresh-scanned lookup: the asset behind ``asset_id``, or None.

    Scene acceptance uses this, so an ID is accepted only against the
    directory as it is *now*, with intrinsic dimensions read from the file
    that was just validated. This is not the bounded readiness probe: it
    always scans, and does not reset the negative-refresh cooldown.
    """
    with _scan_lock:
        return _scan(asset_dir()).get(asset_id)


def available(asset_id: str) -> bool:
    """Bounded availability probe for one content ID.

    A cached candidate is validated by reading and hashing that one file
    (``_still_valid``): one capped read, no directory enumeration. Only when
    the candidate is missing or its bytes no longer hash to the requested ID
    does this fall back to a full scan, at most once per
    ``NEGATIVE_REFRESH_SECONDS`` per directory. Repeated misses therefore cost
    one scan per window, while a rename, restoration, or newly copied bytes
    still become available inside the window. A stale entry is never success.
    """
    if not _is_asset_id(asset_id):
        return False
    directory = asset_dir()
    cached = _cached(directory, asset_id)
    if cached is not None and _still_valid(cached, asset_id):
        return True
    with _scan_lock:
        now = _clock()
        last = _negative_refresh.get(directory)
        if last is not None and now - last < NEGATIVE_REFRESH_SECONDS:
            return False
        _negative_refresh[directory] = now
        fresh = _scan(directory)
    return asset_id in fresh


def _cached(directory: str, asset_id: str) -> Asset | None:
    """The cached candidate for ``asset_id``, only from ``directory``."""
    state = _inventory_state
    if state is None or state[0] != directory:
        return None
    return state[1].get(asset_id)


def _still_valid(asset: Asset, asset_id: str) -> bool:
    """True when the cached candidate still hashes to ``asset_id``.

    ``_load`` re-reads the path capped (``O_NOFOLLOW``), re-hashes the bytes,
    and re-checks the extension against the decoded format using cached decode
    facts. A changed, corrupt, oversized, or symlinked replacement therefore
    fails here and can never answer for the old identity.
    """
    try:
        current_asset = _load(asset.name, asset.path)
    except _Rejected:
        return False
    return current_asset.id == asset_id


def fetch(asset_id: str) -> tuple[Asset, bytes] | None:
    """Fresh-scanned lookup plus the asset's bytes, re-hashed to prove them.

    None means "do not serve": unknown or malformed ID, a file that vanished
    or was swapped for a symlink, or bytes that no longer hash to the
    requested ID. The hash check is what guarantees only validated bytes go
    out under a given ID.
    """
    if not _is_asset_id(asset_id):
        return None
    with _scan_lock:
        inventory = _scan(asset_dir())
    asset = inventory.get(asset_id)
    if asset is None:
        return None
    data = _read_capped(asset.path)
    if data is None or len(data) > MAX_ASSET_BYTES:
        return None
    if ASSET_ID_PREFIX + hashlib.sha256(data).hexdigest() != asset_id:
        # The bytes behind this ID changed after the scan: they are a
        # different asset now, and this ID must serve nothing at all.
        return None
    return asset, data


# ---------------------------------------------------------------------------
# scanning
# ---------------------------------------------------------------------------


def _candidates(directory: str) -> list[tuple[str, str]]:
    """Top-level, regular, non-symlink entries as ``(name, path)``, sorted.

    Sorted so the canonical display name of a duplicated asset is
    deterministic. Symlinks are skipped even when they point at a perfectly
    valid image: only the file itself is the asset. A skipped entry is
    reported once, because an operator who dropped a link or a sub-directory
    in the directory deserves to learn why it is not showing up. A missing
    directory is an empty inventory; any other failure to scan (permissions,
    say) propagates.
    """
    try:
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
    except FileNotFoundError:
        return []

    candidates: list[tuple[str, str]] = []
    for entry in entries:
        try:
            if entry.is_symlink():
                # Even a link to a perfectly valid image: only the file
                # itself is the asset.
                _record_rejection(directory, entry.name, "symlinked entries are not assets")
                continue
            if not entry.is_file(follow_symlinks=False):
                # Directories (including a sub-directory of curation), FIFOs,
                # sockets: none of them is a regular file.
                _record_rejection(directory, entry.name, "not a regular file")
                continue
        except OSError:
            continue  # vanished between listing and statting: not an error
        candidates.append((entry.name, entry.path))
    return candidates


def _read_capped(path: str) -> bytes | None:
    """Read at most ``MAX_ASSET_BYTES + 1`` bytes from a verified regular file.

    The ``O_NOFOLLOW`` open plus the ``fstat`` re-check on *that* descriptor
    close the symlink race: a path swapped for a link or a directory between
    the scan and the open is refused here instead of being followed, and a
    descriptor that does not refer to a regular file is refused even if the
    path looked like one a moment earlier. The cap bounds the work if the
    file was swapped for something enormous — one byte past the limit, then
    rejection.
    """
    try:
        fd = os.open(path, _OPEN_FLAGS)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        chunks: list[bytes] = []
        remaining = MAX_ASSET_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(_READ_CHUNK, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def _load(name: str, path: str) -> Asset:
    """Read, validate, and address one candidate file.

    Raises ``_Rejected`` with a stable, human-readable reason for anything
    that must stay out of the inventory; ``refresh`` turns each one into a
    single log line, so no curated file is ever excluded silently.
    """
    data = _read_capped(path)
    if data is None:
        raise _Rejected("unreadable or not a regular file")
    if len(data) > MAX_ASSET_BYTES:
        # Checked before hashing and before Pillow ever sees the bytes, which
        # is also what bounds the decode below: nothing over the cap can be
        # opened, let alone decoded.
        raise _Rejected("larger than the 10 MiB limit")
    asset_id = ASSET_ID_PREFIX + hashlib.sha256(data).hexdigest()
    key = (asset_id, MAX_ASSET_PIXELS)
    with _decode_lock:
        inspected = _decoded.get(key)
        if inspected is None:
            inspected = _inspect(data)
            _decoded[key] = inspected
            if len(_decoded) > _MAX_DECODE_CACHE:
                _decoded.popitem(last=False)
        else:
            _decoded.move_to_end(key)
    image_format, width, height = inspected
    lowered = name.lower()
    if not any(lowered.endswith(ext) for ext in _EXTENSIONS_BY_FORMAT[image_format]):
        raise _Rejected(f"extension does not match the {image_format} content")
    return Asset(
        id=asset_id,
        name=name,
        mime=_MIME_BY_FORMAT[image_format],
        width=width,
        height=height,
        size=len(data),
        path=path,
    )


def _inspect(data: bytes) -> tuple[str, int, int]:
    """Validate bytes with Pillow; return ``(format, width, height)`` or raise.

    Untrusted bytes must never crash the server, so *any* failure of the
    parser is a rejection: a half-copied file, a hand-edited header, a file
    that is not an image at all, or a header claiming more pixels than the
    decoder is willing to touch.

    The checks are ordered, and each Pillow step gets a handle of its own:

    * the first handle gathers format, dimensions, animation, and the EXIF
      orientation;
    * ``verify`` runs on a second handle nothing else has touched, because
      PNG's implementation may only be called directly after ``open`` and is
      invalidated by other accessors — ``getexif`` among them — while it
      reads chunks the header-only first open never reaches;
    * a third handle decodes every pixel. ``verify`` is structural, not
      decodability: a JPEG missing only its end marker passes it while
      ``load`` raises, and an inventoried file has to be one a browser can
      actually draw. That decode is bounded — the byte cap in ``_load``, the
      format and animation checks, and the 12-megapixel cap below all run
      first, so Pillow never decodes more than the limits allow.
    """
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            animated = bool(getattr(image, "is_animated", False))
            orientation = image.getexif().get(_EXIF_ORIENTATION)
    except Exception as error:
        raise _Rejected(
            f"cannot be identified as an image ({type(error).__name__})"
        ) from error
    if image_format not in _MIME_BY_FORMAT:
        raise _Rejected(f"unsupported format ({image_format or 'unidentified'})")
    if animated:
        # GIFs, APNGs, multi-frame anything: the wall shows one still.
        raise _Rejected("animated, not a still image")
    if orientation not in (None, _NORMAL_ORIENTATION):
        # EXIF-rotated files would need a transform the protocol does not
        # define, so they are rejected rather than rendered sideways.
        raise _Rejected(f"EXIF orientation {orientation}, not upright")
    if width * height > MAX_ASSET_PIXELS:
        raise _Rejected("more than the 12 megapixel limit")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
    except Exception as error:
        raise _Rejected(f"does not decode ({type(error).__name__})") from error
    return image_format, width, height
