from dataclasses import dataclass
import queue
import unittest

import numpy as np

from modules.audio.voice_turn_detector import SpeechTurn
from modules.common.schemas import Transcript
from modules.system.audio_worker import AudioTurnResult
from modules.system.controller import SystemController
from modules.system.runtime_state import RuntimeState


@dataclass(frozen=True)
class FakeContext:
    slide_id: int
    speech_started_at: float
    speech_ended_at: float | None = None
    slide_changed_during_turn: bool = False


class FakeCollector:
    def freeze_start(self, *, slide_id, speech_started_at):
        return FakeContext(slide_id, speech_started_at)

    def freeze_end(self, context, *, speech_ended_at, current_slide_id):
        return FakeContext(
            context.slide_id,
            context.speech_started_at,
            speech_ended_at,
            current_slide_id != context.slide_id,
        )


class FakeMedia:
    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.reasons = []

    def start(self):
        self.starts += 1

    def stop(self, reason="requested"):
        self.stops += 1
        self.reasons.append(reason)


class FakeSensing:
    def __init__(self):
        self.slides = []
        self.starts = 0
        self.stops = 0

    def set_slide(self, slide_id):
        self.slides.append(slide_id)

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1


class FakeAudio:
    def __init__(self):
        self.results = queue.Queue()
        self.starts = 0
        self.stops = 0
        self.on_started = None
        self.on_discarded = None

    def set_turn_callbacks(self, *, on_started, on_discarded):
        self.on_started = on_started
        self.on_discarded = on_discarded

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1

    def get_result_nowait(self):
        return self.results.get_nowait()

    def emit_started(self, timestamp):
        self.on_started(timestamp)


@dataclass(frozen=True)
class FakeOutcome:
    query_id: str | None
    pending_confirmation: bool


class FakeRunner:
    def __init__(self):
        self.contexts = []
        self.resumes = []

    def run(self, audio_result, context):
        self.contexts.append(context)
        return FakeOutcome("q_1", pending_confirmation=True)

    def resume_confirmation(self, query_id, confirmed_aoi_id):
        self.resumes.append((query_id, confirmed_aoi_id))
        return FakeOutcome(query_id, pending_confirmation=False)


def result(started_at, ended_at, *, status="completed"):
    return AudioTurnResult(
        turn=SpeechTurn(
            samples=np.ones(480, dtype=np.int16),
            sample_rate=16_000,
            started_at=started_at,
            ended_at=ended_at,
            finalization_reason="silence",
        ),
        transcript=Transcript("解释这个") if status == "completed" else None,
        status=status,
        error=None if status == "completed" else "stt failure",
    )


class SystemControllerTest(unittest.TestCase):
    def setUp(self):
        self.media = FakeMedia()
        self.sensing = FakeSensing()
        self.audio = FakeAudio()
        self.collector = FakeCollector()
        self.runner = FakeRunner()
        self.controller = SystemController(
            media_source=self.media,
            sensing_worker=self.sensing,
            audio_worker=self.audio,
            context_collector=self.collector,
            turn_runner=self.runner,
        )
        self.controller.set_slide(5)

    def test_start_stop_disconnect_are_idempotent_and_cleanup_workers(self):
        self.controller.start()
        self.controller.start()

        self.assertEqual(self.controller.state, RuntimeState.MONITORING)
        self.assertEqual((self.media.starts, self.sensing.starts, self.audio.starts), (1, 1, 1))
        self.assertEqual(self.sensing.slides, [5])

        self.controller.handle_disconnect()
        self.controller.handle_disconnect()

        self.assertEqual(self.controller.state, RuntimeState.STOPPED)
        self.assertEqual((self.media.stops, self.sensing.stops, self.audio.stops), (1, 1, 1))
        self.assertEqual(self.media.reasons, ["browser disconnected"])

    def test_freezes_start_slide_ignores_busy_speech_and_resumes_confirmation(self):
        self.controller.start()
        self.audio.emit_started(10.0)
        self.assertEqual(self.controller.state, RuntimeState.SPEECH_ACTIVE)

        self.controller.set_slide(6)
        self.audio.results.put(result(10.0, 11.0))
        outcomes = self.controller.poll()

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(self.controller.state, RuntimeState.WAITING_CONFIRMATION)
        self.assertTrue(self.runner.contexts[0].slide_changed_during_turn)
        self.assertEqual(self.runner.contexts[0].slide_id, 5)

        self.audio.emit_started(12.0)
        self.assertEqual(self.controller.busy_turn_count, 1)
        self.controller.confirm("q_1", "alpha")

        self.assertEqual(self.controller.state, RuntimeState.MONITORING)
        self.assertEqual(self.runner.resumes, [("q_1", "alpha")])

    def test_recoverable_stt_error_returns_to_monitoring_without_running_tutor(self):
        self.controller.start()
        self.audio.emit_started(10.0)
        self.audio.results.put(result(10.0, 10.5, status="stt_error"))

        outcomes = self.controller.poll()

        self.assertEqual(outcomes, [])
        self.assertEqual(self.controller.state, RuntimeState.MONITORING)
        self.assertEqual(self.runner.contexts, [])


if __name__ == "__main__":
    unittest.main()
