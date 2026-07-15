import unittest

import numpy as np

from modules.media import (
    AudioPacket,
    BrowserMediaSource,
    FaceCropPacket,
    VideoPacket,
)


class FakeVideoFrame:
    time = 12.5

    def __init__(self):
        self.requested_format = None

    def to_ndarray(self, format):
        self.requested_format = format
        return np.zeros((4, 6, 3), dtype=np.uint8)


class FakeAudioLayout:
    name = "stereo"
    channels = ("left", "right")


class FakeAudioFormat:
    is_planar = True


class FakeAudioFrame:
    time = 8.25
    sample_rate = 48_000
    layout = FakeAudioLayout()

    def __init__(self, samples):
        self._samples = samples
        self.format = FakeAudioFormat()

    def to_ndarray(self):
        return self._samples


class BrowserMediaSourceTest(unittest.TestCase):
    def test_callbacks_convert_and_enqueue_immutable_packets(self):
        source = BrowserMediaSource(video_queue_size=2, audio_queue_size=3)
        source.start()
        video_frame = FakeVideoFrame()
        audio_frame = FakeAudioFrame(
            np.array([[1, 2, 3], [4, 5, 6]], dtype=np.int16)
        )

        self.assertIs(source.video_frame_callback(video_frame), video_frame)
        self.assertIs(source.audio_frame_callback(audio_frame), audio_frame)

        video = source.video_queue.get_nowait()
        audio = source.audio_queue.get_nowait()
        self.assertIsInstance(video, VideoPacket)
        self.assertEqual(video.frame.shape, (4, 6, 3))
        self.assertEqual(video.frame.dtype, np.uint8)
        self.assertEqual(video.pixel_format, "bgr24")
        self.assertEqual(video.timestamp, 12.5)
        self.assertFalse(video.frame.flags.writeable)
        self.assertEqual(video_frame.requested_format, "bgr24")
        self.assertIsInstance(audio, AudioPacket)
        self.assertEqual(audio.samples.shape, (3, 2))
        self.assertEqual(audio.samples.dtype, np.int16)
        self.assertEqual(audio.sample_rate, 48_000)
        self.assertEqual(audio.channels, 2)
        self.assertEqual(audio.sample_format, "s16")
        self.assertEqual(audio.layout, "interleaved")
        self.assertEqual(audio.timestamp, 8.25)
        self.assertFalse(audio.samples.flags.writeable)

    def test_face_crop_packet_is_exact_size_immutable_and_latest_only(self):
        source = BrowserMediaSource()
        source.start()
        first = np.zeros((224, 224, 3), dtype=np.uint8)
        second = np.full((224, 224, 3), 7, dtype=np.uint8)

        self.assertTrue(
            source.accept_face_crop(
                first,
                timestamp=1.0,
                timestamp_clock="browser_performance_seconds",
            )
        )
        self.assertTrue(
            source.accept_face_crop(
                second,
                timestamp=1.5,
                timestamp_clock="browser_performance_seconds",
            )
        )

        packet = source.face_crop_queue.get_nowait()
        self.assertIsInstance(packet, FaceCropPacket)
        self.assertEqual(packet.image.shape, (224, 224, 3))
        self.assertFalse(packet.image.flags.writeable)
        self.assertEqual(packet.timestamp, 1.5)
        self.assertEqual(packet.image[0, 0, 0], 7)
        self.assertEqual(source.face_crop_queue.dropped_count, 1)
        with self.assertRaises(ValueError):
            FaceCropPacket(np.zeros((223, 224, 3)), timestamp=0.0)

    def test_planar_audio_layout_wins_when_shape_is_ambiguous(self):
        source = BrowserMediaSource()
        source.start()
        source.audio_frame_callback(
            FakeAudioFrame(np.array([[1, 2], [3, 4]], dtype=np.int16))
        )

        packet = source.audio_queue.get_nowait()

        np.testing.assert_array_equal(
            packet.samples,
            np.array([[1, 3], [2, 4]], dtype=np.int16),
        )

    def test_start_and_stop_are_idempotent_and_stop_clears_queues(self):
        source = BrowserMediaSource()

        source.start()
        source.start()
        self.assertTrue(source.is_running)
        self.assertEqual(source.start_count, 1)
        source.video_frame_callback(FakeVideoFrame())
        source.accept_face_crop(
            np.zeros((224, 224, 3), dtype=np.uint8),
            timestamp=1.0,
            timestamp_clock="browser_performance_seconds",
        )

        source.stop(reason="master switch off")
        source.stop(reason="master switch off")

        self.assertFalse(source.is_running)
        self.assertEqual(source.stop_count, 1)
        self.assertTrue(source.video_queue.empty())
        self.assertTrue(source.audio_queue.empty())
        self.assertTrue(source.face_crop_queue.empty())
        self.assertEqual(source.cleanup_state, "stopped: master switch off")

    def test_callbacks_ignore_media_while_stopped(self):
        source = BrowserMediaSource()

        source.video_frame_callback(FakeVideoFrame())
        source.audio_frame_callback(
            FakeAudioFrame(np.zeros((1, 4), dtype=np.int16))
        )
        source.accept_face_crop(
            np.zeros((224, 224, 3), dtype=np.uint8),
            timestamp=1.0,
            timestamp_clock="browser_performance_seconds",
        )

        self.assertTrue(source.video_queue.empty())
        self.assertTrue(source.audio_queue.empty())
        self.assertTrue(source.face_crop_queue.empty())

    def test_disconnect_cleanup_is_idempotent(self):
        source = BrowserMediaSource()
        source.start()
        source.video_frame_callback(FakeVideoFrame())

        source.handle_disconnect()
        source.handle_disconnect()

        self.assertFalse(source.is_running)
        self.assertEqual(source.stop_count, 1)
        self.assertTrue(source.video_queue.empty())
        self.assertEqual(source.cleanup_state, "stopped: browser disconnected")

    def test_component_error_cleanup_is_idempotent(self):
        source = BrowserMediaSource()
        source.start()
        source.audio_frame_callback(
            FakeAudioFrame(np.zeros((1, 4), dtype=np.int16))
        )
        source.accept_face_crop(
            np.zeros((224, 224, 3), dtype=np.uint8),
            timestamp=2.0,
            timestamp_clock="browser_performance_seconds",
        )
        source.accept_face_crop(
            np.ones((224, 224, 3), dtype=np.uint8),
            timestamp=2.5,
            timestamp_clock="browser_performance_seconds",
        )

        source.handle_component_error("permission denied")
        source.handle_component_error("permission denied")

        self.assertFalse(source.is_running)
        self.assertEqual(source.stop_count, 1)
        self.assertTrue(source.audio_queue.empty())
        self.assertTrue(source.face_crop_queue.empty())
        self.assertEqual(source.cleanup_state, "stopped: component error: permission denied")

    def test_stats_report_rates_timestamps_depths_and_drops(self):
        source = BrowserMediaSource(video_queue_size=1, audio_queue_size=1)
        source.start()
        source.video_frame_callback(FakeVideoFrame())
        source.video_frame_callback(FakeVideoFrame())
        source.audio_frame_callback(
            FakeAudioFrame(np.zeros((1, 4), dtype=np.int16))
        )
        source.audio_frame_callback(
            FakeAudioFrame(np.zeros((1, 4), dtype=np.int16))
        )
        source.accept_face_crop(
            np.zeros((224, 224, 3), dtype=np.uint8),
            timestamp=2.0,
            timestamp_clock="browser_performance_seconds",
        )
        source.accept_face_crop(
            np.ones((224, 224, 3), dtype=np.uint8),
            timestamp=2.5,
            timestamp_clock="browser_performance_seconds",
        )

        stats = source.stats()

        self.assertEqual(stats.video_queue_depth, 1)
        self.assertEqual(stats.audio_queue_depth, 1)
        self.assertEqual(stats.face_crop_queue_depth, 1)
        self.assertEqual(stats.video_drops, 1)
        self.assertEqual(stats.audio_drops, 1)
        self.assertEqual(stats.face_crop_drops, 1)
        self.assertEqual(stats.last_video_timestamp, 12.5)
        self.assertEqual(stats.last_audio_timestamp, 8.25)
        self.assertEqual(stats.last_face_crop_timestamp, 2.5)
        self.assertGreater(stats.video_fps, 0.0)
        self.assertGreater(stats.audio_chunks_per_second, 0.0)
        self.assertGreater(stats.face_crop_fps, 0.0)
