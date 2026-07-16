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

    def test_navigation_is_embedded_in_slide_workspace(
        self,
    ) -> None:
        workspace_function = self.functions[
            "_render_slide_workspace"
        ]

        positions = {}

        for node in ast.walk(
            workspace_function
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
                "_render_navigation",
                "render_slide_viewport",
            }:
                positions[name] = (
                    node.lineno
                )

        self.assertIn(
            "_render_navigation",
            positions,
        )

        self.assertIn(
            "render_slide_viewport",
            positions,
        )

        self.assertLess(
            positions[
                "_render_navigation"
            ],
            positions[
                "render_slide_viewport"
            ],
        )

    def test_learner_reminder_is_fixed_out_of_control_row_flow(self) -> None:
        workspace = self.source_of("_render_slide_workspace")
        self.assertLess(
            workspace.index('with st.popover(\n                "Learner state"'),
            workspace.index("_render_learner_state_alert_periodic"),
        )
        self.assertIn('key="main_learner_state_reminder_slot"', workspace)
        for contract in (
            ".st-key-main_learner_state_reminder_slot",
            "height: 0 !important",
            "min-height: 0 !important",
            "overflow: visible !important",
            "position: fixed",
            "top: 0.45rem",
            "z-index: 1000001",
        ):
            self.assertIn(contract, self.source)

    def test_built_in_missing_image_uses_centered_16_by_9_placeholder(self) -> None:
        workspace = self.source_of("_render_slide_workspace")
        placeholder = self.source_of("_render_builtin_slide_placeholder")
        self.assertIn('view.deck_id == "mock_deck"', workspace)
        self.assertIn("not view.active_slide.image_available", workspace)
        self.assertLess(
            workspace.index("_render_builtin_slide_placeholder()"),
            workspace.index("render_slide_viewport("),
        )
        self.assertIn('st.session_state["main_slide_width_percent"]', placeholder)
        self.assertIn("[margin, width_percent, margin]", placeholder)
        self.assertIn("attentive-built-in-stage", placeholder)
        self.assertIn("AttentiveSlides", placeholder)
        self.assertIn(
            "Select a slide region, state your learning goal, and receive a grounded tutor response.",
            placeholder,
        )
        self.assertNotIn("slide_text", placeholder)
        self.assertNotIn("Slide {", placeholder)
        self.assertIn("aspect-ratio: 16 / 9", self.source)

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

    def test_viewport_component_replaces_region_sliders(
        self,
    ) -> None:
        function = self.functions[
            "_render_slide_workspace"
        ]
        calls = self.calls_of(
            "_render_slide_workspace"
        )

        slider_calls = [
            call
            for call in calls
            if (
                dotted_name(
                    call.func
                ).split(".")[-1]
                == "slider"
            )
        ]

        self.assertEqual(
            len(slider_calls),
            1,
        )
        slider = slider_calls[0]
        self.assertEqual(slider.args[0].value, "Slide size")
        keywords = {
            keyword.arg: keyword.value.value
            for keyword in slider.keywords
            if (
                keyword.arg is not None
                and isinstance(keyword.value, ast.Constant)
            )
        }
        self.assertEqual(keywords["min_value"], 50)
        self.assertEqual(keywords["max_value"], 100)
        self.assertEqual(keywords["step"], 5)
        self.assertEqual(keywords["key"], "main_slide_width_percent")

        statement_calls = [
            {
                dotted_name(node.func).split(".")[-1]
                for node in ast.walk(statement)
                if isinstance(node, ast.Call)
            }
            for statement in function.body
        ]
        slider_statement = next(
            index
            for index, names in enumerate(statement_calls)
            if "slider" in names
        )
        render_statement = next(
            index
            for index, names in enumerate(statement_calls)
            if "render_slide_viewport" in names
        )
        self.assertEqual(render_statement, slider_statement + 1)

        self.assertIn(
            "render_slide_viewport",
            self.source_of(
                "_render_slide_workspace"
            ),
        )
        self.assertNotIn("st_canvas", self.source)

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
