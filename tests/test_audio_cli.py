import json
import subprocess
import sys
import unittest


class AudioCliTest(unittest.TestCase):
    def test_transcribe_audio_file_mock_outputs_transcript_json(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/transcribe_audio_file.py",
                "--audio",
                "data/audio_samples/explain_this.wav",
                "--engine",
                "mock",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)

        self.assertEqual(payload["text"], "解释一下这个")
        self.assertEqual(payload["language"], "en")
        self.assertIsNone(payload["confidence"])
        self.assertEqual(payload["source"], "audio_file")
        self.assertEqual(payload["engine"], "mock")
        self.assertEqual(payload["language"], "en")

    def test_transcribe_audio_file_profile_defaults_to_balanced_and_allows_overrides(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/transcribe_audio_file.py",
                "--audio",
                "data/audio_samples/explain_this.wav",
                "--engine",
                "mock",
                "--profile",
                "accurate",
                "--model",
                "small",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)

        self.assertEqual(payload["engine"], "mock")
        self.assertEqual(payload["model_size"], "small")

    def test_demo_audio_to_tutor_loop_mock_outputs_interaction_json(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/demo_audio_to_tutor_loop.py",
                "--audio",
                "data/audio_samples/right_figure.wav",
                "--engine",
                "mock",
                "--sensing-preset",
                "high_confidence_right_figure",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)

        self.assertEqual(payload["transcript"]["text"], "讲讲右边这个图")
        self.assertEqual(payload["resolved_query"]["intent"], "explain")
        self.assertEqual(payload["resolved_query"]["resolved_aoi_id"], "right_figure")
        self.assertEqual(payload["tutor_response"]["response_mode"], "explain")

    def test_demo_audio_to_tutor_loop_accepts_profile(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/demo_audio_to_tutor_loop.py",
                "--audio",
                "data/audio_samples/right_figure.wav",
                "--engine",
                "mock",
                "--profile",
                "fast",
                "--sensing-preset",
                "high_confidence_right_figure",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)

        self.assertEqual(payload["transcript"]["engine"], "mock")
        self.assertEqual(payload["transcript"]["model_size"], "small")
        self.assertEqual(payload["transcript"]["language"], "en")

    def test_record_audio_file_cli_outputs_recording_metadata(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/record_audio_file.py",
                "--duration",
                "2.5",
                "--sample-rate",
                "8000",
                "--output",
                "data/audio_samples/recorded/test_cli.wav",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)

        self.assertEqual(payload["audio_path"], "data/audio_samples/recorded/test_cli.wav")
        self.assertEqual(payload["duration_sec"], 2.5)
        self.assertEqual(payload["sample_rate"], 8000)


if __name__ == "__main__":
    unittest.main()
