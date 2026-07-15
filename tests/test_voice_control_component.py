from pathlib import Path
import unittest


class VoiceControlComponentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.component = Path(
            "modules/ui/voice_control_component/index.html"
        ).read_text(encoding="utf-8")
        cls.capture = Path(
            "modules/media/live_capture_component/index.html"
        ).read_text(encoding="utf-8")

    def test_component_never_opens_a_second_device_capture(self) -> None:
        self.assertNotIn("getUserMedia", self.component)
        self.assertNotIn("MediaRecorder", self.component)
        self.assertNotIn("AudioWorklet", self.component)
        self.assertEqual(self.capture.count("navigator.mediaDevices.getUserMedia"), 1)
        self.assertEqual(self.capture.count("new window.FaceMesh("), 1)

    def test_session_handoff_and_same_origin_routes_are_explicit(self) -> None:
        self.assertIn('"attentive-media-session"', self.component)
        self.assertIn('"attentive-media-session"', self.capture)
        self.assertIn("globalThis.localStorage.setItem", self.capture)
        self.assertIn("globalThis.localStorage.removeItem", self.capture)
        self.assertIn('"X-Attentive-Media-Session"', self.component)
        self.assertIn('new URL("/attentive-voice/events", window.location.href)', self.component)
        self.assertIn('url.searchParams.set("session", session)', self.component)
        self.assertNotIn("127.0.0.1:8503", self.component)

    def test_ptt_keyboard_audio_queue_and_safe_text_rendering_exist(self) -> None:
        for token in ("pointerdown", "pointerup", "pointercancel", 'event.code === "Space"', 'event.code === "Enter"'):
            self.assertIn(token, self.component)
        self.assertIn('socket.binaryType = "arraybuffer"', self.component)
        self.assertIn("sampleRate: 24000", self.component)
        self.assertIn("view.getInt16(index * 2, true)", self.component)
        self.assertIn("scheduledNodes", self.component)
        self.assertIn("clearPlayback", self.component)
        self.assertIn("textContent", self.component)
        self.assertNotIn("innerHTML", self.component)

    def test_capture_fatigue_contract_is_unchanged(self) -> None:
        self.assertIn("const FATIGUE_INTERVAL_MS = 500", self.capture)
        self.assertIn("fatigueCanvas.width = 224", self.capture)
        self.assertIn("fatigueCanvas.height = 224", self.capture)
        self.assertIn('}, "image/jpeg", 0.80)', self.capture)
        self.assertIn('fetch("/attentive-media/fatigue"', self.capture)


if __name__ == "__main__":
    unittest.main()
