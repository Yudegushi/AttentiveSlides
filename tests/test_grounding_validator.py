"""Tests for deterministic grounding validation."""

from __future__ import annotations

import unittest

from modules.common.llm_schemas import (
    ClaimEvidence,
    ContextSource,
    StructuredTutorResponse,
    TutorLLMRequest,
)
from modules.tutor.grounding_validator import (
    GroundingValidationError,
    GroundingValidator,
)


class TestGroundingValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = GroundingValidator()

        self.sources = [
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
        ]

    def make_request(
        self,
        *,
        response_mode: str = "compare",
        confirmed: bool = True,
        allow_external: bool = False,
    ) -> TutorLLMRequest:
        return TutorLLMRequest(
            query_id="query_001",
            deck_id="lecture_2",
            slide_id=2,
            question=(
                "fixation 和 saccade 有什么区别？"
            ),
            intent="compare",
            response_mode=response_mode,
            sources=self.sources,
            confirmed_aoi_id=(
                "aoi_fixation"
                if confirmed
                else None
            ),
            allow_external_knowledge=(
                allow_external
            ),
        )

    def make_valid_response(
        self,
        *,
        response_mode: str = "compare",
    ) -> StructuredTutorResponse:
        return StructuredTutorResponse(
            response_mode=response_mode,
            answer=(
                "Fixation 保持视线在单一位置；"
                "Saccade 是 fixation 之间的快速眼动。"
            ),
            decision_summary=(
                "回答使用两个 slide sources。"
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

    def test_valid_grounded_response(self) -> None:
        result = self.validator.validate(
            self.make_request(),
            self.make_valid_response(),
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(
            result.citation_coverage,
            1.0,
        )
        self.assertTrue(
            result.confirmed_aoi_cited
        )
        self.assertEqual(result.errors, ())

    def test_unknown_source_is_error(self) -> None:
        response = StructuredTutorResponse(
            response_mode="compare",
            answer="Unsupported citation.",
            decision_summary="Invalid source test.",
            claims=[
                ClaimEvidence(
                    claim="Unsupported citation.",
                    support="direct",
                    source_ids=["invented_source"],
                )
            ],
            external_knowledge_used=False,
        )

        result = self.validator.validate(
            self.make_request(),
            response,
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            "unknown_source_id",
            [
                issue.code
                for issue in result.errors
            ],
        )

    def test_external_claim_is_rejected_when_disallowed(
        self,
    ) -> None:
        response = StructuredTutorResponse(
            response_mode="explain",
            answer="External background.",
            decision_summary=(
                "The response used external knowledge."
            ),
            claims=[
                ClaimEvidence(
                    claim="External background.",
                    support="external",
                )
            ],
            external_knowledge_used=True,
        )

        request = self.make_request(
            response_mode="explain",
            confirmed=False,
            allow_external=False,
        )

        result = self.validator.validate(
            request,
            response,
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            "external_knowledge_not_allowed",
            [
                issue.code
                for issue in result.errors
            ],
        )

    def test_external_claim_is_allowed_when_enabled(
        self,
    ) -> None:
        response = StructuredTutorResponse(
            response_mode="explain",
            answer="External background.",
            decision_summary=(
                "The response used permitted external knowledge."
            ),
            claims=[
                ClaimEvidence(
                    claim="External background.",
                    support="external",
                )
            ],
            external_knowledge_used=True,
        )

        request = self.make_request(
            response_mode="explain",
            confirmed=False,
            allow_external=True,
        )

        result = self.validator.validate(
            request,
            response,
        )

        self.assertTrue(result.is_valid)

    def test_response_mode_mismatch_is_error(self) -> None:
        result = self.validator.validate(
            self.make_request(
                response_mode="explain"
            ),
            self.make_valid_response(
                response_mode="compare"
            ),
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            "response_mode_mismatch",
            [
                issue.code
                for issue in result.errors
            ],
        )

    def test_confirmed_aoi_must_be_cited(self) -> None:
        response = StructuredTutorResponse(
            response_mode="compare",
            answer="Only saccade is described.",
            decision_summary=(
                "Only the second source was used."
            ),
            claims=[
                ClaimEvidence(
                    claim=(
                        "Saccade is a rapid eye movement "
                        "between fixations."
                    ),
                    support="direct",
                    source_ids=[
                        "slide_02_aoi_02"
                    ],
                )
            ],
            external_knowledge_used=False,
        )

        result = self.validator.validate(
            self.make_request(),
            response,
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            "confirmed_aoi_not_cited",
            [
                issue.code
                for issue in result.errors
            ],
        )

    def test_quiz_requires_active_recall_question(
        self,
    ) -> None:
        response = StructuredTutorResponse(
            response_mode="quiz",
            answer="请回忆 fixation 的定义。",
            decision_summary=(
                "问题依据 fixation source。"
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
                )
            ],
            external_knowledge_used=False,
        )

        request = self.make_request(
            response_mode="quiz"
        )

        result = self.validator.validate(
            request,
            response,
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            "missing_active_recall_question",
            [
                issue.code
                for issue in result.errors
            ],
        )

    def test_non_break_response_requires_claims(
        self,
    ) -> None:
        response = StructuredTutorResponse(
            response_mode="explain",
            answer="An answer without claims.",
            decision_summary="No claims supplied.",
            claims=[],
            external_knowledge_used=False,
        )

        request = self.make_request(
            response_mode="explain",
            confirmed=False,
        )

        result = self.validator.validate(
            request,
            response,
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            "missing_claims",
            [
                issue.code
                for issue in result.errors
            ],
        )

    def test_break_mode_allows_empty_claims(self) -> None:
        response = StructuredTutorResponse(
            response_mode="break",
            answer="好的，我们暂停一下。",
            decision_summary=(
                "用户请求暂停，没有生成教学 claim。"
            ),
            claims=[],
            external_knowledge_used=False,
        )

        request = self.make_request(
            response_mode="break",
            confirmed=False,
        )

        result = self.validator.validate(
            request,
            response,
        )

        self.assertTrue(result.is_valid)

    def test_duplicate_claim_is_warning(self) -> None:
        response = StructuredTutorResponse(
            response_mode="compare",
            answer="Repeated claims.",
            decision_summary="Duplicate test.",
            claims=[
                ClaimEvidence(
                    claim="Fixation definition.",
                    support="direct",
                    source_ids=[
                        "slide_02_aoi_01"
                    ],
                ),
                ClaimEvidence(
                    claim="  fixation   definition. ",
                    support="direct",
                    source_ids=[
                        "slide_02_aoi_01"
                    ],
                ),
            ],
            external_knowledge_used=False,
        )

        result = self.validator.validate(
            self.make_request(),
            response,
        )

        self.assertTrue(result.is_valid)
        self.assertIn(
            "duplicate_claim",
            [
                issue.code
                for issue in result.warnings
            ],
        )

    def test_require_valid_raises_for_errors(
        self,
    ) -> None:
        response = StructuredTutorResponse(
            response_mode="compare",
            answer="Invalid source.",
            decision_summary="Validation test.",
            claims=[
                ClaimEvidence(
                    claim="Invalid source.",
                    support="direct",
                    source_ids=["not_supplied"],
                )
            ],
            external_knowledge_used=False,
        )

        result = self.validator.validate(
            self.make_request(),
            response,
        )

        with self.assertRaises(
            GroundingValidationError
        ):
            result.require_valid()


if __name__ == "__main__":
    unittest.main()
