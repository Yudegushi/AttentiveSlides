"""Unit tests for API tutor request and response contracts."""

from __future__ import annotations

import unittest

from modules.common.llm_schemas import (
    ClaimEvidence,
    ContextSource,
    LLMCallResult,
    LLMUsage,
    StructuredTutorResponse,
    TutorLLMRequest,
)


class TestContextSource(unittest.TestCase):
    def test_confirmed_aoi_source_requires_aoi_id(self) -> None:
        with self.assertRaises(ValueError):
            ContextSource(
                source_id="slide_2_aoi_1",
                slide_id=2,
                source_kind="confirmed_aoi",
                text="Fixation maintains gaze at one location.",
            )

    def test_source_serializes_to_dictionary(self) -> None:
        source = ContextSource(
            source_id="slide_2_aoi_1",
            slide_id=2,
            source_kind="confirmed_aoi",
            text="Fixation maintains gaze at one location.",
            aoi_id="aoi_1",
            title="Fixation definition",
        )

        payload = source.to_dict()

        self.assertEqual(
            payload["source_id"],
            "slide_2_aoi_1",
        )
        self.assertEqual(payload["aoi_id"], "aoi_1")

    def test_visual_observation_source_kind_is_supported(self) -> None:
        source = ContextSource(
            source_id="slide_007_visual_01",
            slide_id=7,
            source_kind="visual_observation",
            text="Description: A visible formula.",
            metadata={"provenance": "llm_visual_analysis"},
        )

        self.assertEqual(source.source_kind, "visual_observation")


class TestTutorLLMRequest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = ContextSource(
            source_id="slide_2_aoi_1",
            slide_id=2,
            source_kind="confirmed_aoi",
            text="Fixation maintains gaze at one location.",
            aoi_id="aoi_1",
        )

    def test_valid_request_exposes_source_ids(self) -> None:
        request = TutorLLMRequest(
            query_id="query_001",
            deck_id="lecture_2",
            slide_id=2,
            question="Fixation 是什么？",
            intent="explain",
            response_mode="explain",
            sources=[self.source],
            confirmed_aoi_id="aoi_1",
        )

        self.assertEqual(
            request.source_ids(),
            {"slide_2_aoi_1"},
        )
        self.assertFalse(
            request.allow_external_knowledge,
        )

    def test_duplicate_source_ids_are_rejected(self) -> None:
        duplicate = ContextSource(
            source_id="slide_2_aoi_1",
            slide_id=2,
            source_kind="current_slide",
            text="A second source with the same identifier.",
        )

        with self.assertRaises(ValueError):
            TutorLLMRequest(
                query_id="query_001",
                deck_id="lecture_2",
                slide_id=2,
                question="Fixation 是什么？",
                intent="explain",
                response_mode="explain",
                sources=[self.source, duplicate],
                confirmed_aoi_id="aoi_1",
            )

    def test_confirmed_aoi_must_match_a_source(self) -> None:
        with self.assertRaises(ValueError):
            TutorLLMRequest(
                query_id="query_001",
                deck_id="lecture_2",
                slide_id=2,
                question="解释这个区域。",
                intent="explain",
                response_mode="explain",
                sources=[self.source],
                confirmed_aoi_id="another_aoi",
            )


class TestClaimEvidence(unittest.TestCase):
    def test_direct_claim_requires_source(self) -> None:
        with self.assertRaises(ValueError):
            ClaimEvidence(
                claim="Fixation maintains gaze at one location.",
                support="direct",
            )

    def test_external_claim_cannot_cite_slide_source(self) -> None:
        with self.assertRaises(ValueError):
            ClaimEvidence(
                claim="External background information.",
                support="external",
                source_ids=["slide_2_aoi_1"],
            )


class TestStructuredTutorResponse(unittest.TestCase):
    def test_valid_grounded_response(self) -> None:
        response = StructuredTutorResponse(
            response_mode="compare",
            answer=(
                "Fixation 保持视线在单一位置；"
                "Saccade 是 fixation 之间的快速眼动。"
            ),
            decision_summary=(
                "回答只使用两个已提供的 slide definitions。"
            ),
            claims=[
                ClaimEvidence(
                    claim=(
                        "Fixation 保持视线在单一位置。"
                    ),
                    support="direct",
                    source_ids=["slide_2_aoi_1"],
                ),
                ClaimEvidence(
                    claim=(
                        "Saccade 是 fixation 之间的快速眼动。"
                    ),
                    support="direct",
                    source_ids=["slide_2_aoi_2"],
                ),
            ],
            external_knowledge_used=False,
        )

        self.assertEqual(
            response.cited_source_ids(),
            {
                "slide_2_aoi_1",
                "slide_2_aoi_2",
            },
        )

    def test_external_flag_must_match_external_claims(self) -> None:
        with self.assertRaises(ValueError):
            StructuredTutorResponse(
                response_mode="explain",
                answer="这里加入了 external knowledge。",
                decision_summary="使用了额外背景知识。",
                claims=[
                    ClaimEvidence(
                        claim="External background information.",
                        support="external",
                    )
                ],
                external_knowledge_used=False,
            )

    def test_insufficient_claim_requires_uncertainty_note(self) -> None:
        with self.assertRaises(ValueError):
            StructuredTutorResponse(
                response_mode="explain",
                answer="当前 slide context 不足。",
                decision_summary="没有足够证据。",
                claims=[
                    ClaimEvidence(
                        claim="无法确定更详细的机制。",
                        support="insufficient",
                    )
                ],
                external_knowledge_used=False,
            )


class TestLLMCallMetadata(unittest.TestCase):
    def test_usage_rejects_invalid_total(self) -> None:
        with self.assertRaises(ValueError):
            LLMUsage(
                prompt_tokens=124,
                completion_tokens=70,
                total_tokens=100,
            )

    def test_call_result_serializes_nested_response(self) -> None:
        response = StructuredTutorResponse(
            response_mode="explain",
            answer="AOI 表示 Area of Interest。",
            decision_summary="回答使用当前 slide source。",
            claims=[
                ClaimEvidence(
                    claim="AOI 表示 Area of Interest。",
                    support="direct",
                    source_ids=["slide_1_aoi_1"],
                )
            ],
            external_knowledge_used=False,
        )

        result = LLMCallResult(
            query_id="query_002",
            provider="dashscope",
            model="qwen3.7-plus",
            latency_ms=2290.0,
            response=response,
            usage=LLMUsage(
                prompt_tokens=124,
                completion_tokens=70,
                total_tokens=194,
            ),
            provider_request_id="request_123",
        )

        payload = result.to_dict()

        self.assertEqual(
            payload["provider"],
            "dashscope",
        )
        self.assertEqual(
            payload["response"]["claims"][0]["source_ids"],
            ["slide_1_aoi_1"],
        )
        self.assertEqual(
            payload["usage"]["total_tokens"],
            194,
        )


if __name__ == "__main__":
    unittest.main()
