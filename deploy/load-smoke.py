"""Exercise 20 mixed-size tablet connections through the tablet ingress.

This is a short connectivity/concurrency probe, NOT a substitute for physical
tablet, radio-capacity, render-seam, or long-running soak tests. It registers
temporary UUIDs and leaves them in the in-memory roster until the app restarts.
Run with ``uv run python deploy/load-smoke.py --tablet-origin ... --ca-cert ...``.
"""

import argparse
import asyncio
import json
import ssl
import time
import uuid
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

import websockets


def fetch(url: str, context: ssl.SSLContext, body: dict | None = None) -> bytes:
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    with opener.open(request, timeout=15) as response:
        return response.read()


async def device(
    index: int, origin: str, context: ssl.SSLContext, barrier: asyncio.Barrier
) -> float:
    device_id = str(uuid.uuid4())
    width, height = ((1024, 768), (800, 1280), (1920, 1080), (1280, 800))[index % 4]
    started = time.perf_counter()
    result = await asyncio.to_thread(
        fetch,
        origin + "/devices/register",
        context,
        {
            "device_id": device_id,
            "width": width,
            "height": height,
            "device_type": "test-tablet",
        },
    )
    assert json.loads(result)["device"] == device_id

    socket_url = "wss://" + urlsplit(origin).netloc + "/ws/device?device_id=" + device_id + "&protocol=2&caps=image,calibration"
    async with websockets.connect(
        socket_url, ssl=context, origin=origin, proxy=None, open_timeout=15
    ) as socket:
        welcome = json.loads(await asyncio.wait_for(socket.recv(), 15))
        wall = json.loads(await asyncio.wait_for(socket.recv(), 15))
        assert welcome["type"] == "welcome" and welcome["device_id"] == device_id
        assert wall["type"] == "wall" and "generation" in wall
        # Hold every socket open until all have received a wall; otherwise a
        # sequence of fast individual handshakes is not an N-device trial.
        await barrier.wait()
        await asyncio.sleep(2)
    return time.perf_counter() - started


async def asset(origin: str, asset_id: str, context: ssl.SSLContext) -> float:
    started = time.perf_counter()
    data = await asyncio.to_thread(fetch, origin + "/assets/" + asset_id, context)
    assert data, "Curated asset response is empty"
    return time.perf_counter() - started


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tablet-origin", required=True, help="https://<hotspot-ip>:8443")
    parser.add_argument("--ca-cert", required=True, help="Caddy local CA's public root.crt")
    parser.add_argument("--devices", type=int, default=20)
    parser.add_argument("--asset-id", help="Optional real sha256:<64 lowercase hex> to GET in parallel")
    args = parser.parse_args()
    origin = args.tablet_origin.rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.path
        or parsed.query or parsed.fragment or parsed.username or parsed.password
    ):
        parser.error("--tablet-origin must be an HTTPS origin without a path")
    if not 1 <= args.devices <= 100:
        parser.error("--devices must be between 1 and 100")
    if args.asset_id and (
        not args.asset_id.startswith("sha256:")
        or len(args.asset_id) != 71
        or any(ch not in "0123456789abcdef" for ch in args.asset_id[7:])
    ):
        parser.error("--asset-id must be sha256:<64 lowercase hex>")
    context = ssl.create_default_context(cafile=args.ca_cert)

    barrier = asyncio.Barrier(args.devices)
    timings = await asyncio.wait_for(
        asyncio.gather(
            *(device(index, origin, context, barrier) for index in range(args.devices))
        ),
        timeout=60,
    )
    print(f"{args.devices} concurrent registrations and device WS handshakes: "
          f"max {max(timings):.2f}s")
    if args.asset_id:
        timings = await asyncio.gather(
            *(asset(origin, args.asset_id, context) for _ in range(args.devices))
        )
        print(f"{args.devices} concurrent curated image reads: "
              f"max {max(timings):.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
