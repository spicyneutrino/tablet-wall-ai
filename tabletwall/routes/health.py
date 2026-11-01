"""Operator readiness, ``/healthz`` and the join QR image.

The router is created with the readers it needs, so this module never imports
``main``: the application hands it a live-state snapshot, the environment
configuration, and an asset resolver. All three routes use
``media.admit_operator_read``,
which is independent of upload admission and refuses the tablet listener's
transport and forwarded headers. The QR is a convenience for the operator's
own controller page, not device pairing, and it encodes no credential.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import segno
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from tabletwall import media, operability

NO_STORE = {"Cache-Control": "no-store"}


def _store_error(error: media.StoreError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"detail": error.message},
        headers=NO_STORE,
    )


def create_router(
    read_state: Callable[[], operability.WallSnapshot] = operability.live_snapshot,
    read_config: Callable[[], operability.Config] = operability.read_config,
    resolve_asset: Callable[[str], bool] = operability.asset_available,
) -> APIRouter:
    """Build the operator routes around the injected state and config readers."""
    router = APIRouter()

    def admitted(request: Request) -> JSONResponse | None:
        try:
            media.admit_operator_read(request)
        except media.StoreError as error:
            return _store_error(error)
        return None

    @router.get("/healthz")
    def healthz(request: Request) -> JSONResponse:
        denied = admitted(request)
        if denied is not None:
            return denied
        try:
            snapshot = read_state()
        except Exception:  # noqa: BLE001 - a health read must answer, not 500
            return JSONResponse(
                status_code=503,
                content={"ready": False, "error": "live state is unavailable"},
                headers=NO_STORE,
            )
        body = operability.health(snapshot)
        return JSONResponse(
            status_code=200 if body["ready"] else 503,
            content=body,
            headers=NO_STORE,
        )

    @router.get("/api/v3/readiness")
    def readiness(request: Request) -> JSONResponse:
        denied = admitted(request)
        if denied is not None:
            return denied
        snapshot: operability.WallSnapshot | None
        error: str | None = None
        try:
            snapshot = read_state()
        except Exception:  # noqa: BLE001 - report the gap instead of a bare 500
            snapshot = None
            error = "live state is unavailable"
        body: dict[str, Any] = operability.readiness(
            snapshot, read_config(), resolve_asset, error
        )
        return JSONResponse(content=body, headers=NO_STORE)

    @router.get("/api/v3/join-qr")
    def join_qr(request: Request) -> Response:
        denied = admitted(request)
        if denied is not None:
            return denied
        config = read_config()
        if config.tablet_origin is None:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": operability.TABLET_ORIGIN_ENV + " is not configured, "
                    "so there is no tablet URL to encode"
                },
                headers=NO_STORE,
            )
        join_url = f"{config.tablet_origin}/client/"
        png = io.BytesIO()
        segno.make(join_url, error="m").save(png, kind="png", scale=8, border=4)
        return Response(
            content=png.getvalue(),
            media_type="image/png",
            headers={
                **NO_STORE,
                "Content-Disposition": 'inline; filename="tablet-wall-join.png"',
            },
        )

    return router
