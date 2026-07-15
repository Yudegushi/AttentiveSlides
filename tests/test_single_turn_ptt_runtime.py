from pathlib import Path
import unittest

import numpy as np

from modules.common.schemas import Transcript
from modules.realtime.realtime_contracts import TargetBinding
from modules.system.single_turn_ptt_runtime import SingleTurnPTTRuntime


class FakeClock:
    def __init__(self) -> None:
        self.value = 10.0

    def __call__(self) -> float:
        return self.value


class FakeCollector:
    def __init__(self) -> None:
        self.calls = []

    def freeze_start(self, *, slide_id, speech_started_at):
        token = ("start", slide_id, speech_started_at)
        self.calls.append(token)
        return token

    def freeze_end(self, context, *, speech_ended_at, current_slide_id):
        token = ("end", context, speech_ended_at, current_slide_id)
        self.calls.append(token)
        return token


class FakeRunner:
    def __init__(self) -> None:
        self.calls = []

    def run(self, result, context) -> None:
        self.calls.append((result, context))


class SingleTurnPTTRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.clock = FakeClock()
        self.collector = FakeCollector()
        self.runner = FakeRunner()
        self.transcribe_paths = []
        self.statuses = []

        def transcribe(path):
            self.transcribe_paths.append(path)
            self.assertTrue(Path(path).exists())
            return Transcript(" explain this ", language="en", confidence=0.9)

        self.runtime = SingleTurnPTTRuntime(
            transcribe=transcribe,
            context_collector=self.collector,
            proposal_runner=self.runner,
            on_status=lambda status, message: self.statuses.append((status, message)),
            clock=self.clock,
            minimum_seconds=0.01,
            maximum_seconds=1.0,
        )
        self.target = TargetBinding("deck", 2, "a", "A", "target")
        self.pcm = np.zeros(320, dtype="<i2").tobytes()

    async def test_audio_outside_button_never_publishes(self) -> None:
        await self.runtime.accept_pcm(session_id="session", pcm=self.pcm)
        await self.runtime.stop(session_id="session")
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.transcribe_paths, [])

    async def test_one_press_release_publishes_one_existing_flow_result(self) -> None:
        await self.runtime.start(session_id="session", target=self.target)
        await self.runtime.accept_pcm(session_id="session", pcm=self.pcm)
        self.clock.value = 10.25
        await self.runtime.stop(session_id="session")
        await self.runtime.stop(session_id="session")

        self.assertEqual(len(self.runner.calls), 1)
        result, frozen = self.runner.calls[0]
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.transcript.text, "explain this")
        self.assertEqual(result.turn.finalization_reason, "push_to_talk_release")
        self.assertEqual(self.collector.calls[0], ("start", 2, 10.0))
        self.assertEqual(frozen[0], "end")
        self.assertFalse(Path(self.transcribe_paths[0]).exists())

    async def test_session_mismatch_and_short_input_do_not_publish(self) -> None:
        await self.runtime.start(session_id="session", target=self.target)
        await self.runtime.accept_pcm(session_id="old", pcm=self.pcm)
        await self.runtime.stop(session_id="old")
        self.assertTrue(self.runtime.snapshot()["recording"])
        await self.runtime.stop(session_id="session")
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.runtime.snapshot()["status"], "too_short")

    async def test_overflow_is_rejected_without_transcription(self) -> None:
        runtime = SingleTurnPTTRuntime(
            transcribe=lambda path: Transcript("unused"),
            context_collector=self.collector,
            proposal_runner=self.runner,
            clock=self.clock,
            minimum_seconds=0.001,
            maximum_seconds=0.005,
        )
        await runtime.start(session_id="session", target=self.target)
        await runtime.accept_pcm(session_id="session", pcm=self.pcm)
        await runtime.stop(session_id="session")
        self.assertEqual(runtime.snapshot()["status"], "too_long")
        self.assertEqual(self.runner.calls, [])

    async def test_cancel_invalidates_recording_and_late_stop(self) -> None:
        await self.runtime.start(session_id="session", target=self.target)
        await self.runtime.accept_pcm(session_id="session", pcm=self.pcm)
        await self.runtime.cancel("master off")
        await self.runtime.stop(session_id="session")
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.runtime.snapshot()["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
