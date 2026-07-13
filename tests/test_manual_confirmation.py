"""Tests for manual confirmation and target correction."""

from __future__ import annotations

import unittest

from modules.common.interaction_contracts import (
    interaction_input_from_dict,
)
from modules.common.schemas import AOI
from modules.system.manual_confirmation import (
    assess_manual_confirmation,
    build_manual_confirmation_preview,
    confirm_manual_interaction,
)
from modules.system.manual_intent import (
    make_quick_action_intent_input,
    make_typed_intent_input,
    resolve_manual_intent,
)


def make_aois() -> list[AOI]:
    return [
        AOI(
            aoi_id="left_text",
            bbox=[
                0.05,
                0.10,
                0.45,
                0.80,
            ],
            type="text",
            text="Fixation definition.",
            name="Fixation",
        ),
        AOI(
            aoi_id="right_figure",
            bbox=[
                0.50,
                0.10,
                0.95,
                0.80,
            ],
            type="figure",
            text="Saccade diagram.",
            name="Saccade",
        ),
        AOI(
            aoi_id="whole_slide",
            bbox=[
                0.0,
                0.0,
                1.0,
                1.0,
            ],
            type="whole_slide",
            text=(
                "Fixation definition. "
                "Saccade diagram."
            ),
            name="Whole slide",
        ),
    ]


def make_region_preview():
    return build_manual_confirmation_preview(
        deck_id="demo_deck",
        slide_id=5,
        target_scope="Manual region",
        bbox=[
            0.10,
            0.10,
            0.90,
            0.80,
        ],
        selected_aoi_ids=[
            "left_text",
            "right_figure",
        ],
        selection_matches=[
            {
                "aoi_id": "left_text",
                "score": 0.82,
            },
            {
                "aoi_id": "right_figure",
                "score": 0.71,
            },
        ],
        slide_text=(
            "Fixation definition. "
            "Saccade diagram."
        ),
        aois=make_aois(),
        intent_resolution=(
            resolve_manual_intent(
                make_typed_intent_input(
                    "explain this"
                )
            )
        ),
    )


class TestManualConfirmation(
    unittest.TestCase
):
    def test_region_preview_contains_candidates(
        self,
    ) -> None:
        preview = make_region_preview()

        self.assertEqual(
            preview.proposed_aoi_id,
            "left_text",
        )

        self.assertEqual(
            preview.target_option_ids,
            (
                "left_text",
                "right_figure",
                "whole_slide",
            ),
        )

    def test_explicit_confirmation_builds_contract(
        self,
    ) -> None:
        preview = make_region_preview()

        confirmed = confirm_manual_interaction(
            preview,
            selected_target_id="left_text",
            interaction_id="confirm_001",
        )

        interaction = confirmed.interaction

        self.assertEqual(
            interaction.target.source,
            "manual_rectangle",
        )

        self.assertEqual(
            interaction.target.selected_aoi_id,
            "left_text",
        )

        self.assertEqual(
            interaction.confirmation.source,
            "explicit_user_confirmation",
        )

        self.assertFalse(
            confirmed.corrected
        )

    def test_target_correction_is_recorded(
        self,
    ) -> None:
        preview = make_region_preview()

        confirmed = confirm_manual_interaction(
            preview,
            selected_target_id="right_figure",
            interaction_id="confirm_002",
        )

        interaction = confirmed.interaction

        self.assertTrue(
            confirmed.corrected
        )

        self.assertEqual(
            interaction.confirmation.source,
            "manual_correction",
        )

        self.assertEqual(
            interaction.confirmation
            .corrected_from_aoi_id,
            "left_text",
        )

        self.assertEqual(
            interaction.confirmation
            .confirmed_aoi_id,
            "right_figure",
        )

    def test_whole_slide_override(
        self,
    ) -> None:
        preview = make_region_preview()

        confirmed = confirm_manual_interaction(
            preview,
            selected_target_id="whole_slide",
            interaction_id="confirm_003",
        )

        self.assertEqual(
            confirmed.interaction.target.source,
            "whole_slide",
        )

        self.assertEqual(
            confirmed.interaction
            .confirmation
            .source,
            "manual_correction",
        )

    def test_whole_slide_initial_confirmation(
        self,
    ) -> None:
        preview = build_manual_confirmation_preview(
            deck_id="demo_deck",
            slide_id=5,
            target_scope="Whole slide",
            bbox=None,
            selected_aoi_ids=[
                "whole_slide"
            ],
            selection_matches=[],
            slide_text="Whole slide text.",
            aois=make_aois(),
            intent_resolution=(
                resolve_manual_intent(
                    make_quick_action_intent_input(
                        "summarize"
                    )
                )
            ),
        )

        confirmed = confirm_manual_interaction(
            preview,
            selected_target_id="whole_slide",
            interaction_id="confirm_004",
        )

        self.assertEqual(
            confirmed.interaction.target.source,
            "whole_slide",
        )

        self.assertEqual(
            confirmed.interaction
            .intent
            .source,
            "ui_action",
        )

        self.assertEqual(
            confirmed.interaction
            .confirmation
            .source,
            "explicit_user_confirmation",
        )

    def test_unknown_intent_is_blocked(
        self,
    ) -> None:
        preview = build_manual_confirmation_preview(
            deck_id="demo_deck",
            slide_id=5,
            target_scope="Whole slide",
            bbox=None,
            selected_aoi_ids=[
                "whole_slide"
            ],
            selection_matches=[],
            slide_text="Whole slide text.",
            aois=make_aois(),
            intent_resolution=(
                resolve_manual_intent(
                    make_typed_intent_input(
                        "do something interesting"
                    )
                )
            ),
        )

        assessment = assess_manual_confirmation(
            preview,
            selected_target_id="whole_slide",
        )

        self.assertFalse(
            assessment.ready
        )

        self.assertEqual(
            assessment.status,
            "blocked",
        )

    def test_confirmed_contract_round_trip(
        self,
    ) -> None:
        preview = make_region_preview()

        confirmed = confirm_manual_interaction(
            preview,
            selected_target_id="right_figure",
            interaction_id="confirm_005",
        )

        restored = interaction_input_from_dict(
            confirmed.interaction.to_dict()
        )

        self.assertEqual(
            restored,
            confirmed.interaction,
        )

    def test_invalid_target_is_rejected(
        self,
    ) -> None:
        preview = make_region_preview()

        with self.assertRaises(
            ValueError
        ):
            confirm_manual_interaction(
                preview,
                selected_target_id=(
                    "not_available"
                ),
                interaction_id="confirm_006",
            )


if __name__ == "__main__":
    unittest.main()
