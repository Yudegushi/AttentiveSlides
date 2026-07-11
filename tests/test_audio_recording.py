import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.audio.recording import record_wav


class AudioRecordingTest(unittest.TestCase):
    def test_record_wav_creates_parent_and_writes_mono_audio(self):
        recorded_calls = []
        write_calls = []

        fake_sounddevice = types.SimpleNamespace(
            rec=lambda frames, samplerate, channels, dtype: recorded_calls.append(
                {
                    "frames": frames,
                    "samplerate": samplerate,
                    "channels": channels,
                    "dtype": dtype,
                }
            )
            or [[0.0]],
            wait=lambda: None,
        )
        fake_soundfile = types.SimpleNamespace(
            write=lambda path, data, samplerate: write_calls.append(
                {"path": path, "data": data, "samplerate": samplerate}
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "sample.wav"
            with patch.dict(
                sys.modules,
                {"sounddevice": fake_sounddevice, "soundfile": fake_soundfile},
            ):
                returned_path = record_wav(str(output_path), duration_sec=1.25, sample_rate=16000)

            self.assertEqual(returned_path, str(output_path))
            self.assertEqual(recorded_calls[0]["frames"], 20000)
            self.assertEqual(recorded_calls[0]["samplerate"], 16000)
            self.assertEqual(recorded_calls[0]["channels"], 1)
            self.assertEqual(recorded_calls[0]["dtype"], "float32")
            self.assertEqual(write_calls[0]["path"], str(output_path))
            self.assertEqual(write_calls[0]["data"], [[0.0]])
            self.assertEqual(write_calls[0]["samplerate"], 16000)
            self.assertTrue(output_path.parent.exists())

    def test_record_wav_missing_dependency_has_clear_error(self):
        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name in {"sounddevice", "soundfile"}:
                raise ModuleNotFoundError(f"No module named {name!r}")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaisesRegex(RuntimeError, "Install optional audio recording dependencies"):
                record_wav("ignored.wav", duration_sec=1)


if __name__ == "__main__":
    unittest.main()
