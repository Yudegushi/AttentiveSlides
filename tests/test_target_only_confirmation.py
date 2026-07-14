"""Tests for target-only confirmation."""

from __future__ import annotations

import unittest

from modules.common.schemas import AOI
from modules.system.manual_confirmation import (
    assess_target_confirmation,
    bind_confirmed_target_to_intent,
    build_manual_confirmation_preview,
    confirmed_target_selection_from_dict,
    confirm_target_selection,
)
from modules.system.manual_intent import (
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
            aoi_id="whole_slide",
            bbox=[
                0.0,
                0.0,
                1.0,
                1.0,
            ],
            type="whole_slide",
            text="Fixation definition.",
            name="Whole slide",
        ),
    ]


class TestTargetOnlyConfirmation(
    unittest.TestCase
):
    def make_preview(
        self,
    ):
        return (
            build_manual_confirmation_preview(
                deck_id="demo_deck",
                slide_id=1,
                target_scope="Manual region",
                bbox=[
                    0.05,
                    0.10,
                    0.45,
                    0.80,
                ],
                selected_aoi_ids=[
                    "left_text"
                ],
                selection_matches=[
                    {
                        "aoi_id": (
                            "left_text"
                        ),
                        "score": 0.9,
                    }
                ],
                slide_text=(
                    "Fixation definition."
                ),
                aois=make_aois(),
                intent_resolution=None,
            )
        )

    def test_target_can_be_confirmed_without_intent(
        self,
    ) -> None:
        preview = self.make_preview()

        assessment = (
            assess_target_confirmation(
                preview,
                selected_target_id=(
                    "left_text"
                ),
            )
        )

        self.assertTrue(
            assessment.ready
        )

        confirmed = (
            confirm_target_selection(
                preview,
                selected_target_id=(
                    "left_text"
                ),
            )
        )

        self.assertEqual(
            confirmed
            .selected_target
            .aoi_id,
            "left_text",
        )

    def test_confirmed_target_round_trip(
        self,
    ) -> None:
        confirmed = (
            confirm_target_selection(
                self.make_preview(),
                selected_target_id=(
                    "left_text"
                ),
            )
        )

        restored = (
            confirmed_target_selection_from_dict(
                confirmed.to_dict()
            )
        )

        self.assertEqual(
            restored,
            confirmed,
        )

    def test_intent_is_bound_only_when_request_is_sent(
        self,
    ) -> None:
        confirmed = (
            confirm_target_selection(
                self.make_preview(),
                selected_target_id=(
                    "left_text"
                ),
            )
        )

        resolution = (
            resolve_manual_intent(
                make_typed_intent_input(
                    "explain this"
                )
            )
        )

        interaction = (
            bind_confirmed_target_to_intent(
                confirmed,
                intent_resolution=(
                    resolution
                ),
                interaction_id=(
                    "manual_target_001"
                ),
            )
        )

        self.assertEqual(
            interaction
            .interaction
            .target
            .selected_aoi_id,
            "left_text",
        )

        self.assertEqual(
            interaction
            .interaction
            .intent
            .source,
            "typed_text",
        )


if __name__ == "__main__":
    unittest.main()
