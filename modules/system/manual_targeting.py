"""Manual rectangle selection and AOI overlap mapping."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from modules.common.interaction_contracts import (
    TargetCandidate,
    TargetInput,
)
from modules.common.schemas import AOI


NormalizedBBox = tuple[
    float,
    float,
    float,
    float,
]


@dataclass(frozen=True)
class AOIMatch:
    """One AOI matched by a manual rectangle."""

    aoi_id: str
    aoi_type: str
    text: str
    score: float
    intersection_over_union: float
    selection_coverage: float
    aoi_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ManualSelectionResult:
    """Normalized rectangle and its mapped AOI candidates."""

    bbox: NormalizedBBox
    canvas_width: int
    canvas_height: int
    matches: tuple[AOIMatch, ...]

    @property
    def primary_aoi_id(self) -> str | None:
        if not self.matches:
            return None

        return self.matches[0].aoi_id

    @property
    def selected_text(self) -> str:
        texts: list[str] = []
        seen: set[str] = set()

        for match in self.matches:
            normalized = " ".join(
                match.text.split()
            )

            if (
                normalized
                and normalized not in seen
            ):
                seen.add(normalized)
                texts.append(normalized)

        return "\n\n".join(texts)

    def to_target_input(
        self,
        *,
        slide_id: int,
    ) -> TargetInput:
        """Convert the selection into the Stage 1 contract."""
        alternatives = tuple(
            TargetCandidate(
                aoi_id=match.aoi_id,
                score=match.score,
                evidence=(
                    (
                        "manual rectangle overlap: "
                        f"selection_coverage="
                        f"{match.selection_coverage:.3f}"
                    ),
                    (
                        "manual rectangle overlap: "
                        f"aoi_coverage="
                        f"{match.aoi_coverage:.3f}"
                    ),
                ),
            )
            for match in self.matches
        )

        return TargetInput(
            source="manual_rectangle",
            slide_id=slide_id,
            bbox=self.bbox,
            selected_aoi_id=(
                self.primary_aoi_id
            ),
            alternatives=alternatives,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": list(self.bbox),
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "primary_aoi_id": (
                self.primary_aoi_id
            ),
            "selected_text": self.selected_text,
            "matches": [
                match.to_dict()
                for match in self.matches
            ],
        }


def extract_latest_rectangle(
    canvas_json: Mapping[str, Any] | None,
    *,
    canvas_width: int,
    canvas_height: int,
    aois: Sequence[AOI],
    max_candidates: int = 5,
) -> ManualSelectionResult | None:
    """Extract the latest valid Fabric.js rectangle."""
    if canvas_json is None:
        return None

    objects = canvas_json.get("objects", [])

    if not isinstance(objects, list):
        raise ValueError(
            "Canvas JSON objects must be a list."
        )

    rectangles = [
        item
        for item in objects
        if (
            isinstance(item, Mapping)
            and str(
                item.get("type", "")
            ).casefold()
            == "rect"
        )
    ]

    if not rectangles:
        return None

    bbox = fabric_rectangle_to_bbox(
        rectangles[-1],
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )

    matches = map_bbox_to_aois(
        bbox,
        aois,
        max_candidates=max_candidates,
    )

    return ManualSelectionResult(
        bbox=bbox,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        matches=matches,
    )


def fabric_rectangle_to_bbox(
    rectangle: Mapping[str, Any],
    *,
    canvas_width: int,
    canvas_height: int,
) -> NormalizedBBox:
    """Convert a Fabric.js rectangle to normalized coordinates."""
    if canvas_width <= 0:
        raise ValueError(
            "canvas_width must be positive."
        )

    if canvas_height <= 0:
        raise ValueError(
            "canvas_height must be positive."
        )

    angle = float(
        rectangle.get("angle", 0.0)
    )

    if abs(angle) > 1e-6:
        raise ValueError(
            "Rotated rectangles are not supported."
        )

    left = float(
        rectangle.get("left", 0.0)
    )
    top = float(
        rectangle.get("top", 0.0)
    )
    width = abs(
        float(rectangle.get("width", 0.0))
        * float(
            rectangle.get("scaleX", 1.0)
        )
    )
    height = abs(
        float(rectangle.get("height", 0.0))
        * float(
            rectangle.get("scaleY", 1.0)
        )
    )

    if width < 2.0 or height < 2.0:
        raise ValueError(
            "Manual rectangle is too small."
        )

    origin_x = str(
        rectangle.get("originX", "left")
    ).casefold()

    origin_y = str(
        rectangle.get("originY", "top")
    ).casefold()

    if origin_x == "center":
        x_min = left - width / 2.0
    elif origin_x == "right":
        x_min = left - width
    else:
        x_min = left

    if origin_y == "center":
        y_min = top - height / 2.0
    elif origin_y == "bottom":
        y_min = top - height
    else:
        y_min = top

    x_max = x_min + width
    y_max = y_min + height

    x_min = _clamp(
        x_min,
        0.0,
        float(canvas_width),
    )
    y_min = _clamp(
        y_min,
        0.0,
        float(canvas_height),
    )
    x_max = _clamp(
        x_max,
        0.0,
        float(canvas_width),
    )
    y_max = _clamp(
        y_max,
        0.0,
        float(canvas_height),
    )

    if x_min >= x_max or y_min >= y_max:
        raise ValueError(
            "Manual rectangle has no visible area."
        )

    bbox = (
        round(x_min / canvas_width, 6),
        round(y_min / canvas_height, 6),
        round(x_max / canvas_width, 6),
        round(y_max / canvas_height, 6),
    )

    _validate_normalized_bbox(bbox)

    return bbox


def map_bbox_to_aois(
    bbox: NormalizedBBox,
    aois: Sequence[AOI],
    *,
    max_candidates: int = 5,
) -> tuple[AOIMatch, ...]:
    """Rank AOIs according to overlap with the manual rectangle."""
    _validate_normalized_bbox(bbox)

    if max_candidates <= 0:
        raise ValueError(
            "max_candidates must be positive."
        )

    selection_area = _bbox_area(bbox)
    matches: list[
        tuple[AOIMatch, float]
    ] = []

    for aoi in aois:
        if aoi.aoi_id == "whole_slide":
            continue

        if aoi.type.casefold() == "footer":
            continue

        aoi_bbox = tuple(
            float(value)
            for value in aoi.bbox
        )

        intersection = _intersection_area(
            bbox,
            aoi_bbox,
        )

        if intersection <= 0.0:
            continue

        aoi_area = _bbox_area(aoi_bbox)
        union = (
            selection_area
            + aoi_area
            - intersection
        )

        iou = (
            intersection / union
            if union > 0
            else 0.0
        )

        selection_coverage = (
            intersection / selection_area
            if selection_area > 0
            else 0.0
        )

        aoi_coverage = (
            intersection / aoi_area
            if aoi_area > 0
            else 0.0
        )

        if (
            selection_coverage < 0.05
            and aoi_coverage < 0.15
            and iou < 0.03
        ):
            continue

        score = (
            0.45 * aoi_coverage
            + 0.35 * selection_coverage
            + 0.20 * iou
        )

        match = AOIMatch(
            aoi_id=aoi.aoi_id,
            aoi_type=aoi.type,
            text=aoi.text,
            score=round(score, 6),
            intersection_over_union=round(
                iou,
                6,
            ),
            selection_coverage=round(
                selection_coverage,
                6,
            ),
            aoi_coverage=round(
                aoi_coverage,
                6,
            ),
        )

        matches.append(
            (
                match,
                aoi_area,
            )
        )

    matches.sort(
        key=lambda item: (
            -item[0].score,
            item[1],
            item[0].aoi_id,
        )
    )

    return tuple(
        item[0]
        for item in matches[
            :max_candidates
        ]
    )


def _intersection_area(
    first: Sequence[float],
    second: Sequence[float],
) -> float:
    x_min = max(
        float(first[0]),
        float(second[0]),
    )
    y_min = max(
        float(first[1]),
        float(second[1]),
    )
    x_max = min(
        float(first[2]),
        float(second[2]),
    )
    y_max = min(
        float(first[3]),
        float(second[3]),
    )

    return (
        max(0.0, x_max - x_min)
        * max(0.0, y_max - y_min)
    )


def _bbox_area(
    bbox: Sequence[float],
) -> float:
    return (
        max(
            0.0,
            float(bbox[2])
            - float(bbox[0]),
        )
        * max(
            0.0,
            float(bbox[3])
            - float(bbox[1]),
        )
    )


def _validate_normalized_bbox(
    bbox: Sequence[float],
) -> None:
    if len(bbox) != 4:
        raise ValueError(
            "bbox must contain four values."
        )

    values = tuple(
        float(value)
        for value in bbox
    )

    if any(
        value < 0.0 or value > 1.0
        for value in values
    ):
        raise ValueError(
            "bbox values must be in [0, 1]."
        )

    x_min, y_min, x_max, y_max = values

    if x_min >= x_max or y_min >= y_max:
        raise ValueError(
            "bbox requires x_min < x_max "
            "and y_min < y_max."
        )


def _clamp(
    value: float,
    lower: float,
    upper: float,
) -> float:
    return max(
        lower,
        min(upper, value),
    )
