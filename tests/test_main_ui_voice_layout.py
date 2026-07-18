from __future__ import annotations

import ast
from pathlib import Path
import unittest

from modules.system.live_ui_bridge import should_auto_confirm
from modules.ui.voice_panel import build_voice_panel_view
from tests.test_live_ui_bridge import make_geometry, make_proposal


APP_PATH = Path("apps/streamlit_attentive_slides.py")


class VoicePanelMappingTests(unittest.TestCase):
    def test_ptt_and_hands_free_ready_copy(self) -> None:
        ptt = build_voice_panel_view(
            speech_mode="push_to_talk",
            turn_phase="ready",
            transcript="",
            target_label=None,
            target_needs_confirmation=False,
        )
        hands_free = build_voice_panel_view(
            speech_mode="continuous",
            turn_phase="",
            transcript="",
            target_label=None,
            target_needs_confirmation=False,
        )
        typed = build_voice_panel_view(
            speech_mode="push_to_talk",
            turn_phase="typed",
            transcript="",
            target_label=None,
            target_needs_confirmation=False,
        )
        self.assertEqual((ptt.title, ptt.detail), (
            "Ready", "Hold V or the button to speak"
        ))
        self.assertEqual(hands_free.title, "Listening for speech")
        self.assertEqual(typed.title, "Typed input ready")

    def test_sampling_confirmation_locked_and_answering_copy(self) -> None:
        sampling = build_voice_panel_view(
            speech_mode="push_to_talk",
            turn_phase="sampling",
            transcript=" explain   this ",
            target_label=None,
            target_needs_confirmation=False,
        )
        confirmation = build_voice_panel_view(
            speech_mode="push_to_talk",
            turn_phase="confirmation",
            transcript="explain",
            target_label=None,
            target_needs_confirmation=True,
        )
        locked = build_voice_panel_view(
            speech_mode="push_to_talk",
            turn_phase="locked",
            transcript="explain",
            target_label="Chart",
            target_needs_confirmation=False,
        )
        answering = build_voice_panel_view(
            speech_mode="push_to_talk",
            turn_phase="answering",
            transcript="explain",
            target_label="Chart",
            target_needs_confirmation=False,
        )
        self.assertEqual(sampling.detail, "Sampling attention")
        self.assertEqual(sampling.transcript, "explain this")
        self.assertEqual(confirmation.title, "Target needs confirmation")
        self.assertEqual(locked.title, "Target locked")
        self.assertEqual(answering.title, "Answering")

    def test_unknown_and_retryable_error_states_are_calm(self) -> None:
        unknown = build_voice_panel_view(
            speech_mode="push_to_talk",
            turn_phase="provider_internal_phase",
            transcript="",
            target_label=None,
            target_needs_confirmation=False,
        )
        error = build_voice_panel_view(
            speech_mode="push_to_talk",
            turn_phase="ready",
            transcript="",
            target_label=None,
            target_needs_confirmation=False,
            error_code="empty_transcript",
        )
        self.assertEqual(unknown.title, "Preparing voice")
        self.assertEqual((error.title, error.detail), (
            "Try again", "No speech was detected"
        ))
        self.assertTrue(error.retryable)


class MainUIVoiceLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = APP_PATH.read_text(encoding="utf-8")
        tree = ast.parse(cls.source, filename=str(APP_PATH))
        cls.functions = {
            node.name: ast.unparse(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_live_voice_waits_for_explicit_ask_tutor_submission(self) -> None:
        self.assertNotIn("Generate grounded answer", self.source)
        self.assertNotIn("main_generate_answer_button", self.source)
        maybe = self.functions["_maybe_generate_confirmed_turn"]
        self.assertIn("_confirmed_interaction_id", maybe)
        self.assertIn("main_last_generated_interaction_id", maybe)
        self.assertIn("main_last_generation_attempted_interaction_id", maybe)
        self.assertIn("_generate_confirmed_turn", maybe)

        unified = self.functions["_render_unified_interaction"]
        periodic = self.functions["_render_live_periodic"]
        status = self.functions["_render_generation_status"]
        self.assertIn("ASK TUTOR", unified)
        self.assertNotIn("CONFIRM TARGET", unified)
        self.assertIn("submission_started", unified)
        self.assertIn("_maybe_generate_confirmed_turn", unified)
        self.assertIn("main_live_full_rerun_requested", unified)
        self.assertNotIn("_maybe_generate_confirmed_turn", periodic)
        self.assertIn("LiveInteractionProposal", status)

    def test_target_scope_business_state_is_not_a_widget_key(self) -> None:
        target = self.functions["_render_target_column"]
        callback = self.functions["_on_target_scope_change"]
        self.assertIn("main_target_scope_control", target)
        self.assertIn("main_target_scope", target)
        self.assertIn("main_target_scope_control", callback)
        self.assertIn("main_target_scope", callback)

    def test_reset_turn_clears_stale_recording_errors(self) -> None:
        reset = self.functions["_reset_turn_state"]
        self.assertIn("main_conversation_error", reset)

    def test_dialogue_alone_supplies_bounded_history(self) -> None:
        generation = self.functions["_generate_confirmed_turn"]
        self.assertIn("main_interaction_flow", generation)
        self.assertIn("== 'dialogue'", generation)
        self.assertIn("main_history_max_items", generation)

    def test_all_flows_use_one_interaction_and_one_lower_answer_route(self) -> None:
        self.assertIn("_render_unified_interaction", self.functions)
        self.assertIn("_render_unified_answer", self.functions)
        self.assertNotIn("_render_live_interaction", self.functions)
        self.assertNotIn("_render_omni_interaction", self.functions)
        for obsolete in (
            "1. Live target",
            "2. Live command",
            "3. Tutor answer",
            "2. Realtime dialogue",
            "3. Realtime answer",
        ):
            self.assertNotIn(obsolete, self.source)
        lower = self.functions["_render_lower_workspace"]
        self.assertEqual(lower.count("_render_unified_answer"), 1)

    def test_control_and_tutor_output_match_compact_02_hierarchy(self) -> None:
        unified = self.functions["_render_unified_interaction"]
        target = self.functions["_render_target_column"]
        intent = self.functions["_render_intent_column"]
        lower = self.functions["_render_lower_workspace"]
        tutor = self.functions["_render_tutor_result"]
        periodic = self.functions["_render_live_periodic"]

        self.assertIn("Attention and voice controls", unified)
        self.assertIn("as-panel-index", unified)
        self.assertIn("CONTROL", unified)
        self.assertNotIn("as-status-badge", unified)
        self.assertEqual(unified.count("as-voice-state"), 1)
        self.assertIn("Target source", target)
        self.assertIn("Quick prompts", intent)
        self.assertNotIn("### Target", target)
        self.assertNotIn("### Ask tutor", intent)
        self.assertIn("TUTOR OUTPUT", lower)
        self.assertIn("main_reset_turn_button", lower)
        self.assertIn("as-tutor-meta", tutor)
        self.assertNotIn(".metric(", tutor)
        self.assertNotIn("Live transport:", periodic)

        for routine_copy in (
            "Camera and microphone are off. Typed input remains available.",
            "Attention regions are controlled from the left settings rail.",
            "The complete slide is selected.",
            "Target ready · Slide",
            "Matched: ",
            "#### Quick actions",
        ):
            self.assertNotIn(routine_copy, self.source)

    def test_default_policy_auto_confirms_only_valid_high_confidence_target(self) -> None:
        high = make_proposal(
            layout_revision=7,
            predicted_aoi_id="right",
            target_confidence=0.88,
        )
        low = make_proposal(
            layout_revision=7,
            predicted_aoi_id="right",
            target_confidence=0.79,
        )
        missing = make_proposal(
            layout_revision=7,
            predicted_aoi_id=None,
            target_confidence=0.95,
        )
        self.assertTrue(should_auto_confirm(
            high,
            make_geometry(),
            policy="Confidence-based auto",
            threshold=0.80,
            interaction_pending=False,
        ))
        for proposal in (low, missing):
            self.assertFalse(should_auto_confirm(
                proposal,
                make_geometry(),
                policy="Confidence-based auto",
                threshold=0.80,
                interaction_pending=False,
            ))


if __name__ == "__main__":
    unittest.main()
