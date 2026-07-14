"""Static contracts for Stage 3 voice UI."""

from __future__ import annotations

import unittest
from pathlib import Path


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

UI_PATH = Path(
    "modules/system/realtime_voice_ui.py"
)

HTML_PATH = Path(
    "modules/media/"
    "microphone_component/"
    "index.html"
)


class TestRealtimeVoiceUIContract(
    unittest.TestCase
):
    def test_main_ui_has_stage3_surfaces(
        self,
    ) -> None:
        source = APP_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "render_sidebar_device_controls",
            source,
        )

        self.assertIn(
            "render_grounded_tutor_voice",
            source,
        )

        self.assertIn(
            "render_continuous_voice_panel",
            source,
        )

        self.assertIn(
            "render_realtime_voice_xai",
            source,
        )

    def test_old_stage2_panel_is_removed(
        self,
    ) -> None:
        source = APP_PATH.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "render_voice_input_panel",
            source,
        )

    def test_browser_component_has_three_views(
        self,
    ) -> None:
        source = HTML_PATH.read_text(
            encoding="utf-8"
        )

        for token in (
            'view === "ptt"',
            'view === "continuous"',
            "renderDeviceView",
            "pointerdown",
            "getUserMedia",
            "enqueueSpeakerAudio",
        ):
            self.assertIn(
                token,
                source,
            )

    def test_apptest_guard_exists(
        self,
    ) -> None:
        source = UI_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "ATTENTIVE_DISABLE_"
                "REALTIME_VOICE_FOR_APPTEST"
            ),
            source,
        )


    def test_continuous_view_has_speaker_toggle(
        self,
    ) -> None:
        source = HTML_PATH.read_text(
            encoding="utf-8"
        )

        required = (
            'id="speakerButton"',
            "Speaker Off",
            (
                "/voice/device/"
                "speaker"
            ),
            "prepareSpeaker",
            "speakerEnabled",
            "continuous-controls",
        )

        for token in required:
            self.assertIn(
                token,
                source,
            )

        self.assertLess(
            source.index(
                'id="continuousButton"'
            ),
            source.index(
                'id="speakerButton"'
            ),
        )

    def test_apptest_guard_is_contiguous_literal(
        self,
    ) -> None:
        source = UI_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                '"ATTENTIVE_DISABLE_'
                'REALTIME_VOICE_FOR_APPTEST"'
            ),
            source,
        )


if __name__ == "__main__":
    unittest.main()
