"""Reusable system pipeline for one AttentiveSlides interaction."""

from __future__ import annotations

import time
from dataclasses import asdict, replace
from pathlib import Path

from modules.common.schemas import (
    AOI,
    GazePrediction,
    InteractionLogEvent,
    InteractionResult,
    LearningState,
    ResolvedQuery,
    Transcript,
    TutorResponse,
    UIState,
)
from modules.interaction.intent_parser import parse_intent
from modules.interaction.interaction_history import InteractionHistory
from modules.interaction.reference_resolver import resolve_reference
from modules.logging.interaction_logger import InteractionLogger
from modules.tutor.context_retriever import MockDeckStore
from modules.tutor.tutor_agent import TutorAgent


def run_interaction(
    transcript: str,
    gaze_prediction: GazePrediction,
    learning_state: LearningState,
    deck_id: str = "mock_deck",
    slide_id: int = 5,
    confirmed_aoi_id: str | None = None,
    history: InteractionHistory | None = None,
    deck_store: MockDeckStore | None = None,
    tutor: TutorAgent | None = None,
    logger: InteractionLogger | None = None,
) -> InteractionResult:
    """Run parser, resolver, confirmation gate, tutor, UI state, and logging."""

    start = time.perf_counter()
    deck_state = deck_store or MockDeckStore()
    aois = deck_state.get_aois(slide_id)
    _validate_deck(deck_id, deck_state)
    _validate_confirmed_aoi(confirmed_aoi_id, aois)

    interaction_history = history if history is not None else InteractionHistory()
    intent_result = parse_intent(Transcript(transcript))
    predicted_query = resolve_reference(
        intent_result=intent_result,
        gaze_prediction=gaze_prediction,
        learning_state=learning_state,
        aois=aois,
        history=interaction_history,
        deck_id=deck_state.deck_id,
    )

    resolved_query = _apply_confirmation(
        predicted_query=predicted_query,
        confirmed_aoi_id=confirmed_aoi_id,
        predicted_aoi_id=gaze_prediction.predicted_aoi_id,
    )
    if _is_pending_confirmation(predicted_query, confirmed_aoi_id):
        tutor_response = _pending_confirmation_response(predicted_query, aois)
    else:
        tutor_agent = tutor or TutorAgent()
        tutor_response = tutor_agent.answer(
            resolved_query,
            deck_state=deck_state,
            history=interaction_history,
        )

    latency_ms = (time.perf_counter() - start) * 1000
    log_event = _build_log_event(
        resolved_query=resolved_query,
        tutor_response=tutor_response,
        gaze_prediction=gaze_prediction,
        predicted_query=predicted_query,
        confirmed_aoi_id=confirmed_aoi_id,
        latency_ms=latency_ms,
    )
    ui_state = _build_ui_state(
        resolved_query=resolved_query,
        tutor_response=tutor_response,
        aois=aois,
        learning_state=learning_state,
        pending_confirmation=_is_pending_confirmation(predicted_query, confirmed_aoi_id),
    )

    if logger:
        logger.log_interaction(log_event)
    interaction_history.add(log_event)

    return InteractionResult(
        intent_result=intent_result,
        resolved_query=resolved_query,
        tutor_response=tutor_response,
        log_event=log_event,
        ui_state=ui_state,
    )


def _apply_confirmation(
    predicted_query: ResolvedQuery,
    confirmed_aoi_id: str | None,
    predicted_aoi_id: str | None,
) -> ResolvedQuery:
    if confirmed_aoi_id is None:
        return predicted_query

    evidence = list(predicted_query.evidence)
    evidence.append(f"user confirmed AOI = {confirmed_aoi_id}")
    if confirmed_aoi_id != predicted_aoi_id:
        evidence.append(f"user corrected predicted AOI from {predicted_aoi_id} to {confirmed_aoi_id}")

    return replace(
        predicted_query,
        resolved_aoi_id=confirmed_aoi_id,
        target_confidence=1.0,
        needs_confirmation=False,
        confirmation_mode="none",
        evidence=evidence,
    )


def _is_pending_confirmation(
    predicted_query: ResolvedQuery,
    confirmed_aoi_id: str | None,
) -> bool:
    return predicted_query.needs_confirmation and confirmed_aoi_id is None


def _pending_confirmation_response(
    resolved_query: ResolvedQuery,
    aois: list[AOI],
) -> TutorResponse:
    return TutorResponse(
        query_id=resolved_query.query_id,
        response_mode="pending_confirmation",
        answer=_confirmation_message(resolved_query, aois),
        used_context={
            "slide_id": resolved_query.slide_id,
            "aoi_id": None,
            "aoi_text": "",
        },
        safety_notes=[
            "Final AOI-specific answer is gated until the user confirms or corrects the target.",
            "Observable learning-state signals are not treated as true emotion or cognition.",
        ],
    )


def _build_log_event(
    resolved_query: ResolvedQuery,
    tutor_response: TutorResponse,
    gaze_prediction: GazePrediction,
    predicted_query: ResolvedQuery,
    confirmed_aoi_id: str | None,
    latency_ms: float,
) -> InteractionLogEvent:
    if predicted_query.needs_confirmation and confirmed_aoi_id is None:
        user_corrected = None
    else:
        user_corrected = False
    if confirmed_aoi_id is not None:
        user_corrected = confirmed_aoi_id != gaze_prediction.predicted_aoi_id

    return InteractionLogEvent(
        query_id=resolved_query.query_id,
        timestamp=time.time(),
        deck_id=resolved_query.deck_id,
        slide_id=resolved_query.slide_id,
        transcript=resolved_query.transcript,
        intent=resolved_query.intent,
        predicted_aoi_id=gaze_prediction.predicted_aoi_id,
        resolved_aoi_id=resolved_query.resolved_aoi_id,
        confirmed_aoi_id=confirmed_aoi_id,
        target_confidence=resolved_query.target_confidence,
        needs_confirmation=resolved_query.needs_confirmation,
        confirmation_mode=resolved_query.confirmation_mode,
        user_corrected=user_corrected,
        adaptive_strategy=resolved_query.adaptive_strategy,
        response_mode=tutor_response.response_mode,
        latency_ms=round(latency_ms, 2),
    )


def _build_ui_state(
    resolved_query: ResolvedQuery,
    tutor_response: TutorResponse,
    aois: list[AOI],
    learning_state: LearningState,
    pending_confirmation: bool,
) -> UIState:
    response_payload = {
        "response_mode": tutor_response.response_mode,
        "answer": None if pending_confirmation else tutor_response.answer,
        "active_recall_question": None if pending_confirmation else tutor_response.active_recall_question,
        "adaptive_suggestion": tutor_response.adaptive_suggestion,
        "safety_notes": tutor_response.safety_notes,
    }

    return UIState(
        slide_id=resolved_query.slide_id,
        aois=[asdict(aoi) for aoi in aois],
        highlighted_aoi_id=resolved_query.resolved_aoi_id if not pending_confirmation else None,
        confirmation_mode=resolved_query.confirmation_mode,
        confirmation_message=_confirmation_message(resolved_query, aois) if pending_confirmation else None,
        candidate_targets=_candidate_targets(resolved_query, aois),
        evidence=list(resolved_query.evidence),
        learning_state_summary=_learning_state_summary(learning_state),
        transcript=resolved_query.transcript,
        intent=resolved_query.intent,
        response=response_payload,
    )


def _candidate_targets(resolved_query: ResolvedQuery, aois: list[AOI]) -> list[dict[str, object]]:
    candidates = list(resolved_query.alternative_targets)
    if resolved_query.resolved_aoi_id and not any(
        candidate.get("aoi_id") == resolved_query.resolved_aoi_id for candidate in candidates
    ):
        candidates.insert(0, {"aoi_id": resolved_query.resolved_aoi_id, "score": resolved_query.target_confidence})

    if resolved_query.confirmation_mode == "click_required" and not candidates:
        candidates = [{"aoi_id": aoi.aoi_id, "score": None} for aoi in aois]

    names = {aoi.aoi_id: aoi.name or aoi.aoi_id for aoi in aois}
    return [
        {
            "aoi_id": candidate.get("aoi_id"),
            "name": names.get(str(candidate.get("aoi_id")), str(candidate.get("aoi_id"))),
            "score": candidate.get("score"),
        }
        for candidate in candidates
    ]


def _confirmation_message(resolved_query: ResolvedQuery, aois: list[AOI]) -> str:
    if resolved_query.confirmation_mode == "confirm_one" and resolved_query.resolved_aoi_id:
        target_name = _aoi_name(resolved_query.resolved_aoi_id, aois)
        return f"我理解你指的是 {target_name}。请确认后我再继续讲解。"
    if resolved_query.confirmation_mode == "choose_top2":
        targets = ", ".join(
            _aoi_name(str(candidate.get("aoi_id")), aois)
            for candidate in resolved_query.alternative_targets[:2]
        )
        return f"我不完全确定你指的是哪一块。请在这些候选中选择：{targets}。"
    return "我还不能可靠确定你指的是哪一块。请点击一个区域，或选择整页。"


def _aoi_name(aoi_id: str, aois: list[AOI]) -> str:
    for aoi in aois:
        if aoi.aoi_id == aoi_id:
            return aoi.name or aoi.aoi_id
    return aoi_id


def _learning_state_summary(learning_state: LearningState) -> dict[str, object]:
    return {
        "face_detected": learning_state.face_detected,
        "screen_facing_score": learning_state.screen_facing_score,
        "yawn_count_last_3min": learning_state.yawn_count_last_3min,
        "eyes_closed": learning_state.eyes_closed,
        "head_down": learning_state.head_down,
        "fatigue_signal_score": learning_state.fatigue_signal_score,
        "possible_review_needed": learning_state.possible_review_needed,
    }


def _validate_deck(deck_id: str, deck_store: MockDeckStore) -> None:
    if deck_id != deck_store.deck_id:
        raise ValueError(f"Unsupported deck_id {deck_id!r}; loaded deck is {deck_store.deck_id!r}.")


def _validate_confirmed_aoi(confirmed_aoi_id: str | None, aois: list[AOI]) -> None:
    if confirmed_aoi_id is None:
        return
    valid_ids = {aoi.aoi_id for aoi in aois}
    if confirmed_aoi_id not in valid_ids:
        raise ValueError(f"confirmed_aoi_id {confirmed_aoi_id!r} is not in the current slide AOIs.")


def load_interaction_log(log_path: str | Path) -> list[dict[str, object]]:
    """Small helper for demos/tests that need to inspect a JSONL log."""

    path = Path(log_path)
    if not path.exists():
        return []
    import json

    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]
