"""Browser-timestamped lock button for the isolated gaze-lock test."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import streamlit.components.v1 as components

from modules.ui.design_tokens import SEMANTIC_KEYS


_COMPONENT: Any = None


def render_gaze_lock_control_component(
    *,
    label: str,
    disabled: bool,
    palette_tokens: Mapping[str, str],
    key: str,
) -> dict[str, object] | None:
    missing = set(SEMANTIC_KEYS) - set(palette_tokens)
    if missing:
        raise ValueError("palette_tokens must contain every semantic token")
    value: Any = _component()(
        label=str(label),
        disabled=bool(disabled),
        palette_tokens={
            name: str(palette_tokens[name])
            for name in SEMANTIC_KEYS
        },
        default={"event": "mounted"},
        key=key,
    )
    return value if isinstance(value, dict) else None


def _component() -> Any:
    global _COMPONENT
    if _COMPONENT is None:
        _COMPONENT = components.declare_component(
            "attentive_gaze_lock_control",
            path=str(Path(__file__).parent),
        )
    return _COMPONENT
