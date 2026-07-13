"""Integrated public XAI for the complete AttentiveSlides pipeline.

The payload explains observable pipeline decisions only:

1. target acquisition and correction;
2. intent resolution;
3. answer grounding;
4. reliability and corrective control.

It never exposes hidden Chain-of-Thought, raw provider responses,
prompts, API credentials, or provider request identifiers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from modules.system.xai_view_model import (
    assert_public_xai_payload,
)


def build_integrated_pipeline_xai(
    *,
    target_scope: str,
    manual_bbox: Sequence[float] | None,
    selection_matches: Sequence[
        Mapping[str, Any]
    ],
    intent_result: Mapping[str, Any] | None,
    confirmed_interaction: (
        Mapping[str, Any] | None
    ),
    tutor_result: Mapping[str, Any] | None,
    llm_xai: Mapping[str, Any] | None,
    cloud_text_allowed: bool,
) -> dict[str, Any]:
    """Build one sanitized explanation for the complete pipeline."""
    interaction_wrapper = _as_mapping(
        confirmed_interaction
    )

    interaction = _extract_interaction(
        interaction_wrapper
    )

    target = _as_mapping(
        interaction.get("target")
    )

    intent_input = _as_mapping(
        interaction.get("intent")
    )

    confirmation = _as_mapping(
        interaction.get("confirmation")
    )

    resolved_intent_payload = _as_mapping(
        intent_result
    )

    parsed_intent = _as_mapping(
        resolved_intent_payload.get(
            "intent_result"
        )
    )

    tutor = _as_mapping(
        tutor_result
    )

    grounded_xai = _as_mapping(
        llm_xai
    )

    validation = _as_mapping(
        grounded_xai.get("validation")
    )

    telemetry = _as_mapping(
        grounded_xai.get("telemetry")
    )

    target_view = _build_target_view(
        target_scope=target_scope,
        manual_bbox=manual_bbox,
        selection_matches=selection_matches,
        interaction_wrapper=(
            interaction_wrapper
        ),
        target=target,
        confirmation=confirmation,
    )

    intent_view = _build_intent_view(
        intent_input=intent_input,
        parsed_intent=parsed_intent,
        resolution_payload=(
            resolved_intent_payload
        ),
    )

    answer_view = _build_answer_view(
        tutor=tutor,
        grounded_xai=grounded_xai,
    )

    reliability_view = _build_reliability_view(
        target_view=target_view,
        intent_view=intent_view,
        confirmation=confirmation,
        tutor=tutor,
        validation=validation,
        telemetry=telemetry,
        cloud_text_allowed=(
            cloud_text_allowed
        ),
    )

    pipeline = _build_pipeline_rows(
        target_view=target_view,
        intent_view=intent_view,
        confirmation=confirmation,
        tutor=tutor,
        validation=validation,
    )

    payload = {
        "schema_version": "1.0",
        "pipeline_status": (
            _derive_pipeline_status(
                pipeline
            )
        ),
        "questions": {
            "target": target_view,
            "intent": intent_view,
            "answer": answer_view,
            "reliability": reliability_view,
        },
        "pipeline": pipeline,
        "privacy": {
            "interaction_mode": "manual",
            "camera_enabled": False,
            "microphone_enabled": False,
            "raw_biometrics_collected": False,
            "cloud_text_allowed": (
                bool(cloud_text_allowed)
            ),
            "cloud_tutor_called": bool(
                tutor
            ),
            "raw_provider_response_exposed": (
                False
            ),
            "prompt_messages_exposed": False,
            "internal_reasoning_exposed": (
                False
            ),
        },
        "corrective_actions": (
            _build_corrective_actions(
                target_view=target_view,
                intent_view=intent_view,
                confirmation=confirmation,
                tutor=tutor,
                validation=validation,
                telemetry=telemetry,
                cloud_text_allowed=(
                    cloud_text_allowed
                ),
            )
        ),
    }

    assert_public_integrated_xai_payload(
        payload
    )

    return payload


def assert_public_integrated_xai_payload(
    payload: dict[str, Any],
) -> None:
    """Reject private or hidden-reasoning fields."""
    if not isinstance(payload, dict):
        raise TypeError(
            "Integrated XAI payload must be a dictionary."
        )

    assert_public_xai_payload(payload)

    forbidden = _find_forbidden_keys(
        payload
    )

    if forbidden:
        raise ValueError(
            "Integrated XAI payload contains "
            f"forbidden fields: "
            f"{sorted(forbidden)}"
        )


def _build_target_view(
    *,
    target_scope: str,
    manual_bbox: Sequence[float] | None,
    selection_matches: Sequence[
        Mapping[str, Any]
    ],
    interaction_wrapper: Mapping[str, Any],
    target: Mapping[str, Any],
    confirmation: Mapping[str, Any],
) -> dict[str, Any]:
    target_source = _safe_text(
        target.get("source")
    )

    if not target_source:
        if (
            target_scope == "Manual region"
            and manual_bbox is not None
        ):
            target_source = "manual_rectangle"
        elif target_scope == "Whole slide":
            target_source = "whole_slide"

    bbox = target.get("bbox")

    if bbox is None:
        bbox = manual_bbox

    normalized_bbox = _safe_bbox(
        bbox
    )

    selected_aoi_id = _safe_text(
        target.get("selected_aoi_id")
    )

    confirmed_aoi_id = _safe_text(
        confirmation.get(
            "confirmed_aoi_id"
        )
    )

    corrected_from = _safe_text(
        confirmation.get(
            "corrected_from_aoi_id"
        )
    )

    proposed_aoi_id = _safe_text(
        interaction_wrapper.get(
            "proposed_aoi_id"
        )
    )

    corrected = bool(
        interaction_wrapper.get(
            "corrected",
            False,
        )
    ) or bool(corrected_from)

    candidate_rows = _candidate_rows(
        selection_matches
    )

    acquired = bool(
        target_source
        and (
            target_source == "whole_slide"
            or normalized_bbox is not None
            or selected_aoi_id
            or confirmed_aoi_id
        )
    )

    if corrected:
        explanation = (
            "The system proposed "
            f"{proposed_aoi_id or corrected_from or 'another AOI'}, "
            "and the learner explicitly corrected "
            f"the target to "
            f"{confirmed_aoi_id or selected_aoi_id or 'the selected AOI'}."
        )

    elif target_source == "manual_rectangle":
        explanation = (
            "The learner drew a manual rectangle. "
            "Candidate AOIs were ranked using observable "
            "geometric overlap, and the selected AOI was "
            "presented for explicit confirmation."
        )

    elif target_source == "whole_slide":
        explanation = (
            "The learner selected the whole slide as the "
            "target rather than relying on gaze or another "
            "biometric signal."
        )

    else:
        explanation = (
            "No target has been acquired yet."
        )

    return {
        "question": "Why this target?",
        "status": (
            "ready"
            if acquired
            else "pending"
        ),
        "explanation": explanation,
        "target_scope": target_scope,
        "target_source": (
            target_source or None
        ),
        "bbox": (
            list(normalized_bbox)
            if normalized_bbox is not None
            else None
        ),
        "selected_aoi_id": (
            selected_aoi_id or None
        ),
        "proposed_aoi_id": (
            proposed_aoi_id or None
        ),
        "confirmed_aoi_id": (
            confirmed_aoi_id or None
        ),
        "corrected_from_aoi_id": (
            corrected_from or None
        ),
        "corrected_by_learner": corrected,
        "candidates": candidate_rows,
    }


def _build_intent_view(
    *,
    intent_input: Mapping[str, Any],
    parsed_intent: Mapping[str, Any],
    resolution_payload: Mapping[str, Any],
) -> dict[str, Any]:
    source = _safe_text(
        intent_input.get("source")
    )

    if not source:
        source = _safe_text(
            _as_mapping(
                resolution_payload.get(
                    "intent_input"
                )
            ).get("source")
        )

    command = _safe_text(
        intent_input.get("text")
    )

    if not command:
        command = _safe_text(
            _as_mapping(
                resolution_payload.get(
                    "intent_input"
                )
            ).get("text")
        )

    resolved_intent = _safe_text(
        parsed_intent.get("intent")
    )

    confidence = _optional_float(
        parsed_intent.get("confidence")
    )

    recognized_value = (
        resolution_payload.get(
            "recognized"
        )
    )

    if recognized_value is None:
        recognized = bool(
            resolved_intent
            and resolved_intent
            != "unknown"
        )
    else:
        recognized = bool(
            recognized_value
        )

    explicit_intent = _safe_text(
        _as_mapping(
            resolution_payload.get(
                "intent_input"
            )
        ).get("explicit_intent")
    )

    if source == "ui_action":
        explanation = (
            "The learner explicitly selected the "
            f"{resolved_intent or explicit_intent or 'requested'} "
            "operation through a Quick action."
        )

    elif source == "typed_text":
        explanation = (
            "The learner entered a typed command. "
            "The existing intent parser mapped the "
            f"observable text to "
            f"{resolved_intent or 'an unresolved intent'}."
        )

    else:
        explanation = (
            "No intent has been resolved yet."
        )

    provenance = resolution_payload.get(
        "provenance",
        [],
    )

    if not isinstance(
        provenance,
        (list, tuple),
    ):
        provenance = []

    return {
        "question": "Why this intent?",
        "status": (
            "ready"
            if recognized
            else "pending"
        ),
        "explanation": explanation,
        "source": source or None,
        "command": command or None,
        "resolved_intent": (
            resolved_intent or None
        ),
        "confidence": confidence,
        "recognized": recognized,
        "explicit_user_choice": (
            source == "ui_action"
        ),
        "has_deictic_reference": bool(
            parsed_intent.get(
                "has_deictic_reference",
                False,
            )
        ),
        "explicit_target_hint": (
            _safe_text(
                parsed_intent.get(
                    "explicit_target_hint"
                )
            )
            or None
        ),
        "provenance": [
            str(item)
            for item in provenance
        ],
    }


def _build_answer_view(
    *,
    tutor: Mapping[str, Any],
    grounded_xai: Mapping[str, Any],
) -> dict[str, Any]:
    answer = _safe_text(
        tutor.get("answer")
    )

    decision_summary = _safe_text(
        grounded_xai.get(
            "decision_summary"
        )
    )

    if not decision_summary:
        decision_summary = _safe_text(
            tutor.get(
                "decision_summary"
            )
        )

    claims = _claim_rows(
        grounded_xai.get("claims")
    )

    sources = _source_rows(
        grounded_xai.get("sources")
    )

    if answer:
        explanation = (
            decision_summary
            or (
                "The answer was generated from the "
                "confirmed slide context and evaluated "
                "against the available source IDs."
            )
        )
    else:
        explanation = (
            "No grounded tutor answer has been "
            "generated yet."
        )

    return {
        "question": "Why this answer?",
        "status": (
            "ready"
            if answer
            else "pending"
        ),
        "explanation": explanation,
        "response_mode": (
            _safe_text(
                tutor.get(
                    "response_mode"
                )
            )
            or None
        ),
        "answer_available": bool(answer),
        "claim_count": len(claims),
        "source_count": len(sources),
        "external_knowledge_used": bool(
            tutor.get(
                "external_knowledge_used",
                False,
            )
        ),
        "uncertainty_note": (
            _safe_text(
                tutor.get(
                    "uncertainty_note"
                )
            )
            or None
        ),
        "claims": claims,
        "sources": sources,
    }


def _build_reliability_view(
    *,
    target_view: Mapping[str, Any],
    intent_view: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    tutor: Mapping[str, Any],
    validation: Mapping[str, Any],
    telemetry: Mapping[str, Any],
    cloud_text_allowed: bool,
) -> dict[str, Any]:
    confirmed = bool(
        confirmation.get(
            "confirmed",
            False,
        )
    )

    answer_available = bool(
        tutor.get("answer")
    )

    is_valid_value = validation.get(
        "is_valid"
    )

    is_valid = (
        bool(is_valid_value)
        if is_valid_value is not None
        else None
    )

    coverage = _optional_float(
        validation.get(
            "citation_coverage"
        )
    )

    confirmed_aoi_cited_value = (
        validation.get(
            "confirmed_aoi_cited"
        )
    )

    confirmed_aoi_cited = (
        bool(
            confirmed_aoi_cited_value
        )
        if confirmed_aoi_cited_value
        is not None
        else None
    )

    fallback_used = bool(
        telemetry.get(
            "fallback_used",
            tutor.get(
                "fallback_used",
                False,
            ),
        )
    )

    retry_count = _safe_int(
        telemetry.get(
            "retry_count",
            tutor.get(
                "retry_count",
                0,
            ),
        )
    )

    uncertainty_note = _safe_text(
        tutor.get(
            "uncertainty_note"
        )
    )

    warnings: list[str] = []

    if fallback_used:
        warnings.append(
            "A deterministic fallback response "
            "was used instead of a validated API response."
        )

    if retry_count > 0:
        warnings.append(
            f"The provider call required "
            f"{retry_count} retry attempt(s)."
        )

    if (
        coverage is not None
        and coverage < 1.0
    ):
        warnings.append(
            "Not every educational claim has "
            "complete source coverage."
        )

    if confirmed_aoi_cited is False:
        warnings.append(
            "The confirmed AOI was not cited by "
            "the generated educational claims."
        )

    if uncertainty_note:
        warnings.append(
            "The tutor response contains an "
            "explicit uncertainty note."
        )

    if not cloud_text_allowed:
        warnings.append(
            "Cloud-text permission is disabled."
        )

    if not answer_available:
        reliability_level = "pending"
        summary = (
            "Reliability cannot be assessed until "
            "a grounded answer is generated."
        )

    elif is_valid is False:
        reliability_level = "unsupported"
        summary = (
            "Grounding validation did not pass. "
            "The answer should not be treated as "
            "fully supported by the selected context."
        )

    elif warnings:
        reliability_level = "caution"
        summary = (
            "The answer passed enough gates to be "
            "shown, but one or more reliability "
            "warnings require inspection."
        )

    elif is_valid is True:
        reliability_level = "supported"
        summary = (
            "The target and intent were explicitly "
            "confirmed, and the answer passed the "
            "configured grounding validation."
        )

    else:
        reliability_level = "pending"
        summary = (
            "Grounding validation information is "
            "not yet available."
        )

    checks = [
        {
            "check": "Target acquired",
            "status": (
                "pass"
                if target_view.get(
                    "status"
                )
                == "ready"
                else "pending"
            ),
        },
        {
            "check": "Intent recognized",
            "status": (
                "pass"
                if intent_view.get(
                    "recognized"
                )
                else "pending"
            ),
        },
        {
            "check": "Explicit confirmation",
            "status": (
                "pass"
                if confirmed
                else "pending"
            ),
        },
        {
            "check": "Grounded answer generated",
            "status": (
                "pass"
                if answer_available
                else "pending"
            ),
        },
        {
            "check": "Grounding validation",
            "status": (
                "pass"
                if is_valid is True
                else (
                    "fail"
                    if is_valid is False
                    else "pending"
                )
            ),
        },
        {
            "check": "Confirmed AOI cited",
            "status": (
                "pass"
                if confirmed_aoi_cited is True
                else (
                    "fail"
                    if confirmed_aoi_cited is False
                    else "pending"
                )
            ),
        },
    ]

    return {
        "question": (
            "How reliable is the pipeline?"
        ),
        "level": reliability_level,
        "summary": summary,
        "checks": checks,
        "warnings": warnings,
        "citation_coverage": coverage,
        "confirmed_aoi_cited": (
            confirmed_aoi_cited
        ),
        "validation_is_valid": is_valid,
        "fallback_used": fallback_used,
        "retry_count": retry_count,
        "provider": (
            _safe_text(
                telemetry.get("provider")
            )
            or _safe_text(
                tutor.get("provider")
            )
            or None
        ),
        "model": (
            _safe_text(
                telemetry.get("model")
            )
            or _safe_text(
                tutor.get("model")
            )
            or None
        ),
        "latency_ms": (
            _optional_float(
                telemetry.get(
                    "latency_ms"
                )
            )
            if telemetry
            else _optional_float(
                tutor.get(
                    "latency_ms"
                )
            )
        ),
    }


def _build_pipeline_rows(
    *,
    target_view: Mapping[str, Any],
    intent_view: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    tutor: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> list[dict[str, str]]:
    validation_value = validation.get(
        "is_valid"
    )

    return [
        {
            "stage": "Target acquisition",
            "status": (
                "complete"
                if target_view.get(
                    "status"
                )
                == "ready"
                else "pending"
            ),
        },
        {
            "stage": "Intent resolution",
            "status": (
                "complete"
                if intent_view.get(
                    "recognized"
                )
                else "pending"
            ),
        },
        {
            "stage": "User confirmation",
            "status": (
                "complete"
                if confirmation.get(
                    "confirmed"
                )
                else "pending"
            ),
        },
        {
            "stage": "Grounded generation",
            "status": (
                "complete"
                if tutor.get("answer")
                else "pending"
            ),
        },
        {
            "stage": "Grounding validation",
            "status": (
                "complete"
                if validation_value is True
                else (
                    "failed"
                    if validation_value is False
                    else "pending"
                )
            ),
        },
    ]


def _derive_pipeline_status(
    rows: Sequence[Mapping[str, str]],
) -> str:
    statuses = [
        row.get("status")
        for row in rows
    ]

    if "failed" in statuses:
        return "validation_failed"

    if all(
        status == "complete"
        for status in statuses
    ):
        return "complete"

    completed_count = sum(
        status == "complete"
        for status in statuses
    )

    if completed_count >= 3:
        return "ready_for_generation"

    if completed_count > 0:
        return "in_progress"

    return "not_started"


def _build_corrective_actions(
    *,
    target_view: Mapping[str, Any],
    intent_view: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    tutor: Mapping[str, Any],
    validation: Mapping[str, Any],
    telemetry: Mapping[str, Any],
    cloud_text_allowed: bool,
) -> list[str]:
    actions: list[str] = []

    if target_view.get("status") != "ready":
        actions.append(
            "Select the whole slide or draw a "
            "manual target rectangle."
        )

    if not intent_view.get("recognized"):
        actions.append(
            "Rewrite the command or select a "
            "Quick action."
        )

    if not confirmation.get(
        "confirmed"
    ):
        actions.append(
            "Inspect the target and intent, then "
            "confirm or correct them."
        )

    if not cloud_text_allowed:
        actions.append(
            "Enable cloud-text permission before "
            "requesting a cloud tutor response."
        )

    if (
        confirmation.get("confirmed")
        and not tutor.get("answer")
    ):
        actions.append(
            "Generate a grounded answer."
        )

    if validation.get(
        "is_valid"
    ) is False:
        actions.append(
            "Adjust the target context or command "
            "and regenerate the answer."
        )

    coverage = _optional_float(
        validation.get(
            "citation_coverage"
        )
    )

    if (
        coverage is not None
        and coverage < 1.0
    ):
        actions.append(
            "Inspect claims without complete "
            "source coverage."
        )

    if validation.get(
        "confirmed_aoi_cited"
    ) is False:
        actions.append(
            "Verify that the confirmed AOI contains "
            "the evidence needed for the question."
        )

    if telemetry.get(
        "fallback_used"
    ):
        actions.append(
            "Retry API generation when provider "
            "access is stable."
        )

    if not actions:
        actions.append(
            "No corrective action is currently required."
        )

    return actions


def _candidate_rows(
    selection_matches: Sequence[
        Mapping[str, Any]
    ],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for item in selection_matches:
        if not isinstance(
            item,
            Mapping,
        ):
            continue

        aoi_id = _safe_text(
            item.get("aoi_id")
        )

        if not aoi_id:
            continue

        rows.append(
            {
                "aoi_id": aoi_id,
                "aoi_type": (
                    _safe_text(
                        item.get(
                            "aoi_type"
                        )
                    )
                    or None
                ),
                "score": _optional_float(
                    item.get("score")
                ),
                "selection_coverage": (
                    _optional_float(
                        item.get(
                            "selection_coverage"
                        )
                    )
                ),
                "aoi_coverage": (
                    _optional_float(
                        item.get(
                            "aoi_coverage"
                        )
                    )
                ),
                "intersection_over_union": (
                    _optional_float(
                        item.get(
                            "intersection_over_union"
                        )
                    )
                ),
            }
        )

    return rows


def _claim_rows(
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    rows: list[dict[str, Any]] = []

    for item in value:
        if not isinstance(
            item,
            Mapping,
        ):
            continue

        source_ids = item.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            (list, tuple),
        ):
            source_ids = []

        rows.append(
            {
                "claim_index": (
                    item.get(
                        "claim_index"
                    )
                ),
                "claim": (
                    _safe_text(
                        item.get("claim")
                    )
                    or None
                ),
                "support": (
                    _safe_text(
                        item.get("support")
                    )
                    or None
                ),
                "source_ids": [
                    str(source_id)
                    for source_id
                    in source_ids
                ],
                "all_sources_valid": bool(
                    item.get(
                        "all_sources_valid",
                        False,
                    )
                ),
            }
        )

    return rows


def _source_rows(
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    rows: list[dict[str, Any]] = []

    for item in value:
        if not isinstance(
            item,
            Mapping,
        ):
            continue

        rows.append(
            {
                "source_id": (
                    _safe_text(
                        item.get(
                            "source_id"
                        )
                    )
                    or None
                ),
                "source_kind": (
                    _safe_text(
                        item.get(
                            "source_kind"
                        )
                    )
                    or None
                ),
                "slide_id": item.get(
                    "slide_id"
                ),
                "aoi_id": (
                    _safe_text(
                        item.get("aoi_id")
                    )
                    or None
                ),
                "title": (
                    _safe_text(
                        item.get("title")
                    )
                    or None
                ),
                "cited": bool(
                    item.get(
                        "cited",
                        False,
                    )
                ),
                "text_preview": (
                    _safe_text(
                        item.get(
                            "text_preview"
                        )
                    )
                    or None
                ),
            }
        )

    return rows


def _extract_interaction(
    wrapper: Mapping[str, Any],
) -> Mapping[str, Any]:
    interaction = wrapper.get(
        "interaction"
    )

    if isinstance(
        interaction,
        Mapping,
    ):
        return interaction

    return wrapper


def _as_mapping(
    value: Any,
) -> Mapping[str, Any]:
    if isinstance(
        value,
        Mapping,
    ):
        return value

    return {}


def _safe_bbox(
    value: Any,
) -> tuple[
    float,
    float,
    float,
    float,
] | None:
    if not isinstance(
        value,
        (list, tuple),
    ):
        return None

    if len(value) != 4:
        return None

    try:
        values = tuple(
            float(item)
            for item in value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    x_min, y_min, x_max, y_max = (
        values
    )

    if any(
        item < 0.0 or item > 1.0
        for item in values
    ):
        return None

    if (
        x_min >= x_max
        or y_min >= y_max
    ):
        return None

    return values


def _safe_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _optional_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        return round(
            float(value),
            6,
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _safe_int(
    value: Any,
) -> int:
    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return 0


_EXTRA_FORBIDDEN_KEYS = {
    "raw_response",
    "raw_provider_response",
    "provider_request_id",
    "request_id",
    "prompt",
    "prompts",
    "prompt_messages",
    "system_prompt",
    "user_prompt",
    "api_key",
    "authorization",
    "chain_of_thought",
    "hidden_reasoning",
    "reasoning_content",
}


def _find_forbidden_keys(
    value: Any,
) -> set[str]:
    discovered: set[str] = set()

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = (
                str(key)
                .strip()
                .casefold()
            )

            if (
                normalized_key
                in _EXTRA_FORBIDDEN_KEYS
            ):
                discovered.add(
                    normalized_key
                )

            discovered.update(
                _find_forbidden_keys(
                    child
                )
            )

    elif isinstance(
        value,
        (list, tuple),
    ):
        for child in value:
            discovered.update(
                _find_forbidden_keys(
                    child
                )
            )

    return discovered
