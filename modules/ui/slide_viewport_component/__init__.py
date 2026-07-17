"""Dependency-free Streamlit slide viewport component wrapper."""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Any, Mapping

import streamlit.components.v1 as components

from modules.system.main_ui_state import MainUISlide
from modules.ui.design_tokens import SEMANTIC_KEYS


_COMPONENT: Any = None


def render_slide_viewport(
    *,
    deck_id: str,
    slide: MainUISlide,
    layout_revision: int,
    drawing_enabled: bool,
    show_aoi_overlay: bool,
    display_width_percent: int,
    palette_tokens: Mapping[str, str],
    key: str,
    clear_server_match: bool = False,
) -> dict[str, object] | None:
    if os.environ.get("ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST") == "1":
        return {"event": "disabled"}
    if not slide.image_available or slide.image_path is None:
        return None

    image_path = Path(slide.image_path)
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    image_data_url = (
        f"data:{mime_type};base64,"
        + base64.b64encode(image_path.read_bytes()).decode("ascii")
    )
    bounded_width = max(50, min(100, int(display_width_percent)))
    missing = set(SEMANTIC_KEYS) - set(palette_tokens)
    if missing:
        raise ValueError("palette_tokens must contain every semantic token")
    safe_tokens = {
        name: str(palette_tokens[name])
        for name in SEMANTIC_KEYS
    }
    value: Any = _component()(
        deck_id=deck_id,
        slide_id=slide.slide_id,
        layout_revision=int(layout_revision),
        image_data_url=image_data_url,
        aois=[
            {
                "aoi_id": aoi.aoi_id,
                "bbox": list(aoi.bbox),
                "type": aoi.type,
            }
            for aoi in slide.aois
        ],
        drawing_enabled=bool(drawing_enabled),
        show_aoi_overlay=bool(show_aoi_overlay),
        clear_server_match=bool(clear_server_match),
        display_width_percent=bounded_width,
        palette_tokens=safe_tokens,
        default={"event": "mounted"},
        key=key,
    )
    return value if isinstance(value, dict) else None


def _component() -> Any:
    global _COMPONENT
    if _COMPONENT is None:
        _COMPONENT = components.declare_component(
            "attentive_slide_viewport",
            path=str(Path(__file__).parent),
        )
    return _COMPONENT
