"""Static render contracts for the current Main UI."""

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


def constant_string(
    node: ast.AST | None,
) -> str | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
    ):
        return node.value

    return None


def keyword_node(
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
        keyword_node(
            call,
            name,
        )
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

    def function_source(
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

    def test_source_parses(
        self,
    ) -> None:
        self.assertIn(
            "main",
            self.functions,
        )

    def test_single_main_title(
        self,
    ) -> None:
        title_calls = []

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

            if node.args:
                title_calls.append(
                    constant_string(
                        node.args[0]
                    )
                )

        self.assertEqual(
            title_calls.count(
                "AttentiveSlides"
            ),
            1,
        )

    def test_thumbnail_selector_replaces_selectbox(
        self,
    ) -> None:
        function = self.functions[
            "_render_slide_selector"
        ]

        call_names = {
            dotted_name(node.func)
            .split(".")[-1]
            for node in ast.walk(
                function
            )
            if isinstance(
                node,
                ast.Call,
            )
        }

        self.assertNotIn(
            "selectbox",
            call_names,
        )

        self.assertIn(
            "button",
            call_names,
        )

        self.assertIn(
            "image",
            call_names,
        )

        self.assertNotIn(
            '"Current slide"',
            self.function_source(
                "_render_slide_selector"
            ),
        )

    def test_main_render_order(
        self,
    ) -> None:
        function = self.functions[
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

        positions = {
            name: []
            for name in required
        }

        for node in ast.walk(
            function
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
        )

        ordered = [
            min(
                positions[name]
            )
            for name in required
        ]

        self.assertEqual(
            ordered,
            sorted(ordered),
        )

    def test_slide_workspace_heading_removed(
        self,
    ) -> None:
        self.assertNotIn(
            "Slide workspace",
            self.source,
        )

    def test_navigation_keys_remain(
        self,
    ) -> None:
        function = self.functions[
            "_render_navigation"
        ]

        keys = {
            keyword_string(
                node,
                "key",
            )
            for node in ast.walk(
                function
            )
            if isinstance(
                node,
                ast.Call,
            )
        }

        self.assertTrue(
            {
                "main_previous_slide_button",
                "main_next_slide_button",
            }.issubset(keys)
        )

    def test_target_scope_has_two_modes(
        self,
    ) -> None:
        source = self.function_source(
            "_render_target_column"
        )

        self.assertIn(
            "main_target_scope",
            source,
        )

        whole_present = any(
            label in source
            for label in (
                "Whole slide",
                "Use whole slide",
            )
        )

        region_present = any(
            label in source
            for label in (
                "Manual region",
                "Select region",
            )
        )

        self.assertTrue(
            whole_present,
        )

        self.assertTrue(
            region_present,
        )

    def test_slide_workspace_uses_viewport_component(
        self,
    ) -> None:
        function = self.functions[
            "_render_slide_workspace"
        ]

        call_names = {
            dotted_name(node.func)
            .split(".")[-1]
            for node in ast.walk(
                function
            )
            if isinstance(
                node,
                ast.Call,
            )
        }

        source = self.function_source(
            "_render_slide_workspace"
        )

        self.assertIn(
            "render_slide_viewport",
            source,
        )
        self.assertIn("parse_component_geometry", source)
        self.assertNotIn("st_canvas", self.source)
        self.assertNotIn("streamlit_drawable_canvas", self.source)

    def test_production_live_graph_has_no_second_tutor_path(self) -> None:
        source = self.function_source("build_main_live_resources")

        self.assertIn("ActiveDeckSlideProvider", source)
        self.assertIn("ProposalTurnRunner", source)
        self.assertIn('aggregation_key="gaze_grid"', source)
        self.assertNotIn("RealSlideProvider", source)
        self.assertNotIn("LiveTurnRunner", source)
        self.assertNotIn("LiveTutorAdapter", source)
        self.assertNotIn("InteractionLogger", source)

    def test_capture_is_outside_periodic_fragment(self) -> None:
        controls = self.function_source("_render_live_controls")
        periodic = self.function_source("_render_live_periodic")

        self.assertIn('st.iframe("/capture"', controls)
        self.assertNotIn("iframe", periodic)

    def test_periodic_fragment_refreshes_live_transport_status(self) -> None:
        periodic = self.function_source("_render_live_periodic")

        self.assertIn("session_snapshot", periodic)
        self.assertIn("controller.state.value", periodic)
        self.assertIn("Media:", periodic)

    def test_live_fragment_runs_only_while_media_is_enabled(self) -> None:
        interaction = self.function_source("_render_manual_interaction")

        self.assertIn("main_live_master_enabled", interaction)
        self.assertIn("_render_live_interaction", interaction)
        master_check = interaction.index("main_live_master_enabled")
        periodic = interaction.index("_render_live_periodic", master_check)
        inactive = interaction.index("_render_live_interaction", periodic)

        self.assertLess(master_check, periodic)
        self.assertLess(periodic, inactive)

    def test_live_fragment_callbacks_do_not_force_app_reruns(self) -> None:
        manual = self.function_source("_enable_live_manual_region")
        overlay = self.function_source("_on_live_overlay_change")

        self.assertNotIn("st.rerun", manual)
        self.assertNotIn("st.rerun", overlay)

    def test_xai_drawer_is_collapsed(
        self,
    ) -> None:
        function = self.functions[
            "_render_xai_drawer"
        ]

        matches = []

        for node in ast.walk(
            function
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
                != "expander"
            ):
                continue

            label = (
                constant_string(
                    node.args[0]
                )
                if node.args
                else None
            )

            expanded = keyword_node(
                node,
                "expanded",
            )

            matches.append(
                (
                    label,
                    (
                        expanded.value
                        if isinstance(
                            expanded,
                            ast.Constant,
                        )
                        else None
                    ),
                )
            )

        self.assertEqual(
            matches,
            [
                (
                    "Explainability (XAI)",
                    False,
                )
            ],
        )

    def test_no_arrow_backed_tables(
        self,
    ) -> None:
        forbidden = {
            "dataframe",
            "data_editor",
            "table",
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

            call_name = (
                dotted_name(
                    node.func
                ).split(".")[-1]
            )

            if call_name in forbidden:
                violations.append(
                    (
                        call_name,
                        node.lineno,
                    )
                )

        self.assertEqual(
            violations,
            [],
        )


if __name__ == "__main__":
    unittest.main()
