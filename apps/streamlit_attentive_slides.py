"""Interactive privacy-preserving Main UI for AttentiveSlides."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace

import json
from io import BytesIO
import os
import sys
import time
import uuid
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

from modules.audio.faster_whisper_transcriber import (
    FasterWhisperTranscriber,
)
from modules.audio.streaming_vad import default_vad_backend
from modules.audio.transcriber import TranscriptionConfig
from modules.audio.voice_turn_detector import VoiceTurnDetector
from modules.logging.interaction_logger import InteractionLogger
from modules.media import BrowserMediaSource
from modules.media.live_ingress_service import LiveIngressService
from modules.media.single_port_transport import FallbackMediaIngress

from modules.system.safe_table import (
    records_to_html,
)
from modules.system.conversation_history import (
    build_conversation_turn,
    export_conversation,
    upsert_conversation_turn,
)
from modules.system.integrated_pipeline_xai import (
    build_integrated_pipeline_xai,
)

from modules.system.main_tutor_integration import (
    assess_tutor_generation,
    generate_main_tutor_response,
)
from modules.tutor.api_llm_client import (
    OpenAICompatibleLLMClient,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
)

from modules.system.main_ui_state import (
    MainUISlide,
    MainUIViewModel,
    ManifestDeckBrowser,
    build_main_conversation_defaults,
    build_main_live_defaults,
    build_main_turn_defaults,
    build_main_ui_view_model,
    normalize_main_slide_width_percent,
    reset_main_conversation_state,
    reset_main_live_turn_state,
    reset_main_turn_state,
    write_main_interaction_once,
)
from modules.system.manual_confirmation import (
    assess_manual_confirmation,
    build_manual_confirmation_preview,
    confirm_manual_interaction,
)
from modules.system.manual_intent import (
    QUICK_INTENT_ACTIONS,
    ManualIntentResolution,
    assess_intent_target,
    make_quick_action_intent_input,
    make_typed_intent_input,
    resolve_manual_intent,
)
from modules.system.manual_targeting import (
    ManualSelectionResult,
    map_bbox_to_aois,
)
from modules.system.active_deck_slide_provider import (
    ActiveDeckSlideProvider,
)
from modules.system.audio_worker import AudioWorker
from modules.system.controller import SystemController
from modules.system.live_ui_bridge import (
    LatestProposalInbox,
    LiveInteractionProposal,
    MainUILiveRuntime,
    ProposalTurnRunner,
    build_live_interaction_input,
    map_gaze_grid_only,
    resolve_grid_target,
    should_auto_confirm,
)
from modules.system.sensing_snapshot_store import SensingSnapshotStore
from modules.system.sensing_worker import SensingWorker
from modules.system.slide_geometry import (
    SlideViewportGeometry,
    parse_component_geometry,
)
from modules.system.turn_context import TurnContextCollector
from modules.system.uploaded_deck_service import (
    UploadedDeckWorkspace,
)
from modules.ui.slide_viewport_component import render_slide_viewport


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

MAIN_INTERACTION_LOG_PATH = (
    RUNTIME_DATA_DIR
    / "logs"
    / "main_interactions.jsonl"
)


@dataclass
class MainLiveResources:
    """One cached production graph shared by Main UI reruns."""

    runtime: MainUILiveRuntime
    provider: ActiveDeckSlideProvider
    snapshots: SensingSnapshotStore
    inbox: LatestProposalInbox
    ingress: FallbackMediaIngress
    service: LiveIngressService
    bound_deck_id: str | None = None
    bound_slide_id: int | None = None


@st.cache_resource
def build_main_live_resources(
    *,
    start_ingress: bool = True,
) -> MainLiveResources:
    """Build the thin Live proposal graph; the Main UI owns tutoring."""
    media_source = BrowserMediaSource()
    provider = ActiveDeckSlideProvider()
    snapshots = SensingSnapshotStore()
    sensing_worker = SensingWorker(
        media_source=media_source,
        slide_provider=provider,
        snapshot_store=snapshots,
        gaze_to_aoi=map_gaze_grid_only,
    )
    transcriber = FasterWhisperTranscriber(
        TranscriptionConfig(
            engine="faster_whisper",
            model_size=os.environ.get(
                "ATTENTIVE_WHISPER_MODEL",
                "small",
            ),
        )
    )
    audio_worker = AudioWorker(
        media_source=media_source,
        detector=VoiceTurnDetector(
            default_vad_backend()
        ),
        transcribe=transcriber.transcribe,
    )
    collector = TurnContextCollector(
        slide_provider=provider,
        snapshot_store=snapshots,
        aggregation_key="gaze_grid",
    )
    inbox = LatestProposalInbox()
    runner = ProposalTurnRunner(
        context_collector=collector,
        inbox=inbox,
    )
    controller = SystemController(
        media_source=media_source,
        sensing_worker=sensing_worker,
        audio_worker=audio_worker,
        context_collector=collector,
        turn_runner=runner,
    )
    runtime = MainUILiveRuntime(
        controller=controller,
        inbox=inbox,
        snapshot_store=snapshots,
    )
    ingress = FallbackMediaIngress(
        media_source,
        start_armed=False,
        coordinated_activation=True,
        media_stale_after_seconds=2.0,
        inactive_after_seconds=3.0,
    )
    capture_html = (
        REPOSITORY_ROOT
        / "modules"
        / "media"
        / "live_capture_component"
        / "index.html"
    ).read_text(encoding="utf-8")
    service = LiveIngressService(
        runtime=runtime,
        source=media_source,
        ingress=ingress,
        capture_html=capture_html,
    )
    if start_ingress:
        service.ensure_started()
    return MainLiveResources(
        runtime=runtime,
        provider=provider,
        snapshots=snapshots,
        inbox=inbox,
        ingress=ingress,
        service=service,
    )


@st.cache_resource
def _main_interaction_logger() -> InteractionLogger:
    return InteractionLogger(MAIN_INTERACTION_LOG_PATH)



def main() -> None:
    st.set_page_config(
        page_title="AttentiveSlides",
        page_icon="📘",
        layout="wide",
    )

    _inject_compact_ui_css()

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
    _normalize_widget_state()

    _render_upload_controls(
        workspace
    )

    browser = _resolve_active_browser(
        workspace,
        built_in_browser,
    )

    _ensure_deck_state(browser)

    try:
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

    except Exception as exc:
        st.error(
            "Unable to prepare the uploaded PDF. "
            "The native PDF worker failed, but "
            "the Streamlit server remains active."
        )

        st.exception(exc)
        st.stop()

    live_resources = build_main_live_resources(
        start_ingress=(
            os.environ.get(
                "ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST",
                "0",
            )
            != "1"
        )
    )
    _bind_main_live_resources(
        live_resources,
        browser=browser,
        view=view,
    )
    _render_live_controls(
        live_resources
    )

    _render_sidebar_status(
        browser,
        view,
    )

    _render_header(view)
    _render_slide_selector(
        browser
    )
    geometry = _render_slide_workspace(
        view
    )
    _render_navigation(
        browser,
        view,
    )
    _render_manual_interaction(
        view,
        live_resources=live_resources,
        geometry=geometry,
    )
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


def _load_uploaded_workspace(
    data_dir: str,
) -> UploadedDeckWorkspace:
    """Create a lightweight disk-backed workspace per rerun."""
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
        "main_slide_width_percent": 100,
        "main_selection_matches": [],
        "main_selection_text": "",
        "main_selection_error": None,
        **build_main_turn_defaults(),
        **build_main_conversation_defaults(),
        **build_main_live_defaults(),
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    # Thumbnail strip state.
    st.session_state.setdefault(
        "main_thumbnail_window_start",
        0,
    )


def _render_records_table(
    data: Any,
    *args: Any,
    **kwargs: Any,
) -> None:
    """Render a small table without Pandas or PyArrow."""
    del args
    del kwargs

    st.markdown(
        records_to_html(data),
        unsafe_allow_html=True,
    )


def _normalized_range(
    value: Any,
    *,
    default: tuple[float, float],
) -> tuple[float, float]:
    """Return a valid normalized range for a range slider."""
    if (
        not isinstance(
            value,
            (list, tuple),
        )
        or len(value) != 2
    ):
        return default

    try:
        lower = max(
            0.0,
            min(
                1.0,
                float(value[0]),
            ),
        )
        upper = max(
            0.0,
            min(
                1.0,
                float(value[1]),
            ),
        )

    except (
        TypeError,
        ValueError,
    ):
        return default

    if lower >= upper:
        return default

    return (
        round(lower, 4),
        round(upper, 4),
    )


def _normalize_widget_state() -> None:
    """Normalize persisted state before widgets are instantiated."""
    st.session_state[
        "main_slide_width_percent"
    ] = normalize_main_slide_width_percent(
        st.session_state.get("main_slide_width_percent")
    )

    boolean_defaults = {
        "main_cloud_text_allowed": True,
        "main_history_enabled": True,
        "main_show_aoi_overlay": True,
        "main_manual_region_active": False,
    }

    for key, default in boolean_defaults.items():
        value = st.session_state.get(
            key,
            default,
        )

        st.session_state[key] = (
            value
            if isinstance(value, bool)
            else default
        )

    try:
        history_limit = int(
            st.session_state.get(
                "main_history_max_items",
                4,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        history_limit = 4

    st.session_state[
        "main_history_max_items"
    ] = max(
        1,
        min(
            4,
            history_limit,
        ),
    )

    st.session_state[
        "main_region_x_range"
    ] = _normalized_range(
        st.session_state.get(
            "main_region_x_range"
        ),
        default=(0.10, 0.90),
    )

    st.session_state[
        "main_region_y_range"
    ] = _normalized_range(
        st.session_state.get(
            "main_region_y_range"
        ),
        default=(0.10, 0.90),
    )

    if not isinstance(
        st.session_state.get(
            "main_conversation_turns"
        ),
        list,
    ):
        st.session_state[
            "main_conversation_turns"
        ] = []

    if not isinstance(
        st.session_state.get("main_logged_interaction_ids"),
        list,
    ):
        st.session_state["main_logged_interaction_ids"] = []

    if st.session_state.get("main_interaction_mode") not in {
        "Manual",
        "Live",
    }:
        st.session_state["main_interaction_mode"] = "Manual"

    if st.session_state.get("main_confirmation_policy") not in {
        "Always confirm",
        "Confidence-based auto",
    }:
        st.session_state["main_confirmation_policy"] = "Always confirm"

    st.session_state[
        "main_widget_error"
    ] = None
    # Canonical target scope is stored independently from the user-facing label.
    raw_target_scope = str(
        st.session_state.get(
            "main_target_scope",
            "Whole slide",
        )
    ).strip()

    target_scope_aliases = {
        "whole slide": "Whole slide",
        "use whole slide": "Whole slide",
        "whole_slide": "Whole slide",
        "manual region": "Manual region",
        "select region": "Manual region",
        "manual_rectangle": "Manual region",
    }

    st.session_state[
        "main_target_scope"
    ] = target_scope_aliases.get(
        raw_target_scope.casefold(),
        "Whole slide",
    )


@st.cache_data(show_spinner=False)
def _read_slide_image_bytes(
    image_path: str,
    modified_time_ns: int,
) -> bytes:
    """Read immutable image bytes without keeping a file open."""
    del modified_time_ns

    return Path(
        image_path
    ).read_bytes()


def _load_slide_image(
    image_path: str,
) -> Image.Image:
    """Load an RGB image from cached bytes."""
    path = Path(image_path)

    payload = _read_slide_image_bytes(
        str(path),
        path.stat().st_mtime_ns,
    )

    with Image.open(
        BytesIO(payload)
    ) as source:
        return source.convert("RGB")


def _on_cloud_permission_change() -> None:
    """Handle cloud-permission changes after Streamlit updates the key."""
    st.session_state[
        "main_widget_error"
    ] = None


def _on_history_enabled_change() -> None:
    """Handle history enablement without rewriting its widget key."""
    st.session_state[
        "main_widget_error"
    ] = None


def _on_history_limit_change() -> None:
    """Handle a valid history-limit change."""
    st.session_state[
        "main_widget_error"
    ] = None


def _on_overlay_change() -> None:
    """Handle overlay visibility changes."""
    st.session_state[
        "main_widget_error"
    ] = None


def _on_live_preference_change() -> None:
    st.session_state["main_widget_error"] = None


def _bind_main_live_resources(
    resources: MainLiveResources,
    *,
    browser: Any,
    view: MainUIViewModel,
) -> None:
    """Bind the canonical browser before media can be armed."""
    if resources.bound_deck_id != view.deck_id:
        resources.service.set_master_enabled(False)
        resources.service.reconcile_once()
        st.session_state["main_live_master_enabled"] = False
        resources.provider.set_browser(browser)
        resources.inbox.clear()
        resources.snapshots.clear()
        resources.runtime.set_slide(view.active_slide_id)
        resources.bound_deck_id = view.deck_id
        resources.bound_slide_id = view.active_slide_id
        return

    if resources.bound_slide_id != view.active_slide_id:
        resources.runtime.set_slide(view.active_slide_id)
        resources.bound_slide_id = view.active_slide_id


def _render_live_controls(
    resources: MainLiveResources,
) -> None:
    """Add the small mode/policy controls to the existing sidebar."""
    st.sidebar.markdown("### Interaction")
    st.sidebar.radio(
        "Mode",
        options=["Manual", "Live"],
        horizontal=True,
        key="main_interaction_mode",
        on_change=_on_live_preference_change,
    )
    live_mode = (
        st.session_state["main_interaction_mode"]
        == "Live"
    )

    if live_mode:
        st.sidebar.checkbox(
            "Enable camera and microphone",
            key="main_live_master_enabled",
            on_change=_on_live_preference_change,
            help=(
                "Media remains local to the runtime; only confirmed "
                "text may be sent to the cloud tutor."
            ),
        )
        st.sidebar.radio(
            "Confirmation policy",
            options=[
                "Always confirm",
                "Confidence-based auto",
            ],
            key="main_confirmation_policy",
            on_change=_on_live_preference_change,
        )
        if (
            st.session_state["main_confirmation_policy"]
            == "Confidence-based auto"
        ):
            st.sidebar.slider(
                "Auto-confirm confidence",
                min_value=0.70,
                max_value=0.95,
                value=0.80,
                step=0.01,
                key="main_auto_confirm_threshold",
                on_change=_on_live_preference_change,
            )
    else:
        st.session_state["main_live_master_enabled"] = False

    enabled = bool(
        live_mode
        and st.session_state["main_live_master_enabled"]
    )
    resources.service.set_master_enabled(enabled)
    resources.service.reconcile_once()

    runtime_state = resources.runtime.controller.state.value
    session = resources.ingress.session_snapshot()
    st.sidebar.caption(
        f"Transport: {'armed' if enabled else 'off'} · "
        f"Runtime: {runtime_state} · "
        f"Media: {'ready' if session.video_fresh and session.audio_fresh else 'waiting'}"
    )

    if enabled:
        with st.sidebar.expander(
            "Camera and microphone preview",
            expanded=False,
        ):
            st.iframe("/capture", height=340)


def _on_manual_region_change() -> None:
    """Activate a changed normalized region and invalidate old output."""
    st.session_state[
        "main_manual_region_active"
    ] = True

    st.session_state[
        "main_widget_error"
    ] = None

    _invalidate_confirmation()


def _activate_manual_region() -> None:
    """Apply the current normalized region."""
    st.session_state[
        "main_manual_region_active"
    ] = True

    st.session_state[
        "main_widget_error"
    ] = None

    _invalidate_confirmation()


def _render_upload_controls(
    workspace: UploadedDeckWorkspace,
) -> None:

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
        key="main_load_pdf_button",
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

    if st.session_state[
        "main_uploaded_deck_id"
    ]:
        if st.sidebar.button(
            "Use built-in demo deck",
            width="stretch",
            key="main_use_demo_button",
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
    """Synchronize deck state and isolate conversation history."""
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

    if previous_signature != deck_signature:
        previous_conversation_deck = (
            st.session_state.get(
                "main_conversation_deck_id"
            )
        )

        if (
            previous_conversation_deck
            != browser.deck_id
        ):
            reset_main_conversation_state(
                st.session_state,
                deck_id=browser.deck_id,
            )
        else:
            st.session_state[
                "main_conversation_deck_id"
            ] = browser.deck_id

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
    live_enabled = bool(
        st.session_state.get("main_interaction_mode") == "Live"
        and st.session_state.get("main_live_master_enabled")
    )
    with st.sidebar.expander(
        "Privacy Status",
        expanded=False,
    ):
        st.markdown(
            "**Camera**"
        )

        st.caption(
            "On for coarse 3×3 viewport gaze targeting."
            if live_enabled
            else "Off. No camera frames are collected."
        )

        st.markdown(
            "**Microphone**"
        )

        st.caption(
            "On for local VAD and speech transcription."
            if live_enabled
            else "Off. No audio is collected."
        )

        st.checkbox(
            (
                "Permit selected slide text "
                "to be sent to the cloud tutor"
            ),
            key="main_cloud_text_allowed",
            help=(
                "Only confirmed slide context and "
                "sanitized conversation history "
                "may be transmitted."
            ),
            on_change=(
                _on_cloud_permission_change
            ),
        )
    st.sidebar.markdown(
        "### Conversation Memory"
    )

    st.sidebar.checkbox(
        "Use recent conversation history",
        key="main_history_enabled",
        help=(
            "Only sanitized previous turns are "
            "included. Current slide evidence "
            "remains the grounding source."
        ),
        on_change=(
            _on_history_enabled_change
        ),
    )

    st.session_state[
        "main_history_max_items"
    ] = 4

    st.sidebar.caption(
        "Tutor context uses the latest "
        "4 sanitized turns."
    )

    st.sidebar.caption(
        "Stored in this session: "
        f"{len(st.session_state['main_conversation_turns'])} "
        "turn(s)."
    )

    st.sidebar.markdown(
        "### System Status"
    )

    sidebar_status_row_1 = (
        st.sidebar.columns(2)
    )

    with sidebar_status_row_1[0]:
        with st.container(
            border=True
        ):
            st.caption("MODE")
            st.markdown(
                f"**{st.session_state['main_interaction_mode']}**"
            )

    with sidebar_status_row_1[1]:
        with st.container(
            border=True
        ):
            st.caption("CAMERA")
            st.markdown(
                f"**{'On' if live_enabled else 'Off'}**"
            )

    sidebar_status_row_2 = (
        st.sidebar.columns(2)
    )

    with sidebar_status_row_2[0]:
        with st.container(
            border=True
        ):
            st.caption("MICROPHONE")
            st.markdown(
                f"**{'On' if live_enabled else 'Off'}**"
            )

    cloud_api_configured = bool(
        os.environ.get(
            "DASHSCOPE_API_KEY"
        )
    )

    if not st.session_state[
        "main_cloud_text_allowed"
    ]:
        cloud_tutor_status = "Blocked"

    elif cloud_api_configured:
        cloud_tutor_status = "Ready"

    else:
        cloud_tutor_status = "No API key"

    with sidebar_status_row_2[1]:
        with st.container(
            border=True
        ):
            st.caption("CLOUD TUTOR")
            st.markdown(
                f"**{cloud_tutor_status}**"
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


def _inject_compact_ui_css() -> None:
    """Use the viewport for the learner-facing workspace."""
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 96vw;
            padding-top: 0.8rem;
            padding-bottom: 1.2rem;
        }

        h1 {
            margin-bottom: 0.15rem;
        }

        div[data-testid="stImage"] {
            width: 100%;
        }

        div[data-testid="stImage"] img {
            width: 100%;
            max-height: 72vh;
            object-fit: contain;
        }

        div[data-testid="stCustomComponentV1"] iframe {
            width: 100% !important;
            max-width: 100% !important;
        }

        div[data-testid="stExpander"] details {
            border-radius: 0.7rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

@st.cache_data(show_spinner=False)
def _thumbnail_png_bytes(
    image_path: str,
    modified_time_ns: int,
    max_width: int = 220,
    max_height: int = 124,
) -> bytes:
    """Create a small cached PNG thumbnail without retaining open files."""
    del modified_time_ns

    path = Path(image_path)

    with Image.open(path) as source:
        thumbnail = source.convert("RGB")

    try:
        resampling = getattr(
            Image,
            "Resampling",
            Image,
        ).LANCZOS

        thumbnail.thumbnail(
            (max_width, max_height),
            resampling,
        )

        buffer = BytesIO()
        thumbnail.save(
            buffer,
            format="PNG",
            optimize=True,
        )
        return buffer.getvalue()

    finally:
        thumbnail.close()


def _shift_thumbnail_window(
    delta: int,
    maximum_start: int,
) -> None:
    current = int(
        st.session_state.get(
            "main_thumbnail_window_start",
            0,
        )
    )

    st.session_state[
        "main_thumbnail_window_start"
    ] = max(
        0,
        min(
            maximum_start,
            current + int(delta),
        ),
    )


def _target_scope_label(
    value: str,
) -> str:
    if value == "Whole slide":
        return "Use whole slide"

    return "Select region"



def _render_slide_selector(
    browser: Any,
) -> None:
    """Render a horizontal, clickable slide-preview strip."""
    slide_ids = list(
        browser.slide_ids
    )

    if not slide_ids:
        return

    active_slide_id = st.session_state[
        "main_active_slide_id"
    ]

    try:
        active_index = slide_ids.index(
            active_slide_id
        )
    except ValueError:
        active_index = 0
        active_slide_id = slide_ids[0]
        st.session_state[
            "main_active_slide_id"
        ] = active_slide_id

    window_size = min(
        7,
        len(slide_ids),
    )
    maximum_start = max(
        0,
        len(slide_ids) - window_size,
    )

    start = int(
        st.session_state.get(
            "main_thumbnail_window_start",
            0,
        )
    )
    start = max(
        0,
        min(maximum_start, start),
    )

    if not (
        start
        <= active_index
        < start + window_size
    ):
        start = max(
            0,
            min(
                maximum_start,
                active_index
                - window_size // 2,
            ),
        )

    st.session_state[
        "main_thumbnail_window_start"
    ] = start

    visible_slide_ids = slide_ids[
        start : start + window_size
    ]

    widths = [0.08] + [1.0] * len(
        visible_slide_ids
    ) + [0.08]

    columns = st.columns(
        widths,
        gap="small",
        vertical_alignment="center",
    )

    columns[0].button(
        "‹",
        key="main_thumbnail_window_previous",
        disabled=start == 0,
        help="Show earlier slide previews",
        on_click=_shift_thumbnail_window,
        args=(-window_size, maximum_start),
        width="stretch",
    )

    for offset, slide_id in enumerate(
        visible_slide_ids,
        start=1,
    ):
        with columns[offset]:
            with st.container(
                border=True
            ):
                try:
                    preview_slide = (
                        browser.get_slide(
                            slide_id
                        )
                    )
                except Exception:
                    preview_slide = None

                if (
                    preview_slide is not None
                    and preview_slide.image_available
                    and preview_slide.image_path
                ):
                    preview_path = Path(
                        preview_slide.image_path
                    )

                    st.image(
                        _thumbnail_png_bytes(
                            str(preview_path),
                            preview_path.stat().st_mtime_ns,
                        ),
                        width="stretch",
                    )

                else:
                    st.markdown(
                        "<div style='height:4.8rem;display:flex;"
                        "align-items:center;justify-content:center;"
                        "border:1px dashed rgba(128,128,128,.35);"
                        "border-radius:.35rem;'>Preview</div>",
                        unsafe_allow_html=True,
                    )

                st.button(
                    str(slide_id),
                    key=(
                        "main_slide_preview_"
                        f"{slide_id}"
                    ),
                    type=(
                        "primary"
                        if slide_id
                        == active_slide_id
                        else "secondary"
                    ),
                    width="stretch",
                    on_click=_navigate_to_slide,
                    args=(slide_id,),
                    help=(
                        "Open slide "
                        f"{slide_id}"
                    ),
                )

    columns[-1].button(
        "›",
        key="main_thumbnail_window_next",
        disabled=start >= maximum_start,
        help="Show later slide previews",
        on_click=_shift_thumbnail_window,
        args=(window_size, maximum_start),
        width="stretch",
    )



def _render_compact_target_summary(
    view: MainUIViewModel,
) -> None:
    bbox = st.session_state.get(
        "main_manual_bbox"
    )

    selected_aoi_ids = (
        st.session_state.get(
            "main_selected_aoi_ids",
            [],
        )
    )

    if not bbox:
        st.caption(
            "No target has been selected."
        )
        return

    st.caption(
        "Target ready · "
        f"Slide {view.active_slide_id} · "
        f"{len(selected_aoi_ids)} AOI match(es)"
    )

    if selected_aoi_ids:
        st.caption(
            "Matched: "
            + ", ".join(
                selected_aoi_ids
            )
        )


def _render_target_column(
    view: MainUIViewModel,
) -> None:
    st.markdown(
        "### 1. Select region"
    )

    st.radio(
        "Target scope",
        options=[
            "Whole slide",
            "Manual region",
        ],
        format_func=_target_scope_label,
        horizontal=True,
        key="main_target_scope",
        on_change=_on_target_scope_change,
    )

    st.checkbox(
        "Show AOI overlay",
        key="main_show_aoi_overlay",
        on_change=_on_overlay_change,
    )

    if (
        st.session_state[
            "main_target_scope"
        ]
        == "Manual region"
    ):
        st.caption(
            "Drag directly on the slide to draw one rectangular target."
        )

        st.button(
            "Clear selected region",
            key="main_clear_region_button",
            width="stretch",
            on_click=_clear_manual_region,
        )

    else:
        _set_whole_slide_target(
            view
        )

        st.caption(
            "The complete slide is selected."
        )

    _render_compact_target_summary(
        view
    )



def _render_intent_column(
    view: MainUIViewModel,
) -> None:
    st.markdown(
        "### 2. Ask"
    )

    _render_quick_intent_actions()

    st.text_area(
        "Typed command",
        key="main_typed_command",
        height=110,
        placeholder=(
            "Examples: explain this, "
            "summarize this, quiz me"
        ),
        on_change=_on_typed_command_change,
    )

    command = st.session_state[
        "main_typed_command"
    ].strip()

    target_ready = bool(
        st.session_state[
            "main_manual_bbox"
        ]
    )

    resolution = (
        _resolve_current_intent()
    )

    assessment = assess_intent_target(
        resolution,
        target_available=target_ready,
        selected_aoi_count=len(
            st.session_state[
                "main_selected_aoi_ids"
            ]
        ),
    )

    if st.session_state[
        "main_intent_error"
    ]:
        st.error(
            st.session_state[
                "main_intent_error"
            ]
        )
    elif not command:
        st.caption(
            "Choose a Quick action or type a command."
        )
    elif resolution is None:
        st.info(
            assessment.message
        )
    elif not resolution.recognized:
        st.error(
            assessment.message
        )
    elif assessment.status == "warning":
        st.warning(
            assessment.message
        )
    else:
        st.success(
            "Intent recognized: "
            f"{resolution.intent_result.intent}"
        )

    _render_confirmation_panel(
        view,
        resolution,
    )


@contextmanager
def _xai_section(
    label: str,
    expanded: bool = False,
):
    """Render an XAI subsection without nesting expanders."""
    del expanded

    with st.container(
        border=True
    ):
        st.markdown(
            f"#### {label}"
        )
        yield


def _render_xai_drawer() -> None:
    """Single home for current and future XAI content."""
    with st.expander(
        "Explainability (XAI)",
        expanded=False,
    ):
        _render_main_xai()


def _render_answer_column(
    view: MainUIViewModel,
) -> None:
    st.markdown(
        "### 3. Tutor answer"
    )

    _render_tutor_generation_panel(
        view
    )
    _render_tutor_result()
    _render_xai_drawer()

    st.button(
        "Reset current turn",
        width="stretch",
        key="main_reset_turn_button",
        on_click=_reset_turn_state,
    )

def _render_header(
    view: MainUIViewModel,
) -> None:
    del view

    st.title("AttentiveSlides")

    st.caption(
        "Select a slide region, state your learning goal, "
        "and receive a grounded tutor response."
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

    (
        left_spacer,
        previous_column,
        next_column,
        right_spacer,
    ) = st.columns(
        [0.26, 0.24, 0.24, 0.26],
        gap="small",
    )

    del left_spacer
    del right_spacer

    previous_column.button(
        "← Previous",
        disabled=previous_id is None,
        width="stretch",
        key="main_previous_slide_button",
        on_click=_navigate_to_slide,
        args=(previous_id,),
    )

    next_column.button(
        "Next →",
        disabled=next_id is None,
        width="stretch",
        key="main_next_slide_button",
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

    reset_main_live_turn_state(
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


def _invalidate_confirmation() -> None:
    """Invalidate confirmation and any generated answer."""
    st.session_state[
        "main_confirmed"
    ] = False
    st.session_state[
        "main_confirmation_source"
    ] = None
    st.session_state[
        "main_confirmed_aoi_id"
    ] = None
    st.session_state[
        "main_corrected_from_aoi_id"
    ] = None
    st.session_state[
        "main_confirmed_interaction"
    ] = None
    st.session_state[
        "main_confirmation_error"
    ] = None
    st.session_state[
        "main_tutor_result"
    ] = None
    st.session_state[
        "main_tutor_context"
    ] = None

    st.session_state[
        "main_last_generated_interaction_id"
    ] = None
    st.session_state[
        "main_tutor_error"
    ] = None
    st.session_state[
        "main_xai_result"
    ] = None



def _clear_manual_region() -> None:
    """Clear the current region and mapped AOIs."""
    st.session_state[
        "main_region_x_range"
    ] = (0.10, 0.90)

    st.session_state[
        "main_region_y_range"
    ] = (0.10, 0.90)

    st.session_state[
        "main_manual_region_active"
    ] = False

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
        "main_confirmation_target_choice"
    ] = None

    _invalidate_confirmation()

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
) -> SlideViewportGeometry | None:
    drawing_enabled = (
        st.session_state["main_target_scope"]
        == "Manual region"
    )
    if not drawing_enabled:
        _set_whole_slide_target(view)

    st.slider(
        "Slide size",
        min_value=50,
        max_value=100,
        step=5,
        key="main_slide_width_percent",
        help=(
            "Resize the displayed slide while preserving normalized AOI "
            "geometry."
        ),
    )
    payload = render_slide_viewport(
        deck_id=view.deck_id,
        slide=view.active_slide,
        layout_revision=int(
            st.session_state.get(
                "main_canvas_revision",
                0,
            )
        ),
        drawing_enabled=drawing_enabled,
        show_aoi_overlay=bool(
            st.session_state["main_show_aoi_overlay"]
        ),
        display_width_percent=int(
            st.session_state["main_slide_width_percent"]
        ),
        key=(
            "main_slide_viewport_"
            f"{view.deck_id}_{view.active_slide_id}"
        ),
    )
    if payload is None:
        _render_static_slide(view.active_slide)
        if drawing_enabled:
            st.caption(
                "Viewport selection is disabled only in AppTest workers."
            )
        return None

    try:
        geometry = parse_component_geometry(
            payload,
            received_at=time.monotonic(),
        )
        raw_bbox = payload.get("manual_bbox")
        if (
            drawing_enabled
            and isinstance(raw_bbox, (list, tuple))
            and len(raw_bbox) == 4
        ):
            bbox = tuple(float(value) for value in raw_bbox)
            selection = ManualSelectionResult(
                bbox=bbox,
                canvas_width=max(
                    1,
                    round(
                        geometry.slide_rect.x2
                        - geometry.slide_rect.x1
                    ),
                ),
                canvas_height=max(
                    1,
                    round(
                        geometry.slide_rect.y2
                        - geometry.slide_rect.y1
                    ),
                ),
                matches=map_bbox_to_aois(
                    bbox,
                    view.active_slide.aois,
                ),
            )
            st.session_state["main_manual_region_active"] = True
            _store_manual_selection(selection)
            st.session_state["main_selection_error"] = None
    except Exception as exc:
        st.session_state["main_selection_error"] = (
            f"{type(exc).__name__}: {exc}"
        )
        st.error(
            "Unable to read slide viewport geometry: "
            + st.session_state["main_selection_error"]
        )
        return None

    return geometry




def _render_static_slide(
    slide: MainUISlide,
) -> None:
    if (
        slide.image_available
        and slide.image_path
    ):
        base_image = _load_slide_image(
            slide.image_path
        )

        display_image = base_image

        try:
            if st.session_state[
                "main_show_aoi_overlay"
            ]:
                display_image = _draw_aoi_overlay(
                    base_image,
                    slide,
                )

            bbox = st.session_state.get(
                "main_manual_bbox"
            )

            if (
                bbox
                and st.session_state.get(
                    "main_target_scope"
                )
                == "Manual region"
            ):
                if display_image is base_image:
                    display_image = (
                        base_image.copy()
                    )

                width, height = (
                    display_image.size
                )

                rectangle = (
                    round(float(bbox[0]) * width),
                    round(float(bbox[1]) * height),
                    round(float(bbox[2]) * width),
                    round(float(bbox[3]) * height),
                )

                ImageDraw.Draw(
                    display_image
                ).rectangle(
                    rectangle,
                    outline=(220, 70, 40),
                    width=max(
                        3,
                        round(width / 360),
                    ),
                )

            st.image(
                display_image,
                width="stretch",
            )

        finally:
            if display_image is not base_image:
                display_image.close()

            base_image.close()

    else:
        with st.container(
            border=True
        ):
            st.markdown(
                f"### Slide {slide.slide_id}"
            )

            st.write(
                slide.slide_text
                or "Slide image unavailable."
            )



def _store_manual_selection(
    selection: ManualSelectionResult,
) -> None:
    """Store a rectangle and invalidate only when it changes."""
    next_bbox = list(
        selection.bbox
    )

    next_aoi_ids = [
        match.aoi_id
        for match in selection.matches
    ]

    changed = (
        st.session_state.get(
            "main_manual_bbox"
        )
        != next_bbox
        or st.session_state.get(
            "main_selected_aoi_ids"
        )
        != next_aoi_ids
    )

    if changed:
        _invalidate_confirmation()
        st.session_state[
            "main_confirmation_target_choice"
        ] = None

    st.session_state[
        "main_manual_bbox"
    ] = next_bbox
    st.session_state[
        "main_selected_aoi_ids"
    ] = next_aoi_ids
    st.session_state[
        "main_selection_matches"
    ] = [
        match.to_dict()
        for match in selection.matches
    ]
    st.session_state[
        "main_selection_text"
    ] = selection.selected_text


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



def _on_typed_command_change() -> None:
    """Mark manually edited text as typed-text input."""
    command = st.session_state[
        "main_typed_command"
    ].strip()

    st.session_state[
        "main_intent_source"
    ] = (
        "typed_text"
        if command
        else None
    )
    st.session_state[
        "main_explicit_intent"
    ] = None
    st.session_state[
        "main_intent_result"
    ] = None
    st.session_state[
        "main_intent_error"
    ] = None

    _invalidate_confirmation()


def _apply_quick_intent(
    intent_name: str,
    command: str,
) -> None:
    """Apply an explicit learner-selected intent."""
    if (
        st.session_state.get(
            "main_typed_command"
        )
        == command
        and st.session_state.get(
            "main_intent_source"
        )
        == "ui_action"
        and st.session_state.get(
            "main_explicit_intent"
        )
        == intent_name
    ):
        return

    st.session_state[
        "main_typed_command"
    ] = command

    st.session_state[
        "main_intent_source"
    ] = "ui_action"

    st.session_state[
        "main_explicit_intent"
    ] = intent_name

    st.session_state[
        "main_intent_result"
    ] = None

    st.session_state[
        "main_intent_error"
    ] = None

    _invalidate_confirmation()


def _resolve_current_intent(
) -> ManualIntentResolution | None:
    """Resolve the current command and update session state."""
    command = st.session_state[
        "main_typed_command"
    ].strip()

    if not command:
        st.session_state[
            "main_intent_source"
        ] = None
        st.session_state[
            "main_explicit_intent"
        ] = None
        st.session_state[
            "main_intent_result"
        ] = None
        st.session_state[
            "main_intent_error"
        ] = None
        return None

    source = st.session_state.get(
        "main_intent_source"
    )

    explicit_intent = (
        st.session_state.get(
            "main_explicit_intent"
        )
    )

    try:
        if (
            source == "ui_action"
            and explicit_intent
        ):
            intent_input = (
                make_quick_action_intent_input(
                    explicit_intent
                )
            )
        else:
            intent_input = (
                make_typed_intent_input(
                    command
                )
            )

        resolution = resolve_manual_intent(
            intent_input
        )

    except Exception as exc:
        st.session_state[
            "main_intent_error"
        ] = (
            f"{type(exc).__name__}: {exc}"
        )

        st.session_state[
            "main_intent_result"
        ] = None

        return None

    st.session_state[
        "main_intent_source"
    ] = intent_input.source

    st.session_state[
        "main_intent_result"
    ] = resolution.to_dict()

    st.session_state[
        "main_intent_error"
    ] = None

    return resolution


def _render_quick_intent_actions() -> None:
    """Render explicit intent buttons in two rows."""
    st.markdown(
        "#### Quick actions"
    )

    first_row = st.columns(3)

    for column, action in zip(
        first_row,
        QUICK_INTENT_ACTIONS[:3],
    ):
        column.button(
            action.label,
            key=(
                "quick_intent_"
                f"{action.intent}"
            ),
            help=action.description,
            width="stretch",
            on_click=_apply_quick_intent,
            args=(
                action.intent,
                action.command,
            ),
        )

    second_row = st.columns(3)

    for column, action in zip(
        second_row,
        QUICK_INTENT_ACTIONS[3:],
    ):
        column.button(
            action.label,
            key=(
                "quick_intent_"
                f"{action.intent}"
            ),
            help=action.description,
            width="stretch",
            on_click=_apply_quick_intent,
            args=(
                action.intent,
                action.command,
            ),
        )


def _switch_to_whole_slide() -> None:
    """Switch target scope through a widget callback."""
    _clear_manual_region()

    st.session_state[
        "main_target_scope"
    ] = "Whole slide"

    st.session_state[
        "main_confirmation_target_choice"
    ] = "whole_slide"


def _render_confirmation_panel(
    view: MainUIViewModel,
    resolution: ManualIntentResolution | None,
) -> None:
    """Render a compact user-facing confirmation step."""
    try:
        preview = build_manual_confirmation_preview(
            deck_id=view.deck_id,
            slide_id=view.active_slide_id,
            target_scope=(
                st.session_state[
                    "main_target_scope"
                ]
            ),
            bbox=(
                st.session_state[
                    "main_manual_bbox"
                ]
            ),
            selected_aoi_ids=(
                st.session_state[
                    "main_selected_aoi_ids"
                ]
            ),
            selection_matches=(
                st.session_state[
                    "main_selection_matches"
                ]
            ),
            slide_text=(
                view.active_slide.slide_text
            ),
            aois=view.active_slide.aois,
            intent_resolution=resolution,
        )

    except Exception as exc:
        st.error(
            "Unable to prepare confirmation: "
            f"{type(exc).__name__}: {exc}"
        )
        return

    option_ids = list(
        preview.target_option_ids
    )

    if not option_ids:
        st.info(
            "Select a target and command before confirming."
        )
        return

    current_choice = st.session_state.get(
        "main_confirmation_target_choice"
    )

    if current_choice not in option_ids:
        st.session_state[
            "main_confirmation_target_choice"
        ] = (
            preview.proposed_aoi_id
            if preview.proposed_aoi_id
            in option_ids
            else option_ids[0]
        )

    option_by_id = {
        option.aoi_id: option
        for option in preview.target_options
    }

    selected_target_id = st.selectbox(
        "Confirm target",
        options=option_ids,
        key="main_confirmation_target_choice",
        format_func=lambda aoi_id: (
            option_by_id[aoi_id].label
        ),
        on_change=_invalidate_confirmation,
    )

    assessment = assess_manual_confirmation(
        preview,
        selected_target_id=selected_target_id,
    )

    if assessment.status == "blocked":
        st.error(
            assessment.message
        )
    elif assessment.status == "warning":
        st.warning(
            assessment.message
        )
    else:
        st.caption(
            assessment.message
        )

    confirm_column, whole_column, cancel_column = (
        st.columns(3)
    )

    confirm_clicked = confirm_column.button(
        "Confirm target and intent",
        type="primary",
        disabled=(
            not assessment.ready
            or (
                st.session_state[
                    "main_confirmed"
                ]
                and st.session_state.get(
                    "main_confirmed_aoi_id"
                )
                == selected_target_id
            )
        ),
        width="stretch",
        key="main_confirm_button",
    )

    whole_column.button(
        "Use whole slide",
        disabled=(
            selected_target_id
            == "whole_slide"
        ),
        width="stretch",
        key="main_use_whole_slide_button",
        on_click=_switch_to_whole_slide,
    )

    cancel_column.button(
        "Cancel confirmation",
        disabled=not st.session_state[
            "main_confirmed"
        ],
        width="stretch",
        key="main_cancel_confirmation_button",
        on_click=_invalidate_confirmation,
    )

    if confirm_clicked:
        try:
            confirmed = confirm_manual_interaction(
                preview,
                selected_target_id=(
                    selected_target_id
                ),
                interaction_id=(
                    "manual_"
                    + uuid.uuid4().hex
                ),
            )

        except Exception as exc:
            _invalidate_confirmation()
            st.session_state[
                "main_confirmation_error"
            ] = (
                f"{type(exc).__name__}: {exc}"
            )

        else:
            interaction = confirmed.interaction

            st.session_state[
                "main_confirmed"
            ] = True
            st.session_state[
                "main_confirmation_source"
            ] = interaction.confirmation.source
            st.session_state[
                "main_confirmed_aoi_id"
            ] = (
                interaction.confirmation
                .confirmed_aoi_id
            )
            st.session_state[
                "main_corrected_from_aoi_id"
            ] = (
                interaction.confirmation
                .corrected_from_aoi_id
            )
            st.session_state[
                "main_confirmed_interaction"
            ] = confirmed.to_dict()
            st.session_state[
                "main_confirmation_error"
            ] = None

    if st.session_state[
        "main_confirmation_error"
    ]:
        st.error(
            st.session_state[
                "main_confirmation_error"
            ]
        )

    if st.session_state[
        "main_confirmed"
    ]:
        st.success(
            "Target and intent confirmed."
        )



def _clear_conversation() -> None:
    """Clear stored turns without changing current settings."""
    active_deck_id = st.session_state.get(
        "main_conversation_deck_id"
    )

    reset_main_conversation_state(
        st.session_state,
        deck_id=active_deck_id,
    )


def _start_follow_up() -> None:
    """Start a new confirmed turn while preserving the target."""
    st.session_state[
        "main_typed_command"
    ] = ""

    st.session_state[
        "main_intent_source"
    ] = None

    st.session_state[
        "main_explicit_intent"
    ] = None

    st.session_state[
        "main_intent_result"
    ] = None

    st.session_state[
        "main_intent_error"
    ] = None

    _invalidate_confirmation()


def _record_completed_turn(
    *,
    tutor_payload: dict[str, Any],
    llm_xai_payload: dict[str, Any],
) -> None:
    """Upsert one successful, sanitized tutoring turn."""
    confirmed = st.session_state.get(
        "main_confirmed_interaction"
    )

    if confirmed is None:
        raise ValueError(
            "A confirmed interaction is required "
            "before recording a conversation turn."
        )

    integrated = build_integrated_pipeline_xai(
        target_scope=(
            st.session_state[
                "main_target_scope"
            ]
        ),
        manual_bbox=(
            st.session_state[
                "main_manual_bbox"
            ]
        ),
        selection_matches=(
            st.session_state[
                "main_selection_matches"
            ]
        ),
        intent_result=(
            st.session_state[
                "main_intent_result"
            ]
        ),
        confirmed_interaction=confirmed,
        tutor_result=tutor_payload,
        llm_xai=llm_xai_payload,
        cloud_text_allowed=(
            st.session_state[
                "main_cloud_text_allowed"
            ]
        ),
    )

    turn = build_conversation_turn(
        confirmed_interaction=confirmed,
        tutor_result=tutor_payload,
        llm_xai=llm_xai_payload,
        integrated_xai=integrated,
    )

    st.session_state[
        "main_conversation_turns"
    ] = upsert_conversation_turn(
        st.session_state[
            "main_conversation_turns"
        ],
        turn,
    )


def _log_completed_interaction_once() -> None:
    """Write one sanitized JSONL record after successful generation."""
    confirmed = st.session_state.get("main_confirmed_interaction") or {}
    interaction = confirmed.get("interaction", {})
    interaction_id = str(interaction.get("interaction_id", ""))
    if (
        not interaction_id
        or st.session_state.get("main_last_generated_interaction_id")
        != interaction_id
        or not st.session_state.get("main_tutor_result")
    ):
        return
    logged = st.session_state["main_logged_interaction_ids"]
    write_main_interaction_once(
        logged,
        interaction_id=interaction_id,
        payload={
            "interaction_id": interaction_id,
            "deck_id": interaction.get("deck_id"),
            "slide_id": interaction.get("slide_id"),
            "interaction": interaction,
            "tutor": st.session_state["main_tutor_result"],
            "xai": st.session_state["main_xai_result"],
        },
        write=_main_interaction_logger().log_interaction,
    )


def _render_conversation_history(
    view: MainUIViewModel,
) -> None:
    """Render sanitized session-level tutoring history."""
    turns = st.session_state[
        "main_conversation_turns"
    ]

    metric_columns = st.columns(3)

    metric_columns[0].metric(
        "Stored turns",
        len(turns),
    )

    metric_columns[1].metric(
        "History enabled",
        (
            "Yes"
            if st.session_state[
                "main_history_enabled"
            ]
            else "No"
        ),
    )

    metric_columns[2].metric(
        "Tutor history limit",
        st.session_state[
            "main_history_max_items"
        ],
    )

    st.caption(
        "Conversation data remains in the current "
        "Streamlit session. Only bounded, sanitized "
        "history is supplied to the tutor."
    )

    control_columns = st.columns(2)

    control_columns[0].button(
        "Clear conversation",
        width="stretch",
        disabled=not turns,
        key="main_clear_conversation_button",
        on_click=_clear_conversation,
    )

    export_payload = export_conversation(
        deck_id=view.deck_id,
        turns=turns,
    )

    control_columns[1].download_button(
        "Export conversation JSON",
        data=json.dumps(
            export_payload,
            ensure_ascii=False,
            indent=2,
        ),
        file_name=(
            f"{view.deck_id}_conversation.json"
        ),
        mime="application/json",
        disabled=not turns,
        key=(
            f"conversation_export_"
            f"{view.deck_id}"
        ),
    )

    if st.session_state[
        "main_conversation_error"
    ]:
        st.error(
            st.session_state[
                "main_conversation_error"
            ]
        )

    if not turns:
        st.info(
            "No completed tutoring turns "
            "have been recorded."
        )
        return

    summary_rows = [
        {
            "turn": index,
            "slide": turn["slide_id"],
            "command": turn[
                "user_command"
            ],
            "intent": turn["intent"],
            "target": turn.get(
                "confirmed_aoi_id"
            ),
            "reliability": turn[
                "reliability_level"
            ],
            "fallback": turn[
                "fallback_used"
            ],
        }
        for index, turn in enumerate(
            turns,
            start=1,
        )
    ]

    _render_records_table(
        summary_rows,
        hide_index=True,
        width="stretch",
    )

    indexed_turns = list(
        enumerate(
            turns,
            start=1,
        )
    )

    for index, turn in reversed(
        indexed_turns
    ):
        with st.expander(
            (
                f"Turn {index}: "
                f"{turn['user_command']}"
            ),
            expanded=(
                index == len(turns)
            ),
        ):
            st.markdown(
                "**Learner**"
            )
            st.write(
                turn["user_command"]
            )

            st.markdown(
                "**Tutor**"
            )
            st.write(
                turn["answer"]
            )

            if turn.get(
                "active_recall_question"
            ):
                st.info(
                    turn[
                        "active_recall_question"
                    ]
                )

            st.json(
                {
                    "slide_id": (
                        turn["slide_id"]
                    ),
                    "intent": (
                        turn["intent"]
                    ),
                    "intent_source": (
                        turn[
                            "intent_source"
                        ]
                    ),
                    "target_source": (
                        turn[
                            "target_source"
                        ]
                    ),
                    "confirmed_aoi_id": (
                        turn[
                            "confirmed_aoi_id"
                        ]
                    ),
                    "confirmation_source": (
                        turn[
                            "confirmation_source"
                        ]
                    ),
                    "source_ids": (
                        turn["source_ids"]
                    ),
                    "reliability_level": (
                        turn[
                            "reliability_level"
                        ]
                    ),
                    "validation_is_valid": (
                        turn[
                            "validation_is_valid"
                        ]
                    ),
                    "fallback_used": (
                        turn[
                            "fallback_used"
                        ]
                    ),
                }
            )


def _render_tutor_generation_panel(
    view: MainUIViewModel,
) -> None:
    """Render explicit grounded generation with history gates."""
    st.markdown(
        "#### Grounded tutor"
    )

    api_configured = bool(
        os.environ.get(
            "DASHSCOPE_API_KEY"
        )
    )

    assessment = assess_tutor_generation(
        st.session_state[
            "main_confirmed_interaction"
        ],
        cloud_text_allowed=(
            st.session_state[
                "main_cloud_text_allowed"
            ]
        ),
        api_configured=api_configured,
    )

    if assessment.ready:
        st.success(
            assessment.message
        )
    elif (
        assessment.code
        == "cloud_permission_required"
    ):
        st.warning(
            assessment.message
        )
    elif (
        assessment.code
        == "api_not_configured"
    ):
        st.error(
            assessment.message
        )
    else:
        st.info(
            assessment.message
        )

    confirmed_wrapper = (
        st.session_state.get(
            "main_confirmed_interaction"
        )
        or {}
    )

    confirmed_interaction = (
        confirmed_wrapper.get(
            "interaction",
            {},
        )
    )

    current_interaction_id = str(
        confirmed_interaction.get(
            "interaction_id",
            "",
        )
    )

    already_generated = bool(
        current_interaction_id
        and st.session_state.get(
            "main_last_generated_interaction_id"
        )
        == current_interaction_id
        and st.session_state.get(
            "main_tutor_result"
        )
    )

    generate_clicked = st.button(
        "Generate grounded answer",
        type="primary",
        disabled=(
            not assessment.ready
            or already_generated
        ),
        width="stretch",
        key="main_generate_answer_button",
        help=(
            "Change the target or command "
            "to create a new turn."
            if already_generated
            else None
        ),
    )

    if generate_clicked:
        st.session_state[
            "main_tutor_error"
        ] = None

        st.session_state[
            "main_conversation_error"
        ] = None

        try:
            with st.spinner(
                "Generating and validating "
                "the grounded answer..."
            ):
                client = (
                    OpenAICompatibleLLMClient
                    .from_env()
                )

                agent = GroundedTutorAgent(
                    llm_client=client,
                    max_retries=1,
                )

                generation = (
                    generate_main_tutor_response(
                        st.session_state[
                            "main_confirmed_interaction"
                        ],
                        slide=view.active_slide,
                        agent=agent,
                        cloud_text_allowed=(
                            st.session_state[
                                "main_cloud_text_allowed"
                            ]
                        ),
                        api_configured=True,
                        conversation_turns=(
                            st.session_state[
                                "main_conversation_turns"
                            ]
                            if st.session_state[
                                "main_history_enabled"
                            ]
                            else []
                        ),
                        history_max_items=int(
                            st.session_state[
                                "main_history_max_items"
                            ]
                        ),
                    )
                )

                payload = (
                    generation
                    .to_session_payload()
                )

        except Exception as exc:
            st.session_state[
                "main_tutor_error"
            ] = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            st.session_state[
                "main_tutor_context"
            ] = None

            st.session_state[
                "main_tutor_result"
            ] = None

            st.session_state[
                "main_xai_result"
            ] = None

        else:
            st.session_state[
                "main_tutor_context"
            ] = payload["context"]

            st.session_state[
                "main_tutor_result"
            ] = payload["tutor"]

            st.session_state[
                "main_xai_result"
            ] = payload["xai"]

            st.session_state[
                "main_tutor_error"
            ] = None

            st.session_state[
                "main_last_generated_interaction_id"
            ] = current_interaction_id

            try:
                _record_completed_turn(
                    tutor_payload=(
                        payload["tutor"]
                    ),
                    llm_xai_payload=(
                        payload["xai"]
                    ),
                )

            except Exception as exc:
                st.session_state[
                    "main_conversation_error"
                ] = (
                    "Tutor answer succeeded, but "
                    "conversation recording failed: "
                    f"{type(exc).__name__}: {exc}"
                )

    try:
        _log_completed_interaction_once()
    except Exception as exc:
        st.session_state["main_conversation_error"] = (
            "Tutor answer succeeded, but JSONL recording failed: "
            f"{type(exc).__name__}: {exc}"
        )

    if st.session_state[
        "main_tutor_error"
    ]:
        st.error(
            st.session_state[
                "main_tutor_error"
            ]
        )

    if st.session_state[
        "main_conversation_error"
    ]:
        st.warning(
            st.session_state[
                "main_conversation_error"
            ]
        )

    if st.session_state[
        "main_tutor_result"
    ]:
        st.success(
            "A validated tutor response "
            "is shown below."
        )


def _render_tutor_result() -> None:
    """Render the learner-facing answer without developer diagnostics."""
    result = st.session_state[
        "main_tutor_result"
    ]

    if result is None:
        st.info(
            "Confirm the request and generate an answer."
        )
        return

    st.markdown(
        result["answer"]
    )

    if result.get(
        "active_recall_question"
    ):
        st.info(
            "Active recall: "
            + result[
                "active_recall_question"
            ]
        )

    if result.get(
        "uncertainty_note"
    ):
        st.warning(
            "Uncertainty: "
            + result[
                "uncertainty_note"
            ]
        )

    status_column, validation_column = (
        st.columns(2)
    )

    status_column.metric(
        "Status",
        result["status"],
    )

    validation_column.metric(
        "Validation",
        (
            "PASS"
            if result[
                "validation_is_valid"
            ]
            else "FAIL"
        ),
    )

    st.button(
        "Start follow-up",
        width="stretch",
        key="main_start_follow_up_button",
        on_click=_start_follow_up,
    )



def _render_main_xai() -> None:
    """Render integrated, observable pipeline explanations."""
    integrated = build_integrated_pipeline_xai(
        target_scope=(
            st.session_state.get(
                "main_target_scope",
                "Whole slide",
            )
        ),
        manual_bbox=(
            st.session_state.get(
                "main_manual_bbox"
            )
        ),
        selection_matches=(
            st.session_state.get(
                "main_selection_matches",
                [],
            )
        ),
        intent_result=(
            st.session_state.get(
                "main_intent_result"
            )
        ),
        confirmed_interaction=(
            st.session_state.get(
                "main_confirmed_interaction"
            )
        ),
        tutor_result=(
            st.session_state.get(
                "main_tutor_result"
            )
        ),
        llm_xai=(
            st.session_state.get(
                "main_xai_result"
            )
        ),
        cloud_text_allowed=bool(
            st.session_state.get(
                "main_cloud_text_allowed",
                False,
            )
        ),
    )

    st.markdown(
        "### Integrated pipeline explanation"
    )

    questions = integrated[
        "questions"
    ]

    target = questions["target"]
    intent = questions["intent"]
    answer = questions["answer"]
    reliability = questions[
        "reliability"
    ]

    metrics = st.columns(4)

    metrics[0].metric(
        "Pipeline",
        integrated[
            "pipeline_status"
        ],
    )

    metrics[1].metric(
        "Target",
        (
            target[
                "confirmed_aoi_id"
            ]
            or target[
                "selected_aoi_id"
            ]
            or "pending"
        ),
    )

    metrics[2].metric(
        "Intent",
        (
            intent[
                "resolved_intent"
            ]
            or "pending"
        ),
    )

    metrics[3].metric(
        "Reliability",
        reliability["level"],
    )

    _render_records_table(
        integrated["pipeline"],
        hide_index=True,
        width="stretch",
    )

    with st.container(
        border=True
    ):
        st.markdown(
            "#### Why this target?"
        )

        st.write(
            target["explanation"]
        )

        target_columns = st.columns(3)

        target_columns[0].metric(
            "Source",
            (
                target["target_source"]
                or "pending"
            ),
        )

        target_columns[1].metric(
            "Confirmed AOI",
            (
                target[
                    "confirmed_aoi_id"
                ]
                or "pending"
            ),
        )

        target_columns[2].metric(
            "Corrected",
            (
                "Yes"
                if target[
                    "corrected_by_learner"
                ]
                else "No"
            ),
        )

        if target["bbox"] is not None:
            st.code(
                json.dumps(
                    {
                        "normalized_bbox": (
                            target["bbox"]
                        )
                    },
                    indent=2,
                ),
                language="json",
            )

        if target["candidates"]:
            st.markdown(
                "##### AOI overlap candidates"
            )

            _render_records_table(
                target["candidates"],
                hide_index=True,
                width="stretch",
            )

    with st.container(
        border=True
    ):
        st.markdown(
            "#### Why this intent?"
        )

        st.write(
            intent["explanation"]
        )

        intent_columns = st.columns(3)

        intent_columns[0].metric(
            "Source",
            intent["source"]
            or "pending",
        )

        intent_columns[1].metric(
            "Resolved intent",
            (
                intent[
                    "resolved_intent"
                ]
                or "pending"
            ),
        )

        intent_columns[2].metric(
            "Confidence",
            (
                f"{intent['confidence']:.2f}"
                if intent[
                    "confidence"
                ]
                is not None
                else "N/A"
            ),
        )

        if intent["command"]:
            st.code(
                intent["command"],
                language="text",
            )

        if intent["provenance"]:
            with _xai_section(
                "Intent provenance",
                expanded=False,
            ):
                for item in intent[
                    "provenance"
                ]:
                    st.write(
                        f"- {item}"
                    )

    with st.container(
        border=True
    ):
        st.markdown(
            "#### Why this answer?"
        )

        st.write(
            answer["explanation"]
        )

        answer_columns = st.columns(3)

        answer_columns[0].metric(
            "Response mode",
            (
                answer[
                    "response_mode"
                ]
                or "pending"
            ),
        )

        answer_columns[1].metric(
            "Claims",
            answer[
                "claim_count"
            ],
        )

        answer_columns[2].metric(
            "Sources",
            answer[
                "source_count"
            ],
        )

        if answer[
            "uncertainty_note"
        ]:
            st.warning(
                answer[
                    "uncertainty_note"
                ]
            )

        if answer["claims"]:
            st.markdown(
                "##### Claim–source mapping"
            )

            _render_records_table(
                answer["claims"],
                hide_index=True,
                width="stretch",
            )

        if answer["sources"]:
            st.markdown(
                "##### Available sources"
            )

            _render_records_table(
                answer["sources"],
                hide_index=True,
                width="stretch",
            )

    with st.container(
        border=True
    ):
        st.markdown(
            "#### How reliable is the pipeline?"
        )

        if (
            reliability["level"]
            == "supported"
        ):
            st.success(
                reliability["summary"]
            )

        elif (
            reliability["level"]
            == "caution"
        ):
            st.warning(
                reliability["summary"]
            )

        elif (
            reliability["level"]
            == "unsupported"
        ):
            st.error(
                reliability["summary"]
            )

        else:
            st.info(
                reliability["summary"]
            )

        _render_records_table(
            reliability["checks"],
            hide_index=True,
            width="stretch",
        )

        if reliability["warnings"]:
            st.markdown(
                "##### Reliability warnings"
            )

            for warning in reliability[
                "warnings"
            ]:
                st.write(
                    f"- {warning}"
                )

        with _xai_section(
            "Reliability telemetry",
            expanded=False,
        ):
            st.json(
                {
                    "citation_coverage": (
                        reliability[
                            "citation_coverage"
                        ]
                    ),
                    "confirmed_aoi_cited": (
                        reliability[
                            "confirmed_aoi_cited"
                        ]
                    ),
                    "validation_is_valid": (
                        reliability[
                            "validation_is_valid"
                        ]
                    ),
                    "fallback_used": (
                        reliability[
                            "fallback_used"
                        ]
                    ),
                    "retry_count": (
                        reliability[
                            "retry_count"
                        ]
                    ),
                    "provider": (
                        reliability[
                            "provider"
                        ]
                    ),
                    "model": (
                        reliability[
                            "model"
                        ]
                    ),
                    "latency_ms": (
                        reliability[
                            "latency_ms"
                        ]
                    ),
                }
            )

    st.markdown(
        "#### Corrective control"
    )

    for action in integrated[
        "corrective_actions"
    ]:
        st.write(
            f"- {action}"
        )

    with _xai_section(
        "Privacy and public-XAI guarantees",
        expanded=False,
    ):
        st.json(
            integrated["privacy"]
        )


def _live_target_options(
    proposal: LiveInteractionProposal,
) -> list[str]:
    options: list[str] = []
    for aoi_id in (
        proposal.predicted_aoi_id,
        *(
            candidate.aoi_id
            for candidate in proposal.alternatives
        ),
    ):
        if aoi_id and aoi_id not in options:
            options.append(aoi_id)
    options.append("whole_slide")
    if st.session_state.get("main_manual_bbox"):
        options.append("manual_region")
    return options


def _enable_live_manual_region() -> None:
    st.session_state["main_target_scope"] = "Manual region"
    st.session_state["main_manual_region_active"] = True
    _invalidate_confirmation()
    st.session_state["main_live_full_rerun_requested"] = True


def _on_live_overlay_change() -> None:
    _on_overlay_change()
    st.session_state["main_live_full_rerun_requested"] = True


def _store_live_confirmation(
    view: MainUIViewModel,
    proposal: LiveInteractionProposal,
    *,
    selected_option: str,
    automatic: bool,
) -> None:
    manual_bbox = None
    selected_aoi_id = selected_option
    if selected_option == "manual_region":
        raw_bbox = st.session_state.get("main_manual_bbox")
        if not raw_bbox:
            raise ValueError("Draw a manual rectangle before confirming it.")
        manual_bbox = tuple(float(value) for value in raw_bbox)
        selected_ids = st.session_state.get(
            "main_selected_aoi_ids",
            [],
        )
        selected_aoi_id = (
            str(selected_ids[0])
            if selected_ids
            else "whole_slide"
        )

    interaction = build_live_interaction_input(
        proposal,
        command=st.session_state["main_typed_command"],
        selected_aoi_id=selected_aoi_id,
        automatic=automatic,
        manual_bbox=manual_bbox,
    )
    selected_aoi = next(
        (
            aoi
            for aoi in view.active_slide.aois
            if aoi.aoi_id == selected_aoi_id
        ),
        None,
    )
    confirmed_context = (
        selected_aoi.text.strip()
        if selected_aoi is not None
        and selected_aoi.text.strip()
        else view.active_slide.slide_text.strip()
    )
    wrapper = {
        "interaction": interaction.to_dict(),
        "selected_target": {"aoi_id": selected_aoi_id},
        "proposed_aoi_id": proposal.predicted_aoi_id,
        "corrected": (
            selected_aoi_id != proposal.predicted_aoi_id
        ),
        "confirmed_context": confirmed_context,
    }
    st.session_state["main_confirmed"] = True
    st.session_state["main_confirmation_source"] = (
        interaction.confirmation.source
    )
    st.session_state["main_confirmed_aoi_id"] = selected_aoi_id
    st.session_state["main_corrected_from_aoi_id"] = (
        interaction.confirmation.corrected_from_aoi_id
    )
    st.session_state["main_confirmed_interaction"] = wrapper
    st.session_state["main_confirmation_error"] = None


def _consume_live_proposal(
    resources: MainLiveResources,
    view: MainUIViewModel,
    geometry: SlideViewportGeometry | None,
) -> None:
    resources.runtime.poll()
    confirmed = (
        st.session_state.get("main_confirmed_interaction")
        or {}
    ).get("interaction", {})
    pending_id = str(confirmed.get("interaction_id", ""))
    if (
        pending_id
        and pending_id
        != st.session_state.get("main_last_generated_interaction_id")
    ):
        return

    raw = resources.inbox.pop()
    if raw is None:
        return
    if raw.deck_id != view.deck_id or raw.slide_id != view.active_slide_id:
        return

    if geometry is None:
        proposal = replace(
            raw,
            predicted_aoi_id=None,
            target_confidence=0.0,
            alternatives=(),
        )
    else:
        proposal = resolve_grid_target(
            raw,
            geometry,
            view.active_slide.aois,
        )

    reset_main_turn_state(st.session_state)
    st.session_state["main_live_proposal"] = proposal
    st.session_state["main_live_original_transcript"] = (
        proposal.original_speech_transcript
    )
    st.session_state["main_live_predicted_aoi_id"] = (
        proposal.predicted_aoi_id
    )
    st.session_state["main_live_layout_revision"] = (
        proposal.layout_revision
        if proposal.layout_revision >= 0
        else None
    )
    st.session_state["main_typed_command"] = proposal.transcript
    options = _live_target_options(proposal)
    st.session_state["main_live_target_choice"] = (
        proposal.predicted_aoi_id
        if proposal.predicted_aoi_id in options
        else options[0]
    )

    if should_auto_confirm(
        proposal,
        geometry,
        policy=st.session_state["main_confirmation_policy"],
        threshold=float(
            st.session_state["main_auto_confirm_threshold"]
        ),
        interaction_pending=False,
    ):
        _store_live_confirmation(
            view,
            proposal,
            selected_option=str(proposal.predicted_aoi_id),
            automatic=True,
        )


def _render_live_target_column(
    view: MainUIViewModel,
    proposal: LiveInteractionProposal | None,
) -> str | None:
    st.markdown("### 1. Live target")
    st.checkbox(
        "Show AOI overlay",
        key="main_show_aoi_overlay",
        on_change=_on_live_overlay_change,
    )
    if proposal is None:
        st.caption("Waiting for a completed speech turn and gaze evidence.")
        return None

    options = _live_target_options(proposal)
    current = st.session_state.get("main_live_target_choice")
    if current not in options:
        st.session_state["main_live_target_choice"] = options[0]
    selected = st.selectbox(
        "Confirm or correct target",
        options=options,
        key="main_live_target_choice",
        format_func=lambda value: (
            "Manual rectangle"
            if value == "manual_region"
            else "Whole slide"
            if value == "whole_slide"
            else value
        ),
        on_change=_invalidate_confirmation,
    )
    if proposal.predicted_aoi_id:
        st.caption(
            f"Predicted: {proposal.predicted_aoi_id} · "
            f"confidence {proposal.target_confidence:.2f} · "
            f"grid {proposal.gaze_grid}"
        )
    else:
        st.warning(
            "No valid gaze target. Choose whole slide or draw a region."
        )
    st.button(
        "Draw manual region",
        key="main_live_draw_region_button",
        width="stretch",
        on_click=_enable_live_manual_region,
    )
    if st.session_state.get("main_manual_bbox"):
        st.caption("A manual rectangle is available as a fallback target.")
    return selected


def _render_live_interaction(
    view: MainUIViewModel,
) -> None:
    proposal = st.session_state.get("main_live_proposal")
    if not isinstance(proposal, LiveInteractionProposal):
        proposal = None
    target_column, intent_column, answer_column = st.columns(
        [1.05, 1.20, 1.35],
        gap="medium",
    )
    with target_column:
        selected = _render_live_target_column(view, proposal)
    with intent_column:
        st.markdown("### 2. Live command")
        st.text_area(
            "Speech transcript",
            key="main_typed_command",
            height=110,
            placeholder="Speak a request after enabling camera and microphone.",
            on_change=_on_typed_command_change,
        )
        if proposal is not None:
            edited = (
                st.session_state["main_typed_command"].strip()
                != proposal.original_speech_transcript.strip()
            )
            st.caption(
                "Edited transcript: hybrid provenance."
                if edited
                else "Original speech transcript: sensor-assisted provenance."
            )
        confirm_clicked = st.button(
            "Confirm target and command",
            type="primary",
            disabled=(
                proposal is None
                or selected is None
                or not st.session_state["main_typed_command"].strip()
                or st.session_state["main_confirmed"]
            ),
            width="stretch",
            key="main_live_confirm_button",
        )
        if confirm_clicked and proposal is not None and selected is not None:
            try:
                _store_live_confirmation(
                    view,
                    proposal,
                    selected_option=selected,
                    automatic=False,
                )
            except Exception as exc:
                _invalidate_confirmation()
                st.session_state["main_confirmation_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
        if st.session_state["main_confirmation_error"]:
            st.error(st.session_state["main_confirmation_error"])
        elif st.session_state["main_confirmed"]:
            st.success(
                "Live request confirmed via "
                f"{st.session_state['main_confirmation_source']}."
            )
    with answer_column:
        _render_answer_column(view)


@st.fragment(run_every=0.5)
def _render_live_periodic(
    resources: MainLiveResources,
    view: MainUIViewModel,
    geometry: SlideViewportGeometry | None,
) -> None:
    try:
        _consume_live_proposal(resources, view, geometry)
    except Exception as exc:
        st.error(
            "Live proposal processing failed: "
            f"{type(exc).__name__}: {exc}"
        )
    session = resources.ingress.session_snapshot()
    runtime_state = resources.runtime.controller.state.value
    st.caption(
        f"Live transport: {'armed' if session.armed else 'off'} · "
        f"Runtime: {runtime_state} · "
        f"Media: {'ready' if session.video_fresh and session.audio_fresh else 'waiting'}"
    )
    _render_live_interaction(view)
    if st.session_state.pop("main_live_full_rerun_requested", False):
        st.rerun(scope="app")



def _render_manual_interaction(
    view: MainUIViewModel,
    *,
    live_resources: MainLiveResources | None = None,
    geometry: SlideViewportGeometry | None = None,
) -> None:
    """Render the core learner workflow in one horizontal row."""
    if (
        st.session_state.get("main_interaction_mode") == "Live"
        and live_resources is not None
    ):
        if st.session_state.get("main_live_master_enabled"):
            _render_live_periodic(
                live_resources,
                view,
                geometry,
            )
        else:
            _render_live_interaction(view)
        return

    (
        target_column,
        intent_column,
        answer_column,
    ) = st.columns(
        [1.05, 1.20, 1.35],
        gap="medium",
    )

    with target_column:
        _render_target_column(
            view
        )

    with intent_column:
        _render_intent_column(
            view
        )

    with answer_column:
        _render_answer_column(
            view
        )



def _render_lower_workspace(
    view: MainUIViewModel,
) -> None:
    """Keep secondary session information collapsed by default."""
    with st.expander(
        "Conversation history",
        expanded=False,
    ):
        _render_conversation_history(
            view
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
