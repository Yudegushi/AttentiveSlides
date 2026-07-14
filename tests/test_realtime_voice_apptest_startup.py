"""Ensure Stage 3 voice integration remains safe in Streamlit AppTest."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import unittest


os.environ.setdefault(
    "ATTENTIVE_DISABLE_REALTIME_VOICE_FOR_APPTEST",
    "1",
)

os.environ.setdefault(
    "ATTENTIVE_DISABLE_MICROPHONE_FOR_APPTEST",
    "1",
)


from streamlit.testing.v1 import AppTest


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

STAGE3_RENDERERS = {
    "render_grounded_tutor_voice",
    "render_continuous_voice_panel",
}


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


class TestRealtimeVoiceAppTestStartup(
    unittest.TestCase
):
    def test_stage3_calls_do_not_directly_load_local_view(
        self,
    ) -> None:
        source = APP_PATH.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source,
            filename=str(
                APP_PATH
            ),
        )

        found = 0

        for node in ast.walk(tree):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if call_name(
                node
            ) not in STAGE3_RENDERERS:
                continue

            found += 1

            direct_arguments = [
                argument
                for argument in node.args
                if (
                    isinstance(
                        argument,
                        ast.Name,
                    )
                    and argument.id
                    == "view"
                )
            ]

            direct_keywords = [
                keyword
                for keyword
                in node.keywords
                if (
                    keyword.arg == "view"
                    and isinstance(
                        keyword.value,
                        ast.Name,
                    )
                    and keyword.value.id
                    == "view"
                )
            ]

            self.assertEqual(
                direct_arguments,
                [],
                msg=(
                    "Stage 3 renderer directly "
                    "reads local view at line "
                    f"{node.lineno}"
                ),
            )

            self.assertEqual(
                direct_keywords,
                [],
                msg=(
                    "Stage 3 renderer directly "
                    "reads local view at line "
                    f"{node.lineno}"
                ),
            )

        self.assertGreaterEqual(
            found,
            2,
        )

    def test_main_app_starts_without_exception(
        self,
    ) -> None:
        app = AppTest.from_file(
            str(APP_PATH)
        )

        app.run(
            timeout=120,
        )

        exceptions = [
            str(
                item.value
            )
            for item in app.exception
        ]

        self.assertEqual(
            exceptions,
            [],
            msg=(
                "Main UI AppTest exceptions: "
                + repr(exceptions)
            ),
        )


if __name__ == "__main__":
    unittest.main()
