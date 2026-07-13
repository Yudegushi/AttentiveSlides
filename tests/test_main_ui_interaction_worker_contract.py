"""Static contracts for the isolated Main UI AppTest worker."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


WORKER_PATH = Path(
    "scripts/_main_ui_interaction_worker.py"
)


class TestMainUIInteractionWorkerContract(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.source = (
            WORKER_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.tree = ast.parse(
            cls.source,
            filename=str(
                WORKER_PATH
            ),
        )

    def test_safe_session_state_helper_exists(
        self,
    ) -> None:
        functions = {
            node.name
            for node in self.tree.body
            if isinstance(
                node,
                ast.FunctionDef,
            )
        }

        self.assertIn(
            "session_state_value",
            functions,
        )

    def test_apptest_session_state_get_is_not_used(
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

            function = node.func

            if not (
                isinstance(
                    function,
                    ast.Attribute,
                )
                and function.attr
                == "get"
            ):
                continue

            value = function.value

            if not (
                isinstance(
                    value,
                    ast.Attribute,
                )
                and value.attr
                == "session_state"
            ):
                continue

            violations.append(
                node.lineno
            )

        self.assertEqual(
            violations,
            [],
        )

    def test_manual_region_uses_safe_reader(
        self,
    ) -> None:
        function = next(
            node
            for node in self.tree.body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name
                == "run_manual_region_scenario"
            )
        )

        function_source = (
            ast.get_source_segment(
                self.source,
                function,
            )
            or ""
        )

        self.assertIn(
            "session_state_value",
            function_source,
        )


if __name__ == "__main__":
    unittest.main()
