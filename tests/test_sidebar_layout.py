"""Tests for the compact Main UI sidebar layout."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

STATE_PATH = Path(
    "modules/system/main_ui_state.py"
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


def string_keyword(
    call: ast.Call,
    name: str,
) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != name:
            continue

        if (
            isinstance(
                keyword.value,
                ast.Constant,
            )
            and isinstance(
                keyword.value.value,
                str,
            )
        ):
            return keyword.value.value

    return None


class TestSidebarLayout(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.app_source = (
            APP_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.state_source = (
            STATE_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.tree = ast.parse(
            cls.app_source,
            filename=str(APP_PATH),
        )

    def test_privacy_expander_is_collapsed(
        self,
    ) -> None:
        matches = []

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
            ) != "st.sidebar.expander":
                continue

            if not node.args:
                continue

            title = node.args[0]

            if not (
                isinstance(
                    title,
                    ast.Constant,
                )
                and title.value
                == "Privacy Status"
            ):
                continue

            expanded_value = None

            for keyword in node.keywords:
                if keyword.arg == "expanded":
                    expanded_value = (
                        keyword.value
                    )

            matches.append(
                expanded_value
            )

        self.assertEqual(
            len(matches),
            1,
        )

        self.assertIsInstance(
            matches[0],
            ast.Constant,
        )

        self.assertIs(
            matches[0].value,
            False,
        )

    def test_history_limit_slider_is_absent(
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

            if (
                dotted_name(
                    node.func
                ).split(".")[-1]
                != "slider"
            ):
                continue

            if (
                string_keyword(
                    node,
                    "key",
                )
                == "main_history_max_items"
            ):
                violations.append(
                    node.lineno
                )

        self.assertEqual(
            violations,
            [],
        )

        self.assertNotIn(
            '"Recent turns sent to tutor"',
            self.app_source,
        )

    def test_history_limit_defaults_to_four(
        self,
    ) -> None:
        self.assertRegex(
            self.state_source,
            re.compile(
                r'''
                "main_history_max_items"
                \s*:\s*4
                ''',
                re.VERBOSE,
            ),
        )

    def test_app_forces_history_limit_to_four(
        self,
    ) -> None:
        found = False

        for node in ast.walk(
            self.tree
        ):
            if not isinstance(
                node,
                ast.Assign,
            ):
                continue

            if not (
                isinstance(
                    node.value,
                    ast.Constant,
                )
                and node.value.value == 4
            ):
                continue

            for target in node.targets:
                if not isinstance(
                    target,
                    ast.Subscript,
                ):
                    continue

                if dotted_name(
                    target.value
                ) != "st.session_state":
                    continue

                slice_value = target.slice

                if (
                    isinstance(
                        slice_value,
                        ast.Constant,
                    )
                    and slice_value.value
                    == "main_history_max_items"
                ):
                    found = True

        self.assertTrue(
            found,
        )

    def test_system_status_has_two_rows(
        self,
    ) -> None:
        """Stage 3 delegates the 2x2 status grid to the browser component."""

        from pathlib import Path

        app_source = Path(
            "apps/"
            "streamlit_attentive_slides.py"
        ).read_text(
            encoding="utf-8"
        )

        component_source = Path(
            "modules/media/"
            "microphone_component/"
            "index.html"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "render_sidebar_device_controls",
            app_source,
        )

        start = component_source.index(
            "  function renderDeviceView() {"
        )

        end = component_source.index(
            "  function renderPushToTalkView() {",
            start,
        )

        device_block = component_source[
            start:end
        ]

        self.assertIn(
            'data-testid="system-status-grid"',
            device_block,
        )

        self.assertIn(
            'data-columns="2"',
            device_block,
        )

        self.assertIn(
            'data-rows="2"',
            device_block,
        )

        self.assertIn(
            'data-items="4"',
            device_block,
        )

        labels = (
            "MODE",
            "CAMERA",
            "MICROPHONE",
            "CLOUD TUTOR",
        )

        for label in labels:
            with self.subTest(
                label=label,
            ):
                self.assertIn(
                    label,
                    device_block,
                )

        self.assertEqual(
            sum(
                device_block.count(
                    label
                )
                for label in labels
            ),
            4,
        )

    def test_main_workspace_status_metrics_are_absent(
        self,
    ) -> None:
        labels = {
            "mode",
            "camera",
            "microphone",
            "cloud tutor",
            "cloud llm",
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

            if not (
                isinstance(
                    node.func,
                    ast.Attribute,
                )
                and node.func.attr
                == "metric"
            ):
                continue

            if not node.args:
                continue

            value = node.args[0]

            if not (
                isinstance(
                    value,
                    ast.Constant,
                )
                and isinstance(
                    value.value,
                    str,
                )
            ):
                continue

            if (
                value.value
                .strip()
                .casefold()
                in labels
            ):
                violations.append(
                    {
                        "label": value.value,
                        "line": node.lineno,
                    }
                )

        self.assertEqual(
            violations,
            [],
        )


    def test_device_status_renderer_targets_streamlit_sidebar(
        self,
    ) -> None:
        import ast
        from pathlib import Path

        ui_path = Path(
            "modules/system/"
            "realtime_voice_ui.py"
        )

        ui_source = ui_path.read_text(
            encoding="utf-8"
        )

        ui_tree = ast.parse(
            ui_source,
            filename=str(
                ui_path
            ),
        )

        renderer = next(
            (
                node
                for node in ui_tree.body
                if (
                    isinstance(
                        node,
                        ast.FunctionDef,
                    )
                    and node.name
                    == (
                        "render_sidebar_"
                        "device_controls"
                    )
                )
            ),
            None,
        )

        self.assertIsNotNone(
            renderer
        )

        parents = {}

        for parent in ast.walk(
            renderer
        ):
            for child in (
                ast.iter_child_nodes(
                    parent
                )
            ):
                parents[child] = parent

        def call_name(
            call: ast.Call,
        ) -> str:
            if isinstance(
                call.func,
                ast.Name,
            ):
                return call.func.id

            if isinstance(
                call.func,
                ast.Attribute,
            ):
                return call.func.attr

            return ""

        iframe_calls = [
            node
            for node in ast.walk(
                renderer
            )
            if (
                isinstance(
                    node,
                    ast.Call,
                )
                and call_name(node)
                == "iframe"
            )
        ]

        self.assertEqual(
            len(iframe_calls),
            1,
        )

        current = iframe_calls[0]
        inside_sidebar = False

        while current in parents:
            current = parents[
                current
            ]

            if not isinstance(
                current,
                ast.With,
            ):
                continue

            for item in current.items:
                context = (
                    item.context_expr
                )

                if (
                    isinstance(
                        context,
                        ast.Attribute,
                    )
                    and isinstance(
                        context.value,
                        ast.Name,
                    )
                    and context.value.id
                    == "st"
                    and context.attr
                    == "sidebar"
                ):
                    inside_sidebar = True
                    break

            if inside_sidebar:
                break

        self.assertTrue(
            inside_sidebar,
            msg=(
                "The actual device iframe "
                "must execute inside "
                "with st.sidebar."
            ),
        )

        app_path = Path(
            "apps/"
            "streamlit_attentive_slides.py"
        )

        app_source = app_path.read_text(
            encoding="utf-8"
        )

        app_tree = ast.parse(
            app_source,
            filename=str(
                app_path
            ),
        )

        app_calls = [
            node
            for node in ast.walk(
                app_tree
            )
            if (
                isinstance(
                    node,
                    ast.Call,
                )
                and call_name(node)
                == (
                    "render_sidebar_"
                    "device_controls"
                )
            )
        ]

        self.assertEqual(
            len(app_calls),
            1,
        )


if __name__ == "__main__":
    unittest.main()
