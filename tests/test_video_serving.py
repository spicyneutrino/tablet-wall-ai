"""Serving published video: ranges, validators, bounds, and refusal (R4).

The first block pins what Starlette 1.6.0's ``FileResponse`` does by itself on
the real ``/assets/{id}`` route, so a framework upgrade that changes it fails
here instead of on a tablet. The second block covers the gaps
``tabletwall.media_serve`` fills.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import tabletwall.media as media
from video_fixtures import fabricate_video

SIZE = 12 * 1024 * 1024  # larger than the 10 MiB still-object ceiling on purpose


@pytest.fixture
def served(client):
    descriptor = fabricate_video(SIZE)
    path = os.path.join(media.media_dir(), media.find_servable(descriptor["id"])["path"])
    with open(path, "rb") as handle:
        data = handle.read()
    return client, descriptor, data


def test_full_get_streams_the_whole_object_with_the_headers_a_player_needs(served):
    client, descriptor, data = served
    response = client.get(descriptor["url"])
    assert response.status_code == 200
    assert response.content == data
    assert "sha256:" + hashlib.sha256(response.content).hexdigest() == descriptor["id"]
    headers = response.headers
    assert headers["content-type"] == "video/mp4"
    assert headers["content-length"] == str(SIZE)
    assert headers["accept-ranges"] == "bytes"
    assert headers["etag"] == '"' + descriptor["id"].split(":")[1] + '"'
    assert headers["last-modified"]
    assert headers["cache-control"] == "public, max-age=31536000, immutable"
    assert headers["x-content-type-options"] == "nosniff"


def test_head_matches_get_headers_with_no_body(served):
    client, descriptor, _data = served
    get = client.get(descriptor["url"])
    head = client.head(descriptor["url"])
    assert head.status_code == 200
    assert head.content == b""
    for name in ("content-length", "content-type", "accept-ranges", "etag", "last-modified"):
        assert head.headers[name] == get.headers[name]


@pytest.mark.parametrize(
    ("header", "first", "last"),
    [
        ("bytes=0-99", 0, 99),
        ("bytes=0-0", 0, 0),
        ("bytes=5000000-5000099", 5_000_000, 5_000_099),
        ("bytes=12582800-", SIZE - 112, SIZE - 1),  # open-ended
        ("bytes=-100", SIZE - 100, SIZE - 1),  # suffix
        ("bytes=-99999999999", 0, SIZE - 1),  # suffix longer than the file
        ("bytes=12582000-99999999999", 12_582_000, SIZE - 1),  # end clamped
    ],
)
def test_single_ranges_answer_206_with_exact_content_range(served, header, first, last):
    client, descriptor, data = served
    response = client.get(descriptor["url"], headers={"Range": header})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes {first}-{last}/{SIZE}"
    assert response.headers["content-length"] == str(last - first + 1)
    assert response.content == data[first : last + 1]
    assert response.headers["etag"]
    assert response.headers["accept-ranges"] == "bytes"


def test_head_with_a_range_reports_the_part_without_a_body(served):
    client, descriptor, _data = served
    response = client.head(descriptor["url"], headers={"Range": "bytes=10-19"})
    assert response.status_code == 206
    assert response.content == b""
    assert response.headers["content-range"] == f"bytes 10-19/{SIZE}"
    assert response.headers["content-length"] == "10"


@pytest.mark.parametrize("header", [f"bytes={SIZE}-", f"bytes={SIZE + 5}-", "bytes=-0"])
def test_an_unsatisfiable_range_is_416_with_the_size(served, header):
    client, descriptor, _data = served
    response = client.get(descriptor["url"], headers={"Range": header})
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{SIZE}"
    assert response.content == b""


def test_if_range_with_the_current_validator_keeps_the_range(served):
    client, descriptor, data = served
    full = client.get(descriptor["url"])
    for validator in (full.headers["etag"], full.headers["last-modified"]):
        response = client.get(descriptor["url"], headers={"Range": "bytes=0-9", "If-Range": validator})
        assert response.status_code == 206
        assert response.content == data[:10]


def test_if_range_with_a_stale_validator_returns_the_whole_object(served):
    client, descriptor, data = served
    response = client.get(
        descriptor["url"], headers={"Range": "bytes=0-9", "If-Range": '"0123456789abcdef"'}
    )
    assert response.status_code == 200
    assert len(response.content) == SIZE


def test_if_none_match_revalidates_with_304_and_no_body(served):
    client, descriptor, _data = served
    etag = client.get(descriptor["url"]).headers["etag"]
    for header in (etag, "*", f"W/{etag}", f'"nope", {etag}'):
        response = client.get(descriptor["url"], headers={"If-None-Match": header})
        assert response.status_code == 304, header
        assert response.content == b""
        assert response.headers["etag"] == etag
        assert "immutable" in response.headers["cache-control"]
    assert client.get(descriptor["url"], headers={"If-None-Match": '"other"'}).status_code == 200
    # Validators are evaluated before the Range header (RFC 9110 section 13.2.2).
    both = client.get(descriptor["url"], headers={"If-None-Match": etag, "Range": "bytes=0-9"})
    assert both.status_code == 304


def test_multirange_is_bounded(served):
    client, descriptor, data = served
    two = client.get(descriptor["url"], headers={"Range": "bytes=0-1,10-11"})
    assert two.status_code == 206
    assert two.headers["content-type"].startswith("multipart/byteranges")
    assert data[0:2] in two.content and data[10:12] in two.content

    five = "bytes=" + ",".join(f"{i * 10}-{i * 10 + 1}" for i in range(5))
    over = client.get(descriptor["url"], headers={"Range": five})
    assert over.status_code == 200
    assert len(over.content) == SIZE

    huge = client.get(descriptor["url"], headers={"Range": "bytes=" + "0-1," * 100 + "5-6"})
    assert huge.status_code == 431


@pytest.mark.parametrize("header", ["bytes=10-5", "items=0-1", "bytes=abc", "bytes=", "garbage"])
def test_a_malformed_range_is_ignored_not_an_error(served, header):
    client, descriptor, _data = served
    response = client.get(descriptor["url"], headers={"Range": header})
    assert response.status_code == 200
    assert len(response.content) == SIZE


def test_the_etag_is_the_content_hash_so_a_rewritten_mtime_keeps_it(served):
    client, descriptor, _data = served
    before = client.get(descriptor["url"], headers={"Range": "bytes=0-0"}).headers
    path = os.path.join(media.media_dir(), media.find_servable(descriptor["id"])["path"])
    os.utime(path, (1_000_000_000, 1_000_000_000))
    after = client.get(descriptor["url"], headers={"Range": "bytes=0-0", "If-Range": before["etag"]})
    assert after.headers["etag"] == before["etag"]
    assert after.status_code == 206
    assert after.headers["last-modified"] != before["last-modified"]


def test_the_poster_is_an_ordinary_cached_image_not_a_ranged_video(served):
    client, descriptor, _data = served
    poster = client.get(descriptor["poster"]["url"])
    assert poster.status_code == 200
    assert poster.headers["content-type"] == "image/jpeg"
    assert poster.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "accept-ranges" not in poster.headers


def test_a_tampered_object_is_never_served_and_the_cache_does_not_hide_it(served):
    client, descriptor, data = served
    assert client.get(descriptor["url"], headers={"Range": "bytes=0-9"}).status_code == 206
    path = os.path.join(media.media_dir(), media.find_servable(descriptor["id"])["path"])
    with open(path, "r+b") as handle:
        handle.seek(1000)
        handle.write(bytes([data[1000] ^ 0xFF]))
    assert client.get(descriptor["url"], headers={"Range": "bytes=0-9"}).status_code == 404
    assert client.get(descriptor["url"]).status_code == 404
    assert client.head(descriptor["url"]).status_code == 404


def test_a_truncated_missing_or_symlinked_object_is_404(served, tmp_path):
    client, descriptor, data = served
    path = os.path.join(media.media_dir(), media.find_servable(descriptor["id"])["path"])
    decoy = tmp_path / "decoy.bin"
    decoy.write_bytes(data)
    os.rename(path, path + ".kept")
    os.symlink(decoy, path)
    assert client.get(descriptor["url"]).status_code == 404
    os.unlink(path)
    assert client.get(descriptor["url"]).status_code == 404
    with open(path, "wb") as handle:
        handle.write(data[: SIZE // 2])
    assert client.get(descriptor["url"]).status_code == 404


def test_unknown_malformed_and_unready_ids_are_404(client):
    descriptor = fabricate_video(1024 * 1024)
    assert client.get("/assets/sha256:" + "0" * 64).status_code == 404
    assert client.get("/assets/not-an-id").status_code == 404
    assert client.get(descriptor["url"]).status_code == 200
    import tabletwall.persist as persist

    with persist._connection() as connection:
        connection.execute("UPDATE media_assets SET state = 'unavailable'")
    assert client.get(descriptor["url"], headers={"Range": "bytes=0-1"}).status_code == 404


def test_stills_keep_their_whole_body_behaviour_and_gain_head(client):
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="JPEG")
    digest = hashlib.sha256(buffer.getvalue()).hexdigest()
    curated = os.environ["TABLET_WALL_ASSET_DIR"]
    os.makedirs(curated, exist_ok=True)
    with open(os.path.join(curated, f"{digest}.jpg"), "wb") as handle:
        handle.write(buffer.getvalue())
    url = f"/assets/sha256:{digest}"
    get = client.get(url)
    assert get.status_code == 200 and get.content == buffer.getvalue()
    assert get.headers["content-type"] == "image/jpeg"
    assert "accept-ranges" not in get.headers
    assert client.head(url).status_code == 200


def test_the_server_process_never_loads_the_decoder_worker():
    """Importing the worker would install Pillow's global warning policy server-wide."""
    code = (
        "import sys, warnings, main; "
        "assert 'tabletwall.media_worker' not in sys.modules; "
        "assert 'tabletwall.video' not in sys.modules; "
        "assert not any('DecompressionBomb' in getattr(f[2], '__name__', '') for f in warnings.filters)"
    )
    subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], check=True)
