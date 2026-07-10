import builtins
import unittest
from unittest import mock

from scripts.prepare_audio_eval_samples import build_manifest, prepare_minds14_zh_cn_samples


class PrepareAudioEvalSamplesTest(unittest.TestCase):
    def test_build_manifest_uses_relative_paths_and_expected_metadata(self):
        rows = [
            {
                "case_id": "minds14_zh_cn_0000",
                "audio_path": "data/audio_eval/minds14_zh_cn/minds14_zh_cn_0000.wav",
                "expected_transcript": "你好 我想查询账户余额",
            }
        ]

        manifest = build_manifest(rows)

        self.assertEqual(manifest["dataset"], "PolyAI/minds14")
        self.assertEqual(manifest["language"], "zh-CN")
        self.assertEqual(manifest["license"], "cc-by-4.0")
        self.assertEqual(manifest["cases"][0]["case_id"], "minds14_zh_cn_0000")
        self.assertEqual(manifest["cases"][0]["expected_intent"], "unknown")
        self.assertEqual(manifest["cases"][0]["sensing_preset"], "high_confidence_right_figure")

    def test_prepare_samples_missing_optional_dependency_has_clear_error(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in {"datasets", "soundfile"}:
                raise ModuleNotFoundError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaisesRegex(RuntimeError, "Install optional audio evaluation dependencies"):
                prepare_minds14_zh_cn_samples(limit=1)


if __name__ == "__main__":
    unittest.main()
