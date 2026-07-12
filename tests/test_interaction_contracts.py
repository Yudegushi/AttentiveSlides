"""Tests for hardware-independent interaction contracts."""

from __future__ import annotations

import unittest

from modules.common.interaction_contracts import (
    ConfirmationInput,
    InteractionInput,
    IntentInput,
    TargetCandidate,
    TargetInput,
    interaction_input_from_dict,
)


class TestInteractionContracts(unittest.TestCase):
    def test_manual_rectangle_round_trip(self) -> None:
        interaction = InteractionInput(
            interaction_id="manual_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="manual",
            target=TargetInput(
                source="manual_rectangle",
                slide_id=5,
                bbox=(0.1, 0.2, 0.6, 0.7),
                selected_aoi_id="right_figure",
            ),
            intent=IntentInput(
                source="typed_text",
                text="explain this",
                language="en",
            ),
            confirmation=ConfirmationInput(
                confirmed=True,
                source=(
                    "explicit_user_confirmation"
                ),
                confirmed_aoi_id=(
                    "right_figure"
                ),
            ),
        )

        restored = interaction_input_from_dict(
            interaction.to_dict()
        )

        self.assertEqual(
            restored,
            interaction,
        )

    def test_manual_mode_rejects_gaze(self) -> None:
        with self.assertRaises(ValueError):
            InteractionInput(
                interaction_id="invalid_001",
                deck_id="demo_deck",
                slide_id=5,
                mode="manual",
                target=TargetInput(
                    source="gaze_prediction",
                    slide_id=5,
                    predicted_aoi_id=(
                        "right_figure"
                    ),
                    confidence=0.8,
                ),
                intent=IntentInput(
                    source="typed_text",
                    text="explain this",
                ),
            )

    def test_manual_mode_rejects_speech(self) -> None:
        with self.assertRaises(ValueError):
            InteractionInput(
                interaction_id="invalid_002",
                deck_id="demo_deck",
                slide_id=5,
                mode="manual",
                target=TargetInput(
                    source="manual_aoi",
                    slide_id=5,
                    selected_aoi_id=(
                        "right_figure"
                    ),
                ),
                intent=IntentInput(
                    source="speech_transcript",
                    text="explain this",
                ),
            )

    def test_ui_action_requires_intent(self) -> None:
        with self.assertRaises(ValueError):
            IntentInput(
                source="ui_action"
            )

    def test_manual_rectangle_requires_bbox(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            TargetInput(
                source="manual_rectangle",
                slide_id=5,
            )

    def test_bbox_must_be_normalized(self) -> None:
        with self.assertRaises(ValueError):
            TargetInput(
                source="manual_rectangle",
                slide_id=5,
                bbox=(-0.1, 0.2, 0.5, 0.6),
            )

    def test_duplicate_candidates_rejected(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            TargetInput(
                source="manual_rectangle",
                slide_id=5,
                bbox=(0.1, 0.2, 0.5, 0.6),
                alternatives=(
                    TargetCandidate(
                        aoi_id="right_figure",
                        score=0.8,
                    ),
                    TargetCandidate(
                        aoi_id="right_figure",
                        score=0.7,
                    ),
                ),
            )

    def test_automatic_confirmation_requires_gaze(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            InteractionInput(
                interaction_id="invalid_003",
                deck_id="demo_deck",
                slide_id=5,
                mode="hybrid",
                target=TargetInput(
                    source="manual_aoi",
                    slide_id=5,
                    selected_aoi_id=(
                        "right_figure"
                    ),
                ),
                intent=IntentInput(
                    source="typed_text",
                    text="explain this",
                ),
                confirmation=ConfirmationInput(
                    confirmed=True,
                    source=(
                        "automatic_high_confidence"
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
