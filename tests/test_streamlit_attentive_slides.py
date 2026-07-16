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

    def test_runtime_data_dir_is_environment_configurable(
        self,
    ) -> None:
        self.assertIn(
            '"ATTENTIVE_RUNTIME_DATA_DIR"',
            self.source,
        )

    def test_runtime_data_dir_defaults_to_xdg_user_data(
        self,
    ) -> None:
        self.assertIn(
            '"XDG_DATA_HOME"',
            self.source,
        )
        self.assertIn(
            'Path.home() / ".local" / "share"',
            self.source,
        )
        self.assertNotIn("/root/autodl-tmp", self.source)

    def test_single_main_title(
        self,
    ) -> None:
        header = self.function_source("_render_header")
        self.assertEqual(
            header.count(
                '<span class="attentive-top-title">AttentiveSlides</span>'
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
            "_render_slide_workspace",
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
        workspace = self.function_source("_render_slide_workspace")
        self.assertLess(
            workspace.index("_render_slide_selector(browser)"),
            workspace.index("_render_navigation(browser, view)"),
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
        self.assertIn('event == "mounted"', source)
        self.assertIn('event == "disabled"', source)
        self.assertIn('event != "manual_selection"', source)
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

    def test_live_fragment_does_not_receive_component_geometry(self) -> None:
        periodic = self.function_source("_render_live_periodic")
        manual = self.function_source("_render_manual_interaction")
        consume = self.function_source("_consume_live_proposal")

        self.assertNotIn("SlideViewportGeometry", self.source)
        self.assertNotIn("geometry:", periodic)
        self.assertNotIn("geometry=", manual)
        self.assertIn("latest_geometry_for", consume)

    def test_main_contains_no_global_llm_checkbox_or_deck_batch_action(self) -> None:
        self.assertNotIn("main_llm_aoi_enabled", self.source)
        self.assertNotIn("main_process_deck_llm_aoi", self.source)
        self.assertNotIn("Process entire deck with LLM", self.source)
        self.assertNotIn("prepare_llm_deck", self.source)
        self.assertNotIn("_render_llm_aoi_opt_in", self.functions)
        self.assertNotIn("_render_llm_aoi_deck_batch", self.functions)

    def test_current_slide_action_is_available_without_global_opt_in(self) -> None:
        source = self.function_source("_render_current_slide_llm_aoi_action")
        self.assertIn("main_uploaded_deck_id", source)
        self.assertNotIn("main_llm_aoi_enabled", source)
        self.assertIn("Enhance this slide with LLM", source)
        self.assertIn("Retry this slide with LLM", source)
        self.assertIn("main_process_current_llm_aoi", source)

    def test_eligible_slide_renders_compact_aoi_and_visual_status(self) -> None:
        source = self.function_source("_render_current_slide_llm_aoi_action")
        self.assertIn("LLM-enhanced ·", source)
        self.assertIn("AOIs ·", source)
        self.assertIn("visual notes", source)

    def test_invalid_visual_context_status_does_not_hide_valid_llm_aoi_status(self) -> None:
        source = self.function_source("_render_current_slide_llm_aoi_action")
        self.assertIn('visual_status == "invalid"', source)
        self.assertIn("visual context unavailable", source)
        self.assertLess(
            source.index("LLM-enhanced ·"),
            source.index("visual context unavailable"),
        )

    def test_production_live_graph_has_no_second_tutor_path(self) -> None:
        source = self.function_source("build_main_live_resources")

        self.assertIn("ActiveDeckSlideProvider", source)
        self.assertIn("ProposalTurnRunner", source)
        self.assertIn('aggregation_key="gaze_grid"', source)
        self.assertNotIn("RealSlideProvider", source)
        self.assertNotIn("LiveTurnRunner", source)
        self.assertNotIn("LiveTutorAdapter", source)
        self.assertNotIn("InteractionLogger", source)
        self.assertEqual(source.count("BrowserGazeSource()"), 1)
        self.assertIn("browser_gaze_source=observations", source)
        self.assertIn("observations=observations", source)

    def test_capture_is_outside_periodic_fragment(self) -> None:
        controls = self.function_source("_render_live_controls")
        periodic = self.function_source("_render_live_periodic")

        self.assertIn('st.iframe("/capture"', controls)
        self.assertNotIn("iframe", periodic)

    def test_omni_initial_target_uses_recent_stable_gaze(self) -> None:
        resources = self.function_source("build_main_live_resources")
        sync = self.function_source("_sync_main_live_voice_resources")
        target = self.function_source("_voice_target_binding")
        target_column = self.function_source("_render_target_column")

        self.assertIn("resolve_initial_omni_target", resources)
        self.assertIn("resolve_initial_target=resolve_initial_omni_target", resources)
        self.assertIn("allow_auto_gaze=preferences.engine is VoiceEngine.OMNI", sync)
        self.assertIn("AUTO_GAZE_TARGET_ID", target)
        self.assertIn('"Gaze AOI"', target_column)

    def test_main_live_resources_serve_the_formal_capture_component(self) -> None:
        source = self.function_source("build_main_live_resources")

        self.assertIn('"live_capture_component"', source)
        self.assertIn('"index.html"', source)
        self.assertIn("capture_html=capture_html", source)
        self.assertIn("media_stale_after_seconds=10.0", source)
        self.assertIn("inactive_after_seconds=12.0", source)

    def test_periodic_fragment_refreshes_live_transport_status(self) -> None:
        periodic = self.function_source("_render_live_periodic")

        self.assertIn("session_snapshot", periodic)
        self.assertIn("controller.state.value", periodic)
        self.assertIn("Media:", periodic)
        self.assertIn("Local gaze:", periodic)
        self.assertIn("gaze_fresh", periodic)

    def test_live_debug_bridge_uses_existing_state_inside_fragment(
        self,
    ) -> None:
        periodic = self.function_source("_render_live_periodic")
        workspace = self.function_source("_render_slide_workspace")
        self.assertIn("resolve_live_debug_aoi_id", periodic)
        self.assertIn("render_live_debug_bridge", periodic)
        self.assertIn("main_live_proposal", periodic)
        self.assertIn("main_confirmed_interaction", periodic)
        self.assertIn("clear_match", periodic)
        self.assertLess(
            periodic.index("_render_live_interaction"),
            periodic.index("render_live_debug_bridge"),
        )
        self.assertNotIn("main_live_debug_match", self.source)
        self.assertIn("clear_server_match", workspace)
        self.assertIn("main_live_proposal", workspace)
        self.assertIn("main_confirmed_interaction", workspace)

    def test_live_proposal_uses_point_revision_or_latest_grid_geometry(self) -> None:
        consume = self.function_source("_consume_live_proposal")

        self.assertIn('raw.gaze_source == "eyetheia_local"', consume)
        self.assertIn("raw.layout_revision == geometry.layout_revision", consume)
        self.assertIn("resolve_grid_target", consume)
        self.assertIn("latest_geometry_for", consume)

    def test_deck_and_slide_binding_clear_browser_observations(self) -> None:
        binding = self.function_source("_bind_main_live_resources")

        self.assertEqual(
            binding.count("resources.ingress.observations.clear()"),
            2,
        )

    def test_live_binding_reloads_browser_when_aoi_signature_changes(self) -> None:
        binding = self.function_source("_bind_main_live_resources")
        signature = self.function_source("_active_aoi_signature")

        self.assertIn("bound_aoi_signature", self.source)
        self.assertIn("aoi_changed", binding)
        self.assertIn("deck_changed or aoi_changed", binding)
        self.assertEqual(binding.count("resources.provider.set_browser(browser)"), 1)
        self.assertIn("resources.inbox.clear()", binding)
        self.assertIn("resources.snapshots.clear()", binding)
        self.assertIn("resources.ingress.observations.clear()", binding)
        self.assertIn('"aoi_profile"', signature)
        self.assertIn('"aoi_id"', signature)
        self.assertIn('"bbox"', signature)
        self.assertIn('"type"', signature)
        self.assertIn('"text"', signature)
        self.assertIn('"name"', signature)
        self.assertIn("hashlib.sha256", signature)

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

    def test_voice_runtime_extends_the_existing_single_resource_graph(self) -> None:
        builder = self.function_source("build_main_live_resources")
        self.assertEqual(builder.count("BrowserMediaSource()"), 1)
        self.assertEqual(builder.count("LiveIngressService("), 1)
        self.assertEqual(builder.count("SystemController("), 1)
        self.assertEqual(builder.count("VoiceOrchestrator("), 1)
        self.assertIn("voice_transport=voice", builder)
        self.assertIn("fatigue_worker=fatigue_worker", builder)

    def test_live_binding_synchronizes_voice_after_provider_binding(self) -> None:
        binding = self.function_source("_bind_main_live_resources")
        provider_position = binding.index("resources.provider.set_browser(browser)")
        voice_position = binding.index("_sync_main_live_voice_resources(resources, view)")
        self.assertLess(provider_position, voice_position)
        self.assertIn("resources.bound_voice_target_signature = None", binding)

    def test_omni_ui_preserves_three_column_interaction_layout(self) -> None:
        source = self.function_source("_render_omni_interaction")
        self.assertIn("st.columns", source)
        self.assertIn("[1.05, 1.20, 1.35]", source)
        self.assertIn("_render_voice_component(view)", source)

    def test_single_turn_tts_is_text_first_and_uses_the_cached_controller(self) -> None:
        result = self.function_source("_render_tutor_result")
        self.assertLess(
            result.index('st.markdown(\n        result["answer"]'),
            result.index("tts_controller.synthesize_once("),
        )
        self.assertIn("st.audio", result)
        self.assertIn('main_interaction_mode") == "Live"', result)
        self.assertIn('main_voice_engine") == "single_turn"', result)
        builder = self.function_source("build_main_live_resources")
        self.assertEqual(builder.count("SingleTurnTTSController("), 1)

    def test_fallback_transcript_reuses_proposal_confirmation_path(self) -> None:
        builder = self.function_source("build_main_live_resources")
        self.assertIn("runner.publish_transcript(transcript, target=target)", builder)
        self.assertNotIn("generate_main_tutor_response", builder)
        consumer = self.function_source("_consume_live_proposal")
        self.assertIn('raw.gaze_source == "voice_locked_target"', consumer)
        self.assertIn("preserved_manual_state", consumer)

    def test_live_confirmation_prefers_linked_visual_context_before_slide(self) -> None:
        confirmation = self.function_source("_store_live_confirmation")
        self.assertIn("_linked_visual_context_text(", confirmation)
        self.assertLess(
            confirmation.index("native_context\n        or linked_visual_context"),
            confirmation.index("or view.active_slide.slide_text.strip()"),
        )


if __name__ == "__main__":
    unittest.main()
