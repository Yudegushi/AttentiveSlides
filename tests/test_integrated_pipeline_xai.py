"""Tests for integrated pipeline-level public XAI."""

from __future__ import annotations

import json
import unittest

from modules.system.integrated_pipeline_xai import (
    assert_public_integrated_xai_payload,
    build_integrated_pipeline_xai,
)


def make_intent_result() -> dict:
    return {
        "intent_input": {
            "source": "typed_text",
            "text": "explain this",
            "explicit_intent": None,
        },
        "intent_result": {
            "intent": "explain",
            "confidence": 0.9,
            "has_deictic_reference": True,
            "explicit_target_hint": None,
            "transcript": "explain this",
        },
        "recognized": True,
        "provenance": [
            "intent source = typed_text",
            "resolved intent = explain",
            "intent confidence = 0.900",
        ],
    }


def make_confirmed_interaction(
    *,
    corrected: bool = False,
) -> dict:
    confirmed_aoi_id = (
        "right_figure"
        if corrected
        else "left_text"
    )

    confirmation_source = (
        "manual_correction"
        if corrected
        else "explicit_user_confirmation"
    )

    return {
        "interaction": {
            "interaction_id": "xai_test_001",
            "deck_id": "demo_deck",
            "slide_id": 5,
            "mode": "manual",
            "target": {
                "source": "manual_rectangle",
                "slide_id": 5,
                "bbox": [
                    0.1,
                    0.1,
                    0.9,
                    0.8,
                ],
                "selected_aoi_id": (
                    confirmed_aoi_id
                ),
                "alternatives": [],
            },
            "intent": {
                "source": "typed_text",
                "text": "explain this",
                "explicit_intent": None,
            },
            "confirmation": {
                "confirmed": True,
                "source": (
                    confirmation_source
                ),
                "confirmed_aoi_id": (
                    confirmed_aoi_id
                ),
                "corrected_from_aoi_id": (
                    "left_text"
                    if corrected
                    else None
                ),
            },
            "metadata": {
                "privacy_mode": (
                    "camera_and_microphone_disabled"
                )
            },
        },
        "selected_target": {
            "aoi_id": confirmed_aoi_id,
        },
        "proposed_aoi_id": "left_text",
        "corrected": corrected,
        "confirmed_context": (
            "Selected educational context."
        ),
    }


def make_tutor_result(
    *,
    fallback_used: bool = False,
) -> dict:
    return {
        "status": (
            "fallback"
            if fallback_used
            else "success"
        ),
        "response_mode": "explain",
        "answer": (
            "Fixation maintains gaze "
            "on one location."
        ),
        "active_recall_question": None,
        "uncertainty_note": None,
        "decision_summary": (
            "The answer uses the confirmed AOI."
        ),
        "external_knowledge_used": False,
        "validation_is_valid": True,
        "provider": "test_provider",
        "model": "test_model",
        "latency_ms": 100.0,
        "retry_count": 0,
        "fallback_used": fallback_used,
        "total_tokens": 120,
    }


def make_llm_xai(
    *,
    valid: bool = True,
    fallback_used: bool = False,
) -> dict:
    return {
        "decision_summary": (
            "The answer uses the confirmed AOI."
        ),
        "claims": [
            {
                "claim_index": 1,
                "claim": (
                    "Fixation maintains gaze "
                    "on one location."
                ),
                "support": "direct",
                "source_ids": [
                    "slide_005_aoi_left_text"
                ],
                "all_sources_valid": valid,
            }
        ],
        "sources": [
            {
                "source_id": (
                    "slide_005_aoi_left_text"
                ),
                "source_kind": "confirmed_aoi",
                "slide_id": 5,
                "aoi_id": "left_text",
                "title": "Fixation",
                "cited": True,
                "text_preview": (
                    "Fixation maintains gaze "
                    "on one location."
                ),
            }
        ],
        "validation": {
            "is_valid": valid,
            "citation_coverage": (
                1.0 if valid else 0.0
            ),
            "confirmed_aoi_cited": valid,
            "issues": [],
        },
        "telemetry": {
            "provider": "test_provider",
            "model": "test_model",
            "latency_ms": 100.0,
            "retry_count": 0,
            "fallback_used": fallback_used,
        },
    }


def build_complete_payload(
    *,
    corrected: bool = False,
    valid: bool = True,
    fallback_used: bool = False,
) -> dict:
    return build_integrated_pipeline_xai(
        target_scope="Manual region",
        manual_bbox=[
            0.1,
            0.1,
            0.9,
            0.8,
        ],
        selection_matches=[
            {
                "aoi_id": "left_text",
                "aoi_type": "text",
                "score": 0.82,
                "selection_coverage": 0.75,
                "aoi_coverage": 0.88,
                "intersection_over_union": 0.67,
            },
            {
                "aoi_id": "right_figure",
                "aoi_type": "figure",
                "score": 0.71,
                "selection_coverage": 0.62,
                "aoi_coverage": 0.77,
                "intersection_over_union": 0.54,
            },
        ],
        intent_result=make_intent_result(),
        confirmed_interaction=(
            make_confirmed_interaction(
                corrected=corrected
            )
        ),
        tutor_result=make_tutor_result(
            fallback_used=fallback_used
        ),
        llm_xai=make_llm_xai(
            valid=valid,
            fallback_used=fallback_used,
        ),
        cloud_text_allowed=True,
    )


class TestIntegratedPipelineXAI(
    unittest.TestCase
):
    def test_complete_pipeline_is_supported(
        self,
    ) -> None:
        payload = build_complete_payload()

        self.assertEqual(
            payload["pipeline_status"],
            "complete",
        )

        self.assertEqual(
            payload["questions"][
                "reliability"
            ]["level"],
            "supported",
        )

    def test_target_overlap_is_explained(
        self,
    ) -> None:
        target = build_complete_payload()[
            "questions"
        ]["target"]

        self.assertEqual(
            target["target_source"],
            "manual_rectangle",
        )

        self.assertEqual(
            target["confirmed_aoi_id"],
            "left_text",
        )

        self.assertEqual(
            len(target["candidates"]),
            2,
        )

        self.assertFalse(
            target[
                "corrected_by_learner"
            ]
        )

    def test_manual_correction_is_explained(
        self,
    ) -> None:
        target = build_complete_payload(
            corrected=True
        )["questions"]["target"]

        self.assertTrue(
            target[
                "corrected_by_learner"
            ]
        )

        self.assertEqual(
            target[
                "corrected_from_aoi_id"
            ],
            "left_text",
        )

        self.assertEqual(
            target[
                "confirmed_aoi_id"
            ],
            "right_figure",
        )

        self.assertIn(
            "explicitly corrected",
            target["explanation"],
        )

    def test_typed_intent_provenance(
        self,
    ) -> None:
        intent = build_complete_payload()[
            "questions"
        ]["intent"]

        self.assertEqual(
            intent["source"],
            "typed_text",
        )

        self.assertEqual(
            intent["resolved_intent"],
            "explain",
        )

        self.assertTrue(
            intent[
                "has_deictic_reference"
            ]
        )

        self.assertFalse(
            intent[
                "explicit_user_choice"
            ]
        )

    def test_claim_source_mapping_is_retained(
        self,
    ) -> None:
        answer = build_complete_payload()[
            "questions"
        ]["answer"]

        self.assertEqual(
            answer["claim_count"],
            1,
        )

        self.assertEqual(
            answer["source_count"],
            1,
        )

        self.assertEqual(
            answer["claims"][0][
                "source_ids"
            ],
            [
                "slide_005_aoi_left_text"
            ],
        )

    def test_failed_validation_is_unsupported(
        self,
    ) -> None:
        reliability = build_complete_payload(
            valid=False
        )["questions"]["reliability"]

        self.assertEqual(
            reliability["level"],
            "unsupported",
        )

        self.assertFalse(
            reliability[
                "validation_is_valid"
            ]
        )

    def test_fallback_produces_caution(
        self,
    ) -> None:
        reliability = build_complete_payload(
            fallback_used=True
        )["questions"]["reliability"]

        self.assertEqual(
            reliability["level"],
            "caution",
        )

        self.assertTrue(
            reliability[
                "fallback_used"
            ]
        )

    def test_pending_pipeline_before_generation(
        self,
    ) -> None:
        payload = build_integrated_pipeline_xai(
            target_scope="Whole slide",
            manual_bbox=[
                0.0,
                0.0,
                1.0,
                1.0,
            ],
            selection_matches=[],
            intent_result=(
                make_intent_result()
            ),
            confirmed_interaction=None,
            tutor_result=None,
            llm_xai=None,
            cloud_text_allowed=True,
        )

        self.assertNotEqual(
            payload["pipeline_status"],
            "complete",
        )

        self.assertEqual(
            payload["questions"][
                "reliability"
            ]["level"],
            "pending",
        )

        self.assertGreaterEqual(
            len(
                payload[
                    "corrective_actions"
                ]
            ),
            1,
        )

    def test_public_payload_has_no_private_fields(
        self,
    ) -> None:
        payload = build_complete_payload()

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
        ).casefold()

        for forbidden in [
            "raw_response",
            "provider_request_id",
            "api_key",
            "chain_of_thought",
            "hidden_reasoning",
        ]:
            self.assertNotIn(
                forbidden,
                serialized,
            )

    def test_forbidden_public_key_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            assert_public_integrated_xai_payload(
                {
                    "questions": {},
                    "raw_response": (
                        "private provider output"
                    ),
                }
            )


if __name__ == "__main__":
    unittest.main()
