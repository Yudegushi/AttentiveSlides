from pathlib import Path
from contextlib import nullcontext
import inspect
import os
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from PIL import Image

from apps import streamlit_live
from apps.streamlit_live import build_aoi_display_label, build_aoi_overlay


class StreamlitLiveSurfaceTest(unittest.TestCase):
    def test_formal_capture_component_keeps_bounded_same_origin_cleanup_contract(self):
        component = Path(
            "modules/media/live_capture_component/index.html"
        ).read_text(encoding="utf-8")

        for expected in (
            "navigator.mediaDevices.getUserMedia",
            "Grant camera/mic",
            'fetch("/media/start"',
            'fetch("/media/video"',
            'fetch("/media/audio"',
            'fetch("/media/heartbeat"',
            'sendBeacon("/media/stop',
            'addEventListener("ended"',
            'addEventListener("mute"',
            'addEventListener("unmute"',
            "startCapture(false)",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, component)
        self.assertNotIn("http://", component)
        self.assertNotIn("https://", component)
        self.assertNotIn('id="start"', component)
        self.assertNotIn('id="stop"', component)
        self.assertEqual(component.count("Grant camera/mic"), 1)

    def test_live_app_uses_cached_shared_http_media_resources(self) -> None:
        source = Path("apps/streamlit_live.py").read_text(encoding="utf-8")

        self.assertIn("@st.cache_resource", source)
        self.assertNotIn("webrtc_streamer(", source)
        self.assertNotIn("streamlit_webrtc", source)

        resources = streamlit_live.build_live_resources(start_ingress=False)
        self.assertIs(resources.runtime.media_source, resources.ingress.source)
        self.assertIs(resources.runtime.controller.media_source, resources.ingress.source)

    def test_live_app_accepts_an_explicit_local_whisper_model(self) -> None:
        model_path = "/models/faster-whisper-small"

        with patch.dict(os.environ, {"ATTENTIVE_WHISPER_MODEL": model_path}):
            resources = streamlit_live.build_live_resources(start_ingress=False)

        transcriber = resources.runtime.controller.audio_worker.transcribe.__self__
        self.assertEqual(transcriber.config.model_size, model_path)

    def test_capture_renderer_uses_relative_url_and_poll_helper_does_not_render_it(self):
        embed = Mock()
        streamlit_live.render_capture_component(embed=embed)
        embed.assert_called_once()
        self.assertEqual(embed.call_args.args[0], "/capture")
        self.assertEqual(embed.call_args.kwargs["height"], 340)

        runtime = Mock()
        streamlit_live.poll_live_runtime(runtime)
        runtime.poll.assert_called_once_with()
        self.assertNotIn(
            "render_capture_component",
            inspect.getsource(streamlit_live.poll_live_runtime),
        )

    def test_live_workspace_places_capture_and_slide_side_by_side_above_telemetry(self):
        columns = Mock(return_value=(nullcontext(), nullcontext()))
        resources = Mock()

        with patch.object(streamlit_live, "_render_media") as render_media, patch.object(
            streamlit_live, "_render_slide_panel"
        ) as render_slide:
            streamlit_live.render_live_workspace(
                resources,
                master_switch=True,
                deck_loaded=True,
                columns=columns,
            )

        columns.assert_called_once_with((0.42, 0.58), gap="large")
        render_media.assert_called_once_with(resources, True, True)
        render_slide.assert_called_once_with(resources)

    def test_slide_panel_is_stable_outside_fragments_and_collapses_aoi_details(self):
        source = inspect.getsource(streamlit_live._render_slide_panel)

        self.assertNotIn("st.fragment", source)
        self.assertIn("st.expander", source)

    def test_aoi_overlay_marks_the_predicted_or_confirmed_target(self) -> None:
        image = Image.new("RGB", (100, 100), color="white")

        overlay = build_aoi_overlay(
            image,
            [
                {"aoi_id": "left", "bbox": [0.1, 0.1, 0.4, 0.4]},
                {"aoi_id": "right", "bbox": [0.6, 0.6, 0.9, 0.9]},
            ],
            highlighted_aoi_id="right",
        )

        self.assertNotEqual(overlay.getpixel((60, 60)), (255, 255, 255))

    def test_aoi_overlay_numbers_match_human_readable_confirmation_labels(self) -> None:
        image = Image.new("RGB", (200, 100), color="white")
        aois = [
            {
                "aoi_id": "pdf_semantic_block_10",
                "bbox": [0.1, 0.1, 0.5, 0.5],
                "type": "text",
                "text": "decision-making through providing and weighing information",
            }
        ]

        with patch("apps.streamlit_live.ImageDraw.Draw") as draw_factory:
            streamlit_live.build_aoi_overlay(image, aois, highlighted_aoi_id=None)

        draw_factory.return_value.text.assert_called_once()
        self.assertEqual(draw_factory.return_value.text.call_args.args[1], "1")
        label = build_aoi_display_label(aois[0], 1)
        self.assertIn("1 · decision-making through providing", label)
        self.assertIn("[text]", label)
        self.assertIn("pdf_semantic_block_10", label)

    def test_slide_image_uses_an_in_memory_data_uri_not_streamlit_media_route(self):
        html = streamlit_live.build_slide_image_html(
            Image.new("RGB", (8, 4), color="white"),
            caption="Slide <1>",
        )

        self.assertIn('src="data:image/jpeg;base64,', html)
        self.assertIn("Slide &lt;1&gt;", html)
        self.assertNotIn("/media/", html)
        self.assertNotIn("st.image(", inspect.getsource(streamlit_live._render_slide_panel))

    def test_live_app_surfaces_required_live_status_and_safe_signal_copy(self) -> None:
        source = Path("apps/streamlit_live.py").read_text(encoding="utf-8")

        for expected in (
            "PDF deck",
            "Master switch",
            "Transport state",
            "Runtime state",
            "Latest gaze evidence",
            "Target confirmation",
            "Grounded tutor response",
            "Use grounded API tutor",
            "Observable signals only",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, source)

    def test_slide_aoi_rendering_does_not_use_pyarrow_dataframe_conversion(self) -> None:
        source = inspect.getsource(streamlit_live._render_slide_panel)

        self.assertNotIn("st.dataframe", source)
        self.assertIn("build_aoi_display_label", source)

    def test_master_switch_uses_a_button_state_transition(self) -> None:
        self.assertTrue(
            hasattr(streamlit_live, "next_master_switch_state"),
            "the live surface must expose the button state transition",
        )
        transition = streamlit_live.next_master_switch_state
        self.assertFalse(transition(False, False))
        self.assertTrue(transition(False, True))
        self.assertTrue(transition(True, False))
        self.assertFalse(transition(True, True))

        source = Path("apps/streamlit_live.py").read_text(encoding="utf-8")
        self.assertIn("st.button(", source)
        self.assertNotIn('st.toggle("Master switch"', source)


if __name__ == "__main__":
    unittest.main()
