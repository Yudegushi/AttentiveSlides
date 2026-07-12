from pathlib import Path
import inspect
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

from modules.media import BrowserMediaSource
from apps.media_transport_probe import (
    MASTER_KEY,
    PENDING_COMPONENT_FAILURE_KEY,
    _apply_pending_component_failure,
    _sync_component_failure,
    _sync_source_lifecycle,
)


class MediaTransportProbeContractTest(unittest.TestCase):
    def setUp(self):
        self.source = BrowserMediaSource()

    def test_probe_uses_webrtc_and_disables_audio_sendback(self):
        source = Path("apps/media_transport_probe.py").read_text(encoding="utf-8")

        self.assertIn("webrtc_streamer(", source)
        self.assertIn("sendback_audio=False", source)
        self.assertIn("desired_playing_state=requested", source)
        self.assertNotIn("cv2.VideoCapture", source)

    @unittest.skipIf(AppTest is None, "Streamlit AppTest is unavailable.")
    def test_probe_initial_render_has_no_import_error(self):
        app = AppTest.from_file("apps/media_transport_probe.py")

        app.run(timeout=20)

        self.assertEqual(
            len(app.exception),
            0,
            [exception.message for exception in app.exception],
        )

    def test_probe_disables_streamlit_webrtc_async_processing(self):
        source = Path("apps/media_transport_probe.py").read_text(encoding="utf-8")

        self.assertIn("async_processing=False", source)
        self.assertNotIn("async_processing=True", source)

    def test_requested_but_not_playing_keeps_source_stopped(self):
        self.source.start()

        _sync_source_lifecycle(self.source, requested=True, playing=False)

        self.assertFalse(self.source.is_running)

    def test_requested_and_playing_starts_source_idempotently(self):
        _sync_source_lifecycle(self.source, requested=True, playing=True)
        _sync_source_lifecycle(self.source, requested=True, playing=True)

        self.assertTrue(self.source.is_running)
        self.assertEqual(self.source.start_count, 1)

    def test_component_failure_stops_source_and_resets_master_before_next_widget(self):
        state = {MASTER_KEY: True}
        self.source.start()

        _sync_component_failure(self.source, state, "permission denied")

        self.assertFalse(self.source.is_running)
        self.assertEqual(state[PENDING_COMPONENT_FAILURE_KEY], "permission denied")
        self.assertTrue(state[MASTER_KEY])

        self.assertEqual(_apply_pending_component_failure(state), "permission denied")
        self.assertFalse(state[MASTER_KEY])
        self.assertNotIn(PENDING_COMPONENT_FAILURE_KEY, state)

    def test_probe_adds_repository_root_when_run_as_a_script(self):
        source = Path("apps/media_transport_probe.py").read_text(encoding="utf-8")

        self.assertIn("REPOSITORY_ROOT = Path(__file__).resolve().parents[1]", source)
        self.assertIn("sys.path.insert(0, str(REPOSITORY_ROOT))", source)

    def test_probe_does_not_persist_raw_media(self):
        source = Path("apps/media_transport_probe.py").read_text(encoding="utf-8")

        for forbidden in ("VideoWriter", "AudioSegment.export", "soundfile.write"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_media_callbacks_only_convert_timestamp_and_push(self):
        for callback_name in ("video_frame_callback", "audio_frame_callback"):
            source = inspect.getsource(getattr(BrowserMediaSource, callback_name))
            for forbidden in (
                "with self._lock",
                "_video_count",
                "_audio_count",
                "_last_video_timestamp",
                "_last_audio_timestamp",
                "streamlit",
                "st.",
                "mediapipe",
                "whisper",
                "llm",
                "open(",
                ".write(",
            ):
                with self.subTest(callback=callback_name, forbidden=forbidden):
                    self.assertNotIn(forbidden, source.lower())
