"""Content validation reuse must not weaken filesystem freshness."""

import os
from io import BytesIO

from PIL import Image

from tabletwall import assets


def image_bytes(color):
    output = BytesIO()
    Image.new("RGB", (16, 12), color).save(output, "PNG")
    return output.getvalue()


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
