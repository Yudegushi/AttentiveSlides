"""Tests for the compact Main UI sidebar layout."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

STATE_PATH = Path(
    "modules/system/main_ui_state.py"
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


def string_keyword(
    call: ast.Call,
    name: str,
) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != name:
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


class TestSidebarLayout(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.app_source = (
            APP_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.state_source = (
            STATE_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.tree = ast.parse(
            cls.app_source,
            filename=str(APP_PATH),
        )

    def test_privacy_expander_is_collapsed(
        self,
    ) -> None:
        matches = []

        for node in ast.walk(
            self.tree
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if dotted_name(
                node.func
            ) != "st.sidebar.expander":
                continue

            if not node.args:
                continue

            title = node.args[0]

            if not (
                isinstance(
                    title,
                    ast.Constant,
                )
                and title.value
                == "Privacy Status"
            ):
                continue

            expanded_value = None

            for keyword in node.keywords:
                if keyword.arg == "expanded":
                    expanded_value = (
                        keyword.value
                    )

            matches.append(
                expanded_value
            )

        self.assertEqual(
            len(matches),
            1,
        )

        self.assertIsInstance(
            matches[0],
            ast.Constant,
        )

        self.assertIs(
            matches[0].value,
            False,
        )

    def test_history_limit_slider_is_absent(
        self,
    ) -> None:
        violations = []

        for node in ast.walk(
            self.tree
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if (
                dotted_name(
                    node.func
                ).split(".")[-1]
                != "slider"
            ):
                continue

            if (
                string_keyword(
                    node,
                    "key",
                )
                == "main_history_max_items"
            ):
                violations.append(
                    node.lineno
                )

        self.assertEqual(
            violations,
            [],
        )

        self.assertNotIn(
            '"Recent turns sent to tutor"',
            self.app_source,
        )

    def test_history_limit_defaults_to_four(
        self,
    ) -> None:
        self.assertRegex(
            self.state_source,
            re.compile(
                r'''
                "main_history_max_items"
                \s*:\s*4
                ''',
                re.VERBOSE,
            ),
        )

    def test_app_forces_history_limit_to_four(
        self,
    ) -> None:
        found = False

        for node in ast.walk(
            self.tree
        ):
            if not isinstance(
                node,
                ast.Assign,
            ):
                continue

            if not (
                isinstance(
                    node.value,
                    ast.Constant,
                )
                and node.value.value == 4
            ):
                continue

            for target in node.targets:
                if not isinstance(
                    target,
                    ast.Subscript,
                ):
                    continue

                if dotted_name(
                    target.value
                ) != "st.session_state":
                    continue

                slice_value = target.slice

                if (
                    isinstance(
                        slice_value,
                        ast.Constant,
                    )
                    and slice_value.value
                    == "main_history_max_items"
                ):
                    found = True

        self.assertTrue(
            found,
        )

    def test_system_status_has_two_rows(
        self,
    ) -> None:
        column_calls = []

        for node in ast.walk(
            self.tree
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if dotted_name(
                node.func
            ) != "st.sidebar.columns":
                continue

            if not node.args:
                continue

            argument = node.args[0]

            if (
                isinstance(
                    argument,
                    ast.Constant,
                )
                and argument.value == 2
            ):
                column_calls.append(
                    node.lineno
                )

        self.assertGreaterEqual(
            len(column_calls),
            2,
        )

        for required_text in (
            '"MODE"',
            '"CAMERA"',
            '"MICROPHONE"',
            '"CLOUD TUTOR"',
        ):
            self.assertIn(
                required_text,
                self.app_source,
            )

    def test_main_workspace_status_metrics_are_absent(
        self,
    ) -> None:
        labels = {
            "mode",
            "camera",
            "microphone",
            "cloud tutor",
            "cloud llm",
        }

        violations = []

        for node in ast.walk(
            self.tree
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if not (
                isinstance(
                    node.func,
                    ast.Attribute,
                )
                and node.func.attr
                == "metric"
            ):
                continue

            if not node.args:
                continue

            value = node.args[0]

            if not (
                isinstance(
                    value,
                    ast.Constant,
                )
                and isinstance(
                    value.value,
                    str,
                )
            ):
                continue

            if (
                value.value
                .strip()
                .casefold()
                in labels
            ):
                violations.append(
                    {
                        "label": value.value,
                        "line": node.lineno,
                    }
                )

        self.assertEqual(
            violations,
            [],
        )


if __name__ == "__main__":
    unittest.main()
