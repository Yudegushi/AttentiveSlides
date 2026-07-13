import unittest

import numpy as np

from modules.audio.voice_turn_detector import SpeechTurn
from modules.common.schemas import GazePrediction, LearningState, Transcript
from modules.system.adapters import MockManifestSlideProvider, SensingFrame
from modules.system.audio_worker import AudioTurnResult
from modules.system.live_turn_runner import LiveTurnRunner
from modules.system.sensing_snapshot_store import SensingSnapshot, SensingSnapshotStore
from modules.system.turn_context import TurnContextCollector


class LiveTurnRunnerTest(unittest.TestCase):
    def setUp(self):
        self.provider = MockManifestSlideProvider()
        self.store = SensingSnapshotStore(stale_after_seconds=5.0)
        self.collector = TurnContextCollector(
            slide_provider=self.provider,
            snapshot_store=self.store,
            minimum_dwell_seconds=0.1,
        )
        self.context = self.collector.freeze_end(
            self.collector.freeze_start(slide_id=5, speech_started_at=10.0),
            speech_ended_at=10.5,
            current_slide_id=5,
        )
        self.store.put(
            SensingSnapshot(
                slide_id=5,
                source_timestamp=1.0,
                source_timestamp_clock="browser_performance_seconds",
                processed_at=10.1,
                frame=SensingFrame(
                    gaze_prediction=GazePrediction(5, "middle_right", "right_figure", 0.9),
                    learning_state=LearningState(),
                ),
                is_valid=True,
                invalid_reason=None,
                manifest_identity=self.context.manifest_identity,
            )
        )
        self.runner = LiveTurnRunner(
            slide_provider=self.provider,
            context_collector=self.collector,
        )

    def audio_result(self, *, status="completed"):
        return AudioTurnResult(
            turn=SpeechTurn(
                samples=np.ones(480, dtype=np.int16),
                sample_rate=16_000,
                started_at=10.0,
                ended_at=10.5,
                finalization_reason="silence",
            ),
            transcript=Transcript("解释这个") if status == "completed" else None,
            status=status,
            error=None if status == "completed" else "stt failure",
        )

    def test_reuses_canonical_pipeline_and_preserves_confirmation_gate(self):
        pending = self.runner.run(self.audio_result(), self.context)

        self.assertTrue(pending.pending_confirmation)
        self.assertEqual(pending.interaction_result.tutor_response.response_mode, "pending_confirmation")
        self.assertEqual(pending.interaction_result.resolved_query.slide_id, 5)

        resumed = self.runner.resume_confirmation(
            pending.interaction_result.resolved_query.query_id,
            "bottom_caption",
        )

        self.assertFalse(resumed.pending_confirmation)
        self.assertEqual(resumed.interaction_result.resolved_query.resolved_aoi_id, "bottom_caption")
        self.assertTrue(resumed.interaction_result.log_event.user_corrected)

    def test_stt_error_is_recoverable_and_does_not_enter_pipeline(self):
        outcome = self.runner.run(self.audio_result(status="stt_error"), self.context)

        self.assertFalse(outcome.pending_confirmation)
        self.assertIsNone(outcome.interaction_result)
        self.assertEqual(outcome.error, "stt failure")


if __name__ == "__main__":
    unittest.main()
