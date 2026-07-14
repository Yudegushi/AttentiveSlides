import math
import unittest

from modules.media.browser_gaze_source import BrowserGazeSource


class FakeClock:
    def __init__(self):
        self.value = 10.0

    def __call__(self):
        return self.value


def geometry_payload():
    return {
        "deck_id": "deck-a",
        "slide_id": 2,
        "layout_revision": 7,
        "browser_timestamp_ms": 1000.0,
        "viewport_width": 1440,
        "viewport_height": 900,
        "device_pixel_ratio": 2,
        "slide_rect": {"x1": 100, "y1": 20, "x2": 1100, "y2": 780},
        "aoi_rects": {
            "title": {"x1": 150, "y1": 50, "x2": 900, "y2": 150},
        },
    }


def gaze_payload(**overrides):
    payload = {
        "sequence": 3,
        "browser_timestamp_ms": 1200.0,
        "x_css": 320.0,
        "y_css": 240.0,
        "viewport_width": 1440,
        "viewport_height": 900,
        "valid": True,
        "face_detected": True,
        "source": "eyetheia_local",
    }
    payload.update(overrides)
    return payload


class BrowserGazeSourceTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.source = BrowserGazeSource(clock=self.clock)

    def test_geometry_is_parsed_and_returned_for_matching_slide(self):
        snapshot = self.source.accept_geometry(geometry_payload())

        self.assertEqual(snapshot.browser_timestamp_ms, 1000.0)
        self.assertEqual(snapshot.received_at, 10.0)
        self.assertIs(
            self.source.latest_geometry_for("deck-a", 2),
            snapshot,
        )
        self.assertIsNone(self.source.latest_geometry_for("deck-a", 3))
        self.assertIsNone(self.source.latest_geometry_for("deck-b", 2))

    def test_gaze_attaches_matching_viewport_geometry(self):
        geometry = self.source.accept_geometry(geometry_payload())
        self.clock.value = 10.5

        sample = self.source.accept_gaze(gaze_payload(valid=False))

        self.assertIs(sample.geometry, geometry)
        self.assertFalse(sample.valid)
        self.assertEqual(
            self.source.gaze_in_window(
                start_received_at=10.0,
                end_received_at=11.0,
            ),
            [sample],
        )

    def test_gaze_does_not_attach_mismatched_viewport_geometry(self):
        self.source.accept_geometry(geometry_payload())

        sample = self.source.accept_gaze(
            gaze_payload(viewport_width=1438.9)
        )

        self.assertIsNone(sample.geometry)

    def test_gaze_storage_is_bounded_to_latest_samples(self):
        source = BrowserGazeSource(max_gaze_samples=2, clock=self.clock)
        for sequence in range(3):
            self.clock.value = 10.0 + sequence
            source.accept_gaze(gaze_payload(sequence=sequence))

        samples = source.gaze_in_window(
            start_received_at=0.0,
            end_received_at=20.0,
        )

        self.assertEqual([sample.sequence for sample in samples], [1, 2])
        self.assertEqual(source.stats().gaze_samples, 2)

    def test_clear_gaze_preserves_geometry_and_clear_removes_both(self):
        geometry = self.source.accept_geometry(geometry_payload())
        self.source.accept_gaze(gaze_payload())

        self.source.clear_gaze()

        self.assertEqual(self.source.stats().gaze_samples, 0)
        self.assertIs(
            self.source.latest_geometry_for("deck-a", 2),
            geometry,
        )

        self.source.clear()

        self.assertIsNone(self.source.latest_geometry_for("deck-a", 2))

    def test_gaze_freshness_uses_server_receive_time(self):
        self.source.accept_gaze(
            gaze_payload(browser_timestamp_ms=-999999.0)
        )

        self.clock.value = 10.99
        self.assertTrue(self.source.gaze_is_fresh())
        self.clock.value = 11.01
        self.assertFalse(self.source.gaze_is_fresh())

    def test_invalid_numbers_and_wrong_source_are_rejected(self):
        invalid_payloads = (
            gaze_payload(x_css=math.nan),
            gaze_payload(viewport_height=0),
            gaze_payload(source="cloud"),
            gaze_payload(sequence=1.5),
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.source.accept_gaze(payload)

        bad_geometry = geometry_payload()
        bad_geometry["browser_timestamp_ms"] = math.inf
        with self.assertRaises(ValueError):
            self.source.accept_geometry(bad_geometry)
        self.assertEqual(
            self.source.stats().gaze_rejections,
            len(invalid_payloads),
        )


if __name__ == "__main__":
    unittest.main()
