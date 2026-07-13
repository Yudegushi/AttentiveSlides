"""Static render-contract tests for the AttentiveSlides Main UI.

This test module must not import Streamlit, Pandas, PyArrow, the app
module, or Streamlit AppTest. It only parses the app source with AST.
"""

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
        prefix = dotted_name(node.value)

        return (
            f"{prefix}.{node.attr}"
            if prefix
            else node.attr
        )

    if isinstance(node, ast.Subscript):
        return dotted_name(node.value)

    return ""


def constant_string(
    node: ast.AST | None,
) -> str | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
    ):
        return node.value

    return None


def keyword_value(
    call: ast.Call,
    name: str,
) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value

    return None


def keyword_string(
    call: ast.Call,
    name: str,
) -> str | None:
    return constant_string(
        keyword_value(call, name)
    )


class TestStreamlitAttentiveSlides(
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

        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(
                node,
                ast.FunctionDef,
            )
        }

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

    def test_app_source_parses(
        self,
    ) -> None:
        self.assertIn(
            "main",
            self.functions,
        )

    def test_main_title_is_rendered_once(
        self,
    ) -> None:
        titles = []

        for call in self.calls:
            if dotted_name(
                call.func
            ) != "st.title":
                continue

            if not call.args:
                continue

            value = constant_string(
                call.args[0]
            )

            if value is not None:
                titles.append(value)

        self.assertEqual(
            titles.count(
                "AttentiveSlides"
            ),
            1,
        )

    def test_sidebar_brand_is_removed(
        self,
    ) -> None:
        violations = []

        for call in self.calls:
            function_name = dotted_name(
                call.func
            )

            if not function_name.startswith(
                "st.sidebar."
            ):
                continue

            if not call.args:
                continue

            text = constant_string(
                call.args[0]
            )

            if text is None:
                continue

            normalized = (
                text.strip()
                .lstrip("#")
                .strip()
            )

            if normalized == "AttentiveSlides":
                violations.append(
                    {
                        "line": call.lineno,
                        "function": function_name,
                    }
                )

        self.assertEqual(
            violations,
            [],
        )

    def test_slide_workspace_label_is_removed(
        self,
    ) -> None:
        self.assertNotIn(
            "Slide workspace",
            self.source,
        )

    def test_main_render_order(
        self,
    ) -> None:
        main_function = self.functions[
            "main"
        ]

        required = [
            "_render_header",
            "_render_slide_selector",
            "_render_slide_workspace",
            "_render_navigation",
            "_render_manual_interaction",
            "_render_lower_workspace",
        ]

        positions: dict[
            str,
            list[int],
        ] = {
            name: []
            for name in required
        }

        for node in ast.walk(
            main_function
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            name = dotted_name(
                node.func
            )

            if name in positions:
                positions[name].append(
                    node.lineno
                )

        missing = [
            name
            for name, lines
            in positions.items()
            if not lines
        ]

        self.assertEqual(
            missing,
            [],
            (
                "Missing main render calls: "
                f"{missing}"
            ),
        )

        ordered_lines = [
            min(
                positions[name]
            )
            for name in required
        ]

        self.assertEqual(
            ordered_lines,
            sorted(
                ordered_lines
            ),
            (
                "Unexpected main render order: "
                f"{dict(zip(required, ordered_lines))}"
            ),
        )


    def test_current_slide_selector_keeps_key(
        self,
    ) -> None:
        function = self.functions[
            "_render_slide_selector"
        ]

        matches = []

        for call in ast.walk(
            function
        ):
            if not isinstance(
                call,
                ast.Call,
            ):
                continue

            if (
                dotted_name(
                    call.func
                ).split(".")[-1]
                != "selectbox"
            ):
                continue

            label = (
                constant_string(
                    call.args[0]
                )
                if call.args
                else None
            )

            matches.append(
                {
                    "label": label,
                    "key": keyword_string(
                        call,
                        "key",
                    ),
                }
            )

        self.assertIn(
            {
                "label": "Current slide",
                "key": (
                    "main_active_slide_id"
                ),
            },
            matches,
        )

    def test_navigation_buttons_keep_keys(
        self,
    ) -> None:
        function = self.functions[
            "_render_navigation"
        ]

        keys = set()

        for call in ast.walk(
            function
        ):
            if not isinstance(
                call,
                ast.Call,
            ):
                continue

            if (
                dotted_name(
                    call.func
                ).split(".")[-1]
                != "button"
            ):
                continue

            key = keyword_string(
                call,
                "key",
            )

            if key:
                keys.add(key)

        self.assertTrue(
            {
                "main_previous_slide_button",
                "main_next_slide_button",
            }.issubset(keys)
        )

    def test_interaction_workspace_has_three_columns(
        self,
    ) -> None:
        function = self.functions[
            "_render_manual_interaction"
        ]

        matches = []

        for call in ast.walk(
            function
        ):
            if not isinstance(
                call,
                ast.Call,
            ):
                continue

            if dotted_name(
                call.func
            ) != "st.columns":
                continue

            if not call.args:
                continue

            value = call.args[0]

            if (
                isinstance(
                    value,
                    (
                        ast.List,
                        ast.Tuple,
                    ),
                )
                and len(value.elts) == 3
            ):
                matches.append(
                    call.lineno
                )

        self.assertTrue(
            matches,
        )

    def test_xai_drawer_is_collapsed(
        self,
    ) -> None:
        function = self.functions[
            "_render_xai_drawer"
        ]

        matches = []

        for call in ast.walk(
            function
        ):
            if not isinstance(
                call,
                ast.Call,
            ):
                continue

            if (
                dotted_name(
                    call.func
                ).split(".")[-1]
                != "expander"
            ):
                continue

            label = (
                constant_string(
                    call.args[0]
                )
                if call.args
                else None
            )

            expanded_node = keyword_value(
                call,
                "expanded",
            )

            expanded = (
                expanded_node.value
                if isinstance(
                    expanded_node,
                    ast.Constant,
                )
                else None
            )

            matches.append(
                {
                    "label": label,
                    "expanded": expanded,
                }
            )

        self.assertEqual(
            matches,
            [
                {
                    "label": (
                        "Explainability (XAI)"
                    ),
                    "expanded": False,
                }
            ],
        )

    def test_xai_content_has_no_nested_expanders(
        self,
    ) -> None:
        function = self.functions[
            "_render_main_xai"
        ]

        violations = []

        for call in ast.walk(
            function
        ):
            if not isinstance(
                call,
                ast.Call,
            ):
                continue

            if (
                dotted_name(
                    call.func
                ).split(".")[-1]
                == "expander"
            ):
                violations.append(
                    call.lineno
                )

        self.assertEqual(
            violations,
            [],
        )

    def test_no_arrow_backed_widgets(
        self,
    ) -> None:
        forbidden = {
            "dataframe",
            "data_editor",
            "table",
        }

        violations = []

        for call in self.calls:
            function_type = (
                dotted_name(
                    call.func
                ).split(".")[-1]
            )

            if function_type in forbidden:
                violations.append(
                    {
                        "line": call.lineno,
                        "function": function_type,
                    }
                )

        self.assertEqual(
            violations,
            [],
        )


if __name__ == "__main__":
    unittest.main()
