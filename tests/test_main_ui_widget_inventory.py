"""Static audit of all interactive widgets in the Main UI."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)


def dotted_name(
    node: ast.AST,
) -> str:
    if isinstance(
        node,
        ast.Name,
    ):
        return node.id

    if isinstance(
        node,
        ast.Attribute,
    ):
        prefix = dotted_name(
            node.value
        )

        return (
            f"{prefix}.{node.attr}"
            if prefix
            else node.attr
        )

    if isinstance(
        node,
        ast.Subscript,
    ):
        return dotted_name(
            node.value
        )

    return ""


def keyword_names(
    call: ast.Call,
) -> set[str]:
    return {
        keyword.arg
        for keyword in call.keywords
        if keyword.arg is not None
    }


class TestMainUIWidgetInventory(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.source = APP_PATH.read_text(
            encoding="utf-8"
        )

        cls.tree = ast.parse(
            cls.source,
            filename=str(APP_PATH),
        )

        cls.calls: list[
            tuple[str, ast.Call]
        ] = []

        for node in ast.walk(
            cls.tree
        ):
            if isinstance(
                node,
                ast.Call,
            ):
                cls.calls.append(
                    (
                        dotted_name(
                            node.func
                        ),
                        node,
                    )
                )

    def test_no_arrow_backed_table_widgets(
        self,
    ) -> None:
        forbidden = {
            "dataframe",
            "table",
            "data_editor",
        }

        violations: list[str] = []

        for name, call in self.calls:
            widget_type = (
                name.split(".")[-1]
            )

            if widget_type in forbidden:
                violations.append(
                    (
                        f"{name} at "
                        f"line {call.lineno}"
                    )
                )

        self.assertEqual(
            violations,
            [],
            (
                "Arrow-backed UI tables remain: "
                f"{violations}"
            ),
        )

    def test_safe_table_renderer_exists(
        self,
    ) -> None:
        self.assertIn(
            "def _render_records_table(",
            self.source,
        )

        self.assertIn(
            "records_to_html",
            self.source,
        )

    def test_custom_canvas_is_absent(
        self,
    ) -> None:
        self.assertNotIn(
            "st_canvas",
            self.source,
        )

        self.assertNotIn(
            "streamlit_drawable_canvas",
            self.source,
        )

    def test_checkbox_and_slider_have_keys(
        self,
    ) -> None:
        audited = {
            "checkbox",
            "slider",
        }

        discovered = 0

        for name, call in self.calls:
            widget_type = (
                name.split(".")[-1]
            )

            if widget_type not in audited:
                continue

            discovered += 1
            keywords = keyword_names(
                call
            )

            self.assertIn(
                "key",
                keywords,
                (
                    f"{name} at line "
                    f"{call.lineno} has no key."
                ),
            )

        self.assertGreaterEqual(
            discovered,
            5,
        )

    def test_checkbox_and_slider_have_callbacks(
        self,
    ) -> None:
        audited = {
            "checkbox",
            "slider",
        }

        for name, call in self.calls:
            widget_type = (
                name.split(".")[-1]
            )

            if widget_type not in audited:
                continue

            self.assertIn(
                "on_change",
                keyword_names(call),
                (
                    f"{name} at line "
                    f"{call.lineno} has no "
                    "on_change callback."
                ),
            )

    def test_interactive_widgets_have_keys(
        self,
    ) -> None:
        audited = {
            "button",
            "checkbox",
            "download_button",
            "file_uploader",
            "radio",
            "selectbox",
            "slider",
            "text_area",
            "text_input",
        }

        violations: list[str] = []

        for name, call in self.calls:
            widget_type = (
                name.split(".")[-1]
            )

            if widget_type not in audited:
                continue

            if "key" not in keyword_names(
                call
            ):
                violations.append(
                    (
                        f"{name} at "
                        f"line {call.lineno}"
                    )
                )

        self.assertEqual(
            violations,
            [],
            (
                "Interactive widgets without "
                f"explicit keys: {violations}"
            ),
        )

    def test_required_widget_keys_exist(
        self,
    ) -> None:
        required = {
            "main_pdf_upload",
            "main_cloud_text_allowed",
            "main_history_enabled",
            "main_history_max_items",
            "main_active_slide_id",
            "main_show_aoi_overlay",
            "main_region_x_range",
            "main_region_y_range",
            "main_target_scope",
            "main_typed_command",
            "main_confirmation_target_choice",
            "main_load_pdf_button",
            "main_previous_slide_button",
            "main_next_slide_button",
            "main_apply_region_button",
            "main_clear_region_button",
            "main_confirm_button",
            "main_generate_answer_button",
            "main_reset_turn_button",
            "main_clear_conversation_button",
        }

        missing = [
            key
            for key in sorted(
                required
            )
            if f'"{key}"'
            not in self.source
        ]

        self.assertEqual(
            missing,
            [],
            (
                "Required widget keys missing: "
                f"{missing}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
