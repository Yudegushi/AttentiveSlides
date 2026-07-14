import unittest

from modules.common.schemas import AOI, GazePrediction, LearningState
from modules.media.browser_gaze_source import BrowserGazeSource
from modules.system.adapters import SensingFrame, SlideFrame
from modules.system.sensing_snapshot_store import SensingSnapshot, SensingSnapshotStore
from modules.system.turn_context import TurnContextCollector


class FakeSlideProvider:
    deck_id = "deck-live"

    def get_slide_frame(self, slide_id):
        return SlideFrame(
            deck_id=self.deck_id,
            slide_id=slide_id,
            slide_text="Current concept",
            neighbor_slide_text="Neighbor concept",
            aois=[
                AOI("alpha", [0.1, 0.1, 0.4, 0.4], "text", text="Alpha"),
                AOI("beta", [0.5, 0.1, 0.8, 0.4], "figure", text="Beta"),
                AOI("whole_slide", [0, 0, 1, 1], "whole_slide"),
            ],
        )


def frame(
    slide_id,
    target,
    confidence=0.8,
    grid="middle_center",
    learning_state=None,
):
    return SensingFrame(
        gaze_prediction=GazePrediction(
            slide_id=slide_id,
            gaze_grid=grid,
            predicted_aoi_id=target,
            confidence=confidence,
            stable_duration_sec=0.2,
        ),
        learning_state=learning_state or LearningState(),
    )


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


def geometry_payload():
    return {
        "deck_id": "deck-live",
        "slide_id": 2,
        "layout_revision": 9,
        "browser_timestamp_ms": 1000.0,
        "viewport_width": 1000,
        "viewport_height": 800,
        "device_pixel_ratio": 1,
        "slide_rect": {"x1": 0, "y1": 0, "x2": 1000, "y2": 800},
        "aoi_rects": {
            "alpha": {"x1": 100, "y1": 100, "x2": 400, "y2": 400},
            "beta": {"x1": 500, "y1": 100, "x2": 800, "y2": 400},
        },
    }


def point_payload(sequence=1, x=200.0):
    return {
        "sequence": sequence,
        "browser_timestamp_ms": 1200.0 + sequence,
        "x_css": x,
        "y_css": 200.0,
        "viewport_width": 1000,
        "viewport_height": 800,
        "valid": True,
        "face_detected": True,
        "source": "eyetheia_local",
    }


class TurnContextCollectorTest(unittest.TestCase):
    def setUp(self):
        self.store = SensingSnapshotStore(stale_after_seconds=5.0)
        self.collector = TurnContextCollector(
            slide_provider=FakeSlideProvider(),
            snapshot_store=self.store,
            minimum_dwell_seconds=0.15,
            max_sample_dwell_seconds=0.5,
        )

    def snapshot(
        self,
        context,
        processed_at,
        target,
        confidence=0.8,
        *,
        grid="middle_center",
        valid=True,
        manifest=True,
        learning_state=None,
    ):
        self.store.put(
            SensingSnapshot(
                slide_id=context.slide_id,
                source_timestamp=processed_at,
                source_timestamp_clock="browser_performance_seconds",
                processed_at=processed_at,
                frame=frame(
                    context.slide_id,
                    target,
                    confidence,
                    grid=grid,
                    learning_state=learning_state,
                ),
                is_valid=valid,
                invalid_reason=None if valid else "no_face",
                manifest_identity=context.manifest_identity if manifest else None,
            )
        )

    def test_freezes_start_time_slide_and_manifest_then_records_slide_change_at_end(self):
        context = self.collector.freeze_start(slide_id=2, speech_started_at=10.0)
        ended = self.collector.freeze_end(context, speech_ended_at=11.0, current_slide_id=3)

        self.assertEqual(context.deck_id, "deck-live")
        self.assertEqual(context.slide_id, 2)
        self.assertAlmostEqual(context.sensing_window_start, 9.5)
        self.assertTrue(context.manifest_identity)
        self.assertTrue(ended.slide_changed_during_turn)
        self.assertEqual(ended.speech_ended_at, 11.0)

    def test_aggregates_confidence_times_dwell_with_deterministic_top_two(self):
        context = self.collector.freeze_end(
            self.collector.freeze_start(slide_id=2, speech_started_at=10.0),
            speech_ended_at=10.8,
            current_slide_id=2,
        )
        self.snapshot(context, 9.9, "alpha", 0.9)
        self.snapshot(context, 10.3, "alpha", 0.9)
        self.snapshot(context, 10.5, "beta", 0.6)

        aggregated = self.collector.aggregate(context)

        self.assertEqual(aggregated.frame.gaze_prediction.predicted_aoi_id, "alpha")
        self.assertGreater(aggregated.frame.gaze_prediction.confidence, 0.7)
        self.assertEqual(
            [item["aoi_id"] for item in aggregated.frame.gaze_prediction.alternative_targets],
            ["alpha", "beta"],
        )
        self.assertIn("dwell", aggregated.evidence[0])

    def test_tied_scores_are_stable_and_invalid_or_legacy_snapshots_downgrade_to_no_target(self):
        context = self.collector.freeze_end(
            self.collector.freeze_start(slide_id=2, speech_started_at=10.0),
            speech_ended_at=10.6,
            current_slide_id=2,
        )
        self.snapshot(context, 10.0, "beta", 0.8)
        self.snapshot(context, 10.3, "alpha", 0.8)

        ambiguous = self.collector.aggregate(context)
        self.assertEqual(ambiguous.frame.gaze_prediction.predicted_aoi_id, "alpha")
        self.assertEqual(ambiguous.frame.gaze_prediction.confidence, 0.5)

        empty_context = self.collector.freeze_end(
            self.collector.freeze_start(slide_id=2, speech_started_at=20.0),
            speech_ended_at=20.2,
            current_slide_id=2,
        )
        self.snapshot(empty_context, 20.0, "alpha", valid=False)
        self.snapshot(empty_context, 20.1, "beta", manifest=False)

        downgraded = self.collector.aggregate(empty_context)
        self.assertIsNone(downgraded.frame.gaze_prediction.predicted_aoi_id)
        self.assertEqual(downgraded.frame.gaze_prediction.confidence, 0.0)

    def test_grid_aggregation_returns_dwell_winner_without_aoi(self):
        collector = TurnContextCollector(
            slide_provider=FakeSlideProvider(),
            snapshot_store=self.store,
            aggregation_key="gaze_grid",
            minimum_dwell_seconds=0.15,
            max_sample_dwell_seconds=0.5,
        )
        context = collector.freeze_end(
            collector.freeze_start(slide_id=2, speech_started_at=10.0),
            speech_ended_at=10.8,
            current_slide_id=2,
        )
        self.snapshot(
            context,
            10.0,
            "temporary-grid-key",
            0.9,
            grid="middle_left",
        )
        self.snapshot(
            context,
            10.5,
            "temporary-grid-key",
            0.6,
            grid="middle_right",
        )

        gaze = collector.aggregate(context).frame.gaze_prediction

        self.assertEqual(gaze.gaze_grid, "middle_left")
        self.assertIsNone(gaze.predicted_aoi_id)
        self.assertGreater(gaze.confidence, 0.5)

    def test_local_point_dwell_wins_and_keeps_latest_cloud_learning_state(self):
        clock = FakeClock(10.0)
        observations = BrowserGazeSource(clock=clock)
        observations.accept_geometry(geometry_payload())
        observations.accept_gaze(point_payload(sequence=1, x=200))
        clock.value = 10.3
        observations.accept_gaze(point_payload(sequence=2, x=200))
        collector = TurnContextCollector(
            slide_provider=FakeSlideProvider(),
            snapshot_store=self.store,
            browser_gaze_source=observations,
            aggregation_key="gaze_grid",
        )
        context = collector.freeze_end(
            collector.freeze_start(slide_id=2, speech_started_at=10.0),
            speech_ended_at=10.5,
            current_slide_id=2,
        )
        learning = LearningState(head_down=True, fatigue_signal_score=0.7)
        self.snapshot(
            context,
            10.1,
            "temporary-grid-key",
            grid="middle_right",
            learning_state=learning,
        )

        aggregated = collector.aggregate(context)

        self.assertEqual(aggregated.gaze_source, "eyetheia_local")
        self.assertEqual(aggregated.layout_revision, 9)
        self.assertEqual(
            aggregated.frame.gaze_prediction.predicted_aoi_id,
            "alpha",
        )
        self.assertEqual(aggregated.frame.gaze_prediction.gaze_grid, "point")
        self.assertEqual(aggregated.frame.learning_state, learning)

    def test_insufficient_point_evidence_preserves_exact_grid_result(self):
        clock = FakeClock(10.45)
        observations = BrowserGazeSource(clock=clock)
        observations.accept_geometry(geometry_payload())
        observations.accept_gaze(point_payload())
        point_collector = TurnContextCollector(
            slide_provider=FakeSlideProvider(),
            snapshot_store=self.store,
            browser_gaze_source=observations,
            aggregation_key="gaze_grid",
        )
        grid_collector = TurnContextCollector(
            slide_provider=FakeSlideProvider(),
            snapshot_store=self.store,
            aggregation_key="gaze_grid",
        )
        context = point_collector.freeze_end(
            point_collector.freeze_start(slide_id=2, speech_started_at=10.0),
            speech_ended_at=10.5,
            current_slide_id=2,
        )
        self.snapshot(
            context,
            10.0,
            "temporary-grid-key",
            confidence=0.9,
            grid="middle_left",
        )

        fallback = point_collector.aggregate(context)
        expected = grid_collector.aggregate(context)

        self.assertEqual(fallback.gaze_source, "cloud_grid")
        self.assertEqual(fallback, expected)

    def test_stale_point_evidence_preserves_exact_grid_result(self):
        clock = FakeClock(10.0)
        observations = BrowserGazeSource(
            clock=clock,
            gaze_stale_after_seconds=0.1,
        )
        observations.accept_geometry(geometry_payload())
        observations.accept_gaze(point_payload(sequence=1, x=200))
        point_collector = TurnContextCollector(
            slide_provider=FakeSlideProvider(),
            snapshot_store=self.store,
            browser_gaze_source=observations,
            sensing_lookback_seconds=1.0,
            aggregation_key="gaze_grid",
        )
        context = point_collector.freeze_end(
            point_collector.freeze_start(slide_id=2, speech_started_at=10.0),
            speech_ended_at=10.5,
            current_slide_id=2,
        )
        self.snapshot(
            context,
            10.0,
            "temporary-grid-key",
            confidence=0.9,
            grid="middle_right",
        )

        aggregated = point_collector.aggregate(context)

        self.assertEqual(aggregated.gaze_source, "cloud_grid")
        self.assertEqual(aggregated.frame.gaze_prediction.gaze_grid, "middle_right")


if __name__ == "__main__":
    unittest.main()
