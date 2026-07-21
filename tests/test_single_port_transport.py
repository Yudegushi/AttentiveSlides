from io import BytesIO
from pathlib import Path
from threading import Event, Thread
import unittest
from unittest.mock import MagicMock, patch
import warnings

import numpy as np
from aiohttp import WSMsgType, web
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

    def test_audio_can_update_freshness_without_entering_audio_worker_queue(self):
        self.ingress.start("session-a")
        accepted = self.ingress.accept_audio_pcm(
            "session-a",
            np.array([1, -2, 3, -4], dtype="<i2").tobytes(),
            timestamp=1.0,
            sample_rate=16_000,
            channels=1,
            enqueue=False,
        )
        self.assertTrue(accepted)
        self.assertTrue(self.ingress.session_snapshot().audio_fresh)
        self.assertTrue(self.source.audio_queue.empty())
        with self.assertRaises(ValueError):
            self.ingress.accept_audio_pcm(
                "session-a",
                b"\x00",
                timestamp=1.0,
                sample_rate=16_000,
                channels=1,
                enqueue=False,
            )

    def test_native_browser_sample_rate_is_accepted_and_preserved_in_queue(self):
        self.ingress.start("session-a")
        payload = np.arange(16, dtype="<i2").tobytes()

        self.ingress.accept_audio_pcm(
            "session-a",
            payload,
            timestamp=1.0,
            sample_rate=48_000,
            channels=1,
        )

        packet = self.source.audio_queue.get_nowait()
        self.assertEqual(packet.sample_rate, 48_000)
        self.assertEqual(packet.samples.reshape(-1).tobytes(), payload)

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
        self.assertIn("function floatToS16(input)", page)
        self.assertNotIn("downsampleToS16", page)
        self.assertNotIn("audioInFlight", page)
        self.assertIn("async function drainAudioQueue()", page)
        self.assertIn("const AUDIO_BATCH_MAX_BYTES = 96 * 1024", page)
        self.assertIn(
            '"X-Media-Sample-Rate": String(Math.round(audioContext.sampleRate))',
            page,
        )
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

    def test_study_review_receives_samples_and_marks_gap_on_stop(self):
        review = MagicMock()
        ingress = FallbackMediaIngress(
            self.source,
            observations=self.ingress.observations,
            study_review=review,
            clock=self.clock,
        )
        ingress.accept_geometry_json(geometry_payload())
        ingress.start("session-a")

        sample = ingress.accept_gaze_json("session-a", gaze_payload())
        ingress.stop("session-a")

        review.accept_gaze.assert_called_once_with(sample)
        review.mark_observation_gap.assert_called()
        review.pause.assert_not_called()

    def test_stop_waits_for_study_review_forwarding_under_ingress_lock(self):
        review = MagicMock()
        ingress = FallbackMediaIngress(
            self.source,
            observations=self.ingress.observations,
            study_review=review,
            clock=self.clock,
        )
        ingress.accept_geometry_json(geometry_payload())
        ingress.start("session-a")
        review.reset_mock()

        gaze_entered = Event()
        release_gaze = Event()
        stop_started = Event()
        stop_returned = Event()
        call_order = []
        failures = []
        original_accept = ingress.observations.accept_gaze

        def blocking_accept(payload):
            gaze_entered.set()
            if not release_gaze.wait(timeout=2.0):
                raise AssertionError("timed out waiting to release gaze parsing")
            sample = original_accept(payload)
            call_order.append("gaze parsed")
            return sample

        review.accept_gaze.side_effect = lambda sample: call_order.append("review accepted")
        review.mark_observation_gap.side_effect = (
            lambda: call_order.append("observation gap")
        )

        def accept_gaze():
            try:
                ingress.accept_gaze_json("session-a", gaze_payload())
            except BaseException as exc:
                failures.append(exc)

        def stop_ingress():
            stop_started.set()
            try:
                ingress.stop("session-a")
            except BaseException as exc:
                failures.append(exc)
            finally:
                stop_returned.set()

        with patch.object(
            ingress.observations,
            "accept_gaze",
            side_effect=blocking_accept,
        ):
            gaze_thread = Thread(target=accept_gaze)
            stop_thread = Thread(target=stop_ingress)
            gaze_thread.start()
            self.assertTrue(gaze_entered.wait(timeout=1.0))
            stop_thread.start()
            self.assertTrue(stop_started.wait(timeout=1.0))
            self.assertFalse(stop_returned.wait(timeout=0.05))
            release_gaze.set()
            gaze_thread.join(timeout=2.0)
            stop_thread.join(timeout=2.0)

        self.assertFalse(gaze_thread.is_alive())
        self.assertFalse(stop_thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(
            call_order,
            ["gaze parsed", "review accepted", "observation gap"],
        )

    def test_replacement_readiness_and_disconnect_use_technical_gap_only(self):
        review = MagicMock()
        ingress = FallbackMediaIngress(
            self.source,
            observations=self.ingress.observations,
            study_review=review,
            clock=self.clock,
        )
        ingress.start("session-a")
        review.reset_mock()

        self.assertTrue(ingress.reset_active_readiness(reason="device reset"))
        ingress.start("session-b")
        ingress.stop("session-b", reason="browser disconnected")

        self.assertEqual(review.mark_observation_gap.call_count, 3)
        review.pause.assert_not_called()

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
        self.assertIn("ensureCanvasSize(", component)
        self.assertIn('}, "image/jpeg", 0.65)', component)
        self.assertIn("}, 200)", component)
        self.assertIn("let videoInFlight = false", component)
        self.assertIn("const audioQueue = []", component)
        self.assertIn("const AUDIO_BATCH_MAX_BYTES = 96 * 1024", component)
        self.assertIn("const AUDIO_QUEUE_MAX_BYTES = 192 * 1024", component)
        self.assertIn("async function drainAudioQueue()", component)
        self.assertNotIn("audioInFlight", component)

    def test_audio_processor_keeps_a_live_output_pull_path(self):
        component = self.component_source()

        self.assertIn("processor.connect(silentGain)", component)
        self.assertIn("silentGain.connect(audioContext.destination)", component)
        self.assertIn("silentGain.gain.value = 1", component)
        self.assertNotIn("silentGain.gain.value = 0", component)

    def test_audio_upload_keeps_native_rate_and_does_not_downsample_in_browser(self):
        component = self.component_source()

        self.assertIn("function floatToS16(input)", component)
        self.assertNotIn("downsampleToS16", component)
        self.assertIn(
            '"X-Media-Sample-Rate": String(Math.round(audioContext.sampleRate))',
            component,
        )
        self.assertIn('"X-Media-Audio-First-Sequence"', component)
        self.assertIn('"X-Media-Audio-Last-Sequence"', component)
        self.assertIn('"X-Media-Audio-Block-Count"', component)

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
        self.assertIn("const FACE_MESH_INTERVAL_MS = 100", component)
        self.assertIn("ensureCanvasSize(eyeTheiaCanvas", component)
        self.assertNotIn("eyeTheiaCanvas.width = preview.videoWidth", component)
        self.assertNotIn("FACE_MESH_MAX_WIDTH", component)
        self.assertIn("if (target.width !== nextWidth)", component)
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
        self.assertIn("const FATIGUE_INTERVAL_MS = 250", component)
        self.assertIn("ensureCanvasSize(fatigueCanvas, 224, 224)", component)
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


class FakeVoiceTransport:
    def __init__(self, *, consume=True) -> None:
        self.consume = consume
        self.audio = []
        self.commands = []
        self.suspended = False

    def set_suspended(self, suspended, reason):
        del reason
        self.suspended = bool(suspended)

    def should_consume_audio(self):
        return self.consume

    async def accept_pcm(self, session_id, pcm):
        self.audio.append((session_id, pcm))

    async def handle_http_command(self, command, session_id):
        self.commands.append((command, session_id))
        return {"command": command, "session_id": session_id}

    def snapshot(self):
        return {"state": "ready", "engine": "omni"}

    async def stop(self, reason):
        return None

    async def websocket(self, request):
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        await socket.send_json(
            {
                "type": "audio.config",
                "payload": {"sample_rate": 24000, "channels": 1, "sample_width": 2},
            }
        )
        await socket.send_bytes(b"pcm")
        await socket.close()
        return socket


class VoiceTransportRouteTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = FakeClock()
        self.source = BrowserMediaSource(clock=self.clock)
        self.ingress = FallbackMediaIngress(self.source, clock=self.clock)
        self.voice = FakeVoiceTransport()
        with warnings.catch_warnings():
            warnings.simplefilter("error", web.NotAppKeyWarning)
            app = build_fallback_app(self.ingress, voice_transport=self.voice)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.ingress.start("session-a")

    async def test_selected_voice_route_consumes_pcm_once_without_audio_enqueue(self):
        payload = np.array([1, -2, 3, -4], dtype="<i2").tobytes()
        response = await self.client.post(
            "/attentive-media/audio",
            data=payload,
            headers={
                SESSION_HEADER: "session-a",
                "X-Media-Timestamp": "1.0",
                "X-Media-Sample-Rate": "16000",
                "X-Media-Channels": "1",
            },
        )
        self.assertEqual(response.status, 204)
        self.assertEqual(self.voice.audio, [("session-a", payload)])
        self.assertTrue(self.source.audio_queue.empty())
        self.assertTrue(self.ingress.session_snapshot().audio_fresh)

    async def test_native_48k_voice_audio_is_stream_resampled_before_ptt_runtime(self):
        source = np.arange(4096, dtype="<i2").tobytes()
        response = await self.client.post(
            "/attentive-media/audio",
            data=source,
            headers={
                SESSION_HEADER: "session-a",
                "X-Media-Timestamp": "1.0",
                "X-Media-Sample-Rate": "48000",
                "X-Media-Channels": "1",
                "X-Media-Audio-First-Sequence": "1",
                "X-Media-Audio-Last-Sequence": "1",
                "X-Media-Audio-Block-Count": "1",
            },
        )
        stopped = await self.client.post(
            "/attentive-voice/ptt/stop",
            headers={
                SESSION_HEADER: "session-a",
                "X-Attentive-Audio-Through-Sequence": "1",
            },
        )

        self.assertEqual(response.status, 204)
        self.assertEqual(stopped.status, 200)
        converted = b"".join(pcm for session_id, pcm in self.voice.audio)
        self.assertTrue(all(session_id == "session-a" for session_id, _ in self.voice.audio))
        self.assertEqual(len(converted) // 2, 1365)
        self.assertTrue(self.source.audio_queue.empty())

    async def test_audio_batches_require_contiguous_sequences_and_stop_watermark(self):
        payload = np.arange(8192, dtype="<i2").tobytes()
        accepted = await self.client.post(
            "/attentive-media/audio",
            data=payload,
            headers={
                SESSION_HEADER: "session-a",
                "X-Media-Timestamp": "1.0",
                "X-Media-Sample-Rate": "48000",
                "X-Media-Channels": "1",
                "X-Media-Audio-First-Sequence": "1",
                "X-Media-Audio-Last-Sequence": "2",
                "X-Media-Audio-Block-Count": "2",
            },
        )
        premature_stop = await self.client.post(
            "/attentive-voice/ptt/stop",
            headers={
                SESSION_HEADER: "session-a",
                "X-Attentive-Audio-Through-Sequence": "3",
            },
        )
        gap = await self.client.post(
            "/attentive-media/audio",
            data=np.arange(4096, dtype="<i2").tobytes(),
            headers={
                SESSION_HEADER: "session-a",
                "X-Media-Timestamp": "1.2",
                "X-Media-Sample-Rate": "48000",
                "X-Media-Channels": "1",
                "X-Media-Audio-First-Sequence": "4",
                "X-Media-Audio-Last-Sequence": "4",
                "X-Media-Audio-Block-Count": "1",
            },
        )
        stats = await self.client.get("/attentive-media/stats")

        self.assertEqual(accepted.status, 204)
        self.assertEqual(premature_stop.status, 409)
        self.assertEqual(gap.status, 400)
        payload_stats = await stats.json()
        self.assertEqual(payload_stats["audio_last_sequence"], 2)
        self.assertEqual(payload_stats["audio_sequence_gaps"], 1)

    async def test_commands_state_and_websocket_reject_stale_sessions(self):
        stale = await self.client.post(
            "/attentive-voice/ptt/start",
            headers={SESSION_HEADER: "stale"},
        )
        self.assertEqual(stale.status, 409)

        command = await self.client.post(
            "/attentive-voice/ptt/start",
            headers={SESSION_HEADER: "session-a"},
        )
        state = await self.client.get(
            "/attentive-voice/state",
            headers={SESSION_HEADER: "session-a"},
        )
        self.assertEqual(command.status, 200)
        self.assertEqual((await command.json())["command"], "ptt/start")
        self.assertEqual((await state.json())["state"], "ready")

        socket = await self.client.ws_connect(
            "/attentive-voice/events?session=session-a"
        )
        first = await socket.receive(timeout=2)
        second = await socket.receive(timeout=2)
        self.assertEqual(first.type, WSMsgType.TEXT)
        self.assertEqual(first.json()["payload"]["sample_rate"], 24000)
        self.assertEqual(second.type, WSMsgType.BINARY)
        self.assertEqual(second.data, b"pcm")
