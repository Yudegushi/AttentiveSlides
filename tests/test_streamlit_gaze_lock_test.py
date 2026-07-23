import ast
from pathlib import Path
import unittest

from scripts.run_live_single_port import parse_args


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "streamlit_gaze_lock_test.py"


class StreamlitGazeLockTestModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(APP))

    def test_is_a_standalone_parseable_app_selected_by_parameter(self):
        self.assertIsNotNone(self.tree)
        self.assertEqual(
            parse_args([]).streamlit_app,
            "apps/streamlit_attentive_slides.py",
        )
        self.assertEqual(
            parse_args(
                ["--streamlit-app", "apps/streamlit_gaze_lock_test.py"]
            ).streamlit_app,
            "apps/streamlit_gaze_lock_test.py",
        )
        self.assertNotIn("streamlit_attentive_slides", self.source)

    def test_contains_only_the_b_gaze_lock_typed_workflow(self):
        for required in (
            '"B Gaze-Lock Typed Test"',
            '"LOCK GAZE TARGET"',
            '"RETARGET"',
            '"Typed question"',
            '"ASK TUTOR"',
            "render_slide_viewport(",
            "render_live_debug_bridge(",
            "build_typed_interaction(",
            "generate_main_tutor_response(",
        ):
            self.assertIn(required, self.source)
        for forbidden in (
            "speech_transcript",
            "AudioContext",
            "main_interactions.jsonl",
            "timing_experiment",
            "manual_rectangle",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_lock_is_revalidated_before_tutor_and_logs_are_separate(self):
        ask_start = self.source.index("if st.button(\n            \"ASK TUTOR\"")
        ask_source = self.source[ask_start:]
        self.assertIn("lock_is_current(target, current_scope)", ask_source)
        self.assertLess(
            ask_source.index("lock_is_current(target, current_scope)"),
            ask_source.index("_ask_tutor("),
        )
        self.assertIn("gaze_lock_log_path(", self.source)
        self.assertIn('"gaze_lock_session_id"', self.source)


if __name__ == "__main__":
    unittest.main()
