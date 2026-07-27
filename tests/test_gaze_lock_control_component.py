from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GazeLockControlComponentTest(unittest.TestCase):
    def test_lock_control_uses_browser_timestamp_for_click_or_tab_release(self):
        source = (
            ROOT
            / "modules"
            / "ui"
            / "gaze_lock_control_component"
            / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('event: "gaze_lock"', source)
        self.assertIn('return "lock-" + crypto.randomUUID()', source)
        self.assertIn(
            "clicked_at_browser_ms: performance.timeOrigin + performance.now()",
            source,
        )
        self.assertIn("if (button.disabled || submitted) return", source)
        self.assertIn('button.addEventListener("click", submitLock)', source)
        self.assertIn('button.addEventListener("keyup", (event) => {', source)
        self.assertIn('event.key !== "Tab" || event.shiftKey', source)
        self.assertIn("document.activeElement !== button", source)


if __name__ == "__main__":
    unittest.main()
