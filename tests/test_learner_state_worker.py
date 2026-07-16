import threading
import time
import unittest

import numpy as np

from modules.fatigue import FatigueTemporalTracker
from modules.learner_state import (
    AffectFrameOutput,
    EmotionTemporalTracker,
    EngagementTemporalConfig,
    EngagementTemporalTracker,
    LearnerStateStore,
)
from modules.media import FaceCropPacket
from modules.media.queue_policy import BoundedMediaQueue
from modules.system.learner_state_worker import LearnerStateWorker


class FakeClock:
    def __init__(self, value=10.0):
        self.value = value

    def __call__(self):
        return self.value


class RecordingAffectEstimator:
    def __init__(self, *, engagement=(0.2, 0.8)):
        self.images = []
        self.engagement_calls = []
        self.engagement = engagement

    def infer_frame(self, image):
        self.images.append(image.copy())
        return AffectFrameOutput(
            emotion_probabilities=(0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            feature=np.full((1280,), float(image[0, 0, 0]), dtype=np.float32),
        )

    def infer_engagement(self, features):
        self.engagement_calls.append(features.copy())
        return self.engagement


class RecordingFatigueEstimator:
    def __init__(self, probability=0.8):
        self.probability = probability
        self.images = []

    def predict(self, image):
        self.images.append(image.copy())
        return self.probability


def face_packet(value, timestamp=1.0):
    return FaceCropPacket(
        np.full((224, 224, 3), value, dtype=np.uint8),
        timestamp=timestamp,
    )


class LearnerStateWorkerTest(unittest.TestCase):
    def build_worker(
        self,
        affect_factory,
        fatigue_factory,
        *,
        engagement_config=None,
        emotion_tracker=None,
        on_snapshot=None,
        queue_size=4,
    ):
        media_queue = BoundedMediaQueue(queue_size)
        clock = FakeClock()
        store = LearnerStateStore(clock=clock)
        worker = LearnerStateWorker(
            media_queue,
            affect_estimator_factory=affect_factory,
            fatigue_estimator_factory=fatigue_factory,
            emotion_tracker=emotion_tracker or EmotionTemporalTracker(),
            engagement_tracker=EngagementTemporalTracker(engagement_config),
            fatigue_tracker=FatigueTemporalTracker(),
            store=store,
            on_snapshot=on_snapshot,
            clock=clock,
            empty_wait_seconds=0.005,
        )
        self.addCleanup(worker.stop)
        return worker, media_queue, store, clock

    def test_only_newest_queued_crop_updates_all_modalities(self):
        affect = RecordingAffectEstimator()
        fatigue = RecordingFatigueEstimator(0.82)
        worker, media_queue, store, _ = self.build_worker(
            lambda: affect,
            lambda: fatigue,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
        )
        media_queue.push(face_packet(1))
        media_queue.push(face_packet(9))

        worker.start()

        self.assertTrue(self._wait_until(lambda: store.snapshot().fatigue.status == "ready"))
        self.assertEqual(len(affect.images), 1)
        self.assertEqual(affect.images[0][0, 0, 0], 9)
        snapshot = store.snapshot()
        self.assertEqual(snapshot.emotion.status, "ready")
        self.assertEqual(snapshot.engagement.status, "ready")
        self.assertEqual(snapshot.fatigue.raw_probability, 0.82)

    def test_start_stop_is_idempotent_and_retains_both_estimators(self):
        affects = []
        fatigues = []

        def affect_factory():
            affects.append(RecordingAffectEstimator())
            return affects[-1]

        def fatigue_factory():
            fatigues.append(RecordingFatigueEstimator())
            return fatigues[-1]

        worker, media_queue, store, _ = self.build_worker(
            affect_factory,
            fatigue_factory,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
        )
        worker.start()
        worker.start()
        media_queue.push(face_packet(1))
        self.assertTrue(self._wait_until(lambda: store.snapshot().emotion.status == "ready"))
        worker.stop()
        worker.stop()
        self.assertEqual(store.snapshot().emotion.status, "waiting")

        worker.start()
        media_queue.push(face_packet(2))
        self.assertTrue(self._wait_until(lambda: store.snapshot().emotion.status == "ready"))

        self.assertEqual(len(affects), 1)
        self.assertEqual(len(fatigues), 1)

    def test_affect_runs_each_crop_while_fatigue_is_capped_at_half_second(self):
        affect = RecordingAffectEstimator()
        fatigue = RecordingFatigueEstimator()
        worker, media_queue, _, clock = self.build_worker(
            lambda: affect,
            lambda: fatigue,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
        )
        worker.start()
        media_queue.push(face_packet(1))
        self.assertTrue(self._wait_until(lambda: len(affect.images) == 1))
        clock.value = 10.25
        media_queue.push(face_packet(2))
        self.assertTrue(self._wait_until(lambda: len(affect.images) == 2))
        clock.value = 10.5
        media_queue.push(face_packet(3))
        self.assertTrue(self._wait_until(lambda: len(affect.images) == 3))

        self.assertEqual(len(fatigue.images), 2)

    def test_engagement_head_runs_only_at_tracker_window_and_stride(self):
        affect = RecordingAffectEstimator()
        worker, media_queue, _, clock = self.build_worker(
            lambda: affect,
            RecordingFatigueEstimator,
            engagement_config=EngagementTemporalConfig(window_frames=2, stride_frames=2),
        )
        worker.start()
        for index in range(4):
            clock.value = 10.0 + index * 0.25
            media_queue.push(face_packet(index + 1))
            self.assertTrue(self._wait_until(lambda: len(affect.images) == index + 1))

        self.assertEqual(len(affect.engagement_calls), 2)

    def test_affect_failure_does_not_stop_fatigue_or_worker(self):
        class RecoveringAffect(RecordingAffectEstimator):
            def infer_frame(self, image):
                if not self.images:
                    self.images.append(image.copy())
                    raise RuntimeError("emotion failed")
                return super().infer_frame(image)

        affect = RecoveringAffect()
        worker, media_queue, store, clock = self.build_worker(
            lambda: affect,
            RecordingFatigueEstimator,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
        )
        worker.start()
        media_queue.push(face_packet(1))
        self.assertTrue(
            self._wait_until(
                lambda: store.snapshot().emotion.status == "unavailable"
                and store.snapshot().fatigue.status == "ready"
            )
        )
        self.assertEqual(store.snapshot().engagement.status, "unavailable")
        self.assertTrue(worker.is_running)
        clock.value = 10.5
        media_queue.push(face_packet(2))
        self.assertTrue(self._wait_until(lambda: store.snapshot().emotion.status == "ready"))

    def test_engagement_failure_does_not_hide_emotion_or_fatigue(self):
        class RecoveringEngagement(RecordingAffectEstimator):
            def infer_engagement(self, features):
                self.engagement_calls.append(features.copy())
                if len(self.engagement_calls) == 1:
                    raise RuntimeError("head failed")
                return self.engagement

        affect = RecoveringEngagement()
        worker, media_queue, store, clock = self.build_worker(
            lambda: affect,
            RecordingFatigueEstimator,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
        )
        worker.start()
        media_queue.push(face_packet(1))
        self.assertTrue(
            self._wait_until(lambda: store.snapshot().engagement.status == "unavailable")
        )
        snapshot = store.snapshot()
        self.assertEqual(snapshot.emotion.status, "ready")
        self.assertEqual(snapshot.fatigue.status, "ready")
        clock.value = 10.25
        media_queue.push(face_packet(2))
        self.assertTrue(
            self._wait_until(lambda: store.snapshot().engagement.status == "ready")
        )

    def test_emotion_tracker_failure_does_not_hide_engagement_or_fatigue(self):
        class FailingEmotionTracker(EmotionTemporalTracker):
            def update(self, probabilities, now):
                raise RuntimeError("emotion tracker failed")

        worker, media_queue, store, _ = self.build_worker(
            RecordingAffectEstimator,
            RecordingFatigueEstimator,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
            emotion_tracker=FailingEmotionTracker(),
        )
        worker.start()
        media_queue.push(face_packet(1))

        self.assertTrue(
            self._wait_until(lambda: store.snapshot().emotion.status == "unavailable")
        )
        snapshot = store.snapshot()
        self.assertEqual(snapshot.engagement.status, "ready")
        self.assertEqual(snapshot.fatigue.status, "ready")
        self.assertTrue(worker.is_running)

    def test_fatigue_failure_does_not_hide_affect(self):
        class RecoveringFatigue(RecordingFatigueEstimator):
            def predict(self, image):
                self.images.append(image.copy())
                if len(self.images) == 1:
                    raise RuntimeError("fatigue failed")
                return self.probability

        fatigue = RecoveringFatigue()
        worker, media_queue, store, clock = self.build_worker(
            RecordingAffectEstimator,
            lambda: fatigue,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
        )
        worker.start()
        media_queue.push(face_packet(1))
        self.assertTrue(self._wait_until(lambda: store.snapshot().fatigue.status == "unavailable"))
        self.assertEqual(store.snapshot().emotion.status, "ready")
        self.assertEqual(store.snapshot().engagement.status, "ready")
        self.assertTrue(worker.is_running)
        clock.value = 10.5
        media_queue.push(face_packet(2))
        self.assertTrue(self._wait_until(lambda: store.snapshot().fatigue.status == "ready"))

    def test_context_is_captured_before_blocked_inference(self):
        entered = threading.Event()
        release = threading.Event()
        callbacks = []

        class BlockingAffect(RecordingAffectEstimator):
            def infer_frame(self, image):
                entered.set()
                release.wait(1.0)
                return super().infer_frame(image)

        worker, media_queue, _, _ = self.build_worker(
            BlockingAffect,
            RecordingFatigueEstimator,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
            on_snapshot=lambda *args: callbacks.append(args),
        )
        worker.set_context("deck-a", 1)
        worker.start()
        media_queue.push(face_packet(1))
        self.assertTrue(entered.wait(1.0))
        worker.set_context("deck-a", 2)
        release.set()

        self.assertTrue(self._wait_until(lambda: len(callbacks) == 1))
        self.assertEqual(callbacks[0][:2], ("deck-a", 1))

    def test_dismiss_updates_live_store_without_review_callback(self):
        callbacks = []
        affect = RecordingAffectEstimator(engagement=(0.8, 0.2))
        worker, media_queue, store, clock = self.build_worker(
            lambda: affect,
            RecordingFatigueEstimator,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
            on_snapshot=lambda *args: callbacks.append(args),
        )
        worker.set_context("deck-a", 1)
        worker.start()
        for index in range(2):
            clock.value = 10.0 + index * 0.25
            media_queue.push(face_packet(index + 1))
            self.assertTrue(self._wait_until(lambda: len(callbacks) == index + 1))
        self.assertTrue(store.snapshot().engagement.alert_active)

        worker.dismiss_distraction()

        engagement = store.snapshot().engagement
        self.assertTrue(engagement.alert_active)
        self.assertTrue(engagement.reminder_suppressed)
        self.assertEqual(len(callbacks), 2)

    def test_stop_clears_live_state_and_joins_thread(self):
        worker, media_queue, store, _ = self.build_worker(
            RecordingAffectEstimator,
            RecordingFatigueEstimator,
            engagement_config=EngagementTemporalConfig(window_frames=1, stride_frames=1),
        )
        worker.start()
        media_queue.push(face_packet(1))
        self.assertTrue(self._wait_until(lambda: store.snapshot().emotion.status == "ready"))

        worker.stop()

        self.assertFalse(worker.is_running)
        self.assertEqual(store.snapshot().emotion.status, "waiting")
        self.assertEqual(store.snapshot().engagement.status, "waiting")
        self.assertEqual(store.snapshot().fatigue.status, "waiting")

    @staticmethod
    def _wait_until(predicate, timeout=1.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return predicate()
