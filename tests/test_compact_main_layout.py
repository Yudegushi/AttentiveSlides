"""Static contracts for the compact Main UI layout."""

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

    return ""


class TestCompactMainLayout(
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

    def source_of(
        self,
        name: str,
    ) -> str:
        self.assertIn(
            name,
            self.functions,
        )

        return ast.get_source_segment(
            self.source,
            self.functions[name],
        ) or ""

    def calls_of(
        self,
        name: str,
    ) -> list[ast.Call]:
        return [
            node
            for node in ast.walk(
                self.functions[name]
            )
            if isinstance(
                node,
                ast.Call,
            )
        ]

    def test_thumbnail_strip_is_clickable(
        self,
    ) -> None:
        calls = self.calls_of(
            "_render_slide_selector"
        )

        call_names = {
            dotted_name(
                call.func
            ).split(".")[-1]
            for call in calls
        }

        self.assertIn(
            "button",
            call_names,
        )

        self.assertIn(
            "image",
            call_names,
        )

        self.assertNotIn(
            "selectbox",
            call_names,
        )

    def test_current_slide_label_removed(
        self,
    ) -> None:
        self.assertNotIn(
            '"Current slide"',
            self.source_of(
                "_render_slide_selector"
            ),
        )

    def test_slide_workspace_label_removed(
        self,
    ) -> None:
        self.assertNotIn(
            "Slide workspace",
            self.source,
        )

    def test_slide_precedes_navigation(
        self,
    ) -> None:
        main_function = self.functions[
            "main"
        ]

        positions = {}

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

            if name in {
                "_render_slide_workspace",
                "_render_navigation",
            }:
                positions[name] = (
                    node.lineno
                )

        self.assertIn(
            "_render_slide_workspace",
            positions,
        )

        self.assertIn(
            "_render_navigation",
            positions,
        )

        self.assertLess(
            positions[
                "_render_slide_workspace"
            ],
            positions[
                "_render_navigation"
            ],
        )

    def test_interaction_area_has_three_columns(
        self,
    ) -> None:
        matches = []

        for call in self.calls_of(
            "_render_manual_interaction"
        ):
            if dotted_name(
                call.func
            ) != "st.columns":
                continue

            if not call.args:
                continue

            argument = call.args[0]

            if (
                isinstance(
                    argument,
                    (
                        ast.List,
                        ast.Tuple,
                    ),
                )
                and len(argument.elts) == 3
            ):
                matches.append(
                    call.lineno
                )

        self.assertTrue(
            matches,
        )

    def test_region_sliders_are_not_rendered(
        self,
    ) -> None:
        calls = self.calls_of(
            "_render_manual_canvas"
        )

        slider_calls = [
            call.lineno
            for call in calls
            if (
                dotted_name(
                    call.func
                ).split(".")[-1]
                == "slider"
            )
        ]

        self.assertEqual(
            slider_calls,
            [],
        )

        self.assertIn(
            "st_canvas",
            self.source_of(
                "_render_manual_canvas"
            ),
        )

    def test_xai_drawer_is_collapsed(
        self,
    ) -> None:
        source = self.source_of(
            "_render_xai_drawer"
        )

        self.assertIn(
            "Explainability (XAI)",
            source,
        )

        self.assertIn(
            "expanded=False",
            source,
        )


if __name__ == "__main__":
    unittest.main()
