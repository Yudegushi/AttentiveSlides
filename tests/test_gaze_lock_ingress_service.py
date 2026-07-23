import asyncio
from pathlib import Path
import unittest

from aiohttp.test_utils import TestClient, TestServer

from modules.gaze_lock_test.ingress_service import GazeOnlyIngressService


ROOT = Path(__file__).resolve().parents[1]


def geometry_payload():
    return {
        "deck_id": "deck-a",
        "slide_id": 1,
        "layout_revision": 7,
        "browser_timestamp_ms": 1000.0,
        "viewport_width": 1000,
        "viewport_height": 800,
        "device_pixel_ratio": 1,
        "slide_rect": {"x1": 0, "y1": 0, "x2": 1000, "y2": 800},
        "aoi_rects": {
            "alpha": {"x1": 100, "y1": 100, "x2": 300, "y2": 300},
        },
    }


def gaze_payload():
    return {
        "sequence": 1,
        "browser_timestamp_ms": 1200.0,
        "x_css": 150.0,
        "y_css": 150.0,
        "viewport_width": 1000,
        "viewport_height": 800,
        "valid": True,
        "face_detected": True,
        "source": "eyetheia_local",
    }


class GazeOnlyIngressServiceTest(unittest.TestCase):
    def test_owns_one_directly_activated_gaze_transport(self):
        service = GazeOnlyIngressService(capture_html="<p>capture-only</p>")

        self.assertIs(service.ingress.source, service.source)
        self.assertIs(service.ingress.observations, service.observations)
        self.assertTrue(service.ingress.session_snapshot().armed)
        service.ingress.start("capture-a")
        service.ingress.accept_geometry_json(geometry_payload())
        sample = service.ingress.accept_gaze_json("capture-a", gaze_payload())

        self.assertEqual(service.capture_generation(), 1)
        self.assertEqual(sample.geometry.geometry.slide_id, 1)
        self.assertFalse(service.ingress.session_snapshot().video_fresh)
        self.assertFalse(service.ingress.session_snapshot().audio_fresh)

    def test_capture_page_and_health_are_served(self):
        async def scenario():
            service = GazeOnlyIngressService(capture_html="<p>capture-only</p>")
            client = TestClient(TestServer(service.build_app()))
            await client.start_server()
            try:
                capture = await client.get("/capture")
                health = await client.get("/health")
                self.assertEqual(await capture.text(), "<p>capture-only</p>")
                self.assertEqual(health.status, 503)
                self.assertTrue((await health.json())["gaze_only"])
            finally:
                await client.close()

        asyncio.run(scenario())

    def test_capture_html_is_camera_only_and_uploads_only_gaze(self):
        source = (
            ROOT
            / "modules"
            / "gaze_lock_test"
            / "capture"
            / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("navigator.mediaDevices.getUserMedia({", source)
        self.assertIn("audio: false", source)
        self.assertIn("getVideoTracks().length !== 1", source)
        self.assertIn("getAudioTracks().length !== 0", source)
        self.assertIn('fetch("/attentive-media/gaze"', source)
        self.assertIn('fetch("/attentive-media/heartbeat"', source)
        self.assertIn('fetch("/attentive-media/start"', source)
        self.assertIn('fetch("/attentive-media/stop"', source)
        self.assertIn("new window.FaceMesh", source)
        self.assertIn("new WebSocket(EYETHEIA_URL)", source)
        self.assertNotIn("AudioContext", source)
        self.assertNotIn('fetch("/attentive-media/audio"', source)
        self.assertNotIn('fetch("/attentive-media/video"', source)
        self.assertNotIn('fetch("/attentive-media/fatigue"', source)


if __name__ == "__main__":
    unittest.main()
