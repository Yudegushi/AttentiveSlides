"""View-model helpers for the local AttentiveSlides UI demo."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from modules.common.schemas import InteractionResult
from modules.logging.interaction_logger import InteractionLogger
from modules.system.adapters import (
    MockManifestSlideProvider,
    ScenarioSensingProvider,
    ScenarioTranscriptProvider,
    build_pipeline_input_bundle,
    run_interaction_from_bundle,
)
from modules.system.scenarios import InteractionScenario


EXPECTED_FIELDS = (
    "intent",
    "resolved_aoi_id",
    "confirmation_mode",
    "adaptive_strategy",
    "response_mode",
    "confirmed_aoi_id",
    "user_corrected",
)


def run_scenario_turn(
    scenario: InteractionScenario,
    confirmed_aoi_id: str | None = None,
    logger: InteractionLogger | None = None,
) -> InteractionResult:
    """Run one UI demo turn from a scenario and optional user-confirmed AOI."""

    bundle = build_pipeline_input_bundle(
        slide_provider=MockManifestSlideProvider(),
        transcript_provider=ScenarioTranscriptProvider(scenario),
        sensing_provider=ScenarioSensingProvider(scenario),
        slide_id=scenario.gaze_prediction.slide_id,
    )
    return run_interaction_from_bundle(
        bundle,
        confirmed_aoi_id=confirmed_aoi_id,
        logger=logger,
    )


def build_interaction_view_model(
    result: InteractionResult,
    scenario: InteractionScenario | None = None,
) -> dict[str, Any]:
    """Convert an interaction result into stable data for Streamlit rendering."""

    actual = _actual_fields(result)
    expected = dict(scenario.expected) if scenario else {}
    return {
        "scenario_name": scenario.name if scenario else "manual input",
        "slide_id": result.ui_state.slide_id,
        "transcript": result.ui_state.transcript,
        "intent": result.ui_state.intent,
        "pending_confirmation": result.tutor_response.response_mode == "pending_confirmation",
        "confirmation_mode": result.ui_state.confirmation_mode,
        "confirmation_message": result.ui_state.confirmation_message,
        "confirmation_options": _confirmation_options(result),
        "highlighted_aoi_id": result.ui_state.highlighted_aoi_id,
        "aois": _aoi_display_items(result),
        "evidence": list(result.ui_state.evidence),
        "learning_state_summary": dict(result.ui_state.learning_state_summary),
        "response": dict(result.ui_state.response),
        "actual": actual,
        "expected": expected,
        "expected_actual": _expected_actual(expected, actual),
        "log_event": result.log_event.to_dict(),
    }


def _confirmation_options(result: InteractionResult) -> list[dict[str, Any]]:
    if result.ui_state.confirmation_mode == "click_required":
        candidate_scores = {
            str(candidate.get("aoi_id")): candidate.get("score") for candidate in result.ui_state.candidate_targets
        }
        return [
            {
                "aoi_id": aoi["aoi_id"],
                "name": aoi.get("name") or aoi["aoi_id"],
                "score": candidate_scores.get(str(aoi["aoi_id"])),
            }
            for aoi in result.ui_state.aois
        ]
    if result.ui_state.candidate_targets:
        return [dict(candidate) for candidate in result.ui_state.candidate_targets]
    return []


def _aoi_display_items(result: InteractionResult) -> list[dict[str, Any]]:
    candidate_ids = {str(candidate["aoi_id"]) for candidate in _confirmation_options(result)}
    return [
        {
            **dict(aoi),
            "is_candidate": aoi["aoi_id"] in candidate_ids,
            "is_highlighted": aoi["aoi_id"] == result.ui_state.highlighted_aoi_id,
        }
        for aoi in result.ui_state.aois
    ]


def _actual_fields(result: InteractionResult) -> dict[str, Any]:
    return {
        "intent": result.resolved_query.intent,
        "resolved_aoi_id": result.resolved_query.resolved_aoi_id,
        "confirmation_mode": result.resolved_query.confirmation_mode,
        "adaptive_strategy": result.resolved_query.adaptive_strategy,
        "response_mode": result.tutor_response.response_mode,
        "confirmed_aoi_id": result.log_event.confirmed_aoi_id,
        "user_corrected": result.log_event.user_corrected,
    }


def _expected_actual(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields = [field for field in EXPECTED_FIELDS if field in expected or field in actual]
    return {
        field: {
            "expected": expected.get(field),
            "actual": actual.get(field),
            "matches": expected.get(field) == actual.get(field) if field in expected else None,
        }
        for field in fields
    }


def scenario_to_dict(scenario: InteractionScenario) -> dict[str, Any]:
    """Serialize a scenario for debug panels without exposing dataclass internals."""

    return {
        "name": scenario.name,
        "transcript": scenario.transcript,
        "gaze_prediction": asdict(scenario.gaze_prediction),
        "learning_state": asdict(scenario.learning_state),
        "confirmed_aoi_id": scenario.confirmed_aoi_id,
        "expected": dict(scenario.expected),
    }
