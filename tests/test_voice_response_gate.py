"""Tests for invalid and meaningful voice input."""

from __future__ import annotations

import unittest

from modules.system.voice_response_gate import (
    evaluate_voice_turn,
)


class TestVoiceResponseGate(
    unittest.TestCase
):
    def decision(
        self,
        text: str,
        *,
        duration: int = 900,
        rms: float = 800.0,
    ):
        return evaluate_voice_turn(
            transcript=text,
            voiced_duration_ms=(
                duration
            ),
            audio_rms=rms,
        )

    def test_empty_is_rejected(
        self,
    ) -> None:
        self.assertFalse(
            self.decision(
                ""
            ).accepted
        )

    def test_filler_is_rejected(
        self,
    ) -> None:
        self.assertEqual(
            self.decision(
                "嗯"
            ).reason,
            "filler_only",
        )

    def test_short_audio_is_rejected(
        self,
    ) -> None:
        self.assertEqual(
            self.decision(
                "解释这一页",
                duration=100,
            ).reason,
            "utterance_too_short",
        )

    def test_low_energy_is_rejected(
        self,
    ) -> None:
        self.assertEqual(
            self.decision(
                "解释这一页",
                rms=20,
            ).reason,
            "audio_energy_too_low",
        )

    def test_noise_marker_is_rejected(
        self,
    ) -> None:
        self.assertEqual(
            self.decision(
                "[noise]"
            ).reason,
            "noise_transcript",
        )

    def test_chinese_question_is_accepted(
        self,
    ) -> None:
        self.assertTrue(
            self.decision(
                "请解释 fixation"
            ).accepted
        )

    def test_english_question_is_accepted(
        self,
    ) -> None:
        self.assertTrue(
            self.decision(
                "Explain visual attention"
            ).accepted
        )


if __name__ == "__main__":
    unittest.main()
