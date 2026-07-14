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

        slider_calls = [
            node
            for node in ast.walk(function)
            if (
                isinstance(node, ast.Call)
                and dotted_name(node.func).split(".")[-1] == "slider"
            )
        ]
        self.assertEqual(len(slider_calls), 1)
        slider = slider_calls[0]
        self.assertEqual(constant_string(slider.args[0]), "Slide size")
        self.assertEqual(keyword_node(slider, "min_value").value, 50)
        self.assertEqual(keyword_node(slider, "max_value").value, 100)
        self.assertEqual(keyword_node(slider, "step").value, 5)
        self.assertEqual(
            keyword_string(slider, "key"),
            "main_slide_width_percent",
        )

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

        process_statement = next(
            index
            for index, names in enumerate(statement_calls)
            if "_render_current_slide_llm_aoi_action" in names
        )
        self.assertLess(process_statement, slider_statement)

    def test_llm_opt_in_precedes_browser_resolution_and_live_binding(self) -> None:
        statement_calls = [
            {
                dotted_name(node.func).split(".")[-1]
                for node in ast.walk(statement)
                if isinstance(node, ast.Call)
            }
            for statement in self.functions["main"].body
        ]
        checkbox = next(i for i, names in enumerate(statement_calls) if "_render_llm_aoi_opt_in" in names)
        resolve = next(i for i, names in enumerate(statement_calls) if "_resolve_active_browser" in names)
        signature = next(i for i, names in enumerate(statement_calls) if "_sync_active_aoi_signature" in names)
        bind = next(i for i, names in enumerate(statement_calls) if "_bind_main_live_resources" in names)
        self.assertLess(checkbox, resolve)
        self.assertLess(signature, bind)

    def test_llm_deck_batch_sidebar_contract_and_persistent_summary(self) -> None:
        function = self.functions["_render_llm_aoi_deck_batch"]
        source = self.function_source("_render_llm_aoi_deck_batch")

        built_in_guard = function.body[0]
        self.assertIsInstance(built_in_guard, ast.If)
        self.assertIn(
            "main_uploaded_deck_id",
            ast.get_source_segment(self.source, built_in_guard.test) or "",
        )
        self.assertTrue(
            any(isinstance(statement, ast.Return) for statement in built_in_guard.body)
        )

        batch_buttons = [
            node
            for node in ast.walk(function)
            if (
                isinstance(node, ast.Call)
                and dotted_name(node.func) == "st.sidebar.button"
                and keyword_string(node, "key") == "main_process_deck_llm_aoi"
            )
        ]
        self.assertEqual(len(batch_buttons), 1)
        batch_button = batch_buttons[0]
        self.assertEqual(
            constant_string(batch_button.args[0]),
            "Process entire deck with LLM",
        )
        self.assertEqual(keyword_string(batch_button, "width"), "stretch")
        disabled = keyword_node(batch_button, "disabled")
        self.assertIsNotNone(disabled)
        self.assertIn("main_llm_aoi_enabled", ast.unparse(disabled))
        self.assertTrue(ast.unparse(disabled).startswith("not "))

        self.assertIn("main_uploaded_deck_id", source)
        self.assertIn("browser.page_count", source)
        self.assertIn("pages will be processed sequentially", source)
        self.assertIn("cached successful pages are skipped", source)
        self.assertIn("main_process_deck_llm_aoi", source)
        self.assertIn("main_llm_aoi_enabled", source)
        self.assertIn("disabled", source)
        self.assertIn("st.sidebar.progress", source)
        self.assertIn("st.sidebar.empty", source)
        self.assertIn("completed / total", source)
        self.assertIn("status.caption", source)
        self.assertIn("workspace.prepare_llm_deck", source)
        self.assertIn("main_llm_aoi_deck_summary", source)
        self.assertIn("LLM AOI deck processing finished", source)
        self.assertIn("successful", source)
        self.assertIn("fallback", source)
        self.assertIn("skipped", source)
        self.assertIn("_reset_turn_state", source)
        self.assertIn("main_active_aoi_signature", source)
        self.assertEqual(source.count("st.rerun"), 1)

        uploaded_guard = source.index("main_uploaded_deck_id")
        button = source.index("main_process_deck_llm_aoi")
        self.assertLess(uploaded_guard, button)

        clear_summary = source.index(
            'st.session_state["main_llm_aoi_deck_summary"] = None'
        )
        prepare = source.index("workspace.prepare_llm_deck")
        store_summary = source.index(
            'st.session_state["main_llm_aoi_deck_summary"] = summary_message'
        )
        self.assertLess(clear_summary, prepare)
        self.assertLess(prepare, store_summary)

    def test_llm_deck_batch_renders_after_uploaded_browser_resolution(self) -> None:
        statement_calls = [
            {
                dotted_name(node.func).split(".")[-1]
                for node in ast.walk(statement)
                if isinstance(node, ast.Call)
            }
            for statement in self.functions["main"].body
        ]

        resolve = next(
            i for i, names in enumerate(statement_calls) if "_resolve_active_browser" in names
        )
        ensure = next(
            i for i, names in enumerate(statement_calls) if "_ensure_deck_state" in names
        )
        batch = next(
            i
            for i, names in enumerate(statement_calls)
            if "_render_llm_aoi_deck_batch" in names
        )
        self.assertLess(resolve, ensure)
        self.assertLess(ensure, batch)

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
