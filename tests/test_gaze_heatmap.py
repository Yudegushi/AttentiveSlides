import unittest

from modules.attention.gaze_heatmap import (
    GazeHeatmapAccumulator,
    GazeReviewSession,
)
from modules.common.schemas import AOI
from modules.media.browser_gaze_source import (
    BrowserGeometrySnapshot,
    BrowserPointGazeSample,
)
from modules.system.slide_geometry import SlideViewportGeometry, ViewportBBox


def make_sample(
    *,
    x=250.0,
    y=200.0,
    received_at=1.0,
    slide_id=1,
    revision=1,
    valid=True,
    face_detected=True,
):
    slide_rect = ViewportBBox(100.0, 100.0, 900.0, 550.0)
    geometry = SlideViewportGeometry(
        deck_id="deck-a",
        slide_id=slide_id,
        layout_revision=revision,
        received_at=received_at,
        viewport_width=1000.0,
        viewport_height=700.0,
        device_pixel_ratio=1.0,
        slide_rect=slide_rect,
        aoi_rects={
            "definition": ViewportBBox(140.0, 140.0, 420.0, 330.0),
            "diagram": ViewportBBox(500.0, 140.0, 850.0, 480.0),
        },
    )
    snapshot = BrowserGeometrySnapshot(
        browser_timestamp_ms=received_at * 1000.0,
        received_at=received_at,
        geometry=geometry,
    )
    return BrowserPointGazeSample(
        sequence=round(received_at * 10),
        browser_timestamp_ms=received_at * 1000.0,
        received_at=received_at,
        x_css=x,
        y_css=y,
        viewport_width=1000.0,
        viewport_height=700.0,
        valid=valid,
        face_detected=face_detected,
        source="eyetheia_local",
        geometry=snapshot,
    )


AOIS = (
    AOI("definition", [0.05, 0.08, 0.40, 0.52], "text", "Definition", "Definition"),
    AOI("diagram", [0.50, 0.08, 0.94, 0.84], "figure", "Diagram", "Diagram"),
    AOI("footer", [0.0, 0.92, 1.0, 1.0], "footer", "Footer", "Footer"),
)


class GazeHeatmapAccumulatorTest(unittest.TestCase):
    def make_accumulator(self):
        accumulator = GazeHeatmapAccumulator(
            session_id="session-1",
            deck_id="deck-a",
            started_at_epoch=100.0,
        )
        accumulator.register_slide("deck-a", 1, AOIS)
        accumulator.register_slide("deck-a", 2, AOIS)
        return accumulator

    def test_valid_dwell_updates_grid_and_one_aoi(self):
        accumulator = self.make_accumulator()
        accumulator.accept(make_sample(received_at=1.0))
        accumulator.accept(make_sample(received_at=1.2))

        review = accumulator.finish(ended_received_at=1.2, ended_at_epoch=101.0)
        slide = review.slides[0]

        self.assertAlmostEqual(slide.observed_seconds, 0.2)
        self.assertAlmostEqual(slide.valid_gaze_seconds, 0.2)
        self.assertAlmostEqual(sum(slide.grid), 0.2)
        dwell = {item.aoi_id: item.dwell_seconds for item in slide.aoi_dwell}
        self.assertAlmostEqual(dwell["definition"], 0.2)
        self.assertEqual(dwell["diagram"], 0.0)

    def test_one_sample_contribution_is_capped_at_half_second(self):
        accumulator = self.make_accumulator()
        accumulator.accept(make_sample(received_at=1.0))
        accumulator.accept(make_sample(received_at=5.0))

        slide = accumulator.finish(
            ended_received_at=5.0,
            ended_at_epoch=105.0,
        ).slides[0]

        self.assertEqual(slide.observed_seconds, 0.5)
        self.assertEqual(slide.valid_gaze_seconds, 0.5)

    def test_invalid_and_off_slide_samples_reduce_coverage(self):
        accumulator = self.make_accumulator()
        accumulator.accept(make_sample(received_at=1.0, valid=False))
        accumulator.accept(make_sample(received_at=1.2, x=950.0, y=650.0))
        accumulator.accept(make_sample(received_at=1.4))

        slide = accumulator.finish(
            ended_received_at=1.4,
            ended_at_epoch=101.0,
        ).slides[0]

        self.assertAlmostEqual(slide.observed_seconds, 0.4)
        self.assertEqual(slide.valid_gaze_seconds, 0.0)
        self.assertEqual(slide.coverage, 0.0)

    def test_slide_and_layout_changes_break_continuity(self):
        accumulator = self.make_accumulator()
        accumulator.accept(make_sample(received_at=1.0, slide_id=1, revision=1))
        accumulator.accept(make_sample(received_at=1.2, slide_id=2, revision=1))
        accumulator.accept(make_sample(received_at=1.4, slide_id=2, revision=2))
        accumulator.accept(make_sample(received_at=1.6, slide_id=2, revision=2))

        review = accumulator.finish(ended_received_at=1.6, ended_at_epoch=101.0)
        slides = {slide.slide_id: slide for slide in review.slides}

        self.assertEqual(slides[1].observed_seconds, 0.0)
        self.assertAlmostEqual(slides[2].observed_seconds, 0.2)

    def test_pause_prevents_dwell_across_transport_gap(self):
        accumulator = self.make_accumulator()
        accumulator.accept(make_sample(received_at=1.0))
        accumulator.pause()
        accumulator.accept(make_sample(received_at=9.0))
        accumulator.accept(make_sample(received_at=9.2))

        slide = accumulator.finish(
            ended_received_at=9.2,
            ended_at_epoch=109.0,
        ).slides[0]

        self.assertAlmostEqual(slide.valid_gaze_seconds, 0.2)

    def test_snapshot_round_trip_keeps_grid_and_reading_order(self):
        accumulator = self.make_accumulator()
        accumulator.accept(make_sample(received_at=1.0))
        accumulator.accept(make_sample(received_at=1.2))
        original = accumulator.finish(ended_received_at=1.2, ended_at_epoch=101.0)

        restored = type(original).from_dict(original.to_dict())

        self.assertEqual(restored.to_dict(), original.to_dict())
        self.assertEqual(
            [item.aoi_id for item in restored.slides[0].aoi_dwell],
            ["definition", "diagram"],
        )

    def test_snapshot_rejects_negative_grid_values(self):
        accumulator = self.make_accumulator()
        accumulator.accept(make_sample(received_at=1.0))
        accumulator.accept(make_sample(received_at=1.2))
        payload = accumulator.finish(
            ended_received_at=1.2,
            ended_at_epoch=101.0,
        ).to_dict()
        payload["slides"][0]["grid"][0] = -1.0

        with self.assertRaisesRegex(ValueError, "grid values"):
            GazeReviewSession.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
