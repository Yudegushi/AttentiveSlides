"""Recorded smoke test for tutor LLM request/response schemas."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_smoke_common import base_record, write_record
from modules.common.llm_schemas import (
    ClaimEvidence,
    ContextSource,
    LLMCallResult,
    LLMUsage,
    StructuredTutorResponse,
    TutorLLMRequest,
)


def capture_error(function: Callable[[], object]) -> dict:
    try:
        function()
    except Exception as exc:
        return {
            "raised": True,
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }

    return {
        "raised": False,
        "exception_type": None,
        "message": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    sources = [
        ContextSource(
            source_id="slide_02_aoi_01",
            slide_id=2,
            source_kind="confirmed_aoi",
            aoi_id="aoi_fixation",
            title="Fixation definition",
            text=(
                "Fixation is maintaining gaze "
                "on a single location."
            ),
        ),
        ContextSource(
            source_id="slide_02_aoi_02",
            slide_id=2,
            source_kind="current_slide",
            aoi_id="aoi_saccade",
            title="Saccade definition",
            text=(
                "Saccade is a rapid eye movement "
                "between fixations."
            ),
        ),
    ]

    request = TutorLLMRequest(
        query_id="schema_smoke_001",
        deck_id="lecture_2",
        slide_id=2,
        question="fixation 和 saccade 有什么区别？",
        intent="compare",
        response_mode="compare",
        sources=sources,
        confirmed_aoi_id="aoi_fixation",
    )

    response = StructuredTutorResponse(
        response_mode="compare",
        answer=(
            "Fixation 是保持视线在单一位置；"
            "Saccade 是 fixation 之间的快速眼动。"
        ),
        decision_summary=(
            "回答仅使用两个提供的 slide sources。"
        ),
        claims=[
            ClaimEvidence(
                claim=(
                    "Fixation 是保持视线在单一位置。"
                ),
                support="direct",
                source_ids=["slide_02_aoi_01"],
            ),
            ClaimEvidence(
                claim=(
                    "Saccade 是 fixation 之间的快速眼动。"
                ),
                support="direct",
                source_ids=["slide_02_aoi_02"],
            ),
        ],
        external_knowledge_used=False,
    )

    result = LLMCallResult(
        query_id=request.query_id,
        provider="dashscope",
        model="qwen3.7-plus",
        latency_ms=2290.0,
        response=response,
        usage=LLMUsage(
            prompt_tokens=124,
            completion_tokens=70,
            total_tokens=194,
        ),
    )

    negative_checks = {
        "direct_claim_without_source": capture_error(
            lambda: ClaimEvidence(
                claim="Unsupported direct claim.",
                support="direct",
                source_ids=[],
            )
        ),
        "confirmed_aoi_without_matching_source": capture_error(
            lambda: TutorLLMRequest(
                query_id="invalid_001",
                deck_id="lecture_2",
                slide_id=2,
                question="解释这个。",
                intent="explain",
                response_mode="explain",
                sources=sources,
                confirmed_aoi_id="missing_aoi",
            )
        ),
        "invalid_token_total": capture_error(
            lambda: LLMUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=120,
            )
        ),
    }

    checks = {
        "source_ids_are_unique": request.source_ids()
        == {
            "slide_02_aoi_01",
            "slide_02_aoi_02",
        },
        "confirmed_aoi_preserved": (
            request.confirmed_aoi_id
            == "aoi_fixation"
        ),
        "all_direct_claims_cited": all(
            claim.source_ids
            for claim in response.claims
            if claim.support == "direct"
        ),
        "external_knowledge_disabled": not (
            response.external_knowledge_used
        ),
        "usage_preserved": (
            result.usage is not None
            and result.usage.total_tokens == 194
        ),
        "negative_checks_raised": all(
            item["raised"]
            for item in negative_checks.values()
        ),
    }

    payload = base_record(
        "request_response_schema_smoke"
    )
    payload.update({
        "passed": all(checks.values()),
        "checks": checks,
        "negative_checks": negative_checks,
        "request": request.to_dict(),
        "result": result.to_dict(),
    })

    write_record(args.output, payload)

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
