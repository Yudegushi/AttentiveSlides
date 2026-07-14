"""Contracts for target-confirmation callback ordering."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


APP_PATH = Path(
    "apps/streamlit_attentive_slides.py"
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


def static_string(
    node: ast.AST,
) -> str | None:
    if (
        isinstance(
            node,
            ast.Constant,
        )
        and isinstance(
            node.value,
            str,
        )
    ):
        return node.value

    if (
        isinstance(
            node,
            ast.BinOp,
        )
        and isinstance(
            node.op,
            ast.Add,
        )
    ):
        left = static_string(
            node.left
        )

        right = static_string(
            node.right
        )

        if (
            left is not None
            and right is not None
        ):
            return left + right

    return None


def keyword_value(
    call: ast.Call,
    name: str,
) -> ast.AST | None:
    return next(
        (
            keyword.value
            for keyword in call.keywords
            if keyword.arg == name
        ),
        None,
    )


class TestConfirmationCallbackOrder(
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

        cls.function = next(
            node
            for node in cls.tree.body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name
                == "_render_confirmation_panel"
            )
        )

    def find_button(
        self,
        expected_key: str,
    ) -> ast.Call:
        matches = []

        for node in ast.walk(
            self.function
        ):
            if (
                not isinstance(
                    node,
                    ast.Call,
                )
                or call_name(node)
                != "button"
            ):
                continue

            key_node = keyword_value(
                node,
                "key",
            )

            if (
                key_node is not None
                and static_string(
                    key_node
                )
                == expected_key
            ):
                matches.append(
                    node
                )

        self.assertEqual(
            len(matches),
            1,
        )

        return matches[0]

    def assert_callback(
        self,
        key: str,
        expected_callback: str,
    ) -> None:
        button = self.find_button(
            key
        )

        callback = keyword_value(
            button,
            "on_click",
        )

        self.assertIsInstance(
            callback,
            ast.Name,
        )

        self.assertEqual(
            callback.id,
            expected_callback,
        )

    def test_confirm_uses_callback(
        self,
    ) -> None:
        self.assert_callback(
            "main_confirm_button",
            "_confirm_selected_target",
        )

    def test_cancel_uses_callback(
        self,
    ) -> None:
        self.assert_callback(
            (
                "main_cancel_"
                "confirmation_button"
            ),
            "_invalidate_confirmation",
        )

    def test_callback_is_defined_before_button(
        self,
    ) -> None:
        callback = next(
            node
            for node in self.function.body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name
                == "_confirm_selected_target"
            )
        )

        confirm = self.find_button(
            "main_confirm_button"
        )

        self.assertLess(
            callback.lineno,
            confirm.lineno,
        )

    def test_callback_updates_confirmation_state(
        self,
    ) -> None:
        callback = next(
            node
            for node in self.function.body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name
                == "_confirm_selected_target"
            )
        )

        calls = {
            call_name(
                node
            )
            for node in ast.walk(
                callback
            )
            if isinstance(
                node,
                ast.Call,
            )
        }

        self.assertIn(
            "confirm_target_selection",
            calls,
        )

        self.assertIn(
            "_invalidate_request_state",
            calls,
        )

        segment = (
            ast.get_source_segment(
                self.source,
                callback,
            )
            or ""
        )

        self.assertIn(
            '"main_confirmed"',
            segment,
        )

        self.assertIn(
            '"main_confirmed_target"',
            segment,
        )

    def test_old_confirm_clicked_flow_is_absent(
        self,
    ) -> None:
        for node in ast.walk(
            self.function
        ):
            self.assertFalse(
                (
                    isinstance(
                        node,
                        ast.Name,
                    )
                    and node.id
                    == "confirm_clicked"
                )
            )


if __name__ == "__main__":
    unittest.main()
