"""Resolve browser point gaze against visible slide AOIs."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from modules.common.schemas import AOI
from modules.media.browser_gaze_source import BrowserPointGazeSample
from modules.system.slide_geometry import ViewportBBox


X_TOLERANCE_CSS = 50.0
Y_TOLERANCE_CSS = 35.0
EXCLUDED_AOI_TYPES = {
    "footer",
    "page_number",
    "decoration",
    "background",
}


@dataclass(frozen=True)
class PointAOICandidate:
    aoi_id: str
    spatial_score: float
    exact_hit: bool


@dataclass(frozen=True)
class AggregatedPointGaze:
    predicted_aoi_id: str
    target_confidence: float
    stable_duration_sec: float
    layout_revision: int
    alternatives: Sequence[dict[str, object]]
    evidence: Sequence[str]


def match_point_to_visible_aois(
    sample: BrowserPointGazeSample,
    aois: Sequence[AOI],
    *,
    x_tolerance_css: float = X_TOLERANCE_CSS,
    y_tolerance_css: float = Y_TOLERANCE_CSS,
    max_candidates: int = 2,
) -> Sequence[PointAOICandidate]:
    if x_tolerance_css <= 0 or y_tolerance_css <= 0:
        raise ValueError("point-gaze tolerances must be positive")
    if max_candidates <= 0:
        return ()
    if not sample.valid or not sample.face_detected or sample.geometry is None:
        return ()

    geometry = sample.geometry.geometry
    viewport = ViewportBBox(
        0.0,
        0.0,
        sample.viewport_width,
        sample.viewport_height,
    )
    visible_slide = _intersection(geometry.slide_rect, viewport)
    if visible_slide is None or not _contains(
        visible_slide,
        sample.x_css,
        sample.y_css,
    ):
        return ()

    ranked: list[tuple[bool, float, float, str]] = []
    for aoi in aois:
        if (
            aoi.aoi_id == "whole_slide"
            or _normalized_type(aoi.type) in EXCLUDED_AOI_TYPES | {"whole_slide"}
        ):
            continue
        rect = geometry.aoi_rects.get(aoi.aoi_id)
        if rect is None:
            continue
        visible = _intersection(rect, geometry.slide_rect)
        if visible is not None:
            visible = _intersection(visible, viewport)
        if visible is None:
            continue

        dx = max(visible.x1 - sample.x_css, 0.0, sample.x_css - visible.x2)
        dy = max(visible.y1 - sample.y_css, 0.0, sample.y_css - visible.y2)
        if dx > x_tolerance_css or dy > y_tolerance_css:
            continue
        exact_hit = dx == 0.0 and dy == 0.0
        spatial_score = (
            1.0
            if exact_hit
            else max(
                0.0,
                1.0
                - max(
                    dx / x_tolerance_css,
                    dy / y_tolerance_css,
                ),
            )
        )
        center_distance = math.hypot(
            sample.x_css - (visible.x1 + visible.x2) / 2.0,
            sample.y_css - (visible.y1 + visible.y2) / 2.0,
        )
        ranked.append(
            (exact_hit, spatial_score, center_distance, aoi.aoi_id)
        )

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    return tuple(
        PointAOICandidate(
            aoi_id=aoi_id,
            spatial_score=spatial_score,
            exact_hit=exact_hit,
        )
        for exact_hit, spatial_score, _distance, aoi_id in ranked[:max_candidates]
    )


def aggregate_point_gaze(
    samples: Sequence[BrowserPointGazeSample],
    aois: Sequence[AOI],
    *,
    speech_ended_at: float,
    minimum_dwell_seconds: float = 0.15,
    max_sample_dwell_seconds: float = 0.5,
) -> AggregatedPointGaze | None:
    if minimum_dwell_seconds <= 0 or max_sample_dwell_seconds <= 0:
        raise ValueError("dwell thresholds must be positive")
    eligible = [
        sample
        for sample in samples
        if sample.valid
        and sample.face_detected
        and sample.geometry is not None
        and abs(
            sample.geometry.geometry.viewport_width - sample.viewport_width
        )
        <= 1.0
        and abs(
            sample.geometry.geometry.viewport_height - sample.viewport_height
        )
        <= 1.0
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda sample: sample.received_at)
    revisions = {
        sample.geometry.geometry.layout_revision
        for sample in eligible
        if sample.geometry is not None
    }
    latest_revision = eligible[-1].geometry.geometry.layout_revision
    current = [
        sample
        for sample in eligible
        if sample.geometry is not None
        and sample.geometry.geometry.layout_revision == latest_revision
    ]

    dwell_by_target: dict[str, float] = {}
    spatial_weight_by_target: dict[str, float] = {}
    for index, sample in enumerate(current):
        next_time = (
            current[index + 1].received_at
            if index + 1 < len(current)
            else speech_ended_at
        )
        dwell = min(
            max_sample_dwell_seconds,
            max(0.0, next_time - sample.received_at),
        )
        candidates = match_point_to_visible_aois(sample, aois)
        if not candidates or dwell <= 0:
            continue
        candidate = candidates[0]
        dwell_by_target[candidate.aoi_id] = (
            dwell_by_target.get(candidate.aoi_id, 0.0) + dwell
        )
        spatial_weight_by_target[candidate.aoi_id] = (
            spatial_weight_by_target.get(candidate.aoi_id, 0.0)
            + dwell * candidate.spatial_score
        )

    total_matched_dwell = sum(dwell_by_target.values())
    if total_matched_dwell < minimum_dwell_seconds:
        return None
    ranked = sorted(
        dwell_by_target.items(),
        key=lambda item: (-item[1], item[0]),
    )
    top_target, top_dwell = ranked[0]
    dwell_share = top_dwell / total_matched_dwell
    mean_spatial = spatial_weight_by_target[top_target] / top_dwell
    evidence = [
        f"local point-gaze matched dwell={total_matched_dwell:.3f}s",
    ]
    if len(revisions) > 1:
        evidence.append(
            "older layout revision evidence discarded; newest layout retained"
        )
    return AggregatedPointGaze(
        predicted_aoi_id=top_target,
        target_confidence=round(dwell_share * mean_spatial, 3),
        stable_duration_sec=round(total_matched_dwell, 3),
        layout_revision=latest_revision,
        alternatives=tuple(
            {
                "aoi_id": target,
                "score": round(dwell / total_matched_dwell, 3),
            }
            for target, dwell in ranked[:2]
        ),
        evidence=tuple(evidence),
    )


def _intersection(first: ViewportBBox, second: ViewportBBox) -> ViewportBBox | None:
    x1 = max(first.x1, second.x1)
    y1 = max(first.y1, second.y1)
    x2 = min(first.x2, second.x2)
    y2 = min(first.y2, second.y2)
    if x1 >= x2 or y1 >= y2:
        return None
    return ViewportBBox(x1, y1, x2, y2)


def _contains(rect: ViewportBBox, x: float, y: float) -> bool:
    return rect.x1 <= x <= rect.x2 and rect.y1 <= y <= rect.y2


def _normalized_type(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
