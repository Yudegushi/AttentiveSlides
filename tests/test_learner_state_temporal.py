import dataclasses
import math
import unittest

import numpy as np

from modules.fatigue import FatigueSnapshot
from modules.learner_state import (
    EMOTION_LABELS,
    EmotionSnapshot,
    EmotionTemporalConfig,
    EmotionTemporalTracker,
    EngagementSnapshot,
    EngagementTemporalConfig,
    EngagementTemporalTracker,
    LearnerStateSnapshot,
    LearnerStateStore,
)


def probabilities(index: int) -> tuple[float, ...]:
    values = [0.0] * 8
    values[index] = 1.0
    return tuple(values)


def feature(value: float = 0.0) -> np.ndarray:
    return np.full((1280,), value, dtype=np.float32)


class LearnerStateContractTest(unittest.TestCase):
    def test_defaults_are_immutable_waiting_snapshots(self):
        snapshot = LearnerStateSnapshot()

        self.assertEqual(snapshot.emotion.status, "waiting")
        self.assertEqual(snapshot.engagement.status, "waiting")
        self.assertEqual(snapshot.fatigue.status, "waiting")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.updated_at = 1.0

    def test_probability_contracts_reject_invalid_values(self):
        with self.assertRaises(ValueError):
            EmotionSnapshot(
                status="ready",
                probabilities=(0.2,) * 8,
                top_label="Neutral",
                top_probability=0.2,
            )
        with self.assertRaises(ValueError):
            EngagementSnapshot(
                status="ready",
                distracted_probability=0.8,
                engaged_probability=0.3,
                buffered_frames=128,
            )
        with self.assertRaises(ValueError):
            EngagementSnapshot(status="warming", reminder_suppressed=True)

    def test_one_unavailable_modality_does_not_hide_ready_modalities(self):
        emotion = EmotionSnapshot(status="unavailable", error="missing")
        engagement = EngagementSnapshot(
            status="ready",
            distracted_probability=0.2,
            engaged_probability=0.8,
            buffered_frames=128,
            updated_at=10.0,
        )
        fatigue = FatigueSnapshot(
            status="ready", raw_probability=0.1, smoothed_probability=0.2, updated_at=10.0
        )
        snapshot = LearnerStateSnapshot(emotion, engagement, fatigue, 10.0)

        self.assertEqual(snapshot.emotion.status, "unavailable")
        self.assertEqual(snapshot.engagement.status, "ready")
        self.assertEqual(snapshot.fatigue.status, "ready")


class EmotionTemporalTrackerTest(unittest.TestCase):
    def test_ema_smooths_all_classes_and_selects_top(self):
        tracker = EmotionTemporalTracker(
            EmotionTemporalConfig(ema_time_constant_seconds=2.0)
        )
        tracker.update(probabilities(0), 0.0)

        snapshot = tracker.update(probabilities(5), 2.0)

        alpha = 1.0 - math.exp(-1.0)
        self.assertAlmostEqual(snapshot.probabilities[0], 1.0 - alpha)
        self.assertAlmostEqual(snapshot.probabilities[5], alpha)
        self.assertEqual(snapshot.top_label, EMOTION_LABELS[5])
        self.assertAlmostEqual(snapshot.top_probability, alpha)

    def test_non_monotonic_timestamp_is_rejected(self):
        tracker = EmotionTemporalTracker()
        tracker.update(probabilities(0), 2.0)
        with self.assertRaisesRegex(ValueError, "monotonic"):
            tracker.update(probabilities(0), 1.0)


class EngagementTemporalTrackerTest(unittest.TestCase):
    def test_warms_through_128_and_infers_at_128_144_160(self):
        tracker = EngagementTemporalTracker()
        calls = []

        def infer(window):
            calls.append(window.copy())
            return (0.2, 0.8)

        for index in range(127):
            snapshot = tracker.add(feature(index), index * 0.25, infer)
            self.assertEqual(snapshot.status, "warming")
            self.assertEqual(snapshot.buffered_frames, index + 1)
        snapshot = tracker.add(feature(127), 127 * 0.25, infer)
        self.assertEqual(snapshot.status, "ready")
        self.assertEqual(len(calls), 1)
        for index in range(128, 143):
            tracker.add(feature(index), index * 0.25, infer)
        self.assertEqual(len(calls), 1)
        tracker.add(feature(143), 143 * 0.25, infer)
        self.assertEqual(len(calls), 2)
        for index in range(144, 159):
            tracker.add(feature(index), index * 0.25, infer)
        tracker.add(feature(159), 159 * 0.25, infer)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call.shape == (128, 1280) for call in calls))

    def test_alert_hysteresis_and_dismissal_keep_objective_state(self):
        tracker = EngagementTemporalTracker(
            EngagementTemporalConfig(window_frames=1, stride_frames=1)
        )
        outputs = iter(((0.8, 0.2), (0.8, 0.2), (0.4, 0.6), (0.4, 0.6)))
        infer = lambda _: next(outputs)

        self.assertFalse(tracker.add(feature(), 0.0, infer).alert_active)
        entered = tracker.add(feature(), 0.25, infer)
        self.assertTrue(entered.alert_active)
        dismissed = tracker.dismiss()
        self.assertTrue(dismissed.alert_active)
        self.assertTrue(dismissed.reminder_suppressed)
        first_exit = tracker.add(feature(), 0.5, infer)
        self.assertTrue(first_exit.alert_active)
        self.assertTrue(first_exit.reminder_suppressed)
        recovered = tracker.add(feature(), 0.75, infer)
        self.assertFalse(recovered.alert_active)
        self.assertFalse(recovered.reminder_suppressed)

    def test_gap_over_two_seconds_clears_window_and_alert_continuity(self):
        tracker = EngagementTemporalTracker(
            EngagementTemporalConfig(window_frames=2, stride_frames=1)
        )
        infer = lambda _: (0.2, 0.8)
        tracker.add(feature(), 0.0, infer)
        self.assertEqual(tracker.add(feature(), 0.25, infer).status, "ready")

        snapshot = tracker.add(feature(), 2.5, infer)

        self.assertEqual(snapshot.status, "warming")
        self.assertEqual(snapshot.buffered_frames, 1)

    def test_feature_and_timestamp_validation(self):
        tracker = EngagementTemporalTracker(
            EngagementTemporalConfig(window_frames=2, stride_frames=1)
        )
        tracker.add(feature(), 1.0, lambda _: (0.2, 0.8))
        with self.assertRaisesRegex(ValueError, "monotonic"):
            tracker.add(feature(), 0.5, lambda _: (0.2, 0.8))
        with self.assertRaisesRegex(ValueError, "1280"):
            tracker.add(np.zeros((1279,), dtype=np.float32), 1.5, lambda _: (0.2, 0.8))


class LearnerStateStoreTest(unittest.TestCase):
    def test_stale_presentation_preserves_values_but_disables_alerts(self):
        emotion = EmotionSnapshot(
            status="ready",
            probabilities=probabilities(5),
            top_label="Neutral",
            top_probability=1.0,
            updated_at=10.0,
        )
        engagement = EngagementSnapshot(
            status="ready",
            distracted_probability=0.8,
            engaged_probability=0.2,
            alert_active=True,
            reminder_suppressed=True,
            buffered_frames=128,
            updated_at=10.0,
        )
        fatigue = FatigueSnapshot(
            status="ready",
            raw_probability=0.9,
            smoothed_probability=0.8,
            alert_active=True,
            updated_at=10.0,
        )
        store = LearnerStateStore()
        store.publish(LearnerStateSnapshot(emotion, engagement, fatigue, 10.0))

        stale = store.snapshot(now=12.1)
        original = store.snapshot(now=10.0)

        self.assertEqual(stale.emotion.status, "stale")
        self.assertEqual(stale.emotion.top_label, "Neutral")
        self.assertEqual(stale.engagement.status, "stale")
        self.assertEqual(stale.engagement.engaged_probability, 0.2)
        self.assertFalse(stale.engagement.alert_active)
        self.assertFalse(stale.engagement.reminder_suppressed)
        self.assertEqual(stale.fatigue.status, "stale")
        self.assertEqual(stale.fatigue.smoothed_probability, 0.8)
        self.assertFalse(stale.fatigue.alert_active)
        self.assertEqual(original.engagement.status, "ready")
        self.assertTrue(original.engagement.alert_active)


if __name__ == "__main__":
    unittest.main()
