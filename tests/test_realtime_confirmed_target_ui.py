"""Contracts for confirmed-target Realtime voice UI."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

REALTIME_PATH = Path(
    "modules/system/realtime_voice_ui.py"
)


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


class TestRealtimeConfirmedTargetUI(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.realtime_source = (
            REALTIME_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.realtime_tree = ast.parse(
            cls.realtime_source,
            filename=str(
                REALTIME_PATH
            ),
        )

        cls.realtime_functions = {
            node.name: node
            for node in ast.walk(
                cls.realtime_tree
            )
            if isinstance(
                node,
                ast.FunctionDef,
            )
        }

    def source_of(
        self,
        name: str,
    ) -> str:
        return (
            ast.get_source_segment(
                self.realtime_source,
                self.realtime_functions[
                    name
                ],
            )
            or ""
        )

    def test_public_result_renderer_exists(
        self,
    ) -> None:
        self.assertIn(
            "render_realtime_voice_result",
            self.realtime_functions,
        )

    def test_grounding_uses_confirmed_context(
        self,
    ) -> None:
        source = self.source_of(
            "update_realtime_grounding"
        )

        self.assertIn(
            "_confirmed_target_payload",
            source,
        )

        self.assertIn(
            "confirmed_context",
            source,
        )

        self.assertIn(
            "selected_region_text",
            source,
        )

    def test_ptt_requires_confirmed_target(
        self,
    ) -> None:
        source = self.source_of(
            "render_grounded_tutor_voice"
        )

        self.assertIn(
            "_confirmed_target_payload",
            source,
        )

        self.assertIn(
            'view="ptt"',
            source,
        )

        self.assertIn(
            "height=82",
            source,
        )

        self.assertNotIn(
            "_render_realtime_result",
            source,
        )

    def test_continuous_requires_confirmed_target(
        self,
    ) -> None:
        source = self.source_of(
            "render_continuous_voice_panel"
        )

        self.assertIn(
            "_confirmed_target_payload",
            source,
        )

        self.assertIn(
            'view="continuous"',
            source,
        )

    def test_shared_output_calls_public_renderer(
        self,
    ) -> None:
        app_source = (
            APP_PATH.read_text(
                encoding="utf-8"
            )
        )

        app_tree = ast.parse(
            app_source,
            filename=str(
                APP_PATH
            ),
        )

        function = next(
            node
            for node in app_tree.body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name
                == "_render_tutor_output"
            )
        )

        calls = [
            call_name(
                node
            )
            for node in ast.walk(
                function
            )
            if isinstance(
                node,
                ast.Call,
            )
        ]

        self.assertIn(
            "_render_tutor_result",
            calls,
        )

        self.assertIn(
            "render_realtime_voice_result",
            calls,
        )


if __name__ == "__main__":
    unittest.main()
