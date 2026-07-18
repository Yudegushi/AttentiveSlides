from __future__ import annotations

import ast
from pathlib import Path
import unittest

from modules.system.main_ui_state import (
    build_main_conversation_defaults,
    build_main_live_defaults,
)


APP_PATH = Path("apps/streamlit_attentive_slides.py")
STATE_PATH = Path("modules/system/main_ui_state.py")
CSS_PATH = Path("modules/ui/workspace.css")


class MainUIWorkspaceLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = APP_PATH.read_text(encoding="utf-8")
        cls.state_source = STATE_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(cls.source, filename=str(APP_PATH))
        cls.functions = {
            node.name: ast.unparse(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_flow_defaults_and_internal_mapping_are_exact(self) -> None:
        defaults = build_main_live_defaults()
        self.assertEqual(defaults["main_interaction_flow"], "one_turn")
        self.assertEqual(defaults["main_speech_mode"], "push_to_talk")
        self.assertEqual(defaults["main_voice_engine"], "single_turn")
        self.assertFalse(build_main_conversation_defaults()["main_history_enabled"])
        self.assertIn('"one_turn": "single_turn"', self.source)
        self.assertIn('"dialogue": "single_turn"', self.source)
        self.assertIn('"realtime": "omni"', self.source)
        callback = self.functions["_on_interaction_flow_change"]
        self.assertIn("FLOW_ENGINE[flow]", callback)
        self.assertIn("flow == 'dialogue'", callback)

    def test_old_top_level_mode_is_fully_removed(self) -> None:
        self.assertNotIn("main_interaction_mode", self.source)
        self.assertNotIn("main_interaction_mode", self.state_source)
        self.assertNotIn('options=["Manual", "Live"]', self.source)

    def test_master_control_is_the_media_runtime_gate(self) -> None:
        helper = self.functions["_media_runtime_requested"]
        self.assertIn("main_live_master_enabled", helper)
        self.assertIn("_study_mutations_enabled", helper)
        controls = self.functions["_render_live_controls"]
        self.assertIn("enabled = _media_runtime_requested(resources)", controls)
        self.assertIn("set_master_enabled(enabled)", controls)
        self.assertIn("_media_runtime_requested(resources)", self.functions["_learner_state_view"])
        self.assertIn("_media_runtime_requested(resources)", self.functions["_render_tutor_result"])
        self.assertIn("_media_runtime_requested(live_resources)", self.functions["_render_manual_interaction"])
        builder = self.functions["build_main_live_resources"]
        self.assertNotIn("service.ensure_started()", builder)
        self.assertIn("resources.service.ensure_started()", controls)
        self.assertNotIn("resources.service.shutdown()", controls)

    def test_palette_confirmation_and_slide_rail_defaults(self) -> None:
        defaults = build_main_live_defaults()
        self.assertEqual(defaults["main_confirmation_policy"], "Confidence-based auto")
        self.assertEqual(defaults["main_auto_confirm_threshold"], 0.80)
        self.assertEqual(defaults["main_ui_palette"], "ivory-study-desk")
        self.assertTrue(defaults["main_slide_rail_expanded"])
        controls = self.functions["_render_live_controls"]
        self.assertIn("Palette is locked", Path(
            "modules/ui/palette_control_component/index.html"
        ).read_text(encoding="utf-8"))
        self.assertIn("render_palette_control", controls)
        palette = Path(
            "modules/ui/palette_control_component/index.html"
        ).read_text(encoding="utf-8")
        self.assertIn("!Boolean(args.locked)", palette)

    def test_visible_shell_uses_flow_speaking_and_advanced_sections(self) -> None:
        controls = self.functions["_render_live_controls"]
        for label in (
            "1 turn",
            "Dialogue",
            "Realtime",
            "Hold",
            "Hands-free",
            "Advanced voice settings",
        ):
            self.assertIn(label, controls)
        self.assertNotIn('key="main_voice_engine"', controls)
        self.assertIn("segmented_control", controls)
        self.assertIn("RUNTIME CONFIGURATION", controls)

    def test_shell_header_and_slide_selector_use_fixed_02_contract(self) -> None:
        selector = self.functions["_render_slide_selector"]
        header = self.functions["_render_header"]
        brand = self.functions["_render_sidebar_brand"]
        self.assertNotIn("st.popover", selector)
        self.assertIn("DECK INDEX", selector)
        self.assertIn("DECK /", selector)
        self.assertIn("main_slide_rail_collapse_button", selector)
        self.assertIn("main_slide_rail_expand_button", selector)
        self.assertIn("STUDY / WORKSPACE", header)
        self.assertIn("REVIEW / WORKSPACE", header)
        self.assertNotIn("AttentiveSlides", header)
        self.assertIn("AttentiveSlides", brand)
        for key in (
            "main_sidebar_brand",
            "main_topbar",
            "main_study_shell",
            "main_slide_toolbar",
            "main_slide_stage",
            "main_interaction_workspace",
            "main_tutor_answer",
            "main_slide_rail",
            "main_slide_rail_reopen",
        ):
            self.assertIn(key, self.source)
        self.assertIn("--as-left-rail-width: 226px", self.css)
        self.assertIn("--as-right-rail-width: 190px", self.css)
        self.assertIn(".st-key-main_sidebar_brand", self.css)
        self.assertIn(".st-key-main_topbar", self.css)
        self.assertIn("position: fixed", self.css)

    def test_main_has_compact_two_column_shell_and_lower_answer(self) -> None:
        main = self.functions["main"]
        self.assertIn("st.container(key='main_study_shell')", main)
        self.assertIn("st.columns([1.0, 0.33]", main)
        self.assertIn("gap='small'", main)
        slide_block = main.split("with slide_column:", 1)[1].split(
            "with interaction_column:", 1
        )[0]
        self.assertIn("_render_slide_workspace", slide_block)
        self.assertIn("_render_lower_workspace", slide_block)
        self.assertIn("_render_manual_interaction", main)
        lower = self.functions["_render_lower_workspace"]
        self.assertIn("main_tutor_answer", lower)
        self.assertIn("Tutor explanation", lower)

if __name__ == "__main__":
    unittest.main()
