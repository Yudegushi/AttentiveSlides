"""Tests for realtime speaker authorization state."""

from __future__ import annotations

import unittest

from modules.system.realtime_voice_runtime import (
    RealtimeVoiceRuntime,
)


class TestRealtimeVoiceSpeaker(
    unittest.IsolatedAsyncioTestCase
):
    async def asyncSetUp(
        self,
    ) -> None:
        self.json_events: list[
            dict
        ] = []

        self.audio_events: list[
            bytes
        ] = []

        async def emit_json(
            payload: dict,
        ) -> None:
            self.json_events.append(
                payload
            )

        async def emit_audio(
            payload: bytes,
        ) -> None:
            self.audio_events.append(
                payload
            )

        self.runtime = (
            RealtimeVoiceRuntime(
                emit_json=emit_json,
                emit_audio=emit_audio,
            )
        )

    async def test_speaker_is_off_by_default(
        self,
    ) -> None:
        self.assertFalse(
            self.runtime.snapshot()[
                "speaker_enabled"
            ]
        )

    async def test_speaker_can_be_enabled(
        self,
    ) -> None:
        await (
            self.runtime
            .set_speaker_enabled(
                enabled=True
            )
        )

        self.assertTrue(
            self.runtime.snapshot()[
                "speaker_enabled"
            ]
        )

    async def test_disabling_speaker_clears_playback(
        self,
    ) -> None:
        await (
            self.runtime
            .set_speaker_enabled(
                enabled=True
            )
        )

        await (
            self.runtime
            .set_speaker_enabled(
                enabled=False
            )
        )

        self.assertFalse(
            self.runtime.snapshot()[
                "speaker_enabled"
            ]
        )

        self.assertIn(
            {
                "type": "playback.clear"
            },
            self.json_events,
        )

    async def test_microphone_off_disables_speaker(
        self,
    ) -> None:
        await (
            self.runtime
            .set_speaker_enabled(
                enabled=True
            )
        )

        await self.runtime.set_microphone(
            enabled=False,
            permission="unknown",
            session_id="",
        )

        self.assertFalse(
            self.runtime.snapshot()[
                "speaker_enabled"
            ]
        )


if __name__ == "__main__":
    unittest.main()
