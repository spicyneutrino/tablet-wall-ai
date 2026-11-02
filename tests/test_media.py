"""Managed store and operator admission (R1).

The decoder is exercised in ``test_media_worker.py``. These tests pin the
store boundary: who may upload, what is reserved before a body is read, how a
failed job is removed, how verified objects are published, and how a served
object is re-hashed rather than trusted.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.datastructures import Headers

import tabletwall.media as media
from tabletwall import persist

ORIGIN = "https://operator.wall.test:8444"
CREDENTIAL = "test-operator-credential-0123456789"


def request(origin: str | None = ORIGIN, host: str = "127.0.0.1",
            credential: str | None = None, extra: list[tuple[str, str]] | None = None):
    raw: list[tuple[bytes, bytes]] = []
    if origin is not None:
        raw.append((b"origin", origin.encode()))
    if credential is not None:
        raw.append((b"x-tablet-wall-operator", credential.encode()))
    for key, value in extra or []:
        raw.append((key.encode(), value.encode()))
    return SimpleNamespace(headers=Headers(raw=raw), client=SimpleNamespace(host=host))


def configure(monkeypatch, tmp_path, mode="loopback", **extra):
    monkeypatch.setenv("TABLET_WALL_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", mode)
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    monkeypatch.setenv("TABLET_WALL_OPERATOR_CREDENTIAL", CREDENTIAL)
    for key, value in extra.items():
        monkeypatch.setenv(key, value)
    media.ensure_dirs()


class TestAdmission:
    def test_disabled_denies_every_upload_and_library_read(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="disabled")
        with pytest.raises(media.StoreError) as upload:
            media.admit_upload(request())
        assert upload.value.status == 403
        with pytest.raises(media.StoreError):
            media.admit_library(request(origin=None))

    def test_unknown_mode_denies_and_is_not_treated_as_disabled(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="sometimes")
        with pytest.raises(media.StoreError) as error:
            media.admit_upload(request())
        assert error.value.status == 503

    @pytest.mark.parametrize("mode,status", [("", 403), ("DISABLED", 403), ("bogus", 503)])
    def test_invalid_or_disabled_modes_fail_closed(self, monkeypatch, tmp_path, mode, status):
        configure(monkeypatch, tmp_path, mode=mode)
        with pytest.raises(media.StoreError) as error:
            media.admit_upload(request())
        assert error.value.status == status

    def test_comma_joined_origin_is_refused(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path)
        with pytest.raises(media.StoreError) as error:
            media.admit_upload(request(origin=f"{ORIGIN}, {ORIGIN}"))
        assert error.value.status == 403

    def test_an_enabled_mode_without_an_operator_origin_denies(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="loopback")
        monkeypatch.delenv("TABLET_WALL_OPERATOR_ORIGIN")
        with pytest.raises(media.StoreError) as error:
            media.admit_upload(request())
        assert error.value.status == 503

    def test_missing_null_and_duplicate_origins_are_refused(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path)
        for candidate in (None, "null",
                          [("origin", ORIGIN), ("origin", ORIGIN)]):
            fake = request(origin=candidate) if not isinstance(candidate, list) else request(
                origin=None, extra=candidate
            )
            with pytest.raises(media.StoreError) as error:
                media.admit_upload(fake)
            assert error.value.status == 403

    def test_loopback_requires_the_transport_peer(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="loopback")
        media.admit_upload(request(host="127.0.0.1"))
        media.admit_upload(request(host="::1"))
        with pytest.raises(media.StoreError) as error:
            media.admit_upload(request(host="10.0.0.7"))
        assert error.value.status == 403

    def test_loopback_refuses_forwarded_headers(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="loopback")
        for header in ("x-forwarded-for", "forwarded", "x-forwarded-proto",
                       "x-forwarded-host", "x-forwarded-port", "x-forwarded-anything"):
            with pytest.raises(media.StoreError) as error:
                media.admit_upload(request(extra=[(header, "10.0.0.7")]))
            assert error.value.status == 403

    def test_forged_operator_credential_does_not_bypass_loopback_guards(
        self, monkeypatch, tmp_path
    ):
        configure(monkeypatch, tmp_path, mode="loopback")
        for host, extra in (
            ("10.0.0.7", [("x-tablet-wall-operator", CREDENTIAL)]),
            ("127.0.0.1", [("x-tablet-wall-operator", CREDENTIAL),
                           ("x-forwarded-for", "127.0.0.1")]),
        ):
            with pytest.raises(media.StoreError) as error:
                media.admit_upload(request(host=host, extra=extra))
            assert error.value.status == 403

    def test_proxy_requires_exactly_one_matching_credential(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="proxy")
        media.admit_upload(request(credential=CREDENTIAL, host="10.0.0.7"))
        for raw in ([], [("x-tablet-wall-operator", "wrong")],
                    [("x-tablet-wall-operator", CREDENTIAL),
                     ("x-tablet-wall-operator", CREDENTIAL)]):
            fake = request(origin=ORIGIN, credential=None, host="10.0.0.7", extra=raw)
            with pytest.raises(media.StoreError) as error:
                media.admit_upload(fake)
            assert error.value.status in (403, 503)

    def test_proxy_still_requires_the_exact_origin(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="proxy")
        with pytest.raises(media.StoreError) as error:
            media.admit_upload(request(origin="https://evil.example", credential=CREDENTIAL))
        assert error.value.status == 403

    def test_library_reads_use_the_credential_on_the_proxy_path(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="proxy")
        media.admit_library(request(origin=None, credential=CREDENTIAL, host="10.0.0.7"))
        with pytest.raises(media.StoreError):
            media.admit_library(request(origin=None, host="10.0.0.7"))

    def test_library_reads_allow_a_loopback_get_without_origin(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path, mode="loopback")
        media.admit_library(request(origin=None, host="127.0.0.1"))
        with pytest.raises(media.StoreError):
            media.admit_library(request(origin=None, host="10.0.0.7"))


class TestCapacity:
    def test_quota_and_free_reserve_are_checked_before_and_after(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path)
        (tmp_path / "media" / "objects" / "aa").mkdir()
        (tmp_path / "media" / "objects" / "aa" / "x").write_bytes(b"x" * 100)
        monkeypatch.setattr(media, "QUOTA_BYTES", 150)
        monkeypatch.setattr(media, "FREE_RESERVE_BYTES", 0)
        media.check_capacity(40)
        with pytest.raises(media.StoreError) as error:
            media.check_capacity(60)
        assert error.value.status == 507
        monkeypatch.setattr(media, "FREE_RESERVE_BYTES", 10**18)
        with pytest.raises(media.StoreError):
            media.check_capacity(0)


def test_receive_body_enforces_the_stream_cap_and_cleans_up(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    job = media.new_job()

    async def chunks():
        yield b"a" * 8
        yield b"b" * 8

    total = asyncio.run(media.receive_body(job, chunks(), 16))
    assert total == 16
    assert Path(job.source).read_bytes() == b"a" * 8 + b"b" * 8

    other = media.new_job()
    monkeypatch.setattr(media, "MAX_SOURCE_BYTES", 10)

    async def too_much():
        yield b"x" * 9
        yield b"x" * 9

    with pytest.raises(media.StoreError) as error:
        asyncio.run(media.receive_body(other, too_much(), None))
    assert error.value.status == 413
    assert not Path(other.directory).exists()


def test_receive_body_rejects_empty_and_mismatched_lengths(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    for payload, declared, status in ((b"", None, 400), (b"abc", 4, 400), (b"abc", None, 0)):
        job = media.new_job()

        async def chunks(data=payload):
            if data:
                yield data

        if status:
            with pytest.raises(media.StoreError) as error:
                asyncio.run(media.receive_body(job, chunks(), declared))
            assert error.value.status == status
            assert not Path(job.directory).exists()
        else:
            assert asyncio.run(media.receive_body(job, chunks(), declared)) == 3


def _synthetic_job(tmp_path) -> tuple[media.Job, dict]:
    job = media.new_job()
    objects = []
    for role in media.TRUE_ROLES:
        data = f"object:{role}:v1".encode()
        digest = hashlib.sha256(data).hexdigest()
        filename = f"{digest}.jpg"
        (Path(job.directory) / filename).write_bytes(data)
        objects.append({
            "role": role, "filename": filename, "sha256": digest,
            "bytes": len(data), "width": 100, "height": 50, "mime": "image/jpeg",
        })
    return job, {"ok": True, "pipeline_version": 1, "objects": objects}


class TestPublication:
    def test_publish_commits_ready_rows_and_serves_exact_bytes(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path)
        job, result = _synthetic_job(tmp_path)
        descriptor = media.publish(job, result, "phone.jpg")
        assert descriptor["state"] == "ready"
        assert descriptor["name"] == "phone.jpg"
        display = descriptor["id"]
        fetched = media.fetch_object(display)
        assert fetched is not None
        assert fetched[0] == f"object:display:v1".encode()
        assert media.fetch_object("sha256:" + "0" * 64) is None
        assert not Path(job.directory).exists()
        assert media.verify_integrity() == []

    def test_a_hash_mismatch_is_never_published(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path)
        job, result = _synthetic_job(tmp_path)
        result["objects"][0]["sha256"] = "0" * 64
        with pytest.raises(media.StoreError) as error:
            media.publish(job, result, "bad.jpg")
        assert error.value.status == 422
        assert not Path(job.directory).exists()

    def test_a_tampered_object_is_reported_and_not_served(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path)
        job, result = _synthetic_job(tmp_path)
        descriptor = media.publish(job, result, "phone.jpg")
        rows = media.find_object(descriptor["id"])
        assert rows is not None
        target = tmp_path / "media" / rows["path"]
        target.write_bytes(b"changed")
        assert media.fetch_object(descriptor["id"]) is None
        problems = media.verify_integrity()
        assert problems and problems[0]["object_id"] == descriptor["id"]

    def test_an_unready_asset_is_not_listed(self, monkeypatch, tmp_path):
        configure(monkeypatch, tmp_path)
        job, result = _synthetic_job(tmp_path)
        descriptor = media.publish(job, result, "phone.jpg")
        assert [entry["asset_id"] for entry in media.list_assets()] == [descriptor["asset_id"]]
        with persist._connection() as connection:
            connection.execute(
                "UPDATE media_assets SET state = 'unavailable' WHERE asset_id = ?",
                (descriptor["asset_id"],),
            )
        assert media.list_assets() == []
        assert media.find_object(descriptor["id"]) is None

    def test_stale_staging_is_removed_only_under_the_staging_directory(
        self, monkeypatch, tmp_path
    ):
        configure(monkeypatch, tmp_path)
        job = media.new_job()
        keep = tmp_path / "media" / "objects" / "keep"
        keep.mkdir()
        (keep / "x").write_bytes(b"x")
        os.utime(job.directory, (0, 0))
        assert media.cleanup_staging(max_age_s=1) == 1
        assert not Path(job.directory).exists()
        assert keep.exists()
