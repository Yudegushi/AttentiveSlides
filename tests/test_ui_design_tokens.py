from __future__ import annotations

import unittest

from modules.ui.design_tokens import (
    DEFAULT_PALETTE_ID,
    PALETTES,
    SEMANTIC_KEYS,
    normalize_palette_id,
    palette_semantic,
    render_palette_css,
)


class DesignTokenTests(unittest.TestCase):
    def test_default_and_unknown_values_normalize_to_ivory(self) -> None:
        self.assertEqual(DEFAULT_PALETTE_ID, "ivory-study-desk")
        for value in (None, "", "unknown", object()):
            self.assertEqual(normalize_palette_id(value), DEFAULT_PALETTE_ID)

    def test_all_four_palette_ids_and_labels_are_exact(self) -> None:
        self.assertEqual(
            {palette_id: definition.label for palette_id, definition in PALETTES.items()},
            {
                "ivory-study-desk": "Ivory Study Desk",
                "autumn-reading-room": "Autumn Reading Room",
                "cool-archive": "Cool Archive",
                "dusty-blue": "Dusty Blue",
            },
        )

    def test_every_palette_has_the_same_complete_semantic_schema(self) -> None:
        expected = set(SEMANTIC_KEYS)
        self.assertEqual(len(expected), 16)
        for definition in PALETTES.values():
            self.assertEqual(set(definition.semantic), expected)

    def test_all_semantic_values_match_the_approved_registry(self) -> None:
        roles = SEMANTIC_KEYS
        expected_columns = {
            "ivory-study-desk": (
                "#F6F1E7", "#F0EBE0", "#FAF7EF", "#F7F3E9",
                "#FFFDF8", "#292A24", "#747168", "#AAA59A",
                "#DDD6C7", "#C9C0AE", "#485F55", "#FFFDF8",
                "#E2E9E1", "#E9E3D7", "#A55D42", "#EDD3C6",
            ),
            "autumn-reading-room": (
                "#F7EFE1", "#EEE4D4", "#FBF6EC", "#F5ECDD",
                "#FFFBF3", "#332B26", "#7D7064", "#AFA195",
                "#DFD0BC", "#C6B49D", "#774837", "#FFFAF1",
                "#EAD8C9", "#E9DECE", "#B97843", "#F0D7B8",
            ),
            "cool-archive": (
                "#EDF0EC", "#E4E9E6", "#F6F7F3", "#F0F3EF",
                "#FBFCF8", "#202A29", "#687371", "#9BA4A1",
                "#CDD5D1", "#AFBBB6", "#3E6264", "#FBFCF8",
                "#D8E6E4", "#DFE5E2", "#8D5A48", "#E8D4CB",
            ),
            "dusty-blue": (
                "#EEF0EF", "#E3E8E8", "#F6F7F5", "#EDF1F0",
                "#FAFBF8", "#263033", "#697377", "#9BA4A6",
                "#CBD3D4", "#ADB9BB", "#4B6169", "#FAFBF8",
                "#DBE5E7", "#DFE5E4", "#9A6653", "#EAD6CC",
            ),
        }
        for palette_id, values in expected_columns.items():
            self.assertEqual(palette_semantic(palette_id), dict(zip(roles, values)))

    def test_rendered_css_is_semantic_root_only_and_light_mode_only(self) -> None:
        rendered = render_palette_css("dusty-blue")
        self.assertTrue(rendered.startswith(":root {"))
        for name in SEMANTIC_KEYS:
            self.assertIn(f"--as-{name}:", rendered)
        self.assertNotIn("@media (prefers-color-scheme: dark)", rendered)
        self.assertNotIn(".as-", rendered)


if __name__ == "__main__":
    unittest.main()

