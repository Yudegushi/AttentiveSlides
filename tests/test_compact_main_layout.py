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
        cls.css = Path("modules/ui/workspace.css").read_text(encoding="utf-8")

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

    def test_learner_state_stays_in_the_primary_slide_actions(self) -> None:
        workspace = self.source_of("_render_slide_workspace")
        self.assertLess(
            workspace.index('with st.popover(\n                "Learner State"'),
            workspace.index('key="main_slide_scale_down"'),
        )
        self.assertIn("_render_learner_state_contents_periodic", workspace)

    def test_built_in_missing_image_uses_centered_16_by_9_placeholder(self) -> None:
        workspace = self.source_of("_render_slide_workspace")
        placeholder = self.source_of("_render_builtin_slide_placeholder")
        self.assertIn('view.deck_id == "attentiveslides_deck"', workspace)
        self.assertIn("not view.active_slide.image_available", workspace)
        self.assertLess(
            workspace.index("_render_builtin_slide_placeholder()"),
            workspace.index("render_slide_viewport("),
        )
        width_helper = self.source_of("_centered_slide_width")
        self.assertIn('st.session_state["main_slide_width_percent"]', width_helper)
        self.assertIn("[gutter, width_percent, gutter]", width_helper)
        self.assertIn("attentive-built-in-stage", placeholder)
        self.assertIn("AttentiveSlides", placeholder)
        self.assertIn(
            "Select a slide region, state your learning goal, and receive a grounded tutor response.",
            placeholder,
        )
        self.assertNotIn("slide_text", placeholder)
        self.assertNotIn("Slide {", placeholder)
        self.assertIn("aspect-ratio: 16 / 9", self.css)

    def test_interaction_area_uses_the_approved_two_column_working_row(
        self,
    ) -> None:
        matches = []

        for call in self.calls_of(
            "main"
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
                and len(argument.elts) == 2
            ):
                values = [
                    item.value
                    for item in argument.elts
                    if isinstance(item, ast.Constant)
                ]
                if values == [1.0, 0.33]:
                    matches.append(call.lineno)

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

        self.assertEqual(len(slider_calls), 0)
        workspace = self.source_of("_render_slide_workspace")
        for key in (
            "main_slide_scale_down",
            "main_slide_scale_up",
            "main_slide_scale_fit",
        ):
            self.assertIn(key, workspace)
        self.assertIn("_adjust_slide_width", workspace)
        self.assertIn("_fit_slide_width", workspace)
        self.assertLess(
            workspace.index('key="main_slide_toolbar"'),
            workspace.index('key="main_slide_stage"'),
        )
        self.assertIn("render_slide_viewport", workspace)
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
