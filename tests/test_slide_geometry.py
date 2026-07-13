import os
from pathlib import Path
import unittest
from unittest.mock import patch

from modules.system.main_ui_state import MainUISlide


def valid_payload():
    return {
        "deck_id": "deck-a",
        "slide_id": 2,
        "layout_revision": 7,
        "viewport_width": 1440,
        "viewport_height": 900,
        "device_pixel_ratio": 2,
        "slide_rect": {"x1": 120, "y1": -40, "x2": 1080, "y2": 500},
        "aoi_rects": {
            "title": {"x1": 168, "y1": -13, "x2": 1032, "y2": 57},
        },
        "browser_timestamp": 999999,
    }


class SlideGeometryTest(unittest.TestCase):
    def parse(self, payload=None, *, received_at=12.5):
        from modules.system.slide_geometry import parse_component_geometry

        return parse_component_geometry(
            valid_payload() if payload is None else payload,
            received_at=received_at,
        )

    def test_parses_viewport_css_pixels_and_server_receive_time(self):
        geometry = self.parse(received_at=12.5)

        self.assertEqual(geometry.deck_id, "deck-a")
        self.assertEqual(geometry.slide_id, 2)
        self.assertEqual(geometry.layout_revision, 7)
        self.assertEqual(geometry.received_at, 12.5)
        self.assertEqual(geometry.viewport_width, 1440.0)
        self.assertEqual(geometry.viewport_height, 900.0)
        self.assertEqual(geometry.device_pixel_ratio, 2.0)
        self.assertEqual(geometry.slide_rect.y1, -40.0)
        self.assertEqual(geometry.aoi_rects["title"].x2, 1032.0)

    def test_negative_viewport_coordinates_are_valid_after_scroll(self):
        payload = valid_payload()
        payload["slide_rect"] = {
            "x1": -30,
            "y1": -400,
            "x2": 930,
            "y2": 140,
        }

        geometry = self.parse(payload)

        self.assertEqual(geometry.slide_rect.x1, -30.0)
        self.assertEqual(geometry.slide_rect.y1, -400.0)

    def test_invalid_rectangle_order_is_rejected(self):
        payload = valid_payload()
        payload["slide_rect"] = {"x1": 5, "y1": 0, "x2": 5, "y2": 10}

        with self.assertRaisesRegex(ValueError, "x1 < x2"):
            self.parse(payload)

    def test_missing_aoi_id_is_rejected(self):
        payload = valid_payload()
        payload["aoi_rects"] = {
            "": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}
        }

        with self.assertRaisesRegex(ValueError, "AOI ID"):
            self.parse(payload)

    def test_deck_and_slide_identity_are_preserved(self):
        payload = valid_payload()
        payload["deck_id"] = "uploaded-deck-42"
        payload["slide_id"] = 19

        geometry = self.parse(payload)

        self.assertEqual(geometry.deck_id, "uploaded-deck-42")
        self.assertEqual(geometry.slide_id, 19)


class SlideViewportComponentContractTest(unittest.TestCase):
    def test_apptest_escape_hatch_returns_none(self):
        from modules.ui.slide_viewport_component import render_slide_viewport

        slide = MainUISlide(
            slide_id=1,
            slide_text="slide",
            neighbor_slide_text="",
            aois=(),
        )
        with patch.dict(os.environ, {"ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST": "1"}):
            value = render_slide_viewport(
                deck_id="deck-a",
                slide=slide,
                layout_revision=0,
                drawing_enabled=False,
                show_aoi_overlay=False,
                key="test-viewport",
            )

        self.assertIsNone(value)

    def test_static_component_uses_parent_viewport_protocol(self):
        component = Path(
            "modules/ui/slide_viewport_component/index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("window.frameElement.getBoundingClientRect()", component)
        self.assertIn("window.parent.innerWidth", component)
        self.assertIn("ResizeObserver", component)
        self.assertIn("streamlit:setComponentValue", component)
        self.assertIn("streamlit:setFrameHeight", component)
        self.assertNotIn("npm", component)


if __name__ == "__main__":
    unittest.main()
