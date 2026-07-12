"""Tests for the sanitized grounded-tutor XAI view model."""

from __future__ import annotations

import json
import unittest

from modules.common.llm_schemas import (
    ClaimEvidence,
    ContextSource,
    LLMCallResult,
    LLMUsage,
    StructuredTutorResponse,
    TutorLLMRequest,
)
from modules.system.xai_view_model import (
    assert_public_xai_payload,
    build_xai_view_model,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorResult,
    LLMAttemptRecord,
)
from modules.tutor.grounding_validator import (
    GroundingValidator,
)


def make_grounded_result() -> GroundedTutorResult:
    request = TutorLLMRequest(
        query_id="xai_test_001",
        deck_id="lecture_2",
        slide_id=2,
        question=(
            "fixation 和 saccade 有什么区别？"
        ),
        intent="compare",
        response_mode="compare",
        confirmed_aoi_id="aoi_fixation",
        sources=[
            ContextSource(
                source_id="slide_02_aoi_01",
                slide_id=2,
                source_kind="confirmed_aoi",
                aoi_id="aoi_fixation",
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
                text=(
                    "Saccade is a rapid eye movement "
                    "between fixations."
                ),
            ),
        ],
    )

    response = StructuredTutorResponse(
        response_mode="compare",
        answer=(
            "Fixation 保持视线在单一位置；"
            "Saccade 是 fixation 之间的快速眼动。"
        ),
        decision_summary=(
            "回答只使用两个提供的 slide sources。"
        ),
        claims=[
            ClaimEvidence(
                claim=(
                    "Fixation 保持视线在单一位置。"
                ),
                support="direct",
                source_ids=[
                    "slide_02_aoi_01"
                ],
            ),
            ClaimEvidence(
                claim=(
                    "Saccade 是 fixation 之间的快速眼动。"
                ),
                support="direct",
                source_ids=[
                    "slide_02_aoi_02"
                ],
            ),
        ],
        external_knowledge_used=False,
    )

    validation = GroundingValidator().validate(
        request,
        response,
    )

    return GroundedTutorResult(
        status="success",
        request=request,
        call_result=LLMCallResult(
            query_id=request.query_id,
            provider="dashscope",
            model="qwen3.7-plus",
            latency_ms=2200.0,
            response=response,
            usage=LLMUsage(
                prompt_tokens=800,
                completion_tokens=200,
                total_tokens=1000,
            ),
            provider_request_id=(
                "private_request_id"
            ),
        ),
        validation=validation,
        attempts=(
            LLMAttemptRecord(
                attempt_number=1,
                provider="dashscope",
                model="qwen3.7-plus",
                latency_ms=2200.0,
                request_id="private_request_id",
                raw_response=(
                    "PRIVATE RAW PROVIDER RESPONSE"
                ),
                validation=validation.to_dict(),
            ),
        ),
        prompt_character_count=3500,
    )


class TestXAIViewModel(unittest.TestCase):
    def test_claim_source_mapping_is_preserved(
        self,
    ) -> None:
        view = build_xai_view_model(
            make_grounded_result()
        )

        self.assertEqual(
            len(view["claims"]),
            2,
        )

        self.assertEqual(
            view["claims"][0]["source_ids"],
            ["slide_02_aoi_01"],
        )

        self.assertTrue(
            all(
                claim["all_sources_valid"]
                for claim in view["claims"]
            )
        )

    def test_validation_and_telemetry_are_exposed(
        self,
    ) -> None:
        view = build_xai_view_model(
            make_grounded_result()
        )

        self.assertTrue(
            view["validation"]["is_valid"]
        )

        self.assertEqual(
            view["validation"][
                "citation_coverage"
            ],
            1.0,
        )

        self.assertEqual(
            view["telemetry"]["total_tokens"],
            1000,
        )

        self.assertEqual(
            view["telemetry"]["provider"],
            "dashscope",
        )

    def test_private_provider_fields_are_removed(
        self,
    ) -> None:
        view = build_xai_view_model(
            make_grounded_result()
        )

        serialized = json.dumps(
            view,
            ensure_ascii=False,
        )

        self.assertNotIn(
            "PRIVATE RAW PROVIDER RESPONSE",
            serialized,
        )

        self.assertNotIn(
            "private_request_id",
            serialized,
        )

        self.assertNotIn(
            "raw_response",
            serialized,
        )

        self.assertNotIn(
            "provider_request_id",
            serialized,
        )

    def test_source_preview_is_truncated(self) -> None:
        view = build_xai_view_model(
            make_grounded_result(),
            source_preview_chars=30,
        )

        self.assertLessEqual(
            len(
                view["sources"][0][
                    "text_preview"
                ]
            ),
            30,
        )

        self.assertTrue(
            view["sources"][0][
                "text_preview"
            ].endswith("…")
        )

    def test_forbidden_public_key_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            assert_public_xai_payload({
                "answer": "safe",
                "raw_response": "not safe",
            })


if __name__ == "__main__":
    unittest.main()
