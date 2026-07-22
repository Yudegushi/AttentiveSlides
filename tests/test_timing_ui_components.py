from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TimingUIComponentTests(unittest.TestCase):
    def test_ptt_persists_browser_timing_without_component_rerun(self) -> None:
        source = (
            ROOT / "modules" / "ui" / "voice_control_component" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn('const PTT_TIMING_KEY = "attentive-timing-ptt"', source)
        self.assertIn("started_at_browser_ms: pttTimingStartedAt", source)
        self.assertIn("const pttReleasedAt = browserTimestampMs()", source)
        self.assertIn("released_at_browser_ms: pttReleasedAt", source)
        self.assertIn("globalThis.localStorage.setItem(PTT_TIMING_KEY", source)
        self.assertNotIn("streamlit:setComponentValue", source)
        self.assertLess(
            source.index('handleCommandResponse(await command("/attentive-voice/ptt/stop"'),
            source.index("globalThis.localStorage.setItem(PTT_TIMING_KEY"),
        )

    def test_manual_selection_reports_pointer_down_and_pointer_up_times(self) -> None:
        source = (
            ROOT / "modules" / "ui" / "slide_viewport_component" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn("drawStartedAtBrowserMs = performance.timeOrigin + performance.now()", source)
        self.assertIn("drawFinishedAtBrowserMs = performance.timeOrigin + performance.now()", source)
        self.assertIn("payload.timing_started_at_browser_ms", source)
        self.assertIn("payload.timing_intermediate_at_browser_ms", source)

    def test_timing_submit_uses_browser_timestamp(self) -> None:
        source = (
            ROOT / "modules" / "ui" / "timing_submit_component" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn('event: "timing_submit"', source)
        self.assertIn("submitted_at_browser_ms: performance.timeOrigin + performance.now()", source)
        self.assertIn("timing_start_event_id: value.event_id", source)
        self.assertIn("timing_started_at_browser_ms: value.started_at_browser_ms", source)
        self.assertIn("timing_intermediate_at_browser_ms: value.released_at_browser_ms", source)


if __name__ == "__main__":
    unittest.main()
