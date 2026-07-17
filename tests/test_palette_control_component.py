from __future__ import annotations

from pathlib import Path
import unittest

from modules.ui.design_tokens import SEMANTIC_KEYS


class PaletteControlComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.component = Path(
            "modules/ui/palette_control_component/index.html"
        ).read_text(encoding="utf-8")
        cls.wrapper = Path(
            "modules/ui/palette_control_component/__init__.py"
        ).read_text(encoding="utf-8")

    def test_local_preference_and_four_palettes_are_present(self) -> None:
        self.assertIn("attentiveslides-ui-palette-v1", self.component)
        for palette_id in (
            "ivory-study-desk",
            "autumn-reading-room",
            "cool-archive",
            "dusty-blue",
        ):
            self.assertIn(palette_id, self.component)
        self.assertIn("localStorage.getItem", self.component)
        self.assertIn("localStorage.setItem", self.component)

    def test_locking_selection_and_streamlit_updates_are_accessible(self) -> None:
        for token in (
            "button.disabled = locked",
            '"aria-disabled"',
            '"aria-pressed"',
            "Palette is locked during an active study.",
            "streamlit:setComponentValue",
        ):
            self.assertIn(token, self.component)

    def test_complete_semantic_map_is_bridged_to_the_iframe_root(self) -> None:
        self.assertIn("palette_tokens=safe_tokens", self.wrapper)
        self.assertIn("applyPalette(args.palette_tokens)", self.component)
        self.assertIn("document.documentElement.style.setProperty", self.component)
        for name in SEMANTIC_KEYS:
            self.assertIn(f'"{name}"', self.component)
        self.assertIn("for (const name of SEMANTIC_KEYS)", self.component)

    def test_component_uses_safe_local_rendering_and_no_remote_asset(self) -> None:
        self.assertIn("textContent", self.component)
        self.assertIn("dataset.paletteId", self.component)
        self.assertIn("document.createElement", self.component)
        self.assertNotIn("innerHTML", self.component)
        self.assertNotIn("http://", self.component)
        self.assertNotIn("https://", self.component)


if __name__ == "__main__":
    unittest.main()

