from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, UUID4

devices = {}

class DeviceRegistration(BaseModel):
    device_id: UUID4
    width: int
    height: int
    device_type: str


app = FastAPI()

app.mount(
    "/client",
    StaticFiles(directory="frontend/client", html=True),
    name="client"
)

app.mount(
    "/controller",
    StaticFiles(directory="frontend/controller", html=True),
    name="controller"
)

@app.get("/device/{device_id}")
async def get_device(device_id:UUID4):
    return {"return_id": device_id}

# @app.get("/devices/register")
# async def device_register(device: DeviceRegistration):
#     print(device.device_id)
#     print(device.device_type)
#     print(device.height)
#     print(device.width)
    
#     return {
#         "registered": True,
#         "device": device.device_id
#     }

@app.get("/devices/register")
async def registration_info():
    return {"message": "Use POST to register a device"}
    
@app.post("/devices/register")
async def device_register(device: DeviceRegistration):
    
    device_id = str(device.device_id)
    
    devices[device_id] = {
        "width": device.width,
        "height": device.height,
        "type": device.device_type,
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }
    
    return {
        "registered": True,
        "device": device_id
    }

@app.post("/devices/{device_id}/color")
async def change_color(device_id: UUID4):
    ...

@app.get("/devices")
async def get_devices():
    return devices

@app.get("/")
async def root():
    return {
        "message": "Hello Tablet Wall"
    }
