"""AppTest smoke test for the grounded Streamlit XAI app."""

from __future__ import annotations

import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(
    AppTest is None,
    "Streamlit AppTest is unavailable.",
)
class TestStreamlitGroundedXAI(unittest.TestCase):
    def test_initial_app_render_has_no_exception(
        self,
    ) -> None:
        app = AppTest.from_file(
            "apps/streamlit_grounded_xai.py"
        )

        app.run(timeout=20)

        self.assertEqual(
            len(app.exception),
            0,
            [
                exception.message
                for exception in app.exception
            ],
        )

        self.assertTrue(
            any(
                "AttentiveSlides" in title.value
                for title in app.title
            )
        )

        subheader_values = {
            subheader.value
            for subheader in app.subheader
        }

        self.assertTrue(
            {
                "Interaction context",
                "Target confirmation",
                "Grounded API tutor",
            }.issubset(subheader_values)
        )

        self.assertGreaterEqual(
            len(app.selectbox),
            1,
        )

        self.assertGreaterEqual(
            len(app.text_area),
            1,
        )


if __name__ == "__main__":
    unittest.main()
