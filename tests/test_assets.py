"""Curated still-image assets (PROTOCOL.md "Still images").

Covers the two endpoints — ``GET /assets`` (inventory) and ``GET
/assets/{id}`` (byte-verified serving) — directory validation, content
addressing (a rename keeps the ID, replaced bytes mint a new one and kill the
old), scene acceptance through ``PUT /scene`` including what is *persisted*
versus what is only projected onto the wire, the capability gate deciding
which devices are sent image content at all, and persistence across a restart.

``conftest.py`` points ``TABLET_WALL_ASSET_DIR`` at a per-test directory under
``tmp_path``, so nothing here reads or writes a real ``./assets`` in the
repository, and no test can see another test's files.
"""

import hashlib
import io
import logging
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from tabletwall import assets, persist

DEVICE_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def device_url(caps: str | None = None) -> str:
    url = f"/ws/device?device_id={DEVICE_ID}&protocol=2"
    if caps is not None:
        url += f"&caps={caps}"
    return url


def register(client, device_payload) -> None:
    response = client.post(
        "/devices/register", json={**device_payload, "device_id": DEVICE_ID}
    )
    assert response.status_code == 200


def image_bytes(
    fmt: str = "PNG", size: tuple[int, int] = (64, 48), color: str = "red", **save_kwargs
) -> bytes:
    """A freshly encoded still image — real bytes, not a stub."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


def digest(data: bytes) -> str:
    """The content ID for these bytes, computed the way the server does."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def put_file(directory: Path, name: str, data: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


def inventory(client) -> list[dict]:
    """The ``GET /assets`` payload, with its two contract points asserted
    on every read: the entries live under an ``assets`` key, and the answer
    is never cacheable (the directory changes by files being copied in).
    """
    response = client.get("/assets")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict) and set(payload) == {"assets"}, (
        "the inventory is a wrapped object, not a bare array"
    )
    assert response.headers["cache-control"] == "no-store", (
        "a snapshot of the directory must be re-read on every refresh"
    )
    return payload["assets"]


class TestInventory:
    def test_the_inventory_is_wrapped_and_never_cached(self, client, asset_dir):
        """Both response-shape contract points, on the raw response.

        The entries live under an ``assets`` key — an object, so the payload
        can grow metadata without breaking array readers — and the snapshot is
        ``no-store``, so a controller's refresh always re-reads the directory
        instead of being answered from a cached copy.
        """
        put_file(asset_dir, "poster.png", image_bytes())

        response = client.get("/assets")

        assert response.status_code == 200
        assert set(response.json()) == {"assets"}
        assert [entry["name"] for entry in response.json()["assets"]] == ["poster.png"]
        assert response.headers["cache-control"] == "no-store"

    def test_a_valid_image_is_listed_with_every_field(self, client, asset_dir):
        data = image_bytes("JPEG", size=(16, 12))
        put_file(asset_dir, "poster.jpg", data)

        assert inventory(client) == [
            {
                "id": digest(data),
                "name": "poster.jpg",
                "mime": "image/jpeg",
                "intrinsicWidth": 16,
                "intrinsicHeight": 12,
                "bytes": len(data),
                "url": f"/assets/{digest(data)}",
            }
        ]

    def test_the_inventory_refreshes_on_request(self, client, asset_dir):
        assert inventory(client) == [], "the directory starts empty"

        # Copied in after startup: the next read must see it, with no
        # restart and no in-process trigger.
        data = image_bytes()
        put_file(asset_dir, "added-later.png", data)

        assert [entry["id"] for entry in inventory(client)] == [digest(data)]

    def test_a_directory_that_does_not_exist_yet_is_an_empty_inventory(
        self, client, tmp_path
    ):
        assert not (tmp_path / "assets").exists()
        assert inventory(client) == []

    def test_an_existing_file_as_asset_directory_fails_loudly(
        self, tmp_path, monkeypatch
    ):
        wrong_path = tmp_path / "not-a-directory"
        wrong_path.write_text("not a directory")
        monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(wrong_path))

        with pytest.raises(NotADirectoryError):
            assets.refresh()

    def test_the_startup_scan_populates_the_inventory_before_any_request(
        self, asset_dir
    ):
        data = image_bytes("JPEG", size=(32, 24))
        put_file(asset_dir, "boot.jpg", data)
        asset_id = digest(data)

        # No ``client`` fixture here on purpose: the lifespan's own scan is
        # what is under test, and it must have run before the first request.
        with TestClient(main.app) as client:
            scanned = assets.current()
            listing = inventory(client)

        assert set(scanned) == {asset_id}
        assert scanned[asset_id].width == 32
        assert [entry["id"] for entry in listing] == [asset_id]

    def test_identical_bytes_have_one_identity(self, client, asset_dir):
        data = image_bytes("JPEG")
        put_file(asset_dir, "second.jpg", data)
        put_file(asset_dir, "first.jpg", data)

        listing = inventory(client)

        assert len(listing) == 1, "duplicate bytes are one logical asset"
        assert listing[0]["id"] == digest(data)
        assert listing[0]["name"] == "first.jpg", (
            "the first name in sort order is the canonical display name"
        )

    def test_a_rename_preserves_the_identity(self, client, asset_dir):
        data = image_bytes()
        original = put_file(asset_dir, "before.png", data)
        assert [entry["id"] for entry in inventory(client)] == [digest(data)]

        original.rename(asset_dir / "after.png")

        listing = inventory(client)
        assert [(entry["id"], entry["name"]) for entry in listing] == [
            (digest(data), "after.png")
        ]


class TestServing:
    def test_serving_returns_the_exact_bytes_with_nosniff_and_immutable_caching(
        self, client, asset_dir
    ):
        data = image_bytes("JPEG", size=(16, 12))
        put_file(asset_dir, "poster.jpg", data)
        asset_id = digest(data)

        response = client.get(f"/assets/{asset_id}")

        assert response.status_code == 200
        assert response.content == data
        assert response.headers["content-type"].startswith("image/jpeg")
        assert response.headers["x-content-type-options"] == "nosniff"
        # Content-addressed: these bytes can never change under this ID, so
        # the browser never needs to revalidate them.
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"

    @pytest.mark.parametrize(
        "asset_id",
        [
            "not-an-id",
            "sha256:" + "a" * 64,  # well formed, but no such asset
            "sha256:" + "A" * 64,  # uppercase: not the canonical form
            "sha256:" + "0" * 63,
            "sha256:",
        ],
    )
    def test_unknown_or_malformed_ids_are_404(self, client, asset_id):
        assert client.get(f"/assets/{asset_id}").status_code == 404

    def test_malformed_id_does_not_scan_the_directory(self, client, monkeypatch):
        def unexpected_scan():
            raise AssertionError("a malformed asset id must be rejected before scanning")

        monkeypatch.setattr(assets, "refresh", unexpected_scan)
        assert client.get("/assets/not-an-id").status_code == 404

    def test_a_removed_file_is_404_on_serving(self, client, asset_dir):
        data = image_bytes()
        path = put_file(asset_dir, "poster.png", data)
        asset_id = digest(data)
        assert client.get(f"/assets/{asset_id}").status_code == 200

        path.unlink()

        assert client.get(f"/assets/{asset_id}").status_code == 404
        assert inventory(client) == []

    def test_replaced_bytes_are_never_served_under_the_old_id(
        self, client, asset_dir
    ):
        """The ID is the hash: new bytes mean a new asset and a dead ID."""
        first = image_bytes("JPEG", color="red")
        path = put_file(asset_dir, "poster.jpg", first)
        first_id = digest(first)
        assert client.get(f"/assets/{first_id}").status_code == 200

        second = image_bytes("JPEG", color="blue")
        path.write_bytes(second)
        second_id = digest(second)
        assert second_id != first_id

        # Inventory, serving, and scene acceptance all re-scan, so all three
        # agree on the new identity at once …
        assert [entry["id"] for entry in inventory(client)] == [second_id]
        assert client.get(f"/assets/{first_id}").status_code == 404
        assert client.get(f"/assets/{second_id}").content == second

        # … and the old ID cannot be accepted into a scene any more.
        before = client.get("/wall").json()
        rejected = client.put(
            "/scene", json={"content": {"type": "image", "asset": first_id}}
        )
        assert rejected.status_code == 422
        assert client.get("/wall").json() == before

    def test_a_file_swapped_for_a_symlink_is_not_served(
        self, client, asset_dir, tmp_path
    ):
        data = image_bytes()
        path = put_file(asset_dir, "poster.png", data)
        # Same bytes, outside the curated directory: the only way to it is
        # through the link, and links are not assets.
        outside = put_file(tmp_path, "copy.png", data)
        asset_id = digest(data)
        assert client.get(f"/assets/{asset_id}").status_code == 200

        path.unlink()
        path.symlink_to(outside)

        assert client.get(f"/assets/{asset_id}").status_code == 404
        assert inventory(client) == []

    def test_bytes_changed_between_scan_and_serve_are_not_mislabeled(
        self, client, asset_dir, monkeypatch
    ):
        original = image_bytes("JPEG", color="red")
        replacement = image_bytes("JPEG", color="blue")
        put_file(asset_dir, "poster.jpg", original)
        original_id = digest(original)
        read = assets._read_capped
        calls = 0

        def swapped_read(path):
            nonlocal calls
            calls += 1
            return replacement if calls == 2 else read(path)

        monkeypatch.setattr(assets, "_read_capped", swapped_read)
        assert client.get(f"/assets/{original_id}").status_code == 404
        assert calls == 2


class TestValidation:
    """Only top-level, regular, non-symlink, still JPEG/PNG files qualify.

    Every rejection below is asserted through the inventory: a file that is
    not listed can never be served and never accepted into a scene, which is
    what makes "validated bytes" mean something.
    """

    def test_a_symlink_is_never_inventoried(self, client, asset_dir, tmp_path):
        outside = put_file(tmp_path, "real.png", image_bytes())
        (asset_dir / "link.png").symlink_to(outside)

        assert inventory(client) == []

    def test_a_symlink_to_an_inventoried_file_does_not_duplicate_it(
        self, client, asset_dir
    ):
        real = put_file(asset_dir, "real.png", image_bytes())
        (asset_dir / "alias.png").symlink_to(real)

        assert [entry["name"] for entry in inventory(client)] == ["real.png"]

    def test_directories_are_never_inventoried(self, client, asset_dir):
        # A directory wearing an image extension, and a real image nested one
        # level down: neither is a top-level regular file.
        (asset_dir / "folder.png").mkdir()
        nested = asset_dir / "nested"
        nested.mkdir()
        put_file(nested, "inside.png", image_bytes())

        assert inventory(client) == []

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX-only")
    def test_a_fifo_is_never_opened(self, client, asset_dir):
        # If non-regular files were read, this would block a worker thread —
        # and the test — instead of being skipped at the scan.
        os.mkfifo(asset_dir / "pipe.png")

        assert inventory(client) == []

    def test_a_jpeg_must_carry_a_jpeg_extension(self, client, asset_dir):
        data = image_bytes("JPEG")
        put_file(asset_dir, "misleading.png", data)
        assert inventory(client) == [], "misleadingly named files are rejected"

        put_file(asset_dir, "honest.jpg", data)
        assert [entry["name"] for entry in inventory(client)] == ["honest.jpg"]

    def test_the_extension_match_is_case_insensitive(self, client, asset_dir):
        put_file(asset_dir, "PHOTO.JPG", image_bytes("JPEG"))

        assert [entry["name"] for entry in inventory(client)] == ["PHOTO.JPG"]

    def test_a_non_image_file_is_rejected(self, client, asset_dir):
        put_file(asset_dir, "notes.txt", b"just some text")

        assert inventory(client) == []

    def test_a_gif_is_rejected(self, client, asset_dir):
        buffer = io.BytesIO()
        frames = [Image.new("P", (4, 4)) for _ in range(2)]
        frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:])
        put_file(asset_dir, "anim.gif", buffer.getvalue())

        assert inventory(client) == []

    def test_an_animated_png_is_rejected(self, client, asset_dir):
        buffer = io.BytesIO()
        frames = [Image.new("RGBA", (8, 8), (i * 40, 0, 0, 255)) for i in range(2)]
        frames[0].save(
            buffer, "PNG", save_all=True, append_images=frames[1:], duration=100
        )
        put_file(asset_dir, "anim.png", buffer.getvalue())

        assert inventory(client) == []

    def test_a_truncated_image_is_rejected(self, client, asset_dir):
        data = image_bytes("JPEG")
        put_file(asset_dir, "broken.jpg", data[: len(data) // 2])

        assert inventory(client) == []

    def test_a_jpeg_missing_only_its_end_marker_is_rejected(self, client, asset_dir):
        """Structural verification is not decodability.

        Pillow's ``verify`` passes on a JPEG that is missing only its final
        two bytes, so a file that merely survives ``verify`` could still be
        one a browser renders as a broken image. The contract is that every
        inventoried file actually decodes, which is what the full pixel
        decode in ``_inspect`` is for.
        """
        data = image_bytes("JPEG")
        put_file(asset_dir, "no-end-marker.jpg", data[:-2])

        assert inventory(client) == []

    def test_rejections_are_logged_once_with_a_useful_reason(
        self, client, asset_dir, caplog
    ):
        """An excluded file must not vanish silently — and must not spam.

        Every read path re-validates the whole directory, so each problem is
        reported on the first refresh only: one line per file and reason,
        naming the file and why it was skipped.
        """
        put_file(asset_dir, "misleading.png", image_bytes("JPEG"))
        put_file(asset_dir, "no-end-marker.jpg", image_bytes("JPEG")[:-2])

        with caplog.at_level(logging.WARNING, logger="tabletwall.assets"):
            assert inventory(client) == []
            assert inventory(client) == [], "the second refresh logs nothing new"

        messages = [
            record.getMessage()
            for record in caplog.records
            if record.name == "tabletwall.assets"
        ]
        assert len(messages) == 2, (
            "one line per problem, not one per inventory read / scene "
            "acceptance / asset serve"
        )
        assert any(
            "misleading.png" in message and "extension" in message
            for message in messages
        )
        assert any(
            "no-end-marker.jpg" in message and "decode" in message
            for message in messages
        )

    @pytest.mark.parametrize("orientation", [2, 6, 8])
    def test_an_exif_rotated_image_is_rejected(self, client, asset_dir, orientation):
        exif = Image.Exif()
        exif[0x0112] = orientation
        put_file(asset_dir, "rotated.jpg", image_bytes("JPEG", exif=exif))

        assert inventory(client) == []

    def test_a_normal_exif_orientation_is_accepted(self, client, asset_dir):
        exif = Image.Exif()
        exif[0x0112] = 1
        put_file(asset_dir, "upright.jpg", image_bytes("JPEG", exif=exif))

        assert [entry["name"] for entry in inventory(client)] == ["upright.jpg"]

    def test_an_image_over_the_pixel_cap_is_rejected(self, client, asset_dir):
        # 4000x4000 = 16 megapixels in ~56 KB on disk: well under the byte
        # cap, so the pixel cap is what rejects it.
        buffer = io.BytesIO()
        Image.new("RGB", (4000, 4000), "white").save(buffer, "PNG")
        data = buffer.getvalue()
        assert len(data) <= 10 * 1024 * 1024
        put_file(asset_dir, "huge.png", data)

        assert inventory(client) == []

    def test_an_image_over_the_byte_cap_is_rejected(self, client, asset_dir):
        # Incompressible content: 1900x1900x3 ≈ 10.8 MB, so the PNG stays
        # over 10 MiB while its pixel count sits well under the cap — the
        # byte cap is what rejects it.
        noise = os.urandom(1900 * 1900 * 3)
        buffer = io.BytesIO()
        Image.frombytes("RGB", (1900, 1900), noise).save(buffer, "PNG")
        data = buffer.getvalue()
        assert len(data) > 10 * 1024 * 1024
        assert 1900 * 1900 <= 12_000_000
        put_file(asset_dir, "noisy.png", data)

        assert inventory(client) == []

    def test_the_reader_refuses_symlinks_and_non_regular_files(
        self, asset_dir, tmp_path
    ):
        """The race defence is in the read itself, not only in the scan.

        A path swapped for a symlink between ``scandir`` and ``open`` is
        refused by ``O_NOFOLLOW``; a directory that somehow reached this far
        is refused by the ``fstat`` re-check on the descriptor.
        """
        outside = put_file(tmp_path, "real.png", image_bytes())
        link = asset_dir / "link.png"
        link.symlink_to(outside)

        assert assets._read_capped(str(link)) is None
        assert assets._read_capped(str(asset_dir)) is None
        assert assets._read_capped(str(asset_dir / "missing.png")) is None


class TestPutSceneImage:
    def test_acceptance_persists_the_id_fit_and_dimensions_but_never_a_url(
        self, client, asset_dir
    ):
        # The file is copied in *after* startup, so accepting it proves scene
        # acceptance re-scans instead of trusting the startup inventory.
        data = image_bytes("JPEG", size=(16, 12))
        put_file(asset_dir, "poster.jpg", data)
        asset_id = digest(data)

        response = client.put(
            "/scene", json={"content": {"type": "image", "asset": asset_id}}
        )

        assert response.status_code == 200
        assert response.json()["revision"] == 1
        # On the wire the descriptor is complete: the server-composed URL and
        # the dimensions derived from the file it just validated …
        assert response.json()["scene"]["content"] == {
            "type": "image",
            "asset": asset_id,
            "url": f"/assets/{asset_id}",
            "fit": "cover",
            "intrinsicWidth": 16,
            "intrinsicHeight": 12,
        }
        # … and nowhere else. The live wall must not grow a URL either, or
        # the next commit would persist one.
        expected = {
            "type": "image",
            "asset": asset_id,
            "fit": "cover",
            "intrinsicWidth": 16,
            "intrinsicHeight": 12,
        }
        assert main.wall["scene"]["content"] == expected
        assert persist.load_state()["scene"]["content"] == expected

    @pytest.mark.parametrize("fit", ["cover", "contain"])
    def test_an_explicit_fit_is_persisted(self, client, asset_dir, fit):
        data = image_bytes()
        put_file(asset_dir, "poster.png", data)

        response = client.put(
            "/scene",
            json={"content": {"type": "image", "asset": digest(data), "fit": fit}},
        )

        assert response.status_code == 200
        assert response.json()["scene"]["content"]["fit"] == fit
        assert persist.load_state()["scene"]["content"]["fit"] == fit

    def test_contain_scene_recall_preserves_fit(self, client, asset_dir):
        data = image_bytes()
        put_file(asset_dir, "poster.png", data)
        response = client.put(
            "/scene",
            json={"content": {"type": "image", "asset": digest(data), "fit": "contain"}},
        )
        assert response.status_code == 200
        expected = response.json()["scene"]["content"]
        assert client.put("/scenes/contained").status_code == 200
        assert client.put("/scene", json={"content": {"type": "color"}}).status_code == 200
        recalled = client.post("/scenes/contained/recall")
        assert recalled.status_code == 200
        assert recalled.json()["scene"]["content"] == expected
        assert persist.load_state()["scene"]["content"]["fit"] == "contain"

    def test_an_unknown_asset_is_422_and_changes_nothing(self, client):
        unknown = digest(image_bytes())  # well formed, but no such file
        before = client.get("/wall").json()

        response = client.put(
            "/scene", json={"content": {"type": "image", "asset": unknown}}
        )

        assert response.status_code == 422
        assert client.get("/wall").json() == before

    @pytest.mark.parametrize(
        "extra",
        [
            {"url": "http://elsewhere/image.png"},
            {"url": "/assets/sha256:" + "0" * 64},
            {"intrinsicWidth": 3840},
            {"intrinsicHeight": 2160},
            {"url": "/x", "intrinsicWidth": 1, "intrinsicHeight": 1},
        ],
    )
    def test_caller_supplied_urls_and_dimensions_are_422(self, client, asset_dir, extra):
        # The asset itself is valid, so the unknown field is the only reason
        # this request can be refused.
        data = image_bytes()
        put_file(asset_dir, "poster.png", data)
        body = {"content": {"type": "image", "asset": digest(data), **extra}}
        before = client.get("/wall").json()

        response = client.put("/scene", json=body)

        assert response.status_code == 422
        assert client.get("/wall").json() == before

    @pytest.mark.parametrize("fit", ["fill", "stretch", "Cover", "Contain", ""])
    def test_an_unsupported_fit_is_422(self, client, asset_dir, fit):
        data = image_bytes()
        put_file(asset_dir, "poster.png", data)
        body = {"content": {"type": "image", "asset": digest(data), "fit": fit}}
        before = client.get("/wall").json()

        response = client.put("/scene", json=body)

        assert response.status_code == 422
        assert client.get("/wall").json() == before

    @pytest.mark.parametrize(
        "asset_id",
        ["poster-1", "", "sha256:" + "0" * 63, "sha256:" + "A" * 64, "sha256:" + "g" * 64],
    )
    def test_a_malformed_asset_id_is_422(self, client, asset_id):
        assert (
            client.put(
                "/scene", json={"content": {"type": "image", "asset": asset_id}}
            ).status_code
            == 422
        )


class TestMissingAsset:
    def test_a_missing_asset_keeps_the_scene_and_never_falls_back_to_colour(
        self, client, device_payload, asset_dir
    ):
        data = image_bytes("JPEG", size=(64, 48))
        path = put_file(asset_dir, "poster.jpg", data)
        asset_id = digest(data)
        register(client, device_payload)
        assert client.put(
            "/scene", json={"content": {"type": "image", "asset": asset_id}}
        ).status_code == 200
        accepted = client.get("/wall").json()
        descriptor = accepted["scene"]["content"]
        assert descriptor["url"] == f"/assets/{asset_id}"
        assert descriptor["intrinsicWidth"] == 64

        path.unlink()

        # Inventory and serving re-scan and report the absence …
        assert inventory(client) == []
        assert client.get(f"/assets/{asset_id}").status_code == 404
        # … but the scene itself is untouched: same revision, same derived
        # dimensions, still an image — an explicit failure for the client to
        # render, never a silent conversion to colour and never a revision
        # the operator did not ask for (PROTOCOL.md "Still images").
        after = client.get("/wall").json()
        assert after["scene"] == accepted["scene"]
        assert after["revision"] == accepted["revision"]

        with client.websocket_connect(device_url(caps="image")) as device:
            device.receive_json()  # welcome
            frame = device.receive_json()  # wall
        assert frame["scene"]["content"] == descriptor
        assert frame["revision"] == accepted["revision"]


class TestCapabilityGate:
    def test_a_capable_device_gets_the_descriptor_with_url_and_dimensions(
        self, client, device_payload, asset_dir
    ):
        data = image_bytes(size=(64, 48))
        put_file(asset_dir, "poster.png", data)
        asset_id = digest(data)
        register(client, device_payload)
        assert client.put(
            "/scene", json={"content": {"type": "image", "asset": asset_id}}
        ).status_code == 200

        with client.websocket_connect(device_url(caps="image")) as device:
            device.receive_json()  # welcome
            frame = device.receive_json()  # wall

        assert frame["scene"] == {
            "content": {
                "type": "image",
                "asset": asset_id,
                "url": f"/assets/{asset_id}",
                "fit": "cover",
                "intrinsicWidth": 64,
                "intrinsicHeight": 48,
            },
            "layout": "active",
        }

    @pytest.mark.parametrize("caps", [None, "", "calibration", "video"])
    def test_a_device_without_the_image_cap_gets_colour_and_no_url(
        self, client, device_payload, asset_dir, caps
    ):
        """``caps=None`` is the legacy v2 client: no caps advertised at all."""
        data = image_bytes()
        put_file(asset_dir, "poster.png", data)
        register(client, device_payload)
        assert client.put(
            "/scene", json={"content": {"type": "image", "asset": digest(data)}}
        ).status_code == 200

        with client.websocket_connect(device_url(caps=caps)) as device:
            device.receive_json()  # welcome
            frame = device.receive_json()  # wall

        assert frame["scene"]["content"] == {"type": "color"}
        assert frame["revision"] == 1, (
            "the scene did change; only this device's rendering is downgraded"
        )

    @pytest.mark.parametrize("suffix", ["", "&protocol=1&caps=image"])
    def test_a_v1_device_still_never_receives_a_wall_frame(
        self, client, device_payload, asset_dir, suffix
    ):
        data = image_bytes()
        put_file(asset_dir, "poster.png", data)
        register(client, device_payload)
        assert client.put(
            "/scene", json={"content": {"type": "image", "asset": digest(data)}}
        ).status_code == 200

        with client.websocket_connect(
            f"/ws/device?device_id={DEVICE_ID}{suffix}"
        ) as device:
            welcome = device.receive_json()
            assert welcome["type"] == "welcome"
            assert "protocol" not in welcome, "a v1 welcome stays exactly as it was"

            # No wall frame follows an image scene either: the colour replay
            # is still the next frame out of a v1 socket.
            assert client.post(
                f"/devices/{DEVICE_ID}/color", json={"color": "#3b82f6"}
            ).status_code == 200
            assert device.receive_json() == {
                "type": "set_color",
                "color": "#3b82f6",
            }

    def test_controller_frames_carry_the_descriptor_with_its_url(
        self, client, asset_dir
    ):
        data = image_bytes(size=(800, 600))
        put_file(asset_dir, "poster.png", data)
        asset_id = digest(data)
        assert client.put(
            "/scene", json={"content": {"type": "image", "asset": asset_id}}
        ).status_code == 200

        with client.websocket_connect("/ws/controller?protocol=2") as controller:
            snapshot = controller.receive_json()
            assert snapshot["wall"]["scene"]["content"] == {
                "type": "image",
                "asset": asset_id,
                "url": f"/assets/{asset_id}",
                "fit": "cover",
                "intrinsicWidth": 800,
                "intrinsicHeight": 600,
            }

            assert client.put("/wall", json={"width": 3000}).status_code == 200
            updated = controller.receive_json()

        assert updated["type"] == "wall_updated"
        assert updated["wall"]["scene"]["content"]["url"] == f"/assets/{asset_id}"
        assert "url" not in persist.load_state()["scene"]["content"], (
            "even the broadcast copy is composed, never persisted"
        )


class TestImageScenePersistence:
    @pytest.mark.parametrize("fit", ["cover", "contain"])
    def test_the_image_scene_survives_a_restart_and_the_url_is_recomposed(
        self, device_payload, asset_dir, fit
    ):
        data = image_bytes("JPEG", size=(64, 48))
        put_file(asset_dir, "poster.jpg", data)
        asset_id = digest(data)

        with TestClient(main.app) as first:
            register(first, device_payload)
            assert first.put(
                "/scene",
                json={"content": {"type": "image", "asset": asset_id, "fit": fit}},
            ).status_code == 200
            before = first.get("/wall").json()
            persisted = persist.load_state()["scene"]["content"]

        with TestClient(main.app) as second:
            after = second.get("/wall").json()
            served = second.get(f"/assets/{asset_id}")
            register(second, device_payload)
            with second.websocket_connect(device_url(caps="image")) as device:
                device.receive_json()  # welcome
                frame = device.receive_json()  # wall

        # What survives the restart is the reference — ID, fit, and derived
        # dimensions — not the bytes and not the URL …
        assert persisted == {
            "type": "image",
            "asset": asset_id,
            "fit": fit,
            "intrinsicWidth": 64,
            "intrinsicHeight": 48,
        }
        # … and the restarted server recomposes the same descriptor from it.
        assert after["scene"] == before["scene"]
        assert after["revision"] == before["revision"]
        assert served.status_code == 200
        assert served.content == data
        assert frame["scene"]["content"]["url"] == f"/assets/{asset_id}"

    def test_deleted_asset_after_restart_keeps_the_broken_scene(self, asset_dir):
        data = image_bytes("JPEG", size=(64, 48))
        path = put_file(asset_dir, "poster.jpg", data)
        asset_id = digest(data)

        with TestClient(main.app) as first:
            before = first.put(
                "/scene", json={"content": {"type": "image", "asset": asset_id}}
            ).json()

        path.unlink()
        with TestClient(main.app) as second:
            after = second.get("/wall").json()
            assert second.get(f"/assets/{asset_id}").status_code == 404

        assert after["scene"] == before["scene"]
        assert after["revision"] == before["revision"]
        assert after["generation"] != before["generation"]
