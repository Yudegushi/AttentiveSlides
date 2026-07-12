"""Tests for unified interaction resolution."""

from __future__ import annotations

import unittest

from modules.common.interaction_contracts import (
    ConfirmationInput,
    InteractionInput,
    IntentInput,
    TargetCandidate,
    TargetInput,
)
from modules.common.schemas import AOI
from modules.interaction.interaction_contract_adapter import (
    resolve_interaction_input,
)


def make_aois() -> list[AOI]:
    return [
        AOI(
            aoi_id="left_text",
            bbox=[0.05, 0.1, 0.45, 0.8],
            type="text",
            text="Fixation definition.",
            name="Left text",
        ),
        AOI(
            aoi_id="right_figure",
            bbox=[0.5, 0.1, 0.95, 0.8],
            type="figure",
            text="Saccade diagram.",
            name="Right figure",
        ),
        AOI(
            aoi_id="whole_slide",
            bbox=[0.0, 0.0, 1.0, 1.0],
            type="whole_slide",
            text=(
                "Fixation definition and "
                "saccade diagram."
            ),
            name="Whole slide",
        ),
    ]


class TestInteractionContractAdapter(
    unittest.TestCase
):
    def test_unconfirmed_manual_rectangle_is_gated(
        self,
    ) -> None:
        interaction = InteractionInput(
            interaction_id="manual_gate_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="manual",
            target=TargetInput(
                source="manual_rectangle",
                slide_id=5,
                bbox=(0.5, 0.1, 0.95, 0.8),
                selected_aoi_id="right_figure",
            ),
            intent=IntentInput(
                source="typed_text",
                text="explain this",
            ),
        )

        result = resolve_interaction_input(
            interaction,
            aois=make_aois(),
        )

        self.assertTrue(
            result.resolved_query.needs_confirmation
        )
        self.assertEqual(
            result.resolved_query.confirmation_mode,
            "confirm_one",
        )
        self.assertEqual(
            result.provenance.target_source,
            "manual_rectangle",
        )

    def test_confirmed_manual_rectangle_resolves(
        self,
    ) -> None:
        interaction = InteractionInput(
            interaction_id="manual_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="manual",
            target=TargetInput(
                source="manual_rectangle",
                slide_id=5,
                bbox=(0.5, 0.1, 0.95, 0.8),
                selected_aoi_id="right_figure",
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
                confirmed_aoi_id=(
                    "right_figure"
                ),
            ),
        )

        result = resolve_interaction_input(
            interaction,
            aois=make_aois(),
        )

        self.assertEqual(
            result.resolved_query.intent,
            "explain",
        )
        self.assertEqual(
            result.resolved_query.resolved_aoi_id,
            "right_figure",
        )
        self.assertFalse(
            result.resolved_query.needs_confirmation
        )
        self.assertEqual(
            result.provenance.intent_source,
            "typed_text",
        )
        self.assertEqual(
            result.provenance.confirmation_source,
            "explicit_user_confirmation",
        )
        self.assertFalse(
            result.provenance.user_corrected
        )

    def test_ui_action_uses_explicit_intent(
        self,
    ) -> None:
        interaction = InteractionInput(
            interaction_id="ui_action_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="manual",
            target=TargetInput(
                source="manual_aoi",
                slide_id=5,
                selected_aoi_id="left_text",
            ),
            intent=IntentInput(
                source="ui_action",
                text="Explain",
                explicit_intent="explain",
            ),
            confirmation=ConfirmationInput(
                confirmed=True,
                source=(
                    "explicit_user_confirmation"
                ),
                confirmed_aoi_id="left_text",
            ),
        )

        result = resolve_interaction_input(
            interaction,
            aois=make_aois(),
        )

        self.assertEqual(
            result.intent_result.intent,
            "explain",
        )
        self.assertEqual(
            result.intent_result.confidence,
            1.0,
        )

    def test_manual_correction_overrides_proposal(
        self,
    ) -> None:
        interaction = InteractionInput(
            interaction_id="correction_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="manual",
            target=TargetInput(
                source="manual_rectangle",
                slide_id=5,
                bbox=(0.4, 0.1, 0.7, 0.8),
                selected_aoi_id="right_figure",
            ),
            intent=IntentInput(
                source="typed_text",
                text="explain this",
            ),
            confirmation=ConfirmationInput(
                confirmed=True,
                source="manual_correction",
                confirmed_aoi_id="left_text",
                corrected_from_aoi_id=(
                    "right_figure"
                ),
            ),
        )

        result = resolve_interaction_input(
            interaction,
            aois=make_aois(),
        )

        self.assertEqual(
            result.resolved_query.resolved_aoi_id,
            "left_text",
        )
        self.assertTrue(
            result.provenance.user_corrected
        )
        self.assertIn(
            "learner corrected the proposed AOI",
            result.resolved_query.evidence,
        )

    def test_gaze_and_speech_use_same_output_contract(
        self,
    ) -> None:
        interaction = InteractionInput(
            interaction_id="sensor_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="sensor_assisted",
            target=TargetInput(
                source="gaze_prediction",
                slide_id=5,
                predicted_aoi_id="right_figure",
                confidence=0.82,
                stable_duration_sec=2.0,
                alternatives=(
                    TargetCandidate(
                        aoi_id="right_figure",
                        score=0.82,
                    ),
                    TargetCandidate(
                        aoi_id="left_text",
                        score=0.40,
                    ),
                ),
            ),
            intent=IntentInput(
                source="speech_transcript",
                text="explain this",
                source_confidence=0.93,
                language="en",
            ),
            confirmation=ConfirmationInput(
                confirmed=True,
                source=(
                    "automatic_high_confidence"
                ),
            ),
        )

        result = resolve_interaction_input(
            interaction,
            aois=make_aois(),
        )

        self.assertEqual(
            result.resolved_query.resolved_aoi_id,
            "right_figure",
        )
        self.assertFalse(
            result.resolved_query.needs_confirmation
        )
        self.assertEqual(
            result.provenance.target_source,
            "gaze_prediction",
        )
        self.assertEqual(
            result.provenance.intent_source,
            "speech_transcript",
        )
        self.assertEqual(
            result.resolved_query.target_confidence,
            0.82,
        )

    def test_whole_slide_summary(self) -> None:
        interaction = InteractionInput(
            interaction_id="whole_slide_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="manual",
            target=TargetInput(
                source="whole_slide",
                slide_id=5,
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

        result = resolve_interaction_input(
            interaction,
            aois=make_aois(),
        )

        self.assertEqual(
            result.resolved_query.intent,
            "summarize",
        )
        self.assertEqual(
            result.resolved_query.resolved_aoi_id,
            "whole_slide",
        )

    def test_unknown_aoi_is_rejected(self) -> None:
        interaction = InteractionInput(
            interaction_id="invalid_aoi_001",
            deck_id="demo_deck",
            slide_id=5,
            mode="manual",
            target=TargetInput(
                source="manual_aoi",
                slide_id=5,
                selected_aoi_id="not_present",
            ),
            intent=IntentInput(
                source="typed_text",
                text="explain this",
            ),
        )

        with self.assertRaises(ValueError):
            resolve_interaction_input(
                interaction,
                aois=make_aois(),
            )


if __name__ == "__main__":
    unittest.main()
