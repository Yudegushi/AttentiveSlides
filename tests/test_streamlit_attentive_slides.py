"""Isolated AppTest for the interactive AttentiveSlides Main UI."""

from __future__ import annotations

import unittest

from tests.streamlit_subprocess_test_utils import (
    format_subprocess_failure,
    run_isolated_apptest,
)


class TestStreamlitAttentiveSlides(
    unittest.TestCase
):
    def test_main_ui_renders(
        self,
    ) -> None:
        result = run_isolated_apptest(
            app_path=(
                "apps/"
                "streamlit_attentive_slides.py"
            ),
            expected_title="AttentiveSlides",
            required_subheaders=(
                "Slide workspace",
                "Manual interaction",
            ),
            required_buttons=(
                "Load PDF",
                "Explain",
                "Summarize",
                "Simplify",
                "Step by step",
                "Compare",
                "Quiz",
                "Confirm target and intent",
                "Use whole slide",
                "Cancel confirmation",
                "Generate grounded answer",
                "Clear conversation",
                "Reset current turn",
            ),
            forbidden_buttons=(),
            required_selectboxes=(
                "Current slide",
            ),
            required_radios=(
                "Target scope",
            ),
            required_text_areas=(
                "Typed command",
            ),
        )

        self.assertEqual(
            result.returncode,
            0,
            format_subprocess_failure(
                result
            ),
        )

        self.assertIn(
            "ISOLATED_APPTEST_PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
