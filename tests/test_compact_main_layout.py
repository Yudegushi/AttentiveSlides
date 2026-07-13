"""Static tests for the compact learner-facing Main UI layout."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)


def dotted_name(node: ast.AST) -> str:
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


def keyword_string(
    call: ast.Call,
    name: str,
) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != name:
            continue

        value = keyword.value

        if (
            isinstance(
                value,
                ast.Constant,
            )
            and isinstance(
                value.value,
                str,
            )
        ):
            return value.value

    return None


class TestCompactMainLayout(
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

    def test_sidebar_brand_is_removed(
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

            name = dotted_name(
                node.func
            )

            if not name.startswith(
                "st.sidebar."
            ):
                continue

            if not node.args:
                continue

            value = node.args[0]

            if (
                isinstance(
                    value,
                    ast.Constant,
                )
                and value.value
                == "AttentiveSlides"
            ):
                violations.append(
                    (
                        name,
                        node.lineno,
                    )
                )

        self.assertEqual(
            violations,
            [],
        )

    def test_main_title_is_retained(
        self,
    ) -> None:
        titles = []

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
            ) != "st.title":
                continue

            if not node.args:
                continue

            value = node.args[0]

            if isinstance(
                value,
                ast.Constant,
            ):
                titles.append(
                    value.value
                )

        self.assertIn(
            "AttentiveSlides",
            titles,
        )

    def test_main_render_order_is_compact(
        self,
    ) -> None:
        main_function = (
            self.functions["main"]
        )

        calls = [
            dotted_name(
                node.func
            )
            for node in ast.walk(
                main_function
            )
            if isinstance(
                node,
                ast.Call,
            )
        ]

        ordered = [
            "_render_header",
            "_render_slide_selector",
            "_render_slide_workspace",
            "_render_navigation",
            "_render_manual_interaction",
            "_render_lower_workspace",
        ]

        positions = [
            calls.index(name)
            for name in ordered
        ]

        self.assertEqual(
            positions,
            sorted(positions),
        )

    def test_slide_workspace_label_is_removed(
        self,
    ) -> None:
        self.assertNotIn(
            "Slide workspace",
            self.source,
        )

    def test_slide_selector_has_stable_key(
        self,
    ) -> None:
        selector = self.functions[
            "_render_slide_selector"
        ]

        keys = []

        for node in ast.walk(
            selector
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
                != "selectbox"
            ):
                continue

            keys.append(
                keyword_string(
                    node,
                    "key",
                )
            )

        self.assertIn(
            "main_active_slide_id",
            keys,
        )

    def test_interaction_uses_three_columns(
        self,
    ) -> None:
        function = self.functions[
            "_render_manual_interaction"
        ]

        found = False

        for node in ast.walk(
            function
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if dotted_name(
                node.func
            ) != "st.columns":
                continue

            if not node.args:
                continue

            value = node.args[0]

            if (
                isinstance(
                    value,
                    ast.List,
                )
                and len(value.elts) == 3
            ):
                found = True

        self.assertTrue(
            found,
        )

    def test_xai_has_one_collapsed_drawer(
        self,
    ) -> None:
        drawer = self.functions[
            "_render_xai_drawer"
        ]

        expanders = []
        xai_calls = 0

        for node in ast.walk(
            drawer
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if dotted_name(
                node.func
            ) == "st.expander":
                expanders.append(
                    node
                )

            if dotted_name(
                node.func
            ) == "_render_main_xai":
                xai_calls += 1

        self.assertEqual(
            len(expanders),
            1,
        )

        self.assertEqual(
            xai_calls,
            1,
        )

        expanded_values = [
            keyword.value
            for keyword
            in expanders[0].keywords
            if keyword.arg
            == "expanded"
        ]

        self.assertEqual(
            len(expanded_values),
            1,
        )

        self.assertIsInstance(
            expanded_values[0],
            ast.Constant,
        )

        self.assertIs(
            expanded_values[0].value,
            False,
        )

    def test_xai_renderer_has_no_nested_expanders(
        self,
    ) -> None:
        renderer = self.functions[
            "_render_main_xai"
        ]

        calls = {
            dotted_name(
                node.func
            )
            for node in ast.walk(
                renderer
            )
            if isinstance(
                node,
                ast.Call,
            )
        }

        self.assertNotIn(
            "st.expander",
            calls,
        )

        self.assertIn(
            "_xai_section",
            calls,
        )

    def test_lower_workspace_has_no_tabs_or_xai(
        self,
    ) -> None:
        lower = self.functions[
            "_render_lower_workspace"
        ]

        calls = {
            dotted_name(
                node.func
            )
            for node in ast.walk(
                lower
            )
            if isinstance(
                node,
                ast.Call,
            )
        }

        self.assertNotIn(
            "st.tabs",
            calls,
        )

        self.assertNotIn(
            "_render_main_xai",
            calls,
        )

    def test_slide_image_uses_stretch_width(
        self,
    ) -> None:
        function = self.functions[
            "_render_static_slide"
        ]

        widths = []

        for node in ast.walk(
            function
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if dotted_name(
                node.func
            ) != "st.image":
                continue

            widths.append(
                keyword_string(
                    node,
                    "width",
                )
            )

        self.assertIn(
            "stretch",
            widths,
        )


if __name__ == "__main__":
    unittest.main()
