"""Dataset contracts and loader for grounded tutor LLM evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.common.llm_schemas import (
    ContextSource,
    TutorLLMRequest,
)


@dataclass(frozen=True)
class LLMCaseExpectations:
    expected_validation_valid: bool = True
    required_source_ids: tuple[str, ...] = ()
    forbidden_phrases: tuple[str, ...] = ()
    expected_external_knowledge_used: bool = False
    min_direct_claims: int = 1
    require_active_recall_question: bool = False

    def __post_init__(self) -> None:
        if self.min_direct_claims < 0:
            raise ValueError(
                "min_direct_claims must be non-negative."
            )


@dataclass(frozen=True)
class LLMEvaluationCase:
    case_id: str
    category: str
    description: str
    request: TutorLLMRequest
    expectations: LLMCaseExpectations
    fixture_response: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be blank.")

        if not self.category.strip():
            raise ValueError("category must not be blank.")

        if not self.description.strip():
            raise ValueError(
                "description must not be blank."
            )

        if not isinstance(
            self.fixture_response,
            dict,
        ):
            raise TypeError(
                "fixture_response must be an object."
            )


def _build_request(
    payload: dict[str, Any],
) -> TutorLLMRequest:
    request_payload = dict(payload)
    sources_payload = request_payload.pop("sources")

    sources = [
        ContextSource(**source_payload)
        for source_payload in sources_payload
    ]

    return TutorLLMRequest(
        sources=sources,
        **request_payload,
    )


def load_llm_cases(
    path: str | Path,
) -> list[LLMEvaluationCase]:
    dataset_path = Path(path)

    payload = json.loads(
        dataset_path.read_text(encoding="utf-8")
    )

    if payload.get("schema_version") != "1.0":
        raise ValueError(
            "Unsupported LLM evaluation dataset version."
        )

    cases_payload = payload.get("cases")

    if not isinstance(cases_payload, list):
        raise ValueError(
            "Dataset must contain a cases array."
        )

    cases: list[LLMEvaluationCase] = []

    for item in cases_payload:
        expectations_payload = item["expectations"]

        case = LLMEvaluationCase(
            case_id=item["case_id"],
            category=item["category"],
            description=item["description"],
            request=_build_request(item["request"]),
            expectations=LLMCaseExpectations(
                expected_validation_valid=(
                    expectations_payload.get(
                        "expected_validation_valid",
                        True,
                    )
                ),
                required_source_ids=tuple(
                    expectations_payload.get(
                        "required_source_ids",
                        [],
                    )
                ),
                forbidden_phrases=tuple(
                    expectations_payload.get(
                        "forbidden_phrases",
                        [],
                    )
                ),
                expected_external_knowledge_used=(
                    expectations_payload.get(
                        "expected_external_knowledge_used",
                        False,
                    )
                ),
                min_direct_claims=(
                    expectations_payload.get(
                        "min_direct_claims",
                        1,
                    )
                ),
                require_active_recall_question=(
                    expectations_payload.get(
                        "require_active_recall_question",
                        False,
                    )
                ),
            ),
            fixture_response=item["fixture_response"],
        )

        unknown_required_sources = (
            set(case.expectations.required_source_ids)
            - case.request.source_ids()
        )

        if unknown_required_sources:
            raise ValueError(
                f"{case.case_id} expects unknown sources: "
                f"{sorted(unknown_required_sources)}"
            )

        cases.append(case)

    case_ids = [case.case_id for case in cases]

    if len(case_ids) != len(set(case_ids)):
        raise ValueError(
            "Evaluation case IDs must be unique."
        )

    return cases
