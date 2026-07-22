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

import math
from collections.abc import Mapping
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

    source_rows: list[dict[str, Any]] = []

    for source in request.sources:
        metadata, metadata_warnings = (
            _public_source_metadata(
                source.metadata,
                geometry_expected=bool(
                    source.aoi_id
                    or source.source_kind
                    == "visual_observation"
                ),
            )
        )

        source_rows.append({
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
            "metadata": metadata,
            "warnings": metadata_warnings,
        })

    claim_rows = [
        {
            "claim_index": claim_index + 1,
            "claim": claim.claim,
            "support": claim.support,
            "source_ids": list(claim.source_ids),
            "all_sources_valid": (
                all(
                    source_id in valid_source_ids
                    for source_id in claim.source_ids
                )
                if claim.support == "direct"
                else None
            ),
            "source_validation_status": (
                (
                    "valid"
                    if all(
                        source_id in valid_source_ids
                        for source_id in claim.source_ids
                    )
                    else "invalid"
                )
                if claim.support == "direct"
                else "not_applicable"
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
        "claim_evidence_map": (
            _build_claim_evidence_map(
                claims=response.claims,
                source_rows=source_rows,
                issues=validation.issues,
                confirmed_aoi_id=(
                    request.confirmed_aoi_id
                ),
            )
        ),
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


def _build_claim_evidence_map(
    *,
    claims: Any,
    source_rows: list[dict[str, Any]],
    issues: Any,
    confirmed_aoi_id: str | None,
) -> list[dict[str, Any]]:
    """Join public claims, cited sources, and structural issues."""
    source_by_id = {
        row["source_id"]: row
        for row in source_rows
    }
    issues_by_claim: dict[
        int,
        list[dict[str, Any]],
    ] = {}
    confirmed_target_issues: list[
        dict[str, Any]
    ] = []

    for issue in issues:
        validator_index = getattr(
            issue,
            "claim_index",
            None,
        )
        public_issue = {
            "severity": getattr(
                issue,
                "severity",
                None,
            ),
            "code": getattr(
                issue,
                "code",
                None,
            ),
            "message": getattr(
                issue,
                "message",
                None,
            ),
            "claim_index": (
                validator_index + 1
                if isinstance(
                    validator_index,
                    int,
                )
                else None
            ),
            "source_id": getattr(
                issue,
                "source_id",
                None,
            ),
        }

        if not isinstance(validator_index, int):
            if public_issue["code"] in {
                "missing_confirmed_aoi_source",
                "confirmed_aoi_unused",
                "confirmed_aoi_not_cited",
            }:
                confirmed_target_issues.append(
                    public_issue
                )
            continue

        issues_by_claim.setdefault(
            validator_index,
            [],
        ).append(public_issue)

    rows: list[dict[str, Any]] = []

    for validator_index, claim in enumerate(claims):
        public_claim_index = validator_index + 1
        claim_issues = issues_by_claim.get(
            validator_index,
            [],
        )
        direct = claim.support == "direct"
        if direct:
            claim_issues = [
                *claim_issues,
                *confirmed_target_issues,
            ]
        evidence_rows: list[dict[str, Any]] = []

        for source_id in claim.source_ids:
            source = source_by_id.get(source_id)
            source_issues = [
                issue
                for issue in claim_issues
                if issue.get("source_id")
                in {None, source_id}
            ]

            if source is None:
                evidence_rows.append({
                    "source_id": source_id,
                    "source_kind": None,
                    "slide_id": None,
                    "aoi_id": None,
                    "title": None,
                    "cited": True,
                    "text_preview": None,
                    "metadata": {},
                    "warnings": [
                        "Cited source was not supplied "
                        "to the tutor request."
                    ],
                    "source_existence_status": (
                        "missing"
                    ),
                    "citation_status": "cited",
                    "confirmed_target_match": (
                        "not_applicable"
                    ),
                    "structural_validation": {
                        "status": _issue_status(
                            source_issues
                        ),
                        "issues": source_issues,
                    },
                })
                continue

            evidence = dict(source)
            evidence.update({
                "source_existence_status": "found",
                "citation_status": "cited",
                "confirmed_target_match": (
                    "not_applicable"
                    if confirmed_aoi_id is None
                    else (
                        "matching"
                        if (
                            source.get("source_kind")
                            == "confirmed_aoi"
                            and source.get("aoi_id")
                            == confirmed_aoi_id
                        )
                        else "not_matching"
                    )
                ),
                "structural_validation": {
                    "status": _issue_status(
                        source_issues
                    ),
                    "issues": source_issues,
                },
            })
            evidence_rows.append(evidence)

        if direct:
            all_sources_valid = all(
                source_id in source_by_id
                for source_id in claim.source_ids
            )
            source_validation_status = (
                "valid"
                if all_sources_valid
                else "invalid"
            )
            warnings = (
                []
                if all_sources_valid
                else [
                    "One or more cited sources are missing."
                ]
            )
        else:
            all_sources_valid = None
            source_validation_status = (
                "not_applicable"
            )
            warnings = [
                "Slide-source citation does not apply "
                f"to {claim.support} support."
            ]

        rows.append({
            "claim_index": public_claim_index,
            "claim": claim.claim,
            "support": claim.support,
            "source_ids": list(claim.source_ids),
            "cited_source_count": len(
                claim.source_ids
            ),
            "all_sources_valid": all_sources_valid,
            "source_validation_status": (
                source_validation_status
            ),
            "structural_validation": {
                "status": _issue_status(
                    claim_issues
                ),
                "issues": claim_issues,
            },
            "semantic_verification": (
                "not_performed"
            ),
            "sources": evidence_rows,
            "warnings": warnings,
        })

    return rows


def _issue_status(
    issues: list[dict[str, Any]],
) -> str:
    if any(
        issue.get("severity") == "error"
        for issue in issues
    ):
        return "failed"

    if any(
        issue.get("severity") == "warning"
        for issue in issues
    ):
        return "warning"

    return "passed"


def _public_source_metadata(
    value: Any,
    *,
    geometry_expected: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Copy only validated metadata intended for public XAI."""
    if not isinstance(value, Mapping):
        return {}, ["Source metadata was unavailable."]

    public: dict[str, Any] = {}
    warnings: list[str] = []

    for key in (
        "aoi_type",
        "aoi_name",
        "visual_type",
        "provenance",
    ):
        text = _metadata_text(value.get(key))
        if text is not None:
            public[key] = text

    for key in (
        "target_confidence",
        "confidence",
    ):
        confidence = _normalized_number(
            value.get(key)
        )
        if confidence is not None:
            public[key] = confidence
        elif key in value:
            warnings.append(
                f"Invalid {key} was omitted."
            )

    bbox = _normalized_bbox(
        value.get("bbox")
    )
    if bbox is not None:
        public["bbox"] = list(bbox)
    elif "bbox" in value:
        warnings.append(
            "Invalid normalized bbox was omitted."
        )
    elif geometry_expected:
        warnings.append(
            "Normalized bbox is unavailable."
        )

    return public, warnings


def _metadata_text(
    value: Any,
) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = " ".join(value.split())
    if not normalized:
        return None

    return normalized[:160]


def _normalized_number(
    value: Any,
) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if (
        not math.isfinite(number)
        or number < 0.0
        or number > 1.0
    ):
        return None

    return number


def _normalized_bbox(
    value: Any,
) -> tuple[float, float, float, float] | None:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 4
        or any(isinstance(item, bool) for item in value)
    ):
        return None

    try:
        bbox = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None

    if any(
        not math.isfinite(item)
        or item < 0.0
        or item > 1.0
        for item in bbox
    ):
        return None

    x_min, y_min, x_max, y_max = bbox
    if x_min >= x_max or y_min >= y_max:
        return None

    return bbox


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
