"""Browser viewport CSS-pixel geometry reported by the slide component."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class ViewportBBox:
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if self.x1 >= self.x2 or self.y1 >= self.y2:
            raise ValueError("ViewportBBox requires x1 < x2 and y1 < y2.")


@dataclass(frozen=True)
class SlideViewportGeometry:
    deck_id: str
    slide_id: int
    layout_revision: int
    received_at: float
    viewport_width: float
    viewport_height: float
    device_pixel_ratio: float
    slide_rect: ViewportBBox
    aoi_rects: dict[str, ViewportBBox]


def parse_component_geometry(
    payload: Mapping[str, Any],
    *,
    received_at: float,
) -> SlideViewportGeometry:
    """Validate component geometry and stamp it with the server clock."""

    if not isinstance(payload, Mapping):
        raise ValueError("Component geometry must be an object.")
    deck_id = str(payload.get("deck_id", "")).strip()
    if not deck_id:
        raise ValueError("Component geometry requires a deck ID.")
    viewport_width = _number(payload, "viewport_width")
    viewport_height = _number(payload, "viewport_height")
    device_pixel_ratio = _number(payload, "device_pixel_ratio")
    if viewport_width <= 0 or viewport_height <= 0:
        raise ValueError("Viewport dimensions must be positive.")
    if device_pixel_ratio <= 0:
        raise ValueError("Device pixel ratio must be positive.")

    raw_aoi_rects = payload.get("aoi_rects")
    if not isinstance(raw_aoi_rects, Mapping):
        raise ValueError("AOI rectangles must be an object keyed by AOI ID.")
    aoi_rects: dict[str, ViewportBBox] = {}
    for raw_aoi_id, raw_rect in raw_aoi_rects.items():
        aoi_id = str(raw_aoi_id).strip()
        if not aoi_id:
            raise ValueError("AOI ID must not be empty.")
        aoi_rects[aoi_id] = _bbox(raw_rect)

    return SlideViewportGeometry(
        deck_id=deck_id,
        slide_id=int(payload["slide_id"]),
        layout_revision=int(payload["layout_revision"]),
        received_at=_finite(received_at, "received_at"),
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        device_pixel_ratio=device_pixel_ratio,
        slide_rect=_bbox(payload.get("slide_rect")),
        aoi_rects=aoi_rects,
    )


def _bbox(payload: Any) -> ViewportBBox:
    if not isinstance(payload, Mapping):
        raise ValueError("Viewport rectangle must be an object.")
    return ViewportBBox(
        x1=_number(payload, "x1"),
        y1=_number(payload, "y1"),
        x2=_number(payload, "x2"),
        y2=_number(payload, "y2"),
    )


def _number(payload: Mapping[str, Any], key: str) -> float:
    if key not in payload:
        raise ValueError(f"Component geometry is missing {key}.")
    return _finite(payload[key], key)


def _finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number
