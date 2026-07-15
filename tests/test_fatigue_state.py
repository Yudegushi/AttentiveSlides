import unittest

from modules.fatigue import (
    FatigueSnapshot,
    FatigueStateStore,
    FatigueTemporalConfig,
    FatigueTemporalTracker,
)


class FatigueTemporalTrackerTest(unittest.TestCase):
    def test_first_sample_initializes_raw_and_smoothed_probability(self):
        snapshot = FatigueTemporalTracker().update(0.62, 10.0)

        self.assertEqual(snapshot.status, "ready")
        self.assertEqual(snapshot.raw_probability, 0.62)
        self.assertEqual(snapshot.smoothed_probability, 0.62)
        self.assertFalse(snapshot.alert_active)
        self.assertEqual(snapshot.updated_at, 10.0)

    def test_high_probability_requires_three_continuous_seconds(self):
        tracker = FatigueTemporalTracker()

        self.assertFalse(tracker.update(1.0, 0.0).alert_active)
        self.assertFalse(tracker.update(1.0, 1.0).alert_active)
        self.assertFalse(tracker.update(1.0, 2.99).alert_active)
        self.assertTrue(tracker.update(1.0, 3.0).alert_active)

    def test_hysteresis_band_preserves_an_active_alert(self):
        tracker = FatigueTemporalTracker()
        tracker.update(1.0, 0.0)
        tracker.update(1.0, 1.0)
        tracker.update(1.0, 3.0)

        snapshot = tracker.update(0.60, 3.5)

        self.assertTrue(snapshot.alert_active)

    def test_low_probability_requires_five_continuous_seconds(self):
        tracker = FatigueTemporalTracker()
        tracker.update(1.0, 0.0)
        tracker.update(1.0, 1.0)
        tracker.update(1.0, 3.0)

        self.assertTrue(tracker.update(0.0, 4.0).alert_active)
        for now in (5.0, 6.0, 7.0, 8.0, 9.0):
            self.assertTrue(tracker.update(0.0, now).alert_active)
        self.assertTrue(tracker.update(0.0, 9.99).alert_active)
        self.assertFalse(tracker.update(0.0, 10.0).alert_active)

    def test_gap_over_stale_timeout_resets_ema_and_gates(self):
        tracker = FatigueTemporalTracker()
        tracker.update(1.0, 0.0)
        tracker.update(1.0, 1.5)

        snapshot = tracker.update(0.2, 4.0)

        self.assertEqual(snapshot.smoothed_probability, 0.2)
        self.assertFalse(snapshot.alert_active)
        self.assertFalse(tracker.update(1.0, 6.0).alert_active)

    def test_invalid_probability_is_rejected(self):
        tracker = FatigueTemporalTracker()

        for value in (-0.01, 1.01, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tracker.update(value, 0.0)


class FatigueStateStoreTest(unittest.TestCase):
    def test_store_suppresses_stale_ready_alert(self):
        store = FatigueStateStore(clock=lambda: 12.1)
        store.publish(
            FatigueSnapshot(
                status="ready",
                raw_probability=0.9,
                smoothed_probability=0.8,
                alert_active=True,
                updated_at=10.0,
            )
        )

        snapshot = store.snapshot()

        self.assertEqual(snapshot.status, "waiting")
        self.assertIsNone(snapshot.smoothed_probability)
        self.assertFalse(snapshot.alert_active)

    def test_clear_restores_waiting_state(self):
        store = FatigueStateStore()
        store.publish(FatigueSnapshot(status="unavailable", error="missing model"))

        store.clear()

        self.assertEqual(store.snapshot().status, "waiting")

    def test_invalid_contracts_and_configurations_are_rejected(self):
        with self.assertRaises(ValueError):
            FatigueSnapshot(status="ready", raw_probability=1.1)
        with self.assertRaises(ValueError):
            FatigueSnapshot(status="waiting", alert_active=True)
        with self.assertRaises(ValueError):
            FatigueTemporalConfig(ema_time_constant_seconds=0.0)
        with self.assertRaises(ValueError):
            FatigueTemporalConfig(exit_threshold=0.8, enter_threshold=0.7)
        with self.assertRaises(ValueError):
            FatigueStateStore(stale_after_seconds=0.0)


if __name__ == "__main__":
    unittest.main()
