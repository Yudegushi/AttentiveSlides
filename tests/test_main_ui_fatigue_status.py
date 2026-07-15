from pathlib import Path
import unittest

from modules.fatigue import FatigueSnapshot, FatigueStateStore
from modules.ui.fatigue_status import build_fatigue_status_view


class FatigueStatusViewTest(unittest.TestCase):
    def test_live_off_text_is_exact_and_never_alerts(self):
        view = build_fatigue_status_view(
            FatigueSnapshot(
                status="ready",
                smoothed_probability=0.9,
                alert_active=True,
                updated_at=1.0,
            ),
            live_enabled=False,
        )

        self.assertEqual(
            view.probability_text,
            "疲劳概率（模型估计）：--（Live 未开启）",
        )
        self.assertFalse(view.show_alert)

    def test_waiting_stale_and_unavailable_text_are_exact(self):
        waiting = build_fatigue_status_view(
            FatigueSnapshot(), live_enabled=True
        )
        store = FatigueStateStore(clock=lambda: 3.1)
        store.publish(
            FatigueSnapshot(
                status="ready",
                smoothed_probability=0.8,
                alert_active=True,
                updated_at=1.0,
            )
        )
        stale = build_fatigue_status_view(
            store.snapshot(), live_enabled=True
        )
        unavailable = build_fatigue_status_view(
            FatigueSnapshot(status="unavailable", error="missing"),
            live_enabled=True,
        )

        expected_waiting = "疲劳概率（模型估计）：--（等待有效人脸）"
        self.assertEqual(waiting.probability_text, expected_waiting)
        self.assertEqual(stale.probability_text, expected_waiting)
        self.assertFalse(stale.show_alert)
        self.assertEqual(
            unavailable.probability_text,
            "疲劳概率（模型估计）：--（模型不可用）",
        )
        self.assertFalse(unavailable.show_alert)

    def test_ready_probability_rounds_and_alert_uses_exact_text(self):
        view = build_fatigue_status_view(
            FatigueSnapshot(
                status="ready",
                raw_probability=0.81,
                smoothed_probability=0.374,
                alert_active=True,
                updated_at=1.0,
            ),
            live_enabled=True,
        )

        self.assertEqual(view.probability_text, "疲劳概率（模型估计）：37%")
        self.assertTrue(view.show_alert)
        self.assertEqual(view.alert_text, "检测到持续疲劳迹象，建议短暂休息。")

    def test_ready_without_alert_shows_only_probability(self):
        view = build_fatigue_status_view(
            FatigueSnapshot(
                status="ready",
                smoothed_probability=0.4,
                updated_at=1.0,
            ),
            live_enabled=True,
        )

        self.assertEqual(view.probability_text, "疲劳概率（模型估计）：40%")
        self.assertFalse(view.show_alert)


class MainFatigueUIContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("apps/streamlit_attentive_slides.py").read_text(
            encoding="utf-8"
        )

    def test_fragment_is_half_second_and_between_header_and_slide_picker(self):
        header_call = self.source.index("    _render_header(view)\n")
        fatigue_call = self.source.index(
            "    _render_fatigue_periodic(live_resources)\n"
        )
        picker_call = self.source.index("    _render_slide_selector(\n")

        self.assertLess(header_call, fatigue_call)
        self.assertLess(fatigue_call, picker_call)
        self.assertIn(
            "@st.fragment(run_every=0.5)\ndef _render_fatigue_periodic",
            self.source,
        )

    def test_fragment_uses_caption_and_conditional_warning_without_rerun(self):
        start = self.source.index("def _render_fatigue_periodic")
        end = self.source.index("def _render_navigation", start)
        fragment = self.source[start:end]

        self.assertIn("st.caption(view.probability_text)", fragment)
        self.assertIn("if view.show_alert:", fragment)
        self.assertIn("st.warning(view.alert_text)", fragment)
        self.assertNotIn("st.rerun", fragment)

    def test_fatigue_ui_has_no_tutor_aoi_or_confirmation_path(self):
        module = Path("modules/ui/fatigue_status.py").read_text(encoding="utf-8")

        self.assertNotIn("possible_review_needed", module)
        self.assertNotIn("adaptive_policy", module)
        self.assertNotIn("Tutor", module)
        self.assertNotIn("AOI", module)
        self.assertNotIn("confirmation", module)


if __name__ == "__main__":
    unittest.main()
