import unittest

from modules.common.schemas import AOI
from modules.media.browser_gaze_source import (
    BrowserGeometrySnapshot,
    BrowserPointGazeSample,
)
from modules.system.point_gaze import (
    aggregate_point_gaze,
    match_point_to_visible_aois,
)
from modules.system.slide_geometry import SlideViewportGeometry, ViewportBBox


def make_sample(
    *,
    x=150.0,
    y=150.0,
    received_at=1.0,
    revision=1,
    slide_rect=None,
    aoi_rects=None,
    valid=True,
    face_detected=True,
):
    geometry = SlideViewportGeometry(
        deck_id="deck-a",
        slide_id=1,
        layout_revision=revision,
        received_at=received_at,
        viewport_width=1000.0,
        viewport_height=800.0,
        device_pixel_ratio=1.0,
        slide_rect=slide_rect or ViewportBBox(0.0, 0.0, 1000.0, 800.0),
        aoi_rects=aoi_rects or {
            "alpha": ViewportBBox(100.0, 100.0, 300.0, 250.0),
        },
    )
    snapshot = BrowserGeometrySnapshot(
        browser_timestamp_ms=999999.0 - received_at,
        received_at=received_at,
        geometry=geometry,
    )
    return BrowserPointGazeSample(
        sequence=round(received_at * 100),
        browser_timestamp_ms=999999.0 - received_at,
        received_at=received_at,
        x_css=x,
        y_css=y,
        viewport_width=1000.0,
        viewport_height=800.0,
        valid=valid,
        face_detected=face_detected,
        source="eyetheia_local",
        geometry=snapshot,
    )


class PointGazeTest(unittest.TestCase):
    def test_exact_visible_aoi_hit_ranks_first(self):
        sample = make_sample(
            aoi_rects={
                "alpha": ViewportBBox(100, 100, 300, 250),
                "beta": ViewportBBox(170, 100, 370, 250),
            }
        )
        aois = (
            AOI("beta", [0, 0, 0.2, 0.2], "figure"),
            AOI("alpha", [0, 0, 0.2, 0.2], "text"),
        )

        candidates = match_point_to_visible_aois(sample, aois)

        self.assertEqual(candidates[0].aoi_id, "alpha")
        self.assertTrue(candidates[0].exact_hit)
        self.assertEqual(candidates[0].spatial_score, 1.0)

    def test_two_hundred_by_one_fifty_aoi_uses_fifty_by_thirty_five_tolerance(self):
        aois = (AOI("alpha", [0, 0, 0.2, 0.2], "text"),)

        outside_x = match_point_to_visible_aois(
            make_sample(x=351, y=150),
            aois,
        )
        outside_y = match_point_to_visible_aois(
            make_sample(x=150, y=286),
            aois,
        )

        self.assertEqual(outside_x, ())
        self.assertEqual(outside_y, ())

    def test_fully_offscreen_aoi_is_ignored(self):
        sample = make_sample(
            x=10,
            y=10,
            aoi_rects={"alpha": ViewportBBox(-200, 10, -50, 100)},
        )

        candidates = match_point_to_visible_aois(
            sample,
            (AOI("alpha", [0, 0, 0.2, 0.2], "text"),),
        )

        self.assertEqual(candidates, ())

    def test_partially_visible_aoi_uses_only_visible_rectangle(self):
        sample = make_sample(
            x=75,
            y=150,
            slide_rect=ViewportBBox(100, 50, 900, 750),
            aoi_rects={"alpha": ViewportBBox(50, 100, 200, 250)},
        )

        candidates = match_point_to_visible_aois(
            sample,
            (AOI("alpha", [0, 0, 0.2, 0.2], "text"),),
        )

        self.assertEqual(candidates, ())

    def test_point_outside_visible_slide_has_no_candidate(self):
        sample = make_sample(
            x=50,
            y=50,
            slide_rect=ViewportBBox(100, 100, 900, 700),
            aoi_rects={"alpha": ViewportBBox(40, 40, 160, 160)},
        )

        candidates = match_point_to_visible_aois(
            sample,
            (AOI("alpha", [0, 0, 0.2, 0.2], "text"),),
        )

        self.assertEqual(candidates, ())

    def test_excluded_aoi_types_and_whole_slide_are_ignored(self):
        rects = {
            name: ViewportBBox(100, 100, 300, 250)
            for name in ("footer", "page", "decor", "background", "whole_slide")
        }
        sample = make_sample(aoi_rects=rects)
        aois = (
            AOI("footer", [0, 0, 0.2, 0.2], "footer"),
            AOI("page", [0, 0, 0.2, 0.2], "page number"),
            AOI("decor", [0, 0, 0.2, 0.2], "decoration"),
            AOI("background", [0, 0, 0.2, 0.2], "background"),
            AOI("whole_slide", [0, 0, 1, 1], "whole_slide"),
        )

        self.assertEqual(match_point_to_visible_aois(sample, aois), ())

    def test_candidates_have_deterministic_tie_breaking(self):
        sample = make_sample(
            aoi_rects={
                "zeta": ViewportBBox(100, 100, 300, 250),
                "alpha": ViewportBBox(100, 100, 300, 250),
            }
        )
        aois = (
            AOI("zeta", [0, 0, 0.2, 0.2], "text"),
            AOI("alpha", [0, 0, 0.2, 0.2], "text"),
        )

        candidates = match_point_to_visible_aois(sample, aois)

        self.assertEqual(
            [candidate.aoi_id for candidate in candidates],
            ["alpha", "zeta"],
        )

    def test_aggregation_uses_server_receive_dwell(self):
        aois = (AOI("alpha", [0, 0, 0.2, 0.2], "text"),)
        samples = (
            make_sample(received_at=10.0),
            make_sample(received_at=10.2),
        )

        result = aggregate_point_gaze(
            samples,
            aois,
            speech_ended_at=10.5,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.predicted_aoi_id, "alpha")
        self.assertEqual(result.stable_duration_sec, 0.5)

    def test_aggregation_discards_older_layout_revision(self):
        rects = {
            "alpha": ViewportBBox(100, 100, 300, 250),
            "beta": ViewportBBox(500, 100, 700, 250),
        }
        aois = (
            AOI("alpha", [0, 0, 0.2, 0.2], "text"),
            AOI("beta", [0, 0, 0.2, 0.2], "figure"),
        )
        samples = (
            make_sample(x=150, received_at=0.0, revision=1, aoi_rects=rects),
            make_sample(x=150, received_at=0.2, revision=1, aoi_rects=rects),
            make_sample(x=550, received_at=0.4, revision=2, aoi_rects=rects),
            make_sample(x=550, received_at=0.6, revision=2, aoi_rects=rects),
        )

        result = aggregate_point_gaze(samples, aois, speech_ended_at=0.8)

        self.assertIsNotNone(result)
        self.assertEqual(result.predicted_aoi_id, "beta")
        self.assertEqual(result.layout_revision, 2)
        self.assertTrue(any("older layout" in item for item in result.evidence))

    def test_insufficient_new_revision_dwell_returns_none(self):
        rects = {
            "alpha": ViewportBBox(100, 100, 300, 250),
            "beta": ViewportBBox(500, 100, 700, 250),
        }
        aois = (
            AOI("alpha", [0, 0, 0.2, 0.2], "text"),
            AOI("beta", [0, 0, 0.2, 0.2], "figure"),
        )
        samples = (
            make_sample(x=150, received_at=0.0, revision=1, aoi_rects=rects),
            make_sample(x=550, received_at=0.9, revision=2, aoi_rects=rects),
        )

        result = aggregate_point_gaze(samples, aois, speech_ended_at=1.0)

        self.assertIsNone(result)

    def test_confidence_is_dwell_share_times_spatial_score(self):
        rects = {
            "alpha": ViewportBBox(100, 100, 200, 250),
            "beta": ViewportBBox(300, 100, 400, 250),
        }
        aois = (
            AOI("alpha", [0, 0, 0.2, 0.2], "text"),
            AOI("beta", [0, 0, 0.2, 0.2], "figure"),
        )
        samples = (
            make_sample(x=150, received_at=0.0, aoi_rects=rects),
            make_sample(x=425, received_at=0.2, aoi_rects=rects),
        )

        result = aggregate_point_gaze(samples, aois, speech_ended_at=0.4)

        self.assertIsNotNone(result)
        self.assertEqual(result.predicted_aoi_id, "alpha")
        self.assertEqual(result.target_confidence, 0.5)
        self.assertEqual(
            result.alternatives,
            (
                {"aoi_id": "alpha", "score": 0.5},
                {"aoi_id": "beta", "score": 0.5},
            ),
        )


if __name__ == "__main__":
    unittest.main()
