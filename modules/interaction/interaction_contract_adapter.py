"""Resolve unified interaction contracts into existing ResolvedQuery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from modules.common.interaction_contracts import (
    InteractionInput,
)
from modules.common.schemas import (
    AOI,
    IntentResult,
    LearningState,
    ResolvedQuery,
)
from modules.interaction.adaptive_policy import (
    select_adaptive_strategy,
)
from modules.interaction.intent_parser import (
    parse_intent,
)
from modules.interaction.interaction_history import (
    InteractionHistory,
)


@dataclass(frozen=True)
class InteractionProvenance:
    """Structured input provenance retained for future XAI."""

    interaction_mode: str
    target_source: str
    intent_source: str
    confirmation_source: str | None

    selected_bbox: list[float] | None
    proposed_aoi_id: str | None
    confirmed_aoi_id: str | None

    source_confidence: float | None
    target_confidence: float
    user_corrected: bool | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InteractionResolution:
    """Unified interaction resolution result."""

    interaction: InteractionInput
    intent_result: IntentResult
    resolved_query: ResolvedQuery
    provenance: InteractionProvenance

    def to_dict(self) -> dict[str, Any]:
        return {
            "interaction": self.interaction.to_dict(),
            "intent_result": asdict(
                self.intent_result
            ),
            "resolved_query": asdict(
                self.resolved_query
            ),
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class _TargetProposal:
    aoi_id: str | None
    confidence: float
    confirmation_mode: str
    alternatives: list[dict[str, object]]


def resolve_interaction_input(
    interaction: InteractionInput,
    *,
    aois: list[AOI],
    learning_state: LearningState | None = None,
    history: InteractionHistory | None = None,
) -> InteractionResolution:
    """Convert a hardware-independent interaction into ResolvedQuery."""
    if not isinstance(interaction, InteractionInput):
        raise TypeError(
            "interaction must be an InteractionInput."
        )

    valid_aoi_ids = {
        aoi.aoi_id
        for aoi in aois
    }

    _validate_contract_aoi_ids(
        interaction,
        valid_aoi_ids,
    )

    intent_result = _resolve_intent(
        interaction
    )

    proposal = _propose_target(
        interaction,
        valid_aoi_ids,
    )

    (
        resolved_aoi_id,
        target_confidence,
        needs_confirmation,
        confirmation_mode,
        confirmed_aoi_id,
        user_corrected,
    ) = _apply_confirmation(
        interaction,
        proposal,
        valid_aoi_ids,
    )

    neutral_learning_state = (
        learning_state
        if learning_state is not None
        else LearningState()
    )

    stable_duration_sec = (
        interaction.target.stable_duration_sec
        if (
            interaction.target.source
            == "gaze_prediction"
        )
        else 0.0
    )

    adaptive_strategy = select_adaptive_strategy(
        learning_state=neutral_learning_state,
        intent_result=intent_result,
        history=history,
        resolved_aoi_id=resolved_aoi_id,
        stable_duration_sec=stable_duration_sec,
    )

    evidence = _build_evidence(
        interaction=interaction,
        proposal=proposal,
        resolved_aoi_id=resolved_aoi_id,
        user_corrected=user_corrected,
        learning_state_supplied=(
            learning_state is not None
        ),
    )

    resolved_query = ResolvedQuery(
        query_id=interaction.interaction_id,
        deck_id=interaction.deck_id,
        slide_id=interaction.slide_id,
        transcript=intent_result.transcript,
        intent=intent_result.intent,
        resolved_aoi_id=resolved_aoi_id,
        target_confidence=round(
            target_confidence,
            3,
        ),
        needs_confirmation=needs_confirmation,
        confirmation_mode=confirmation_mode,
        adaptive_strategy=adaptive_strategy,
        evidence=evidence,
        alternative_targets=(
            proposal.alternatives
        ),
    )

    provenance = InteractionProvenance(
        interaction_mode=interaction.mode,
        target_source=interaction.target.source,
        intent_source=interaction.intent.source,
        confirmation_source=(
            interaction.confirmation.source
        ),
        selected_bbox=(
            list(interaction.target.bbox)
            if interaction.target.bbox
            is not None
            else None
        ),
        proposed_aoi_id=proposal.aoi_id,
        confirmed_aoi_id=confirmed_aoi_id,
        source_confidence=(
            interaction.intent.source_confidence
        ),
        target_confidence=round(
            target_confidence,
            3,
        ),
        user_corrected=user_corrected,
    )

    return InteractionResolution(
        interaction=interaction,
        intent_result=intent_result,
        resolved_query=resolved_query,
        provenance=provenance,
    )


def _resolve_intent(
    interaction: InteractionInput,
) -> IntentResult:
    intent_input = interaction.intent

    parsed = parse_intent(
        intent_input.text
        or intent_input.explicit_intent
        or ""
    )

    if intent_input.explicit_intent is None:
        return parsed

    transcript = (
        intent_input.text.strip()
        or intent_input.explicit_intent
    )

    return IntentResult(
        intent=intent_input.explicit_intent,
        confidence=(
            1.0
            if intent_input.source == "ui_action"
            else parsed.confidence
        ),
        has_deictic_reference=(
            parsed.has_deictic_reference
        ),
        explicit_target_hint=(
            parsed.explicit_target_hint
        ),
        transcript=transcript,
    )


def _propose_target(
    interaction: InteractionInput,
    valid_aoi_ids: set[str],
) -> _TargetProposal:
    target = interaction.target

    alternatives = [
        candidate.to_dict()
        for candidate in target.alternatives
    ]

    if target.source == "whole_slide":
        return _TargetProposal(
            aoi_id="whole_slide",
            confidence=1.0,
            confirmation_mode="confirm_one",
            alternatives=[
                {
                    "aoi_id": "whole_slide",
                    "score": 1.0,
                    "evidence": [
                        "learner selected whole slide"
                    ],
                }
            ],
        )

    if target.source == "manual_aoi":
        return _TargetProposal(
            aoi_id=target.selected_aoi_id,
            confidence=1.0,
            confirmation_mode="confirm_one",
            alternatives=_ensure_primary_candidate(
                alternatives,
                target.selected_aoi_id,
                1.0,
                "learner selected AOI",
            ),
        )

    if target.source == "manual_rectangle":
        proposed_aoi_id = (
            target.selected_aoi_id
        )

        proposed_confidence = 1.0

        if (
            proposed_aoi_id is None
            and alternatives
        ):
            first = alternatives[0]
            proposed_aoi_id = str(
                first["aoi_id"]
            )
            proposed_confidence = float(
                first["score"]
            )

        if proposed_aoi_id is None:
            mode = "click_required"
        elif len(alternatives) >= 2:
            mode = "choose_top2"
        else:
            mode = "confirm_one"

        return _TargetProposal(
            aoi_id=proposed_aoi_id,
            confidence=proposed_confidence,
            confirmation_mode=mode,
            alternatives=_ensure_primary_candidate(
                alternatives,
                proposed_aoi_id,
                proposed_confidence,
                "manual rectangle mapping",
            ),
        )

    predicted_aoi_id = (
        target.predicted_aoi_id
    )
    confidence = target.confidence or 0.0

    if predicted_aoi_id not in valid_aoi_ids:
        predicted_aoi_id = None
        confidence = 0.0

    mode = _confidence_confirmation_mode(
        confidence
    )

    if mode == "click_required":
        resolved_proposal = None
    else:
        resolved_proposal = predicted_aoi_id

    return _TargetProposal(
        aoi_id=resolved_proposal,
        confidence=confidence,
        confirmation_mode=mode,
        alternatives=_ensure_primary_candidate(
            alternatives,
            predicted_aoi_id,
            confidence,
            "gaze prediction",
        ),
    )


def _apply_confirmation(
    interaction: InteractionInput,
    proposal: _TargetProposal,
    valid_aoi_ids: set[str],
) -> tuple[
    str | None,
    float,
    bool,
    str,
    str | None,
    bool | None,
]:
    confirmation = interaction.confirmation

    if not confirmation.confirmed:
        return (
            proposal.aoi_id,
            proposal.confidence,
            True,
            proposal.confirmation_mode,
            None,
            None,
        )

    confirmed_aoi_id = (
        confirmation.confirmed_aoi_id
        or proposal.aoi_id
    )

    if confirmed_aoi_id is None:
        raise ValueError(
            "Confirmed interaction has no resolvable AOI."
        )

    if confirmed_aoi_id not in valid_aoi_ids:
        raise ValueError(
            f"confirmed_aoi_id "
            f"{confirmed_aoi_id!r} is not in "
            "the current slide AOIs."
        )

    user_corrected = (
        confirmation.source
        == "manual_correction"
        or confirmed_aoi_id
        != proposal.aoi_id
    )

    if (
        confirmation.source
        == "automatic_high_confidence"
    ):
        confidence = proposal.confidence
    else:
        confidence = 1.0

    return (
        confirmed_aoi_id,
        confidence,
        False,
        "none",
        confirmed_aoi_id,
        user_corrected,
    )


def _build_evidence(
    *,
    interaction: InteractionInput,
    proposal: _TargetProposal,
    resolved_aoi_id: str | None,
    user_corrected: bool | None,
    learning_state_supplied: bool,
) -> list[str]:
    evidence = [
        (
            "interaction mode = "
            f"{interaction.mode}"
        ),
        (
            "target source = "
            f"{interaction.target.source}"
        ),
        (
            "intent source = "
            f"{interaction.intent.source}"
        ),
        (
            "resolved intent = "
            f"{interaction.intent.explicit_intent or 'parsed'}"
        ),
    ]

    if interaction.target.bbox is not None:
        bbox = ", ".join(
            f"{value:.3f}"
            for value in interaction.target.bbox
        )
        evidence.append(
            f"manual bbox = [{bbox}]"
        )

    evidence.append(
        f"proposed AOI = {proposal.aoi_id}"
    )
    evidence.append(
        f"resolved AOI = {resolved_aoi_id}"
    )

    if interaction.confirmation.confirmed:
        evidence.append(
            "confirmation source = "
            f"{interaction.confirmation.source}"
        )

    if user_corrected:
        evidence.append(
            "learner corrected the proposed AOI"
        )

    if learning_state_supplied:
        evidence.append(
            "adaptive policy used supplied "
            "observable learning-state signals"
        )
    else:
        evidence.append(
            "adaptive policy used neutral "
            "learning-state defaults"
        )

    return evidence


def _validate_contract_aoi_ids(
    interaction: InteractionInput,
    valid_aoi_ids: set[str],
) -> None:
    target = interaction.target
    confirmation = interaction.confirmation

    ids_to_validate = {
        target.selected_aoi_id,
        target.predicted_aoi_id,
        confirmation.confirmed_aoi_id,
        confirmation.corrected_from_aoi_id,
    }

    ids_to_validate.update(
        candidate.aoi_id
        for candidate in target.alternatives
    )

    invalid_ids = sorted(
        aoi_id
        for aoi_id in ids_to_validate
        if (
            aoi_id is not None
            and aoi_id not in valid_aoi_ids
        )
    )

    if invalid_ids:
        raise ValueError(
            "Interaction references AOIs not present "
            f"on the current slide: {invalid_ids}"
        )


def _ensure_primary_candidate(
    alternatives: list[dict[str, object]],
    primary_aoi_id: str | None,
    score: float,
    evidence: str,
) -> list[dict[str, object]]:
    if primary_aoi_id is None:
        return alternatives

    if any(
        candidate.get("aoi_id")
        == primary_aoi_id
        for candidate in alternatives
    ):
        return alternatives

    return [
        {
            "aoi_id": primary_aoi_id,
            "score": round(score, 3),
            "evidence": [evidence],
        },
        *alternatives,
    ]


def _confidence_confirmation_mode(
    confidence: float,
) -> str:
    if confidence >= 0.70:
        return "confirm_one"

    if confidence >= 0.45:
        return "choose_top2"

    return "click_required"
