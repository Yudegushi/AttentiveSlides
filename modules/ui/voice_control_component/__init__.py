"""Streamlit wrapper for same-origin voice controls without device capture."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import streamlit.components.v1 as components

from modules.ui.design_tokens import SEMANTIC_KEYS


_COMPONENT: Any = None


def render_voice_control_component(
    *,
    engine: str,
    flow: str,
    speech_mode: str,
    palette_tokens: Mapping[str, str],
    key: str,
) -> dict[str, object] | None:
    missing = set(SEMANTIC_KEYS) - set(palette_tokens)
    if missing:
        raise ValueError("palette_tokens must contain every semantic token")
    safe_tokens = {
        name: str(palette_tokens[name])
        for name in SEMANTIC_KEYS
    }
    value: Any = _component()(
        engine=str(engine),
        flow=str(flow),
        speech_mode=str(speech_mode),
        palette_tokens=safe_tokens,
        default={"event": "mounted"},
        key=key,
    )
    return value if isinstance(value, dict) else None


def _component() -> Any:
    global _COMPONENT
    if _COMPONENT is None:
        _COMPONENT = components.declare_component(
            "attentive_voice_control",
            path=str(Path(__file__).parent),
        )
    return _COMPONENT
