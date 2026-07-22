"""Tests for the sanitized grounded-tutor XAI view model."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

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
                metadata={
                    "aoi_type": "text",
                    "aoi_name": "Fixation definition",
                    "bbox": [0.1, 0.2, 0.6, 0.7],
                    "target_confidence": 0.91,
                    "provenance": "slide_aoi",
                    "raw_media": "PRIVATE IMAGE BYTES",
                    "provider_request_id": "PRIVATE METADATA ID",
                },
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

    def test_claim_evidence_map_joins_safe_source_metadata(
        self,
    ) -> None:
        view = build_xai_view_model(
            make_grounded_result()
        )

        claim = view["claim_evidence_map"][0]
        source = claim["sources"][0]

        self.assertEqual(claim["claim_index"], 1)
        self.assertEqual(
            claim["source_validation_status"],
            "valid",
        )
        self.assertEqual(
            claim["semantic_verification"],
            "not_performed",
        )
        self.assertEqual(
            source["metadata"],
            {
                "aoi_type": "text",
                "aoi_name": "Fixation definition",
                "provenance": "slide_aoi",
                "target_confidence": 0.91,
                "bbox": [0.1, 0.2, 0.6, 0.7],
            },
        )
        serialized = json.dumps(view)
        self.assertNotIn("PRIVATE IMAGE BYTES", serialized)
        self.assertNotIn("PRIVATE METADATA ID", serialized)

    def test_invalid_bbox_is_omitted_fail_safe(
        self,
    ) -> None:
        result = make_grounded_result()
        sources = list(result.request.sources)
        sources[0] = replace(
            sources[0],
            metadata={
                "bbox": [0.1, float("nan"), 0.6, 0.7],
                "confidence": float("inf"),
            },
        )
        request = replace(result.request, sources=sources)
        changed = replace(result, request=request)

        view = build_xai_view_model(changed)
        source = view["sources"][0]

        self.assertNotIn("bbox", source["metadata"])
        self.assertNotIn("confidence", source["metadata"])
        self.assertIn(
            "Invalid normalized bbox was omitted.",
            source["warnings"],
        )
        json.dumps(view, allow_nan=False)

    def test_missing_source_issue_maps_to_public_claim_index(
        self,
    ) -> None:
        result = make_grounded_result()
        response = replace(
            result.call_result.response,
            claims=[
                result.call_result.response.claims[0],
                ClaimEvidence(
                    claim="This cites a missing source.",
                    support="direct",
                    source_ids=["missing_source"],
                ),
            ],
        )
        validation = GroundingValidator().validate(
            result.request,
            response,
        )
        changed = replace(
            result,
            call_result=replace(
                result.call_result,
                response=response,
            ),
            validation=validation,
        )

        view = build_xai_view_model(changed)
        first, second = view["claim_evidence_map"]

        self.assertEqual(
            first["structural_validation"]["issues"],
            [],
        )
        self.assertEqual(second["claim_index"], 2)
        self.assertEqual(
            second["structural_validation"]["issues"][0][
                "claim_index"
            ],
            2,
        )
        self.assertEqual(
            second["sources"][0]["source_existence_status"],
            "missing",
        )

    def test_non_direct_source_validation_is_not_applicable(
        self,
    ) -> None:
        result = make_grounded_result()
        response = replace(
            result.call_result.response,
            uncertainty_note=(
                "The supplied evidence is insufficient."
            ),
            claims=[
                ClaimEvidence(
                    claim="The supplied evidence is insufficient.",
                    support="insufficient",
                )
            ],
        )
        validation = GroundingValidator().validate(
            result.request,
            response,
        )
        changed = replace(
            result,
            call_result=replace(
                result.call_result,
                response=response,
            ),
            validation=validation,
        )

        view = build_xai_view_model(changed)
        claim = view["claim_evidence_map"][0]

        self.assertIsNone(view["claims"][0]["all_sources_valid"])
        self.assertEqual(
            claim["source_validation_status"],
            "not_applicable",
        )
        self.assertIsNone(claim["all_sources_valid"])
        self.assertEqual(claim["sources"], [])

    def test_visual_source_is_not_confirmed_target_match(
        self,
    ) -> None:
        result = make_grounded_result()
        sources = list(result.request.sources)
        sources[1] = replace(
            sources[1],
            source_kind="visual_observation",
            aoi_id="aoi_fixation",
            metadata={
                "visual_type": "diagram",
                "bbox": [0.2, 0.2, 0.8, 0.8],
            },
        )
        request = replace(
            result.request,
            sources=sources,
        )
        response = replace(
            result.call_result.response,
            claims=[
                ClaimEvidence(
                    claim=(
                        "A visual source shares the "
                        "confirmed AOI link."
                    ),
                    support="direct",
                    source_ids=[sources[1].source_id],
                )
            ],
        )
        validation = GroundingValidator().validate(
            request,
            response,
        )
        changed = replace(
            result,
            request=request,
            call_result=replace(
                result.call_result,
                response=response,
            ),
            validation=validation,
        )

        view = build_xai_view_model(changed)
        claim = view["claim_evidence_map"][0]
        evidence = claim["sources"][0]

        self.assertFalse(validation.is_valid)
        self.assertEqual(
            evidence["confirmed_target_match"],
            "not_matching",
        )
        self.assertEqual(
            claim["structural_validation"]["status"],
            "failed",
        )
        self.assertIn(
            "confirmed_aoi_not_cited",
            {
                issue["code"]
                for issue in claim[
                    "structural_validation"
                ]["issues"]
            },
        )


if __name__ == "__main__":
    unittest.main()
