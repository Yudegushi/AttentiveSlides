"""Tests for manual rectangle selection and AOI mapping."""

from __future__ import annotations

import unittest

from modules.common.schemas import AOI
from modules.system.manual_targeting import (
    extract_latest_rectangle,
    fabric_rectangle_to_bbox,
    map_bbox_to_aois,
)


def make_aois() -> list[AOI]:
    return [
        AOI(
            aoi_id="left_text",
            bbox=[
                0.05,
                0.10,
                0.45,
                0.80,
            ],
            type="text",
            text="Fixation definition.",
        ),
        AOI(
            aoi_id="right_figure",
            bbox=[
                0.50,
                0.10,
                0.95,
                0.80,
            ],
            type="figure",
            text="Saccade diagram.",
        ),
        AOI(
            aoi_id="whole_slide",
            bbox=[
                0.0,
                0.0,
                1.0,
                1.0,
            ],
            type="whole_slide",
            text=(
                "Fixation definition. "
                "Saccade diagram."
            ),
        ),
    ]


class TestManualTargeting(
    unittest.TestCase
):
    def test_fabric_rectangle_normalization(
        self,
    ) -> None:
        bbox = fabric_rectangle_to_bbox(
            {
                "type": "rect",
                "left": 360,
                "top": 90,
                "width": 324,
                "height": 270,
                "scaleX": 1.0,
                "scaleY": 1.0,
                "originX": "left",
                "originY": "top",
                "angle": 0,
            },
            canvas_width=720,
            canvas_height=450,
        )

        self.assertEqual(
            bbox,
            (
                0.5,
                0.2,
                0.95,
                0.8,
            ),
        )

    def test_scaled_rectangle(
        self,
    ) -> None:
        bbox = fabric_rectangle_to_bbox(
            {
                "left": 72,
                "top": 45,
                "width": 144,
                "height": 90,
                "scaleX": 2.0,
                "scaleY": 2.0,
            },
            canvas_width=720,
            canvas_height=450,
        )

        self.assertEqual(
            bbox,
            (
                0.1,
                0.1,
                0.5,
                0.5,
            ),
        )

    def test_right_aoi_is_ranked_first(
        self,
    ) -> None:
        matches = map_bbox_to_aois(
            (
                0.52,
                0.12,
                0.94,
                0.78,
            ),
            make_aois(),
        )

        self.assertGreaterEqual(
            len(matches),
            1,
        )

        self.assertEqual(
            matches[0].aoi_id,
            "right_figure",
        )

        self.assertGreater(
            matches[0].aoi_coverage,
            0.8,
        )

    def test_latest_rectangle_is_used(
        self,
    ) -> None:
        result = extract_latest_rectangle(
            {
                "objects": [
                    {
                        "type": "rect",
                        "left": 36,
                        "top": 45,
                        "width": 200,
                        "height": 300,
                    },
                    {
                        "type": "rect",
                        "left": 370,
                        "top": 55,
                        "width": 300,
                        "height": 300,
                    },
                ]
            },
            canvas_width=720,
            canvas_height=450,
            aois=make_aois(),
        )

        self.assertIsNotNone(result)

        assert result is not None

        self.assertEqual(
            result.primary_aoi_id,
            "right_figure",
        )

        target = result.to_target_input(
            slide_id=5
        )

        self.assertEqual(
            target.source,
            "manual_rectangle",
        )

        self.assertEqual(
            target.selected_aoi_id,
            "right_figure",
        )

    def test_no_rectangle_returns_none(
        self,
    ) -> None:
        result = extract_latest_rectangle(
            {
                "objects": []
            },
            canvas_width=720,
            canvas_height=450,
            aois=make_aois(),
        )

        self.assertIsNone(result)

    def test_rotated_rectangle_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            fabric_rectangle_to_bbox(
                {
                    "left": 100,
                    "top": 100,
                    "width": 200,
                    "height": 100,
                    "angle": 30,
                },
                canvas_width=720,
                canvas_height=450,
            )


if __name__ == "__main__":
    unittest.main()
