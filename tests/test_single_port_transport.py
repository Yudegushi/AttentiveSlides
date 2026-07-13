from io import BytesIO
import unittest
import warnings

import numpy as np
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from modules.media import BrowserMediaSource
from modules.media.single_port_transport import (
    FallbackMediaIngress,
    InactiveMediaSession,
    MediaPayloadTooLarge,
    build_fallback_app,
    fallback_page_html,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


def jpeg_payload() -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 2), color=(255, 0, 0)).save(output, format="JPEG")
    return output.getvalue()


class SinglePortTransportTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.source = BrowserMediaSource(clock=self.clock)
        self.ingress = FallbackMediaIngress(
            self.source,
            clock=self.clock,
            inactive_after_seconds=2.0,
            max_video_bytes=1024,
            max_audio_bytes=64,
        )

    def test_start_and_same_session_packets_reach_existing_source_contract(self):
        self.ingress.start("session-a")

        self.ingress.accept_video_jpeg(
            "session-a", jpeg_payload(), timestamp=1.25
        )
        self.ingress.accept_audio_pcm(
            "session-a",
            np.array([1, -2, 3, -4], dtype="<i2").tobytes(),
            timestamp=1.5,
            sample_rate=16_000,
            channels=1,
        )

        video = self.source.video_queue.get_nowait()
        audio = self.source.audio_queue.get_nowait()
        self.assertEqual(video.frame.shape, (2, 4, 3))
        self.assertGreater(video.frame[0, 0, 2], 240)
        self.assertEqual(video.frame[0, 0, 0], 0)
        self.assertEqual(video.frame[0, 0, 1], 0)
        self.assertEqual(video.timestamp, 1.25)
        self.assertEqual(video.timestamp_clock, "browser_performance_seconds")
        self.assertEqual(audio.samples.shape, (4, 1))
        self.assertEqual(audio.samples.dtype, np.int16)
        self.assertEqual(audio.sample_rate, 16_000)
        self.assertEqual(audio.channels, 1)
        self.assertEqual(audio.timestamp, 1.5)

    def test_replaced_session_cannot_enqueue_stale_packets(self):
        self.ingress.start("session-a")
        self.ingress.start("session-b")

        with self.assertRaises(InactiveMediaSession):
            self.ingress.accept_video_jpeg(
                "session-a", jpeg_payload(), timestamp=1.0
            )

        self.assertTrue(self.source.video_queue.empty())
        self.assertTrue(self.source.is_running)

    def test_inactive_session_stops_source_and_clears_queues(self):
        self.ingress.start("session-a")
        self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
        self.clock.value = 2.01

        self.assertTrue(self.ingress.stop_if_inactive())
        self.assertFalse(self.source.is_running)
        self.assertTrue(self.source.video_queue.empty())
        self.assertEqual(self.source.cleanup_state, "stopped: browser inactive")

    def test_payload_limits_are_rejected_before_queueing(self):
        self.ingress.start("session-a")

        with self.assertRaises(MediaPayloadTooLarge):
            self.ingress.accept_audio_pcm(
                "session-a",
                bytes(66),
                timestamp=1.0,
                sample_rate=16_000,
                channels=1,
            )

        self.assertTrue(self.source.audio_queue.empty())

    def test_app_exposes_one_origin_media_routes(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", web.NotAppKeyWarning)
            app = build_fallback_app(self.ingress)
        paths = {route.resource.canonical for route in app.router.routes()}

        self.assertTrue(
            {
                "/",
                "/health",
                "/capture",
                "/media/start",
                "/media/video",
                "/media/audio",
                "/media/heartbeat",
                "/media/stop",
                "/media/stats",
            }.issubset(paths)
        )

    def test_page_captures_media_and_uses_relative_single_origin_requests(self):
        page = fallback_page_html()

        self.assertIn("getUserMedia({ video: true, audio: true })", page)
        self.assertIn('fetch("/media/video"', page)
        self.assertIn('fetch("/media/audio"', page)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)


class SinglePortHealthRouteTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_returns_503_for_injected_failure(self):
        payload = {
            "status": "error",
            "coordinator_running": False,
            "coordinator_last_error": "RuntimeError: reconcile exploded",
        }
        app = build_fallback_app(
            health_check=lambda: (False, payload)
        )
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)

        response = await client.get("/health")

        self.assertEqual(response.status, 503)
        self.assertEqual(await response.json(), payload)
