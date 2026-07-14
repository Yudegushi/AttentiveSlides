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
    SESSION_HEADER,
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


def geometry_payload():
    return {
        "deck_id": "deck-a",
        "slide_id": 2,
        "layout_revision": 7,
        "browser_timestamp_ms": 1000.0,
        "viewport_width": 1440,
        "viewport_height": 900,
        "device_pixel_ratio": 2,
        "slide_rect": {"x1": 100, "y1": 20, "x2": 1100, "y2": 780},
        "aoi_rects": {},
    }


def gaze_payload():
    return {
        "sequence": 3,
        "browser_timestamp_ms": 1200.0,
        "x_css": 320.0,
        "y_css": 240.0,
        "viewport_width": 1440,
        "viewport_height": 900,
        "valid": True,
        "face_detected": True,
        "source": "eyetheia_local",
    }


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

        expected_capture_paths = {
            "/attentive-media/start",
            "/attentive-media/video",
            "/attentive-media/audio",
            "/attentive-media/geometry",
            "/attentive-media/gaze",
            "/attentive-media/heartbeat",
            "/attentive-media/stop",
            "/attentive-media/stats",
        }
        self.assertTrue(expected_capture_paths.issubset(paths))
        self.assertNotIn("/media/video", paths)

    def test_page_captures_media_and_uses_relative_single_origin_requests(self):
        page = fallback_page_html()

        self.assertIn("getUserMedia({ video: true, audio: true })", page)
        self.assertIn('fetch("/attentive-media/video"', page)
        self.assertIn('fetch("/attentive-media/audio"', page)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)

    def test_stop_clears_gaze_but_preserves_geometry_and_media_cleanup(self):
        self.ingress.accept_geometry_json(geometry_payload())
        self.ingress.start("session-a")
        self.ingress.accept_gaze_json("session-a", gaze_payload())
        self.ingress.accept_video_jpeg(
            "session-a", jpeg_payload(), timestamp=1.0
        )

        self.ingress.stop("session-a")

        self.assertEqual(self.ingress.observations.stats().gaze_samples, 0)
        self.assertIsNotNone(
            self.ingress.observations.latest_geometry_for("deck-a", 2)
        )
        self.assertFalse(self.source.is_running)
        self.assertTrue(self.source.video_queue.empty())

    def test_stats_include_browser_observation_fields(self):
        self.ingress.accept_geometry_json(geometry_payload())
        self.ingress.start("session-a")
        self.ingress.accept_gaze_json("session-a", gaze_payload())

        stats = self.ingress.stats_payload()

        self.assertTrue(stats["gaze_fresh"])
        self.assertEqual(stats["gaze_samples"], 1)
        self.assertEqual(stats["gaze_rejections"], 0)
        self.assertEqual(stats["geometry_slide_id"], 2)
        self.assertEqual(stats["geometry_layout_revision"], 7)


class BrowserObservationRouteTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = FakeClock()
        self.source = BrowserMediaSource(clock=self.clock)
        self.ingress = FallbackMediaIngress(self.source, clock=self.clock)
        self.client = TestClient(TestServer(build_fallback_app(self.ingress)))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def test_geometry_succeeds_before_media_activation(self):
        response = await self.client.post(
            "/attentive-media/geometry",
            json=geometry_payload(),
        )

        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["geometry_slide_id"], 2)

    async def test_gaze_requires_the_active_media_session(self):
        self.ingress.start("session-a")

        valid = await self.client.post(
            "/attentive-media/gaze",
            json=gaze_payload(),
            headers={SESSION_HEADER: "session-a"},
        )
        stale = await self.client.post(
            "/attentive-media/gaze",
            json=gaze_payload(),
            headers={SESSION_HEADER: "session-old"},
        )

        self.assertEqual(valid.status, 200)
        self.assertEqual(stale.status, 409)

    async def test_invalid_observation_fields_return_400(self):
        invalid_geometry = await self.client.post(
            "/attentive-media/geometry",
            json={"deck_id": "deck-a"},
        )
        self.ingress.start("session-a")
        invalid_gaze = gaze_payload()
        invalid_gaze["source"] = "cloud"
        gaze_response = await self.client.post(
            "/attentive-media/gaze",
            json=invalid_gaze,
            headers={SESSION_HEADER: "session-a"},
        )

        self.assertEqual(invalid_geometry.status, 400)
        self.assertEqual(gaze_response.status, 400)


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
