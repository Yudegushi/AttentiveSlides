import asyncio
import unittest

from modules.realtime.realtime_contracts import (
    SpeechMode,
    TargetBinding,
    VoiceEngine,
    VoicePreferences,
)
from modules.system.target_switching import TargetSwitchController
from modules.system.voice_event_hub import VoiceEventHub
from modules.system.voice_orchestrator import (
    AUTO_GAZE_TARGET_ID,
    VoiceOrchestrator,
)


class FakeOmni:
    def __init__(self) -> None:
        self.calls = []
        self.state = "off"
        self.target = None

    async def start_session(self, *, target, speech_mode):
        self.calls.append(("start", target.signature, speech_mode))
        self.state = "listening" if speech_mode is SpeechMode.CONTINUOUS else "ready"
        self.target = target

    async def set_speech_mode(self, mode):
        self.calls.append(("mode", mode))

    async def set_answer_audio_enabled(self, enabled):
        self.calls.append(("audio", enabled))

    async def accept_pcm(self, session_id, pcm):
        self.calls.append(("pcm", session_id, pcm))

    async def start_push_to_talk(self):
        self.calls.append(("ptt.start",))

    async def stop_push_to_talk(self):
        self.calls.append(("ptt.stop",))

    async def confirm_target_switch(self):
        self.calls.append(("confirm",))

    async def reject_target_switch(self):
        self.calls.append(("reject",))

    async def stop_session(self, reason):
        self.calls.append(("stop", reason))
        self.state = "off"

    def snapshot(self):
        return {"state": self.state, "target_signature": self.target.signature if self.target else None}


class FakePTT:
    def __init__(self) -> None:
        self.calls = []
        self.recording = False

    async def start(self, *, session_id, target):
        self.recording = True
        self.calls.append(("start", session_id, target.signature))

    async def accept_pcm(self, *, session_id, pcm):
        self.calls.append(("pcm", session_id, pcm))

    async def stop(self, *, session_id):
        self.recording = False
        self.calls.append(("stop", session_id))

    async def cancel(self, reason):
        self.recording = False
        self.calls.append(("cancel", reason))

    def snapshot(self):
        return {"recording": self.recording, "session_id": None, "status": "idle", "message": None}


def target(target_id="a"):
    return TargetBinding("deck", 1, target_id, target_id.upper(), "context")


class VoiceOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.events = VoiceEventHub()
        self.omni = FakeOmni()
        self.ptt = FakePTT()
        self.switching = TargetSwitchController()
        self.published = []
        self.boundaries = []
        self.initial_target = None
        self.orchestrator = VoiceOrchestrator(
            events=self.events,
            omni=self.omni,
            single_turn_ptt=self.ptt,
            target_switching=self.switching,
            publish_single_turn_transcript=self.published.append,
            on_single_turn_boundary=self.boundaries.append,
            resolve_initial_target=lambda _target: self.initial_target,
        )
        self.orchestrator.attach_loop(asyncio.get_running_loop())
        self.orchestrator.update_target(target())
        await asyncio.sleep(0)

    async def settle(self):
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_single_turn_continuous_leaves_audio_for_existing_worker(self) -> None:
        self.assertFalse(self.orchestrator.should_consume_audio())
        await self.orchestrator.handle_http_command("continuous/start", "session")
        await self.orchestrator.accept_pcm("session", b"pcm")
        self.assertFalse(any(call[0] == "pcm" for call in self.ptt.calls))
        self.assertFalse(any(call[0] == "pcm" for call in self.omni.calls))

    async def test_single_turn_ptt_consumes_only_the_active_button_session(self) -> None:
        self.orchestrator.update_preferences(
            VoicePreferences(speech_mode=SpeechMode.PUSH_TO_TALK)
        )
        await self.settle()
        self.assertTrue(self.orchestrator.should_consume_audio())
        await self.orchestrator.handle_http_command("ptt/start", "session")
        await self.orchestrator.accept_pcm("stale", b"drop")
        await self.orchestrator.accept_pcm("session", b"keep")
        await self.orchestrator.handle_http_command("ptt/stop", "session")
        self.assertIn(("pcm", "session", b"keep"), self.ptt.calls)
        self.assertNotIn(("pcm", "stale", b"drop"), self.ptt.calls)
        self.assertEqual(self.boundaries, ["voice routing changed"])

    async def test_single_turn_ptt_is_cancelled_on_mode_and_target_boundaries(self) -> None:
        self.orchestrator.update_preferences(
            VoicePreferences(speech_mode=SpeechMode.PUSH_TO_TALK)
        )
        await self.settle()
        await self.orchestrator.handle_http_command("ptt/start", "session")
        self.orchestrator.update_target(target("b"))
        await self.settle()
        self.assertIn(("cancel", "confirmed target changed"), self.ptt.calls)

        self.orchestrator.update_preferences(VoicePreferences())
        await self.settle()
        self.assertIn(("cancel", "speaking mode changed"), self.ptt.calls)

    async def test_omni_continuous_starts_once_and_target_change_is_boundary(self) -> None:
        self.orchestrator.update_preferences(
            VoicePreferences(engine=VoiceEngine.OMNI)
        )
        await self.settle()
        await self.orchestrator.handle_http_command("continuous/start", "session")
        await self.orchestrator.handle_http_command("continuous/start", "session")
        self.assertEqual(sum(call[0] == "start" for call in self.omni.calls), 1)
        self.orchestrator.update_target(target("b"))
        await self.settle()
        self.assertTrue(any(call[:2] == ("stop", "confirmed target changed") for call in self.omni.calls))
        self.assertEqual(self.orchestrator.snapshot()["target_signature"], target("b").signature)

    async def test_omni_resolves_auto_gaze_target_before_starting_provider(self) -> None:
        locked = TargetBinding(
            "deck",
            1,
            "b",
            "B",
            "context",
            (0.0, 0.0, 0.5, 0.5),
        )
        self.initial_target = locked
        self.orchestrator.update_preferences(
            VoicePreferences(engine=VoiceEngine.OMNI)
        )
        self.orchestrator.update_target(target(AUTO_GAZE_TARGET_ID))
        await self.settle()

        await self.orchestrator.handle_http_command("continuous/start", "session")

        starts = [call for call in self.omni.calls if call[0] == "start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0][1], locked.signature)
        self.assertEqual(
            self.orchestrator.snapshot()["target_signature"],
            locked.signature,
        )

    async def test_omni_auto_gaze_waits_when_no_stable_aoi_exists(self) -> None:
        self.orchestrator.update_preferences(
            VoicePreferences(engine=VoiceEngine.OMNI)
        )
        self.orchestrator.update_target(target(AUTO_GAZE_TARGET_ID))
        await self.settle()

        with self.assertRaisesRegex(ValueError, "stable gaze"):
            await self.orchestrator.handle_http_command(
                "continuous/start",
                "session",
            )

        self.assertFalse(any(call[0] == "start" for call in self.omni.calls))
        self.assertIsNone(self.orchestrator.snapshot()["session_id"])

    async def test_speech_mode_hot_update_preserves_active_omni_session(self) -> None:
        self.orchestrator.update_preferences(VoicePreferences(engine=VoiceEngine.OMNI))
        await self.settle()
        await self.orchestrator.handle_http_command("continuous/start", "session")
        self.orchestrator.update_preferences(
            VoicePreferences(engine=VoiceEngine.OMNI, speech_mode=SpeechMode.PUSH_TO_TALK)
        )
        await self.settle()
        self.assertIn(("mode", SpeechMode.PUSH_TO_TALK), self.omni.calls)
        self.assertEqual(sum(call[0] == "start" for call in self.omni.calls), 1)

    async def test_answer_audio_off_clears_runtime_audio_without_changing_engine(self) -> None:
        self.orchestrator.update_preferences(
            VoicePreferences(engine=VoiceEngine.OMNI, answer_audio_enabled=False)
        )
        await self.settle()
        self.assertIn(("audio", False), self.omni.calls)
        self.assertEqual(self.orchestrator.snapshot()["engine"], "omni")

    async def test_fallback_atomically_selects_single_turn_and_republishes_transcript(self) -> None:
        self.orchestrator.update_preferences(VoicePreferences(engine=VoiceEngine.OMNI))
        await self.settle()
        await self.orchestrator.fallback_to_single_turn("connect failed", " recovered ")
        snapshot = self.orchestrator.snapshot()
        self.assertEqual(snapshot["engine"], "single_turn")
        self.assertIn("已切换", snapshot["status_message"])
        self.assertEqual(self.published, ["recovered"])

    async def test_fallback_without_transcript_is_sanitized_and_returns_audio_to_single_turn(self) -> None:
        self.orchestrator.update_preferences(VoicePreferences(engine=VoiceEngine.OMNI))
        await self.settle()
        secret = "Authorization: Bearer private-api-key"
        await self.orchestrator.fallback_to_single_turn(secret, None)
        snapshot = self.orchestrator.snapshot()
        self.assertEqual(snapshot["engine"], "single_turn")
        self.assertIn("重新说一次", snapshot["status_message"])
        self.assertNotIn(secret, snapshot["status_message"])
        self.assertEqual(self.published, [])
        self.assertFalse(self.orchestrator.should_consume_audio())

    async def test_stop_clears_session_before_future_pcm(self) -> None:
        self.orchestrator.update_preferences(
            VoicePreferences(speech_mode=SpeechMode.PUSH_TO_TALK)
        )
        await self.settle()
        await self.orchestrator.handle_http_command("ptt/start", "session")
        await self.orchestrator.stop("master off")
        await self.orchestrator.accept_pcm("session", b"drop")
        self.assertNotIn(("pcm", "session", b"drop"), self.ptt.calls)
        self.assertIsNone(self.orchestrator.snapshot()["session_id"])

    async def test_clearing_target_stops_a_session_and_prevents_restart(self) -> None:
        self.orchestrator.update_preferences(VoicePreferences(engine=VoiceEngine.OMNI))
        await self.settle()
        await self.orchestrator.handle_http_command("continuous/start", "session")
        self.orchestrator.clear_target("selection removed")
        await self.settle()
        self.assertIsNone(self.orchestrator.snapshot()["target_signature"])
        self.assertIn(("stop", "selection removed"), self.omni.calls)
        with self.assertRaisesRegex(ValueError, "confirm a target"):
            await self.orchestrator.handle_http_command("continuous/start", "session")


if __name__ == "__main__":
    unittest.main()
