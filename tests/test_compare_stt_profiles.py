import unittest

from evaluation.compare_stt_profiles import compare_profiles, render_comparison_markdown


def _summary(profile, latency, **metrics):
    base = {
        "profile": profile,
        "case_count": 10,
        "transcript_usable_rate": 1.0,
        "mean_cer": 0.08,
        "mean_transcription_latency_ms": latency - 20,
        "mean_end_to_end_latency_ms": latency,
        "intent_accuracy": 0.96,
        "deictic_detection_accuracy": 0.96,
        "explicit_target_hint_accuracy": 0.96,
        "confirmation_mode_accuracy": 0.96,
        "response_mode_accuracy": 0.96,
    }
    base.update(metrics)
    return base


class CompareSttProfilesTest(unittest.TestCase):
    def test_fast_is_recommended_when_semantics_are_close_and_latency_is_lower(self):
        comparison = compare_profiles(
            [
                _summary("fast", 100, deictic_detection_accuracy=0.94),
                _summary("balanced", 220),
            ]
        )

        self.assertEqual(comparison["recommendation"]["live_profile"], "fast")
        self.assertIn("close", comparison["recommendation"]["reason"])

    def test_balanced_is_recommended_when_fast_misses_a_key_semantic_metric(self):
        comparison = compare_profiles(
            [
                _summary("fast", 100, deictic_detection_accuracy=0.70),
                _summary("balanced", 220),
            ]
        )

        self.assertEqual(comparison["recommendation"]["live_profile"], "balanced")
        markdown = render_comparison_markdown(comparison)
        self.assertIn("Recommended live profile: **balanced**", markdown)
        self.assertIn("Transcript usable rate", markdown)
        self.assertIn("Mean CER", markdown)
        self.assertIn("Deictic detection", markdown)


if __name__ == "__main__":
    unittest.main()
