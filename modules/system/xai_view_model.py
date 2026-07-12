"""Sanitized XAI view model for grounded tutor responses.

The public XAI payload intentionally excludes:
- raw provider responses,
- prompt messages,
- provider request IDs,
- hidden reasoning or Chain-of-Thought,
- API credentials.

It exposes verifiable evidence, validation results, uncertainty,
and operational telemetry suitable for Streamlit presentation.
"""

from __future__ import annotations

from typing import Any

from modules.tutor.grounded_tutor_agent import (
    GroundedTutorResult,
)


_STATUS_LABELS = {
    "success": "Validated API response",
    "fallback": "Deterministic fallback",
    "confirmation_required": "Confirmation required",
}

_FORBIDDEN_PUBLIC_KEYS = {
    "raw_response",
    "provider_request_id",
    "prompt_messages",
    "system_prompt",
    "user_prompt",
    "chain_of_thought",
    "hidden_reasoning",
    "api_key",
}


def build_xai_view_model(
    result: GroundedTutorResult,
    *,
    source_preview_chars: int = 240,
) -> dict[str, Any]:
    """Create a sanitized UI payload from one grounded tutor result."""
    if not isinstance(result, GroundedTutorResult):
        raise TypeError(
            "result must be a GroundedTutorResult."
        )

    if source_preview_chars <= 0:
        raise ValueError(
            "source_preview_chars must be greater than zero."
        )

    request = result.request
    call_result = result.call_result
    response = call_result.response
    validation = result.validation

    valid_source_ids = request.source_ids()
    cited_source_ids = response.cited_source_ids()

    source_rows = [
        {
            "source_id": source.source_id,
            "source_kind": source.source_kind,
            "slide_id": source.slide_id,
            "aoi_id": source.aoi_id,
            "title": source.title,
            "cited": (
                source.source_id in cited_source_ids
            ),
            "text_preview": _preview(
                source.text,
                source_preview_chars,
            ),
        }
        for source in request.sources
    ]

    claim_rows = [
        {
            "claim_index": claim_index + 1,
            "claim": claim.claim,
            "support": claim.support,
            "source_ids": list(claim.source_ids),
            "all_sources_valid": all(
                source_id in valid_source_ids
                for source_id in claim.source_ids
            ),
        }
        for claim_index, claim
        in enumerate(response.claims)
    ]

    issue_rows = [
        {
            "severity": issue.severity,
            "code": issue.code,
            "message": issue.message,
            "claim_index": issue.claim_index,
            "source_id": issue.source_id,
        }
        for issue in validation.issues
    ]

    attempt_rows = [
        _attempt_view(
            attempt_number=attempt.attempt_number,
            provider=attempt.provider,
            model=attempt.model,
            latency_ms=attempt.latency_ms,
            parse_warnings=attempt.parse_warnings,
            parse_error=attempt.parse_error,
            validation=attempt.validation,
            provider_error=attempt.provider_error,
        )
        for attempt in result.attempts
    ]

    usage = call_result.usage

    payload = {
        "schema_version": "1.0",
        "status": result.status,
        "status_label": _STATUS_LABELS[result.status],
        "query_id": request.query_id,
        "response_mode": response.response_mode,
        "answer": response.answer,
        "active_recall_question": (
            response.active_recall_question
        ),
        "uncertainty_note": response.uncertainty_note,
        "decision_summary": response.decision_summary,
        "external_knowledge_used": (
            response.external_knowledge_used
        ),
        "confirmed_aoi_id": request.confirmed_aoi_id,
        "sources": source_rows,
        "claims": claim_rows,
        "validation": {
            "is_valid": validation.is_valid,
            "citation_coverage": (
                validation.citation_coverage
            ),
            "confirmed_aoi_cited": (
                validation.confirmed_aoi_cited
            ),
            "direct_claim_count": (
                validation.direct_claim_count
            ),
            "valid_direct_claim_count": (
                validation.valid_direct_claim_count
            ),
            "issues": issue_rows,
        },
        "telemetry": {
            "provider": call_result.provider,
            "model": call_result.model,
            "latency_ms": round(
                call_result.latency_ms,
                2,
            ),
            "retry_count": call_result.retry_count,
            "fallback_used": (
                call_result.fallback_used
            ),
            "prompt_character_count": (
                result.prompt_character_count
            ),
            "prompt_tokens": (
                usage.prompt_tokens
                if usage is not None
                else None
            ),
            "completion_tokens": (
                usage.completion_tokens
                if usage is not None
                else None
            ),
            "total_tokens": (
                usage.total_tokens
                if usage is not None
                else None
            ),
            "cached_prompt_tokens": (
                usage.cached_prompt_tokens
                if usage is not None
                else None
            ),
        },
        "attempts": attempt_rows,
        "safety": {
            "raw_chain_of_thought_exposed": False,
            "raw_provider_response_exposed": False,
            "observable_signals_are_not_mental_states": True,
        },
    }

    assert_public_xai_payload(payload)

    return payload


def assert_public_xai_payload(
    payload: dict[str, Any],
) -> None:
    """Reject fields that must not appear in public XAI output."""
    discovered = _find_forbidden_keys(payload)

    if discovered:
        raise ValueError(
            "Public XAI payload contains forbidden fields: "
            f"{sorted(discovered)}"
        )


def _attempt_view(
    *,
    attempt_number: int,
    provider: str,
    model: str,
    latency_ms: float,
    parse_warnings: tuple[str, ...],
    parse_error: dict[str, str] | None,
    validation: dict[str, Any] | None,
    provider_error: dict[str, str] | None,
) -> dict[str, Any]:
    if provider_error is not None:
        outcome = "provider_error"
    elif parse_error is not None:
        outcome = "parse_error"
    elif validation is None:
        outcome = "unknown"
    elif validation.get("is_valid"):
        outcome = "validated"
    else:
        outcome = "validation_error"

    validation_error_codes: list[str] = []

    if validation is not None:
        validation_error_codes = [
            str(issue.get("code"))
            for issue in validation.get("issues", [])
            if issue.get("severity") == "error"
        ]

    return {
        "attempt_number": attempt_number,
        "provider": provider,
        "model": model,
        "latency_ms": round(latency_ms, 2),
        "outcome": outcome,
        "parse_warnings": list(parse_warnings),
        "parse_error_code": (
            parse_error.get("code")
            if parse_error is not None
            else None
        ),
        "validation_error_codes": (
            validation_error_codes
        ),
        "provider_error_type": (
            provider_error.get("type")
            if provider_error is not None
            else None
        ),
    }


def _preview(
    text: str,
    maximum_chars: int,
) -> str:
    normalized = " ".join(text.split())

    if len(normalized) <= maximum_chars:
        return normalized

    return (
        normalized[: maximum_chars - 1].rstrip()
        + "…"
    )


def _find_forbidden_keys(
    value: Any,
) -> set[str]:
    discovered: set[str] = set()

    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).casefold()

            if normalized_key in _FORBIDDEN_PUBLIC_KEYS:
                discovered.add(normalized_key)

            discovered.update(
                _find_forbidden_keys(child)
            )

    elif isinstance(value, (list, tuple)):
        for child in value:
            discovered.update(
                _find_forbidden_keys(child)
            )

    return discovered
