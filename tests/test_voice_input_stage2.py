"""Tests for Stage 2 browser microphone input."""

from __future__ import annotations

import numpy as np
import unittest

from modules.audio.voice_turn_detector import (
    VoiceTurnDetector,
    VoiceTurnDetectorConfig,
)
from modules.common.schemas import (
    Transcript,
)
from modules.media.browser_audio_source import (
    BrowserAudioSource,
)
from modules.media.microphone_ingress import (
    MicrophoneIngress,
    MicrophoneIngressError,
)
from modules.system.voice_input_worker import (
    VoiceInputWorker,
)


class ThresholdVad:
    def is_speech(
        self,
        pcm_frame: np.ndarray,
        sample_rate: int,
    ) -> bool:
        del sample_rate

        return bool(
            np.max(
                np.abs(
                    pcm_frame
                    .astype(np.int32)
                )
            )
            >= 100
        )


class TestVoiceInputStage2(
    unittest.TestCase
):
    def test_ingress_accepts_pcm(
        self,
    ) -> None:
        source = (
            BrowserAudioSource()
        )

        ingress = (
            MicrophoneIngress(
                source
            )
        )

        ingress.set_enabled(
            True
        )

        ingress.start(
            "test-session"
        )

        payload = (
            np.full(
                1600,
                500,
                dtype="<i2",
            )
            .tobytes()
        )

        accepted = (
            ingress.accept_pcm(
                "test-session",
                payload,
                timestamp=1.0,
                sample_rate=16_000,
                channels=1,
            )
        )

        self.assertTrue(
            accepted
        )

        packet = (
            source.audio_queue
            .get_nowait()
        )

        self.assertEqual(
            packet.sample_rate,
            16_000,
        )

        self.assertEqual(
            packet.channels,
            1,
        )

    def test_ingress_rejects_wrong_rate(
        self,
    ) -> None:
        source = (
            BrowserAudioSource()
        )

        ingress = (
            MicrophoneIngress(
                source
            )
        )

        ingress.set_enabled(
            True
        )

        ingress.start(
            "test-session"
        )

        with self.assertRaises(
            MicrophoneIngressError
        ):
            ingress.accept_pcm(
                "test-session",
                b"\x00\x00" * 100,
                timestamp=1.0,
                sample_rate=44_100,
                channels=1,
            )

    def test_worker_produces_transcript(
        self,
    ) -> None:
        source = (
            BrowserAudioSource()
        )

        source.start()

        detector = (
            VoiceTurnDetector(
                ThresholdVad(),
                config=(
                    VoiceTurnDetectorConfig(
                        sample_rate=16_000,
                        frame_ms=30,
                        pre_roll_ms=30,
                        speech_start_window_ms=30,
                        speech_end_silence_ms=60,
                        minimum_utterance_ms=30,
                        maximum_utterance_sec=2,
                    )
                ),
            )
        )

        def fake_transcribe(
            audio_path: str,
        ) -> Transcript:
            self.assertTrue(
                audio_path.endswith(
                    ".wav"
                )
            )

            return Transcript(
                text="解释这一部分",
                language="zh",
                confidence=0.9,
            )

        worker = VoiceInputWorker(
            source=source,
            detector=detector,
            transcribe=(
                fake_transcribe
            ),
        )

        speech = np.full(
            int(16_000 * 0.15),
            1200,
            dtype=np.int16,
        )

        silence = np.zeros(
            int(16_000 * 0.12),
            dtype=np.int16,
        )

        samples = np.concatenate(
            (
                speech,
                silence,
            )
        ).reshape(
            -1,
            1,
        )

        source.accept_audio_samples(
            samples,
            timestamp=0.0,
            sample_rate=16_000,
            channels=1,
        )

        results = (
            worker
            .process_available_audio()
        )

        completed = [
            result
            for result in results
            if result.status
            == "completed"
        ]

        self.assertEqual(
            len(completed),
            1,
        )

        self.assertEqual(
            completed[0]
            .transcript
            .text,
            "解释这一部分",
        )

    def test_queue_is_bounded(
        self,
    ) -> None:
        source = BrowserAudioSource(
            queue_size=2
        )

        source.start()

        for index in range(5):
            source.accept_audio_samples(
                np.array(
                    [[index]],
                    dtype=np.int16,
                ),
                timestamp=float(
                    index
                ),
                sample_rate=16_000,
                channels=1,
            )

        stats = source.stats()

        self.assertEqual(
            stats.queue_depth,
            2,
        )

        self.assertEqual(
            stats.dropped_chunks,
            3,
        )


if __name__ == "__main__":
    unittest.main()
