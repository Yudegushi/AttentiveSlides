"""Interactive privacy-preserving Main UI for AttentiveSlides."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(
    __file__
).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPOSITORY_ROOT),
    )

import streamlit as st
from PIL import (
    Image,
    ImageDraw,
)
from streamlit_drawable_canvas import (
    st_canvas,
)

from modules.system.main_ui_state import (
    MainUISlide,
    MainUIViewModel,
    ManifestDeckBrowser,
    build_main_turn_defaults,
    build_main_ui_view_model,
    reset_main_turn_state,
)
from modules.system.manual_targeting import (
    ManualSelectionResult,
    extract_latest_rectangle,
)
from modules.system.uploaded_deck_service import (
    UploadedDeckWorkspace,
)


BUILT_IN_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "mock_deck"
    / "mock_aoi_manifest.json"
)

RUNTIME_DATA_DIR = Path(
    "/root/autodl-tmp/"
    "project_data/runtime/"
    "attentive_slides"
)

CANVAS_WIDTH = 720


def main() -> None:
    st.set_page_config(
        page_title="AttentiveSlides",
        page_icon="📘",
        layout="wide",
    )

    workspace = _load_uploaded_workspace(
        str(RUNTIME_DATA_DIR)
    )

    built_in_browser = (
        _load_manifest_browser(
            str(
                BUILT_IN_MANIFEST_PATH
            ),
            str(REPOSITORY_ROOT),
        )
    )

    _initialize_global_state()

    _render_upload_controls(
        workspace
    )

    browser = _resolve_active_browser(
        workspace,
        built_in_browser,
    )

    _ensure_deck_state(browser)

    with st.spinner(
        "Preparing the current slide..."
    ):
        view = build_main_ui_view_model(
            browser,
            active_slide_id=(
                st.session_state[
                    "main_active_slide_id"
                ]
            ),
            cloud_text_allowed=(
                st.session_state[
                    "main_cloud_text_allowed"
                ]
            ),
        )

    _render_sidebar_status(
        browser,
        view,
    )
    _render_header(view)
    _render_navigation(
        browser,
        view,
    )

    slide_column, interaction_column = (
        st.columns(
            [1.55, 0.95],
            gap="large",
        )
    )

    with slide_column:
        _render_slide_workspace(view)

    with interaction_column:
        _render_manual_interaction(
            view
        )

    st.divider()
    _render_lower_workspace(view)


@st.cache_resource
def _load_manifest_browser(
    manifest_path: str,
    asset_root: str,
) -> ManifestDeckBrowser:
    return ManifestDeckBrowser(
        manifest_path,
        asset_root=asset_root,
    )


@st.cache_resource
def _load_uploaded_workspace(
    data_dir: str,
) -> UploadedDeckWorkspace:
    return UploadedDeckWorkspace(
        data_dir
    )


def _initialize_global_state() -> None:
    defaults: dict[str, Any] = {
        "main_uploaded_deck_id": None,
        "main_upload_message": None,
        "main_upload_error": None,
        "main_cloud_text_allowed": True,
        "main_show_aoi_overlay": True,
        "main_canvas_revision": 0,
        "main_selection_matches": [],
        "main_selection_text": "",
        "main_selection_error": None,
        **build_main_turn_defaults(),
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_upload_controls(
    workspace: UploadedDeckWorkspace,
) -> None:
    st.sidebar.header("AttentiveSlides")

    st.sidebar.markdown(
        "### Deck"
    )

    uploaded_file = (
        st.sidebar.file_uploader(
            "Upload a PDF slide deck",
            type=["pdf"],
            key="main_pdf_upload",
            help=(
                "The PDF is stored in the "
                "project runtime directory, "
                "not in the Git repository."
            ),
        )
    )

    load_clicked = st.sidebar.button(
        "Load PDF",
        disabled=uploaded_file is None,
        width="stretch",
    )

    if load_clicked:
        try:
            with st.spinner(
                "Registering uploaded PDF..."
            ):
                summary = (
                    workspace.ingest_pdf(
                        filename=(
                            uploaded_file.name
                        ),
                        content=(
                            uploaded_file
                            .getvalue()
                        ),
                    )
                )

        except Exception as exc:
            st.session_state[
                "main_upload_error"
            ] = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )
            st.session_state[
                "main_upload_message"
            ] = None

        else:
            st.session_state[
                "main_uploaded_deck_id"
            ] = summary.deck_id
            st.session_state[
                "main_upload_message"
            ] = (
                f"Loaded {summary.title} "
                f"({summary.page_count} pages)."
            )
            st.session_state[
                "main_upload_error"
            ] = None
            st.session_state[
                "main_deck_signature"
            ] = None
            _reset_turn_state()
            st.rerun()

    if st.session_state[
        "main_uploaded_deck_id"
    ]:
        if st.sidebar.button(
            "Use built-in demo deck",
            width="stretch",
        ):
            st.session_state[
                "main_uploaded_deck_id"
            ] = None
            st.session_state[
                "main_deck_signature"
            ] = None
            st.session_state[
                "main_upload_message"
            ] = (
                "Switched to the "
                "built-in demo deck."
            )
            st.session_state[
                "main_upload_error"
            ] = None
            _reset_turn_state()
            st.rerun()

    if st.session_state[
        "main_upload_message"
    ]:
        st.sidebar.success(
            st.session_state[
                "main_upload_message"
            ]
        )

    if st.session_state[
        "main_upload_error"
    ]:
        st.sidebar.error(
            st.session_state[
                "main_upload_error"
            ]
        )


def _resolve_active_browser(
    workspace: UploadedDeckWorkspace,
    built_in_browser: ManifestDeckBrowser,
) -> Any:
    deck_id = st.session_state[
        "main_uploaded_deck_id"
    ]

    if not deck_id:
        return built_in_browser

    try:
        return workspace.open_browser(
            deck_id
        )
    except Exception as exc:
        st.session_state[
            "main_upload_error"
        ] = (
            "Unable to reopen uploaded "
            f"deck: {type(exc).__name__}: "
            f"{exc}"
        )
        st.session_state[
            "main_uploaded_deck_id"
        ] = None

        return built_in_browser


def _ensure_deck_state(
    browser: Any,
) -> None:
    deck_signature = json.dumps(
        {
            "deck_id": browser.deck_id,
            "slide_ids": list(
                browser.slide_ids
            ),
        },
        sort_keys=True,
    )

    previous_signature = (
        st.session_state.get(
            "main_deck_signature"
        )
    )

    if (
        previous_signature
        != deck_signature
    ):
        st.session_state[
            "main_deck_signature"
        ] = deck_signature
        st.session_state[
            "main_active_slide_id"
        ] = browser.slide_ids[0]
        _reset_turn_state()

    if (
        st.session_state.get(
            "main_active_slide_id"
        )
        not in browser.slide_ids
    ):
        st.session_state[
            "main_active_slide_id"
        ] = browser.slide_ids[0]
        _reset_turn_state()


def _render_sidebar_status(
    browser: Any,
    view: MainUIViewModel,
) -> None:
    st.sidebar.markdown(
        "### Privacy status"
    )
    st.sidebar.success(
        "Camera: disabled"
    )
    st.sidebar.success(
        "Microphone: disabled"
    )
    st.sidebar.success(
        "Biometric collection: disabled"
    )

    st.sidebar.checkbox(
        (
            "Permit selected slide text "
            "to be sent to the cloud tutor"
        ),
        key="main_cloud_text_allowed",
        help=(
            "No cloud request is made "
            "during this stage."
        ),
    )

    st.sidebar.markdown(
        "### Active deck"
    )
    st.sidebar.caption(
        f"Deck: {browser.title}"
    )
    st.sidebar.caption(
        f"Slides: {view.total_slides}"
    )
    st.sidebar.caption(
        f"Deck ID: {browser.deck_id}"
    )


def _render_header(
    view: MainUIViewModel,
) -> None:
    st.title("AttentiveSlides")

    st.caption(
        "Manual slide targeting and typed "
        "commands without camera or microphone."
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
            if view.privacy
            .cloud_llm_called
            else "Not called"
        ),
    )


def _render_navigation(
    browser: Any,
    view: MainUIViewModel,
) -> None:
    previous_id = (
        browser.previous_slide_id(
            view.active_slide_id
        )
    )
    next_id = (
        browser.next_slide_id(
            view.active_slide_id
        )
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
        options=list(
            browser.slide_ids
        ),
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
    if slide_id is None:
        return

    st.session_state[
        "main_active_slide_id"
    ] = slide_id

    _reset_turn_state()


def _reset_turn_state() -> None:
    next_revision = (
        int(
            st.session_state.get(
                "main_canvas_revision",
                0,
            )
        )
        + 1
    )

    reset_main_turn_state(
        st.session_state
    )

    st.session_state[
        "main_canvas_revision"
    ] = next_revision
    st.session_state[
        "main_selection_matches"
    ] = []
    st.session_state[
        "main_selection_text"
    ] = ""
    st.session_state[
        "main_selection_error"
    ] = None


def _clear_manual_region() -> None:
    st.session_state[
        "main_manual_bbox"
    ] = None
    st.session_state[
        "main_selected_aoi_ids"
    ] = []
    st.session_state[
        "main_selection_matches"
    ] = []
    st.session_state[
        "main_selection_text"
    ] = ""
    st.session_state[
        "main_selection_error"
    ] = None
    st.session_state[
        "main_confirmed"
    ] = False
    st.session_state[
        "main_canvas_revision"
    ] = (
        int(
            st.session_state.get(
                "main_canvas_revision",
                0,
            )
        )
        + 1
    )


def _on_target_scope_change() -> None:
    _clear_manual_region()


def _render_slide_workspace(
    view: MainUIViewModel,
) -> None:
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
            else "Fallback"
        ),
    )

    if (
        st.session_state[
            "main_target_scope"
        ]
        == "Manual region"
    ):
        _render_manual_canvas(
            view
        )
    else:
        _set_whole_slide_target(
            view
        )
        _render_static_slide(
            slide
        )


def _render_static_slide(
    slide: MainUISlide,
) -> None:
    st.checkbox(
        "Show AOI overlay",
        key="main_show_aoi_overlay",
    )

    if (
        slide.image_available
        and slide.image_path
    ):
        image = Image.open(
            slide.image_path
        ).convert("RGB")

        if st.session_state[
            "main_show_aoi_overlay"
        ]:
            image = _draw_aoi_overlay(
                image,
                slide,
            )

        st.image(
            image,
            width="stretch",
        )
    else:
        with st.container(
            border=True
        ):
            st.markdown(
                f"### Slide "
                f"{slide.slide_id}"
            )
            st.write(
                slide.slide_text
                or "Slide image unavailable."
            )


def _render_manual_canvas(
    view: MainUIViewModel,
) -> None:
    slide = view.active_slide

    if (
        not slide.image_available
        or not slide.image_path
    ):
        st.warning(
            "Manual rectangle drawing "
            "requires a rendered slide image."
        )
        return

    background_image = Image.open(
        slide.image_path
    ).convert("RGB")

    image_width, image_height = (
        background_image.size
    )

    canvas_height = round(
        CANVAS_WIDTH
        * image_height
        / max(image_width, 1)
    )

    canvas_height = max(
        220,
        min(canvas_height, 720),
    )

    st.caption(
        "Drag one rectangle around the "
        "region you want to discuss."
    )

    canvas_result = st_canvas(
        fill_color=(
            "rgba(30, 110, 210, 0.20)"
        ),
        stroke_width=3,
        stroke_color="#1E6ED2",
        background_color="#FFFFFF",
        background_image=(
            background_image
        ),
        update_streamlit=True,
        height=canvas_height,
        width=CANVAS_WIDTH,
        drawing_mode="rect",
        display_toolbar=True,
        key=(
            f"manual_canvas_"
            f"{view.deck_id}_"
            f"{view.active_slide_id}_"
            f"{st.session_state['main_canvas_revision']}"
        ),
    )

    try:
        selection = (
            extract_latest_rectangle(
                canvas_result.json_data,
                canvas_width=CANVAS_WIDTH,
                canvas_height=canvas_height,
                aois=slide.aois,
            )
        )

    except Exception as exc:
        st.session_state[
            "main_selection_error"
        ] = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    else:
        st.session_state[
            "main_selection_error"
        ] = None

        if selection is None:
            st.session_state[
                "main_manual_bbox"
            ] = None
            st.session_state[
                "main_selected_aoi_ids"
            ] = []
            st.session_state[
                "main_selection_matches"
            ] = []
            st.session_state[
                "main_selection_text"
            ] = ""
        else:
            _store_manual_selection(
                selection
            )

    if st.session_state[
        "main_selection_error"
    ]:
        st.error(
            st.session_state[
                "main_selection_error"
            ]
        )

    if st.session_state[
        "main_manual_bbox"
    ]:
        st.success(
            "Manual region captured."
        )
    else:
        st.info(
            "No manual region has been "
            "captured yet."
        )

    st.button(
        "Clear selected region",
        width="stretch",
        on_click=_clear_manual_region,
    )


def _store_manual_selection(
    selection: ManualSelectionResult,
) -> None:
    st.session_state[
        "main_manual_bbox"
    ] = list(
        selection.bbox
    )

    st.session_state[
        "main_selected_aoi_ids"
    ] = [
        match.aoi_id
        for match in selection.matches
    ]

    st.session_state[
        "main_selection_matches"
    ] = [
        match.to_dict()
        for match in selection.matches
    ]

    st.session_state[
        "main_selection_text"
    ] = selection.selected_text

    st.session_state[
        "main_confirmed"
    ] = False


def _set_whole_slide_target(
    view: MainUIViewModel,
) -> None:
    st.session_state[
        "main_manual_bbox"
    ] = [
        0.0,
        0.0,
        1.0,
        1.0,
    ]

    whole_slide = next(
        (
            aoi
            for aoi
            in view.active_slide.aois
            if aoi.aoi_id
            == "whole_slide"
        ),
        None,
    )

    st.session_state[
        "main_selected_aoi_ids"
    ] = (
        ["whole_slide"]
        if whole_slide is not None
        else []
    )

    st.session_state[
        "main_selection_matches"
    ] = []

    st.session_state[
        "main_selection_text"
    ] = (
        view.active_slide.slide_text
    )


def _render_manual_interaction(
    view: MainUIViewModel,
) -> None:
    st.subheader("Manual interaction")

    st.radio(
        "Target scope",
        options=[
            "Whole slide",
            "Manual region",
        ],
        horizontal=True,
        key="main_target_scope",
        on_change=_on_target_scope_change,
    )

    st.text_area(
        "Typed command",
        key="main_typed_command",
        height=120,
        placeholder=(
            "Examples: explain this, "
            "summarize this, quiz me "
            "on this"
        ),
    )

    command = st.session_state[
        "main_typed_command"
    ].strip()

    target_ready = bool(
        st.session_state[
            "main_manual_bbox"
        ]
    )

    command_ready = bool(command)

    if target_ready:
        st.success(
            "Target is ready."
        )
    else:
        st.warning(
            "Select a target region."
        )

    if command_ready:
        st.success(
            "Typed command captured."
        )
    else:
        st.info(
            "Enter a typed command."
        )

    st.markdown(
        "#### Selected target"
    )

    bbox = st.session_state[
        "main_manual_bbox"
    ]

    if bbox:
        st.code(
            json.dumps(
                {
                    "slide_id": (
                        view.active_slide_id
                    ),
                    "bbox": bbox,
                    "target_source": (
                        "manual_rectangle"
                        if (
                            st.session_state[
                                "main_target_scope"
                            ]
                            == "Manual region"
                        )
                        else "whole_slide"
                    ),
                },
                indent=2,
            ),
            language="json",
        )

    matches = st.session_state[
        "main_selection_matches"
    ]

    if matches:
        st.markdown(
            "#### AOI matches"
        )
        st.dataframe(
            matches,
            hide_index=True,
            width="stretch",
        )
    elif (
        st.session_state[
            "main_target_scope"
        ]
        == "Manual region"
        and bbox
    ):
        st.warning(
            "The rectangle does not "
            "strongly overlap a known AOI."
        )

    selected_text = (
        st.session_state[
            "main_selection_text"
        ].strip()
    )

    st.markdown(
        "#### Selected context"
    )

    if selected_text:
        st.text_area(
            "Context extracted from target",
            value=selected_text,
            height=180,
            disabled=True,
        )
    else:
        st.caption(
            "No text-bearing AOI "
            "has been selected."
        )

    readiness = [
        {
            "step": "Slide",
            "status": "ready",
        },
        {
            "step": "Manual target",
            "status": (
                "ready"
                if target_ready
                else "missing"
            ),
        },
        {
            "step": "Typed command",
            "status": (
                "captured"
                if command_ready
                else "missing"
            ),
        },
        {
            "step": "Intent resolution",
            "status": "next stage",
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
        readiness,
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
    (
        context_tab,
        tutor_tab,
        xai_tab,
        session_tab,
    ) = st.tabs(
        [
            "Context preview",
            "Tutor",
            "Explainability",
            "Session",
        ]
    )

    with context_tab:
        st.subheader(
            "Context preview"
        )

        st.markdown(
            "#### Selected context"
        )

        st.write(
            st.session_state[
                "main_selection_text"
            ]
            or "No selected context."
        )

        st.markdown(
            "#### Current slide text"
        )
        st.write(
            view.active_slide.slide_text
            or "No slide text."
        )

        st.markdown(
            "#### AOI manifest"
        )

        st.dataframe(
            [
                {
                    "aoi_id": aoi.aoi_id,
                    "name": aoi.name,
                    "type": aoi.type,
                    "bbox": list(
                        aoi.bbox
                    ),
                    "text": aoi.text,
                }
                for aoi
                in view.active_slide.aois
            ],
            hide_index=True,
            width="stretch",
        )

    with tutor_tab:
        st.subheader(
            "Tutor workspace"
        )
        st.info(
            "TutorAgent integration "
            "is not active in this stage."
        )

    with xai_tab:
        st.subheader(
            "Explainability workspace"
        )
        st.json(
            {
                "target_source": (
                    "manual_rectangle"
                    if (
                        st.session_state[
                            "main_target_scope"
                        ]
                        == "Manual region"
                    )
                    else "whole_slide"
                ),
                "selected_bbox": (
                    st.session_state[
                        "main_manual_bbox"
                    ]
                ),
                "mapped_aoi_ids": (
                    st.session_state[
                        "main_selected_aoi_ids"
                    ]
                ),
                "mapping_candidates": (
                    st.session_state[
                        "main_selection_matches"
                    ]
                ),
                "intent_source": (
                    "typed_text"
                ),
                "typed_command": (
                    st.session_state[
                        "main_typed_command"
                    ]
                ),
                "confirmation": (
                    "not yet performed"
                ),
            }
        )

    with session_tab:
        st.subheader(
            "Session state"
        )
        st.json(
            {
                "deck_id": view.deck_id,
                "active_slide_id": (
                    view.active_slide_id
                ),
                "uploaded_deck_id": (
                    st.session_state[
                        "main_uploaded_deck_id"
                    ]
                ),
                "target_scope": (
                    st.session_state[
                        "main_target_scope"
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
                "typed_command": (
                    st.session_state[
                        "main_typed_command"
                    ]
                ),
                "camera_enabled": False,
                "microphone_enabled": False,
                "cloud_llm_called": False,
            }
        )


def _draw_aoi_overlay(
    image: Image.Image,
    slide: MainUISlide,
) -> Image.Image:
    result = image.copy()
    draw = ImageDraw.Draw(
        result
    )

    width, height = result.size

    for aoi in slide.aois:
        if aoi.aoi_id == "whole_slide":
            continue

        x_min, y_min, x_max, y_max = (
            aoi.bbox
        )

        rectangle = (
            round(x_min * width),
            round(y_min * height),
            round(x_max * width),
            round(y_max * height),
        )

        draw.rectangle(
            rectangle,
            outline=(30, 110, 210),
            width=max(
                2,
                round(width / 500),
            ),
        )

        draw.text(
            (
                rectangle[0] + 4,
                rectangle[1] + 4,
            ),
            str(
                aoi.name
                or aoi.aoi_id
            ),
            fill=(30, 70, 160),
        )

    return result


if __name__ == "__main__":
    main()
