"""Read-only device registry HTTP routes."""

from fastapi import APIRouter, HTTPException

from tabletwall.protocol import _parse_device_id
from tabletwall.state import _device_record, devices

router = APIRouter()


@router.get("/device/{device_id}")
async def get_device(device_id: str):
    key = _parse_device_id(device_id)
    if key is None or key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")
    return _device_record(key)


@router.get("/devices/register")
async def registration_info():
    return {"message": "Use POST to register a device"}


@router.get("/devices")
async def get_devices():
    return {device_id: _device_record(device_id) for device_id in list(devices)}


@router.get("/")
async def root():
    return {
        "message": "Hello Tablet Wall"
    }
