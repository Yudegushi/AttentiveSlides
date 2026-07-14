"""Static contract for the Realtime API smoke script."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


SCRIPT_PATH = Path(
    "scripts/"
    "smoke_test_omni_realtime_turn.py"
)


class TestOmniRealtimeSmokeContract(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.source = (
            SCRIPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.tree = ast.parse(
            cls.source,
            filename=str(
                SCRIPT_PATH
            ),
        )

    def test_script_exists(
        self,
    ) -> None:
        self.assertTrue(
            SCRIPT_PATH.is_file()
        )

    def test_script_uses_realtime_client(
        self,
    ) -> None:
        self.assertIn(
            "BailianOmniRealtimeClient",
            self.source,
        )

    def test_manual_mode_commits_and_responds(
        self,
    ) -> None:
        self.assertIn(
            "commit_and_respond",
            self.source,
        )

    def test_audio_rates_are_explicit(
        self,
    ) -> None:
        self.assertIn(
            "INPUT_SAMPLE_RATE = 16_000",
            self.source,
        )

        self.assertIn(
            "OUTPUT_SAMPLE_RATE = 24_000",
            self.source,
        )

    def test_response_events_are_collected(
        self,
    ) -> None:
        string_constants = {
            node.value
            for node in ast.walk(
                self.tree
            )
            if (
                isinstance(
                    node,
                    ast.Constant,
                )
                and isinstance(
                    node.value,
                    str,
                )
            )
        }

        required_events = (
            "session.updated",
            (
                "conversation.item."
                "input_audio_transcription."
                "completed"
            ),
            (
                "response."
                "audio_transcript."
                "done"
            ),
            "response.audio.delta",
            "response.done",
        )

        for event_type in required_events:
            with self.subTest(
                event_type=event_type,
            ):
                self.assertIn(
                    event_type,
                    string_constants,
                )


if __name__ == "__main__":
    unittest.main()
