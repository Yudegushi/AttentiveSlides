"""Streamlit wrapper for same-origin voice controls without device capture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_COMPONENT: Any = None


def render_voice_control_component(
    *,
    engine: str,
    speech_mode: str,
    key: str,
) -> dict[str, object] | None:
    value: Any = _component()(
        engine=str(engine),
        speech_mode=str(speech_mode),
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
