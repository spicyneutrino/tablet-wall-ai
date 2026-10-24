"""Ranged, conditional serving for published video objects (R4).

Starlette 1.6.0's ``FileResponse`` already answers GET and HEAD, 200 and 206,
open and suffix ranges, ``Content-Range``/``Content-Length``, ``Accept-Ranges``,
``416`` with ``Content-Range: bytes */size``, and ``If-Range`` against its
ETag or Last-Modified. ``tests/test_video_serving.py`` pins each of those. This
module adds only what the framework gets wrong for a content-addressed,
immutable object:

- a strong ETag from the object's sha256, passed in so a restore that rewrites
  the file's mtime does not invalidate a client's cached validator or an
  in-flight ``If-Range``;
- ``304`` for ``If-None-Match``, which ``FileResponse`` ignores;
- a multirange count of 4 instead of 100, with a larger request falling back
  to the whole file, and a ``431`` for an oversized ``Range`` header;
- a malformed ``Range`` (reversed, garbage, non-bytes unit) ignored and
  answered ``200``, as RFC 9110 section 14.2 requires, instead of ``400``.

A mixed multirange with one start past the end is still ``416`` as a whole,
which is stricter than the RFC but harmless for browsers, which send one range.
"""

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import FileResponse, MalformedRangeHeader, Response

from tabletwall.media import VideoFile

MAX_RANGE_HEADER_BYTES = 256
MAX_RANGES = 4
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


class _BoundedFileResponse(FileResponse):
    max_ranges = MAX_RANGES

    @classmethod
    def _parse_range_header(cls, http_range: str, file_size: int) -> list[tuple[int, int]]:
        try:
            return super()._parse_range_header(http_range, file_size)
        except MalformedRangeHeader:
            return []


def _matches(if_none_match: str, etag: str) -> bool:
    candidates = [part.strip() for part in if_none_match.split(",")]
    if "*" in candidates:
        return True
    strong = etag.strip('"')
    return any(part.removeprefix("W/").strip('"') == strong for part in candidates)


def video_response(request: Request, video: VideoFile) -> Response:
    """Serve ``video`` for a GET or HEAD, honouring ranges and validators."""
    headers = {
        "ETag": video.etag,
        "Cache-Control": IMMUTABLE_CACHE,
        "X-Content-Type-Options": "nosniff",
    }
    incoming = Headers(scope=request.scope)
    if len(incoming.get("range", "")) > MAX_RANGE_HEADER_BYTES:
        return Response(status_code=431, content="Range header too large", media_type="text/plain")
    if_none_match = incoming.get("if-none-match")
    if if_none_match and _matches(if_none_match, video.etag):
        return Response(status_code=304, headers=headers)
    return _BoundedFileResponse(
        video.path, media_type=video.mime, headers=headers, stat_result=video.stat
    )
