"""Unified Main UI shell for privacy-preserving AttentiveSlides."""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import streamlit as st

from modules.system.main_ui_state import (
    MainUISlide,
    MainUIViewModel,
    ManifestDeckBrowser,
    build_main_turn_defaults,
    build_main_ui_view_model,
    reset_main_turn_state,
)


MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "mock_deck"
    / "mock_aoi_manifest.json"
)


def main() -> None:
    """Render the AttentiveSlides Main UI shell."""
    st.set_page_config(
        page_title="AttentiveSlides",
        page_icon="📘",
        layout="wide",
    )

    browser = _load_browser(
        str(MANIFEST_PATH),
        str(REPOSITORY_ROOT),
    )

    _ensure_session_state(browser)

    view = build_main_ui_view_model(
        browser,
        active_slide_id=(
            st.session_state["main_active_slide_id"]
        ),
        cloud_text_allowed=(
            st.session_state[
                "main_cloud_text_allowed"
            ]
        ),
    )

    _render_sidebar(browser, view)
    _render_header(view)
    _render_navigation(browser, view)

    slide_column, interaction_column = st.columns(
        [1.55, 0.95],
        gap="large",
    )

    with slide_column:
        _render_slide_workspace(view)

    with interaction_column:
        _render_manual_interaction()

    st.divider()
    _render_lower_workspace(view)


@st.cache_resource
def _load_browser(
    manifest_path: str,
    asset_root: str,
) -> ManifestDeckBrowser:
    """Load and cache the current manifest deck."""
    return ManifestDeckBrowser(
        manifest_path,
        asset_root=asset_root,
    )


def _ensure_session_state(
    browser: ManifestDeckBrowser,
) -> None:
    """Initialize stable state for the active deck."""
    deck_signature = json.dumps(
        {
            "deck_id": browser.deck_id,
            "slide_ids": list(browser.slide_ids),
        },
        sort_keys=True,
    )

    defaults: dict[str, Any] = {
        "main_deck_signature": deck_signature,
        "main_active_slide_id": (
            browser.slide_ids[0]
        ),
        "main_cloud_text_allowed": True,
        "main_show_aoi_overlay": True,
        **build_main_turn_defaults(),
    }

    previous_signature = st.session_state.get(
        "main_deck_signature"
    )

    if (
        previous_signature is not None
        and previous_signature != deck_signature
    ):
        for key, value in defaults.items():
            st.session_state[key] = value
        return

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if (
        st.session_state["main_active_slide_id"]
        not in browser.slide_ids
    ):
        st.session_state["main_active_slide_id"] = (
            browser.slide_ids[0]
        )


def _render_sidebar(
    browser: ManifestDeckBrowser,
    view: MainUIViewModel,
) -> None:
    """Render deck and privacy controls."""
    st.sidebar.header("AttentiveSlides")

    st.sidebar.selectbox(
        "Interaction mode",
        options=["Private Manual Mode"],
        disabled=True,
    )

    st.sidebar.markdown("### Privacy status")
    st.sidebar.success("Camera: disabled")
    st.sidebar.success("Microphone: disabled")
    st.sidebar.success(
        "Biometric data collection: disabled"
    )

    st.sidebar.checkbox(
        (
            "Permit selected slide text to be "
            "sent to the cloud tutor"
        ),
        key="main_cloud_text_allowed",
        help=(
            "No cloud request is made during the "
            "Main UI shell stage."
        ),
    )

    st.sidebar.markdown("### Deck source")

    st.sidebar.selectbox(
        "Source",
        options=["Built-in manifest deck"],
        disabled=True,
    )

    st.sidebar.caption(
        f"Deck: {browser.title}"
    )
    st.sidebar.caption(
        f"Slides available: {view.total_slides}"
    )

    with st.sidebar.expander(
        "Developer deck details",
        expanded=False,
    ):
        st.json(
            {
                "deck_id": browser.deck_id,
                "manifest_path": str(
                    browser.manifest_path
                ),
                "slide_ids": list(
                    browser.slide_ids
                ),
            }
        )


def _render_header(
    view: MainUIViewModel,
) -> None:
    """Render the product title and modality status."""
    st.title("AttentiveSlides")

    st.caption(
        "A privacy-preserving slide tutor with "
        "manual target selection, typed commands, "
        "explicit confirmation, and grounded answers."
    )

    columns = st.columns(4)

    columns[0].metric(
        "Mode",
        "Manual",
    )
    columns[1].metric(
        "Camera",
        "Off",
    )
    columns[2].metric(
        "Microphone",
        "Off",
    )
    columns[3].metric(
        "Cloud tutor",
        (
            "Called"
            if view.privacy.cloud_llm_called
            else "Not called"
        ),
    )


def _render_navigation(
    browser: ManifestDeckBrowser,
    view: MainUIViewModel,
) -> None:
    """Render previous, slide selector, and next controls."""
    previous_id = browser.previous_slide_id(
        view.active_slide_id
    )
    next_id = browser.next_slide_id(
        view.active_slide_id
    )

    previous_column, selector_column, next_column = (
        st.columns(
            [0.18, 0.64, 0.18],
            gap="medium",
        )
    )

    previous_column.button(
        "← Previous",
        disabled=previous_id is None,
        width="stretch",
        on_click=_navigate_to_slide,
        args=(previous_id,),
    )

    selector_column.selectbox(
        "Current slide",
        options=list(browser.slide_ids),
        key="main_active_slide_id",
        format_func=lambda slide_id: (
            f"Slide {slide_id}"
        ),
        on_change=_reset_turn_state,
    )

    next_column.button(
        "Next →",
        disabled=next_id is None,
        width="stretch",
        on_click=_navigate_to_slide,
        args=(next_id,),
    )


def _navigate_to_slide(
    slide_id: int | None,
) -> None:
    """Move to a slide and clear turn-specific state."""
    if slide_id is None:
        return

    st.session_state["main_active_slide_id"] = (
        slide_id
    )

    _reset_turn_state()


def _reset_turn_state() -> None:
    """Clear all state associated with one tutoring turn."""
    reset_main_turn_state(
        st.session_state
    )


def _render_slide_workspace(
    view: MainUIViewModel,
) -> None:
    """Render the slide and AOI manifest overlay."""
    st.subheader("Slide workspace")

    slide = view.active_slide
    columns = st.columns(3)

    columns[0].metric(
        "Slide",
        (
            f"{view.active_slide_index + 1}"
            f" / {view.total_slides}"
        ),
    )
    columns[1].metric(
        "AOIs",
        len(slide.aois),
    )
    columns[2].metric(
        "Image",
        (
            "Available"
            if slide.image_available
            else "Fallback view"
        ),
    )

    st.checkbox(
        "Show AOI manifest overlay",
        key="main_show_aoi_overlay",
    )

    st.markdown(
        _slide_surface_html(
            slide,
            show_aois=st.session_state[
                "main_show_aoi_overlay"
            ],
        ),
        unsafe_allow_html=True,
    )

    st.caption(
        "The visible boxes are loaded from the AOI "
        "manifest. Manual rectangle drawing will be "
        "implemented in the next stage."
    )


def _render_manual_interaction() -> None:
    """Render the manual interaction placeholder."""
    st.subheader("Manual interaction")

    st.radio(
        "Target scope",
        options=[
            "Whole slide",
            "Manual region",
        ],
        horizontal=True,
        key="main_target_scope",
    )

    if (
        st.session_state["main_target_scope"]
        == "Manual region"
    ):
        st.info(
            "Manual region drawing is not active in "
            "this shell stage. The next stage will "
            "add normalized rectangle selection."
        )
    else:
        st.success(
            "Target scope: whole slide"
        )

    st.text_area(
        "Typed command",
        key="main_typed_command",
        height=110,
        placeholder=(
            "Examples: explain this, summarize this "
            "slide, quiz me on this"
        ),
    )

    command = st.session_state[
        "main_typed_command"
    ].strip()

    if command:
        st.caption(
            "Command captured. Intent resolution "
            "will be connected in a later stage."
        )
    else:
        st.caption(
            "Enter a command to prepare a "
            "manual interaction."
        )

    st.markdown("#### Turn readiness")

    target_ready = (
        st.session_state["main_target_scope"]
        == "Whole slide"
    )

    readiness_rows = [
        {
            "step": "Slide",
            "status": "ready",
        },
        {
            "step": "Target",
            "status": (
                "ready"
                if target_ready
                else "awaiting region"
            ),
        },
        {
            "step": "Typed command",
            "status": (
                "captured"
                if command
                else "not entered"
            ),
        },
        {
            "step": "Confirmation",
            "status": "not connected",
        },
        {
            "step": "Tutor",
            "status": "not called",
        },
    ]

    st.dataframe(
        readiness_rows,
        hide_index=True,
        width="stretch",
    )

    st.button(
        "Reset current turn",
        width="stretch",
        on_click=_reset_turn_state,
    )


def _render_lower_workspace(
    view: MainUIViewModel,
) -> None:
    """Render context, tutor, XAI, and session tabs."""
    context_tab, tutor_tab, xai_tab, session_tab = (
        st.tabs(
            [
                "Context preview",
                "Tutor",
                "Explainability",
                "Session",
            ]
        )
    )

    with context_tab:
        st.subheader("Context preview")

        st.markdown("#### Current slide text")

        if view.active_slide.slide_text.strip():
            st.write(
                view.active_slide.slide_text
            )
        else:
            st.warning(
                "No slide text is available."
            )

        st.markdown("#### AOI manifest")

        aoi_rows = [
            {
                "aoi_id": aoi.aoi_id,
                "name": aoi.name,
                "type": aoi.type,
                "bbox": list(aoi.bbox),
                "text": aoi.text,
            }
            for aoi in view.active_slide.aois
        ]

        if aoi_rows:
            st.dataframe(
                aoi_rows,
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption(
                "No AOIs are available for this slide."
            )

        with st.expander(
            "Neighbor slide context",
            expanded=False,
        ):
            st.write(
                (
                    view.active_slide
                    .neighbor_slide_text
                )
                or "No neighbor context."
            )

    with tutor_tab:
        st.subheader("Tutor workspace")

        st.info(
            "GroundedTutorAgent is not called during "
            "the Main UI shell stage."
        )

        st.code(
            "\n".join(
                [
                    "manual target",
                    "+ typed command",
                    "+ explicit confirmation",
                    "→ GroundedTutorAgent",
                    "→ validated answer",
                ]
            ),
            language="text",
        )

    with xai_tab:
        st.subheader("Explainability workspace")

        st.info(
            "The integrated XAI panel will be "
            "connected after manual selection, "
            "intent resolution, confirmation, and "
            "tutor generation are implemented."
        )

        st.markdown(
            "\n".join(
                [
                    "Planned explanation layers:",
                    "",
                    "1. Interaction provenance",
                    "2. Target mapping",
                    "3. Intent resolution",
                    "4. Confirmation and correction",
                    "5. Claim–source grounding",
                ]
            )
        )

    with session_tab:
        st.subheader("Session state")

        st.json(
            {
                "deck_id": view.deck_id,
                "active_slide_id": (
                    view.active_slide_id
                ),
                "interaction_mode": "manual",
                "target_scope": (
                    st.session_state[
                        "main_target_scope"
                    ]
                ),
                "typed_command": (
                    st.session_state[
                        "main_typed_command"
                    ]
                ),
                "manual_bbox": (
                    st.session_state[
                        "main_manual_bbox"
                    ]
                ),
                "selected_aoi_ids": (
                    st.session_state[
                        "main_selected_aoi_ids"
                    ]
                ),
                "confirmed": (
                    st.session_state[
                        "main_confirmed"
                    ]
                ),
                "camera_enabled": False,
                "microphone_enabled": False,
                "cloud_text_allowed": (
                    st.session_state[
                        "main_cloud_text_allowed"
                    ]
                ),
                "cloud_llm_called": False,
            }
        )


def _slide_surface_html(
    slide: MainUISlide,
    *,
    show_aois: bool,
) -> str:
    """Build the current slide surface."""
    image_html = _slide_image_html(slide)

    if show_aois:
        boxes = [
            _aoi_box_html(aoi)
            for aoi in slide.aois
            if aoi.aoi_id != "whole_slide"
        ]
        aoi_html = "\n".join(boxes)
    else:
        aoi_html = ""

    return f"""
<div style="
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    overflow: hidden;
    border: 1px solid rgba(128, 128, 128, 0.45);
    border-radius: 12px;
    background: #f7f7f7;
">
    {image_html}
    {aoi_html}
</div>
"""


def _slide_image_html(
    slide: MainUISlide,
) -> str:
    """Return an image or text fallback surface."""
    if (
        slide.image_available
        and slide.image_path is not None
    ):
        path = Path(slide.image_path)

        mime_type = mimetypes.guess_type(
            path.name
        )[0]

        if (
            mime_type is not None
            and mime_type.startswith("image/")
        ):
            encoded = base64.b64encode(
                path.read_bytes()
            ).decode("ascii")

            return (
                "<img "
                f'src="data:{mime_type};base64,{encoded}" '
                'style="'
                "position:absolute;"
                "inset:0;"
                "width:100%;"
                "height:100%;"
                "object-fit:contain;"
                "background:white;"
                '" />'
            )

    preview = html.escape(
        slide.slide_text[:900]
        or "Slide image unavailable."
    ).replace("\n", "<br>")

    return f"""
<div style="
    position: absolute;
    inset: 0;
    padding: 2rem;
    background: white;
    color: #222;
    overflow: auto;
">
    <h3>Slide {slide.slide_id}</h3>
    <p>{preview}</p>
</div>
"""


def _aoi_box_html(
    aoi: Any,
) -> str:
    """Render one normalized AOI box."""
    x1, y1, x2, y2 = aoi.bbox

    label = html.escape(
        str(aoi.name or aoi.aoi_id)
    )

    return f"""
<div
    title="{label}"
    style="
        position: absolute;
        left: {x1 * 100:.2f}%;
        top: {y1 * 100:.2f}%;
        width: {(x2 - x1) * 100:.2f}%;
        height: {(y2 - y1) * 100:.2f}%;
        border: 2px solid rgba(30, 110, 210, 0.85);
        background: rgba(30, 110, 210, 0.08);
        border-radius: 6px;
        box-sizing: border-box;
        pointer-events: none;
    "
>
    <span style="
        position: absolute;
        left: 3px;
        top: 3px;
        padding: 1px 5px;
        background: rgba(30, 110, 210, 0.92);
        color: white;
        border-radius: 4px;
        font-size: 11px;
        line-height: 1.4;
    ">
        {label}
    </span>
</div>
"""


if __name__ == "__main__":
    main()
