"""The operator's unified, content-addressed still-image inventory."""

from typing import Literal, TypedDict

from tabletwall import assets, media


class OperatorImage(TypedDict):
    id: str
    name: str
    width: int
    height: int
    url: str
    thumbnail_url: str
    source: Literal["curated", "managed"]


def list_images() -> list[OperatorImage]:
    """Prefer managed metadata on duplicate IDs, as scene resolution does."""
    images: dict[str, OperatorImage] = {}
    for entry in media.list_assets():
        if entry.get("kind", "image") != "image":
            continue
        thumbnail = entry["thumbnail"]
        images.setdefault(entry["id"], {
            "id": entry["id"],
            "name": entry["name"],
            "width": entry["intrinsicWidth"],
            "height": entry["intrinsicHeight"],
            "url": entry["url"],
            "thumbnail_url": thumbnail["url"] if thumbnail else entry["url"],
            "source": "managed",
        })
    for entry in assets.list_assets():
        images.setdefault(entry["id"], {
            "id": entry["id"],
            "name": entry["name"],
            "width": entry["intrinsicWidth"],
            "height": entry["intrinsicHeight"],
            "url": entry["url"],
            "thumbnail_url": entry["url"],
            "source": "curated",
        })
    return sorted(images.values(), key=lambda image: (image["name"].casefold(), image["id"]))
