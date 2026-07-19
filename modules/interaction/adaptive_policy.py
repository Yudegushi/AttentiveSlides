"""Adaptive response strategy selection from observable learning-state signals."""

from __future__ import annotations

from modules.common.schemas import AdaptiveStrategy, IntentResult, LearningState
from modules.interaction.interaction_history import InteractionHistory


def select_adaptive_strategy(
    learning_state: LearningState,
    intent_result: IntentResult,
    history: InteractionHistory | None,
    resolved_aoi_id: str | None,
    stable_duration_sec: float = 0.0,
) -> AdaptiveStrategy:
    if learning_state.screen_facing_score < 0.5:
        return "ask_confirmation"

    if learning_state.yawn_count_last_3min >= 2:
        return "short_recap"

    if history and resolved_aoi_id and history.same_aoi_question_count(resolved_aoi_id) >= 2:
        return "simpler_explanation"

    if intent_result.intent == "review" or learning_state.possible_review_needed:
        return "review_question"

    return "normal"
