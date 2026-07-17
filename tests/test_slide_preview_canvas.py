from __future__ import annotations

import ast
import unittest
from pathlib import Path

APP_PATH = Path("apps/streamlit_attentive_slides.py")


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Subscript):
        return dotted_name(node.value)
    return ""


class TestSlidePreviewCanvas(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = APP_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(APP_PATH))
        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_current_slide_selectbox_is_removed(self) -> None:
        selector = self.functions["_render_slide_selector"]
        selectboxes = [
            node.lineno
            for node in ast.walk(selector)
            if isinstance(node, ast.Call)
            and dotted_name(node.func).split(".")[-1] == "selectbox"
        ]
        self.assertEqual(selectboxes, [])
        self.assertNotIn('"Current slide"', ast.unparse(selector))

    def test_clickable_preview_buttons_exist(self) -> None:
        selector = self.functions["_render_slide_selector"]
        self.assertIn("main_slide_preview_", ast.unparse(selector))
        self.assertIn("_navigate_to_slide", ast.unparse(selector))

    def test_selector_scrolls_to_active_slide_in_persistent_rail(self) -> None:
        selector = ast.unparse(self.functions["_render_slide_selector"])
        scroll_helper = ast.unparse(
            self.functions["_slide_selector_scroll_html"]
        )

        self.assertIn("main_slide_preview_scroll", selector)
        self.assertIn("_slide_selector_scroll_html(active_slide_id)", selector)
        self.assertIn("main_slide_preview_", scroll_helper)
        self.assertIn("setTimeout(position", scroll_helper)
        self.assertIn("scrollTop", scroll_helper)

    def test_selector_is_one_collapsible_right_rail(self) -> None:
        selector = ast.unparse(self.functions["_render_slide_selector"])
        self.assertNotIn("st.popover", selector)
        self.assertIn("main_slide_rail", selector)
        self.assertIn("main_slide_rail_collapse_button", selector)
        self.assertIn("main_slide_rail_expand_button", selector)
        self.assertIn("Collapse slide deck", selector)

    def test_viewport_component_replaces_region_sliders(self) -> None:
        workspace = self.functions["_render_slide_workspace"]
        rendered = ast.unparse(workspace)
        self.assertIn("render_slide_viewport", rendered)
        self.assertIn("parse_component_geometry", rendered)
        self.assertNotIn("st_canvas", self.source)
        self.assertNotIn("main_region_x_range", rendered)
        self.assertNotIn("main_region_y_range", rendered)
        self.assertNotIn("main_apply_region_button", rendered)

    def test_scope_values_are_canonical(self) -> None:
        target = self.functions["_render_target_column"]
        rendered = ast.unparse(target)
        self.assertIn("Whole slide", rendered)
        self.assertIn("Manual region", rendered)
        self.assertIn("format_func=_target_scope_label", rendered)
        self.assertNotIn('options=[\'Use whole slide\'', rendered)


if __name__ == "__main__":
    unittest.main()
