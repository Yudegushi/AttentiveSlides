"""Bounded browser geometry and local point-gaze observations."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
from threading import RLock
import time

from modules.system.slide_geometry import (
    SlideViewportGeometry,
    parse_component_geometry,
)


@dataclass(frozen=True)
class BrowserGeometrySnapshot:
    browser_timestamp_ms: float
    received_at: float
    geometry: SlideViewportGeometry


@dataclass(frozen=True)
class BrowserPointGazeSample:
    sequence: int
    browser_timestamp_ms: float
    received_at: float
    x_css: float
    y_css: float
    viewport_width: float
    viewport_height: float
    valid: bool
    face_detected: bool
    source: str
    geometry: BrowserGeometrySnapshot | None


@dataclass(frozen=True)
class BrowserObservationStats:
    gaze_samples: int
    gaze_rejections: int
    last_gaze_received_at: float | None
    geometry_slide_id: int | None
    geometry_layout_revision: int | None


class BrowserGazeSource:
    """Retain the latest browser layout and a bounded point-gaze history."""

    def __init__(
        self,
        *,
        max_gaze_samples: int = 300,
        gaze_stale_after_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_gaze_samples <= 0:
            raise ValueError("max_gaze_samples must be positive")
        if gaze_stale_after_seconds <= 0:
            raise ValueError("gaze_stale_after_seconds must be positive")
        self._clock = clock
        self._gaze_stale_after_seconds = float(gaze_stale_after_seconds)
        self._lock = RLock()
        self._geometry: BrowserGeometrySnapshot | None = None
        self._gaze: deque[BrowserPointGazeSample] = deque(
            maxlen=max_gaze_samples
        )
        self._gaze_rejections = 0
        self._last_gaze_received_at: float | None = None

    def accept_geometry(
        self,
        payload: Mapping[str, object],
    ) -> BrowserGeometrySnapshot:
        if not isinstance(payload, Mapping):
            raise ValueError("Browser geometry must be an object.")
        received_at = _finite(self._clock(), "received_at")
        browser_timestamp_ms = _number(
            payload, "browser_timestamp_ms"
        )
        geometry = parse_component_geometry(payload, received_at=received_at)
        snapshot = BrowserGeometrySnapshot(
            browser_timestamp_ms=browser_timestamp_ms,
            received_at=received_at,
            geometry=geometry,
        )
        with self._lock:
            self._geometry = snapshot
        return snapshot

    def accept_gaze(
        self,
        payload: Mapping[str, object],
    ) -> BrowserPointGazeSample:
        try:
            sample = self._parse_gaze(payload)
        except (KeyError, TypeError, ValueError) as exc:
            with self._lock:
                self._gaze_rejections += 1
            if isinstance(exc, ValueError):
                raise
            raise ValueError("Browser gaze payload is invalid.") from exc
        with self._lock:
            self._gaze.append(sample)
            self._last_gaze_received_at = sample.received_at
        return sample

    def latest_geometry_for(
        self,
        deck_id: str,
        slide_id: int,
    ) -> BrowserGeometrySnapshot | None:
        with self._lock:
            snapshot = self._geometry
            if snapshot is None:
                return None
            geometry = snapshot.geometry
            if geometry.deck_id != deck_id or geometry.slide_id != slide_id:
                return None
            return snapshot

    def gaze_in_window(
        self,
        *,
        start_received_at: float,
        end_received_at: float,
    ) -> list[BrowserPointGazeSample]:
        start = _finite(start_received_at, "start_received_at")
        end = _finite(end_received_at, "end_received_at")
        if end < start:
            raise ValueError("end_received_at must not precede start_received_at")
        with self._lock:
            return [
                sample
                for sample in self._gaze
                if start <= sample.received_at <= end
            ]

    def gaze_is_fresh(self, *, now: float | None = None) -> bool:
        current = _finite(self._clock() if now is None else now, "now")
        with self._lock:
            received_at = self._last_gaze_received_at
            return (
                received_at is not None
                and current - received_at <= self._gaze_stale_after_seconds
            )

    def clear_gaze(self) -> None:
        with self._lock:
            self._gaze.clear()
            self._last_gaze_received_at = None

    def clear(self) -> None:
        with self._lock:
            self._gaze.clear()
            self._last_gaze_received_at = None
            self._geometry = None

    def stats(self) -> BrowserObservationStats:
        with self._lock:
            geometry = self._geometry.geometry if self._geometry else None
            return BrowserObservationStats(
                gaze_samples=len(self._gaze),
                gaze_rejections=self._gaze_rejections,
                last_gaze_received_at=self._last_gaze_received_at,
                geometry_slide_id=(geometry.slide_id if geometry else None),
                geometry_layout_revision=(
                    geometry.layout_revision if geometry else None
                ),
            )

    def _parse_gaze(
        self,
        payload: Mapping[str, object],
    ) -> BrowserPointGazeSample:
        if not isinstance(payload, Mapping):
            raise ValueError("Browser gaze must be an object.")
        source = str(payload.get("source", ""))
        if source != "eyetheia_local":
            raise ValueError("Browser gaze source must be eyetheia_local.")
        sequence = _integer(payload, "sequence")
        if sequence < 0:
            raise ValueError("Browser gaze sequence must be non-negative.")
        viewport_width = _number(payload, "viewport_width")
        viewport_height = _number(payload, "viewport_height")
        if viewport_width <= 0 or viewport_height <= 0:
            raise ValueError("Browser gaze viewport dimensions must be positive.")
        received_at = _finite(self._clock(), "received_at")
        with self._lock:
            geometry = self._geometry
            if geometry is not None and (
                abs(geometry.geometry.viewport_width - viewport_width) > 1.0
                or abs(geometry.geometry.viewport_height - viewport_height) > 1.0
            ):
                geometry = None
        return BrowserPointGazeSample(
            sequence=sequence,
            browser_timestamp_ms=_number(payload, "browser_timestamp_ms"),
            received_at=received_at,
            x_css=_number(payload, "x_css"),
            y_css=_number(payload, "y_css"),
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            valid=_boolean(payload, "valid"),
            face_detected=_boolean(payload, "face_detected"),
            source=source,
            geometry=geometry,
        )


def _number(payload: Mapping[str, object], key: str) -> float:
    if key not in payload:
        raise ValueError(f"Browser observation is missing {key}.")
    return _finite(payload[key], key)


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number


def _integer(payload: Mapping[str, object], key: str) -> int:
    value = _number(payload, key)
    if not value.is_integer():
        raise ValueError(f"{key} must be an integer.")
    return int(value)


def _boolean(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value
