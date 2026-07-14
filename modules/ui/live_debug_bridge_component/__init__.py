"""Publish authoritative debug overlay state without returning component values."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_COMPONENT: Any = None


def render_live_debug_bridge(
    *,
    deck_id: str,
    slide_id: int,
    matched_aoi_id: str | None,
    enabled: bool,
    clear_match: bool,
    key: str,
) -> None:
    if os.environ.get("ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST") == "1":
        return
    _component()(
        deck_id=str(deck_id),
        slide_id=int(slide_id),
        matched_aoi_id=(str(matched_aoi_id) if matched_aoi_id else None),
        enabled=bool(enabled),
        clear_match=bool(clear_match),
        default=None,
        key=key,
    )


def _component() -> Any:
    global _COMPONENT
    if _COMPONENT is None:
        _COMPONENT = components.declare_component(
            "attentive_live_debug_bridge",
            path=str(Path(__file__).parent),
        )
    return _COMPONENT
