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


def jpeg_payload() -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 2), color=(255, 0, 0)).save(output, format="JPEG")
    return output.getvalue()


def pcm_payload() -> bytes:
    return np.array([1, -2, 3, -4], dtype="<i2").tobytes()


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

    def test_external_shared_source_stop_restarts_runtime_through_fresh_gate(self):
        original_start = self.runtime.start

        def start_runtime_and_source():
            self.source.start()
            original_start()

        self.runtime.start = start_runtime_and_source
        self.start_ready_session()
        self.source.stop(reason="deck reload")

        self.service.reconcile_once()

        self.assertEqual(self.runtime.stop_count, 1)
        self.assertFalse(self.runtime.is_running)
        self.service.reconcile_once()
        self.assertEqual(self.runtime.start_count, 2)
        self.assertTrue(self.source.is_running)

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


if __name__ == "__main__":
    unittest.main()
