"""Static inventory for current Main UI widgets."""

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
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        prefix = dotted_name(
            node.value
        )

        return (
            f"{prefix}.{node.attr}"
            if prefix
            else node.attr
        )

    if isinstance(node, ast.Subscript):
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


def literal_key(
    call: ast.Call,
) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != "key":
            continue

        if (
            isinstance(
                keyword.value,
                ast.Constant,
            )
            and isinstance(
                keyword.value.value,
                str,
            )
        ):
            return keyword.value.value

    return None


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

        cls.calls = [
            node
            for node in ast.walk(
                cls.tree
            )
            if isinstance(
                node,
                ast.Call,
            )
        ]

    def test_interactive_widgets_have_key_argument(
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

        violations = []

        for call in self.calls:
            widget_type = (
                dotted_name(
                    call.func
                ).split(".")[-1]
            )

            if widget_type not in audited:
                continue

            if "key" not in keyword_names(
                call
            ):
                violations.append(
                    {
                        "widget": widget_type,
                        "line": call.lineno,
                    }
                )

        self.assertEqual(
            violations,
            [],
        )

    def test_checkbox_and_slider_callbacks(
        self,
    ) -> None:
        violations = []

        for call in self.calls:
            widget_type = (
                dotted_name(
                    call.func
                ).split(".")[-1]
            )

            if widget_type not in {
                "checkbox",
                "slider",
            }:
                continue

            if (
                widget_type == "slider"
                and literal_key(call) == "main_slide_width_percent"
            ):
                continue

            if "on_change" not in keyword_names(
                call
            ):
                violations.append(
                    {
                        "widget": widget_type,
                        "line": call.lineno,
                    }
                )

        self.assertEqual(
            violations,
            [],
        )


    def test_required_static_keys_exist(
        self,
    ) -> None:
        discovered = {
            key
            for call in self.calls
            if (
                key := literal_key(
                    call
                )
            )
        }

        required = {
            "main_pdf_upload",
            "main_process_current_llm_aoi",
            "main_cloud_text_allowed",
            "main_interaction_mode",
            "main_live_master_enabled",
            "main_confirmation_policy",
            "main_history_enabled",
            "main_previous_slide_button",
            "main_next_slide_button",
            "main_target_scope",
            "main_show_aoi_overlay",
            "main_clear_region_button",
            "main_typed_command",
            "main_confirm_button",
            "main_live_confirm_button",
            "main_generate_answer_button",
            "main_reset_turn_button",
            "main_clear_conversation_button",
        }

        missing = sorted(
            required - discovered
        )

        self.assertEqual(
            missing,
            [],
        )

    def test_no_arrow_widgets(
        self,
    ) -> None:
        forbidden = {
            "dataframe",
            "data_editor",
            "table",
        }

        violations = []

        for call in self.calls:
            call_type = (
                dotted_name(
                    call.func
                ).split(".")[-1]
            )

            if call_type in forbidden:
                violations.append(
                    {
                        "widget": call_type,
                        "line": call.lineno,
                    }
                )

        self.assertEqual(
            violations,
            [],
        )


if __name__ == "__main__":
    unittest.main()
