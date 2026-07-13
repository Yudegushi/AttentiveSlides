"""Explicit confirmation and correction for manual interaction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Sequence

from modules.common.interaction_contracts import (
    ConfirmationInput,
    InteractionInput,
    TargetCandidate,
    TargetInput,
)
from modules.common.schemas import AOI
from modules.system.manual_intent import (
    ManualIntentResolution,
)


ConfirmationAssessmentStatus = Literal[
    "ready",
    "warning",
    "blocked",
]

TargetOptionSource = Literal[
    "manual_mapping",
    "whole_slide",
]


@dataclass(frozen=True)
class ConfirmationTargetOption:
    """One learner-selectable target in the confirmation panel."""

    aoi_id: str
    label: str
    source: TargetOptionSource
    text: str
    score: float | None
    is_proposed: bool

    def __post_init__(self) -> None:
        if not self.aoi_id.strip():
            raise ValueError(
                "Confirmation target AOI ID must not be blank."
            )

        if not self.label.strip():
            raise ValueError(
                "Confirmation target label must not be blank."
            )

        if (
            self.score is not None
            and not 0.0 <= self.score <= 1.0
        ):
            raise ValueError(
                "Confirmation target score must be in [0, 1]."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ManualConfirmationPreview:
    """Target, intent, and context shown before confirmation."""

    deck_id: str
    slide_id: int
    target_scope: str
    target_source: str
    bbox: tuple[float, float, float, float] | None
    proposed_aoi_id: str | None
    target_options: tuple[
        ConfirmationTargetOption,
        ...,
    ]
    intent_resolution: ManualIntentResolution | None

    @property
    def target_option_ids(self) -> tuple[str, ...]:
        return tuple(
            option.aoi_id
            for option in self.target_options
        )

    def get_target_option(
        self,
        aoi_id: str,
    ) -> ConfirmationTargetOption:
        for option in self.target_options:
            if option.aoi_id == aoi_id:
                return option

        raise ValueError(
            f"Target {aoi_id!r} is not available "
            "for confirmation."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deck_id": self.deck_id,
            "slide_id": self.slide_id,
            "target_scope": self.target_scope,
            "target_source": self.target_source,
            "bbox": (
                list(self.bbox)
                if self.bbox is not None
                else None
            ),
            "proposed_aoi_id": self.proposed_aoi_id,
            "target_options": [
                option.to_dict()
                for option in self.target_options
            ],
            "intent_resolution": (
                self.intent_resolution.to_dict()
                if self.intent_resolution is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ConfirmationAssessment:
    """Whether the current target and intent can be confirmed."""

    ready: bool
    status: ConfirmationAssessmentStatus
    message: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfirmedManualInteraction:
    """Confirmed interaction and correction provenance."""

    interaction: InteractionInput
    selected_target: ConfirmationTargetOption
    proposed_aoi_id: str | None
    corrected: bool
    confirmed_context: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "interaction": self.interaction.to_dict(),
            "selected_target": (
                self.selected_target.to_dict()
            ),
            "proposed_aoi_id": self.proposed_aoi_id,
            "corrected": self.corrected,
            "confirmed_context": self.confirmed_context,
        }


def normalize_manual_target_scope(
    value: str,
) -> str:
    """Map user-facing target labels to the canonical domain values."""
    aliases = {
        "whole slide": "Whole slide",
        "use whole slide": "Whole slide",
        "whole_slide": "Whole slide",
        "manual region": "Manual region",
        "select region": "Manual region",
        "manual_rectangle": "Manual region",
    }

    normalized = aliases.get(
        str(value).strip().casefold()
    )

    if normalized is None:
        raise ValueError(
            f"Unsupported target scope: {value!r}."
        )

    return normalized

def build_manual_confirmation_preview(
    *,
    deck_id: str,
    slide_id: int,
    target_scope: str,
    bbox: Sequence[float] | None,
    selected_aoi_ids: Sequence[str],
    selection_matches: Sequence[
        Mapping[str, Any]
    ],
    slide_text: str,
    aois: Sequence[AOI],
    intent_resolution: (
        ManualIntentResolution | None
    ),
) -> ManualConfirmationPreview:
    """Build the target and intent preview shown to the learner."""
    target_scope = normalize_manual_target_scope(
        target_scope
    )

    if target_scope not in {
        "Whole slide",
        "Manual region",
    }:
        raise ValueError(
            f"Unsupported target scope: {target_scope!r}."
        )

    normalized_bbox = _normalize_optional_bbox(
        bbox
    )

    aoi_by_id = {
        aoi.aoi_id: aoi
        for aoi in aois
    }

    match_scores = _extract_match_scores(
        selection_matches
    )

    options: list[
        ConfirmationTargetOption
    ] = []

    proposed_aoi_id: str | None = None

    if target_scope == "Manual region":
        content_aoi_ids = _deduplicate(
            selected_aoi_ids
        )

        for aoi_id in content_aoi_ids:
            if aoi_id == "whole_slide":
                continue

            aoi = aoi_by_id.get(aoi_id)

            if aoi is None:
                continue

            if proposed_aoi_id is None:
                proposed_aoi_id = aoi_id

            options.append(
                ConfirmationTargetOption(
                    aoi_id=aoi_id,
                    label=str(
                        aoi.name
                        or aoi.aoi_id
                    ),
                    source="manual_mapping",
                    text=aoi.text,
                    score=match_scores.get(
                        aoi_id
                    ),
                    is_proposed=(
                        aoi_id
                        == proposed_aoi_id
                    ),
                )
            )

        target_source = "manual_rectangle"

    else:
        proposed_aoi_id = "whole_slide"
        target_source = "whole_slide"

    whole_slide_aoi = aoi_by_id.get(
        "whole_slide"
    )

    whole_slide_text = (
        whole_slide_aoi.text
        if (
            whole_slide_aoi is not None
            and whole_slide_aoi.text.strip()
        )
        else slide_text
    )

    options.append(
        ConfirmationTargetOption(
            aoi_id="whole_slide",
            label="Whole slide",
            source="whole_slide",
            text=whole_slide_text,
            score=(
                1.0
                if target_scope
                == "Whole slide"
                else None
            ),
            is_proposed=(
                proposed_aoi_id
                == "whole_slide"
            ),
        )
    )

    return ManualConfirmationPreview(
        deck_id=deck_id,
        slide_id=slide_id,
        target_scope=target_scope,
        target_source=target_source,
        bbox=(
            normalized_bbox
            if target_scope
            == "Manual region"
            else None
        ),
        proposed_aoi_id=proposed_aoi_id,
        target_options=tuple(options),
        intent_resolution=intent_resolution,
    )


def assess_manual_confirmation(
    preview: ManualConfirmationPreview,
    *,
    selected_target_id: str,
) -> ConfirmationAssessment:
    """Assess the selected target before confirmation."""
    resolution = preview.intent_resolution

    if resolution is None:
        return ConfirmationAssessment(
            ready=False,
            status="blocked",
            message=(
                "Enter a command or select "
                "a quick action."
            ),
        )

    if not resolution.recognized:
        return ConfirmationAssessment(
            ready=False,
            status="blocked",
            message=(
                "The intent is unknown and cannot "
                "be confirmed."
            ),
        )

    try:
        option = preview.get_target_option(
            selected_target_id
        )
    except ValueError:
        return ConfirmationAssessment(
            ready=False,
            status="blocked",
            message=(
                "Select an available target."
            ),
        )

    if (
        option.source == "manual_mapping"
        and preview.bbox is None
    ):
        return ConfirmationAssessment(
            ready=False,
            status="blocked",
            message=(
                "The manual rectangle is missing."
            ),
        )

    if not option.text.strip():
        return ConfirmationAssessment(
            ready=False,
            status="blocked",
            message=(
                "The selected target has no usable "
                "text context. Select Whole slide "
                "or adjust the region."
            ),
        )

    warnings: list[str] = []

    if (
        resolution.intent == "compare"
        and len(
            [
                current
                for current
                in preview.target_options
                if current.source
                == "manual_mapping"
            ]
        )
        < 2
    ):
        warnings.append(
            "Compare currently has fewer than "
            "two mapped regions."
        )

    corrected = (
        selected_target_id
        != preview.proposed_aoi_id
    )

    if corrected:
        warnings.append(
            "The confirmed target differs from "
            "the initially proposed target."
        )

    if warnings:
        return ConfirmationAssessment(
            ready=True,
            status="warning",
            message=(
                "The interaction can be confirmed, "
                "but review the warnings."
            ),
            warnings=tuple(warnings),
        )

    return ConfirmationAssessment(
        ready=True,
        status="ready",
        message=(
            "Target, intent, and context are ready "
            "for explicit confirmation."
        ),
    )


def confirm_manual_interaction(
    preview: ManualConfirmationPreview,
    *,
    selected_target_id: str,
    interaction_id: str,
) -> ConfirmedManualInteraction:
    """Create the unified confirmed InteractionInput."""
    if not interaction_id.strip():
        raise ValueError(
            "interaction_id must not be blank."
        )

    assessment = assess_manual_confirmation(
        preview,
        selected_target_id=selected_target_id,
    )

    if not assessment.ready:
        raise ValueError(
            assessment.message
        )

    resolution = preview.intent_resolution

    if resolution is None:
        raise ValueError(
            "Intent resolution is unavailable."
        )

    option = preview.get_target_option(
        selected_target_id
    )

    corrected = (
        selected_target_id
        != preview.proposed_aoi_id
    )

    if option.source == "whole_slide":
        target = TargetInput(
            source="whole_slide",
            slide_id=preview.slide_id,
            selected_aoi_id="whole_slide",
        )

    else:
        if preview.bbox is None:
            raise ValueError(
                "Manual rectangle bbox is unavailable."
            )

        alternatives = tuple(
            TargetCandidate(
                aoi_id=current.aoi_id,
                score=_candidate_score(
                    current
                ),
                evidence=(
                    "manual rectangle AOI mapping",
                ),
            )
            for current
            in preview.target_options
            if current.source
            == "manual_mapping"
        )

        target = TargetInput(
            source="manual_rectangle",
            slide_id=preview.slide_id,
            bbox=preview.bbox,
            selected_aoi_id=(
                selected_target_id
            ),
            alternatives=alternatives,
        )

    confirmation_source = (
        "manual_correction"
        if corrected
        else "explicit_user_confirmation"
    )

    confirmation = ConfirmationInput(
        confirmed=True,
        source=confirmation_source,
        confirmed_aoi_id=(
            selected_target_id
        ),
        corrected_from_aoi_id=(
            preview.proposed_aoi_id
            if corrected
            else None
        ),
    )

    interaction = InteractionInput(
        interaction_id=interaction_id,
        deck_id=preview.deck_id,
        slide_id=preview.slide_id,
        mode="manual",
        target=target,
        intent=resolution.intent_input,
        confirmation=confirmation,
        metadata={
            "privacy_mode": (
                "camera_and_microphone_disabled"
            ),
            "target_source_before_confirmation": (
                preview.target_source
            ),
            "confirmed_context": option.text,
            "intent_source": (
                resolution.intent_input.source
            ),
            "confirmation_schema_version": (
                "1.0"
            ),
        },
    )

    return ConfirmedManualInteraction(
        interaction=interaction,
        selected_target=option,
        proposed_aoi_id=(
            preview.proposed_aoi_id
        ),
        corrected=corrected,
        confirmed_context=option.text,
    )


def _extract_match_scores(
    selection_matches: Sequence[
        Mapping[str, Any]
    ],
) -> dict[str, float]:
    scores: dict[str, float] = {}

    for item in selection_matches:
        aoi_id = str(
            item.get("aoi_id", "")
        ).strip()

        if not aoi_id:
            continue

        raw_score = item.get("score")

        if raw_score is None:
            continue

        score = float(raw_score)
        scores[aoi_id] = max(
            0.0,
            min(1.0, score),
        )

    return scores


def _normalize_optional_bbox(
    bbox: Sequence[float] | None,
) -> tuple[
    float,
    float,
    float,
    float,
] | None:
    if bbox is None:
        return None

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
            "bbox must be normalized to [0, 1]."
        )

    x_min, y_min, x_max, y_max = values

    if (
        x_min >= x_max
        or y_min >= y_max
    ):
        raise ValueError(
            "bbox requires x_min < x_max "
            "and y_min < y_max."
        )

    return values


def _deduplicate(
    values: Sequence[str],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = str(value).strip()

        if (
            normalized
            and normalized not in seen
        ):
            seen.add(normalized)
            result.append(normalized)

    return result


def _candidate_score(
    option: ConfirmationTargetOption,
) -> float:
    if option.score is not None:
        return option.score

    if option.is_proposed:
        return 1.0

    return 0.5
