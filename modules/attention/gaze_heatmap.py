from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Sequence

from modules.common.schemas import AOI
from modules.media.browser_gaze_source import BrowserPointGazeSample
from modules.system.point_gaze import (
    EXCLUDED_AOI_TYPES,
    match_point_to_visible_aois,
)


SCHEMA_VERSION = 1
GRID_WIDTH = 64
MIN_GRID_HEIGHT = 24
MAX_GRID_HEIGHT = 64
MAX_DWELL_SECONDS = 0.5


@dataclass(frozen=True)
class AOIDwellSnapshot:
    aoi_id: str
    label: str
    bbox: tuple[float, float, float, float]
    dwell_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "aoi_id": self.aoi_id,
            "label": self.label,
            "bbox": list(self.bbox),
            "dwell_seconds": round(self.dwell_seconds, 4),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "AOIDwellSnapshot":
        bbox = tuple(float(value) for value in payload["bbox"])
        dwell = float(payload["dwell_seconds"])
        if (
            len(bbox) != 4
            or not all(
                math.isfinite(value) and 0.0 <= value <= 1.0 for value in bbox
            )
            or bbox[0] >= bbox[2]
            or bbox[1] >= bbox[3]
        ):
            raise ValueError("review AOI bbox is invalid")
        if not math.isfinite(dwell) or dwell < 0.0:
            raise ValueError("review AOI dwell must be finite and non-negative")
        return cls(
            aoi_id=str(payload["aoi_id"]),
            label=str(payload["label"]),
            bbox=bbox,
            dwell_seconds=dwell,
        )


@dataclass(frozen=True)
class SlideHeatmapSnapshot:
    deck_id: str
    slide_id: int
    grid_width: int
    grid_height: int
    grid: tuple[float, ...]
    observed_seconds: float
    valid_gaze_seconds: float
    aoi_dwell: tuple[AOIDwellSnapshot, ...]

    @property
    def coverage(self) -> float:
        if self.observed_seconds <= 0.0:
            return 0.0
        return min(1.0, self.valid_gaze_seconds / self.observed_seconds)

    @property
    def other_slide_seconds(self) -> float:
        matched = sum(item.dwell_seconds for item in self.aoi_dwell)
        return max(0.0, self.valid_gaze_seconds - matched)

    def to_dict(self) -> dict[str, object]:
        return {
            "deck_id": self.deck_id,
            "slide_id": self.slide_id,
            "grid_width": self.grid_width,
            "grid_height": self.grid_height,
            "grid": [round(value, 4) for value in self.grid],
            "observed_seconds": round(self.observed_seconds, 4),
            "valid_gaze_seconds": round(self.valid_gaze_seconds, 4),
            "aoi_dwell": [item.to_dict() for item in self.aoi_dwell],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SlideHeatmapSnapshot":
        width = int(payload["grid_width"])
        height = int(payload["grid_height"])
        grid = tuple(float(value) for value in payload["grid"])
        observed = float(payload["observed_seconds"])
        valid = float(payload["valid_gaze_seconds"])
        if width <= 0 or height <= 0 or len(grid) != width * height:
            raise ValueError("review grid shape is invalid")
        if not all(math.isfinite(value) and value >= 0.0 for value in grid):
            raise ValueError("review grid values must be finite and non-negative")
        if (
            not math.isfinite(observed)
            or not math.isfinite(valid)
            or observed < 0.0
            or valid < 0.0
            or valid > observed + 1e-4
        ):
            raise ValueError("review dwell totals are invalid")
        return cls(
            deck_id=str(payload["deck_id"]),
            slide_id=int(payload["slide_id"]),
            grid_width=width,
            grid_height=height,
            grid=grid,
            observed_seconds=observed,
            valid_gaze_seconds=valid,
            aoi_dwell=tuple(
                AOIDwellSnapshot.from_dict(item)
                for item in payload.get("aoi_dwell", [])
            ),
        )


@dataclass(frozen=True)
class GazeReviewSession:
    schema_version: int
    session_id: str
    deck_id: str
    started_at_epoch: float
    ended_at_epoch: float
    slides: tuple[SlideHeatmapSnapshot, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "deck_id": self.deck_id,
            "started_at_epoch": round(self.started_at_epoch, 4),
            "ended_at_epoch": round(self.ended_at_epoch, 4),
            "slides": [slide.to_dict() for slide in self.slides],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "GazeReviewSession":
        if int(payload.get("schema_version", -1)) != SCHEMA_VERSION:
            raise ValueError("unsupported gaze review schema")
        started = float(payload["started_at_epoch"])
        ended = float(payload["ended_at_epoch"])
        if (
            not math.isfinite(started)
            or not math.isfinite(ended)
            or ended < started
        ):
            raise ValueError("review session timestamps are invalid")
        return cls(
            schema_version=SCHEMA_VERSION,
            session_id=str(payload["session_id"]),
            deck_id=str(payload["deck_id"]),
            started_at_epoch=started,
            ended_at_epoch=ended,
            slides=tuple(
                SlideHeatmapSnapshot.from_dict(item)
                for item in payload.get("slides", [])
            ),
        )


def normalized_slide_point(
    sample: BrowserPointGazeSample,
) -> tuple[float, float] | None:
    if not sample.valid or not sample.face_detected or sample.geometry is None:
        return None
    geometry = sample.geometry.geometry
    values = (
        sample.x_css,
        sample.y_css,
        sample.viewport_width,
        sample.viewport_height,
    )
    if not all(math.isfinite(value) for value in values):
        return None
    if sample.viewport_width <= 0.0 or sample.viewport_height <= 0.0:
        return None

    slide = geometry.slide_rect
    if (
        abs(geometry.viewport_width - sample.viewport_width) > 1.0
        or abs(geometry.viewport_height - sample.viewport_height) > 1.0
    ):
        return None
    visible_x1 = max(0.0, slide.x1)
    visible_y1 = max(0.0, slide.y1)
    visible_x2 = min(sample.viewport_width, slide.x2)
    visible_y2 = min(sample.viewport_height, slide.y2)
    if visible_x1 >= visible_x2 or visible_y1 >= visible_y2:
        return None
    if not (
        visible_x1 <= sample.x_css <= visible_x2
        and visible_y1 <= sample.y_css <= visible_y2
    ):
        return None

    return (
        min(1.0, max(0.0, (sample.x_css - slide.x1) / (slide.x2 - slide.x1))),
        min(1.0, max(0.0, (sample.y_css - slide.y1) / (slide.y2 - slide.y1))),
    )


@dataclass
class _PendingObservation:
    deck_id: str
    slide_id: int
    layout_revision: int
    received_at: float
    point: tuple[float, float] | None
    matched_aoi_id: str | None


@dataclass
class _MutableSlide:
    grid_width: int
    grid_height: int
    grid: list[float]
    observed_seconds: float
    valid_gaze_seconds: float
    aoi_seconds: dict[str, float]


class GazeHeatmapAccumulator:
    def __init__(self, *, session_id: str, deck_id: str, started_at_epoch: float):
        self.session_id = session_id
        self.deck_id = deck_id
        self.started_at_epoch = float(started_at_epoch)
        self._aois: dict[tuple[str, int], tuple[AOI, ...]] = {}
        self._slides: dict[tuple[str, int], _MutableSlide] = {}
        self._pending: _PendingObservation | None = None

    def register_slide(
        self,
        deck_id: str,
        slide_id: int,
        aois: Sequence[AOI],
    ) -> None:
        key = (str(deck_id), int(slide_id))
        self._aois[key] = tuple(aois)
        state = self._slides.get(key)
        if state is not None:
            for aoi in self._review_aois(key):
                state.aoi_seconds.setdefault(aoi.aoi_id, 0.0)

    def pause(self) -> None:
        self._pending = None

    def accept(self, sample: BrowserPointGazeSample) -> bool:
        geometry = sample.geometry.geometry if sample.geometry is not None else None
        identity = (
            (geometry.deck_id, geometry.slide_id, geometry.layout_revision)
            if geometry is not None
            else None
        )
        if self._pending is not None and identity == (
            self._pending.deck_id,
            self._pending.slide_id,
            self._pending.layout_revision,
        ):
            dwell = min(
                MAX_DWELL_SECONDS,
                max(0.0, sample.received_at - self._pending.received_at),
            )
            self._add_pending(self._pending, dwell)

        if geometry is None or geometry.deck_id != self.deck_id:
            self._pending = None
            return False

        point = normalized_slide_point(sample)
        matched_aoi_id = None
        if point is not None:
            candidates = match_point_to_visible_aois(
                sample,
                self._aois.get((geometry.deck_id, geometry.slide_id), ()),
                max_candidates=1,
            )
            matched_aoi_id = candidates[0].aoi_id if candidates else None

        self._ensure_slide(geometry)
        self._pending = _PendingObservation(
            deck_id=geometry.deck_id,
            slide_id=geometry.slide_id,
            layout_revision=geometry.layout_revision,
            received_at=sample.received_at,
            point=point,
            matched_aoi_id=matched_aoi_id,
        )
        return point is not None

    def finish(
        self,
        *,
        ended_received_at: float,
        ended_at_epoch: float,
    ) -> GazeReviewSession:
        if self._pending is not None:
            dwell = min(
                MAX_DWELL_SECONDS,
                max(0.0, float(ended_received_at) - self._pending.received_at),
            )
            self._add_pending(self._pending, dwell)
        self.pause()
        return GazeReviewSession(
            schema_version=SCHEMA_VERSION,
            session_id=self.session_id,
            deck_id=self.deck_id,
            started_at_epoch=self.started_at_epoch,
            ended_at_epoch=float(ended_at_epoch),
            slides=tuple(self._snapshot_slides()),
        )

    def _review_aois(self, key: tuple[str, int]) -> tuple[AOI, ...]:
        return tuple(
            aoi
            for aoi in self._aois.get(key, ())
            if aoi.aoi_id != "whole_slide"
            and aoi.type.strip().lower().replace("-", "_").replace(" ", "_")
            not in EXCLUDED_AOI_TYPES | {"whole_slide"}
        )

    def _ensure_slide(self, geometry) -> _MutableSlide:
        key = (geometry.deck_id, geometry.slide_id)
        existing = self._slides.get(key)
        if existing is not None:
            return existing
        width = geometry.slide_rect.x2 - geometry.slide_rect.x1
        height = geometry.slide_rect.y2 - geometry.slide_rect.y1
        grid_height = max(
            MIN_GRID_HEIGHT,
            min(MAX_GRID_HEIGHT, round(GRID_WIDTH * height / width)),
        )
        state = _MutableSlide(
            grid_width=GRID_WIDTH,
            grid_height=grid_height,
            grid=[0.0] * (GRID_WIDTH * grid_height),
            observed_seconds=0.0,
            valid_gaze_seconds=0.0,
            aoi_seconds={
                aoi.aoi_id: 0.0
                for aoi in self._review_aois(key)
            },
        )
        self._slides[key] = state
        return state

    def _add_pending(self, pending: _PendingObservation, dwell: float) -> None:
        state = self._slides[(pending.deck_id, pending.slide_id)]
        state.observed_seconds += dwell
        if pending.point is None:
            return
        state.valid_gaze_seconds += dwell
        self._splat(state, pending.point, dwell)
        if pending.matched_aoi_id in state.aoi_seconds:
            state.aoi_seconds[pending.matched_aoi_id] += dwell

    @staticmethod
    def _splat(
        state: _MutableSlide,
        point: tuple[float, float],
        dwell: float,
    ) -> None:
        x = point[0] * (state.grid_width - 1)
        y = point[1] * (state.grid_height - 1)
        x0, y0 = math.floor(x), math.floor(y)
        x1 = min(state.grid_width - 1, x0 + 1)
        y1 = min(state.grid_height - 1, y0 + 1)
        wx, wy = x - x0, y - y0
        for cell_x, cell_y, weight in (
            (x0, y0, (1.0 - wx) * (1.0 - wy)),
            (x1, y0, wx * (1.0 - wy)),
            (x0, y1, (1.0 - wx) * wy),
            (x1, y1, wx * wy),
        ):
            state.grid[cell_y * state.grid_width + cell_x] += dwell * weight

    def _snapshot_slides(self) -> list[SlideHeatmapSnapshot]:
        snapshots = []
        for key in sorted(self._slides, key=lambda item: item[1]):
            state = self._slides[key]
            aois = sorted(
                self._review_aois(key),
                key=lambda aoi: (aoi.bbox[1], aoi.bbox[0], aoi.aoi_id),
            )
            snapshots.append(
                SlideHeatmapSnapshot(
                    deck_id=key[0],
                    slide_id=key[1],
                    grid_width=state.grid_width,
                    grid_height=state.grid_height,
                    grid=tuple(state.grid),
                    observed_seconds=state.observed_seconds,
                    valid_gaze_seconds=state.valid_gaze_seconds,
                    aoi_dwell=tuple(
                        AOIDwellSnapshot(
                            aoi_id=aoi.aoi_id,
                            label=(
                                aoi.name
                                or (
                                    aoi.text[:57] + "..."
                                    if len(aoi.text) > 60
                                    else aoi.text
                                )
                                or aoi.aoi_id
                            ),
                            bbox=tuple(float(value) for value in aoi.bbox),
                            dwell_seconds=state.aoi_seconds.get(aoi.aoi_id, 0.0),
                        )
                        for aoi in aois
                    ),
                )
            )
        return snapshots
