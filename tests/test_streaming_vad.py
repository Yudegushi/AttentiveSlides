import unittest
from pathlib import Path

import numpy as np

from modules.audio.streaming_vad import EnergyVadBackend, VadBackend, default_vad_backend


class StreamingVadTest(unittest.TestCase):
    def test_audio_requirements_install_the_preferred_pcm_vad_backend(self):
        requirements = Path("requirements-audio.txt").read_text(encoding="utf-8")

        self.assertIn("webrtcvad-wheels==2.0.14", requirements.splitlines())

    def test_energy_backend_classifies_deterministic_pcm_without_external_model(self):
        backend = EnergyVadBackend(speech_threshold=100)

        self.assertFalse(backend.is_speech(np.zeros(480, dtype=np.int16), 16_000))
        self.assertTrue(backend.is_speech(np.full(480, 500, dtype=np.int16), 16_000))

    def test_default_backend_satisfies_the_injectable_protocol(self):
        backend = default_vad_backend()

        self.assertIsInstance(backend, VadBackend)


if __name__ == "__main__":
    unittest.main()
