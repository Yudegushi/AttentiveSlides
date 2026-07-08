"""Reference resolution for gaze-grounded slide tutoring."""

from __future__ import annotations

from itertools import count

from modules.common.schemas import (
    AOI,
    GazePrediction,
    IntentResult,
    LearningState,
    ResolvedQuery,
)
from modules.interaction.adaptive_policy import select_adaptive_strategy
from modules.interaction.interaction_history import InteractionHistory


_QUERY_COUNTER = count(1)


def resolve_reference(
    intent_result: IntentResult,
    gaze_prediction: GazePrediction,
    learning_state: LearningState,
    aois: list[AOI],
    history: InteractionHistory | None = None,
    deck_id: str = "mock_deck",
    query_id: str | None = None,
) -> ResolvedQuery:
    aoi_ids = {aoi.aoi_id for aoi in aois}
    evidence: list[str] = [f"intent = {intent_result.intent}"]
    alternative_targets = _normalized_alternatives(gaze_prediction)

    resolved_aoi_id: str | None = None
    target_confidence = 0.0
    confirmation_mode = "click_required"

    if intent_result.explicit_target_hint:
        resolved_aoi_id = _valid_or_none(intent_result.explicit_target_hint, aoi_ids)
        target_confidence = 1.0 if resolved_aoi_id else 0.0
        confirmation_mode = "none" if resolved_aoi_id else "click_required"
        evidence.append(f"explicit target hint = {intent_result.explicit_target_hint}")
    elif intent_result.intent == "summarize" and "whole_slide" in aoi_ids:
        resolved_aoi_id = "whole_slide"
        target_confidence = 1.0
        confirmation_mode = "none"
        evidence.append("summarize intent uses whole_slide")
    elif intent_result.has_deictic_reference:
        resolved_aoi_id = _valid_or_none(gaze_prediction.predicted_aoi_id, aoi_ids)
        target_confidence = gaze_prediction.confidence if resolved_aoi_id else 0.0
        confirmation_mode = _confirmation_mode(target_confidence)
        evidence.extend(
            [
                "transcript includes deictic reference",
                f"gaze_grid = {gaze_prediction.gaze_grid}",
                f"predicted_aoi = {gaze_prediction.predicted_aoi_id}",
                f"stable_duration = {gaze_prediction.stable_duration_sec:.1f}s",
            ]
        )
        if confirmation_mode == "click_required":
            resolved_aoi_id = None
    elif "whole_slide" in aoi_ids:
        resolved_aoi_id = "whole_slide"
        target_confidence = 0.65
        confirmation_mode = "confirm_one"
        evidence.append("no target reference; falling back to whole_slide")

    adaptive_strategy = select_adaptive_strategy(
        learning_state=learning_state,
        intent_result=intent_result,
        history=history,
        resolved_aoi_id=resolved_aoi_id,
        stable_duration_sec=gaze_prediction.stable_duration_sec,
    )

    needs_confirmation = confirmation_mode != "none"

    return ResolvedQuery(
        query_id=query_id or f"q_{next(_QUERY_COUNTER):03d}",
        deck_id=deck_id,
        slide_id=gaze_prediction.slide_id,
        transcript=intent_result.transcript,
        intent=intent_result.intent,
        resolved_aoi_id=resolved_aoi_id,
        target_confidence=round(target_confidence, 3),
        needs_confirmation=needs_confirmation,
        confirmation_mode=confirmation_mode,
        adaptive_strategy=adaptive_strategy,
        evidence=evidence,
        alternative_targets=alternative_targets,
    )


def _confirmation_mode(confidence: float) -> str:
    if confidence >= 0.70:
        return "confirm_one"
    if confidence >= 0.45:
        return "choose_top2"
    return "click_required"


def _valid_or_none(aoi_id: str | None, aoi_ids: set[str]) -> str | None:
    if aoi_id in aoi_ids:
        return aoi_id
    return None


def _normalized_alternatives(gaze_prediction: GazePrediction) -> list[dict[str, object]]:
    if gaze_prediction.alternative_targets:
        return gaze_prediction.alternative_targets
    if gaze_prediction.predicted_aoi_id:
        return [
            {
                "aoi_id": gaze_prediction.predicted_aoi_id,
                "score": round(gaze_prediction.confidence, 3),
            }
        ]
    return []
