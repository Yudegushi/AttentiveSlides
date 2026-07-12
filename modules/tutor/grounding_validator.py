"""Deterministic provenance validation for tutor LLM responses.

This validator checks source identity, response policy, confirmation
provenance, and response-mode requirements.

It does not perform semantic entailment. A valid result means that source
references and declared evidence types are structurally consistent; it
does not prove that every sentence is factually entailed by the source
text.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from modules.common.llm_schemas import (
    StructuredTutorResponse,
    TutorLLMRequest,
)


ValidationSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic validation finding."""

    code: str
    message: str
    severity: ValidationSeverity
    claim_index: int | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("code must not be blank.")

        if not self.message.strip():
            raise ValueError("message must not be blank.")

        if self.severity not in {"error", "warning"}:
            raise ValueError(
                "severity must be 'error' or 'warning'."
            )


@dataclass(frozen=True)
class GroundingValidationResult:
    """Validation result used by retry, fallback, logging, and XAI."""

    issues: tuple[ValidationIssue, ...]
    cited_source_ids: tuple[str, ...]
    valid_source_ids: tuple[str, ...]
    direct_claim_count: int
    valid_direct_claim_count: int
    citation_coverage: float | None
    confirmed_aoi_cited: bool | None

    @property
    def is_valid(self) -> bool:
        return not any(
            issue.severity == "error"
            for issue in self.issues
        )

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.severity == "error"
        )

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.severity == "warning"
        )

    def require_valid(self) -> None:
        if not self.is_valid:
            raise GroundingValidationError(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": [
                asdict(issue)
                for issue in self.issues
            ],
            "cited_source_ids": list(
                self.cited_source_ids
            ),
            "valid_source_ids": list(
                self.valid_source_ids
            ),
            "direct_claim_count": (
                self.direct_claim_count
            ),
            "valid_direct_claim_count": (
                self.valid_direct_claim_count
            ),
            "citation_coverage": (
                self.citation_coverage
            ),
            "confirmed_aoi_cited": (
                self.confirmed_aoi_cited
            ),
        }


class GroundingValidationError(ValueError):
    """Raised when callers require a valid grounding result."""

    def __init__(
        self,
        result: GroundingValidationResult,
    ) -> None:
        self.result = result

        codes = [
            issue.code
            for issue in result.errors
        ]

        super().__init__(
            "Grounding validation failed: "
            + ", ".join(codes)
        )


class GroundingValidator:
    """Validate one structured response against its original request."""

    def validate(
        self,
        request: TutorLLMRequest,
        response: StructuredTutorResponse,
    ) -> GroundingValidationResult:
        if not isinstance(request, TutorLLMRequest):
            raise TypeError(
                "request must be a TutorLLMRequest."
            )

        if not isinstance(
            response,
            StructuredTutorResponse,
        ):
            raise TypeError(
                "response must be a StructuredTutorResponse."
            )

        issues: list[ValidationIssue] = []

        def add_issue(
            code: str,
            message: str,
            severity: ValidationSeverity,
            *,
            claim_index: int | None = None,
            source_id: str | None = None,
        ) -> None:
            issues.append(
                ValidationIssue(
                    code=code,
                    message=message,
                    severity=severity,
                    claim_index=claim_index,
                    source_id=source_id,
                )
            )

        source_by_id = {
            source.source_id: source
            for source in request.sources
        }

        valid_source_ids = set(source_by_id)
        cited_source_ids: set[str] = set()

        if response.response_mode != request.response_mode:
            add_issue(
                "response_mode_mismatch",
                (
                    "Response mode does not match the "
                    "requested response mode."
                ),
                "error",
            )

        if (
            response.response_mode != "break"
            and not response.claims
        ):
            add_issue(
                "missing_claims",
                (
                    "A non-break response must declare "
                    "at least one claim."
                ),
                "error",
            )

        direct_claim_count = 0
        valid_direct_claim_count = 0
        seen_claim_text: dict[str, int] = {}

        for claim_index, claim in enumerate(
            response.claims
        ):
            normalized_claim = " ".join(
                claim.claim.casefold().split()
            )

            if normalized_claim in seen_claim_text:
                add_issue(
                    "duplicate_claim",
                    (
                        "The response contains a duplicate "
                        "claim."
                    ),
                    "warning",
                    claim_index=claim_index,
                )
            else:
                seen_claim_text[
                    normalized_claim
                ] = claim_index

            if claim.support == "direct":
                direct_claim_count += 1
                claim_has_invalid_source = False

                for source_id in claim.source_ids:
                    cited_source_ids.add(source_id)

                    if source_id not in valid_source_ids:
                        claim_has_invalid_source = True

                        add_issue(
                            "unknown_source_id",
                            (
                                "A direct claim cites a "
                                "source ID not supplied in "
                                "the request."
                            ),
                            "error",
                            claim_index=claim_index,
                            source_id=source_id,
                        )

                if not claim_has_invalid_source:
                    valid_direct_claim_count += 1

            elif claim.support == "external":
                if not request.allow_external_knowledge:
                    add_issue(
                        "external_knowledge_not_allowed",
                        (
                            "The response contains an external "
                            "claim although the request "
                            "disallows external knowledge."
                        ),
                        "error",
                        claim_index=claim_index,
                    )

        if direct_claim_count:
            citation_coverage: float | None = (
                valid_direct_claim_count
                / direct_claim_count
            )
        else:
            citation_coverage = None

        confirmed_aoi_cited = self._validate_confirmed_aoi(
            request=request,
            response=response,
            cited_source_ids=cited_source_ids,
            add_issue=add_issue,
        )

        if request.response_mode in {"quiz", "review"}:
            if not response.active_recall_question:
                add_issue(
                    "missing_active_recall_question",
                    (
                        "Quiz and review responses require "
                        "active_recall_question."
                    ),
                    "error",
                )

        has_insufficient_claim = any(
            claim.support == "insufficient"
            for claim in response.claims
        )

        if (
            response.uncertainty_note is not None
            and not has_insufficient_claim
        ):
            add_issue(
                "unnecessary_uncertainty_note",
                (
                    "uncertainty_note was provided without "
                    "an insufficient claim."
                ),
                "warning",
            )

        return GroundingValidationResult(
            issues=tuple(issues),
            cited_source_ids=tuple(
                sorted(cited_source_ids)
            ),
            valid_source_ids=tuple(
                sorted(valid_source_ids)
            ),
            direct_claim_count=direct_claim_count,
            valid_direct_claim_count=(
                valid_direct_claim_count
            ),
            citation_coverage=citation_coverage,
            confirmed_aoi_cited=confirmed_aoi_cited,
        )

    @staticmethod
    def _validate_confirmed_aoi(
        *,
        request: TutorLLMRequest,
        response: StructuredTutorResponse,
        cited_source_ids: set[str],
        add_issue: Any,
    ) -> bool | None:
        if request.confirmed_aoi_id is None:
            return None

        confirmed_source_ids = {
            source.source_id
            for source in request.sources
            if (
                source.aoi_id
                == request.confirmed_aoi_id
                and source.source_kind
                == "confirmed_aoi"
            )
        }

        if not confirmed_source_ids:
            add_issue(
                "missing_confirmed_aoi_source",
                (
                    "The request declares confirmed_aoi_id "
                    "but contains no confirmed_aoi source "
                    "for that AOI."
                ),
                "error",
            )
            return False

        has_direct_claim = any(
            claim.support == "direct"
            for claim in response.claims
        )

        if not has_direct_claim:
            if response.response_mode != "break":
                add_issue(
                    "confirmed_aoi_unused",
                    (
                        "A confirmed AOI was available but "
                        "the response contains no direct "
                        "source-grounded claim."
                    ),
                    "warning",
                )

            return False

        confirmed_aoi_cited = bool(
            confirmed_source_ids
            & cited_source_ids
        )

        if not confirmed_aoi_cited:
            add_issue(
                "confirmed_aoi_not_cited",
                (
                    "The response contains direct claims "
                    "but none cites the confirmed AOI source."
                ),
                "error",
            )

        return confirmed_aoi_cited
