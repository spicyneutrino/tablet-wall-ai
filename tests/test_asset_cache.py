"""Content validation reuse must not weaken filesystem freshness."""

import hashlib
import logging
import os
from io import BytesIO

import pytest
from PIL import Image

from tabletwall import assets


def image_bytes(color):
    output = BytesIO()
    Image.new("RGB", (16, 12), color).save(output, "PNG")
    return output.getvalue()


def asset_id(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


class FakeClock:
    """A controlled monotonic clock for the negative-refresh cooldown."""

    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_repeated_reads_hash_current_bytes_but_decode_only_once(asset_dir, monkeypatch):
    path = asset_dir / "poster.png"
    path.write_bytes(image_bytes("red"))
    assets._decoded.clear()
    decoded = []
    inspect = assets._inspect

    def track(data):
        decoded.append(data)
        return inspect(data)

    monkeypatch.setattr(assets, "_inspect", track)
    first = assets.list_assets()
    assert assets.list_assets() == first
    assert len(decoded) == 1
    path.write_bytes(image_bytes("blue"))
    second = assets.list_assets()
    assert second[0]["id"] != first[0]["id"]
    assert len(decoded) == 2


def test_stat_preserving_malicious_swap_is_not_a_cache_hit(asset_dir):
    path = asset_dir / "poster.png"
    data = image_bytes("red")
    path.write_bytes(data)
    asset_id = assets.list_assets()[0]["id"]
    previous = path.stat()
    path.write_bytes(b"x" * len(data))
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert assets.list_assets() == []
    assert assets.fetch(asset_id) is None


def test_cached_content_is_rechecked_for_extension_and_symlinks(asset_dir):
    path = asset_dir / "poster.png"
    path.write_bytes(image_bytes("red"))
    asset_id = assets.list_assets()[0]["id"]
    renamed = path.rename(asset_dir / "poster.jpg")
    assert assets.find(asset_id) is None
    renamed.rename(path)
    assert assets.find(asset_id) is not None
    outside = asset_dir.parent / "outside.png"
    path.rename(outside)
    path.symlink_to(outside)
    assert assets.fetch(asset_id) is None


def test_cached_validation_does_not_survive_stricter_pixel_limits(asset_dir, monkeypatch):
    (asset_dir / "poster.png").write_bytes(image_bytes("red"))
    assert assets.list_assets()
    monkeypatch.setattr(assets, "MAX_ASSET_PIXELS", 1)
    assert assets.list_assets() == []


def test_decode_cache_is_bounded_and_does_not_keep_image_bytes(asset_dir, monkeypatch):
    assets._decoded.clear()
    monkeypatch.setattr(assets, "_MAX_DECODE_CACHE", 2)
    for color in ("red", "green", "blue"):
        (asset_dir / "poster.png").write_bytes(image_bytes(color))
        assert assets.list_assets()
    assert len(assets._decoded) == 2
    assert all(isinstance(facts, tuple) for facts in assets._decoded.values())


def test_deletion_and_directory_change_do_not_reuse_cached_inventory(asset_dir, tmp_path, monkeypatch):
    path = asset_dir / "poster.png"
    path.write_bytes(image_bytes("red"))
    asset_id = assets.list_assets()[0]["id"]
    path.unlink()
    assert assets.find(asset_id) is None
    path.write_bytes(image_bytes("red"))
    assert assets.find(asset_id) is not None
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(tmp_path / "different"))
    assert assets.find(asset_id) is None


def test_a_healthy_probe_enumerates_nothing(asset_dir, monkeypatch, caplog):
    data = image_bytes("red")
    (asset_dir / "poster.png").write_bytes(data)
    (asset_dir / "unrelated.png").write_bytes(image_bytes("blue"))
    assets.refresh()
    target = asset_id(data)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a healthy probe must not enumerate the directory")

    monkeypatch.setattr(assets.os, "scandir", forbidden)
    before = list(caplog.records)
    with caplog.at_level(logging.WARNING, logger="tabletwall.assets"):
        assert assets.available(target) is True
    assert caplog.records == before, "no unrelated candidate was read or rejected"


def test_repeated_misses_scan_at_most_once_per_cooldown(asset_dir, monkeypatch):
    assets.refresh()
    clock = FakeClock(100.0)
    monkeypatch.setattr(assets, "_clock", clock)
    data = image_bytes("red")
    target = asset_id(data)

    assert assets.available(target) is False, "the first miss scans"
    (asset_dir / "late.png").write_bytes(data)
    assert assets.available(target) is False, "inside the window nothing is re-scanned"
    clock.now = 101.999
    assert assets.available(target) is False
    clock.now = 102.0
    assert assets.available(target) is True, "the next window recovers the bytes"


def test_a_rename_keeps_identity_without_waiting_for_a_refresh(asset_dir):
    data = image_bytes("red")
    before = asset_dir / "before.png"
    before.write_bytes(data)
    assets.refresh()
    target = asset_id(data)
    assert assets.available(target) is True

    before.rename(asset_dir / "after.png")

    assert assets.available(target) is True
    assert assets.current()[target].name == "after.png"


def test_deletion_then_restoration_recovers_after_the_cooldown(asset_dir, monkeypatch):
    data = image_bytes("red")
    path = asset_dir / "poster.png"
    path.write_bytes(data)
    assets.refresh()
    target = asset_id(data)
    assert assets.available(target) is True

    clock = FakeClock(200.0)
    monkeypatch.setattr(assets, "_clock", clock)
    path.unlink()
    assert assets.available(target) is False
    path.write_bytes(data)
    assert assets.available(target) is False, "a miss inside the window is not re-scanned"
    clock.now = 202.0
    assert assets.available(target) is True


def test_an_explicit_refresh_renews_the_discovery_opportunity(asset_dir, monkeypatch):
    assets.refresh()
    clock = FakeClock(300.0)
    monkeypatch.setattr(assets, "_clock", clock)
    data = image_bytes("red")
    target = asset_id(data)

    assert assets.available(target) is False, "opens the cooldown while still absent"
    assets.refresh()
    (asset_dir / "poster.png").write_bytes(data)
    clock.now = 300.5

    assert assets.available(target) is True, "the explicit refresh reset the window"


def test_uncached_bytes_are_found_inside_the_bound(asset_dir, monkeypatch):
    assets.refresh()
    clock = FakeClock(400.0)
    monkeypatch.setattr(assets, "_clock", clock)
    other = asset_id(image_bytes("blue"))
    data = image_bytes("green")
    target = asset_id(data)

    assert assets.available(other) is False, "one window serves every missing ID"
    (asset_dir / "new.png").write_bytes(data)
    assert assets.available(target) is False
    clock.now = 402.0
    assert assets.available(target) is True


@pytest.mark.parametrize("replacement", ["corrupt", "different", "oversize", "symlink"])
def test_replaced_bytes_never_satisfy_the_old_identity(
    asset_dir, tmp_path, monkeypatch, replacement
):
    original = image_bytes("red")
    path = asset_dir / "poster.png"
    path.write_bytes(original)
    assets.refresh()
    target = asset_id(original)
    assert assets.available(target) is True

    clock = FakeClock(500.0)
    monkeypatch.setattr(assets, "_clock", clock)
    replacement_data = image_bytes("blue")
    if replacement == "corrupt":
        path.write_bytes(b"not an image")
    elif replacement == "different":
        path.write_bytes(replacement_data)
    elif replacement == "oversize":
        path.write_bytes(b"x" * (assets.MAX_ASSET_BYTES + 1))
    else:
        outside = tmp_path / "outside.png"
        outside.write_bytes(original)
        path.unlink()
        path.symlink_to(outside)

    assert assets.available(target) is False
    clock.now = 502.0
    assert assets.available(target) is False, "the old identity never comes back"
    if replacement == "different":
        assert assets.available(asset_id(replacement_data)) is True


def test_a_stat_preserving_swap_is_not_available(asset_dir):
    data = image_bytes("red")
    path = asset_dir / "poster.png"
    path.write_bytes(data)
    assets.refresh()
    target = asset_id(data)
    assert assets.available(target) is True

    previous = path.stat()
    path.write_bytes(b"x" * len(data))
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))

    assert assets.available(target) is False


def test_a_matching_extension_is_required_for_a_healthy_candidate(asset_dir):
    data = image_bytes("red")
    path = asset_dir / "poster.png"
    path.write_bytes(data)
    assets.refresh()
    target = asset_id(data)
    assert assets.available(target) is True

    path.rename(asset_dir / "poster.jpg")

    assert assets.available(target) is False


def test_directory_scoping_does_not_reuse_another_directory(
    asset_dir, tmp_path, monkeypatch
):
    data = image_bytes("red")
    (asset_dir / "poster.png").write_bytes(data)
    assets.refresh()
    target = asset_id(data)
    assert assets.available(target) is True

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(other))
    clock = FakeClock(600.0)
    monkeypatch.setattr(assets, "_clock", clock)
    assert assets.available(target) is False, (
        "the previous directory's cache is not reused"
    )
    (other / "poster.png").write_bytes(data)
    assert assets.available(target) is False
    clock.now = 602.0
    assert assets.available(target) is True

    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(asset_dir))
    assert assets.available(target) is True, "cooldowns do not cross directories"


@pytest.mark.parametrize(
    "bad",
    ["not-an-id", "sha256:" + "A" * 64, "sha256:" + "0" * 63, "sha256:"],
)
def test_malformed_ids_do_not_scan(monkeypatch, bad):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("a malformed id must not scan")

    monkeypatch.setattr(assets.os, "scandir", forbidden)
    assert assets.available(bad) is False
