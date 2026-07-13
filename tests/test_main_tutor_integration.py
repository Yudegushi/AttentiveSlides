"""Tests for confirmed Main UI to GroundedTutorAgent integration."""

from __future__ import annotations

import json
import unittest

from modules.common.interaction_contracts import (
    ConfirmationInput,
    InteractionInput,
    IntentInput,
    TargetCandidate,
    TargetInput,
)
from modules.common.llm_schemas import (
    LLMUsage,
)
from modules.common.schemas import (
    AOI,
)
from modules.system.main_tutor_integration import (
    assess_tutor_generation,
    build_main_tutor_context,
    generate_main_tutor_response,
)
from modules.system.main_ui_state import (
    MainUISlide,
)
from modules.tutor.api_llm_client import (
    RawLLMResponse,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
)


class StaticClient:
    provider = "test_provider"
    model = "test_model"

    def __init__(
        self,
        payload: dict,
    ) -> None:
        self.payload = payload
        self.calls = 0

    def generate(
        self,
        messages,
    ) -> RawLLMResponse:
        del messages

        self.calls += 1

        return RawLLMResponse(
            provider=self.provider,
            model=self.model,
            raw_text=json.dumps(
                self.payload,
                ensure_ascii=False,
            ),
            latency_ms=120.0,
            usage=LLMUsage(
                prompt_tokens=100,
                completion_tokens=40,
                total_tokens=140,
            ),
            request_id="private_request_id",
        )


def make_slide() -> MainUISlide:
    return MainUISlide(
        slide_id=5,
        slide_text=(
            "Fixation maintains gaze on a "
            "single location. Saccade is a "
            "rapid eye movement between fixations."
        ),
        neighbor_slide_text=(
            "Previous slide introduced "
            "visual attention."
        ),
        aois=(
            AOI(
                aoi_id="left_text",
                bbox=[
                    0.05,
                    0.1,
                    0.45,
                    0.8,
                ],
                type="text",
                text=(
                    "Fixation maintains gaze "
                    "on a single location."
                ),
                name="Fixation",
            ),
            AOI(
                aoi_id="right_figure",
                bbox=[
                    0.5,
                    0.1,
                    0.95,
                    0.8,
                ],
                type="figure",
                text=(
                    "Saccade is a rapid eye "
                    "movement between fixations."
                ),
                name="Saccade",
            ),
        ),
    )


def make_confirmed_payload() -> dict:
    interaction = InteractionInput(
        interaction_id="main_tutor_001",
        deck_id="demo_deck",
        slide_id=5,
        mode="manual",
        target=TargetInput(
            source="manual_rectangle",
            slide_id=5,
            bbox=(
                0.05,
                0.1,
                0.45,
                0.8,
            ),
            selected_aoi_id="left_text",
            alternatives=(
                TargetCandidate(
                    aoi_id="left_text",
                    score=0.95,
                ),
            ),
        ),
        intent=IntentInput(
            source="typed_text",
            text="explain this",
        ),
        confirmation=ConfirmationInput(
            confirmed=True,
            source=(
                "explicit_user_confirmation"
            ),
            confirmed_aoi_id="left_text",
        ),
        metadata={
            "confirmed_context": (
                "Fixation maintains gaze "
                "on a single location."
            ),
        },
    )

    return {
        "interaction": interaction.to_dict(),
        "selected_target": {
            "aoi_id": "left_text",
        },
        "proposed_aoi_id": "left_text",
        "corrected": False,
        "confirmed_context": (
            "Fixation maintains gaze "
            "on a single location."
        ),
    }


def valid_response() -> dict:
    return {
        "response_mode": "explain",
        "answer": (
            "Fixation 指视线保持在一个位置。"
        ),
        "decision_summary": (
            "回答使用了已确认的 "
            "Fixation AOI source。"
        ),
        "claims": [
            {
                "claim": (
                    "Fixation 指视线保持在 "
                    "一个位置。"
                ),
                "support": "direct",
                "source_ids": [
                    "slide_005_aoi_left_text"
                ],
            }
        ],
        "external_knowledge_used": False,
        "uncertainty_note": None,
        "active_recall_question": None,
    }


class TestMainTutorIntegration(
    unittest.TestCase
):
    def test_missing_confirmation_is_blocked(
        self,
    ) -> None:
        assessment = assess_tutor_generation(
            None,
            cloud_text_allowed=True,
            api_configured=True,
        )

        self.assertFalse(
            assessment.ready
        )

        self.assertEqual(
            assessment.code,
            "confirmation_missing",
        )

    def test_cloud_permission_is_required(
        self,
    ) -> None:
        assessment = assess_tutor_generation(
            make_confirmed_payload(),
            cloud_text_allowed=False,
            api_configured=True,
        )

        self.assertFalse(
            assessment.ready
        )

        self.assertEqual(
            assessment.code,
            "cloud_permission_required",
        )

    def test_api_configuration_is_required(
        self,
    ) -> None:
        assessment = assess_tutor_generation(
            make_confirmed_payload(),
            cloud_text_allowed=True,
            api_configured=False,
        )

        self.assertFalse(
            assessment.ready
        )

        self.assertEqual(
            assessment.code,
            "api_not_configured",
        )

    def test_context_uses_confirmed_aoi(
        self,
    ) -> None:
        build = build_main_tutor_context(
            make_confirmed_payload(),
            slide=make_slide(),
        )

        self.assertEqual(
            build.context.current_aoi.aoi_id,
            "left_text",
        )

        self.assertEqual(
            build.context
            .resolved_query
            .resolved_aoi_id,
            "left_text",
        )

        self.assertFalse(
            build.context
            .resolved_query
            .needs_confirmation,
        )

        self.assertEqual(
            build.context.current_aoi_text,
            (
                "Fixation maintains gaze "
                "on a single location."
            ),
        )

    def test_whole_slide_aoi_is_synthesized(
        self,
    ) -> None:
        interaction = InteractionInput(
            interaction_id="whole_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="manual",
            target=TargetInput(
                source="whole_slide",
                slide_id=5,
                selected_aoi_id="whole_slide",
            ),
            intent=IntentInput(
                source="typed_text",
                text="summarize this slide",
            ),
            confirmation=ConfirmationInput(
                confirmed=True,
                source=(
                    "explicit_user_confirmation"
                ),
                confirmed_aoi_id="whole_slide",
            ),
        )

        payload = {
            "interaction": interaction.to_dict(),
            "confirmed_context": (
                make_slide().slide_text
            ),
        }

        build = build_main_tutor_context(
            payload,
            slide=make_slide(),
        )

        self.assertEqual(
            build.context.current_aoi.aoi_id,
            "whole_slide",
        )

        self.assertEqual(
            build.context.current_aoi.text,
            make_slide().slide_text,
        )

    def test_grounded_generation_succeeds(
        self,
    ) -> None:
        client = StaticClient(
            valid_response()
        )

        agent = GroundedTutorAgent(
            llm_client=client,
            max_retries=1,
        )

        generation = (
            generate_main_tutor_response(
                make_confirmed_payload(),
                slide=make_slide(),
                agent=agent,
                cloud_text_allowed=True,
                api_configured=True,
            )
        )

        self.assertEqual(
            generation.result.status,
            "success",
        )

        self.assertTrue(
            generation.result
            .validation
            .is_valid
        )

        self.assertEqual(
            client.calls,
            1,
        )

        self.assertEqual(
            generation.public_response[
                "answer"
            ],
            (
                "Fixation 指视线保持在一个位置。"
            ),
        )

        self.assertTrue(
            generation.xai_view[
                "validation"
            ][
                "confirmed_aoi_cited"
            ]
        )

    def test_session_payload_is_sanitized(
        self,
    ) -> None:
        client = StaticClient(
            valid_response()
        )

        generation = (
            generate_main_tutor_response(
                make_confirmed_payload(),
                slide=make_slide(),
                agent=GroundedTutorAgent(
                    llm_client=client,
                ),
                cloud_text_allowed=True,
                api_configured=True,
            )
        )

        serialized = json.dumps(
            generation.to_session_payload(),
            ensure_ascii=False,
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
            "api_key",
            serialized,
        )


    def test_context_contains_sanitized_history(
        self,
    ) -> None:
        history = [
            {
                "turn_id": "turn_001",
                "interaction_id": "old_001",
                "deck_id": "demo_deck",
                "slide_id": 4,
                "timestamp_utc": (
                    "2026-07-13T00:00:00+00:00"
                ),
                "user_command": "summarize this",
                "intent": "summarize",
                "intent_source": "typed_text",
                "target_source": "whole_slide",
                "confirmed_aoi_id": "whole_slide",
                "confirmation_source": (
                    "explicit_user_confirmation"
                ),
                "corrected_from_aoi_id": None,
                "answer": "Previous summary.",
                "response_mode": "summarize",
                "decision_summary": "",
                "active_recall_question": None,
                "source_ids": [
                    "slide_004_full_text"
                ],
                "reliability_level": "supported",
                "validation_is_valid": True,
                "fallback_used": False,
            }
        ]

        build = build_main_tutor_context(
            make_confirmed_payload(),
            slide=make_slide(),
            conversation_turns=history,
            history_max_items=4,
        )

        self.assertEqual(
            len(
                build.context
                .interaction_history
            ),
            1,
        )

        self.assertEqual(
            build.context
            .interaction_history[0][
                "assistant_answer"
            ],
            "Previous summary.",
        )

        self.assertEqual(
            build.to_public_dict()[
                "history_item_count"
            ],
            1,
        )

    def test_generation_request_receives_history(
        self,
    ) -> None:
        history = [
            {
                "turn_id": "turn_001",
                "interaction_id": "old_001",
                "deck_id": "demo_deck",
                "slide_id": 4,
                "timestamp_utc": (
                    "2026-07-13T00:00:00+00:00"
                ),
                "user_command": "summarize this",
                "intent": "summarize",
                "intent_source": "typed_text",
                "target_source": "whole_slide",
                "confirmed_aoi_id": "whole_slide",
                "confirmation_source": (
                    "explicit_user_confirmation"
                ),
                "corrected_from_aoi_id": None,
                "answer": "Previous summary.",
                "response_mode": "summarize",
                "decision_summary": "",
                "active_recall_question": None,
                "source_ids": [
                    "slide_004_full_text"
                ],
                "reliability_level": "supported",
                "validation_is_valid": True,
                "fallback_used": False,
            }
        ]

        generation = generate_main_tutor_response(
            make_confirmed_payload(),
            slide=make_slide(),
            agent=GroundedTutorAgent(
                llm_client=StaticClient(
                    valid_response()
                ),
            ),
            cloud_text_allowed=True,
            api_configured=True,
            conversation_turns=history,
        )

        self.assertEqual(
            len(
                generation.result.request
                .interaction_history
            ),
            1,
        )



if __name__ == "__main__":
    unittest.main()
