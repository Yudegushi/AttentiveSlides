import unittest
from pathlib import Path

from modules.common.schemas import GazePrediction, InteractionLogEvent, LearningState
from modules.interaction.intent_parser import parse_intent
from modules.interaction.reference_resolver import resolve_reference
from modules.logging.interaction_logger import InteractionLogger
from modules.tutor.context_retriever import MockDeckStore
from modules.tutor.tutor_agent import TutorAgent


class TutorAgentTest(unittest.TestCase):
    def test_tutor_agent_returns_grounded_mock_response(self):
        store = MockDeckStore()
        resolved = resolve_reference(
            parse_intent("解释右边这个图"),
            GazePrediction(5, "bottom_left", "bottom_caption", 0.30),
            LearningState(),
            store.get_aois(5),
            deck_id=store.deck_id,
        )

        response = TutorAgent().answer(resolved, deck_state=store)

        self.assertEqual(response.query_id, resolved.query_id)
        self.assertEqual(response.response_mode, "explain")
        self.assertIn("feature", response.answer)
        self.assertTrue(response.active_recall_question)
        self.assertEqual(response.used_context["aoi_id"], "right_figure")

    def test_interaction_logger_writes_jsonl(self):
        log_path = Path("/tmp/attentive_slides_test_events.jsonl")
        if log_path.exists():
            log_path.unlink()
        logger = InteractionLogger(log_path)
        event = InteractionLogEvent(
            query_id="q_test",
            timestamp=1.0,
            deck_id="mock_deck",
            slide_id=5,
            transcript="解释这个",
            intent="explain",
            predicted_aoi_id="right_figure",
            resolved_aoi_id="right_figure",
            confirmed_aoi_id=None,
            target_confidence=0.76,
            needs_confirmation=True,
            confirmation_mode="confirm_one",
            user_corrected=False,
            adaptive_strategy="normal",
            response_mode="explain",
            latency_ms=3.2,
        )

        logger.log_interaction(event)

        content = log_path.read_text(encoding="utf-8")
        self.assertEqual(content.count("\n"), 1)
        self.assertIn('"query_id": "q_test"', content)


if __name__ == "__main__":
    unittest.main()
