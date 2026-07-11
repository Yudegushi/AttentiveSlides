import csv
import tempfile
import unittest
from pathlib import Path

from scripts.create_audio_smoke_manifest import create_manifest_rows, write_manifest


class CreateAudioSmokeManifestTest(unittest.TestCase):
    def test_create_manifest_rows_derives_expected_text_and_scenario_from_m4a_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)
            for filename in ["right-figure.m4a", "explain-this.m4a", "ignore.wav"]:
                (audio_dir / filename).write_bytes(b"audio")

            rows = create_manifest_rows(audio_dir)

        self.assertEqual(
            rows,
            [
                {
                    "case_id": "explain_this",
                    "audio_path": f"{audio_dir.as_posix()}/explain-this.m4a",
                    "expected_text": "explain this",
                    "scenario": "explain_deictic",
                },
                {
                    "case_id": "right_figure",
                    "audio_path": f"{audio_dir.as_posix()}/right-figure.m4a",
                    "expected_text": "right figure",
                    "scenario": "explain_explicit_right",
                },
            ],
        )

    def test_write_manifest_creates_parent_directory_and_csv_header(self):
        rows = [
            {
                "case_id": "summarize_this_slide",
                "audio_path": "audio_eval/summarize-this-slide.m4a",
                "expected_text": "summarize this slide",
                "scenario": "summarize_whole_slide",
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "manifest.csv"

            write_manifest(rows, output_path)

            with output_path.open(newline="", encoding="utf-8") as manifest_file:
                self.assertEqual(list(csv.DictReader(manifest_file)), rows)


if __name__ == "__main__":
    unittest.main()
