"""Semantic light-mode design tokens for AttentiveSlides."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


DEFAULT_PALETTE_ID = "ivory-study-desk"
PALETTE_STORAGE_KEY = "attentiveslides-ui-palette-v1"

SEMANTIC_KEYS = (
    "canvas",
    "workspace",
    "topbar",
    "rail",
    "surface",
    "ink",
    "muted",
    "muted-2",
    "border",
    "border-strong",
    "primary",
    "primary-on",
    "primary-soft",
    "segment",
    "slide-accent",
    "slide-accent-soft",
)


@dataclass(frozen=True)
class PaletteDefinition:
    palette_id: str
    label: str
    semantic: Mapping[str, str]


def _palette(
    palette_id: str,
    label: str,
    values: tuple[str, ...],
) -> PaletteDefinition:
    if len(values) != len(SEMANTIC_KEYS):
        raise ValueError(f"{palette_id} must define every semantic token")
    return PaletteDefinition(
        palette_id=palette_id,
        label=label,
        semantic=MappingProxyType(dict(zip(SEMANTIC_KEYS, values))),
    )


PALETTES: Mapping[str, PaletteDefinition] = MappingProxyType(
    {
        palette.palette_id: palette
        for palette in (
            _palette(
                "ivory-study-desk",
                "Ivory Study Desk",
                (
                    "#F6F1E7", "#F0EBE0", "#FAF7EF", "#F7F3E9",
                    "#FFFDF8", "#292A24", "#747168", "#AAA59A",
                    "#DDD6C7", "#C9C0AE", "#485F55", "#FFFDF8",
                    "#E2E9E1", "#E9E3D7", "#A55D42", "#EDD3C6",
                ),
            ),
            _palette(
                "autumn-reading-room",
                "Autumn Reading Room",
                (
                    "#F7EFE1", "#EEE4D4", "#FBF6EC", "#F5ECDD",
                    "#FFFBF3", "#332B26", "#7D7064", "#AFA195",
                    "#DFD0BC", "#C6B49D", "#774837", "#FFFAF1",
                    "#EAD8C9", "#E9DECE", "#B97843", "#F0D7B8",
                ),
            ),
            _palette(
                "cool-archive",
                "Cool Archive",
                (
                    "#EDF0EC", "#E4E9E6", "#F6F7F3", "#F0F3EF",
                    "#FBFCF8", "#202A29", "#687371", "#9BA4A1",
                    "#CDD5D1", "#AFBBB6", "#3E6264", "#FBFCF8",
                    "#D8E6E4", "#DFE5E2", "#8D5A48", "#E8D4CB",
                ),
            ),
            _palette(
                "dusty-blue",
                "Dusty Blue",
                (
                    "#EEF0EF", "#E3E8E8", "#F6F7F5", "#EDF1F0",
                    "#FAFBF8", "#263033", "#697377", "#9BA4A6",
                    "#CBD3D4", "#ADB9BB", "#4B6169", "#FAFBF8",
                    "#DBE5E7", "#DFE5E4", "#9A6653", "#EAD6CC",
                ),
            ),
        )
    }
)

_expected_keys = frozenset(SEMANTIC_KEYS)
for _definition in PALETTES.values():
    if frozenset(_definition.semantic) != _expected_keys:
        raise ValueError(f"{_definition.palette_id} has an inconsistent semantic schema")


def normalize_palette_id(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in PALETTES else DEFAULT_PALETTE_ID


def palette_semantic(value: object) -> dict[str, str]:
    palette = PALETTES[normalize_palette_id(value)]
    return dict(palette.semantic)


def render_palette_css(value: object) -> str:
    declarations = "\n".join(
        f"--as-{name}: {css_value};"
        for name, css_value in palette_semantic(value).items()
    )
    return f":root {{\n{declarations}\n}}"

