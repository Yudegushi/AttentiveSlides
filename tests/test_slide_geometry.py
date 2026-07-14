import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

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
    @staticmethod
    def component_source():
        return Path(
            "modules/ui/slide_viewport_component/index.html"
        ).read_text(encoding="utf-8")

    def test_apptest_escape_hatch_returns_disabled_event(self):
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
                display_width_percent=100,
                key="test-viewport",
            )

        self.assertEqual(value, {"event": "disabled"})

    def test_display_width_is_passed_to_declared_component(self):
        from modules.ui.slide_viewport_component import render_slide_viewport

        declared_component = Mock(return_value={"status": "ok"})
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "slide.png"
            image_path.write_bytes(b"png")
            slide = MainUISlide(
                slide_id=1,
                slide_text="slide",
                neighbor_slide_text="",
                aois=(),
                image_path=str(image_path),
            )
            with patch.dict(
                os.environ,
                {"ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST": "0"},
            ):
                with patch(
                    "modules.ui.slide_viewport_component._component",
                    return_value=declared_component,
                ):
                    value = render_slide_viewport(
                        deck_id="deck-a",
                        slide=slide,
                        layout_revision=0,
                        drawing_enabled=False,
                        show_aoi_overlay=False,
                        display_width_percent=75,
                        key="test-viewport",
                    )

        self.assertEqual(value, {"status": "ok"})
        self.assertEqual(
            declared_component.call_args.kwargs["display_width_percent"],
            75,
        )
        self.assertEqual(
            declared_component.call_args.kwargs["default"],
            {"event": "mounted"},
        )

    def test_static_component_uses_parent_viewport_protocol(self):
        component = self.component_source()

        self.assertIn("margin-inline: auto", component)
        self.assertIn("display_width_percent", component)
        self.assertIn("slide.style.width", component)
        self.assertIn("image.getBoundingClientRect()", component)
        self.assertIn("window.frameElement.getBoundingClientRect()", component)
        self.assertIn("window.parent.innerWidth", component)
        self.assertIn("ResizeObserver", component)
        self.assertIn("streamlit:setComponentValue", component)
        self.assertIn("streamlit:setFrameHeight", component)
        self.assertIn('fetch("/attentive-media/geometry"', component)
        self.assertIn("geometryInFlight", component)
        self.assertIn("pendingGeometry", component)
        self.assertIn(
            "performance.timeOrigin + performance.now()",
            component,
        )
        self.assertNotIn("npm", component)

    def test_unchanged_geometry_is_deduplicated_before_revision_advances(self):
        component = self.component_source()

        self.assertIn("lastReportedSignature", component)
        self.assertIn("geometrySignature", component)
        comparison = component.index(
            "signature !== lastReportedSignature"
        )
        self.assertNotIn("revision += 1", component[:comparison])
        revision = component.index("revision += 1", comparison)
        send = component.index("postGeometry(payload)", revision)

        self.assertLess(comparison, revision)
        self.assertLess(revision, send)

    def test_component_value_is_reserved_for_manual_selection_and_errors(self):
        component = self.component_source()

        self.assertNotIn("setValue(payload)", component)
        self.assertIn(
            'setValue(Object.assign({ event: "manual_selection" }, payload))',
            component,
        )
        self.assertIn("setValue(errorPayload)", component)
        self.assertIn(
            "scheduleReport({ componentValue: true })",
            component,
        )

    def test_repeated_coordinate_errors_are_deduplicated(self):
        component = self.component_source()

        self.assertIn("lastCoordinateErrorSignature", component)
        self.assertIn(
            "errorSignature === lastCoordinateErrorSignature",
            component,
        )

    def test_coordinate_error_invalidates_last_successful_signature(self):
        component = self.component_source()
        error_guard = component.index(
            "errorSignature === lastCoordinateErrorSignature"
        )
        error_send = component.index("setValue(errorPayload)", error_guard)

        self.assertIn(
            "lastReportedSignature = null",
            component[error_guard:error_send],
        )

    def test_manual_bbox_keeps_finer_signature_precision_than_layout_pixels(self):
        component = self.component_source()

        self.assertIn("this === payload.manual_bbox", component)
        self.assertIn("? 10000 : 10", component)

    def test_same_render_preserves_manual_bbox_until_explicit_reset(self):
        component = self.component_source()

        self.assertIn("lastRequestedRevision", component)
        self.assertIn("sameSlideIdentity", component)
        self.assertIn("preserveManualBBox", component)
        self.assertIn("!preserveManualBBox", component)
        self.assertIn("lastRequestedRevision = requestedRevision", component)
        self.assertIn("showManualBBox(manualBBox)", component)

        identity_start = component.index(
            "const requestedRevision = Number(nextArgs.layout_revision)"
        )
        identity_end = component.index("args = nextArgs", identity_start)
        reset_identity = component[identity_start:identity_end]
        self.assertIn("args.deck_id", reset_identity)
        self.assertIn("args.slide_id", reset_identity)
        self.assertIn("nextArgs.drawing_enabled", reset_identity)
        self.assertIn("requestedRevision", reset_identity)
        self.assertNotIn("display_width_percent", reset_identity)

    def test_layout_listeners_use_one_throttled_report(self):
        component = self.component_source()

        self.assertIn("let reportTimer = null", component)
        self.assertIn("function scheduleThrottledReport", component)
        self.assertIn("if (reportTimer !== null) return", component)
        self.assertIn("window.setTimeout", component)
        self.assertIn("}, 180)", component)
        self.assertIn(
            "resizeHandler = scheduleThrottledReport",
            component,
        )
        self.assertIn(
            "parentScrollHandler = scheduleThrottledReport",
            component,
        )
        self.assertIn(
            "ResizeObserver(scheduleThrottledReport)",
            component,
        )


if __name__ == "__main__":
    unittest.main()
