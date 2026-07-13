"""Tests for sanitized multi-turn conversation history."""

from __future__ import annotations

import json
import unittest

from modules.system.conversation_history import (
    MAX_LLM_HISTORY_TURNS,
    assert_public_conversation_payload,
    build_conversation_turn,
    build_llm_interaction_history,
    export_conversation,
    upsert_conversation_turn,
)


def make_confirmed(
    interaction_id: str = "interaction_001",
    *,
    deck_id: str = "deck_a",
    slide_id: int = 1,
) -> dict:
    return {
        "interaction": {
            "interaction_id": interaction_id,
            "deck_id": deck_id,
            "slide_id": slide_id,
            "mode": "manual",
            "target": {
                "source": "manual_rectangle",
                "slide_id": slide_id,
                "bbox": [
                    0.1,
                    0.1,
                    0.8,
                    0.8,
                ],
                "selected_aoi_id": "definition",
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
                    "explicit_user_confirmation"
                ),
                "confirmed_aoi_id": "definition",
                "corrected_from_aoi_id": None,
            },
            "metadata": {},
        }
    }


def make_tutor(
    query_id: str = "query_001",
    answer: str = "AOI means Area of Interest.",
) -> dict:
    return {
        "query_id": query_id,
        "answer": answer,
        "response_mode": "explain",
        "decision_summary": (
            "The confirmed AOI was used."
        ),
        "active_recall_question": None,
        "validation_is_valid": True,
        "fallback_used": False,
    }


def make_xai() -> dict:
    return {
        "claims": [
            {
                "claim": (
                    "AOI means Area of Interest."
                ),
                "source_ids": [
                    "slide_001_aoi_definition"
                ],
            }
        ],
        "validation": {
            "is_valid": True,
        },
    }


def make_integrated() -> dict:
    return {
        "questions": {
            "reliability": {
                "level": "supported",
            }
        }
    }


def make_turn(
    interaction_id: str,
    *,
    deck_id: str = "deck_a",
    slide_id: int = 1,
    answer: str = "Answer",
):
    return build_conversation_turn(
        confirmed_interaction=make_confirmed(
            interaction_id,
            deck_id=deck_id,
            slide_id=slide_id,
        ),
        tutor_result=make_tutor(
            query_id=(
                f"query_{interaction_id}"
            ),
            answer=answer,
        ),
        llm_xai=make_xai(),
        integrated_xai=make_integrated(),
        timestamp_utc=(
            "2026-07-13T00:00:00+00:00"
        ),
    )


class TestConversationHistory(
    unittest.TestCase
):
    def test_turn_uses_public_whitelist(
        self,
    ) -> None:
        payload = make_turn(
            "interaction_001"
        ).to_dict()

        self.assertEqual(
            payload["intent"],
            "explain",
        )

        self.assertEqual(
            payload["confirmed_aoi_id"],
            "definition",
        )

        self.assertEqual(
            payload["source_ids"],
            [
                "slide_001_aoi_definition"
            ],
        )

    def test_upsert_is_idempotent(
        self,
    ) -> None:
        turns = upsert_conversation_turn(
            [],
            make_turn(
                "interaction_001",
                answer="First answer",
            ),
        )

        turns = upsert_conversation_turn(
            turns,
            make_turn(
                "interaction_001",
                answer="Updated answer",
            ),
        )

        self.assertEqual(
            len(turns),
            1,
        )

        self.assertEqual(
            turns[0]["answer"],
            "Updated answer",
        )

    def test_storage_is_bounded(
        self,
    ) -> None:
        turns: list[dict] = []

        for index in range(6):
            turns = upsert_conversation_turn(
                turns,
                make_turn(
                    f"interaction_{index}"
                ),
                max_stored_turns=3,
            )

        self.assertEqual(
            len(turns),
            3,
        )

        self.assertEqual(
            turns[0]["interaction_id"],
            "interaction_3",
        )

    def test_history_is_same_deck_only(
        self,
    ) -> None:
        turns = [
            make_turn(
                "a1",
                deck_id="deck_a",
            ).to_dict(),
            make_turn(
                "b1",
                deck_id="deck_b",
            ).to_dict(),
            make_turn(
                "a2",
                deck_id="deck_a",
            ).to_dict(),
        ]

        history = build_llm_interaction_history(
            turns,
            deck_id="deck_a",
        )

        self.assertEqual(
            [
                item["interaction_id"]
                for item in history
            ],
            [
                "a1",
                "a2",
            ],
        )

    def test_current_interaction_is_excluded(
        self,
    ) -> None:
        turns = [
            make_turn("a1").to_dict(),
            make_turn("a2").to_dict(),
        ]

        history = build_llm_interaction_history(
            turns,
            deck_id="deck_a",
            exclude_interaction_id="a2",
        )

        self.assertEqual(
            len(history),
            1,
        )

        self.assertEqual(
            history[0]["interaction_id"],
            "a1",
        )

    def test_history_limit_is_four(
        self,
    ) -> None:
        turns = [
            make_turn(
                f"turn_{index}"
            ).to_dict()
            for index in range(10)
        ]

        history = build_llm_interaction_history(
            turns,
            deck_id="deck_a",
            max_items=(
                MAX_LLM_HISTORY_TURNS
            ),
        )

        self.assertEqual(
            len(history),
            4,
        )

        self.assertEqual(
            history[0]["interaction_id"],
            "turn_6",
        )

    def test_long_answer_is_truncated(
        self,
    ) -> None:
        history = build_llm_interaction_history(
            [
                make_turn(
                    "long_answer",
                    answer="x" * 3000,
                )
            ],
            deck_id="deck_a",
        )

        answer = history[0][
            "assistant_answer"
        ]

        self.assertLessEqual(
            len(answer),
            1200,
        )

        self.assertIn(
            "TRUNCATED",
            answer,
        )

    def test_export_is_public(
        self,
    ) -> None:
        payload = export_conversation(
            deck_id="deck_a",
            turns=[
                make_turn(
                    "interaction_001"
                )
            ],
        )

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
        )

        self.assertEqual(
            payload["turn_count"],
            1,
        )

        self.assertNotIn(
            "raw_response",
            serialized,
        )

        self.assertNotIn(
            "provider_request_id",
            serialized,
        )

    def test_forbidden_key_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            assert_public_conversation_payload(
                {
                    "raw_response": (
                        "private provider output"
                    )
                }
            )


if __name__ == "__main__":
    unittest.main()
