import unittest

from modules.common.schemas import GazePrediction, LearningState
from modules.interaction.intent_parser import parse_intent
from modules.interaction.reference_resolver import resolve_reference
from modules.tutor.context_retriever import ContextRetriever, MockDeckStore


class ContextRetrieverTest(unittest.TestCase):
    def test_context_retriever_returns_slide_and_aoi_text(self):
        store = MockDeckStore()
        resolved = resolve_reference(
            parse_intent("解释右边这个图"),
            GazePrediction(5, "middle_right", "right_figure", 0.2),
            LearningState(),
            store.get_aois(5),
            deck_id=store.deck_id,
        )

        context = ContextRetriever(store).retrieve_context(resolved)

        self.assertIsNotNone(context.current_aoi)
        self.assertEqual(context.current_aoi.aoi_id, "right_figure")
        self.assertIn("feature contributions", context.current_aoi_text)
        self.assertIn("SHAP values", context.current_slide_text)


if __name__ == "__main__":
    unittest.main()
