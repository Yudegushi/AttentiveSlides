import csv
import tempfile
import unittest
from pathlib import Path

from evaluation.eval_audio_usability import evaluate_audio_usability_manifest
from modules.audio.mock_transcriber import MockTranscriber


class AudioUsabilityEvalTest(unittest.TestCase):
    def test_csv_manifest_compares_stt_semantics_and_resolves_remote_audio_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.csv"
            with manifest_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["case_id", "audio_path", "expected_text", "scenario"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "case_id": "explain_this",
                            "audio_path": "audio_eval/explain-this.m4a",
                            "expected_text": "explain this",
                            "scenario": "explain_deictic",
                        },
                        {
                            "case_id": "summarize_slide",
                            "audio_path": "audio_eval/summarize-slide.m4a",
                            "expected_text": "summarize this slide",
                            "scenario": "summarize_whole_slide",
                        },
                    ]
                )

            summary = evaluate_audio_usability_manifest(
                manifest_path=manifest_path,
                engine="mock",
                profile="balanced",
                audio_root="data/audio_eval/user_smoke",
                transcriber=MockTranscriber(
                    transcripts={
                        "explain-this": "explain this",
                        "summarize-slide": "summarize this slide",
                    },
                    language="en",
                ),
            )

        self.assertEqual(summary["case_count"], 2)
        self.assertEqual(summary["language"], "en")
        self.assertEqual(summary["transcript_usable_rate"], 1.0)
        self.assertEqual(summary["mean_cer"], 0.0)
        self.assertEqual(summary["intent_accuracy"], 1.0)
        self.assertEqual(summary["deictic_detection_accuracy"], 1.0)
        self.assertEqual(summary["explicit_target_hint_accuracy"], 1.0)
        self.assertEqual(summary["confirmation_mode_accuracy"], 1.0)
        self.assertEqual(summary["response_mode_accuracy"], 1.0)
        self.assertEqual(
            summary["cases"][0]["audio_path"],
            "data/audio_eval/user_smoke/explain-this.m4a",
        )
        self.assertGreaterEqual(summary["mean_transcription_latency_ms"], 0.0)
        self.assertGreaterEqual(summary["mean_end_to_end_latency_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
