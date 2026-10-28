"""Curated and managed asset inventory and byte serving."""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from tabletwall import assets, media, media_serve
from tabletwall.protocol import _is_asset_id

router = APIRouter()


@router.get("/assets")
def get_assets():
    """The curated inventory: ``{"assets": [<entry>, …]}`` with each entry
    carrying ID, display name, MIME type, intrinsic dimensions, byte size,
    and the same-origin URL the asset is served from.

    Wrapped in an object rather than a bare array so the payload can grow
    metadata later without breaking readers. ``Cache-Control: no-store`` is
    part of the contract: the inventory is a snapshot of a directory that
    changes by files being copied in, so a browser must re-read it on every
    refresh instead of answering from a cached copy.

    Sync rather than async on purpose: this re-scans, re-hashes, and now
    validates current bytes, reusing decoded facts by content hash, and Starlette runs a plain
    ``def`` route in a worker thread, so the event loop — which is also
    pushing heartbeats — never waits on the filesystem. The re-scan itself is
    the contract: inventory refreshes on request.
    """
    return JSONResponse(
        content={"assets": assets.list_assets()},
        headers={"Cache-Control": "no-store"},
    )


@router.api_route("/assets/{asset_id}", methods=["GET", "HEAD"])
def get_asset(asset_id: str, request: Request):
    """Serve one asset's bytes, and only when they still hash to that ID.

    Managed uploads are checked first through the indexed media store, so a
    ready upload avoids re-scanning the curated directory entirely. Curated
    bytes remain the fallback. Unknown, malformed, removed, and replaced IDs
    are all ``404``: because the ID *is* the hash of the validated bytes,
    re-hashing what was just read proves this response is exactly those bytes.
    The bytes are content-addressed, hence cached as immutable; ``nosniff``
    keeps a browser from second-guessing the declared image type.

    A published video is the one object that is not buffered: it is streamed
    with byte ranges and a strong ETag (``tabletwall.media_serve``), after its
    hash has been checked once for the file's identity.
    """
    if _is_asset_id(asset_id):
        file = media.open_video(asset_id)
        if file is not None:
            return media_serve.video_response(request, file)
    managed = media.fetch_object(asset_id)
    if managed is not None:
        data, mime = managed
    else:
        served = assets.fetch(asset_id)
        if served is None:
            raise HTTPException(status_code=404, detail="Unknown asset")
        asset, data = served
        mime = asset.mime
    return Response(
        content=data,
        media_type=mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
