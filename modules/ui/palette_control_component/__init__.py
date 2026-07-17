"""Streamlit wrapper for the local AttentiveSlides palette preference."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import streamlit.components.v1 as components

from modules.ui.design_tokens import (
    SEMANTIC_KEYS,
    normalize_palette_id,
    palette_semantic,
)


_COMPONENT: Any = None


def render_palette_control(
    *,
    selected: str,
    palette_tokens: Mapping[str, str],
    locked: bool,
    key: str,
) -> str | None:
    normalized = normalize_palette_id(selected)
    fallback = palette_semantic(normalized)
    safe_tokens = {
        name: str(palette_tokens.get(name, fallback[name]))
        for name in SEMANTIC_KEYS
    }
    value: Any = _component()(
        selected=normalized,
        palette_tokens=safe_tokens,
        locked=bool(locked),
        default=None,
        key=key,
    )
    return normalize_palette_id(value) if isinstance(value, str) else None


def _component() -> Any:
    global _COMPONENT
    if _COMPONENT is None:
        _COMPONENT = components.declare_component(
            "attentive_palette_control",
            path=str(Path(__file__).parent),
        )
    return _COMPONENT

