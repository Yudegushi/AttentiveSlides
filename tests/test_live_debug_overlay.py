from __future__ import annotations

import unittest
from pathlib import Path

from modules.system.live_debug_overlay import resolve_live_debug_aoi_id
from modules.system.live_ui_bridge import LiveInteractionProposal


def proposal(**overrides) -> LiveInteractionProposal:
    values = {
        "interaction_id": "turn-1",
        "deck_id": "deck-1",
        "slide_id": 2,
        "layout_revision": 7,
        "transcript": "explain this",
        "gaze_grid": "middle_center",
        "gaze_confidence": 0.9,
        "stable_duration_sec": 0.8,
        "predicted_aoi_id": "aoi-1",
        "target_confidence": 0.86,
        "original_speech_transcript": "explain this",
        "gaze_source": "eyetheia_local",
    }
    values.update(overrides)
    return LiveInteractionProposal(**values)


class LiveDebugOverlayTest(unittest.TestCase):
    def test_valid_completed_proposal_is_displayed(self) -> None:
        self.assertEqual(
            resolve_live_debug_aoi_id(
                deck_id="deck-1",
                slide_id=2,
                valid_aoi_ids={"aoi-1", "aoi-2"},
                proposal=proposal(),
                confirmed_interaction=None,
            ),
            "aoi-1",
        )

    def test_empty_failed_or_other_slide_proposal_does_not_replace_display(self) -> None:
        for item in (
            proposal(transcript=""),
            proposal(predicted_aoi_id=None),
            proposal(slide_id=3),
        ):
            self.assertIsNone(
                resolve_live_debug_aoi_id(
                    deck_id="deck-1",
                    slide_id=2,
                    valid_aoi_ids={"aoi-1"},
                    proposal=item,
                    confirmed_interaction=None,
                )
            )

    def test_current_manual_confirmation_overrides_proposal(self) -> None:
        confirmed = {
            "interaction": {"deck_id": "deck-1", "slide_id": 2},
            "selected_target": {"aoi_id": "aoi-2"},
        }
        self.assertEqual(
            resolve_live_debug_aoi_id(
                deck_id="deck-1",
                slide_id=2,
                valid_aoi_ids={"aoi-1", "aoi-2"},
                proposal=proposal(),
                confirmed_interaction=confirmed,
            ),
            "aoi-2",
        )

    def test_bridge_preserves_match_for_failed_turn_and_never_sets_value(self) -> None:
        source = Path(
            "modules/ui/live_debug_bridge_component/index.html"
        ).read_text(encoding="utf-8")
        self.assertIn('kind: "server_match"', source)
        self.assertIn('"attentiveslides-gaze-debug-v1"', source)
        self.assertIn("!args.matched_aoi_id && !args.clear_match", source)
        self.assertNotIn("streamlit:setComponentValue", source)


if __name__ == "__main__":
    unittest.main()
