from pathlib import Path
import unittest

from PIL import Image

from apps.streamlit_live import build_aoi_overlay


class StreamlitLiveSurfaceTest(unittest.TestCase):
    def test_live_app_uses_cached_runtime_and_existing_media_callbacks(self) -> None:
        source = Path("apps/streamlit_live.py").read_text(encoding="utf-8")

        self.assertIn("@st.cache_resource", source)
        self.assertIn("webrtc_streamer(", source)
        self.assertIn("video_frame_callback=runtime.media_source.video_frame_callback", source)
        self.assertIn("audio_frame_callback=runtime.media_source.audio_frame_callback", source)
        self.assertIn("async_processing=False", source)

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


if __name__ == "__main__":
    unittest.main()
