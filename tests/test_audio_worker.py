from pathlib import Path
import unittest
import wave

import numpy as np

from modules.audio.voice_turn_detector import VoiceTurnDetector, VoiceTurnDetectorConfig
from modules.common.schemas import Transcript
from modules.media import BrowserMediaSource
from modules.system.audio_worker import AudioWorker, AudioWorkerConfig


class AmplitudeVad:
    def is_speech(self, pcm_frame, sample_rate):
        return bool(np.max(np.abs(pcm_frame)) >= 100)


class FakeClock:
    def __init__(self, value=10.0):
        self.value = value

    def __call__(self):
        return self.value


def pcm(levels, *, sample_rate=16_000, channels=1):
    frame_size = sample_rate * 30 // 1_000
    mono = np.concatenate(
        [np.full(frame_size, level, dtype=np.int16) for level in levels]
    )
    if channels == 1:
        return mono.reshape(-1, 1)
    return np.column_stack([mono] * channels)


def make_detector():
    return VoiceTurnDetector(
        AmplitudeVad(),
        config=VoiceTurnDetectorConfig(
            sample_rate=16_000,
            frame_ms=30,
            pre_roll_ms=60,
            speech_start_window_ms=30,
            speech_end_silence_ms=30,
            minimum_utterance_ms=30,
            maximum_utterance_sec=2.0,
        ),
    )


class AudioWorkerTest(unittest.TestCase):
    def setUp(self):
        self.source = BrowserMediaSource(audio_queue_size=4)
        self.source.start()
        self.clock = FakeClock()

    def tearDown(self):
        self.source.stop()

    def test_normalizes_to_mono_16k_transcribes_and_removes_temporary_wav(self):
        observed_paths = []

        def transcribe(path):
            observed_paths.append(Path(path))
            self.assertTrue(Path(path).exists())
            with wave.open(path, "rb") as wav:
                self.assertEqual(wav.getframerate(), 16_000)
                self.assertEqual(wav.getnchannels(), 1)
            return Transcript(text="hello", language="en")

        worker = AudioWorker(
            media_source=self.source,
            detector=make_detector(),
            transcribe=transcribe,
            clock=self.clock,
        )
        source_pcm = pcm([1_000, 0, 0], sample_rate=48_000, channels=2)
        self.source.accept_audio_samples(
            source_pcm,
            timestamp=3.0,
            sample_rate=48_000,
            channels=2,
            timestamp_clock="browser_performance_seconds",
        )

        results = worker.process_available_audio()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "completed")
        self.assertEqual(results[0].transcript, Transcript(text="hello", language="en"))
        self.assertEqual(worker.get_result_nowait(), results[0])
        self.assertFalse(observed_paths[0].exists())
        self.assertAlmostEqual(results[0].turn.started_at, 10.0)

    def test_stt_failure_is_recoverable_result_and_temporary_wav_is_removed(self):
        observed_paths = []

        def failing_transcribe(path):
            observed_paths.append(Path(path))
            raise RuntimeError("synthetic stt failure")

        worker = AudioWorker(
            media_source=self.source,
            detector=make_detector(),
            transcribe=failing_transcribe,
            clock=self.clock,
        )
        self.source.accept_audio_samples(
            pcm([1_000, 0, 0]),
            timestamp=3.0,
            sample_rate=16_000,
            channels=1,
            timestamp_clock="browser_performance_seconds",
        )

        result = worker.process_available_audio()[0]

        self.assertEqual(result.status, "stt_error")
        self.assertIsNone(result.transcript)
        self.assertIn("synthetic stt failure", result.error)
        self.assertFalse(observed_paths[0].exists())

    def test_queue_overrun_invalidates_active_turn_without_transcribing(self):
        self.source.stop()
        self.source = BrowserMediaSource(audio_queue_size=1)
        self.source.start()
        calls = []
        worker = AudioWorker(
            media_source=self.source,
            detector=make_detector(),
            transcribe=lambda path: calls.append(path) or Transcript("unexpected"),
            clock=self.clock,
        )
        self.source.accept_audio_samples(
            pcm([1_000]), timestamp=1.0, sample_rate=16_000, channels=1,
            timestamp_clock="browser_performance_seconds",
        )
        worker.process_available_audio()
        self.source.accept_audio_samples(
            pcm([0]), timestamp=1.03, sample_rate=16_000, channels=1,
            timestamp_clock="browser_performance_seconds",
        )
        self.source.accept_audio_samples(
            pcm([0]), timestamp=1.06, sample_rate=16_000, channels=1,
            timestamp_clock="browser_performance_seconds",
        )

        result = worker.process_available_audio()[0]

        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.error, "audio_overrun")
        self.assertEqual(calls, [])

    def test_start_stop_are_idempotent_and_stop_cancels_sensitive_audio(self):
        worker = AudioWorker(
            media_source=self.source,
            detector=make_detector(),
            transcribe=lambda path: Transcript("unused"),
            clock=self.clock,
            config=AudioWorkerConfig(poll_interval_seconds=0.01),
        )
        self.source.accept_audio_samples(
            pcm([1_000]), timestamp=1.0, sample_rate=16_000, channels=1,
            timestamp_clock="browser_performance_seconds",
        )
        worker.process_available_audio()

        worker.start()
        worker.start()
        worker.stop()
        worker.stop()

        self.assertFalse(worker.is_running)
        self.assertEqual(worker.start_count, 1)
        self.assertEqual(worker.stop_count, 1)
        self.assertFalse(worker.detector.has_active_turn)
        self.assertTrue(self.source.audio_queue.empty())


if __name__ == "__main__":
    unittest.main()
