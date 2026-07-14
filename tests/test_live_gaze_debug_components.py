from __future__ import annotations

import unittest
from pathlib import Path


CAPTURE_PATH = Path("modules/media/live_capture_component/index.html")
VIEWPORT_PATH = Path("modules/ui/slide_viewport_component/index.html")


class LiveGazeDebugComponentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = CAPTURE_PATH.read_text(encoding="utf-8")
        cls.viewport = VIEWPORT_PATH.read_text(encoding="utf-8")

    def test_capture_broadcasts_only_gaze_debug_contract(self) -> None:
        self.assertIn('"attentiveslides-gaze-debug-v1"', self.capture)
        self.assertIn('kind: "gaze"', self.capture)
        self.assertIn('kind: "gaze_clear"', self.capture)
        self.assertIn('source: "eyetheia_local"', self.capture)
        self.assertNotIn("landmarks: latestLandmarks", self.capture)

    def test_viewport_has_transient_gaze_and_aoi_states(self) -> None:
        self.assertIn('"attentiveslides-gaze-debug-v1"', self.viewport)
        self.assertIn('className = "gaze-dot"', self.viewport)
        self.assertIn("aoi-live-candidate", self.viewport)
        self.assertIn("aoi-server-match", self.viewport)
        self.assertIn("GAZE_STALE_AFTER_MS = 1000", self.viewport)

    def test_server_match_style_has_priority_over_live_candidate(self) -> None:
        self.assertIn("serverMatchedAoiId === aoiId", self.viewport)
        self.assertIn("else if (liveCandidateAoiId === aoiId)", self.viewport)


if __name__ == "__main__":
    unittest.main()
