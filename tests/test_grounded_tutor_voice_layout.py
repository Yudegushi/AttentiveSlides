"""Layout contracts for the merged Tutor workflow."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
)

UI_PATH = Path(
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


class TestGroundedTutorVoiceLayout(
    unittest.TestCase
):
    def test_ptt_belongs_to_second_tutor_panel(
        self,
    ) -> None:
        source = APP_PATH.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source,
            filename=str(APP_PATH),
        )

        parents = {}

        for parent in ast.walk(
            tree
        ):
            for child in (
                ast.iter_child_nodes(
                    parent
                )
            ):
                parents[
                    child
                ] = parent

        calls = [
            node
            for node in ast.walk(
                tree
            )
            if (
                isinstance(
                    node,
                    ast.Call,
                )
                and call_name(
                    node
                )
                == (
                    "render_grounded_"
                    "tutor_voice"
                )
            )
        ]

        self.assertEqual(
            len(calls),
            1,
        )

        current = calls[0]
        owner = None

        while current in parents:
            current = parents[
                current
            ]

            if isinstance(
                current,
                ast.FunctionDef,
            ):
                owner = (
                    current.name
                )
                break

        self.assertEqual(
            owner,
            "_render_intent_column",
        )

    def test_ptt_precedes_send_and_output(
        self,
    ) -> None:
        source = APP_PATH.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source,
            filename=str(APP_PATH),
        )

        function = next(
            node
            for node in tree.body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name
                == "_render_intent_column"
            )
        )

        positions = {}

        for node in ast.walk(
            function
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            name = call_name(
                node
            )

            if name in {
                (
                    "render_grounded_"
                    "tutor_voice"
                ),
                (
                    "_render_tutor_"
                    "generation_panel"
                ),
                "_render_tutor_output",
            }:
                positions[
                    name
                ] = node.lineno

        ordered = [
            positions[
                (
                    "render_grounded_"
                    "tutor_voice"
                )
            ],
            positions[
                (
                    "_render_tutor_"
                    "generation_panel"
                )
            ],
            positions[
                "_render_tutor_output"
            ],
        ]

        self.assertEqual(
            ordered,
            sorted(
                ordered
            ),
        )

    def test_ptt_iframe_remains_compact(
        self,
    ) -> None:
        source = UI_PATH.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source,
            filename=str(UI_PATH),
        )

        function = next(
            node
            for node in tree.body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name
                == (
                    "render_grounded_"
                    "tutor_voice"
                )
            )
        )

        iframe = next(
            node
            for node in ast.walk(
                function
            )
            if (
                isinstance(
                    node,
                    ast.Call,
                )
                and call_name(
                    node
                )
                == "iframe"
            )
        )

        height = next(
            (
                keyword
                .value
                .value
                for keyword
                in iframe.keywords
                if (
                    keyword.arg
                    == "height"
                    and isinstance(
                        keyword.value,
                        ast.Constant,
                    )
                )
            ),
            None,
        )

        self.assertIsNotNone(
            height
        )

        self.assertLessEqual(
            height,
            96,
        )


if __name__ == "__main__":
    unittest.main()
