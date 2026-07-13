from __future__ import annotations

import unittest

from modules.common.schemas import AOI
from modules.system.manual_confirmation import build_manual_confirmation_preview


class TestManualConfirmationScopeAlias(unittest.TestCase):
    def setUp(self) -> None:
        self.aois = (
            AOI(
                aoi_id="whole_slide",
                bbox=[0.0, 0.0, 1.0, 1.0],
                type="whole_slide",
                text="Whole slide text",
            ),
            AOI(
                aoi_id="region_1",
                bbox=[0.1, 0.1, 0.5, 0.5],
                type="text",
                text="Region text",
            ),
        )

    def build(self, scope: str):
        return build_manual_confirmation_preview(
            deck_id="deck",
            slide_id=1,
            target_scope=scope,
            bbox=[0.1, 0.1, 0.5, 0.5],
            selected_aoi_ids=["region_1"],
            selection_matches=[
                {
                    "aoi_id": "region_1",
                    "score": 0.9,
                }
            ],
            slide_text="Whole slide text",
            aois=self.aois,
            intent_resolution=None,
        )

    def test_whole_slide_aliases(self) -> None:
        for value in (
            "Whole slide",
            "Use whole slide",
            "whole_slide",
        ):
            with self.subTest(value=value):
                preview = self.build(value)
                self.assertEqual(preview.target_scope, "Whole slide")
                self.assertEqual(preview.proposed_aoi_id, "whole_slide")

    def test_manual_region_aliases(self) -> None:
        for value in (
            "Manual region",
            "Select region",
            "manual_rectangle",
        ):
            with self.subTest(value=value):
                preview = self.build(value)
                self.assertEqual(preview.target_scope, "Manual region")
                self.assertEqual(preview.proposed_aoi_id, "region_1")


if __name__ == "__main__":
    unittest.main()
