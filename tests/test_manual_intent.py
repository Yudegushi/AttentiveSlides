"""Tests for typed and explicit manual intent resolution."""

from __future__ import annotations

import unittest

from modules.system.manual_intent import (
    QUICK_INTENT_ACTIONS,
    assess_intent_target,
    make_quick_action_intent_input,
    make_typed_intent_input,
    resolve_manual_intent,
)


class TestManualIntent(unittest.TestCase):
    def test_typed_explain_is_resolved(
        self,
    ) -> None:
        resolution = resolve_manual_intent(
            make_typed_intent_input(
                "explain this"
            )
        )

        self.assertEqual(
            resolution.intent,
            "explain",
        )

        self.assertTrue(
            resolution.recognized
        )

        self.assertEqual(
            resolution.intent_input.source,
            "typed_text",
        )

        self.assertGreaterEqual(
            resolution.intent_result.confidence,
            0.8,
        )

    def test_typed_deictic_reference_is_retained(
        self,
    ) -> None:
        resolution = resolve_manual_intent(
            make_typed_intent_input(
                "explain this figure"
            )
        )

        self.assertTrue(
            resolution.intent_result
            .has_deictic_reference
        )

    def test_quick_action_is_explicit(
        self,
    ) -> None:
        resolution = resolve_manual_intent(
            make_quick_action_intent_input(
                "summarize"
            )
        )

        self.assertEqual(
            resolution.intent,
            "summarize",
        )

        self.assertEqual(
            resolution.intent_input.source,
            "ui_action",
        )

        self.assertEqual(
            resolution.intent_result.confidence,
            1.0,
        )

        self.assertIn(
            (
                "intent was explicitly selected "
                "through a UI action"
            ),
            resolution.provenance,
        )

    def test_unknown_text_is_blocked(
        self,
    ) -> None:
        resolution = resolve_manual_intent(
            make_typed_intent_input(
                "do something interesting"
            )
        )

        assessment = assess_intent_target(
            resolution,
            target_available=True,
            selected_aoi_count=1,
        )

        self.assertEqual(
            resolution.intent,
            "unknown",
        )

        self.assertFalse(
            assessment.ready
        )

        self.assertEqual(
            assessment.status,
            "blocked",
        )

    def test_missing_target_is_blocked(
        self,
    ) -> None:
        resolution = resolve_manual_intent(
            make_typed_intent_input(
                "explain this"
            )
        )

        assessment = assess_intent_target(
            resolution,
            target_available=False,
            selected_aoi_count=0,
        )

        self.assertFalse(
            assessment.ready
        )

        self.assertEqual(
            assessment.status,
            "blocked",
        )

    def test_compare_with_one_target_warns(
        self,
    ) -> None:
        resolution = resolve_manual_intent(
            make_quick_action_intent_input(
                "compare"
            )
        )

        assessment = assess_intent_target(
            resolution,
            target_available=True,
            selected_aoi_count=1,
        )

        self.assertTrue(
            assessment.ready
        )

        self.assertEqual(
            assessment.status,
            "warning",
        )

    def test_quick_actions_are_unique(
        self,
    ) -> None:
        labels = [
            action.label
            for action
            in QUICK_INTENT_ACTIONS
        ]

        intents = [
            action.intent
            for action
            in QUICK_INTENT_ACTIONS
        ]

        self.assertEqual(
            len(labels),
            len(set(labels)),
        )

        self.assertEqual(
            len(intents),
            len(set(intents)),
        )

    def test_quick_actions_cover_core_intents(
        self,
    ) -> None:
        intents = {
            action.intent
            for action
            in QUICK_INTENT_ACTIONS
        }

        self.assertEqual(
            intents,
            {
                "explain",
                "summarize",
                "simplify",
                "step_by_step",
                "compare",
                "quiz",
            },
        )


if __name__ == "__main__":
    unittest.main()
