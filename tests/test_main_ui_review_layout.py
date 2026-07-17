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
            "Learner State Overview",
            "Slide-order overview",
            "Selected Slide Detail",
            "AOI dwell",
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
            "Interactions",
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

    def test_no_raw_timeline_or_transcript_history_is_added(self) -> None:
        self.assertNotIn("second-by-second learner", self.source.lower())
        self.assertNotIn("learner-state timeline", self.source.lower())
        self.assertNotIn("review transcript history", self.source.lower())


if __name__ == "__main__":
    unittest.main()
