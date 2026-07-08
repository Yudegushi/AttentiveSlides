import unittest

from modules.common.schemas import GazePrediction, LearningState
from modules.interaction.intent_parser import parse_intent
from modules.interaction.reference_resolver import resolve_reference
from modules.tutor.context_retriever import MockDeckStore


def _aois():
    return MockDeckStore().get_aois(5)


class ReferenceResolverTest(unittest.TestCase):
    def test_high_confidence_deictic_uses_gaze_with_confirmation(self):
        resolved = resolve_reference(
            parse_intent("解释这个"),
            GazePrediction(5, "middle_right", "right_figure", 0.76, stable_duration_sec=2.3),
            LearningState(),
            _aois(),
        )

        self.assertEqual(resolved.resolved_aoi_id, "right_figure")
        self.assertEqual(resolved.confirmation_mode, "confirm_one")
        self.assertTrue(resolved.needs_confirmation)

    def test_medium_confidence_uses_choose_top2(self):
        resolved = resolve_reference(
            parse_intent("考我一下这个概念"),
            GazePrediction(
                5,
                "bottom_right",
                "right_figure",
                0.55,
                alternative_targets=[
                    {"aoi_id": "right_figure", "score": 0.55},
                    {"aoi_id": "bottom_caption", "score": 0.51},
                ],
            ),
            LearningState(),
            _aois(),
        )

        self.assertEqual(resolved.resolved_aoi_id, "right_figure")
        self.assertEqual(resolved.confirmation_mode, "choose_top2")
        self.assertEqual(len(resolved.alternative_targets), 2)

    def test_explicit_target_overrides_low_gaze_confidence(self):
        resolved = resolve_reference(
            parse_intent("解释右边这个图"),
            GazePrediction(5, "bottom_left", "bottom_caption", 0.30),
            LearningState(),
            _aois(),
        )

        self.assertEqual(resolved.resolved_aoi_id, "right_figure")
        self.assertEqual(resolved.confirmation_mode, "none")
        self.assertEqual(resolved.target_confidence, 1.0)

    def test_low_confidence_requires_click(self):
        resolved = resolve_reference(
            parse_intent("解释这个"),
            GazePrediction(5, "middle_right", "right_figure", 0.30),
            LearningState(),
            _aois(),
        )

        self.assertIsNone(resolved.resolved_aoi_id)
        self.assertEqual(resolved.confirmation_mode, "click_required")

    def test_low_screen_facing_selects_ask_confirmation_strategy(self):
        resolved = resolve_reference(
            parse_intent("解释这个"),
            GazePrediction(5, "middle_right", "right_figure", 0.78),
            LearningState(screen_facing_score=0.35),
            _aois(),
        )

        self.assertEqual(resolved.adaptive_strategy, "ask_confirmation")


if __name__ == "__main__":
    unittest.main()
