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

    def test_main_has_explicit_study_review_branch(self):
        source = self.function_source("main")
        self.assertIn("main_workspace_mode", source)
        self.assertIn('== "review"', source)
        self.assertIn("_render_review_workspace", source)
        self.assertIn("_render_review_sidebar", source)

    def test_review_does_not_reuse_interactive_slide_component(self):
        source = self.function_source("_render_review_workspace")
        self.assertIn("render_review_slide", source)
        self.assertIn("review_png_bytes", source)
        self.assertNotIn("render_slide_viewport", source)
        self.assertNotIn("parse_component_geometry", source)

    def test_review_is_minimal_and_region_times_are_collapsed(self):
        source = self.function_source("_render_review_workspace")
        self.assertIn("Valid gaze", source)
        self.assertIn("Data coverage", source)
        self.assertIn('st.expander("Learner state", expanded=False)', source)
        self.assertIn("Region times", source)
        self.assertIn("expanded=False", source)
        self.assertNotIn("Most attended", source)
        self.assertNotIn("Least attended", source)

    def test_review_history_selector_uses_stable_session_ids_newest_first(self):
        source = self.function_source("_render_review_sidebar")
        self.assertIn("resources.study_review.list_sessions()", source)
        self.assertIn("options=session_ids", source)
        self.assertIn('key="main_review_session"', source)
        self.assertIn("on_change=_on_review_option_change", source)
        self.assertIn('args=("session",)', source)
        self.assertIn("_format_review_session_option", source)

    def test_review_history_selection_does_not_arm_or_replace_collection(self):
        selected = self.function_source("_selected_study_review")
        changed = self.function_source("_on_review_option_change")
        self.assertIn("resources.study_review.get", selected)
        self.assertNotIn("start_new", selected)
        self.assertNotIn("start_new", changed)
        self.assertNotIn("main_live_master_enabled", selected)
        self.assertNotIn("main_live_master_enabled", changed)

    def test_selected_session_delete_is_confirmed_and_non_arming(self):
        sidebar = self.function_source("_render_review_sidebar")
        delete = self.function_source("_delete_selected_study_review")
        self.assertIn('key="main_review_delete_confirm"', sidebar)
        self.assertIn("on_change=_on_review_option_change", sidebar)
        self.assertIn('key="main_review_delete"', sidebar)
        self.assertEqual(delete.count("resources.study_review.delete("), 1)
        self.assertIn("OSError", delete)
        self.assertIn("KeyError", delete)
        self.assertNotIn("start_new", delete)
        self.assertNotIn('main_live_master_enabled"] = True', delete)

    def test_review_warnings_do_not_hide_valid_history(self):
        source = self.function_source("_render_review_sidebar")
        self.assertLess(source.index("list_sessions()"), source.index("load_warnings()"))
        self.assertIn("Saved review warning", source)

    def test_open_latest_selects_newest_valid_review(self):
        source = self.function_source("_open_latest_review")
        self.assertEqual(source.count("resources.study_review.latest()"), 1)
        self.assertIn('main_review_session"] = review.session_id', source)
        self.assertNotIn("latest.json", source)

    def test_review_state_summary_follows_gaze_coverage_and_precedes_regions(self):
        source = self.function_source("_render_review_workspace")
        coverage = source.index("Valid gaze")
        learner = source.index('st.expander("Learner state"')
        regions = source.index('st.expander("Region times"')
        self.assertLess(coverage, learner)
        self.assertLess(learner, regions)
        for expected in (
            "Study time",
            "Interactions",
            "Engaged",
            "Top emotion",
            "Fatigue",
            "Alerts: distraction",
            "Model estimates; not a diagnosis.",
        ):
            self.assertIn(expected, source)
        for forbidden in (
            "AOI entries",
            "Cognitive load",
            "Emotion table",
            "Emotion alert",
        ):
            self.assertNotIn(forbidden, source)

    def test_review_state_empty_copy_keeps_gaze_review(self):
        source = self.function_source("_render_review_workspace")
        self.assertIn(
            "No learner-state estimate was available for this slide",
            source,
        )
        self.assertIn("render_review_slide", source)
        self.assertIn("Show heatmap", source)

    def test_review_json_exports_integrated_selected_session(self):
        source = self.function_source("_render_review_sidebar")
        self.assertIn("review.to_json()", source)
        self.assertIn('f"study_review_{review.session_id}.json"', source)
        self.assertNotIn("gaze_review.to_json", source)

    def test_missing_deck_still_shows_session_metadata_and_sidebar_actions(self):
        workspace = self.function_source("_render_review_workspace")
        sidebar = self.function_source("_render_review_sidebar")
        self.assertLess(
            workspace.index("_review_session_caption(review)"),
            workspace.index("review.deck_id != view.deck_id"),
        )
        self.assertIn("main_review_download_json", sidebar)
        self.assertIn("main_review_delete", sidebar)

    def test_live_sidebar_exposes_review_actions(self):
        source = self.function_source("_render_live_controls")
        self.assertIn("End study & review", source)
        self.assertIn("Open latest review", source)
        self.assertIn("is_armed()", source)
        self.assertIn("load_warnings()", source)

    def test_end_review_retains_active_or_armed_overwrite_guard(self):
        source = self.function_source("_render_live_controls")
        button = source.index('"End study & review"')
        guard = source.rfind(
            "resources.study_review.has_active()",
            0,
            button,
        )
        armed = source.rfind(
            "enabled and resources.study_review.is_armed()",
            0,
            button,
        )
        self.assertGreater(guard, -1)
        self.assertGreater(armed, guard)

    def test_live_sidebar_requires_explicit_new_study_after_deck_change(self):
        source = self.function_source("_render_live_controls")
        self.assertIn("active_deck_id()", source)
        self.assertIn("active_deck_mismatch", source)
        self.assertIn("Start new study with this deck", source)

    def test_review_lifecycle_errors_stay_inline(self):
        finish = self.function_source("_finish_study_review")
        start_new = self.function_source("_start_new_study_review")
        delete = self.function_source("_delete_selected_study_review")
        self.assertIn("RuntimeError", finish)
        self.assertIn("OSError", start_new)
        self.assertIn("RuntimeError", start_new)
        self.assertIn("OSError", delete)

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
        self.assertIn("learner_state_worker=learner_state_worker", builder)

    def test_learner_state_resources_follow_integrated_build_order(self) -> None:
        builder = self.function_source("build_main_live_resources")
        study = builder.index("study_review = StudyReviewStore(")
        store = builder.index("learner_state_store = LearnerStateStore()")
        worker = builder.index("learner_state_worker = LearnerStateWorker(")
        controller = builder.index("controller = SystemController(")
        ingress = builder.index("ingress = FallbackMediaIngress(")
        self.assertLess(study, store)
        self.assertLess(store, worker)
        self.assertLess(worker, controller)
        self.assertLess(controller, ingress)
        self.assertIn("on_snapshot=study_review.accept_learner_state", builder)
        self.assertIn("study_review=study_review", builder)
        self.assertIn("media_stale_after_seconds=10.0", builder)
        self.assertIn("inactive_after_seconds=12.0", builder)

    def test_emotieff_paths_are_environment_configurable_with_local_defaults(self) -> None:
        builder = self.function_source("build_main_live_resources")
        self.assertIn('"ATTENTIVE_EMOTIEFF_MODEL_PATH"', builder)
        self.assertIn("enet_b0_8_best_vgaf_features.ts", builder)
        self.assertIn('"ATTENTIVE_EMOTIEFF_ENGAGEMENT_PATH"', builder)
        self.assertIn("engagement_single_attention.pt", builder)
        self.assertIn('"ATTENTIVE_EMOTIEFF_DEVICE", "cuda"', builder)

    def test_live_binding_sets_worker_and_review_context_before_capture(self) -> None:
        binding = self.function_source("_bind_main_live_resources")
        self.assertIn(
            "resources.learner_state_worker.set_context(view.deck_id, view.active_slide_id)",
            binding,
        )
        self.assertIn(
            "resources.study_review.set_context(view.deck_id, view.active_slide_id)",
            binding,
        )
        self.assertIn("resources.study_review.register_slide(", binding)

    def test_successful_turn_records_existing_nested_interaction_once(self) -> None:
        record = self.function_source("_record_completed_turn")
        self.assertLess(
            record.index("upsert_conversation_turn("),
            record.index("resources.study_review.record_completed_interaction("),
        )
        self.assertIn(
            'interaction = st.session_state["main_confirmed_interaction"]["interaction"]',
            record,
        )
        self.assertIn('interaction_id=str(interaction["interaction_id"])', record)
        self.assertIn('deck_id=str(interaction["deck_id"])', record)
        self.assertIn('slide_id=int(interaction["slide_id"])', record)
        self.assertNotIn("uuid", record)

    def test_finish_and_start_new_preserve_lifecycle_guards(self) -> None:
        finish = self.function_source("_finish_study_review")
        start_new = self.function_source("_start_new_study_review")
        self.assertEqual(finish.count("resources.study_review.finish("), 1)
        self.assertLess(
            finish.index("resources.study_review.finish("),
            finish.index('main_live_master_enabled"] = False'),
        )
        self.assertIn("resources.study_review.start_new()", start_new)
        self.assertIn('main_workspace_mode"] = "study"', start_new)
        self.assertIn('main_live_master_enabled"] = False', start_new)
        self.assertNotIn("delete(", start_new)

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
