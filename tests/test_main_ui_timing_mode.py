from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "streamlit_attentive_slides.py"


class MainUITimingModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = APP.read_text(encoding="utf-8")

    def test_mode_is_environment_gated_and_default_path_is_preserved(self) -> None:
        self.assertIn("ATTENTIVE_TIMING_EXPERIMENT_AVAILABLE", self.source)
        self.assertIn('confirm_clicked = confirm_column.button(', self.source)
        self.assertIn('confirm_clicked = st.button(', self.source)
        self.assertIn('key="main_timing_manual_submit"', self.source)
        self.assertIn('key="main_timing_live_submit"', self.source)

    def test_tutor_generation_has_a_hard_timing_mode_guard(self) -> None:
        start = self.source.index("def _generate_confirmed_turn(")
        client = self.source.index("OpenAICompatibleLLMClient.from_env()", start)
        guarded = self.source[start:client]
        self.assertIn("if _timing_mode_enabled():\n        return False", guarded)

    def test_pair_controls_and_local_log_location_are_exposed(self) -> None:
        self.assertIn('"CONTINUE TO BASELINE"', self.source)
        self.assertIn('"START NEXT PAIR"', self.source)
        self.assertIn('/ "timing_experiments"', self.source)
        self.assertIn("Tutor LLM was not called.", self.source)

    def test_ptt_timing_is_consumed_only_when_the_trial_is_submitted(self) -> None:
        record_start = self.source.index("def _record_timing_submission(")
        record_end = self.source.index("\ndef _render_confirmation_panel(", record_start)
        record = self.source[record_start:record_end]
        voice_start = self.source.index("def _render_voice_component(")
        voice_end = self.source.index("\ndef _current_voice_panel_view(", voice_start)
        voice = self.source[voice_start:voice_end]
        self.assertIn('payload["timing_started_at_browser_ms"]', record)
        self.assertIn("capture_timing_start(", record)
        self.assertNotIn("capture_timing_start(", voice)

    def test_live_transcript_uses_a_proposal_scoped_widget_key(self) -> None:
        render_start = self.source.index("def _render_unified_interaction(")
        render_end = self.source.index("\n@st.fragment", render_start)
        render = self.source[render_start:render_end]
        self.assertIn("main_live_transcript_editor_", render)
        self.assertIn("proposal.interaction_id", render)
        self.assertIn("on_change=_on_live_transcript_change", render)
        self.assertIn(
            'st.session_state["main_typed_command"] = str(transcript_value or "")',
            render,
        )
        self.assertIn(
            'str(st.session_state.get("main_typed_command") or "").strip()',
            render,
        )

    def test_baseline_submission_reruns_to_reveal_next_pair_button(self) -> None:
        start = self.source.index("def _render_confirmation_panel(")
        end = self.source.index("\ndef _clear_conversation(", start)
        confirmation = self.source[start:end]
        record = "_record_timing_submission(view, timing_submit_payload)"
        self.assertIn(f"if {record}:\n                    st.rerun()", confirmation)

    def test_arbitrary_typed_text_is_accepted_and_timing_uses_a_fresh_viewport(self) -> None:
        resolve_start = self.source.index("def _resolve_current_intent(")
        resolve_end = self.source.index("\ndef _render_quick_intent_actions(", resolve_start)
        resolve = self.source[resolve_start:resolve_end]
        workspace_start = self.source.index("def _render_slide_workspace(")
        workspace_end = self.source.index("\ndef _centered_slide_width(", workspace_start)
        workspace = self.source[workspace_start:workspace_end]
        self.assertIn('intent_input.source == "typed_text"', resolve)
        self.assertIn("and not resolution.recognized", resolve)
        self.assertIn('intent="explain"', resolve)
        self.assertIn("unrecognized typed text defaults to explain", resolve)
        self.assertNotIn("_timing_mode_enabled()", resolve)
        self.assertIn("main_timing_trial_revision", workspace)
        self.assertIn("main_timing_session_id", workspace)
        self.assertIn("key=viewport_component_key", workspace)


if __name__ == "__main__":
    unittest.main()
