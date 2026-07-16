from pathlib import Path
import unittest

from modules.fatigue import FatigueSnapshot
from modules.learner_state import (
    EmotionSnapshot,
    EngagementSnapshot,
    LearnerStateSnapshot,
)
from modules.review import SlideLearnerStateSummary
from modules.ui.learner_state_status import (
    COMBINED_ALERT,
    DISCLAIMER,
    DISTRACTION_ALERT,
    FATIGUE_ALERT,
    build_learner_state_view,
)


def slide_summary(seconds=266.0, interactions=3):
    return SlideLearnerStateSummary(
        slide_id=1,
        study_seconds=seconds,
        observed_seconds=0.0,
        emotion_observed_seconds=0.0,
        engagement_observed_seconds=0.0,
        fatigue_observed_seconds=0.0,
        interaction_count=interactions,
        mean_engaged_probability=None,
        mean_fatigue_probability=None,
        emotion_probabilities=(),
        top_emotion=None,
        top_emotion_probability=None,
        distraction_alert_seconds=0.0,
        distraction_alert_count=0,
        fatigue_alert_seconds=0.0,
        fatigue_alert_count=0,
    )


def ready_snapshot(*, distraction_alert=False, suppressed=False, fatigue_alert=False):
    return LearnerStateSnapshot(
        emotion=EmotionSnapshot(
            status="ready",
            probabilities=(0.05, 0.05, 0.05, 0.05, 0.1, 0.6, 0.05, 0.05),
            top_label="Neutral",
            top_probability=0.6,
            updated_at=1.0,
        ),
        engagement=EngagementSnapshot(
            status="ready",
            distracted_probability=0.32,
            engaged_probability=0.68,
            alert_active=distraction_alert,
            reminder_suppressed=suppressed,
            buffered_frames=128,
            updated_at=1.0,
        ),
        fatigue=FatigueSnapshot(
            status="ready",
            raw_probability=0.2,
            smoothed_probability=0.18,
            alert_active=fatigue_alert,
            updated_at=1.0,
        ),
        updated_at=1.0,
    )


class LearnerStateViewTest(unittest.TestCase):
    def test_ready_view_shows_only_top_emotion_and_compact_slide_metadata(self):
        view = build_learner_state_view(
            ready_snapshot(), slide_summary(), live_enabled=True
        )

        self.assertEqual(view.emotion_text, "Neutral 60%")
        self.assertEqual(view.engagement_text, "Engaged 68%")
        self.assertEqual(view.fatigue_text, "18%")
        self.assertEqual(view.slide_text, "04:26 · 3 interactions")
        self.assertNotIn("Anger", view.emotion_text)
        self.assertIsNone(view.alert_text)

    def test_engagement_warmup_uses_frame_progress(self):
        snapshot = ready_snapshot()
        snapshot = LearnerStateSnapshot(
            emotion=snapshot.emotion,
            engagement=EngagementSnapshot(
                status="warming", buffered_frames=92, required_frames=128, updated_at=1.0
            ),
            fatigue=snapshot.fatigue,
            updated_at=1.0,
        )

        view = build_learner_state_view(snapshot, slide_summary(), live_enabled=True)

        self.assertEqual(view.engagement_text, "Learning pattern · 92 / 128 frames")

    def test_unavailable_modalities_remain_separate_and_errors_are_escaped(self):
        snapshot = ready_snapshot()
        snapshot = LearnerStateSnapshot(
            emotion=EmotionSnapshot(
                status="unavailable", updated_at=1.0, error="<script>x</script>" + "x" * 200
            ),
            engagement=snapshot.engagement,
            fatigue=FatigueSnapshot(
                status="unavailable", updated_at=1.0, error="missing model"
            ),
            updated_at=1.0,
        )

        view = build_learner_state_view(snapshot, slide_summary(), live_enabled=True)

        self.assertEqual(view.emotion_text, "Unavailable")
        self.assertEqual(view.engagement_text, "Engaged 68%")
        self.assertEqual(view.fatigue_text, "Unavailable")
        self.assertTrue(any("&lt;script&gt;" in item for item in view.unavailable_details))
        self.assertFalse(any("<script>" in item for item in view.unavailable_details))
        self.assertTrue(all(len(item) <= 180 for item in view.unavailable_details))

    def test_alert_copy_has_fatigue_distraction_and_combined_priority(self):
        fatigue = build_learner_state_view(
            ready_snapshot(fatigue_alert=True), slide_summary(), live_enabled=True
        )
        distraction = build_learner_state_view(
            ready_snapshot(distraction_alert=True), slide_summary(), live_enabled=True
        )
        combined = build_learner_state_view(
            ready_snapshot(distraction_alert=True, fatigue_alert=True),
            slide_summary(),
            live_enabled=True,
        )

        self.assertEqual(fatigue.alert_text, FATIGUE_ALERT)
        self.assertEqual(distraction.alert_text, DISTRACTION_ALERT)
        self.assertEqual(combined.alert_text, COMBINED_ALERT)

    def test_suppression_hides_only_reminder_not_objective_alert(self):
        snapshot = ready_snapshot(
            distraction_alert=True, suppressed=True, fatigue_alert=True
        )

        view = build_learner_state_view(snapshot, slide_summary(), live_enabled=True)

        self.assertTrue(snapshot.engagement.alert_active)
        self.assertEqual(view.alert_text, FATIGUE_ALERT)
        self.assertFalse(view.can_dismiss_distraction)

    def test_emotion_never_creates_an_alert_and_live_off_is_quiet(self):
        active = build_learner_state_view(
            ready_snapshot(), slide_summary(seconds=1.0, interactions=1), live_enabled=True
        )
        off = build_learner_state_view(
            ready_snapshot(distraction_alert=True, fatigue_alert=True),
            slide_summary(seconds=1.0, interactions=1),
            live_enabled=False,
        )

        self.assertIsNone(active.alert_text)
        self.assertEqual(active.slide_text, "00:01 · 1 interaction")
        self.assertEqual(off.emotion_text, "Live off")
        self.assertIsNone(off.alert_text)

    def test_disclaimer_is_interpretation_safe(self):
        self.assertEqual(DISCLAIMER, "Model estimates; not a diagnosis.")


class MainLearnerStateUIContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("apps/streamlit_attentive_slides.py").read_text(
            encoding="utf-8"
        )

    def test_stable_popover_is_between_enhance_and_slides(self):
        workspace_start = self.source.index("def _render_slide_workspace")
        workspace = self.source[workspace_start:]
        enhance = workspace.index("_render_current_slide_llm_aoi_action")
        popover = workspace.index('with st.popover(\n                "Learner state"')
        slides = workspace.index("_render_slide_selector(browser)")
        self.assertLess(enhance, popover)
        self.assertLess(popover, slides)
        self.assertIn('key="main_learner_state_popover"', workspace)
        self.assertIn("[0.52, 0.33, 0.15]", workspace)

    def test_only_popover_contents_and_alert_refresh_at_one_second(self):
        self.assertIn(
            "@st.fragment(run_every=1.0)\ndef _render_learner_state_contents_periodic",
            self.source,
        )
        self.assertIn(
            "@st.fragment(run_every=1.0)\ndef _render_learner_state_alert_periodic",
            self.source,
        )
        self.assertNotIn("_render_fatigue_probability_periodic", self.source)

    def test_floating_alert_has_no_layout_shift_or_pointer_capture(self):
        self.assertIn("max-width: min(25rem, 70vw)", self.source)
        self.assertIn("pointer-events: none", self.source)
        self.assertIn("height: 0", self.source)
        self.assertIn('role="status"', self.source)


if __name__ == "__main__":
    unittest.main()
