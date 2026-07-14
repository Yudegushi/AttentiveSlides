"""Static contracts for the target and Tutor workflow."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

REALTIME_PATH = Path(
    "modules/system/realtime_voice_ui.py"
)


def call_name(
    call: ast.Call,
) -> str:
    if isinstance(
        call.func,
        ast.Name,
    ):
        return call.func.id

    if isinstance(
        call.func,
        ast.Attribute,
    ):
        return call.func.attr

    return ""


class TestTutorWorkflowLayout(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.source = (
            APP_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.tree = ast.parse(
            cls.source,
            filename=str(APP_PATH),
        )

        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(
                node,
                ast.FunctionDef,
            )
        }

    def source_of(
        self,
        name: str,
    ) -> str:
        return (
            ast.get_source_segment(
                self.source,
                self.functions[
                    name
                ],
            )
            or ""
        )

    def calls_of(
        self,
        name: str,
    ) -> list[str]:
        return [
            call_name(
                node
            )
            for node in ast.walk(
                self.functions[
                    name
                ]
            )
            if isinstance(
                node,
                ast.Call,
            )
        ]

    def test_confirmation_is_in_step_one(
        self,
    ) -> None:
        self.assertIn(
            "_render_confirmation_panel",
            self.calls_of(
                "_render_target_column"
            ),
        )

        self.assertNotIn(
            "_render_confirmation_panel",
            self.calls_of(
                "_render_intent_column"
            ),
        )

    def test_confirmation_has_only_confirm_and_cancel(
        self,
    ) -> None:
        source = self.source_of(
            "_render_confirmation_panel"
        )

        self.assertIn(
            "Confirm target",
            source,
        )

        self.assertIn(
            "Cancel confirmation",
            source,
        )

        self.assertNotIn(
            "Use whole slide",
            source,
        )

        self.assertNotIn(
            "Confirm target and intent",
            source,
        )

        self.assertIn(
            "assess_target_confirmation",
            source,
        )

        self.assertIn(
            "confirm_target_selection",
            source,
        )

    def test_second_panel_combines_tutor_controls(
        self,
    ) -> None:
        source = self.source_of(
            "_render_intent_column"
        )

        calls = self.calls_of(
            "_render_intent_column"
        )

        self.assertIn(
            "### 2. Tutor",
            source,
        )

        for required in (
            "_render_quick_intent_actions",
            "text_area",
            "render_grounded_tutor_voice",
            "_render_tutor_generation_panel",
            "_render_tutor_output",
        ):
            with self.subTest(
                required=required,
            ):
                self.assertIn(
                    required,
                    calls,
                )

    def test_third_panel_is_continuous_only(
        self,
    ) -> None:
        source = self.source_of(
            "_render_answer_column"
        )

        calls = self.calls_of(
            "_render_answer_column"
        )

        self.assertIn(
            "### 3. Tutor",
            source,
        )

        self.assertIn(
            "render_continuous_voice_panel",
            calls,
        )

        for forbidden in (
            "render_grounded_tutor_voice",
            "_render_tutor_generation_panel",
            "_render_tutor_result",
            "_render_xai_drawer",
            "button",
        ):
            with self.subTest(
                forbidden=forbidden,
            ):
                self.assertNotIn(
                    forbidden,
                    calls,
                )

    def test_prompt_changes_preserve_target(
        self,
    ) -> None:
        for name in (
            "_on_typed_command_change",
            "_apply_quick_intent",
        ):
            source = self.source_of(
                name
            )

            self.assertIn(
                "_invalidate_request_state",
                source,
            )

            self.assertNotIn(
                "_invalidate_confirmation()",
                source,
            )

    def test_canvas_is_capped_and_preserves_ratio(
        self,
    ) -> None:
        source = self.source_of(
            "_render_manual_canvas"
        )

        self.assertIn(
            "900",
            source,
        )

        self.assertNotIn(
            "1400",
            source,
        )

        self.assertNotIn(
            "max(\n            420",
            source,
        )

    def test_voice_uses_confirmed_target(
        self,
    ) -> None:
        source = (
            REALTIME_PATH.read_text(
                encoding="utf-8"
            )
        )

        self.assertIn(
            "main_confirmed_target",
            source,
        )

        self.assertIn(
            "confirmed_context",
            source,
        )

        self.assertIn(
            "render_realtime_voice_result",
            source,
        )


if __name__ == "__main__":
    unittest.main()
