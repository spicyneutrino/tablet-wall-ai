"""Prospective ruler arithmetic, admitted independently of uploads.

Mount ``create_router()`` on the main app so its POST also uses the existing
operator-origin middleware. This route never writes a profile or calibration.
"""

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tabletwall import displays, media
from tabletwall.calibration_health import CalibrationHealthError, check_ruler_scale

NO_STORE = {"Cache-Control": "no-store"}


class RulerCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    device_id: str
    profile_revision: int = Field(ge=1)
    quarter_turn: int = Field(ge=0, le=3)
    axis: Literal["x", "y"]
    span_px: float
    span_mm: float
    span_error_mm: float
    usable_width_px: float
    usable_height_px: float


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/v3/calibration-check")
    async def calibration_check(request: Request) -> JSONResponse:
        try:
            media.admit_operator_read(request)
        except media.StoreError as error:
            return JSONResponse(status_code=error.status,
                                content={"detail": error.message}, headers=NO_STORE)
        try:
            command = RulerCheck.model_validate(await request.json())
        except ValidationError as error:
            return JSONResponse(status_code=422, content={"detail": error.errors(
                include_input=False, include_context=False, include_url=False)}, headers=NO_STORE)
        except (ValueError, OverflowError):
            return JSONResponse(status_code=422,
                                content={"detail": "The ruler check requires a valid JSON object."},
                                headers=NO_STORE)
        try:
            device_id = displays._device(command.device_id)
            profile = displays.profile(device_id, command.profile_revision)
            if profile is None:
                return JSONResponse(status_code=404,
                                    content={"detail": "The selected profile revision does not exist."},
                                    headers=NO_STORE)
            width = profile["active_width_mm"]
            height = profile["active_height_mm"]
            swapped = command.quarter_turn % 2 == 1
            result = check_ruler_scale(
                span_px=command.span_px, span_mm=command.span_mm,
                span_error_mm=command.span_error_mm, axis=command.axis,
                usable_width_px=command.usable_width_px,
                usable_height_px=command.usable_height_px,
                supplied_width_mm=height if swapped else width,
                supplied_height_mm=width if swapped else height,
            )
        except (displays.DisplayError, CalibrationHealthError) as error:
            return JSONResponse(status_code=422, content={"detail": str(error)}, headers=NO_STORE)
        result["profile"] = {
            "device_id": device_id, "revision": profile["revision"],
            "active_width_mm": width, "active_height_mm": height,
            "quarter_turn": command.quarter_turn,
            "native_axis": ("height" if swapped else "width") if command.axis == "x"
            else ("width" if swapped else "height"),
        }
        return JSONResponse(content=result, headers=NO_STORE)

    return router
