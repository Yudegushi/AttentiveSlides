from __future__ import annotations

import ast
from pathlib import Path
import unittest


APP_PATH = Path("apps/streamlit_attentive_slides.py")


class MainUIReviewLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = APP_PATH.read_text(encoding="utf-8")
        cls.combined = cls.source + Path(
            "modules/ui/review_view.py"
        ).read_text(encoding="utf-8")
        cls.css = Path("modules/ui/workspace.css").read_text(encoding="utf-8")
        tree = ast.parse(cls.source, filename=str(APP_PATH))
        cls.functions = {
            node.name: ast.unparse(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        cls.review = cls.functions["_render_review_workspace"]

    def test_review_sections_render_in_approved_order(self) -> None:
        labels = (
            "Session Summary",
            "Slide Review",
            "Selected Slide Detail",
            "AOI DWELL",
            "Learner State Evidence",
        )
        positions = [self.review.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))

    def test_review_uses_one_study_review_mapper_and_slide_id_detail(self) -> None:
        self.assertIn("build_review_view(review)", self.review)
        self.assertIn("slide_details[view.active_slide_id]", self.review)
        self.assertIn("review.gaze_review.slides", self.review)
        self.assertIn("_render_slide_selector", self.review)

    def test_required_review_metrics_and_exports_are_visible(self) -> None:
        for label in (
            "Study duration",
            "Slides viewed",
            "Interactions",
            "Gaze coverage",
            "Mean engagement",
            "Mean fatigue",
            "Top emotion",
            "Learner coverage",
            "Valid gaze duration",
            "Gaze coverage",
            "Distraction alerts",
            "Fatigue alerts",
            "Download heatmap PNG",
            "Model estimates, not a diagnosis.",
        ):
            self.assertIn(label, self.combined)

    def test_review_reuses_shell_and_has_one_topbar_back_action(self) -> None:
        main = self.functions["main"]
        sidebar = self.functions["_render_review_sidebar"]
        header = self.functions["_render_header"]
        self.assertIn("main_review_workspace", main)
        self.assertIn("REVIEW / WORKSPACE", header)
        self.assertIn("BACK TO STUDY", header)
        self.assertNotIn("Back to Study Workspace", sidebar)
        self.assertIn("main_slide_rail", self.source)

    def test_review_uses_compact_instrument_toolbar_not_wide_slider(self) -> None:
        self.assertIn("main_review_slide_toolbar", self.review)
        self.assertIn("main_review_slide_stage", self.review)
        self.assertIn("main_review_slide_frame", self.review)
        self.assertIn("main_review_slide_scale_down", self.review)
        self.assertIn("main_review_slide_scale_up", self.review)
        self.assertIn("main_review_slide_scale_fit", self.review)
        self.assertNotIn("st.slider", self.review)
        self.assertIn(".as-review-table-head", self.css)
        self.assertIn("grid-template-columns", self.css)
        self.assertIn("border-left: 3px solid var(--as-slide-accent)", self.css)

    def test_review_navigation_is_anchored_to_the_centered_slide_frame(self) -> None:
        centered = self.review.index("_centered_slide_width")
        frame = self.review.index("main_review_slide_frame")
        self.assertLess(centered, frame)
        frame_segment = self.review[frame:self.review.index(
            "if slide_review is None", frame
        )]
        self.assertIn("_render_navigation", frame_segment)
        self.assertIn("_render_review_text_fallback", frame_segment)
        self.assertIn("st.image", frame_segment)
        self.assertEqual(self.review.count("_centered_slide_width"), 1)
        self.assertIn(
            ".st-key-main_review_slide_frame {\n  position: relative;\n}",
            self.css,
        )

    def test_summary_band_separates_primary_and_learner_evidence(self) -> None:
        for label in (
            "Study duration",
            "Slides viewed",
            "Interactions",
            "Gaze coverage",
            "Learner coverage",
        ):
            self.assertIn(label, self.review)
        self.assertIn("learner_summary", self.review)
        self.assertIn("main_review_emotion_distribution", self.review)
        self.assertIn("main_review_alert_summary", self.review)

    def test_no_raw_timeline_or_transcript_history_is_added(self) -> None:
        self.assertNotIn("second-by-second learner", self.source.lower())
        self.assertNotIn("learner-state timeline", self.source.lower())
        self.assertNotIn("review transcript history", self.source.lower())


if __name__ == "__main__":
    unittest.main()
