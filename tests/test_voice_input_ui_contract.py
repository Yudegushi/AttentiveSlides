"""Static contracts for Stage 2 voice input UI."""

from __future__ import annotations

import unittest
from pathlib import Path


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

UI_PATH = Path(
    "modules/system/voice_input_ui.py"
)


class TestVoiceInputUIContract(
    unittest.TestCase
):
    def test_main_ui_renders_voice_panel(
        self,
    ) -> None:
        source = APP_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "render_voice_input_panel",
            source,
        )

        self.assertIn(
            'command_key="main_typed_command"',
            source,
        )

    def test_voice_ui_does_not_call_tutor(
        self,
    ) -> None:
        source = UI_PATH.read_text(
            encoding="utf-8"
        )

        forbidden = (
            "generate_main_tutor_response",
            "GroundedTutorAgent",
            "BailianTTSClient",
            "send_email",
        )

        for token in forbidden:
            self.assertNotIn(
                token,
                source,
            )

    def test_apptest_disable_flag_exists(
        self,
    ) -> None:
        source = UI_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "ATTENTIVE_DISABLE_"
                "MICROPHONE_FOR_APPTEST"
            ),
            source,
        )


if __name__ == "__main__":
    unittest.main()
