import unittest

import numpy as np

from modules.audio.audio_ring_buffer import AudioRingBuffer


class AudioRingBufferTest(unittest.TestCase):
    def test_keeps_only_the_most_recent_bounded_pcm_samples(self):
        buffer = AudioRingBuffer(max_samples=5)

        buffer.append(np.array([1, 2, 3], dtype=np.int16))
        buffer.append(np.array([4, 5, 6], dtype=np.int16))

        self.assertEqual(buffer.sample_count, 5)
        np.testing.assert_array_equal(
            buffer.samples(),
            np.array([2, 3, 4, 5, 6], dtype=np.int16),
        )

    def test_clear_releases_sensitive_samples(self):
        buffer = AudioRingBuffer(max_samples=4)
        buffer.append(np.array([1, 2], dtype=np.int16))

        buffer.clear()

        self.assertEqual(buffer.sample_count, 0)
        self.assertEqual(buffer.samples().size, 0)

    def test_rejects_invalid_capacity_and_normalizes_input_shape(self):
        with self.assertRaisesRegex(ValueError, "max_samples"):
            AudioRingBuffer(max_samples=0)

        buffer = AudioRingBuffer(max_samples=4)
        buffer.append(np.array([[1], [2]], dtype=np.int16))
        np.testing.assert_array_equal(buffer.samples(), np.array([1, 2], dtype=np.int16))


if __name__ == "__main__":
    unittest.main()
