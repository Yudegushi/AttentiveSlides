import asyncio
from io import BytesIO
import unittest

import numpy as np
from PIL import Image

from modules.media import BrowserMediaSource
from modules.media.single_port_transport import FallbackMediaIngress


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class FakeRuntime:
    def __init__(self):
        self.start_count = 0
        self.stop_count = 0
        self.disconnect_count = 0
        self.is_running = False
        self.stop_reasons = []

    def start(self):
        if self.is_running:
            return
        self.start_count += 1
        self.is_running = True

    def stop(self, *, reason="requested"):
        if not self.is_running:
            return
        self.stop_count += 1
        self.stop_reasons.append(reason)
        self.is_running = False

    def handle_disconnect(self):
        if not self.is_running:
            return
        self.disconnect_count += 1
        self.is_running = False


class FakeVoiceTransport:
    def __init__(self):
        self.state = "off"
        self.stop_reasons = []
        self.loop = None
        self.suspended = False
        self.suspension_events = []
        self.stop_error = None

    def set_suspended(self, suspended, reason):
        self.suspended = bool(suspended)
        self.suspension_events.append((bool(suspended), reason))

    def attach_loop(self, loop):
        self.loop = loop

    def snapshot(self):
        return {"state": self.state, "ptt_active": False}

    async def stop(self, reason):
        if self.stop_error is not None:
            raise self.stop_error
        self.stop_reasons.append(reason)
        self.state = "off"

    def should_consume_audio(self):
        return False

    async def accept_pcm(self, session_id, pcm):
        return None

    async def handle_http_command(self, command, session_id):
        return {}

    async def websocket(self, request):
        raise RuntimeError("not used")


def jpeg_payload() -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 2), color=(255, 0, 0)).save(output, format="JPEG")
    return output.getvalue()


def pcm_payload() -> bytes:
    return np.array([1, -2, 3, -4], dtype="<i2").tobytes()


def gaze_payload() -> dict[str, object]:
    return {
        "sequence": 1,
        "browser_timestamp_ms": 1000.0,
        "x_css": 200.0,
        "y_css": 100.0,
        "viewport_width": 1440.0,
        "viewport_height": 900.0,
        "valid": True,
        "face_detected": True,
        "source": "eyetheia_local",
    }


class LiveIngressServiceTest(unittest.TestCase):
    def setUp(self):
        from modules.media.live_ingress_service import LiveIngressService

        self.clock = FakeClock()
        self.source = BrowserMediaSource(clock=self.clock)
        self.ingress = FallbackMediaIngress(
            self.source,
            clock=self.clock,
            start_armed=False,
            coordinated_activation=True,
            media_stale_after_seconds=2.0,
            inactive_after_seconds=3.0,
        )
        self.runtime = FakeRuntime()
        self.service = LiveIngressService(
            runtime=self.runtime,
            source=self.source,
            ingress=self.ingress,
            clock=self.clock,
            port=0,
        )

    def start_ready_session(self, session_id="session-a"):
        self.service.set_master_enabled(True)
        self.ingress.start(session_id)
        self.service.reconcile_once()
        self.ingress.accept_video_jpeg(
            session_id, jpeg_payload(), timestamp=self.clock.value
        )
        self.ingress.accept_audio_pcm(
            session_id,
            pcm_payload(),
            timestamp=self.clock.value,
            sample_rate=16_000,
            channels=1,
        )
        self.service.reconcile_once()

    def test_ingress_and_runtime_share_exactly_one_source(self):
        self.assertIs(self.service.source, self.source)
        self.assertIs(self.service.ingress.source, self.source)

    def test_mismatched_source_is_rejected(self):
        from modules.media.live_ingress_service import LiveIngressService

        with self.assertRaisesRegex(ValueError, "share BrowserMediaSource"):
            LiveIngressService(
                runtime=self.runtime,
                source=BrowserMediaSource(),
                ingress=self.ingress,
            )

    def test_controller_starts_only_after_fresh_video_and_audio(self):
        self.service.set_master_enabled(True)
        self.ingress.start("session-a")
        self.service.reconcile_once()
        self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 0)
        self.ingress.accept_audio_pcm(
            "session-a",
            pcm_payload(),
            timestamp=1.1,
            sample_rate=16_000,
            channels=1,
        )
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 1)

    def test_gaze_does_not_start_runtime_without_video_and_audio(self):
        self.service.set_master_enabled(True)
        self.ingress.start("session-a")
        self.service.reconcile_once()

        self.ingress.accept_gaze_json("session-a", gaze_payload())
        self.service.reconcile_once()

        self.assertEqual(self.runtime.start_count, 0)
        self.assertEqual(self.ingress.observations.stats().gaze_samples, 1)

    def test_audio_only_does_not_start_controller(self):
        self.service.set_master_enabled(True)
        self.ingress.start("session-a")
        self.service.reconcile_once()
        self.ingress.accept_audio_pcm(
            "session-a",
            pcm_payload(),
            timestamp=1.0,
            sample_rate=16_000,
            channels=1,
        )
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 0)

    def test_video_only_does_not_start_controller(self):
        self.service.set_master_enabled(True)
        self.ingress.start("session-a")
        self.service.reconcile_once()
        self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 0)

    def test_master_off_before_controller_start_clears_queues(self):
        self.service.set_master_enabled(True)
        self.ingress.start("session-a")
        self.service.reconcile_once()
        self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
        self.service.set_master_enabled(False)
        self.service.reconcile_once()
        self.assertFalse(self.source.is_running)
        self.assertTrue(self.source.video_queue.empty())
        self.assertTrue(self.source.audio_queue.empty())

    def test_master_off_stops_running_controller_once(self):
        self.start_ready_session()
        self.service.set_master_enabled(False)
        self.service.set_master_enabled(False)
        self.service.reconcile_once()
        self.service.reconcile_once()
        self.assertEqual(self.runtime.stop_count, 1)
        self.assertFalse(self.source.is_running)
        self.assertTrue(self.source.video_queue.empty())
        self.assertTrue(self.source.audio_queue.empty())

    def test_external_source_stop_requires_new_video_and_audio(self):
        original_start = self.runtime.start

        def start_runtime_and_source():
            self.source.start()
            original_start()

        self.runtime.start = start_runtime_and_source
        self.start_ready_session()
        self.source.stop(reason="deck reload")

        self.service.reconcile_once()
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 1)

        self.ingress.accept_video_jpeg(
            "session-a", jpeg_payload(), timestamp=2.0
        )
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 1)

        self.ingress.accept_audio_pcm(
            "session-a",
            pcm_payload(),
            timestamp=2.1,
            sample_rate=16_000,
            channels=1,
        )
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 2)

    def test_timeout_and_disconnect_stop_controller_and_source(self):
        self.start_ready_session()
        self.clock.value += 3.01
        self.assertTrue(self.ingress.stop_if_inactive())
        self.service.reconcile_once()
        self.assertEqual(self.runtime.disconnect_count, 1)
        self.assertFalse(self.source.is_running)

    def test_explicit_page_stop_uses_disconnect_cleanup(self):
        self.start_ready_session("session-a")
        self.ingress.stop("session-a", reason="pagehide")
        self.service.reconcile_once()
        self.assertEqual(self.runtime.disconnect_count, 1)
        self.assertFalse(self.source.is_running)

    def test_new_session_generation_restarts_readiness_gate(self):
        self.start_ready_session("session-a")
        self.assertEqual(self.runtime.start_count, 1)
        self.ingress.start("session-b")
        self.assertFalse(self.source.is_running)
        self.service.reconcile_once()
        self.assertEqual(self.runtime.stop_count, 1)
        self.assertTrue(self.source.is_running)
        self.ingress.accept_video_jpeg("session-b", jpeg_payload(), timestamp=2.0)
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 1)
        self.ingress.accept_audio_pcm(
            "session-b",
            pcm_payload(),
            timestamp=2.1,
            sample_rate=16_000,
            channels=1,
        )
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 2)
        self.assertEqual(self.runtime.stop_count, 1)
        self.assertTrue(self.source.is_running)

    def test_lifetime_packet_history_does_not_count_as_current_freshness(self):
        self.service.set_master_enabled(True)
        self.ingress.start("session-a")
        self.service.reconcile_once()
        self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
        self.clock.value += 2.01
        self.ingress.accept_audio_pcm(
            "session-a",
            pcm_payload(),
            timestamp=1.1,
            sample_rate=16_000,
            channels=1,
        )
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 0)

    def test_stale_track_while_running_uses_disconnect_cleanup(self):
        self.start_ready_session("session-a")
        self.clock.value += 2.01
        self.ingress.accept_audio_pcm(
            "session-a",
            pcm_payload(),
            timestamp=2.0,
            sample_rate=16_000,
            channels=1,
        )
        self.ingress.heartbeat("session-a")
        self.service.reconcile_once()
        self.assertEqual(self.runtime.disconnect_count, 1)
        self.assertFalse(self.source.is_running)

    def test_freshness_uses_server_receive_clock_not_browser_timestamp(self):
        self.service.set_master_enabled(True)
        self.ingress.start("session-a")
        self.service.reconcile_once()
        self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=-999.0)
        self.ingress.accept_audio_pcm(
            "session-a",
            pcm_payload(),
            timestamp=999999.0,
            sample_rate=16_000,
            channels=1,
        )
        snapshot = self.ingress.session_snapshot()
        self.assertTrue(snapshot.video_fresh)
        self.assertTrue(snapshot.audio_fresh)
        self.assertEqual(snapshot.last_video_received_at, self.clock.value)
        self.assertEqual(snapshot.last_audio_received_at, self.clock.value)

    def test_repeated_ensure_started_and_shutdown_do_not_duplicate_thread(self):
        self.service.ensure_started()
        thread = self.service.server_thread
        self.service.ensure_started()
        self.assertIs(self.service.server_thread, thread)
        self.assertTrue(thread.is_alive())
        self.service.shutdown()
        self.service.shutdown()
        self.assertFalse(thread.is_alive())


class LiveIngressCoordinatorHealthTest(unittest.IsolatedAsyncioTestCase):
    def make_service(self):
        from modules.media.live_ingress_service import LiveIngressService

        clock = FakeClock()
        source = BrowserMediaSource(clock=clock)
        ingress = FallbackMediaIngress(
            source,
            clock=clock,
            start_armed=False,
            coordinated_activation=True,
        )
        return LiveIngressService(
            runtime=FakeRuntime(),
            source=source,
            ingress=ingress,
            clock=clock,
            port=0,
        )

    async def test_health_is_available_while_coordinator_is_pending(self):
        service = self.make_service()
        task = asyncio.create_task(asyncio.sleep(60))
        self.addAsyncCleanup(self._cancel_task, task)
        service._coordinator_task = task

        healthy, payload = service.health_status()

        self.assertTrue(healthy)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["coordinator_running"])
        self.assertIsNone(payload["coordinator_last_error"])

    async def test_health_is_unavailable_after_coordinator_failure(self):
        service = self.make_service()

        async def fail():
            raise RuntimeError("reconcile exploded")

        task = asyncio.create_task(fail())
        with self.assertRaisesRegex(RuntimeError, "reconcile exploded"):
            await task

        service._coordinator_task = task
        service._coordinator_last_error = "RuntimeError: reconcile exploded"

        healthy, payload = service.health_status()

        self.assertFalse(healthy)
        self.assertEqual(payload["status"], "error")
        self.assertIn("reconcile exploded", payload["coordinator_last_error"])

    async def _cancel_task(self, task):
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task


class LiveIngressVoiceLifecycleTest(unittest.TestCase):
    def setUp(self):
        from modules.media.live_ingress_service import LiveIngressService

        self.clock = FakeClock()
        self.source = BrowserMediaSource(clock=self.clock)
        self.ingress = FallbackMediaIngress(
            self.source,
            clock=self.clock,
            start_armed=False,
            coordinated_activation=True,
        )
        self.voice = FakeVoiceTransport()
        self.service = LiveIngressService(
            runtime=FakeRuntime(),
            source=self.source,
            ingress=self.ingress,
            voice_transport=self.voice,
            reconcile_interval_seconds=10.0,
            port=0,
        )
        self.service.ensure_started()
        self.addCleanup(self.service.shutdown)

    def test_server_loop_is_attached_and_master_off_stops_voice(self):
        self.assertIs(self.voice.loop, self.service._server_loop)
        self.service.set_master_enabled(True)
        self.voice.state = "ready"
        self.service.set_master_enabled(False)
        self.service.reconcile_once()
        self.assertEqual(self.voice.stop_reasons, ["master switch off"])

    def test_session_replacement_stops_voice_before_pending_activation(self):
        self.service.set_master_enabled(True)
        self.ingress.start("session-a")
        self.service.reconcile_once()
        self.voice.state = "ready"
        self.ingress.start("session-b")
        self.service.reconcile_once()
        self.assertEqual(self.voice.stop_reasons, ["browser session replaced"])
        snapshot = self.ingress.session_snapshot()
        self.assertTrue(snapshot.active)
        self.assertFalse(snapshot.session_pending)

    def test_quiesce_closes_gate_and_stops_runtime_even_when_voice_stop_fails(self):
        self.service.set_master_enabled(True)
        self.service.runtime.is_running = True
        self.voice.state = "ready"
        self.voice.stop_error = OSError("provider timeout")

        with self.assertRaisesRegex(RuntimeError, "provider timeout"):
            self.service.quiesce("study paused")

        self.assertTrue(self.voice.suspended)
        self.assertEqual(
            self.voice.suspension_events[0],
            (True, "study paused"),
        )
        self.assertFalse(self.service.master_enabled)
        self.assertFalse(self.service.runtime.is_running)
        self.assertEqual(self.service.runtime.stop_count, 1)

    def test_resume_reopens_gate_before_restoring_master_and_is_idempotent(self):
        self.service.quiesce("study paused")
        self.service.resume_from_quiesce(master_enabled=True)
        self.service.resume_from_quiesce(master_enabled=True)

        self.assertFalse(self.voice.suspended)
        self.assertEqual(self.voice.suspension_events[-1][0], False)
        self.assertTrue(self.service.master_enabled)
        self.assertTrue(self.ingress.session_snapshot().armed)

        self.service.quiesce("study paused")
        self.service.quiesce("study paused")
        self.assertTrue(self.voice.suspended)
        self.assertFalse(self.service.master_enabled)


if __name__ == "__main__":
    unittest.main()
