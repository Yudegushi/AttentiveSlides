import queue
import unittest

import numpy as np

from modules.media import AudioPacket, BoundedMediaQueue, VideoPacket


class MediaQueuePolicyTest(unittest.TestCase):
    def test_full_queue_drops_oldest_and_keeps_recent_items_in_order(self):
        media_queue = BoundedMediaQueue(max_items=2)

        media_queue.push("old")
        media_queue.push("middle")
        media_queue.push("new")

        self.assertEqual(media_queue.dropped_count, 1)
        self.assertEqual(media_queue.get_nowait(), "middle")
        self.assertEqual(media_queue.get_nowait(), "new")
        with self.assertRaises(queue.Empty):
            media_queue.get_nowait()

    def test_byte_limit_is_bounded_and_overruns_are_visible(self):
        media_queue = BoundedMediaQueue(
            max_items=10,
            max_bytes=8,
            item_size=lambda item: item.nbytes,
        )

        media_queue.push(np.zeros(4, dtype=np.uint8))
        media_queue.push(np.ones(6, dtype=np.uint8))

        self.assertEqual(media_queue.qsize(), 1)
        self.assertEqual(media_queue.current_bytes, 6)
        self.assertEqual(media_queue.dropped_count, 1)
        self.assertEqual(media_queue.overrun_count, 1)

    def test_item_larger_than_byte_limit_is_dropped_without_blocking(self):
        media_queue = BoundedMediaQueue(
            max_items=10,
            max_bytes=4,
            item_size=lambda item: item.nbytes,
        )

        accepted = media_queue.push(np.zeros(5, dtype=np.uint8))

        self.assertFalse(accepted)
        self.assertTrue(media_queue.empty())
        self.assertEqual(media_queue.dropped_count, 1)
        self.assertEqual(media_queue.overrun_count, 1)

    def test_push_tracks_accepted_count_and_last_packet_timestamp(self):
        class TimestampedItem:
            def __init__(self, timestamp):
                self.timestamp = timestamp

        media_queue = BoundedMediaQueue(max_items=2)

        self.assertTrue(media_queue.push(TimestampedItem(1.25)))
        self.assertTrue(media_queue.push(TimestampedItem(2.5)))

        self.assertEqual(media_queue.accepted_count, 2)
        self.assertEqual(media_queue.last_timestamp, 2.5)

    def test_rejected_push_does_not_advance_acceptance_metrics(self):
        class TimestampedBytes:
            def __init__(self, timestamp, size):
                self.timestamp = timestamp
                self.nbytes = size

        media_queue = BoundedMediaQueue(
            max_items=2,
            max_bytes=4,
            item_size=lambda item: item.nbytes,
        )

        self.assertTrue(media_queue.push(TimestampedBytes(1.0, 4)))
        self.assertFalse(media_queue.push(TimestampedBytes(2.0, 5)))

        self.assertEqual(media_queue.accepted_count, 1)
        self.assertEqual(media_queue.last_timestamp, 1.0)

    def test_packet_contracts_are_frozen(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        samples = np.zeros((4, 1), dtype=np.int16)
        video = VideoPacket(frame=frame, timestamp=1.0)
        audio = AudioPacket(
            samples=samples,
            timestamp=2.0,
            sample_rate=16_000,
            channels=1,
        )

        with self.assertRaises(AttributeError):
            video.timestamp = 3.0
        with self.assertRaises(AttributeError):
            audio.sample_rate = 8_000

    def test_clear_releases_items_and_resets_current_bytes(self):
        media_queue = BoundedMediaQueue(
            max_items=2,
            max_bytes=16,
            item_size=lambda item: item.nbytes,
        )
        media_queue.push(np.zeros(8, dtype=np.uint8))

        media_queue.clear()
        self.assertTrue(media_queue.empty())
        self.assertEqual(media_queue.current_bytes, 0)
        media_queue.clear(reset_counters=True)
        self.assertEqual(media_queue.accepted_count, 0)
        self.assertIsNone(media_queue.last_timestamp)
