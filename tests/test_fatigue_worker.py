import threading
import time
import unittest

import numpy as np

from modules.fatigue import FatigueStateStore, FatigueTemporalTracker
from modules.media import FaceCropPacket
from modules.media.queue_policy import BoundedMediaQueue
from modules.system.fatigue_worker import FatigueWorker


class FakeClock:
    def __init__(self, value=10.0):
        self.value = value

    def __call__(self):
        return self.value


class RecordingEstimator:
    def __init__(self, probability=0.8):
        self.probability = probability
        self.images = []
        self.called = threading.Event()

    def predict(self, image):
        self.images.append(image.copy())
        self.called.set()
        return self.probability


def face_packet(value, timestamp=1.0):
    return FaceCropPacket(
        np.full((224, 224, 3), value, dtype=np.uint8),
        timestamp=timestamp,
    )


class FatigueWorkerTest(unittest.TestCase):
    def build_worker(self, estimator_factory, *, queue_size=3):
        media_queue = BoundedMediaQueue(queue_size)
        clock = FakeClock()
        store = FatigueStateStore(clock=clock)
        tracker = FatigueTemporalTracker()
        worker = FatigueWorker(
            media_queue,
            estimator_factory=estimator_factory,
            tracker=tracker,
            store=store,
            clock=clock,
        )
        self.addCleanup(worker.stop)
        return worker, media_queue, store, clock

    def test_only_newest_queued_crop_is_classified_and_published(self):
        estimator = RecordingEstimator(probability=0.82)
        worker, media_queue, store, _ = self.build_worker(lambda: estimator)
        media_queue.push(face_packet(1, 1.0))
        media_queue.push(face_packet(9, 1.5))

        worker.start()

        self.assertTrue(estimator.called.wait(1.0))
        self.assertEqual(len(estimator.images), 1)
        self.assertEqual(estimator.images[0][0, 0, 0], 9)
        snapshot = store.snapshot()
        self.assertEqual(snapshot.raw_probability, 0.82)
        self.assertEqual(snapshot.status, "ready")

    def test_repeated_start_stop_is_idempotent_and_retains_estimator(self):
        estimators = []

        def factory():
            estimator = RecordingEstimator()
            estimators.append(estimator)
            return estimator

        worker, media_queue, store, _ = self.build_worker(factory)
        worker.start()
        worker.start()
        media_queue.push(face_packet(1))
        self.assertTrue(self._wait_until(lambda: store.snapshot().status == "ready"))
        worker.stop()
        worker.stop()
        self.assertEqual(store.snapshot().status, "waiting")

        worker.start()
        media_queue.push(face_packet(2))
        self.assertTrue(self._wait_until(lambda: store.snapshot().status == "ready"))

        self.assertEqual(len(estimators), 1)

    def test_model_initialization_error_marks_only_fatigue_unavailable(self):
        def explode():
            raise RuntimeError("missing model")

        worker, _, store, _ = self.build_worker(explode)

        worker.start()

        self.assertTrue(
            self._wait_until(
                lambda: store.snapshot().status == "unavailable"
                and not worker.is_running
            )
        )
        self.assertIn("missing model", worker.last_error)
        self.assertFalse(worker.is_running)

    def test_inference_error_marks_unavailable_and_stops_worker(self):
        class ExplodingEstimator:
            def predict(self, _image):
                raise RuntimeError("inference failed")

        worker, media_queue, store, _ = self.build_worker(ExplodingEstimator)
        media_queue.push(face_packet(1))

        worker.start()

        self.assertTrue(
            self._wait_until(
                lambda: store.snapshot().status == "unavailable"
                and not worker.is_running
            )
        )
        self.assertIn("inference failed", worker.last_error)
        self.assertFalse(worker.is_running)

    def test_stop_clears_fatigue_state(self):
        estimator = RecordingEstimator()
        worker, media_queue, store, _ = self.build_worker(lambda: estimator)
        media_queue.push(face_packet(1))
        worker.start()
        self.assertTrue(estimator.called.wait(1.0))

        worker.stop()

        self.assertEqual(store.snapshot().status, "waiting")
        self.assertFalse(store.snapshot().alert_active)

    @staticmethod
    def _wait_until(predicate, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()
