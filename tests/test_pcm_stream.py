from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

import numpy as np

from modules.audio.pcm_stream import Pcm16StreamResampler, PcmWaveDebugRecorder


class Pcm16StreamResamplerTests(unittest.TestCase):
    def test_streaming_resample_preserves_duration_and_filters_aliases(self):
        source_rate = 48_000
        time = np.arange(source_rate, dtype=np.float64) / source_rate
        source = np.rint(
            12_000 * np.sin(2 * np.pi * 1_000 * time)
            + 12_000 * np.sin(2 * np.pi * 10_000 * time)
        ).astype("<i2")
        resampler = Pcm16StreamResampler()
        output = []
        for start in range(0, source.size, 4096):
            output.append(
                resampler.convert(
                    source[start : start + 4096].tobytes(),
                    source_rate=source_rate,
                )
            )
        output.append(resampler.flush())
        converted = np.frombuffer(b"".join(output), dtype="<i2")

        self.assertEqual(converted.size, 16_000)
        spectrum = np.abs(np.fft.rfft(converted.astype(np.float64)))
        self.assertGreater(spectrum[1_000], spectrum[6_000] * 20)

    def test_native_16k_pcm_is_unchanged(self):
        pcm = np.array([1, -2, 3, -4], dtype="<i2").tobytes()
        resampler = Pcm16StreamResampler()

        self.assertEqual(resampler.convert(pcm, source_rate=16_000), pcm)
        self.assertEqual(resampler.flush(), b"")


class PcmWaveDebugRecorderTests(unittest.TestCase):
    def test_writes_safe_wav_files_for_raw_and_normalized_streams(self):
        with TemporaryDirectory() as directory:
            recorder = PcmWaveDebugRecorder(Path(directory))
            recorder.write(
                "../../browser-session",
                "browser_raw",
                np.arange(48, dtype="<i2").tobytes(),
                sample_rate=48_000,
            )
            recorder.write(
                "../../browser-session",
                "voice_16k",
                np.arange(16, dtype="<i2").tobytes(),
                sample_rate=16_000,
            )
            paths = recorder.paths()
            recorder.close()

            self.assertEqual(len(paths), 2)
            self.assertTrue(all(path.parent == Path(directory) for path in paths))
            rates = set()
            frame_counts = set()
            for path in paths:
                with wave.open(str(path), "rb") as audio:
                    rates.add(audio.getframerate())
                    frame_counts.add(audio.getnframes())
            self.assertEqual(rates, {16_000, 48_000})
            self.assertEqual(frame_counts, {16, 48})


if __name__ == "__main__":
    unittest.main()
