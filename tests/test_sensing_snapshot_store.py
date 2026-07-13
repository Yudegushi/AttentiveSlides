import unittest

from modules.common.schemas import GazePrediction, LearningState
from modules.system.adapters import SensingFrame

try:
    from modules.system.sensing_snapshot_store import SensingSnapshot, SensingSnapshotStore
except ImportError:
    SensingSnapshot = None
    SensingSnapshotStore = None


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def sensing_frame(slide_id: int, target: str = "target") -> SensingFrame:
    return SensingFrame(
        gaze_prediction=GazePrediction(
            slide_id=slide_id,
            gaze_grid="middle_center",
            predicted_aoi_id=target,
            confidence=0.76,
            stable_duration_sec=2.0,
        ),
        learning_state=LearningState(),
    )


class SensingSnapshotStoreTest(unittest.TestCase):
    def test_returns_latest_valid_snapshot_and_windowed_history(self):
        self.assertIsNotNone(SensingSnapshotStore)
        clock = FakeClock(10.0)
        store = SensingSnapshotStore(stale_after_seconds=1.0, clock=clock)
        first = SensingSnapshot(
            slide_id=2,
            source_timestamp=4.0,
            source_timestamp_clock="browser_performance_seconds",
            processed_at=9.2,
            frame=sensing_frame(2),
            is_valid=True,
            invalid_reason=None,
        )
        second = SensingSnapshot(
            slide_id=2,
            source_timestamp=4.2,
            source_timestamp_clock="browser_performance_seconds",
            processed_at=9.8,
            frame=sensing_frame(2, target="newer"),
            is_valid=True,
            invalid_reason=None,
        )
        store.put(first)
        store.put(second)

        latest = store.latest_valid_for_slide(2)

        self.assertEqual(latest, second)
        self.assertEqual(
            store.snapshots_in_window(2, start_processed_at=9.0, end_processed_at=10.0),
            [first, second],
        )
        self.assertEqual(store.get_sensing_frame(2), second.frame)

    def test_rejects_stale_invalid_and_slide_mismatched_snapshots(self):
        self.assertIsNotNone(SensingSnapshotStore)
        clock = FakeClock(10.0)
        store = SensingSnapshotStore(stale_after_seconds=1.0, clock=clock)
        store.put(
            SensingSnapshot(
                slide_id=2,
                source_timestamp=4.0,
                source_timestamp_clock="browser_performance_seconds",
                processed_at=8.9,
                frame=sensing_frame(2),
                is_valid=True,
                invalid_reason=None,
            )
        )
        store.put(
            SensingSnapshot(
                slide_id=3,
                source_timestamp=4.1,
                source_timestamp_clock="browser_performance_seconds",
                processed_at=9.9,
                frame=sensing_frame(3),
                is_valid=False,
                invalid_reason="no_face",
            )
        )

        self.assertIsNone(store.latest_valid_for_slide(2))
        self.assertIsNone(store.latest_valid_for_slide(3))
        self.assertIsNone(store.latest_valid_for_slide(4))
        with self.assertRaisesRegex(LookupError, "valid sensing snapshot"):
            store.get_sensing_frame(3)


if __name__ == "__main__":
    unittest.main()
