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
                "metadata": {
                    "aoi_type": "text",
                    "bbox": [0.1, 0.2, 0.6, 0.7],
                    "target_confidence": 0.9,
                    "provider_request_id": "PRIVATE ID",
                },
                "warnings": [],
            }
        ],
        "claim_evidence_map": [
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
                "cited_source_count": 1,
                "all_sources_valid": valid,
                "source_validation_status": (
                    "valid" if valid else "invalid"
                ),
                "structural_validation": {
                    "status": (
                        "passed" if valid else "failed"
                    ),
                    "issues": [],
                },
                "semantic_verification": "not_performed",
                "sources": [
                    {
                        "source_id": "slide_005_aoi_left_text",
                        "source_kind": "confirmed_aoi",
                        "slide_id": 5,
                        "aoi_id": "left_text",
                        "title": "Fixation",
                        "cited": True,
                        "text_preview": (
                            "Fixation maintains gaze "
                            "on one location."
                        ),
                        "metadata": {
                            "aoi_type": "text",
                            "bbox": [0.1, 0.2, 0.6, 0.7],
                            "target_confidence": 0.9,
                            "raw_media": "PRIVATE IMAGE",
                        },
                        "warnings": [],
                        "source_existence_status": "found",
                        "citation_status": "cited",
                        "confirmed_target_match": "matching",
                        "structural_validation": {
                            "status": "passed",
                            "issues": [],
                        },
                    }
                ],
                "warnings": [],
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


def build_for_interaction(
    confirmed_interaction: dict | None,
    *,
    target_scope: str = "Live target",
    manual_bbox=None,
    selection_matches=(),
    live_proposal: dict | None = None,
) -> dict:
    return build_integrated_pipeline_xai(
        target_scope=target_scope,
        manual_bbox=manual_bbox,
        selection_matches=selection_matches,
        intent_result=make_intent_result(),
        confirmed_interaction=confirmed_interaction,
        tutor_result=None,
        llm_xai=None,
        cloud_text_allowed=True,
        live_proposal=live_proposal,
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

    def test_manual_modalities_and_correction_are_decomposed(self) -> None:
        decomposition = build_complete_payload(
            corrected=True
        )["multimodal_evidence"]
        records = {
            row["modality"]: row
            for row in decomposition["modalities"]
        }

        self.assertEqual(
            records["manual_rectangle"]["status"],
            "available",
        )
        self.assertEqual(
            records["manual_rectangle"]["metrics"]["bbox"],
            [0.1, 0.1, 0.9, 0.8],
        )
        self.assertEqual(
            records["language_intent"]["metrics"]["source"],
            "typed_text",
        )
        self.assertEqual(
            records["gaze"]["status"],
            "not_applicable",
        )
        self.assertEqual(
            records["correction"]["metrics"][
                "corrected_from_aoi_id"
            ],
            "left_text",
        )
        self.assertEqual(
            decomposition["final"]["confirmed_aoi_id"],
            "right_figure",
        )
        self.assertEqual(decomposition["fusion"], "not_performed")
        self.assertNotIn(
            "percentage",
            json.dumps(decomposition).casefold(),
        )

    def test_point_gaze_retains_dwell_layout_and_discarded_note(
        self,
    ) -> None:
        wrapper = make_confirmed_interaction()
        interaction = wrapper["interaction"]
        interaction["mode"] = "sensor_assisted"
        interaction["target"] = {
            "source": "gaze_prediction",
            "slide_id": 5,
            "predicted_aoi_id": "left_text",
            "confidence": 0.82,
            "stable_duration_sec": 0.4,
            "alternatives": [
                {
                    "aoi_id": "left_text",
                    "score": 0.82,
                    "evidence": ["local EyeTheia dwell"],
                },
                {
                    "aoi_id": "right_figure",
                    "score": 0.18,
                    "evidence": ["local EyeTheia dwell"],
                },
            ],
        }
        interaction["intent"]["source"] = "speech_transcript"
        interaction["metadata"] = {
            "gaze_source": "eyetheia_local",
            "gaze_grid": "point",
            "target_confidence": 0.82,
            "layout_revision": 7,
            "predicted_aoi_id": "left_text",
            "sensing_evidence": [
                "local point-gaze matched dwell=0.400s",
                "older layout revision evidence discarded; "
                "newest layout retained",
            ],
            "raw_gaze_coordinates": [[0.1, 0.2]],
            "provider_request_id": "PRIVATE",
        }

        decomposition = build_for_interaction(wrapper)[
            "multimodal_evidence"
        ]
        point = next(
            row
            for row in decomposition["modalities"]
            if row["modality"] == "point_gaze"
        )

        self.assertTrue(point["available"])
        self.assertEqual(point["confidence"], 0.82)
        self.assertEqual(
            point["metrics"],
            {
                "stable_duration_sec": 0.4,
                "layout_revision": 7,
            },
        )
        self.assertIn(
            "older layout revision evidence discarded",
            point["discarded_reason"],
        )
        serialized = json.dumps(decomposition)
        self.assertNotIn("raw_gaze_coordinates", serialized)
        self.assertNotIn("PRIVATE", serialized)
        privacy = build_for_interaction(wrapper)["privacy"]
        self.assertEqual(
            privacy["interaction_mode"],
            "sensor_assisted",
        )
        self.assertTrue(privacy["camera_enabled"])
        self.assertTrue(privacy["microphone_enabled"])
        self.assertIsNone(privacy["raw_biometrics_collected"])
        self.assertFalse(privacy["raw_gaze_coordinates_exposed"])

    def test_grid_gaze_and_auto_confirmation_are_distinct(self) -> None:
        wrapper = make_confirmed_interaction()
        interaction = wrapper["interaction"]
        interaction["mode"] = "sensor_assisted"
        interaction["target"] = {
            "source": "gaze_prediction",
            "slide_id": 5,
            "predicted_aoi_id": "left_text",
            "confidence": 0.76,
            "stable_duration_sec": 0.3,
            "alternatives": [],
        }
        interaction["confirmation"]["source"] = (
            "automatic_high_confidence"
        )
        interaction["metadata"] = {
            "gaze_source": "cloud_grid",
            "gaze_grid": "middle_left",
            "target_confidence": 0.76,
            "layout_revision": 4,
            "predicted_aoi_id": "left_text",
            "sensing_evidence": [
                "dwell-weighted gaze evidence=0.300s"
            ],
        }

        decomposition = build_for_interaction(wrapper)[
            "multimodal_evidence"
        ]
        records = {
            row["modality"]: row
            for row in decomposition["modalities"]
        }

        self.assertEqual(
            records["gaze_grid"]["metrics"]["gaze_grid"],
            "middle_left",
        )
        self.assertEqual(records["gaze_grid"]["confidence"], 0.76)
        self.assertTrue(
            records["confirmation"]["metrics"]["automatic"]
        )

    def test_voice_locked_target_explicitly_marks_gaze_not_applicable(
        self,
    ) -> None:
        wrapper = make_confirmed_interaction()
        interaction = wrapper["interaction"]
        interaction["target"] = {
            "source": "gaze_prediction",
            "slide_id": 5,
            "predicted_aoi_id": "left_text",
            "confidence": 1.0,
            "stable_duration_sec": 0.0,
            "alternatives": [],
        }
        interaction["metadata"] = {
            "gaze_source": "voice_locked_target",
            "gaze_grid": "unknown",
            "target_confidence": 1.0,
            "predicted_aoi_id": "left_text",
        }

        decomposition = build_for_interaction(wrapper)[
            "multimodal_evidence"
        ]
        records = {
            row["modality"]: row
            for row in decomposition["modalities"]
        }

        self.assertTrue(records["voice_locked_target"]["available"])
        self.assertIsNone(
            records["voice_locked_target"]["confidence"]
        )
        self.assertEqual(records["gaze"]["status"], "not_applicable")
        self.assertFalse(records["gaze"]["available"])
        self.assertIsNone(records["gaze"]["confidence"])
        self.assertIn(
            "gaze was not used",
            decomposition["resolver_summary"],
        )

    def test_pending_live_proposal_does_not_invent_whole_slide_input(
        self,
    ) -> None:
        payload = build_for_interaction(
            None,
            target_scope="Whole slide",
            live_proposal={
                "predicted_aoi_id": "left_text",
                "target_confidence": 0.74,
                "alternatives": [],
                "gaze_grid": "middle_left",
                "gaze_source": "cloud_grid",
                "stable_duration_sec": 0.3,
                "layout_revision": 4,
                "sensing_evidence": [
                    "dwell-weighted gaze evidence=0.300s"
                ],
            },
        )
        decomposition = payload["multimodal_evidence"]
        records = {
            row["modality"]: row
            for row in decomposition["modalities"]
        }

        self.assertNotIn("whole_slide", records)
        self.assertTrue(records["gaze_grid"]["available"])
        self.assertEqual(
            decomposition["final"]["proposed_aoi_id"],
            "left_text",
        )
        self.assertEqual(
            payload["privacy"]["interaction_mode"],
            "sensor_assisted",
        )
        self.assertTrue(payload["privacy"]["camera_enabled"])

    def test_current_layout_discard_reason_precedes_historical_note(
        self,
    ) -> None:
        wrapper = make_confirmed_interaction()
        interaction = wrapper["interaction"]
        interaction["target"] = {
            "source": "gaze_prediction",
            "slide_id": 5,
            "predicted_aoi_id": None,
            "confidence": 0.0,
            "stable_duration_sec": 0.4,
            "alternatives": [],
        }
        interaction["metadata"] = {
            "gaze_source": "eyetheia_local",
            "target_confidence": 0.0,
            "layout_revision": 6,
            "predicted_aoi_id": None,
            "sensing_evidence": [
                "older layout revision evidence discarded; "
                "newest layout retained",
                "current point-gaze evidence discarded: "
                "layout mismatch or geometry unavailable",
            ],
        }
        wrapper["proposed_aoi_id"] = None

        point = next(
            row
            for row in build_for_interaction(wrapper)[
                "multimodal_evidence"
            ]["modalities"]
            if row["modality"] == "point_gaze"
        )

        self.assertEqual(point["status"], "discarded")
        self.assertIn(
            "current point-gaze evidence discarded",
            point["discarded_reason"],
        )

    def test_language_hint_is_visible_but_not_a_target_candidate(
        self,
    ) -> None:
        intent = make_intent_result()
        intent["intent_result"]["explicit_target_hint"] = "left_text"
        payload = build_integrated_pipeline_xai(
            target_scope="Whole slide",
            manual_bbox=None,
            selection_matches=[],
            intent_result=intent,
            confirmed_interaction=None,
            tutor_result=None,
            llm_xai=None,
            cloud_text_allowed=True,
        )
        language = next(
            row
            for row in payload["multimodal_evidence"]["modalities"]
            if row["modality"] == "language_intent"
        )

        self.assertIsNone(language["candidate_aoi_id"])
        self.assertEqual(
            language["metrics"]["explicit_target_hint"],
            "left_text",
        )
        self.assertFalse(
            language["metrics"]["target_hint_used_by_resolver"]
        )

    def test_whole_slide_and_manual_aoi_are_explicit_modalities(
        self,
    ) -> None:
        whole = build_for_interaction(
            None,
            target_scope="Whole slide",
            manual_bbox=[0.0, 0.0, 1.0, 1.0],
        )["multimodal_evidence"]
        self.assertIn(
            "whole_slide",
            {
                row["modality"]
                for row in whole["modalities"]
            },
        )

        wrapper = make_confirmed_interaction()
        wrapper["interaction"]["target"] = {
            "source": "manual_aoi",
            "slide_id": 5,
            "selected_aoi_id": "left_text",
            "alternatives": [],
            "stable_duration_sec": 0.0,
        }
        manual_aoi = build_for_interaction(wrapper)[
            "multimodal_evidence"
        ]
        self.assertIn(
            "manual_aoi",
            {
                row["modality"]
                for row in manual_aoi["modalities"]
            },
        )

    def test_pending_and_malformed_proposal_fails_safe(self) -> None:
        payload = build_for_interaction(
            None,
            live_proposal={
                "predicted_aoi_id": {"private": "object"},
                "target_confidence": float("nan"),
                "stable_duration_sec": float("inf"),
                "layout_revision": "bad",
                "gaze_source": "private_provider",
                "gaze_grid": ["raw", "coordinates"],
                "sensing_evidence": [
                    "safe note",
                    3,
                    "x" * 400,
                ]
                * 5,
                "raw_media": "PRIVATE IMAGE",
                "landmarks": [[1, 2, 3]],
                "prompt": "PRIVATE PROMPT",
                "request_id": "PRIVATE ID",
            },
        )
        decomposition = payload["multimodal_evidence"]
        gaze = next(
            row
            for row in decomposition["modalities"]
            if row["modality"] == "gaze"
        )

        self.assertEqual(gaze["status"], "unavailable")
        self.assertIsNone(gaze["confidence"])
        self.assertLessEqual(len(gaze["evidence"]), 6)
        self.assertTrue(
            all(len(item) <= 240 for item in gaze["evidence"])
        )
        serialized = json.dumps(payload, allow_nan=False)
        for forbidden in (
            "PRIVATE IMAGE",
            "PRIVATE PROMPT",
            "PRIVATE ID",
            '"landmarks":',
            '"raw_media":',
        ):
            self.assertNotIn(forbidden, serialized)

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

    def test_claim_evidence_map_and_safe_metadata_are_retained(
        self,
    ) -> None:
        answer = build_complete_payload()[
            "questions"
        ]["answer"]

        claim = answer["claim_evidence_map"][0]
        source = claim["sources"][0]

        self.assertEqual(
            claim["semantic_verification"],
            "not_performed",
        )
        self.assertEqual(
            source["metadata"],
            {
                "aoi_type": "text",
                "target_confidence": 0.9,
                "bbox": [0.1, 0.2, 0.6, 0.7],
            },
        )
        serialized = json.dumps(answer)
        self.assertNotIn("PRIVATE IMAGE", serialized)
        self.assertNotIn("PRIVATE ID", serialized)

    def test_old_payload_without_claim_evidence_map_is_safe(
        self,
    ) -> None:
        llm_xai = make_llm_xai()
        llm_xai.pop("claim_evidence_map")
        payload = build_integrated_pipeline_xai(
            target_scope="Manual region",
            manual_bbox=[0.1, 0.1, 0.9, 0.8],
            selection_matches=[],
            intent_result=make_intent_result(),
            confirmed_interaction=make_confirmed_interaction(),
            tutor_result=make_tutor_result(),
            llm_xai=llm_xai,
            cloud_text_allowed=True,
        )

        self.assertEqual(
            payload["questions"]["answer"][
                "claim_evidence_map"
            ],
            [],
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
