import unittest

from modules.audio.model_policy import transcription_config_for_profile


class AudioModelPolicyTest(unittest.TestCase):
    def test_balanced_profile_uses_medium_cuda_int8_float16(self):
        config = transcription_config_for_profile("balanced")

        self.assertEqual(config.engine, "faster_whisper")
        self.assertEqual(config.model_size, "medium")
        self.assertEqual(config.device, "cuda")
        self.assertEqual(config.compute_type, "int8_float16")
        self.assertEqual(config.language, "en")
        self.assertEqual(config.beam_size, 1)
        self.assertTrue(config.vad_filter)

    def test_profiles_match_audio_demo_policy(self):
        expected = {
            "fast": ("small", "cuda", "int8_float16", "en"),
            "balanced": ("medium", "cuda", "int8_float16", "en"),
            "accurate": ("large-v3", "cuda", "int8_float16", "en"),
            "cpu": ("small", "cpu", "int8", "en"),
        }

        for profile, fields in expected.items():
            with self.subTest(profile=profile):
                config = transcription_config_for_profile(profile)
                self.assertEqual(
                    (config.model_size, config.device, config.compute_type, config.language),
                    fields,
                )

    def test_unknown_profile_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Unknown audio model profile"):
            transcription_config_for_profile("large")


if __name__ == "__main__":
    unittest.main()
