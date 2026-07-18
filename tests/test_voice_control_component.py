from pathlib import Path
import unittest

from modules.ui.design_tokens import SEMANTIC_KEYS


class VoiceControlComponentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.component = Path(
            "modules/ui/voice_control_component/index.html"
        ).read_text(encoding="utf-8")
        cls.wrapper = Path(
            "modules/ui/voice_control_component/__init__.py"
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
        self.assertIn('"X-Attentive-Media-Session"', self.component)
        self.assertIn('new URL("/attentive-voice/events", window.location.href)', self.component)
        self.assertIn('url.searchParams.set("session", session)', self.component)
        self.assertNotIn("127.0.0.1:8503", self.component)

    def test_pointer_and_global_v_use_the_same_ptt_paths(self) -> None:
        for token in (
            "pointerdown",
            "pointerup",
            "pointercancel",
            "lostpointercapture",
            'event.code !== "KeyV"',
            "void startPtt(event)",
            "void stopPtt(event)",
            'command("/attentive-voice/ptt/start")',
            'command("/attentive-voice/ptt/stop")',
        ):
            self.assertIn(token, self.component)
        self.assertIn("setPointerCapture", self.component)
        self.assertIn("releasePointerCapture", self.component)

    def test_global_v_focus_modifier_repeat_and_parent_guards_exist(self) -> None:
        for token in (
            "window.parent.document",
            "const shortcutDocuments = new Set([document])",
            "shortcutDocuments.add(window.parent.document)",
            "shortcutDocument.addEventListener",
            "shouldIgnoreShortcut",
            "event.repeat",
            "event.ctrlKey",
            "event.altKey",
            "event.metaKey",
            "event.shiftKey",
            "input, textarea, select, [contenteditable='true']",
            "[role='dialog'], [role='menu'], .palette-control",
            "keyboardPttActive",
        ):
            self.assertIn(token, self.component)

    def test_lost_keyup_and_teardown_stop_safely_and_remove_listeners(self) -> None:
        for token in (
            'shortcutWindow.addEventListener("blur"',
            '"visibilitychange"',
            'window.addEventListener("pagehide", teardown)',
            'window.addEventListener("beforeunload", teardown)',
            "safeStopPtt",
            "keepalive: true",
            "Promise.resolve(pendingStart)",
            'shortcutDocument.removeEventListener("keydown"',
            'shortcutDocument.removeEventListener("keyup"',
            'shortcutDocument.removeEventListener("visibilitychange"',
            'shortcutWindow.removeEventListener("blur"',
        ):
            self.assertIn(token, self.component)

    def test_ptt_command_responses_surface_nested_retryable_failures(self) -> None:
        for token in (
            "payload.ptt",
            '"too_short"',
            '"too_long"',
            '"empty_transcript"',
            '"stt_failed"',
            "handleCommandResponse(await command",
            "Please try speaking again.",
        ):
            self.assertIn(token, self.component)

    def test_hands_free_pause_resume_and_signature_reset_exist(self) -> None:
        self.assertIn('command("/attentive-voice/continuous/start")', self.component)
        self.assertIn('command("/attentive-voice/continuous/stop")', self.component)
        self.assertIn("continuousPaused", self.component)
        self.assertIn("Pause listening", self.component)
        self.assertIn("Resume listening", self.component)
        self.assertIn("signature !== previousSignature", self.component)

    def test_study_pause_disables_v_and_uses_safe_stop_paths(self) -> None:
        self.assertIn("study_paused=bool(study_paused)", self.wrapper)
        for token in (
            "args.study_paused",
            "wasStudyPaused",
            "safeStopPtt()",
            'command("/attentive-voice/continuous/stop")',
            'updateStatus("Study paused", "", 0)',
        ):
            self.assertIn(token, self.component)

    def test_transport_is_compact_and_has_no_tutor_or_provider_block(self) -> None:
        self.assertIn('id="meter"', self.component)
        self.assertIn('id="ptt"', self.component)
        self.assertIn("<kbd>V</kbd>", self.component)
        self.assertIn('id="activity"', self.component)
        self.assertIn("min-height: 42px", self.component)
        self.assertNotIn('id="answer"', self.component)
        self.assertNotIn("Tutor:", self.component)
        self.assertNotIn("Grounded Tutor", self.component)
        self.assertNotIn("Omni realtime", self.component)
        self.assertNotIn("innerHTML", self.component)

    def test_frame_height_is_fixed_once_without_layout_measurement(self) -> None:
        self.assertIn("const FRAME_HEIGHT = 150", self.component)
        self.assertIn("let frameHeightSent = false", self.component)
        self.assertIn("if (frameHeightSent) return", self.component)
        self.assertIn("height: FRAME_HEIGHT", self.component)
        self.assertEqual(
            self.component.count('send("streamlit:setFrameHeight"'),
            1,
        )
        self.assertNotIn("getBoundingClientRect", self.component)

    def test_complete_whitelisted_palette_map_is_applied_to_iframe_root(self) -> None:
        self.assertIn("palette_tokens=safe_tokens", self.wrapper)
        self.assertIn("palette_tokens must contain every semantic token", self.wrapper)
        self.assertIn("applyPalette(args.palette_tokens)", self.component)
        self.assertIn("document.documentElement.style.setProperty", self.component)
        self.assertIn("for (const name of SEMANTIC_KEYS)", self.component)
        for name in SEMANTIC_KEYS:
            self.assertIn(f'"{name}"', self.component)

    def test_audio_queue_and_safe_text_rendering_are_preserved(self) -> None:
        self.assertIn('socket.binaryType = "arraybuffer"', self.component)
        self.assertIn("sampleRate: 24000", self.component)
        self.assertIn("view.getInt16(index * 2, true)", self.component)
        self.assertIn("scheduledNodes", self.component)
        self.assertIn("clearPlayback", self.component)
        self.assertIn("textContent", self.component)

    def test_playback_is_automatic_without_a_visible_enable_button(self) -> None:
        self.assertNotIn('id="playback"', self.component)
        self.assertNotIn("Enable playback", self.component)
        self.assertNotIn("Playback enabled", self.component)
        self.assertIn("function onPlaybackGesture()", self.component)
        self.assertIn(
            'shortcutDocument.addEventListener("pointerdown", onPlaybackGesture',
            self.component,
        )
        self.assertIn("void ensureAudioContext().catch(() => {})", self.component)

    def test_capture_fatigue_contract_is_unchanged(self) -> None:
        self.assertIn("const FATIGUE_INTERVAL_MS = 250", self.capture)
        self.assertIn("ensureCanvasSize(fatigueCanvas, 224, 224)", self.capture)
        self.assertIn('}, "image/jpeg", 0.80)', self.capture)
        self.assertIn('fetch("/attentive-media/fatigue"', self.capture)


if __name__ == "__main__":
    unittest.main()
