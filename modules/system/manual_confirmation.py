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


@dataclass(frozen=True)
class ConfirmedTargetSelection:
    """Explicitly confirmed slide target, independent of intent."""

    deck_id: str
    slide_id: int
    target_scope: str
    target_source: str
    bbox: (
        tuple[
            float,
            float,
            float,
            float,
        ]
        | None
    )
    selected_target: ConfirmationTargetOption
    target_options: tuple[
        ConfirmationTargetOption,
        ...,
    ]
    proposed_aoi_id: str | None
    corrected: bool
    confirmed_context: str
    confirmation_source: str

    def to_dict(
        self,
    ) -> dict[str, Any]:
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
            "selected_target": (
                self.selected_target.to_dict()
            ),
            "target_options": [
                option.to_dict()
                for option in self.target_options
            ],
            "proposed_aoi_id": (
                self.proposed_aoi_id
            ),
            "corrected": self.corrected,
            "confirmed_context": (
                self.confirmed_context
            ),
            "confirmation_source": (
                self.confirmation_source
            ),
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




def _confirmation_target_option_from_dict(
    payload: Mapping[str, Any],
) -> ConfirmationTargetOption:
    score = payload.get(
        "score"
    )

    return ConfirmationTargetOption(
        aoi_id=str(
            payload["aoi_id"]
        ),
        label=str(
            payload["label"]
        ),
        source=str(
            payload["source"]
        ),
        text=str(
            payload.get(
                "text",
                "",
            )
        ),
        score=(
            None
            if score is None
            else float(score)
        ),
        is_proposed=bool(
            payload.get(
                "is_proposed",
                False,
            )
        ),
    )


def confirmed_target_selection_from_dict(
    payload: Mapping[str, Any],
) -> ConfirmedTargetSelection:
    """Restore a target stored in Streamlit session state."""

    selected_target = (
        _confirmation_target_option_from_dict(
            payload[
                "selected_target"
            ]
        )
    )

    target_options = tuple(
        _confirmation_target_option_from_dict(
            item
        )
        for item in payload.get(
            "target_options",
            [],
        )
    )

    bbox = _normalize_optional_bbox(
        payload.get(
            "bbox"
        )
    )

    return ConfirmedTargetSelection(
        deck_id=str(
            payload["deck_id"]
        ),
        slide_id=int(
            payload["slide_id"]
        ),
        target_scope=str(
            payload["target_scope"]
        ),
        target_source=str(
            payload["target_source"]
        ),
        bbox=bbox,
        selected_target=selected_target,
        target_options=target_options,
        proposed_aoi_id=(
            None
            if payload.get(
                "proposed_aoi_id"
            )
            is None
            else str(
                payload[
                    "proposed_aoi_id"
                ]
            )
        ),
        corrected=bool(
            payload.get(
                "corrected",
                False,
            )
        ),
        confirmed_context=str(
            payload.get(
                "confirmed_context",
                "",
            )
        ),
        confirmation_source=str(
            payload.get(
                "confirmation_source",
                (
                    "explicit_user_"
                    "confirmation"
                ),
            )
        ),
    )


def assess_target_confirmation(
    preview: ManualConfirmationPreview,
    *,
    selected_target_id: str,
) -> ConfirmationAssessment:
    """Assess only the target; intent is not required."""

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
        option.source
        == "manual_mapping"
        and preview.bbox is None
    ):
        return ConfirmationAssessment(
            ready=False,
            status="blocked",
            message=(
                "Select a region before confirming."
            ),
        )

    if not option.text.strip():
        return ConfirmationAssessment(
            ready=False,
            status="blocked",
            message=(
                "The selected target has no usable "
                "text context. Adjust the region or "
                "select the whole slide."
            ),
        )

    corrected = (
        selected_target_id
        != preview.proposed_aoi_id
    )

    if corrected:
        warning = (
            "The selected target differs from "
            "the initially proposed target."
        )

        return ConfirmationAssessment(
            ready=True,
            status="warning",
            message=warning,
            warnings=(
                warning,
            ),
        )

    return ConfirmationAssessment(
        ready=True,
        status="ready",
        message=(
            "The selected target is ready "
            "for confirmation."
        ),
    )


def confirm_target_selection(
    preview: ManualConfirmationPreview,
    *,
    selected_target_id: str,
) -> ConfirmedTargetSelection:
    """Confirm a target without requiring an intent."""

    assessment = assess_target_confirmation(
        preview,
        selected_target_id=(
            selected_target_id
        ),
    )

    if not assessment.ready:
        raise ValueError(
            assessment.message
        )

    option = preview.get_target_option(
        selected_target_id
    )

    corrected = (
        selected_target_id
        != preview.proposed_aoi_id
    )

    confirmation_source = (
        "manual_correction"
        if corrected
        else (
            "explicit_user_"
            "confirmation"
        )
    )

    return ConfirmedTargetSelection(
        deck_id=preview.deck_id,
        slide_id=preview.slide_id,
        target_scope=preview.target_scope,
        target_source=preview.target_source,
        bbox=preview.bbox,
        selected_target=option,
        target_options=(
            preview.target_options
        ),
        proposed_aoi_id=(
            preview.proposed_aoi_id
        ),
        corrected=corrected,
        confirmed_context=option.text,
        confirmation_source=(
            confirmation_source
        ),
    )


def bind_confirmed_target_to_intent(
    confirmed_target: ConfirmedTargetSelection,
    *,
    intent_resolution: ManualIntentResolution,
    interaction_id: str,
) -> ConfirmedManualInteraction:
    """Bind an intent only when the request is submitted."""

    if not interaction_id.strip():
        raise ValueError(
            "interaction_id must not be blank."
        )

    if not intent_resolution.recognized:
        raise ValueError(
            "The intent is unknown and "
            "cannot be submitted."
        )

    option = (
        confirmed_target.selected_target
    )

    if option.source == "whole_slide":
        target = TargetInput(
            source="whole_slide",
            slide_id=(
                confirmed_target.slide_id
            ),
            selected_aoi_id=(
                "whole_slide"
            ),
        )

    else:
        if confirmed_target.bbox is None:
            raise ValueError(
                "Manual rectangle bbox "
                "is unavailable."
            )

        alternatives = tuple(
            TargetCandidate(
                aoi_id=current.aoi_id,
                score=(
                    _candidate_score(
                        current
                    )
                ),
                evidence=(
                    (
                        "manual rectangle "
                        "AOI mapping"
                    ),
                ),
            )
            for current
            in confirmed_target.target_options
            if (
                current.source
                == "manual_mapping"
            )
        )

        target = TargetInput(
            source="manual_rectangle",
            slide_id=(
                confirmed_target.slide_id
            ),
            bbox=confirmed_target.bbox,
            selected_aoi_id=(
                option.aoi_id
            ),
            alternatives=alternatives,
        )

    confirmation = ConfirmationInput(
        confirmed=True,
        source=(
            confirmed_target
            .confirmation_source
        ),
        confirmed_aoi_id=(
            option.aoi_id
        ),
        corrected_from_aoi_id=(
            confirmed_target
            .proposed_aoi_id
            if confirmed_target.corrected
            else None
        ),
    )

    interaction = InteractionInput(
        interaction_id=interaction_id,
        deck_id=confirmed_target.deck_id,
        slide_id=(
            confirmed_target.slide_id
        ),
        mode="manual",
        target=target,
        intent=(
            intent_resolution.intent_input
        ),
        confirmation=confirmation,
        metadata={
            "privacy_mode": (
                "camera_and_microphone_optional"
            ),
            (
                "target_source_before_"
                "confirmation"
            ): confirmed_target.target_source,
            "confirmed_context": (
                confirmed_target
                .confirmed_context
            ),
            "intent_source": (
                intent_resolution
                .intent_input
                .source
            ),
            (
                "confirmation_schema_"
                "version"
            ): "2.0",
            "confirmation_scope": (
                "target_only"
            ),
        },
    )

    return ConfirmedManualInteraction(
        interaction=interaction,
        selected_target=option,
        proposed_aoi_id=(
            confirmed_target
            .proposed_aoi_id
        ),
        corrected=(
            confirmed_target.corrected
        ),
        confirmed_context=(
            confirmed_target
            .confirmed_context
        ),
    )
def assess_manual_confirmation(
    preview: ManualConfirmationPreview,
    *,
    selected_target_id: str,
) -> ConfirmationAssessment:
    """Backward-compatible target-plus-intent assessment."""

    target_assessment = (
        assess_target_confirmation(
            preview,
            selected_target_id=(
                selected_target_id
            ),
        )
    )

    if not target_assessment.ready:
        return target_assessment

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
                "The intent is unknown and "
                "cannot be confirmed."
            ),
        )

    warnings = list(
        target_assessment.warnings
    )

    if (
        resolution.intent == "compare"
        and len(
            [
                current
                for current
                in preview.target_options
                if (
                    current.source
                    == "manual_mapping"
                )
            ]
        )
        < 2
    ):
        warnings.append(
            "Compare currently has fewer "
            "than two mapped regions."
        )

    if warnings:
        return ConfirmationAssessment(
            ready=True,
            status="warning",
            message=(
                "The interaction can be "
                "submitted, but review "
                "the warnings."
            ),
            warnings=tuple(
                warnings
            ),
        )

    return ConfirmationAssessment(
        ready=True,
        status="ready",
        message=(
            "Target and intent are ready "
            "for submission."
        ),
    )


def confirm_manual_interaction(
    preview: ManualConfirmationPreview,
    *,
    selected_target_id: str,
    interaction_id: str,
) -> ConfirmedManualInteraction:
    """Backward-compatible combined helper."""

    assessment = assess_manual_confirmation(
        preview,
        selected_target_id=(
            selected_target_id
        ),
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

    confirmed_target = (
        confirm_target_selection(
            preview,
            selected_target_id=(
                selected_target_id
            ),
        )
    )

    return bind_confirmed_target_to_intent(
        confirmed_target,
        intent_resolution=resolution,
        interaction_id=interaction_id,
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
