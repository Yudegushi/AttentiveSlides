"""Legacy Stage 2 UI contracts after Stage 3 integration."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

STAGE2_UI_PATH = Path(
    "modules/system/voice_input_ui.py"
)


def parse_file(
    path: Path,
) -> ast.Module:
    return ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(path),
    )


def function_names(
    tree: ast.AST,
) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
    }


def call_name(
    node: ast.Call,
) -> str:
    if isinstance(
        node.func,
        ast.Name,
    ):
        return node.func.id

    if isinstance(
        node.func,
        ast.Attribute,
    ):
        return node.func.attr

    return ""


def call_names(
    tree: ast.AST,
) -> list[str]:
    return [
        call_name(node)
        for node in ast.walk(tree)
        if isinstance(
            node,
            ast.Call,
        )
    ]


def string_constants(
    tree: ast.AST,
) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if (
            isinstance(
                node,
                ast.Constant,
            )
            and isinstance(
                node.value,
                str,
            )
        )
    }


class TestVoiceInputUIContract(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.app_tree = parse_file(
            APP_PATH
        )

        cls.stage2_tree = parse_file(
            STAGE2_UI_PATH
        )

    def test_stage2_module_keeps_legacy_renderer(
        self,
    ) -> None:
        self.assertIn(
            "render_voice_input_panel",
            function_names(
                self.stage2_tree
            ),
        )

    def test_main_app_does_not_call_legacy_renderer(
        self,
    ) -> None:
        self.assertNotIn(
            "render_voice_input_panel",
            call_names(
                self.app_tree
            ),
        )

    def test_main_app_uses_stage3_voice_renderers(
        self,
    ) -> None:
        calls = call_names(
            self.app_tree
        )

        required = (
            "render_sidebar_device_controls",
            "render_grounded_tutor_voice",
            "render_continuous_voice_panel",
            "render_realtime_voice_xai",
        )

        for name in required:
            with self.subTest(
                name=name,
            ):
                self.assertIn(
                    name,
                    calls,
                )

    def test_stage2_apptest_guard_remains_available(
        self,
    ) -> None:
        self.assertIn(
            (
                "ATTENTIVE_DISABLE_"
                "MICROPHONE_FOR_APPTEST"
            ),
            string_constants(
                self.stage2_tree
            ),
        )

    def test_stage2_module_remains_local_stt_only(
        self,
    ) -> None:
        source = (
            STAGE2_UI_PATH.read_text(
                encoding="utf-8"
            )
        )

        forbidden = (
            "BailianOmniRealtimeClient",
            "response.create",
            "response.audio.delta",
            "render_continuous_voice_panel",
        )

        for token in forbidden:
            with self.subTest(
                token=token,
            ):
                self.assertNotIn(
                    token,
                    source,
                )


if __name__ == "__main__":
    unittest.main()
