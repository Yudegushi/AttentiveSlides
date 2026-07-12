"""Unified interaction contracts for AttentiveSlides.

Manual, sensor-assisted, and hybrid input modes use the same
contract. Hardware-derived signals are optional rather than required.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping

from modules.common.schemas import IntentName


InteractionMode = Literal[
    "manual",
    "sensor_assisted",
    "hybrid",
]

TargetSource = Literal[
    "manual_rectangle",
    "manual_aoi",
    "gaze_prediction",
    "whole_slide",
]

IntentSource = Literal[
    "typed_text",
    "speech_transcript",
    "ui_action",
]

ConfirmationSource = Literal[
    "explicit_user_confirmation",
    "manual_correction",
    "automatic_high_confidence",
]


_INTERACTION_MODES = {
    "manual",
    "sensor_assisted",
    "hybrid",
}

_TARGET_SOURCES = {
    "manual_rectangle",
    "manual_aoi",
    "gaze_prediction",
    "whole_slide",
}

_INTENT_SOURCES = {
    "typed_text",
    "speech_transcript",
    "ui_action",
}

_CONFIRMATION_SOURCES = {
    "explicit_user_confirmation",
    "manual_correction",
    "automatic_high_confidence",
}


@dataclass(frozen=True)
class TargetCandidate:
    """One AOI candidate produced by mapping or prediction."""

    aoi_id: str
    score: float
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank(
            self.aoi_id,
            "TargetCandidate.aoi_id",
        )
        _require_probability(
            self.score,
            "TargetCandidate.score",
        )

        if any(
            not isinstance(item, str)
            or not item.strip()
            for item in self.evidence
        ):
            raise ValueError(
                "TargetCandidate.evidence entries "
                "must be non-blank strings."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TargetInput:
    """Target information before reference resolution.

    selected_aoi_id is optional for manual rectangles because AOI
    mapping is performed by a later component.
    """

    source: TargetSource
    slide_id: int

    bbox: tuple[float, float, float, float] | None = None
    selected_aoi_id: str | None = None

    predicted_aoi_id: str | None = None
    confidence: float | None = None
    alternatives: tuple[TargetCandidate, ...] = ()

    stable_duration_sec: float = 0.0

    def __post_init__(self) -> None:
        if self.source not in _TARGET_SOURCES:
            raise ValueError(
                f"Unsupported target source: {self.source!r}."
            )

        if self.slide_id < 0:
            raise ValueError(
                "TargetInput.slide_id must be non-negative."
            )

        if self.bbox is not None:
            _validate_bbox(self.bbox)

        _validate_optional_id(
            self.selected_aoi_id,
            "TargetInput.selected_aoi_id",
        )
        _validate_optional_id(
            self.predicted_aoi_id,
            "TargetInput.predicted_aoi_id",
        )

        if self.confidence is not None:
            _require_probability(
                self.confidence,
                "TargetInput.confidence",
            )

        if self.stable_duration_sec < 0:
            raise ValueError(
                "stable_duration_sec must be non-negative."
            )

        candidate_ids = [
            candidate.aoi_id
            for candidate in self.alternatives
        ]

        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError(
                "Target alternatives must use unique AOI IDs."
            )

        self._validate_source_specific_fields()

    def _validate_source_specific_fields(self) -> None:
        if self.source == "manual_rectangle":
            if self.bbox is None:
                raise ValueError(
                    "manual_rectangle requires bbox."
                )

            if self.predicted_aoi_id is not None:
                raise ValueError(
                    "manual_rectangle cannot set "
                    "predicted_aoi_id."
                )

        elif self.source == "manual_aoi":
            if self.selected_aoi_id is None:
                raise ValueError(
                    "manual_aoi requires selected_aoi_id."
                )

            if self.predicted_aoi_id is not None:
                raise ValueError(
                    "manual_aoi cannot set predicted_aoi_id."
                )

        elif self.source == "gaze_prediction":
            if self.confidence is None:
                raise ValueError(
                    "gaze_prediction requires confidence."
                )

            if self.selected_aoi_id is not None:
                raise ValueError(
                    "gaze_prediction cannot set "
                    "selected_aoi_id before confirmation."
                )

        elif self.source == "whole_slide":
            if self.bbox is not None:
                raise ValueError(
                    "whole_slide cannot include bbox."
                )

            if self.predicted_aoi_id is not None:
                raise ValueError(
                    "whole_slide cannot include "
                    "predicted_aoi_id."
                )

            if self.selected_aoi_id not in {
                None,
                "whole_slide",
            }:
                raise ValueError(
                    "whole_slide selected_aoi_id must be "
                    "None or 'whole_slide'."
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IntentInput:
    """Typed, spoken, or explicit UI intent input."""

    source: IntentSource
    text: str = ""
    explicit_intent: IntentName | None = None
    source_confidence: float | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        if self.source not in _INTENT_SOURCES:
            raise ValueError(
                f"Unsupported intent source: {self.source!r}."
            )

        if self.source in {
            "typed_text",
            "speech_transcript",
        }:
            _require_non_blank(
                self.text,
                "IntentInput.text",
            )

        if (
            self.source == "ui_action"
            and self.explicit_intent is None
        ):
            raise ValueError(
                "ui_action requires explicit_intent."
            )

        if self.source_confidence is not None:
            _require_probability(
                self.source_confidence,
                "IntentInput.source_confidence",
            )

        if self.language is not None:
            _require_non_blank(
                self.language,
                "IntentInput.language",
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfirmationInput:
    """Explicit or automatic confirmation state."""

    confirmed: bool = False
    source: ConfirmationSource | None = None
    confirmed_aoi_id: str | None = None
    corrected_from_aoi_id: str | None = None

    def __post_init__(self) -> None:
        _validate_optional_id(
            self.confirmed_aoi_id,
            "ConfirmationInput.confirmed_aoi_id",
        )
        _validate_optional_id(
            self.corrected_from_aoi_id,
            "ConfirmationInput.corrected_from_aoi_id",
        )

        if not self.confirmed:
            if any(
                value is not None
                for value in {
                    self.source,
                    self.confirmed_aoi_id,
                    self.corrected_from_aoi_id,
                }
            ):
                raise ValueError(
                    "Unconfirmed interaction cannot set "
                    "confirmation metadata."
                )

            return

        if self.source not in _CONFIRMATION_SOURCES:
            raise ValueError(
                "Confirmed interaction requires a valid "
                "confirmation source."
            )

        if (
            self.source == "manual_correction"
            and self.confirmed_aoi_id is None
        ):
            raise ValueError(
                "manual_correction requires "
                "confirmed_aoi_id."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InteractionInput:
    """Hardware-independent user interaction input."""

    interaction_id: str
    deck_id: str
    slide_id: int
    mode: InteractionMode
    target: TargetInput
    intent: IntentInput

    confirmation: ConfirmationInput = field(
        default_factory=ConfirmationInput
    )
    metadata: dict[str, Any] = field(
        default_factory=dict
    )
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _require_non_blank(
            self.interaction_id,
            "InteractionInput.interaction_id",
        )
        _require_non_blank(
            self.deck_id,
            "InteractionInput.deck_id",
        )

        if self.slide_id < 0:
            raise ValueError(
                "InteractionInput.slide_id "
                "must be non-negative."
            )

        if self.mode not in _INTERACTION_MODES:
            raise ValueError(
                f"Unsupported interaction mode: "
                f"{self.mode!r}."
            )

        if self.target.slide_id != self.slide_id:
            raise ValueError(
                "Target slide_id must match interaction "
                "slide_id."
            )

        if self.schema_version != "1.0":
            raise ValueError(
                "Unsupported interaction schema version: "
                f"{self.schema_version!r}."
            )

        self._validate_mode()
        self._validate_confirmation()

    def _validate_mode(self) -> None:
        if self.mode != "manual":
            return

        if self.target.source == "gaze_prediction":
            raise ValueError(
                "manual mode cannot use gaze_prediction."
            )

        if self.intent.source == "speech_transcript":
            raise ValueError(
                "manual mode cannot use speech_transcript."
            )

    def _validate_confirmation(self) -> None:
        confirmation = self.confirmation

        if not confirmation.confirmed:
            return

        if (
            confirmation.source
            == "automatic_high_confidence"
        ):
            if self.target.source != "gaze_prediction":
                raise ValueError(
                    "automatic_high_confidence requires "
                    "gaze_prediction."
                )

            if (
                self.target.confidence is None
                or self.target.confidence < 0.70
            ):
                raise ValueError(
                    "automatic_high_confidence requires "
                    "target confidence >= 0.70."
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def interaction_input_from_dict(
    payload: Mapping[str, Any],
) -> InteractionInput:
    """Deserialize an InteractionInput from a JSON-like mapping."""
    target_payload = dict(payload["target"])
    intent_payload = dict(payload["intent"])
    confirmation_payload = dict(
        payload.get(
            "confirmation",
            {"confirmed": False},
        )
    )

    bbox_payload = target_payload.get("bbox")

    bbox = (
        tuple(float(value) for value in bbox_payload)
        if bbox_payload is not None
        else None
    )

    alternatives = tuple(
        TargetCandidate(
            aoi_id=item["aoi_id"],
            score=float(item["score"]),
            evidence=tuple(
                item.get("evidence", ())
            ),
        )
        for item in target_payload.get(
            "alternatives",
            (),
        )
    )

    target = TargetInput(
        source=target_payload["source"],
        slide_id=int(target_payload["slide_id"]),
        bbox=bbox,
        selected_aoi_id=target_payload.get(
            "selected_aoi_id"
        ),
        predicted_aoi_id=target_payload.get(
            "predicted_aoi_id"
        ),
        confidence=_optional_float(
            target_payload.get("confidence")
        ),
        alternatives=alternatives,
        stable_duration_sec=float(
            target_payload.get(
                "stable_duration_sec",
                0.0,
            )
        ),
    )

    intent = IntentInput(
        source=intent_payload["source"],
        text=intent_payload.get("text", ""),
        explicit_intent=intent_payload.get(
            "explicit_intent"
        ),
        source_confidence=_optional_float(
            intent_payload.get(
                "source_confidence"
            )
        ),
        language=intent_payload.get("language"),
    )

    confirmation = ConfirmationInput(
        confirmed=bool(
            confirmation_payload.get(
                "confirmed",
                False,
            )
        ),
        source=confirmation_payload.get("source"),
        confirmed_aoi_id=confirmation_payload.get(
            "confirmed_aoi_id"
        ),
        corrected_from_aoi_id=(
            confirmation_payload.get(
                "corrected_from_aoi_id"
            )
        ),
    )

    return InteractionInput(
        interaction_id=payload["interaction_id"],
        deck_id=payload["deck_id"],
        slide_id=int(payload["slide_id"]),
        mode=payload["mode"],
        target=target,
        intent=intent,
        confirmation=confirmation,
        metadata=dict(payload.get("metadata", {})),
        schema_version=payload.get(
            "schema_version",
            "1.0",
        ),
    )


def _validate_bbox(
    bbox: tuple[float, float, float, float],
) -> None:
    if len(bbox) != 4:
        raise ValueError(
            "bbox must be [x1, y1, x2, y2]."
        )

    if any(
        not isinstance(value, (int, float))
        for value in bbox
    ):
        raise TypeError(
            "bbox coordinates must be numeric."
        )

    if any(
        value < 0 or value > 1
        for value in bbox
    ):
        raise ValueError(
            "bbox coordinates must be normalized "
            "to [0, 1]."
        )

    x1, y1, x2, y2 = bbox

    if x1 >= x2 or y1 >= y2:
        raise ValueError(
            "bbox requires x1 < x2 and y1 < y2."
        )


def _require_probability(
    value: float,
    field_name: str,
) -> None:
    if value < 0 or value > 1:
        raise ValueError(
            f"{field_name} must be in [0, 1]."
        )


def _require_non_blank(
    value: str,
    field_name: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must not be blank."
        )


def _validate_optional_id(
    value: str | None,
    field_name: str,
) -> None:
    if value is not None:
        _require_non_blank(value, field_name)


def _optional_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    return float(value)
