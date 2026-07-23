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
        review_branch = source[source.index('== "review"') : source.index("return")]
        self.assertNotIn("main_live_master_enabled", review_branch)
        self.assertNotIn("set_master_enabled", review_branch)
        self.assertNotIn("reconcile_once", review_branch)

    def test_review_does_not_reuse_interactive_slide_component(self):
        source = self.function_source("_render_review_workspace")
        self.assertIn("render_review_slide", source)
        self.assertIn("review_png_bytes", source)
        self.assertNotIn("render_slide_viewport", source)
        self.assertNotIn("parse_component_geometry", source)

    def test_review_uses_approved_summary_overview_and_detail_sections(self):
        source = self.function_source("_render_review_workspace")
        for label in (
            "Session Summary",
            "Slide Review",
            "Selected Slide Detail",
            "AOI DWELL",
            "Learner State Evidence",
        ):
            self.assertIn(label, source)
        self.assertIn("build_review_view(review)", source)
        self.assertNotIn('st.expander("Learner state"', source)
        self.assertNotIn('st.expander("Region times"', source)

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
        self.assertIn("resources.study_review.lifecycle()", source)
        self.assertIn('status != "idle"', source)
        self.assertIn("Finish the active Study", source)
        self.assertIn('main_review_session"] = review.session_id', source)
        self.assertNotIn("latest.json", source)

    def test_review_sections_follow_the_approved_information_hierarchy(self):
        source = self.function_source("_render_review_workspace")
        positions = [
            source.index(label)
            for label in (
                "Session Summary",
                "Slide Review",
                "Selected Slide Detail",
                "AOI DWELL",
                "Learner State Evidence",
            )
        ]
        self.assertEqual(positions, sorted(positions))
        for expected in (
            "Study time",
            "Interactions",
            "Mean engagement",
            "Top emotion",
            "Mean fatigue",
            "Distraction alerts",
            "Fatigue alerts",
            "Model estimates, not a diagnosis.",
        ):
            self.assertIn(expected, source)

    def test_review_state_empty_copy_keeps_gaze_review(self):
        source = self.function_source("_render_review_workspace")
        self.assertIn("build_review_view(review)", source)
        self.assertIn("No valid gaze captured", source)
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
            workspace.index("build_review_view(review)"),
            workspace.index("review.deck_id != view.deck_id"),
        )
        self.assertIn("_review_session_caption(review)", sidebar)
        self.assertIn("main_review_download_json", sidebar)
        self.assertIn("main_review_delete", sidebar)

    def test_live_sidebar_exposes_review_actions(self):
        controls = self.function_source("_render_live_controls")
        header = self.function_source("_render_header")
        self.assertIn("START STUDY", header)
        self.assertIn("END & REVIEW", header)
        self.assertIn("Open latest review", controls)
        self.assertIn('disabled=lifecycle.status != "idle"', controls)
        self.assertIn("load_warnings()", controls)

    def test_palette_changes_are_defensively_ignored_while_study_is_active(self):
        controls = self.function_source("_render_live_controls")
        review_sidebar = self.function_source("_render_review_sidebar")
        for source in (controls, review_sidebar):
            self.assertIn('lifecycle.status == "idle"', source)
            self.assertIn('{"active", "paused", "finish_pending"}', source)

    def test_study_buttons_follow_one_atomic_lifecycle_snapshot(self):
        source = self.function_source("_render_header")
        self.assertIn('key="main_start_study"', source)
        self.assertIn('lifecycle.status == "idle"', source)
        self.assertIn('key="main_end_study_review"', source)
        self.assertIn('disabled=lifecycle.status not in {', source)
        for status in ('"active"', '"paused"', '"finish_pending"'):
            self.assertIn(status, source)
        self.assertIn('args=(resources, lifecycle.deck_id or "")', source)
        self.assertNotIn("is_armed", source)

    def test_live_sidebar_preserves_authoritative_deck_mismatch(self):
        source = self.function_source("_render_live_controls")
        self.assertIn("lifecycle_deck_id = lifecycle.deck_id", source)
        self.assertIn("active_deck_mismatch", source)
        self.assertIn("Finish that Study before starting one for this deck", source)
        self.assertNotIn("Start new study with this deck", source)

    def test_review_lifecycle_errors_stay_inline(self):
        finish = self.function_source("_finish_study_review")
        start = self.function_source("_start_study_review")
        delete = self.function_source("_delete_selected_study_review")
        self.assertIn("RuntimeError", finish)
        self.assertIn("OSError", start)
        self.assertIn("RuntimeError", start)
        self.assertIn("OSError", delete)

    def test_study_and_review_navigation_preserves_preference_while_gating_service(self):
        start = self.function_source("_start_study_review")
        finish = self.function_source("_finish_study_review")
        opened = self.function_source("_open_latest_review")
        back = self.function_source("_back_to_study_workspace")
        for source in (start, finish, opened, back):
            self.assertNotIn('main_live_master_enabled"] =', source)
            self.assertNotIn("set_master_enabled", source)
            self.assertNotIn("reconcile_once", source)
        self.assertNotIn("quiesce", start)
        self.assertIn("service.quiesce", finish)
        self.assertIn("service.quiesce", opened)
        self.assertIn("service.resume_from_quiesce", back)
        self.assertIn('st.session_state.get("main_live_master_enabled"', back)

    def test_upload_uses_content_signature_and_single_action_state(self):
        upload = self.function_source("_render_upload_controls")
        signature = self.function_source("_uploaded_pdf_signature")
        self.assertEqual(upload.count("uploaded_file.getvalue()"), 1)
        self.assertIn("main_loaded_pdf_signature", upload)
        self.assertIn('key="main_load_pdf_button"', upload)
        self.assertIn('key="main_loaded_pdf_button"', upload)
        self.assertIn('"Loaded PDF"', upload)
        self.assertNotIn("main_upload_message", upload)
        self.assertNotIn("Use built-in demo deck", upload)
        self.assertEqual(upload.count("st.rerun()"), 1)
        self.assertLess(
            upload.index('"main_loaded_pdf_signature"'),
            upload.index("st.rerun()"),
        )
        self.assertIn("hashlib.sha256()", signature)
        self.assertIn('digest.update(b"\\0")', signature)

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

    def test_single_product_title_lives_in_sidebar_brand(
        self,
    ) -> None:
        header = self.function_source("_render_header")
        brand = self.function_source("_render_sidebar_brand")
        self.assertEqual(
            brand.count(
                '<span class="as-brand-name">AttentiveSlides</span>'
            ),
            1,
        )
        self.assertNotIn("AttentiveSlides", header)

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
            "_render_lower_workspace",
            "_render_manual_interaction",
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
        main_source = self.function_source("main")
        self.assertLess(
            main_source.index(
                "active_slide=view.active_slide"
            ),
            main_source.index("_render_slide_workspace("),
        )

    def test_review_detail_uses_one_centered_navigation_frame(self) -> None:
        review = self.function_source("_render_review_workspace")
        self.assertIn('key="main_review_slide_frame"', review)
        self.assertIn("active_slide=view.active_slide", review)
        self.assertEqual(review.count("with _centered_slide_width()"), 1)
        frame = review.index('key="main_review_slide_frame"')
        self.assertLess(frame, review.index("_render_navigation", frame))
        self.assertLess(frame, review.index("_render_review_text_fallback", frame))
        self.assertLess(frame, review.index("st.image", frame))

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
        self.assertEqual(len(slider_calls), 0)
        for key in (
            "main_slide_scale_down",
            "main_slide_scale_up",
            "main_slide_scale_fit",
        ):
            self.assertIn(key, source)
        self.assertIn("_adjust_slide_width", source)
        self.assertIn("_fit_slide_width", source)
        self.assertLess(
            source.index("_render_current_slide_llm_aoi_action"),
            source.index('key="main_slide_stage"'),
        )

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

    def test_transport_status_is_progressively_disclosed_outside_control(self) -> None:
        periodic = self.function_source("_render_live_periodic")
        controls = self.function_source("_render_live_controls")
        for token in (
            "session_snapshot",
            "controller.state.value",
            "gaze_fresh",
        ):
            self.assertNotIn(token, periodic)
            self.assertIn(token, controls)
        self.assertNotIn("Media:", periodic)
        self.assertNotIn("Local gaze:", periodic)

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
            periodic.index("_render_unified_interaction"),
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

        self.assertIn("_media_runtime_requested(live_resources)", interaction)
        self.assertIn("_render_unified_interaction", interaction)
        master_check = interaction.index("_media_runtime_requested(live_resources)")
        periodic = interaction.index("_render_live_periodic", master_check)
        inactive = interaction.index("_render_unified_interaction", periodic)

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

    def test_claim_evidence_map_is_display_only(
        self,
    ) -> None:
        renderer = self.function_source(
            "_render_claim_evidence_map"
        )
        main_xai = self.function_source(
            "_render_main_xai"
        )

        self.assertIn(
            "_render_claim_evidence_map(answer)",
            main_xai,
        )
        self.assertIn("Claim–Evidence Map", renderer)
        self.assertIn(
            "Structural provenance validation",
            renderer,
        )
        self.assertIn(
            "Semantic verification",
            renderer,
        )
        self.assertIn("st.container", renderer)
        self.assertIn("_render_records_table", renderer)

        for forbidden in (
            "st.session_state",
            "st.button",
            "st.expander",
            "_navigate_to_slide",
            "_retry_confirmed_turn",
            "_confirm",
            "_correct",
            "st.rerun",
        ):
            self.assertNotIn(forbidden, renderer)

    def test_multimodal_evidence_is_display_only(self) -> None:
        renderer = self.function_source(
            "_render_multimodal_evidence"
        )
        main_xai = self.function_source("_render_main_xai")
        snapshot = self.function_source(
            "_safe_live_proposal_xai_snapshot"
        )

        self.assertIn(
            "_render_multimodal_evidence(",
            main_xai,
        )
        self.assertIn(
            "Multimodal Evidence Decomposition",
            renderer,
        )
        self.assertIn("Read-only alternatives", renderer)
        self.assertIn("Fusion status", renderer)
        self.assertIn("st.container", renderer)
        self.assertIn("_render_records_table", renderer)
        self.assertIn(".metric(", renderer)

        for forbidden in (
            "st.session_state",
            "st.button",
            "st.expander",
            "_navigate_to_slide",
            "_retry_confirmed_turn",
            "_store_live_confirmation",
            "_confirm",
            "_correct",
            "st.rerun",
        ):
            self.assertNotIn(forbidden, renderer)

        self.assertNotIn("__dict__", snapshot)
        for field in (
            "predicted_aoi_id",
            "target_confidence",
            "alternatives",
            "gaze_grid",
            "gaze_source",
            "stable_duration_sec",
            "layout_revision",
            "sensing_evidence",
        ):
            self.assertIn(f'"{field}"', snapshot)
        for forbidden in (
            "interaction_id",
            "transcript",
            "raw_media",
            "landmarks",
            "request_id",
            "prompt",
        ):
            self.assertNotIn(f'"{forbidden}"', snapshot)

    def test_layout_discard_reasons_are_retained_for_xai(self) -> None:
        consumer = self.function_source("_consume_live_proposal")

        self.assertIn(
            "current point-gaze evidence discarded",
            consumer,
        )
        self.assertIn(
            "gaze-grid evidence discarded",
            consumer,
        )
        self.assertIn("sensing_evidence=", consumer)

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

    def test_omni_completed_turns_are_forwarded_to_study_review(self) -> None:
        builder = self.function_source("build_main_live_resources")
        self.assertIn("def record_omni_turn", builder)
        self.assertIn("study_review.record_completed_interaction(", builder)
        self.assertIn("interaction_id=result.turn_id", builder)
        self.assertIn("deck_id=target.deck_id", builder)
        self.assertIn("slide_id=target.slide_id", builder)
        self.assertIn("on_turn_completed=record_omni_turn", builder)

    def test_finish_and_start_preserve_lifecycle_guards(self) -> None:
        finish = self.function_source("_finish_study_review")
        start = self.function_source("_start_study_review")
        self.assertEqual(finish.count("resources.study_review.finish("), 1)
        self.assertEqual(start.count("resources.study_review.start(deck_id)"), 1)
        self.assertIn('main_workspace_mode"] = "study"', start)
        self.assertNotIn("main_live_master_enabled", finish)
        self.assertNotIn("main_live_master_enabled", start)
        self.assertNotIn("delete(", start)

    def test_live_binding_synchronizes_voice_after_provider_binding(self) -> None:
        binding = self.function_source("_bind_main_live_resources")
        provider_position = binding.index("resources.provider.set_browser(browser)")
        voice_position = binding.index("_sync_main_live_voice_resources(resources, view)")
        self.assertLess(provider_position, voice_position)
        self.assertIn("resources.bound_voice_target_signature = None", binding)

    def test_all_flows_share_one_attention_and_voice_panel(self) -> None:
        source = self.function_source("_render_unified_interaction")
        self.assertIn("Attention and voice controls", source)
        self.assertIn("_render_voice_component(view, resources)", source)
        self.assertIn("_render_target_column(view)", source)
        self.assertIn("_render_intent_column(view)", source)
        self.assertNotIn("main_interaction_mode", source)

    def test_single_turn_tts_is_text_first_and_uses_the_cached_controller(self) -> None:
        result = self.function_source("_render_tutor_result")
        self.assertLess(
            result.index('st.markdown(result["answer"])'),
            result.index("resources.single_turn_tts.synthesize_once("),
        )
        self.assertIn("st.audio", result)
        self.assertIn("_media_runtime_requested(resources)", result)
        self.assertIn("_lifecycle_token_matches", result)
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

    def test_unrecognized_typed_text_falls_back_to_explain(self) -> None:
        resolver = self.function_source("_resolve_current_intent")
        self.assertIn('intent_input.source == "typed_text"', resolver)
        self.assertIn("and not resolution.recognized", resolver)
        self.assertIn('intent="explain"', resolver)
        self.assertIn("unrecognized typed text defaults to explain", resolver)

    def test_live_transcript_uses_proposal_scoped_widget_state(self) -> None:
        interaction = self.function_source("_render_unified_interaction")
        callback = self.function_source("_on_live_transcript_change")
        self.assertIn("main_live_transcript_editor_", interaction)
        self.assertIn("proposal.interaction_id", interaction)
        self.assertIn("on_change=_on_live_transcript_change", interaction)
        self.assertIn(
            'st.session_state["main_typed_command"] = str(transcript_value or "")',
            interaction,
        )
        self.assertIn(
            'str(st.session_state.get("main_typed_command") or "").strip()',
            interaction,
        )
        self.assertIn('st.session_state["main_typed_command"]', callback)


if __name__ == "__main__":
    unittest.main()
