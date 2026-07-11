import json
import subprocess
import sys
import unittest
from pathlib import Path

from evaluation.eval_audio_pipeline import character_error_rate, evaluate_manifest, load_audio_eval_manifest


FIXTURE_MANIFEST = Path("tests/fixtures/audio_eval_manifest.json")


class AudioEvalPipelineTest(unittest.TestCase):
    def test_character_error_rate_handles_exact_match_insertions_and_empty_reference(self):
        self.assertEqual(character_error_rate("解释一下这个", "解释一下这个"), 0.0)
        self.assertEqual(character_error_rate("解释这个", "解释一下这个"), 0.5)
        self.assertEqual(character_error_rate("", "anything"), 1.0)
        self.assertEqual(character_error_rate("", ""), 0.0)

    def test_load_audio_eval_manifest_parses_cases(self):
        manifest = load_audio_eval_manifest(FIXTURE_MANIFEST)

        self.assertEqual(manifest["dataset"], "local_mock")
        self.assertEqual(len(manifest["cases"]), 2)
        self.assertEqual(manifest["cases"][0]["case_id"], "mock_explain")

    def test_evaluate_manifest_with_mock_engine_summarizes_pipeline_results(self):
        summary = evaluate_manifest(
            manifest_path=FIXTURE_MANIFEST,
            engine="mock",
            model_size="small",
            device="auto",
            compute_type="auto",
            language="zh",
        )

        self.assertEqual(summary["dataset"], "local_mock")
        self.assertEqual(summary["engine"], "mock")
        self.assertEqual(summary["case_count"], 2)
        self.assertEqual(summary["pipeline_success_count"], 2)
        self.assertEqual(summary["transcript_usable_rate"], 1.0)
        self.assertEqual(summary["intent_accuracy"], 1.0)
        self.assertEqual(summary["resolved_aoi_accuracy"], 1.0)
        self.assertEqual(summary["mean_cer"], 0.0)
        self.assertEqual(summary["cases"][0]["actual_transcript"], "解释一下这个")
        self.assertEqual(summary["cases"][0]["intent"], "explain")
        self.assertEqual(summary["cases"][0]["resolved_aoi_id"], "right_figure")
        self.assertGreaterEqual(summary["cases"][0]["latency_ms"], 0)

    def test_eval_audio_pipeline_cli_outputs_json_summary(self):
        completed = subprocess.run(
            [
                sys.executable,
                "evaluation/eval_audio_pipeline.py",
                "--manifest",
                str(FIXTURE_MANIFEST),
                "--engine",
                "mock",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)

        self.assertEqual(payload["dataset"], "local_mock")
        self.assertEqual(payload["case_count"], 2)
        self.assertEqual(payload["pipeline_success_count"], 2)


if __name__ == "__main__":
    unittest.main()
