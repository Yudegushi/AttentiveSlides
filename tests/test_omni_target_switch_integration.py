import unittest

from modules.common.schemas import AOI, VisualContextItem
from modules.realtime.realtime_contracts import TargetBinding
from modules.system.main_ui_state import MainUISlide
from modules.system.target_switching import SwitchIntent, TargetSwitchController

from apps.streamlit_attentive_slides import _target_binding_from_slide


class OmniTargetSwitchIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slide = MainUISlide(
            slide_id=1,
            slide_text="Native slide text",
            neighbor_slide_text="",
            aois=(
                AOI("a", [0.0, 0.0, 0.5, 1.0], "text", "Native A", "Area A"),
                AOI("b", [0.5, 0.0, 1.0, 1.0], "image", "", "Chart B"),
            ),
            visual_context=(
                VisualContextItem(
                    visual_id="visual-b",
                    type="chart",
                    bbox=[0.5, 0.0, 1.0, 1.0],
                    description="A model-derived rising line",
                    transcription="Revenue by year",
                    linked_aoi_id="b",
                ),
            ),
        )

    def test_adapter_uses_stable_ids_and_visual_evidence_precedence(self) -> None:
        whole = _target_binding_from_slide(
            deck_id="deck", slide=self.slide, target_id="whole_slide"
        )
        native = _target_binding_from_slide(
            deck_id="deck", slide=self.slide, target_id="a"
        )
        visual = _target_binding_from_slide(
            deck_id="deck", slide=self.slide, target_id="b"
        )
        missing = _target_binding_from_slide(
            deck_id="deck", slide=self.slide, target_id="missing"
        )

        self.assertIsNotNone(whole)
        self.assertEqual(whole.target_id, "whole-slide")
        self.assertEqual(native.text, "Native A")
        self.assertIn("Visible transcription: Revenue by year", visual.text)
        self.assertIn("Visual description: A model-derived rising line", visual.text)
        self.assertIsNone(missing)

    def test_gaze_candidate_does_not_switch_without_explicit_confirmation(self) -> None:
        active = TargetBinding("deck", 1, "a", "Area A", "Native A")
        candidate = TargetBinding("deck", 1, "b", "Chart B", "Visual B")
        controller = TargetSwitchController()
        controller.bind(active)
        controller.observe_candidate(candidate)

        ordinary = controller.handle_transcript("Please explain it more simply")
        self.assertIs(ordinary.intent, SwitchIntent.KEEP)
        self.assertEqual(ordinary.active_target.signature, active.signature)
        self.assertTrue(ordinary.should_create_response)

        proposed = controller.handle_transcript("Switch to this one")
        self.assertIs(proposed.intent, SwitchIntent.PROPOSE)
        self.assertEqual(controller.active_target.signature, active.signature)
        self.assertFalse(proposed.should_create_response)

        confirmed = controller.confirm()
        self.assertIs(confirmed.intent, SwitchIntent.CONFIRM)
        self.assertEqual(controller.active_target.signature, candidate.signature)


if __name__ == "__main__":
    unittest.main()
