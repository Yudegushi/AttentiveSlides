import unittest
import inspect
import tempfile
from pathlib import Path
from unittest.mock import patch

from apps import streamlit_demo
from apps.streamlit_demo import (
    _aoi_box_html,
    _app_header_html,
    _audio_profile_options,
    _confirmation_status_html,
    _default_confirmation_index,
    _profile_from_audio_label,
    _grounding_chips_html,
    _save_uploaded_audio,
    _section_heading_html,
    _slide_html,
    _transcribe_audio_for_ui,
)
from modules.common.schemas import Transcript
from modules.system.demo_view_model import build_interaction_view_model, run_scenario_turn
from modules.system.scenarios import load_scenarios


class StreamlitDemoUITest(unittest.TestCase):
    def test_header_html_uses_planned_editorial_copy(self):
        html = _app_header_html()

        self.assertNotIn("AttentiveSlides · mock tutor loop", html)
        self.assertIn("AttentiveSlides · A slide tutor that asks before it assumes.", html)
        self.assertIn("Gaze gives a hint, voice gives intent, confirmation keeps the answer grounded.", html)
        self.assertIn("as-app-header", html)

    def test_section_heading_uses_uppercase_pill_label(self):
        html = _section_heading_html("Tutor note", "Answer draft")

        self.assertIn('<div class="as-section-label">TUTOR NOTE</div>', html)
        self.assertIn("<h2>Answer draft</h2>", html)

    def test_slide_html_includes_metadata_legend_and_explicit_aoi_states(self):
        scenario = load_scenarios()[0]
        result = run_scenario_turn(scenario)
        view_model = build_interaction_view_model(result, scenario)

        html = _slide_html(view_model)

        self.assertIn("slide_05 · SHAP explanation · AOI manifest", html)
        self.assertIn("candidate", html)
        self.assertIn("confirmed", html)
        self.assertIn("available region", html)

        candidate_html = _aoi_box_html(
            {
                "aoi_id": "right_figure",
                "name": "Right figure",
                "text": "A mock figure",
                "bbox": [0.5, 0.2, 0.9, 0.7],
                "is_candidate": True,
                "is_highlighted": False,
            }
        )
        self.assertIn("candidate", candidate_html)

        confirmed_html = _aoi_box_html(
            {
                "aoi_id": "right_figure",
                "name": "Right figure",
                "text": "A mock figure",
                "bbox": [0.5, 0.2, 0.9, 0.7],
                "is_candidate": False,
                "is_highlighted": True,
            }
        )
        self.assertIn("confirmed", confirmed_html)

    def test_confirmation_status_copy_is_calm_and_target_specific(self):
        pending = _confirmation_status_html(
            pending_confirmation=True,
            target_name="right figure",
            target_id="right_figure",
        )
        confirmed = _confirmation_status_html(
            pending_confirmation=False,
            target_name="right figure",
            target_id="right_figure",
        )

        self.assertIn("I think you mean the right figure. Please confirm before I answer.", pending)
        self.assertIn("Target confirmed · right_figure", confirmed)

    def test_default_confirmation_index_prefers_gaze_hint_over_whole_slide(self):
        options = [
            {"aoi_id": "whole_slide", "name": "Whole slide"},
            {"aoi_id": "title", "name": "Title"},
            {"aoi_id": "bottom_formula", "name": "Bottom formula"},
        ]

        self.assertEqual(_default_confirmation_index(options, "bottom_formula"), 2)
        self.assertEqual(_default_confirmation_index(options, None), 1)

    def test_grounding_chips_html_uses_compact_trace_labels(self):
        scenario = load_scenarios()[0]
        result = run_scenario_turn(scenario)
        view_model = build_interaction_view_model(result, scenario)

        html = _grounding_chips_html(view_model, scenario)

        self.assertIn("intent: explain", html)
        self.assertIn("gaze hint: right_figure", html)
        self.assertIn("confidence: 0.76", html)
        self.assertIn("strategy: normal", html)
        self.assertNotIn("<metric", html.lower())

    def test_css_keeps_header_compact_and_streamlit_controls_warm(self):
        css_source = inspect.getsource(streamlit_demo._inject_css)

        self.assertIn("clamp(1.55rem, 2.6vw, 2.35rem)", css_source)
        self.assertIn("font-family: Georgia, \"Times New Roman\", serif;", css_source)
        self.assertIn("margin-top: 2.2rem", css_source)
        self.assertIn('[data-testid="stHeader"]', css_source)
        self.assertIn('[data-baseweb="select"]', css_source)
        self.assertIn(".stTextArea textarea", css_source)
        self.assertIn("letter-spacing: 0.18em;", css_source)
        self.assertIn("border-radius: 999px;", css_source)

    def test_main_layout_keeps_grounding_trace_below_primary_columns(self):
        main_source = inspect.getsource(streamlit_demo.main)

        self.assertIn("primary_left, primary_right = st.columns([1.65, 0.9], gap=\"large\")", main_source)
        right_column_body = main_source.split("with primary_right:", 1)[1].split("st.html(_section_heading_html(\"Grounding trace\"", 1)[0]

        self.assertIn("_render_response(view_model)", right_column_body)
        self.assertIn("_render_confirmation(view_model, edited_scenario)", right_column_body)
        self.assertNotIn("_render_evidence(view_model, edited_scenario)", right_column_body)

    def test_confirmation_primary_action_uses_half_width_column(self):
        confirmation_source = inspect.getsource(streamlit_demo._render_confirmation)

        self.assertIn("action_col, correction_col = st.columns([1, 1], gap=\"medium\")", confirmation_source)
        self.assertIn("action_col.button(f\"Confirm {target_name}\", type=\"primary\", use_container_width=True)", confirmation_source)

    def test_css_widens_workspace_and_makes_grounding_trace_horizontal(self):
        css_source = inspect.getsource(streamlit_demo._inject_css)

        self.assertIn("max-width: min(1600px, calc(100vw - 3rem));", css_source)
        self.assertIn("min-height: clamp(390px, 36vw, 640px);", css_source)
        self.assertIn(".as-grounding-panel", css_source)
        self.assertIn("grid-template-columns: minmax(0, 0.82fr) minmax(0, 1.18fr);", css_source)

    def test_audio_profile_labels_map_to_model_policy_profiles(self):
        labels = _audio_profile_options()

        self.assertIn("balanced (medium)", labels)
        self.assertIn("accurate (large-v3)", labels)
        self.assertIn("fast (small)", labels)
        self.assertIn("cpu fallback", labels)
        self.assertEqual(_profile_from_audio_label("balanced (medium)"), "balanced")
        self.assertEqual(_profile_from_audio_label("accurate (large-v3)"), "accurate")
        self.assertEqual(_profile_from_audio_label("fast (small)"), "fast")
        self.assertEqual(_profile_from_audio_label("cpu fallback"), "cpu")

    def test_save_uploaded_audio_writes_to_recorded_directory(self):
        class UploadedAudio:
            name = "explain.wav"

            def getbuffer(self):
                return b"RIFF fake wav"

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = _save_uploaded_audio(UploadedAudio(), output_dir=Path(temp_dir))

            self.assertEqual(Path(output_path).name, "explain.wav")
            self.assertEqual(Path(output_path).read_bytes(), b"RIFF fake wav")

    def test_transcribe_audio_for_ui_uses_selected_profile(self):
        with patch(
            "apps.streamlit_demo.transcribe_audio",
            return_value=Transcript(text="解释这个", language="zh", confidence=None),
        ) as transcribe_mock:
            text = _transcribe_audio_for_ui("sample.wav", "accurate")

        self.assertEqual(text, "解释这个")
        config = transcribe_mock.call_args.args[1]
        self.assertEqual(config.model_size, "large-v3")
        self.assertEqual(config.device, "cuda")
        self.assertEqual(config.compute_type, "int8_float16")

    def test_sidebar_controls_include_audio_input_mode_and_manual_transcribe_button(self):
        source = inspect.getsource(streamlit_demo._sidebar_controls)
        audio_source = inspect.getsource(streamlit_demo._render_audio_input_controls)

        self.assertIn("_render_audio_input_controls()", source)
        self.assertIn("Mock scenario text", audio_source)
        self.assertIn("Audio file upload", audio_source)
        self.assertIn("Recorded wav path", audio_source)
        self.assertIn("Transcribe audio", audio_source)
        self.assertIn("st.audio_input", audio_source)


if __name__ == "__main__":
    unittest.main()
