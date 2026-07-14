from threading import Event
import unittest

import numpy as np

from modules.common.schemas import AOI, GazePrediction, LearningState, Transcript
from modules.human_sensing.contracts import (
    AOIPrediction as MemberAOIPrediction,
    FaceStateSignals,
    GazePrediction as MemberGazePrediction,
    LearningState as MemberLearningState,
)
from modules.media import BrowserMediaSource
from modules.system.adapters import SensingFrame, SlideFrame, build_pipeline_input_bundle, run_interaction_from_bundle

try:
    from modules.system.human_sensing_adapter import HumanSensingAdapter
    from modules.system.sensing_snapshot_store import SensingSnapshotStore
    from modules.system.sensing_worker import SensingWorker, SensingWorkerConfig
except ImportError:
    HumanSensingAdapter = None
    SensingSnapshotStore = None
    SensingWorker = None
    SensingWorkerConfig = None


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeSlideProvider:
    deck_id = "live-deck"

    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        return SlideFrame(
            deck_id=self.deck_id,
            slide_id=slide_id,
            slide_text="Current concept",
            neighbor_slide_text="Neighbor concept",
            aois=[
                AOI("target", [0.2, 0.2, 0.6, 0.6], "text", text="Current concept"),
                AOI("whole_slide", [0.0, 0.0, 1.0, 1.0], "whole_slide", text="Current concept"),
            ],
        )


class FakeExtractor:
    def __init__(self) -> None:
        self.values: list[int] = []
        self.shapes: list[tuple[int, ...]] = []
        self.closed = 0

    def extract(self, frame):
        self.values.append(int(frame[0, 0, 0]))
        self.shapes.append(frame.shape)
        return object()

    def close(self) -> None:
        self.closed += 1


class ExplodingExtractor(FakeExtractor):
    def __init__(self, signal: Event) -> None:
        super().__init__()
        self.signal = signal

    def extract(self, frame):
        self.signal.set()
        raise RuntimeError("synthetic inference failure")


class FakeGazeEstimator:
    def predict(self, frame, **_kwargs):
        return MemberGazePrediction(
            timestamp=2.0,
            slide_id=1,
            gaze_grid="middle_center",
            confidence=0.8,
            stable_duration_sec=2.0,
        )


class FakeFaceStateDetector:
    def detect_face_state_signals(self, **kwargs):
        return FaceStateSignals(
            timestamp=kwargs["timestamp"],
            face_detected=True,
            screen_facing_score=0.9,
            yawn_detected=False,
            yawn_count_last_3min=0,
            eyes_closed=False,
            eye_closure_duration_sec=0.0,
            head_down=False,
            mouth_aspect_ratio=0.1,
            eye_aspect_ratio=0.3,
        )


class FakeLearningAggregator:
    def aggregate(self, face_state, **_kwargs):
        return MemberLearningState(
            timestamp=face_state.timestamp,
            face_detected=True,
            screen_facing_score=face_state.screen_facing_score,
            yawn_detected=False,
            yawn_count_last_3min=0,
            eyes_closed=False,
            eye_closure_duration_sec=0.0,
            head_down=False,
            fatigue_signal_score=0.1,
            possible_review_needed=False,
        )


class StaticTranscriptProvider:
    def get_transcript(self) -> Transcript:
        return Transcript("解释这个")


def map_to_target(gaze, aois):
    assert [aoi.aoi_id for aoi in aois] == ["target"]
    return MemberAOIPrediction(
        timestamp=gaze.timestamp,
        slide_id=gaze.slide_id,
        gaze_grid=gaze.gaze_grid,
        predicted_aoi_id="target",
        confidence=0.8,
        stable_duration_sec=gaze.stable_duration_sec,
        candidate_scores={"target": 0.8},
    )


def create_worker(source, store, extractor, clock):
    return SensingWorker(
        media_source=source,
        slide_provider=FakeSlideProvider(),
        snapshot_store=store,
        adapter=HumanSensingAdapter(),
        face_landmark_extractor_factory=lambda: extractor,
        gaze_estimator_factory=FakeGazeEstimator,
        face_state_detector_factory=FakeFaceStateDetector,
        learning_state_aggregator_factory=FakeLearningAggregator,
        head_pose_estimator=lambda _landmarks: None,
        gaze_to_aoi=map_to_target,
        clock=clock,
        config=SensingWorkerConfig(inference_interval_seconds=0.0, poll_interval_seconds=0.01),
    )


class SensingWorkerTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SensingWorker)
        self.source = BrowserMediaSource(video_queue_size=3)
        self.source.start()
        self.clock = FakeClock(10.0)
        self.store = SensingSnapshotStore(stale_after_seconds=1.0, clock=self.clock)

    def tearDown(self):
        self.source.stop()

    def test_processes_only_latest_frame_excludes_whole_slide_and_clears_on_slide_change(self):
        extractor = FakeExtractor()
        worker = create_worker(self.source, self.store, extractor, self.clock)
        worker.set_slide(1)
        self.source.accept_video_frame(
            np.full((4, 4, 3), 1, dtype=np.uint8),
            timestamp=1.0,
            timestamp_clock="browser_performance_seconds",
        )
        self.source.accept_video_frame(
            np.full((4, 4, 3), 2, dtype=np.uint8),
            timestamp=2.0,
            timestamp_clock="browser_performance_seconds",
        )

        self.assertTrue(worker.process_available_frame())
        snapshot = self.store.latest_valid_for_slide(1)

        self.assertEqual(extractor.values, [2])
        self.assertEqual(extractor.shapes, [(4, 4, 3)])
        self.assertEqual(snapshot.source_timestamp, 2.0)
        self.assertEqual(snapshot.frame.gaze_prediction.predicted_aoi_id, "target")
        self.assertTrue(snapshot.frame.learning_state.face_detected)
        self.assertTrue(snapshot.manifest_identity)
        worker.set_slide(2)
        self.assertIsNone(self.store.latest_valid_for_slide(1))
        self.assertIsNone(self.store.latest_valid_for_slide(2))
        worker.stop()
        self.assertEqual(extractor.closed, 1)

    def test_snapshot_store_can_drive_existing_confirmation_gate(self):
        frame = SensingFrame(
            gaze_prediction=GazePrediction(1, "middle_center", "target", 0.8, stable_duration_sec=2.0),
            learning_state=LearningState(),
        )
        self.store.put(
            self.store.snapshot(
                slide_id=1,
                source_timestamp=2.0,
                source_timestamp_clock="browser_performance_seconds",
                frame=frame,
                is_valid=True,
                invalid_reason=None,
            )
        )
        bundle = build_pipeline_input_bundle(
            slide_provider=FakeSlideProvider(),
            transcript_provider=StaticTranscriptProvider(),
            sensing_provider=self.store,
            slide_id=1,
        )

        result = run_interaction_from_bundle(bundle)

        self.assertEqual(result.resolved_query.confirmation_mode, "confirm_one")
        self.assertEqual(result.tutor_response.response_mode, "pending_confirmation")

    def test_thread_records_error_and_releases_extractor(self):
        signal = Event()
        extractor = ExplodingExtractor(signal)
        worker = create_worker(self.source, self.store, extractor, self.clock)
        worker.set_slide(1)
        self.source.accept_video_frame(
            np.full((4, 4, 3), 9, dtype=np.uint8),
            timestamp=3.0,
            timestamp_clock="browser_performance_seconds",
        )

        worker.start()

        self.assertTrue(signal.wait(timeout=1.0))
        worker.stop()

        self.assertFalse(worker.is_running)
        self.assertIsInstance(worker.last_error, RuntimeError)
        self.assertEqual(extractor.closed, 1)


if __name__ == "__main__":
    unittest.main()
