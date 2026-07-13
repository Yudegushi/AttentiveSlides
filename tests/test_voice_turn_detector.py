import unittest

import numpy as np

from modules.audio.voice_turn_detector import VoiceTurnDetector, VoiceTurnDetectorConfig


FRAME_SAMPLES = 480


class AmplitudeVad:
    def is_speech(self, pcm_frame, sample_rate):
        self.last_rate = sample_rate
        return bool(np.max(np.abs(pcm_frame)) >= 100)


def pcm_for_levels(levels):
    return np.concatenate(
        [np.full(FRAME_SAMPLES, level, dtype=np.int16) for level in levels]
    )


def detector_config(**overrides):
    fields = {
        "sample_rate": 16_000,
        "frame_ms": 30,
        "pre_roll_ms": 120,
        "speech_start_window_ms": 60,
        "speech_end_silence_ms": 90,
        "minimum_utterance_ms": 60,
        "maximum_utterance_sec": 2.0,
    }
    fields.update(overrides)
    return VoiceTurnDetectorConfig(**fields)


class VoiceTurnDetectorTest(unittest.TestCase):
    def make_detector(self, **config_overrides):
        self.vad = AmplitudeVad()
        return VoiceTurnDetector(self.vad, config=detector_config(**config_overrides))

    def test_defaults_match_live_contract(self):
        config = VoiceTurnDetectorConfig()

        self.assertEqual(config.sample_rate, 16_000)
        self.assertEqual(config.frame_ms, 30)
        self.assertEqual(config.pre_roll_ms, 300)
        self.assertEqual(config.speech_start_window_ms, 150)
        self.assertEqual(config.speech_end_silence_ms, 800)
        self.assertEqual(config.minimum_utterance_ms, 300)
        self.assertEqual(config.maximum_utterance_sec, 20)

    def test_silence_does_not_create_a_turn(self):
        detector = self.make_detector()

        turns = detector.feed(pcm_for_levels([0, 0, 0, 0]), start_at=5.0)

        self.assertEqual(turns, [])
        self.assertFalse(detector.has_active_turn)
        self.assertEqual(detector.dropped_utterance_count, 0)

    def test_single_turn_includes_pre_roll_and_excludes_trailing_silence_from_end(self):
        detector = self.make_detector()

        turns = detector.feed(
            pcm_for_levels([0, 0, 1_000, 1_000, 0, 0, 0]),
            start_at=0.0,
        )

        self.assertEqual(len(turns), 1)
        turn = turns[0]
        self.assertAlmostEqual(turn.started_at, 0.06)
        self.assertAlmostEqual(turn.ended_at, 0.12)
        self.assertEqual(turn.finalization_reason, "silence")
        self.assertEqual(turn.samples.size, 7 * FRAME_SAMPLES)
        self.assertTrue(np.all(turn.samples[: 2 * FRAME_SAMPLES] == 0))
        self.assertEqual(self.vad.last_rate, 16_000)

    def test_detects_two_turns_from_one_continuous_pcm_stream(self):
        detector = self.make_detector()

        turns = detector.feed(
            pcm_for_levels([1_000, 1_000, 0, 0, 0, 0, 1_000, 1_000, 0, 0, 0]),
            start_at=0.0,
        )

        self.assertEqual(len(turns), 2)
        self.assertLess(turns[0].ended_at, turns[1].started_at)

    def test_drops_short_noise_after_a_valid_start_window(self):
        detector = self.make_detector(minimum_utterance_ms=90)

        turns = detector.feed(
            pcm_for_levels([1_000, 1_000, 0, 0, 0]),
            start_at=0.0,
        )

        self.assertEqual(turns, [])
        self.assertEqual(detector.dropped_utterance_count, 1)

    def test_accepts_pcm_chunks_that_split_a_vad_frame(self):
        detector = self.make_detector()
        pcm = pcm_for_levels([1_000, 1_000, 0, 0, 0])

        first = detector.feed(pcm[:720], start_at=1.0)
        second = detector.feed(pcm[720:], start_at=1.045)

        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        self.assertAlmostEqual(second[0].started_at, 1.0)

    def test_maximum_duration_forces_finalization(self):
        detector = self.make_detector(
            speech_start_window_ms=30,
            minimum_utterance_ms=30,
            maximum_utterance_sec=0.09,
        )

        turns = detector.feed(pcm_for_levels([1_000, 1_000, 1_000, 1_000]), start_at=2.0)

        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].finalization_reason, "maximum_duration")
        self.assertAlmostEqual(turns[0].ended_at, 2.09)

    def test_cancel_immediately_releases_active_audio(self):
        detector = self.make_detector()
        detector.feed(pcm_for_levels([1_000, 1_000]), start_at=0.0)

        detector.cancel()

        self.assertFalse(detector.has_active_turn)
        self.assertEqual(detector.feed(pcm_for_levels([0, 0, 0]), start_at=0.06), [])

    def test_audio_overrun_marks_the_current_turn_degraded(self):
        detector = self.make_detector()
        detector.feed(pcm_for_levels([1_000, 1_000]), start_at=0.0)
        detector.mark_degraded("audio_overrun")

        turns = detector.feed(pcm_for_levels([0, 0, 0]), start_at=0.06)

        self.assertEqual(len(turns), 1)
        self.assertTrue(turns[0].is_degraded)
        self.assertEqual(turns[0].degradation_reason, "audio_overrun")


if __name__ == "__main__":
    unittest.main()
