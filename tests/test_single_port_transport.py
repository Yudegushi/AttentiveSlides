from io import BytesIO
from pathlib import Path
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


def fatigue_jpeg_payload(size=(224, 224)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(output, format="JPEG")
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
            max_fatigue_bytes=4096,
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

    def test_exact_face_crop_reaches_one_item_fatigue_queue(self):
        self.ingress.start("session-a")

        self.ingress.accept_fatigue_jpeg(
            "session-a", fatigue_jpeg_payload(), timestamp=1.75
        )

        packet = self.source.face_crop_queue.get_nowait()
        self.assertEqual(packet.image.shape, (224, 224, 3))
        self.assertEqual(packet.timestamp, 1.75)
        self.assertEqual(packet.timestamp_clock, "browser_performance_seconds")

    def test_fatigue_enforces_active_session_dimensions_and_byte_limit(self):
        self.ingress.start("session-a")

        with self.assertRaises(InactiveMediaSession):
            self.ingress.accept_fatigue_jpeg(
                "session-old", fatigue_jpeg_payload(), timestamp=1.0
            )
        with self.assertRaises(ValueError):
            self.ingress.accept_fatigue_jpeg(
                "session-a", fatigue_jpeg_payload((223, 224)), timestamp=1.0
            )
        with self.assertRaises(MediaPayloadTooLarge):
            self.ingress.accept_fatigue_jpeg(
                "session-a", bytes(4097), timestamp=1.0
            )

        self.assertTrue(self.source.face_crop_queue.empty())

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
            "/attentive-media/fatigue",
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

    def test_stats_include_fatigue_freshness_depth_and_drops(self):
        self.ingress.start("session-a")
        self.ingress.accept_fatigue_jpeg(
            "session-a", fatigue_jpeg_payload(), timestamp=1.0
        )
        self.ingress.accept_fatigue_jpeg(
            "session-a", fatigue_jpeg_payload(), timestamp=1.5
        )

        stats = self.ingress.stats_payload()

        self.assertTrue(stats["fatigue_fresh"])
        self.assertEqual(stats["face_crop_queue_depth"], 1)
        self.assertEqual(stats["face_crop_drops"], 1)
        self.assertEqual(stats["last_face_crop_timestamp"], 1.5)
        self.assertGreater(stats["face_crop_fps"], 0.0)


class LocalEyeTheiaCaptureContractTest(unittest.TestCase):
    @staticmethod
    def component_source() -> str:
        return Path(
            "modules/media/live_capture_component/index.html"
        ).read_text(encoding="utf-8")

    def test_reuses_one_native_camera_without_changing_cloud_encoding(self):
        component = self.component_source()

        self.assertEqual(
            component.count("navigator.mediaDevices.getUserMedia"),
            1,
        )
        self.assertIn("width: { ideal: 1280 }", component)
        self.assertIn("height: { ideal: 720 }", component)
        self.assertIn("frameRate: { ideal: 30, max: 30 }", component)
        self.assertIn("canvas.width = 320", component)
        self.assertIn('}, "image/jpeg", 0.65)', component)
        self.assertIn("}, 200)", component)
        self.assertIn("let videoInFlight = false", component)
        self.assertIn("let audioInFlight = false", component)

    def test_packs_native_frames_for_loopback_eyetheia(self):
        component = self.component_source()

        self.assertIn(
            "@mediapipe/face_mesh@0.4.1633559619/face_mesh.js",
            component,
        )
        self.assertIn(
            'const EYETHEIA_URL = "ws://127.0.0.1:8001/ws/predict_gaze"',
            component,
        )
        self.assertIn("view.setUint32(0, metadata.length, false)", component)
        self.assertIn("window.top.innerWidth", component)
        self.assertIn("window.top.innerHeight", component)
        self.assertNotIn("window.innerWidth", component)
        self.assertNotIn("window.innerHeight", component)
        self.assertIn("faces[0].length === 478", component)
        self.assertIn("eyeTheiaCanvas.width = preview.videoWidth", component)
        self.assertIn('}, "image/jpeg", 0.9)', component)
        self.assertIn("eyeTheiaSocket.bufferedAmount > 1_000_000", component)

    def test_gaze_upload_is_latest_only_and_local_errors_do_not_stop_capture(self):
        component = self.component_source()

        self.assertIn('fetch("/attentive-media/gaze"', component)
        self.assertIn('headers: headers({ "Content-Type": "application/json" })', component)
        self.assertIn("let latestGaze = null", component)
        self.assertIn("let gazeInFlight = false", component)
        self.assertIn("200 - (performance.now() - lastGazeUploadAt)", component)
        self.assertIn('source: "eyetheia_local"', component)
        self.assertIn('type: "reset_filter"', component)
        self.assertIn('message.type === "screen_ack"', component)
        self.assertIn('message.type === "filter_reset"', component)

        failure_start = component.index("function handleLocalGazeFailure")
        failure_end = component.index(
            "function scheduleEyeTheiaReconnect",
            failure_start,
        )
        self.assertNotIn(
            "stopCapture",
            component[failure_start:failure_end],
        )

    def test_fatigue_crop_reuses_face_mesh_and_has_bounded_relative_upload(self):
        component = self.component_source()

        self.assertEqual(
            component.count("navigator.mediaDevices.getUserMedia"),
            1,
        )
        self.assertEqual(component.count("new window.FaceMesh("), 1)
        self.assertIn("const FATIGUE_INTERVAL_MS = 500", component)
        self.assertIn("fatigueCanvas.width = 224", component)
        self.assertIn("fatigueCanvas.height = 224", component)
        self.assertIn("* 1.25", component)
        self.assertIn('fetch("/attentive-media/fatigue"', component)
        self.assertIn('}, "image/jpeg", 0.80)', component)
        self.assertIn("let fatigueInFlight = false", component)
        self.assertNotIn('fetch("http://127.0.0.1:8501/attentive-media/fatigue', component)

        upload_start = component.index("function uploadFatigueCrop")
        upload_end = component.index("function startFaceMeshPump", upload_start)
        self.assertNotIn("stopCapture", component[upload_start:upload_end])


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
