"""Small REST client for the incidental operator setup in browser drivers.

The old ``/controller/physical.html`` page is only a way to reach the rig's
HTTP API. Drivers that used it to place tablets, choose content or drive
playback can call the same endpoints directly. The operator Origin is sent on
every request, and guarded writes take a fresh config ETag from GET
/api/v3/config, exactly as the operator console does.

This module never opens a browser and never inspects a tablet. Tablet-side and
server-side evidence stays in the drivers that own it.
"""

from __future__ import annotations

from typing import Any

import httpx


class Api:
    """A rig REST client with the operator Origin and config ETag handling."""

    def __init__(self, base: str, *, http: httpx.Client | None = None, timeout: float = 30.0):
        self.base = base
        self.http = http if http is not None else httpx.Client(
            base_url=base, headers={"Origin": base}, timeout=timeout
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> Api:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def config(self) -> dict[str, Any]:
        response = self.http.get("/api/v3/config")
        response.raise_for_status()
        return response.json()

    def etag(self) -> str:
        return self.config()["etag"]

    def get(self, path: str) -> httpx.Response:
        return self.http.get(path)

    def guarded(self, method: str, path: str, body: dict[str, Any] | None = None,
                etag: str | None = None) -> httpx.Response:
        """Send a config-guarded write with a fresh If-Match when none is given."""
        headers = {"If-Match": etag if etag is not None else self.etag()}
        return self.http.request(method, path, json=body, headers=headers)

    def put(self, path: str, body: dict[str, Any], etag: str | None = None) -> httpx.Response:
        return self.guarded("PUT", path, body, etag)

    def post(self, path: str, body: dict[str, Any] | None = None,
             etag: str | None = None, guarded: bool = False) -> httpx.Response:
        return self.guarded("POST", path, body, etag) if guarded else self.http.post(path, json=body)

    def place_logical(self, columns: int, rows: int, device_ids: list[str],
                      *, cell_width: int = 800, cell_height: int = 450,
                      etag: str | None = None) -> httpx.Response:
        if columns < 1 or rows < 1 or len(device_ids) > columns * rows:
            raise ValueError("Logical grid needs positive dimensions and enough cells")
        placements = {
            device_id: {
                "device_id": device_id,
                "x": (index % columns) * cell_width,
                "y": (index // columns) * cell_height,
                "w": cell_width,
                "h": cell_height,
                "bezel": {"left": 0, "right": 0, "top": 0, "bottom": 0},
            }
            for index, device_id in enumerate(device_ids)
        }
        return self.put("/api/v3/logical-layout", {
            "width": columns * cell_width,
            "height": rows * cell_height,
            "placements": placements,
            "sizing": {"mode": "fixed", "padding": 0},
        }, etag)

    def place_physical(self, layout: dict[str, Any],
                       etag: str | None = None) -> httpx.Response:
        return self.put("/api/v3/layout", layout, etag)

    def scene(self, content: dict[str, Any], etag: str | None = None) -> httpx.Response:
        return self.put("/api/v3/scene", {"content": content}, etag)

    def test_pattern(self, pattern: str, etag: str | None = None) -> httpx.Response:
        return self.post("/api/v3/test-pattern", {"pattern": pattern}, etag, guarded=True)

    def color(self, color: str, device_id: str | None = None) -> httpx.Response:
        path = f"/devices/{device_id}/color" if device_id else "/devices/color"
        return self.http.post(path, json={"color": color})

    def identify(self, device_id: str, *, duration_ms: int = 5000,
                 etag: str | None = None) -> httpx.Response:
        return self.post(f"/api/v3/devices/{device_id}/identify",
                         {"duration_ms": duration_ms}, etag, guarded=True)

    def placement(self, device_id: str, rect: dict[str, Any]) -> httpx.Response:
        return self.http.put(f"/devices/{device_id}/placement", json=rect)

    def rebind(self, new_id: str, *, replaces: str, number: int | None = None,
               hardware: str = "same_hardware", active: bool = True) -> tuple[httpx.Response, httpx.Response]:
        """Preview then apply a rebind, moving placement and number to a new id."""
        body: dict[str, Any] = {
            "replaces": replaces,
            "hardware": hardware,
            "active": active,
            "saved_layouts": [],
            "transfer_label": True,
        }
        if number is not None:
            body["number"] = number
        preview_response = self.post(f"/api/v3/devices/{new_id}/rebind/preview",
                                     body, self.etag(), guarded=True)
        preview_response.raise_for_status()
        preview = preview_response.json()
        apply_body = {**body, "new_connection_id": preview.get("new_connection_id")}
        apply_response = self.post(f"/api/v3/devices/{new_id}/rebind", apply_body,
                                   preview.get("base_etag") or preview.get("etag"),
                                   guarded=True)
        return preview_response, apply_response

    def grid(self, command: dict[str, Any]) -> tuple[httpx.Response, httpx.Response]:
        """Preview then apply a grid, sending the preview's connection guards."""
        preview_response = self.post("/api/v3/grid/preview", command, self.etag(), guarded=True)
        preview_response.raise_for_status()
        preview = preview_response.json()
        apply_response = self.post("/api/v3/grid", {**command, "guards": preview["guards"]},
                                   preview["base_etag"], guarded=True)
        return preview_response, apply_response

    def playlist(self, items: list[dict[str, Any]], *, loop: bool = False) -> httpx.Response:
        response = self.http.get("/api/v3/playlist")
        response.raise_for_status()
        etag = response.json()["etag"]
        return self.http.put("/api/v3/playlist", json={"items": items, "loop": loop},
                             headers={"If-Match": etag})

    def playback_start(self, policy: str | None = None) -> httpx.Response:
        body = {"policy": policy} if policy else None
        return self.http.post("/api/v3/playback/start", json=body)

    def playback_stop(self) -> httpx.Response:
        version = self.http.get("/api/v3/playback").json()["version"]
        return self.http.post("/api/v3/playback/stop",
                              headers={"If-Match": str(version)})

    def diagnostics(self, *, verify: bool = False) -> httpx.Response:
        return self.http.get("/diagnostics?verify=1" if verify else "/diagnostics")


def client(base: str, *, timeout: float = 30.0) -> httpx.Client:
    """Return an httpx client with the operator Origin, for drivers that need raw calls."""
    return httpx.Client(base_url=base, headers={"Origin": base}, timeout=timeout)
