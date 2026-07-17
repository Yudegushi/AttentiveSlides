"""Interactive privacy-preserving Main UI for AttentiveSlides."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace

import html
import hashlib
import json
from io import BytesIO
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

REPOSITORY_ROOT = Path(
    __file__
).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPOSITORY_ROOT),
    )

import streamlit as st
import streamlit.components.v1 as components
from PIL import (
    Image,
    ImageDraw,
)

from modules.attention import render_review_slide, review_png_bytes
from modules.audio.faster_whisper_transcriber import (
    FasterWhisperTranscriber,
)
from modules.audio.streaming_vad import EnergyVadBackend
from modules.audio.transcriber import TranscriptionConfig
from modules.audio.voice_turn_detector import VoiceTurnDetector
from modules.logging.interaction_logger import InteractionLogger
from modules.fatigue import (
    FatigueTemporalTracker,
)
from modules.fatigue.mobilevit_estimator import (
    DEFAULT_MODEL_PATH,
    MobileViTFatigueEstimator,
)
from modules.learner_state import (
    EmotiEffEstimator,
    EmotionTemporalTracker,
    EngagementTemporalTracker,
    LearnerStateStore,
)
from modules.review import StudyReviewStore
from modules.slide.llm_aoi import sanitized_llm_error
from modules.media import BrowserMediaSource
from modules.media.browser_gaze_source import BrowserGazeSource
from modules.media.live_ingress_service import LiveIngressService
from modules.media.single_port_transport import FallbackMediaIngress
from modules.realtime.bailian_omni_realtime_client import (
    BailianOmniRealtimeClient,
)
from modules.realtime.realtime_contracts import (
    SpeechMode,
    TargetBinding,
    VoiceEngine,
    VoicePreferences,
)

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
    _linked_visual_context_text,
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
    build_main_review_defaults,
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
from modules.system.learner_state_worker import LearnerStateWorker
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
from modules.system.live_debug_overlay import resolve_live_debug_aoi_id
from modules.system.sensing_snapshot_store import SensingSnapshotStore
from modules.system.sensing_worker import SensingWorker
from modules.system.slide_geometry import parse_component_geometry
from modules.system.turn_context import TurnContextCollector
from modules.system.omni_voice_runtime import OmniVoiceRuntime
from modules.system.realtime_tutor_context import (
    RealtimeTutorContext,
    build_realtime_tutor_instructions,
)
from modules.system.single_turn_ptt_runtime import SingleTurnPTTRuntime
from modules.system.single_turn_tts import SingleTurnTTSController
from modules.system.target_switching import TargetSwitchController
from modules.system.voice_event_hub import VoiceEventHub
from modules.system.voice_orchestrator import (
    AUTO_GAZE_TARGET_ID,
    VoiceOrchestrator,
)
from modules.system.uploaded_deck_service import (
    UploadedDeckWorkspace,
)
from modules.ui.slide_viewport_component import render_slide_viewport
from modules.ui.live_debug_bridge_component import render_live_debug_bridge
from modules.ui.learner_state_status import (
    build_learner_state_view,
)
from modules.ui.voice_control_component import render_voice_control_component
from modules.ui.design_tokens import (
    normalize_palette_id,
    palette_semantic,
    render_palette_css,
)
from modules.ui.palette_control_component import render_palette_control
from modules.ui.voice_panel import VoicePanelView, build_voice_panel_view


BUILT_IN_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "mock_deck"
    / "mock_aoi_manifest.json"
)

FLOW_ENGINE = {
    "one_turn": "single_turn",
    "dialogue": "single_turn",
    "realtime": "omni",
}

RUNTIME_DATA_DIR = Path(
    os.environ.get(
        "ATTENTIVE_RUNTIME_DATA_DIR",
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "attentive_slides",
    )
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
    learner_state_store: LearnerStateStore
    learner_state_worker: LearnerStateWorker
    voice: VoiceOrchestrator
    voice_events: VoiceEventHub
    single_turn_tts: SingleTurnTTSController
    study_review: StudyReviewStore
    bound_deck_id: str | None = None
    bound_slide_id: int | None = None
    bound_aoi_signature: str | None = None
    bound_voice_target_signature: str | None = None
    bound_voice_preferences: VoicePreferences | None = None


@st.cache_resource
def build_main_live_resources(
    *,
    start_ingress: bool = True,
) -> MainLiveResources:
    """Build the thin Live proposal graph; the Main UI owns tutoring."""
    media_source = BrowserMediaSource()
    provider = ActiveDeckSlideProvider()
    snapshots = SensingSnapshotStore()
    observations = BrowserGazeSource()
    study_review = StudyReviewStore(
        RUNTIME_DATA_DIR / "study_reviews",
        legacy_gaze_path=RUNTIME_DATA_DIR / "gaze_reviews" / "latest.json",
    )
    learner_state_store = LearnerStateStore()
    emotion_tracker = EmotionTemporalTracker()
    engagement_tracker = EngagementTemporalTracker()
    fatigue_tracker = FatigueTemporalTracker()
    learner_state_worker = LearnerStateWorker(
        media_source.face_crop_queue,
        affect_estimator_factory=lambda: EmotiEffEstimator(
            os.environ.get(
                "ATTENTIVE_EMOTIEFF_MODEL_PATH",
                "/home/charles/.local/share/attentiveslides/models/learner_state/"
                "emotieff/enet_b0_8_best_vgaf_features.ts",
            ),
            os.environ.get(
                "ATTENTIVE_EMOTIEFF_ENGAGEMENT_PATH",
                "/home/charles/.local/share/attentiveslides/models/learner_state/"
                "emotieff/engagement_single_attention.pt",
            ),
            device=os.environ.get("ATTENTIVE_EMOTIEFF_DEVICE", "cuda"),
        ),
        fatigue_estimator_factory=lambda: MobileViTFatigueEstimator(
            os.environ.get(
                "ATTENTIVE_FATIGUE_MODEL_PATH",
                str(DEFAULT_MODEL_PATH),
            ),
            device=os.environ.get(
                "ATTENTIVE_FATIGUE_DEVICE",
                "cuda",
            ),
        ),
        emotion_tracker=emotion_tracker,
        engagement_tracker=engagement_tracker,
        fatigue_tracker=fatigue_tracker,
        store=learner_state_store,
        on_snapshot=study_review.accept_learner_state,
    )
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
            device=os.environ.get(
                "ATTENTIVE_WHISPER_DEVICE",
                "auto",
            ),
            compute_type=os.environ.get(
                "ATTENTIVE_WHISPER_COMPUTE_TYPE",
                "auto",
            ),
        )
    )
    audio_worker = AudioWorker(
        media_source=media_source,
        detector=VoiceTurnDetector(
            EnergyVadBackend(speech_threshold=250)
        ),
        transcribe=transcriber.transcribe,
    )
    collector = TurnContextCollector(
        slide_provider=provider,
        snapshot_store=snapshots,
        browser_gaze_source=observations,
        aggregation_key="gaze_grid",
    )
    inbox = LatestProposalInbox()
    runner = ProposalTurnRunner(
        context_collector=collector,
        inbox=inbox,
    )
    voice_events = VoiceEventHub()
    target_switching = TargetSwitchController()

    def begin_omni_gaze_window(
        target: TargetBinding,
        started_at: float,
    ):
        return collector.freeze_start(
            slide_id=target.slide_id,
            speech_started_at=started_at,
        )

    def resolve_omni_gaze_window(
        context,
        ended_at: float,
        current_target: TargetBinding,
    ) -> TargetBinding | None:
        frozen = collector.freeze_end(
            context,
            speech_ended_at=ended_at,
            current_slide_id=current_target.slide_id,
        )
        if frozen.slide_changed_during_turn:
            return None
        aggregated = collector.aggregate(frozen)
        candidate_id = aggregated.frame.gaze_prediction.predicted_aoi_id
        if not candidate_id:
            return None
        frame = provider.get_slide_frame(current_target.slide_id)
        return _target_binding_from_slide(
            deck_id=frame.deck_id,
            slide=frame,
            target_id=str(candidate_id),
        )

    def resolve_initial_omni_target(
        current_target: TargetBinding,
    ) -> TargetBinding | None:
        resolved_at = time.monotonic()
        context = begin_omni_gaze_window(current_target, resolved_at)
        return resolve_omni_gaze_window(
            context,
            resolved_at,
            current_target,
        )

    def build_omni_instructions(target: TargetBinding) -> str:
        frame = provider.get_slide_frame(target.slide_id)
        visual_derived = (
            "Visible transcription:" in target.text
            or "Visual description:" in target.text
        )
        return build_realtime_tutor_instructions(
            RealtimeTutorContext(
                deck_id=frame.deck_id,
                slide_number=frame.slide_id,
                slide_text=frame.slide_text,
                target=target,
                visual_observation=target.text if visual_derived else "",
                visual_observation_is_model_derived=visual_derived,
            )
        )

    voice_holder: dict[str, VoiceOrchestrator] = {}
    controller_holder: dict[str, SystemController] = {}

    async def fallback_voice(
        reason: str,
        transcript: str | None,
    ) -> None:
        await voice_holder["voice"].fallback_to_single_turn(
            reason,
            transcript,
        )

    def adopt_omni_target(target: TargetBinding) -> None:
        orchestrator = voice_holder.get("voice")
        if orchestrator is not None:
            orchestrator.adopt_confirmed_target(target)

    def reset_single_turn_audio(reason: str) -> None:
        controller = controller_holder.get("controller")
        if controller is not None:
            controller.reset_audio_turn(reason)

    omni_runtime = OmniVoiceRuntime(
        events=voice_events,
        target_switching=target_switching,
        client_factory=BailianOmniRealtimeClient,
        begin_gaze_window=begin_omni_gaze_window,
        resolve_gaze_window=resolve_omni_gaze_window,
        on_fallback=fallback_voice,
        on_target_confirmed=adopt_omni_target,
        build_instructions=build_omni_instructions,
    )
    single_turn_ptt = SingleTurnPTTRuntime(
        transcribe=transcriber.transcribe,
        context_collector=collector,
        proposal_runner=runner,
    )

    def publish_fallback_transcript(transcript: str) -> None:
        orchestrator = voice_holder.get("voice")
        target = orchestrator.current_target() if orchestrator is not None else None
        if target is not None:
            runner.publish_transcript(transcript, target=target)

    voice = VoiceOrchestrator(
        events=voice_events,
        omni=omni_runtime,
        single_turn_ptt=single_turn_ptt,
        target_switching=target_switching,
        publish_single_turn_transcript=publish_fallback_transcript,
        on_single_turn_boundary=reset_single_turn_audio,
        resolve_initial_target=resolve_initial_omni_target,
    )
    voice_holder["voice"] = voice
    single_turn_tts = SingleTurnTTSController(
        output_dir=RUNTIME_DATA_DIR / "tts",
    )
    controller = SystemController(
        media_source=media_source,
        sensing_worker=sensing_worker,
        audio_worker=audio_worker,
        context_collector=collector,
        turn_runner=runner,
        learner_state_worker=learner_state_worker,
    )
    controller_holder["controller"] = controller
    runtime = MainUILiveRuntime(
        controller=controller,
        inbox=inbox,
        snapshot_store=snapshots,
    )
    ingress = FallbackMediaIngress(
        media_source,
        observations=observations,
        study_review=study_review,
        start_armed=False,
        coordinated_activation=True,
        media_stale_after_seconds=10.0,
        inactive_after_seconds=12.0,
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
        voice_transport=voice,
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
        learner_state_store=learner_state_store,
        learner_state_worker=learner_state_worker,
        voice=voice,
        voice_events=voice_events,
        single_turn_tts=single_turn_tts,
        study_review=study_review,
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
    _inject_compact_ui_css()

    if st.session_state["main_workspace_mode"] == "study":
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

    _sync_active_aoi_signature(view)

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
    if st.session_state["main_workspace_mode"] == "review":
        _render_review_sidebar(live_resources)
        _render_header(view, resources=live_resources, review=True)
        _render_review_workspace(
            view,
            browser=browser,
            resources=live_resources,
        )
        return

    _render_live_controls(
        live_resources
    )

    _render_sidebar_status(
        browser,
        view,
    )

    _render_header(view, resources=live_resources)
    _render_slide_selector(browser)
    slide_column, interaction_column = st.columns(
        [1.0, 0.42],
        gap="medium",
        vertical_alignment="top",
    )
    with slide_column:
        _render_slide_workspace(
            view,
            browser=browser,
            workspace=workspace,
            live_resources=live_resources,
        )
    with interaction_column:
        with st.container(key="main_interaction_workspace"):
            _render_manual_interaction(
                view,
                live_resources=live_resources,
            )
    _render_lower_workspace(view, live_resources)



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
        "main_loaded_pdf_signature": None,
        "main_upload_error": None,
        "main_cloud_text_allowed": True,
        "main_active_aoi_signature": None,
        "main_llm_aoi_message": None,
        "main_llm_aoi_error": None,
        "main_show_aoi_overlay": True,
        "main_canvas_revision": 0,
        "main_slide_width_percent": 70,
        "main_selection_matches": [],
        "main_selection_text": "",
        "main_selection_error": None,
        **build_main_turn_defaults(),
        **build_main_conversation_defaults(),
        **build_main_live_defaults(),
        **build_main_review_defaults(),
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


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

    if st.session_state.get("main_workspace_mode") not in {"study", "review"}:
        st.session_state["main_workspace_mode"] = "study"
    st.session_state["main_review_show_heatmap"] = bool(
        st.session_state.get("main_review_show_heatmap", True)
    )

    boolean_defaults = {
        "main_cloud_text_allowed": True,
        "main_show_aoi_overlay": True,
        "main_manual_region_active": False,
        "main_live_master_enabled": False,
        "main_slide_rail_expanded": True,
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

    if st.session_state.get("main_interaction_flow") not in FLOW_ENGINE:
        st.session_state["main_interaction_flow"] = "one_turn"
    interaction_flow = str(st.session_state["main_interaction_flow"])
    st.session_state["main_voice_engine"] = FLOW_ENGINE[interaction_flow]
    st.session_state["main_history_enabled"] = interaction_flow == "dialogue"

    if st.session_state.get("main_confirmation_policy") not in {
        "Always confirm",
        "Confidence-based auto",
    }:
        st.session_state["main_confirmation_policy"] = "Confidence-based auto"

    if st.session_state.get("main_speech_mode") not in {
        "push_to_talk",
        "continuous",
    }:
        st.session_state["main_speech_mode"] = "push_to_talk"
    try:
        auto_confirm_threshold = float(
            st.session_state.get("main_auto_confirm_threshold", 0.80)
        )
    except (TypeError, ValueError):
        auto_confirm_threshold = 0.80
    st.session_state["main_auto_confirm_threshold"] = max(
        0.70,
        min(0.95, auto_confirm_threshold),
    )
    st.session_state["main_ui_palette"] = normalize_palette_id(
        st.session_state.get("main_ui_palette")
    )
    st.session_state["main_answer_audio_enabled"] = bool(
        st.session_state.get("main_answer_audio_enabled", True)
    )
    st.session_state["main_target_scope_explicit"] = bool(
        st.session_state.get("main_target_scope_explicit", False)
    )

    st.session_state[
        "main_widget_error"
    ] = None
    # Canonical target scope is stored independently from the user-facing label.
    default_target_scope = (
        "Gaze AOI"
        if st.session_state["main_voice_engine"] == "omni"
        and not st.session_state["main_target_scope_explicit"]
        else "Whole slide"
    )
    raw_target_scope = str(
        st.session_state.get(
            "main_target_scope",
            default_target_scope,
        )
    ).strip()
    if (
        st.session_state["main_voice_engine"] == "omni"
        and not st.session_state["main_target_scope_explicit"]
        and raw_target_scope.casefold()
        in {"whole slide", "use whole slide", "whole_slide"}
    ):
        raw_target_scope = "Gaze AOI"

    target_scope_aliases = {
        "whole slide": "Whole slide",
        "use whole slide": "Whole slide",
        "whole_slide": "Whole slide",
        "gaze aoi": "Gaze AOI",
        "gaze target": "Gaze AOI",
        "auto gaze": "Gaze AOI",
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
    if st.session_state.get("main_voice_engine") == "omni":
        # Empty string is a one-rerun retry sentinel so a deliberate Omni
        # selection is not mistaken for an unacknowledged fallback.
        st.session_state["main_voice_status_message"] = ""


def _on_interaction_flow_change() -> None:
    flow = str(st.session_state.get("main_interaction_flow", "one_turn"))
    if flow not in FLOW_ENGINE:
        flow = "one_turn"
        st.session_state["main_interaction_flow"] = flow
    st.session_state["main_voice_engine"] = FLOW_ENGINE[flow]
    st.session_state["main_history_enabled"] = flow == "dialogue"
    _on_voice_engine_change()


def _media_runtime_requested() -> bool:
    return bool(st.session_state.get("main_live_master_enabled", False))


def _on_voice_engine_change() -> None:
    _on_live_preference_change()
    if st.session_state.get("main_voice_engine") == "omni":
        if not st.session_state.get("main_target_scope_explicit", False):
            st.session_state["main_target_scope"] = "Gaze AOI"
    elif st.session_state.get("main_target_scope") == "Gaze AOI":
        st.session_state["main_target_scope"] = "Whole slide"
        st.session_state["main_target_scope_explicit"] = False


def _adopt_voice_fallback_state(
    resources: MainLiveResources,
) -> bool:
    snapshot = resources.voice.snapshot()
    status_message = snapshot.get("status_message")
    fell_back = bool(
        st.session_state.get("main_voice_engine") == "omni"
        and st.session_state.get("main_voice_status_message") != ""
        and snapshot.get("engine") == "single_turn"
        and status_message
    )
    if fell_back:
        st.session_state["main_voice_engine"] = "single_turn"
        st.session_state["main_interaction_flow"] = "one_turn"
        st.session_state["main_history_enabled"] = False
        st.session_state["main_voice_status_message"] = str(status_message)
        if st.session_state.get("main_target_scope") == "Gaze AOI":
            st.session_state["main_target_scope"] = "Whole slide"
            st.session_state["main_target_scope_explicit"] = False
    return fell_back


def _sync_main_live_voice_resources(
    resources: MainLiveResources,
    view: MainUIViewModel,
) -> None:
    _adopt_voice_fallback_state(resources)
    preferences = VoicePreferences(
        engine=VoiceEngine(str(st.session_state["main_voice_engine"])),
        speech_mode=SpeechMode(str(st.session_state["main_speech_mode"])),
        answer_audio_enabled=bool(
            st.session_state["main_answer_audio_enabled"]
        ),
    )
    if resources.bound_voice_preferences != preferences:
        resources.voice.update_preferences(preferences)
        resources.bound_voice_preferences = preferences
    if preferences.engine is VoiceEngine.OMNI:
        st.session_state["main_voice_status_message"] = None

    target = _voice_target_binding(
        view,
        allow_auto_gaze=preferences.engine is VoiceEngine.OMNI,
    )
    signature = target.signature if target is not None else None
    if resources.bound_voice_target_signature == signature:
        return
    if target is None:
        resources.voice.clear_target("confirmed target unavailable")
    else:
        resources.voice.update_target(target)
    resources.bound_voice_target_signature = signature


def _bind_main_live_resources(
    resources: MainLiveResources,
    *,
    browser: Any,
    view: MainUIViewModel,
) -> None:
    """Bind the canonical browser before media can be armed."""
    signature = _active_aoi_signature(view)
    deck_changed = resources.bound_deck_id != view.deck_id
    slide_changed = resources.bound_slide_id != view.active_slide_id
    aoi_changed = (
        not deck_changed
        and not slide_changed
        and getattr(resources, "bound_aoi_signature", None) != signature
    )

    # UploadedDeckWorkspace is intentionally recreated on each app rerun.
    # Keep the cached live graph pointed at the current workspace/browser.
    resources.provider.set_browser(browser)
    resources.learner_state_worker.set_context(view.deck_id, view.active_slide_id)
    resources.study_review.set_context(view.deck_id, view.active_slide_id)
    resources.study_review.register_slide(
        view.deck_id,
        view.active_slide_id,
        view.active_slide.aois,
    )
    if aoi_changed:
        resources.bound_voice_target_signature = None
    _sync_main_live_voice_resources(resources, view)

    if deck_changed or aoi_changed:
        resources.inbox.clear()
        resources.snapshots.clear()
        resources.ingress.observations.clear()
        resources.runtime.set_slide(view.active_slide_id)
        resources.bound_deck_id = view.deck_id
        resources.bound_slide_id = view.active_slide_id
        resources.bound_aoi_signature = signature
        return

    if slide_changed:
        resources.ingress.observations.clear()
        resources.runtime.set_slide(view.active_slide_id)
        resources.bound_slide_id = view.active_slide_id
        resources.bound_aoi_signature = signature


def _finish_study_review(resources: MainLiveResources, deck_id: str) -> None:
    try:
        review = resources.study_review.finish(deck_id=deck_id)
    except (OSError, RuntimeError) as exc:
        st.session_state["main_review_error"] = f"Unable to save review: {exc}"
        return
    st.session_state["main_workspace_mode"] = "review"
    st.session_state["main_review_error"] = None
    st.session_state["main_study_started_monotonic"] = None
    st.session_state["main_review_session"] = review.session_id
    if review.gaze_review.slides:
        st.session_state["main_active_slide_id"] = review.gaze_review.slides[0].slide_id


def _open_latest_review(resources: MainLiveResources) -> None:
    review = resources.study_review.latest()
    if review is None:
        warnings = resources.study_review.load_warnings()
        st.session_state["main_review_error"] = warnings[-1] if warnings else (
            "No completed Study Review is available."
        )
        st.session_state["main_workspace_mode"] = "review"
        return
    st.session_state["main_workspace_mode"] = "review"
    st.session_state["main_review_error"] = None
    st.session_state["main_review_session"] = review.session_id
    if review.gaze_review.slides:
        st.session_state["main_active_slide_id"] = review.gaze_review.slides[0].slide_id


def _back_to_study_workspace() -> None:
    st.session_state["main_workspace_mode"] = "study"


def _start_study_review(resources: MainLiveResources, deck_id: str) -> None:
    try:
        resources.study_review.start(deck_id)
    except (OSError, RuntimeError, ValueError) as exc:
        st.session_state["main_review_error"] = (
            f"Unable to start study: {exc}"
        )
        return
    st.session_state["main_workspace_mode"] = "study"
    st.session_state["main_review_show_heatmap"] = True
    st.session_state["main_review_delete_confirm"] = False
    st.session_state["main_review_error"] = None
    st.session_state["main_study_started_monotonic"] = time.monotonic()


def _delete_selected_study_review(resources: MainLiveResources) -> None:
    session_id = st.session_state.get("main_review_session")
    if not session_id:
        st.session_state["main_review_error"] = "No Study Review session is selected."
        return
    try:
        resources.study_review.delete(str(session_id))
    except (OSError, KeyError) as exc:
        st.session_state["main_review_error"] = (
            f"Unable to delete selected review: {exc}"
        )
        return
    sessions = resources.study_review.list_sessions()
    st.session_state["main_review_session"] = (
        sessions[0].session_id if sessions else None
    )
    if not sessions:
        st.session_state["main_workspace_mode"] = "study"
    st.session_state["main_review_delete_confirm"] = False
    st.session_state["main_review_error"] = None


def _on_review_option_change(source: str | None = None) -> None:
    st.session_state["main_review_error"] = None
    if source == "session":
        st.session_state["main_review_delete_confirm"] = False


def _render_live_controls(
    resources: MainLiveResources,
) -> None:
    """Render the stable Study settings rail and reconcile media."""
    st.sidebar.markdown("### Lesson")
    st.sidebar.caption(resources.bound_deck_id or "Preparing lesson")

    st.sidebar.markdown("### Conversation flow")
    st.sidebar.radio(
        "Conversation flow",
        options=["one_turn", "dialogue", "realtime"],
        format_func=lambda value: {
            "one_turn": "One-turn",
            "dialogue": "Dialogue",
            "realtime": "Realtime",
        }[value],
        key="main_interaction_flow",
        on_change=_on_interaction_flow_change,
        label_visibility="collapsed",
    )
    st.sidebar.caption(
        "One grounded turn, bounded dialogue history, or persistent realtime."
    )

    st.sidebar.markdown("### Speaking control")
    st.sidebar.radio(
        "Speaking control",
        options=["push_to_talk", "continuous"],
        format_func=lambda value: (
            "Hold to speak" if value == "push_to_talk" else "Hands-free"
        ),
        key="main_speech_mode",
        on_change=_on_live_preference_change,
        label_visibility="collapsed",
    )

    st.sidebar.markdown("### Attention & answers")
    st.sidebar.checkbox(
        "Enable camera and microphone",
        key="main_live_master_enabled",
        on_change=_on_live_preference_change,
        help=(
            "Media remains local to the runtime; only confirmed text may be "
            "sent to the cloud tutor. Typed input remains available when off."
        ),
    )
    st.sidebar.checkbox(
        "Show attention regions",
        key="main_show_aoi_overlay",
        on_change=_on_overlay_change,
    )
    st.sidebar.checkbox(
        "Answer audio",
        key="main_answer_audio_enabled",
        on_change=_on_live_preference_change,
    )

    lifecycle = resources.study_review.lifecycle()
    st.sidebar.markdown("### Palette")
    with st.sidebar:
        selected_palette = str(st.session_state["main_ui_palette"])
        palette_value = render_palette_control(
            selected=selected_palette,
            palette_tokens=palette_semantic(selected_palette),
            locked=lifecycle.status in {"active", "finish_pending"},
            key="main_palette_control",
        )
    if palette_value is not None and palette_value != selected_palette:
        st.session_state["main_ui_palette"] = normalize_palette_id(palette_value)
        st.rerun()

    enabled = _media_runtime_requested()
    resources.service.set_master_enabled(enabled)
    resources.service.reconcile_once()

    runtime_state = resources.runtime.controller.state.value
    session = resources.ingress.session_snapshot()
    st.sidebar.markdown("### Participant & calibration")
    st.sidebar.caption(
        f"Media {'ready' if session.video_fresh and session.audio_fresh else 'waiting'} · "
        f"runtime {runtime_state}"
    )

    with st.sidebar.expander("Advanced voice settings", expanded=False):
        st.caption(
            "Engine: "
            + ("Omni realtime" if st.session_state["main_voice_engine"] == "omni" else "Grounded single-turn")
        )
        st.radio(
            "Confirmation policy",
            options=[
                "Confidence-based auto",
                "Always confirm",
            ],
            key="main_confirmation_policy",
            on_change=_on_live_preference_change,
        )
        if (
            st.session_state["main_confirmation_policy"]
            == "Confidence-based auto"
        ):
            st.slider(
                "Auto-confirm confidence",
                min_value=0.70,
                max_value=0.95,
                step=0.01,
                key="main_auto_confirm_threshold",
                on_change=_on_live_preference_change,
            )

    deck_id = resources.bound_deck_id
    lifecycle_deck_id = lifecycle.deck_id
    active_deck_mismatch = bool(
        deck_id is not None
        and lifecycle_deck_id is not None
        and lifecycle_deck_id != deck_id
    )
    if active_deck_mismatch:
        st.sidebar.error(
            "The active Study belongs to another deck. "
            "Finish that Study before starting one for this deck."
        )
    if (
        resources.study_review.latest() is not None
        or resources.study_review.load_warnings()
    ):
        st.sidebar.button(
            (
                "Open latest review"
                if resources.study_review.latest() is not None
                else "Resolve saved review"
            ),
            key="main_open_latest_review",
            width="stretch",
            on_click=_open_latest_review,
            args=(resources,),
        )
    if st.session_state.get("main_review_error"):
        st.sidebar.error(st.session_state["main_review_error"])
    if st.session_state.get("main_voice_status_message"):
        st.sidebar.warning(st.session_state["main_voice_status_message"])

    if enabled:
        with st.sidebar.expander(
            "Camera and microphone preview",
            expanded=False,
        ):
            st.iframe("/capture", height=340)


def _format_review_duration(seconds: float) -> str:
    total = max(0, round(float(seconds)))
    minutes, remainder = divmod(total, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _format_review_session_option(review: Any | None) -> str:
    if review is None:
        return "Unavailable Study Review"
    completed = time.strftime(
        "%Y-%m-%d %H:%M",
        time.localtime(review.ended_at_epoch),
    )
    duration = _format_review_duration(
        review.ended_at_epoch - review.started_at_epoch
    )
    return f"{completed} · {review.deck_id} · {duration}"


def _selected_study_review(resources: MainLiveResources):
    session_id = st.session_state.get("main_review_session")
    selected = resources.study_review.get(str(session_id)) if session_id else None
    if selected is not None:
        return selected
    latest = resources.study_review.latest()
    if latest is not None:
        st.session_state["main_review_session"] = latest.session_id
    return latest


def _review_session_caption(review: Any) -> str:
    summary = review.learner_state_summary
    engagement = (
        "--"
        if summary.mean_engaged_probability is None
        else f"{summary.mean_engaged_probability:.0%}"
    )
    fatigue = (
        "--"
        if summary.mean_fatigue_probability is None
        else f"{summary.mean_fatigue_probability:.0%}"
    )
    emotion = (
        "--"
        if summary.top_emotion is None
        else f"{summary.top_emotion} {summary.top_emotion_probability:.0%}"
    )
    return (
        f"Study {_format_review_duration(summary.study_seconds)} · "
        f"{summary.interaction_count} interactions · Engaged {engagement} · "
        f"Top emotion {emotion} · Fatigue {fatigue}"
    )


def _render_review_sidebar(resources: MainLiveResources) -> None:
    st.sidebar.markdown("### Study review")
    st.sidebar.button(
        "Back to workspace",
        key="main_review_back",
        width="stretch",
        on_click=_back_to_study_workspace,
    )
    sessions = resources.study_review.list_sessions()
    session_ids = tuple(review.session_id for review in sessions)
    selected_id = st.session_state.get("main_review_session")
    if selected_id not in session_ids:
        st.session_state["main_review_session"] = (
            session_ids[0] if session_ids else None
        )
    if session_ids:
        st.sidebar.selectbox(
            "Study session",
            options=session_ids,
            format_func=lambda session_id: _format_review_session_option(
                resources.study_review.get(session_id)
            ),
            key="main_review_session",
            on_change=_on_review_option_change,
            args=("session",),
        )

    review = _selected_study_review(resources)
    if review is not None:
        st.sidebar.download_button(
            "Download session JSON",
            data=review.to_json().encode("utf-8"),
            file_name=f"study_review_{review.session_id}.json",
            mime="application/json",
            key="main_review_download_json",
            width="stretch",
        )

    load_warnings = resources.study_review.load_warnings()
    inline_error = st.session_state.get("main_review_error")
    if inline_error:
        st.sidebar.error(inline_error)
    if load_warnings:
        st.sidebar.error(f"Saved review warning: {load_warnings[-1]}")
        st.sidebar.caption(
            "Valid sessions remain available; delete only an affected session if needed."
        )

    with st.sidebar.expander("Delete selected session", expanded=False):
        st.checkbox(
            "I understand this deletes only the selected session",
            key="main_review_delete_confirm",
            on_change=_on_review_option_change,
            args=("confirm",),
        )
        st.button(
            "Delete selected session",
            key="main_review_delete",
            disabled=not bool(
                st.session_state.get("main_review_delete_confirm", False)
            ),
            width="stretch",
            on_click=_delete_selected_study_review,
            args=(resources,),
        )


def _render_review_text_fallback(slide: MainUISlide) -> None:
    with st.container(border=True):
        st.markdown(f"### Slide {slide.slide_id}")
        st.write(slide.slide_text or "Slide image unavailable.")


def _render_review_workspace(
    view: MainUIViewModel,
    *,
    browser: Any,
    resources: MainLiveResources,
) -> None:
    review = _selected_study_review(resources)
    if review is None:
        st.info(
            "No completed gaze review is available. "
            "Start a new study to collect gaze data."
        )
        return
    st.caption(_review_session_caption(review))
    if review.deck_id != view.deck_id:
        st.warning(
            "The saved review belongs to a deck that is not currently available. "
            "You can still download its JSON or delete it from the sidebar."
        )
        return

    available_slide_ids = set(browser.slide_ids)
    review_slides = tuple(
        slide for slide in review.gaze_review.slides
        if slide.slide_id in available_slide_ids
    )
    if not review_slides:
        st.info("No slide gaze data was captured in this study.")
        return

    slide_by_id = {slide.slide_id: slide for slide in review_slides}
    if view.active_slide_id not in slide_by_id:
        st.session_state["main_active_slide_id"] = review_slides[0].slide_id
        st.rerun()
    slide_review = slide_by_id[view.active_slide_id]
    review_slide_ids = tuple(slide_by_id)

    _render_slide_selector(browser, slide_ids=review_slide_ids)

    with st.container(key="main_slide_scale"):
        st.slider(
            "Slide size",
            min_value=50,
            max_value=100,
            step=5,
            key="main_slide_width_percent",
            label_visibility="collapsed",
        )

    image_path = (
        view.active_slide.image_path
        if view.active_slide.image_available
        else None
    )
    show_heatmap = bool(st.session_state["main_review_show_heatmap"])

    def show_image(image: Image.Image) -> None:
        width_percent = int(st.session_state["main_slide_width_percent"])
        if width_percent >= 100:
            st.image(image, width="stretch")
            return
        slide_column, remainder = st.columns(
            [width_percent, 100 - width_percent],
            gap=None,
        )
        del remainder
        with slide_column:
            st.image(image, width="stretch")

    with st.container(key="main_slide_stage"):
        _render_navigation(
            browser,
            view,
            slide_ids=review_slide_ids,
        )
        if image_path is None:
            _render_review_text_fallback(view.active_slide)
        else:
            try:
                rendered = render_review_slide(
                    image_path,
                    slide_review,
                    show_heatmap=show_heatmap,
                )
                try:
                    show_image(rendered)
                finally:
                    rendered.close()
            except (OSError, ValueError):
                st.warning("Heatmap unavailable for this slide.")
                try:
                    original = _load_slide_image(image_path)
                except (OSError, ValueError):
                    _render_review_text_fallback(view.active_slide)
                else:
                    try:
                        show_image(original)
                    finally:
                        original.close()

    st.markdown(
        """
        <div class="attentive-review-legend">
            <span>Lower attention</span>
            <span class="attentive-review-gradient" aria-hidden="true"></span>
            <span>Higher attention</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Valid gaze: {slide_review.valid_gaze_seconds:.1f} s · "
        f"Data coverage: {slide_review.coverage:.0%}"
    )
    learner_slides = {
        slide.slide_id: slide
        for slide in review.learner_state_summary.slides
    }
    learner_summary = learner_slides.get(slide_review.slide_id)
    with st.expander("Learner state", expanded=False):
        if learner_summary is None or learner_summary.observed_seconds <= 0.0:
            st.caption(
                "No learner-state estimate was available for this slide"
            )
        else:
            engagement = (
                "--"
                if learner_summary.mean_engaged_probability is None
                else f"{learner_summary.mean_engaged_probability:.0%}"
            )
            fatigue = (
                "--"
                if learner_summary.mean_fatigue_probability is None
                else f"{learner_summary.mean_fatigue_probability:.0%}"
            )
            emotion = (
                "--"
                if learner_summary.top_emotion is None
                else (
                    f"{learner_summary.top_emotion} "
                    f"{learner_summary.top_emotion_probability:.0%}"
                )
            )
            st.caption(
                f"Study time {_format_review_duration(learner_summary.study_seconds)} · "
                f"Interactions {learner_summary.interaction_count} · "
                f"Engaged {engagement}"
            )
            st.caption(
                f"Top emotion {emotion} · Fatigue {fatigue} · "
                "Alerts: distraction "
                f"{learner_summary.distraction_alert_count}, fatigue "
                f"{learner_summary.fatigue_alert_count}"
            )
        st.caption("Model estimates; not a diagnosis.")
    if slide_review.valid_gaze_seconds <= 0.0:
        st.info("No valid gaze was captured on this slide.")
    st.checkbox(
        "Show heatmap",
        key="main_review_show_heatmap",
        on_change=_on_review_option_change,
    )

    rows = [
        {
            "Region": item.label,
            "Time": f"{item.dwell_seconds:.1f} s",
        }
        for item in slide_review.aoi_dwell
    ]
    if slide_review.other_slide_seconds > 0.05:
        rows.append(
            {
                "Region": "Other slide area",
                "Time": f"{slide_review.other_slide_seconds:.1f} s",
            }
        )
    with st.expander("Region times", expanded=False):
        if rows:
            _render_records_table(rows)
        else:
            st.caption("No region timing data is available for this slide.")

    if image_path is not None:
        try:
            png_payload = review_png_bytes(
                image_path,
                slide_review,
                show_heatmap=show_heatmap,
            )
        except (OSError, ValueError):
            st.caption("PNG export is unavailable for this slide.")
        else:
            st.download_button(
                "Download heatmap PNG",
                data=png_payload,
                file_name=f"slide_{slide_review.slide_id:03d}_gaze_heatmap.png",
                mime="image/png",
                key="main_review_download_png",
            )


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
    uploaded_bytes = uploaded_file.getvalue() if uploaded_file is not None else None
    selected_signature = (
        _uploaded_pdf_signature(uploaded_file.name, uploaded_bytes)
        if uploaded_file is not None and uploaded_bytes is not None
        else None
    )
    loaded = bool(
        selected_signature is not None
        and selected_signature == st.session_state.get("main_loaded_pdf_signature")
        and st.session_state.get("main_uploaded_deck_id")
    )
    if loaded:
        st.sidebar.button(
            "Loaded PDF",
            disabled=True,
            width="stretch",
            key="main_loaded_pdf_button",
        )
        load_clicked = False
    else:
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
                        filename=uploaded_file.name,
                        content=uploaded_bytes,
                    )
                )

        except Exception as exc:
            st.session_state[
                "main_upload_error"
            ] = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )
        else:
            st.session_state[
                "main_uploaded_deck_id"
            ] = summary.deck_id
            st.session_state[
                "main_loaded_pdf_signature"
            ] = selected_signature
            st.session_state[
                "main_upload_error"
            ] = None
            st.session_state[
                "main_deck_signature"
            ] = None
            _reset_turn_state()
            st.rerun()

    if st.session_state[
        "main_upload_error"
    ]:
        st.sidebar.error(
            st.session_state[
                "main_upload_error"
            ]
        )


def _uploaded_pdf_signature(filename: str, content: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(str(filename).encode("utf-8"))
    digest.update(b"\0")
    digest.update(content)
    return digest.hexdigest()


def _active_aoi_signature(view: MainUIViewModel) -> str:
    payload = {
        "deck_id": view.deck_id,
        "slide_id": view.active_slide_id,
        "aoi_profile": view.active_slide.aoi_profile,
        "aois": sorted(
            (
                {
                    "aoi_id": aoi.aoi_id,
                    "bbox": list(aoi.bbox),
                    "type": aoi.type,
                    "text": aoi.text,
                    "name": aoi.name,
                }
                for aoi in view.active_slide.aois
            ),
            key=lambda item: item["aoi_id"],
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _target_binding_from_slide(
    *,
    deck_id: str,
    slide: Any,
    target_id: str,
) -> TargetBinding | None:
    """Adapt a canonical slide/AOI to the shared realtime target contract."""
    normalized_id = str(target_id).strip()
    if normalized_id in {"whole-slide", "whole_slide"}:
        return TargetBinding(
            deck_id=deck_id,
            slide_id=int(slide.slide_id),
            target_id="whole-slide",
            label="Whole slide",
            text=str(slide.slide_text).strip(),
        )

    aoi = next(
        (
            candidate
            for candidate in slide.aois
            if candidate.aoi_id == normalized_id
        ),
        None,
    )
    if aoi is None:
        return None
    native_text = str(aoi.text).strip()
    linked_visual_text = _linked_visual_context_text(
        slide,
        normalized_id,
    ).strip()
    return TargetBinding(
        deck_id=deck_id,
        slide_id=int(slide.slide_id),
        target_id=normalized_id,
        label=str(aoi.name or normalized_id),
        text=(
            native_text
            or linked_visual_text
            or str(slide.slide_text).strip()
        ),
        bbox=tuple(float(value) for value in aoi.bbox),
    )


def _voice_target_binding(
    view: MainUIViewModel,
    *,
    allow_auto_gaze: bool = False,
) -> TargetBinding | None:
    """Resolve the learner-confirmed UI target without reading raw gaze."""
    target_scope = st.session_state.get("main_target_scope")
    if allow_auto_gaze and target_scope == "Gaze AOI":
        return TargetBinding(
            deck_id=view.deck_id,
            slide_id=view.active_slide_id,
            target_id=AUTO_GAZE_TARGET_ID,
            label="Waiting for gaze AOI",
            text="",
        )
    if target_scope != "Manual region":
        return _target_binding_from_slide(
            deck_id=view.deck_id,
            slide=view.active_slide,
            target_id="whole-slide",
        )

    raw_bbox = st.session_state.get("main_manual_bbox")
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        bbox = tuple(float(value) for value in raw_bbox)
        bbox_token = json.dumps(
            bbox,
            separators=(",", ":"),
        ).encode("utf-8")
        target_id = "manual-" + hashlib.sha256(bbox_token).hexdigest()[:16]
        selected_text = str(
            st.session_state.get("main_selection_text", "")
        ).strip()
        selected_ids = st.session_state.get("main_selected_aoi_ids", [])
        linked_visual_text = ""
        if isinstance(selected_ids, list) and len(selected_ids) == 1:
            linked_visual_text = _linked_visual_context_text(
                view.active_slide,
                str(selected_ids[0]),
            ).strip()
        return TargetBinding(
            deck_id=view.deck_id,
            slide_id=view.active_slide_id,
            target_id=target_id,
            label="Manual region",
            text=(
                selected_text
                or linked_visual_text
                or view.active_slide.slide_text.strip()
            ),
            bbox=bbox,
        )
    except (TypeError, ValueError):
        return None


def _sync_active_aoi_signature(view: MainUIViewModel) -> None:
    signature = _active_aoi_signature(view)
    if st.session_state.get("main_active_aoi_signature") != signature:
        _reset_turn_state()
        st.session_state["main_active_aoi_signature"] = signature


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
        return workspace.open_browser(deck_id)
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
    live_enabled = _media_runtime_requested()
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
    st.sidebar.markdown("### Conversation context")

    st.session_state[
        "main_history_max_items"
    ] = 4

    st.sidebar.caption(
        "Dialogue uses the latest 4 sanitized turns. "
        "One-turn does not send prior turns; Realtime history is provider-owned."
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
            st.caption("FLOW")
            st.markdown(
                f"**{str(st.session_state['main_interaction_flow']).replace('_', ' ').title()}**"
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


@st.cache_data(show_spinner=False)
def _workspace_css() -> str:
    return (REPOSITORY_ROOT / "modules" / "ui" / "workspace.css").read_text(
        encoding="utf-8"
    )


def _inject_compact_ui_css() -> None:
    """Inject the selected semantic palette and shared light workspace CSS."""
    st.html(
        "<style>"
        + render_palette_css(st.session_state["main_ui_palette"])
        + _workspace_css()
        + "</style>"
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


def _target_scope_label(
    value: str,
) -> str:
    if value == "Whole slide":
        return "Use whole slide"

    if value == "Gaze AOI":
        return "Use gaze AOI"

    return "Select region"


def _slide_selector_scroll_html(
    active_slide_id: int,
) -> str:
    active_id = json.dumps(str(active_slide_id))
    return f"""
    <script>
    (() => {{
      const doc = window.parent.document;
      const position = () => {{
        const root = doc.querySelector('.st-key-main_slide_preview_scroll');
        if (!root || root.getClientRects().length === 0) return;
        const target = root.querySelector(
          '.st-key-main_slide_preview_' + CSS.escape(String({active_id}))
        );
        if (!target) return;
        const candidates = [root, ...root.querySelectorAll('*')];
        const scroller = candidates.find((node) => {{
          const overflowY = window.parent.getComputedStyle(node).overflowY;
          return /(auto|scroll)/.test(overflowY)
            && node.scrollHeight > node.clientHeight + 8;
        }});
        if (!scroller) return;
        const targetBox = target.getBoundingClientRect();
        const scrollerBox = scroller.getBoundingClientRect();
        scroller.scrollTop = Math.max(
          0,
          scroller.scrollTop + targetBox.top - scrollerBox.top
          - (scroller.clientHeight - targetBox.height) / 2
        );
      }};
      [40, 120, 260].forEach((delay) => window.parent.setTimeout(position, delay));
    }})();
    </script>
    """


def _set_slide_rail_expanded(expanded: bool) -> None:
    st.session_state["main_slide_rail_expanded"] = bool(expanded)



def _render_slide_selector(
    browser: Any,
    *,
    slide_ids: Sequence[int] | None = None,
) -> None:
    """Render the one persistent, independently scrolling slide rail."""
    slide_ids = list(browser.slide_ids if slide_ids is None else slide_ids)
    if not slide_ids:
        return

    active_slide_id = st.session_state.get("main_active_slide_id", slide_ids[0])
    if active_slide_id not in slide_ids:
        active_slide_id = slide_ids[0]
        st.session_state["main_active_slide_id"] = active_slide_id

    if not st.session_state.get("main_slide_rail_expanded", True):
        with st.container(key="main_slide_rail_reopen"):
            st.button(
                "Slides",
                key="main_slide_rail_expand_button",
                help="Open slide deck",
                on_click=_set_slide_rail_expanded,
                args=(True,),
            )
        return

    with st.container(key="main_slide_rail"):
        title_column, close_column = st.columns(
            [0.78, 0.22],
            gap="small",
            vertical_alignment="center",
        )
        with title_column:
            st.markdown("**Slides**")
            st.caption(f"{len(slide_ids)} slides")
        with close_column:
            st.button(
                "×",
                key="main_slide_rail_collapse_button",
                help="Collapse slide deck",
                on_click=_set_slide_rail_expanded,
                args=(False,),
            )
        components.html(
            _slide_selector_scroll_html(active_slide_id),
            height=0,
            width=0,
        )
        with st.container(
            height=850,
            border=False,
            key="main_slide_preview_scroll",
        ):
            for slide_id in slide_ids:
                with st.container(
                    border=True,
                    key=f"main_slide_thumb_{slide_id}",
                ):
                    try:
                        preview_slide = browser.get_slide(slide_id)
                    except Exception:
                        preview_slide = None

                    if (
                        preview_slide is not None
                        and preview_slide.image_available
                        and preview_slide.image_path
                    ):
                        preview_path = Path(preview_slide.image_path)
                        st.image(
                            _thumbnail_png_bytes(
                                str(preview_path),
                                preview_path.stat().st_mtime_ns,
                            ),
                            width="stretch",
                        )
                    else:
                        st.markdown(
                            '<div class="as-slide-preview-empty">Preview</div>',
                            unsafe_allow_html=True,
                        )

                    st.button(
                        f"Slide {slide_id}",
                        key=f"main_slide_preview_{slide_id}",
                        type=(
                            "primary" if slide_id == active_slide_id else "secondary"
                        ),
                        width="stretch",
                        on_click=_navigate_to_slide,
                        args=(slide_id,),
                        help=f"Open slide {slide_id}",
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
        "### Target"
    )

    target_options = ["Whole slide", "Manual region"]
    if st.session_state.get("main_voice_engine") == "omni":
        target_options.insert(0, "Gaze AOI")
    st.radio(
        "Target scope",
        options=target_options,
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

    elif st.session_state["main_target_scope"] == "Gaze AOI":
        st.caption(
            "Look steadily at an AOI before starting Omni. "
            "The first stable target stays locked until you explicitly switch."
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
        "### Ask tutor"
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


def _render_unified_answer(
    view: MainUIViewModel,
    resources: MainLiveResources,
) -> None:
    _render_generation_status(view, resources)
    realtime_answer = (
        str(resources.voice.snapshot().get("answer_text") or "").strip()
        if st.session_state.get("main_interaction_flow") == "realtime"
        else ""
    )
    if realtime_answer:
        st.markdown(realtime_answer)
    else:
        _render_tutor_result(resources.single_turn_tts)
    _render_xai_drawer()

    st.button(
        "Reset current turn",
        width="stretch",
        key="main_reset_turn_button",
        on_click=_reset_turn_state,
    )

def _render_header(
    view: MainUIViewModel,
    *,
    resources: MainLiveResources,
    review: bool = False,
) -> None:
    lifecycle = resources.study_review.lifecycle()
    with st.container(key="main_topbar"):
        identity, context, action = st.columns(
            [0.28, 0.48, 0.24],
            gap="medium",
            vertical_alignment="center",
        )
        with identity:
            st.markdown(
                '<div class="as-topbar__identity">AttentiveSlides</div>'
                f'<div class="as-topbar__context">{"Review Workspace" if review else "Study Workspace"}</div>',
                unsafe_allow_html=True,
            )
        with context:
            st.markdown(f"**{view.deck_title}**")
            st.caption(
                f"Slide {view.active_slide_index + 1:02d} of {view.total_slides:02d}"
            )
        with action:
            if review:
                st.caption("Completed Study Review")
            else:
                started = st.session_state.get("main_study_started_monotonic")
                elapsed = (
                    _format_review_duration(time.monotonic() - float(started))
                    if lifecycle.status == "active" and started is not None
                    else "00:00"
                )
                st.caption(f"{lifecycle.status.replace('_', ' ').title()} · {elapsed}")
                if lifecycle.status == "idle":
                    st.button(
                        "Start study",
                        key="main_start_study",
                        disabled=resources.bound_deck_id is None,
                        width="stretch",
                        on_click=_start_study_review,
                        args=(resources, resources.bound_deck_id or ""),
                    )
                else:
                    st.button(
                        "End study & review",
                        key="main_end_study_review",
                        type="primary",
                        disabled=lifecycle.status not in {"active", "finish_pending"},
                        width="stretch",
                        on_click=_finish_study_review,
                        args=(resources, lifecycle.deck_id or ""),
                    )


def _learner_state_view(resources: MainLiveResources):
    live_enabled = _media_runtime_requested()
    deck_id = resources.bound_deck_id or ""
    slide_id = resources.bound_slide_id or 1
    snapshot = resources.learner_state_store.snapshot()
    slide = resources.study_review.active_slide_summary(deck_id, slide_id)
    return build_learner_state_view(
        snapshot,
        slide,
        live_enabled=live_enabled,
    )


@st.fragment(run_every=1.0)
def _render_learner_state_contents_periodic(
    resources: MainLiveResources,
) -> None:
    view = _learner_state_view(resources)
    rows = (
        ("Emotion", view.emotion_text),
        ("Engagement", view.engagement_text),
        ("Fatigue", view.fatigue_text),
        ("Current slide", view.slide_text),
    )
    row_html = "".join(
        '<div class="attentive-learner-row">'
        f'<span class="attentive-learner-label">{label}</span>'
        f'<span class="attentive-learner-value">{value}</span>'
        "</div>"
        for label, value in rows
    )
    detail_html = "".join(
        f'<div class="attentive-learner-detail">{detail}</div>'
        for detail in view.unavailable_details
    )
    st.markdown(
        '<div class="attentive-learner-panel">'
        f"{row_html}{detail_html}"
        "</div>",
        unsafe_allow_html=True,
    )
    if view.can_dismiss_distraction:
        st.button(
            "Dismiss distraction reminder",
            key="main_dismiss_distraction",
            width="stretch",
            on_click=resources.learner_state_worker.dismiss_distraction,
        )


@st.fragment(run_every=1.0)
def _render_learner_state_alert_periodic(
    resources: MainLiveResources,
) -> None:
    view = _learner_state_view(resources)
    if view.alert_text is None:
        return
    st.markdown(
        '<div class="attentive-learner-alert-anchor">'
        '<div class="attentive-learner-alert" role="status">'
        f"{html.escape(view.alert_text)}"
        "</div></div>",
        unsafe_allow_html=True,
    )




def _render_navigation(
    browser: Any,
    view: MainUIViewModel,
    *,
    slide_ids: Sequence[int] | None = None,
) -> None:
    if slide_ids is None:
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
    else:
        ordered_ids = list(slide_ids)
        active_index = ordered_ids.index(view.active_slide_id)
        previous_id = ordered_ids[active_index - 1] if active_index > 0 else None
        next_id = (
            ordered_ids[active_index + 1]
            if active_index + 1 < len(ordered_ids)
            else None
        )

    st.button(
        "❮",
        disabled=previous_id is None,
        key="main_previous_slide_button",
        help="Previous slide",
        on_click=_navigate_to_slide,
        args=(previous_id,),
    )

    st.button(
        "❯",
        disabled=next_id is None,
        key="main_next_slide_button",
        help="Next slide",
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
    st.session_state["main_target_scope_explicit"] = True
    _clear_manual_region()


def _render_current_slide_llm_aoi_action(
    view: MainUIViewModel,
    workspace: UploadedDeckWorkspace,
) -> None:
    if (
        not st.session_state.get("main_uploaded_deck_id")
    ):
        return
    try:
        state = workspace.get_llm_aoi_state(view.deck_id, view.active_slide_id)
    except Exception as exc:
        message = sanitized_llm_error(exc)
        st.session_state["main_llm_aoi_error"] = message
        st.error(message)
        return

    configured = bool(state.get("configured"))
    eligible = bool(state.get("eligible"))
    retry = state.get("status") == "fallback_used"
    if eligible:
        visual_status = str(state.get("visual_context_status", "empty"))
        if visual_status == "invalid":
            st.caption(
                f"LLM-enhanced · {state.get('aoi_count', 0)} AOIs · "
                "visual context unavailable"
            )
        else:
            st.caption(
                f"LLM-enhanced · {state.get('aoi_count', 0)} AOIs · "
                f"{state.get('visual_count', 0)} visual notes"
            )
        return
    label = (
        "Retry this slide with LLM"
        if retry
        else "Enhance this slide with LLM"
    )
    clicked = st.button(
        label,
        key="main_process_current_llm_aoi",
        disabled=not configured,
    )
    if not configured:
        st.caption("LLM AOI is not configured")
    if st.session_state.get("main_llm_aoi_error"):
        st.error(st.session_state["main_llm_aoi_error"])
    if not clicked:
        return

    st.session_state["main_llm_aoi_message"] = None
    st.session_state["main_llm_aoi_error"] = None
    try:
        result = workspace.prepare_llm_aoi(
            view.deck_id,
            view.active_slide_id,
            force=retry,
        )
    except Exception as exc:
        st.session_state["main_llm_aoi_error"] = sanitized_llm_error(exc)
        st.error(st.session_state["main_llm_aoi_error"])
        return
    if result.get("eligible"):
        st.session_state["main_llm_aoi_message"] = "LLM AOIs loaded"
        _reset_turn_state()
        st.session_state["main_active_aoi_signature"] = (
            f"{view.deck_id}:{view.active_slide_id}:{result.get('profile')}"
        )
        st.rerun()
    else:
        message = str(result.get("error") or "LLM AOI generation fell back to deterministic AOIs")
        st.session_state["main_llm_aoi_error"] = message
        st.error(message)


def _render_slide_workspace(
    view: MainUIViewModel,
    *,
    browser: Any,
    workspace: UploadedDeckWorkspace,
    live_resources: MainLiveResources,
) -> None:
    drawing_enabled = (
        st.session_state["main_target_scope"]
        == "Manual region"
    )
    if not drawing_enabled:
        _set_whole_slide_target(view)

    with st.container(key="main_primary_actions"):
        llm_column, status_column = st.columns(
            [0.62, 0.38],
            gap="small",
            vertical_alignment="center",
        )
        with llm_column:
            _render_current_slide_llm_aoi_action(view, workspace)
        with status_column:
            with st.popover(
                "Learner state",
                key="main_learner_state_popover",
                width="stretch",
            ):
                _render_learner_state_contents_periodic(live_resources)
            with st.container(key="main_learner_state_reminder_slot"):
                _render_learner_state_alert_periodic(live_resources)

    with st.container(key="main_slide_scale"):
        st.slider(
            "Slide size",
            min_value=50,
            max_value=100,
            step=5,
            key="main_slide_width_percent",
            label_visibility="collapsed",
        )

    with st.container(key="main_slide_stage"):
        _render_navigation(browser, view)
        if view.deck_id == "mock_deck" and not view.active_slide.image_available:
            _render_builtin_slide_placeholder()
            return
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
            clear_server_match=(
                not isinstance(
                    st.session_state.get("main_live_proposal"),
                    LiveInteractionProposal,
                )
                and not isinstance(
                    st.session_state.get("main_confirmed_interaction"),
                    dict,
                )
            ),
            key=(
                "main_slide_viewport_"
                f"{view.deck_id}_{view.active_slide_id}"
            ),
        )
    if payload is None:
        _render_static_slide(view.active_slide)
        return

    event = payload.get("event")
    if event == "disabled":
        _render_static_slide(view.active_slide)
        if drawing_enabled:
            st.caption(
                "Viewport selection is disabled only in AppTest workers."
            )
        return
    if event == "mounted":
        return
    if payload.get("coordinate_error"):
        st.session_state["main_selection_error"] = str(
            payload["coordinate_error"]
        )
        st.error(
            "Unable to read slide viewport geometry: "
            + st.session_state["main_selection_error"]
        )
        return
    if event != "manual_selection":
        return

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
        return


@contextmanager
def _left_aligned_slide_width():
    width_percent = int(st.session_state["main_slide_width_percent"])
    if width_percent >= 100:
        yield
        return
    slide_column, remainder = st.columns(
        [width_percent, 100 - width_percent],
        gap=None,
    )
    del remainder
    with slide_column:
        yield


def _render_builtin_slide_placeholder() -> None:
    with _left_aligned_slide_width():
        st.markdown(
            """
            <div class="attentive-built-in-stage">
                <div class="attentive-built-in-title">AttentiveSlides</div>
                <div class="attentive-built-in-tagline">
                    Select a slide region, state your learning goal, and receive a grounded tutor response.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


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

            with _left_aligned_slide_width():
                st.image(
                    display_image,
                    width="stretch",
                )

        finally:
            if display_image is not base_image:
                display_image.close()

            base_image.close()

    else:
        with _left_aligned_slide_width():
            with st.container(border=True):
                st.markdown(f"### Slide {slide.slide_id}")
                st.write(slide.slide_text or "Slide image unavailable.")



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
        "Ask tutor",
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



def _clear_conversation(
    tts_controller: SingleTurnTTSController,
) -> None:
    """Clear stored turns without changing current settings."""
    active_deck_id = st.session_state.get(
        "main_conversation_deck_id"
    )

    reset_main_conversation_state(
        st.session_state,
        deck_id=active_deck_id,
    )
    tts_controller.clear()


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
    resources: MainLiveResources,
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
    interaction = st.session_state["main_confirmed_interaction"]["interaction"]
    resources.study_review.record_completed_interaction(
        interaction_id=str(interaction["interaction_id"]),
        deck_id=str(interaction["deck_id"]),
        slide_id=int(interaction["slide_id"]),
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
    tts_controller: SingleTurnTTSController,
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
        args=(tts_controller,),
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


def _confirmed_interaction_id() -> str:
    wrapper = st.session_state.get("main_confirmed_interaction") or {}
    return str(wrapper.get("interaction", {}).get("interaction_id", ""))


def _generate_confirmed_turn(
    view: MainUIViewModel,
    resources: MainLiveResources,
) -> bool:
    """Generate one confirmed turn while preserving existing backend gates."""
    interaction_id = _confirmed_interaction_id()
    api_configured = bool(os.environ.get("DASHSCOPE_API_KEY"))
    assessment = assess_tutor_generation(
        st.session_state["main_confirmed_interaction"],
        cloud_text_allowed=st.session_state["main_cloud_text_allowed"],
        api_configured=api_configured,
    )
    if not interaction_id or not assessment.ready:
        return False
    st.session_state["main_last_generation_attempted_interaction_id"] = interaction_id
    st.session_state["main_tutor_error"] = None
    st.session_state["main_conversation_error"] = None
    try:
        with st.spinner("Generating and validating the grounded answer..."):
            client = OpenAICompatibleLLMClient.from_env()
            agent = GroundedTutorAgent(llm_client=client, max_retries=1)
            generation = generate_main_tutor_response(
                st.session_state["main_confirmed_interaction"],
                slide=view.active_slide,
                agent=agent,
                cloud_text_allowed=st.session_state["main_cloud_text_allowed"],
                api_configured=True,
                conversation_turns=(
                    st.session_state["main_conversation_turns"]
                    if st.session_state.get("main_interaction_flow") == "dialogue"
                    else []
                ),
                history_max_items=int(st.session_state["main_history_max_items"]),
            )
            payload = generation.to_session_payload()
    except Exception as exc:
        st.session_state["main_tutor_error"] = f"{type(exc).__name__}: {exc}"
        st.session_state["main_tutor_context"] = None
        st.session_state["main_tutor_result"] = None
        st.session_state["main_xai_result"] = None
        return False

    st.session_state["main_tutor_context"] = payload["context"]
    st.session_state["main_tutor_result"] = payload["tutor"]
    st.session_state["main_xai_result"] = payload["xai"]
    st.session_state["main_tutor_error"] = None
    st.session_state["main_last_generated_interaction_id"] = interaction_id
    try:
        _record_completed_turn(
            resources=resources,
            tutor_payload=payload["tutor"],
            llm_xai_payload=payload["xai"],
        )
    except Exception as exc:
        st.session_state["main_conversation_error"] = (
            "Tutor answer succeeded, but conversation recording failed: "
            f"{type(exc).__name__}: {exc}"
        )
    try:
        _log_completed_interaction_once()
    except Exception as exc:
        st.session_state["main_conversation_error"] = (
            "Tutor answer succeeded, but JSONL recording failed: "
            f"{type(exc).__name__}: {exc}"
        )
    return True


def _maybe_generate_confirmed_turn(
    view: MainUIViewModel,
    resources: MainLiveResources,
) -> bool:
    """Automatically continue once per newly confirmed interaction."""
    interaction_id = _confirmed_interaction_id()
    if (
        not interaction_id
        or st.session_state.get("main_last_generated_interaction_id")
        == interaction_id
        or st.session_state.get("main_last_generation_attempted_interaction_id")
        == interaction_id
    ):
        return False
    return _generate_confirmed_turn(view, resources)


def _retry_confirmed_turn() -> None:
    st.session_state["main_last_generation_attempted_interaction_id"] = None
    st.session_state["main_tutor_error"] = None


def _render_generation_status(
    view: MainUIViewModel,
    resources: MainLiveResources,
) -> None:
    assessment = assess_tutor_generation(
        st.session_state["main_confirmed_interaction"],
        cloud_text_allowed=st.session_state["main_cloud_text_allowed"],
        api_configured=bool(os.environ.get("DASHSCOPE_API_KEY")),
    )
    _maybe_generate_confirmed_turn(view, resources)
    if st.session_state["main_tutor_error"]:
        st.error(st.session_state["main_tutor_error"])
        st.button(
            "Retry",
            key="main_retry_answer_button",
            on_click=_retry_confirmed_turn,
        )
    elif assessment.code == "cloud_permission_required":
        st.warning(assessment.message)
    elif assessment.code == "api_not_configured":
        st.error(assessment.message)
    elif assessment.code not in {"ready", "confirmation_missing"}:
        st.info(assessment.message)
    if st.session_state["main_conversation_error"]:
        st.warning(st.session_state["main_conversation_error"])



def _render_tutor_result(
    tts_controller: SingleTurnTTSController,
) -> None:
    """Render the learner-facing answer without developer diagnostics."""
    result = st.session_state[
        "main_tutor_result"
    ]

    if result is None:
        st.info(
            "Ask a question to receive a grounded explanation."
        )
        return

    st.markdown(
        result["answer"]
    )

    speech = tts_controller.synthesize_once(
        interaction_id=str(
            st.session_state.get("main_last_generated_interaction_id") or ""
        ),
        text=str(result["answer"]),
        enabled=bool(
            _media_runtime_requested()
            and st.session_state.get("main_voice_engine") == "single_turn"
            and st.session_state["main_answer_audio_enabled"]
        ),
    )
    if speech.audio_path is not None:
        st.audio(str(speech.audio_path), format="audio/wav")
    elif speech.error_message:
        st.warning(speech.error_message)

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
    native_context = (
        selected_aoi.text.strip()
        if selected_aoi is not None
        else ""
    )
    linked_visual_context = _linked_visual_context_text(
        view.active_slide,
        selected_aoi_id,
    ).strip()
    confirmed_context = (
        native_context
        or linked_visual_context
        or view.active_slide.slide_text.strip()
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

    snapshot = resources.ingress.observations.latest_geometry_for(
        view.deck_id,
        view.active_slide_id,
    )
    geometry = snapshot.geometry if snapshot is not None else None

    if raw.gaze_source == "voice_locked_target":
        proposal = raw
    elif raw.gaze_source == "eyetheia_local":
        proposal = (
            raw
            if geometry is not None
            and raw.layout_revision == geometry.layout_revision
            else replace(
                raw,
                predicted_aoi_id=None,
                target_confidence=0.0,
                alternatives=(),
            )
        )
    elif geometry is None:
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

    preserved_manual_state = {}
    if raw.gaze_source == "voice_locked_target":
        preserved_manual_state = {
            key: st.session_state.get(key)
            for key in (
                "main_target_scope",
                "main_manual_bbox",
                "main_manual_region_active",
                "main_selected_aoi_ids",
                "main_selection_matches",
                "main_selection_text",
            )
        }
    reset_main_turn_state(st.session_state)
    st.session_state.update(preserved_manual_state)
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
    st.markdown("### Target")
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
        label_visibility="collapsed",
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


def _render_voice_component(
    view: MainUIViewModel,
) -> None:
    render_voice_control_component(
        engine=str(st.session_state["main_voice_engine"]),
        flow=str(st.session_state["main_interaction_flow"]),
        speech_mode=str(st.session_state["main_speech_mode"]),
        palette_tokens=palette_semantic(st.session_state["main_ui_palette"]),
        key=(
            "main_voice_control_"
            f"{view.deck_id}_{view.active_slide_id}"
        ),
    )


def _current_voice_panel_view(
    resources: MainLiveResources,
) -> VoicePanelView:
    snapshot = resources.voice.snapshot()
    proposal = st.session_state.get("main_live_proposal")
    if not isinstance(proposal, LiveInteractionProposal):
        proposal = None
    phase_aliases = {
        "capturing": "sampling",
        "recording": "sampling",
        "processing": "transcribing",
        "responding": "answering",
    }
    raw_phase = str(snapshot.get("state") or "").strip().lower()
    phase = phase_aliases.get(raw_phase, raw_phase)
    target_needs_confirmation = bool(
        proposal is not None and not st.session_state.get("main_confirmed")
    )
    confirmed_aoi_id = st.session_state.get("main_confirmed_aoi_id")
    target_label = snapshot.get("target_label") or confirmed_aoi_id
    transcript = (
        snapshot.get("user_transcript")
        if st.session_state.get("main_interaction_flow") == "realtime"
        else st.session_state.get("main_typed_command")
    )
    if target_needs_confirmation:
        phase = "confirmation"
    elif confirmed_aoi_id and phase in {"", "ready", "listening"}:
        phase = "locked"
    error_code = snapshot.get("error_code")
    if st.session_state.get("main_tutor_error"):
        error_code = "tutor_failed"
    return build_voice_panel_view(
        speech_mode=str(st.session_state["main_speech_mode"]),
        turn_phase=phase,
        transcript=str(transcript or ""),
        target_label=str(target_label) if target_label else None,
        target_needs_confirmation=target_needs_confirmation,
        error_code=str(error_code) if error_code else None,
    )


def _render_unified_interaction(
    view: MainUIViewModel,
    resources: MainLiveResources,
) -> None:
    panel = _current_voice_panel_view(resources)
    st.markdown("## Attention & Voice")
    st.markdown(
        '<div class="as-voice-state" role="status">'
        f'<strong>{html.escape(panel.title)}</strong>'
        f'<span>{html.escape(panel.detail)}</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    if panel.target_state == "sampling":
        st.caption("Sampling attention")
    elif panel.target_state == "needs_confirmation":
        st.warning("Target needs confirmation")
    elif panel.target_state == "locked" and panel.target_label:
        st.success(f"Target locked · {panel.target_label}")

    if _media_runtime_requested():
        _render_voice_component(view)
    else:
        st.caption("Camera and microphone are off. Typed input remains available.")

    proposal = st.session_state.get("main_live_proposal")
    if not isinstance(proposal, LiveInteractionProposal):
        proposal = None
    if proposal is None:
        _render_target_column(view)
        _render_intent_column(view)
        if _maybe_generate_confirmed_turn(view, resources) and _media_runtime_requested():
            st.session_state["main_live_full_rerun_requested"] = True
        return

    selected = _render_live_target_column(view, proposal)
    st.text_area(
        "Speech transcript",
        key="main_typed_command",
        height=96,
        placeholder="Your completed speech turn appears here.",
        on_change=_on_typed_command_change,
    )
    st.caption(
        "Edited transcript: hybrid provenance."
        if st.session_state["main_typed_command"].strip()
        != proposal.original_speech_transcript.strip()
        else "Original speech transcript: sensor-assisted provenance."
    )
    confirm_clicked = st.button(
        "Use this target",
        type="primary",
        disabled=(
            selected is None
            or not st.session_state["main_typed_command"].strip()
            or st.session_state["main_confirmed"]
        ),
        width="stretch",
        key="main_live_confirm_button",
    )
    if confirm_clicked and selected is not None:
        try:
            _store_live_confirmation(
                view,
                proposal,
                selected_option=selected,
                automatic=False,
            )
            _maybe_generate_confirmed_turn(view, resources)
        except Exception as exc:
            _invalidate_confirmation()
            st.session_state["main_confirmation_error"] = (
                f"{type(exc).__name__}: {exc}"
            )
    if st.session_state["main_confirmation_error"]:
        st.error(st.session_state["main_confirmation_error"])



@st.fragment(run_every=0.5)
def _render_live_periodic(
    resources: MainLiveResources,
    view: MainUIViewModel,
) -> None:
    if _adopt_voice_fallback_state(resources):
        st.rerun(scope="app")
        return
    try:
        _consume_live_proposal(resources, view)
        _maybe_generate_confirmed_turn(view, resources)
    except Exception as exc:
        st.error(
            "Live proposal processing failed: "
            f"{type(exc).__name__}: {exc}"
        )
    session = resources.ingress.session_snapshot()
    ingress_stats = resources.ingress.stats_payload()
    runtime_state = resources.runtime.controller.state.value
    st.caption(
        f"Live transport: {'armed' if session.armed else 'off'} · "
        f"Runtime: {runtime_state} · "
        f"Media: {'ready' if session.video_fresh and session.audio_fresh else 'waiting'} · "
        f"Local gaze: {'ready' if ingress_stats['gaze_fresh'] else 'fallback'}"
    )
    _render_unified_interaction(view, resources)
    proposal = st.session_state.get("main_live_proposal")
    if not isinstance(proposal, LiveInteractionProposal):
        proposal = None
    confirmed_interaction = st.session_state.get(
        "main_confirmed_interaction"
    )
    if not isinstance(confirmed_interaction, dict):
        confirmed_interaction = None
    valid_aoi_ids = {
        aoi.aoi_id
        for aoi in view.active_slide.aois
        if aoi.aoi_id != "whole_slide"
    }
    matched_aoi_id = resolve_live_debug_aoi_id(
        deck_id=view.deck_id,
        slide_id=view.active_slide_id,
        valid_aoi_ids=valid_aoi_ids,
        proposal=proposal,
        confirmed_interaction=confirmed_interaction,
    )
    render_live_debug_bridge(
        deck_id=view.deck_id,
        slide_id=view.active_slide_id,
        matched_aoi_id=matched_aoi_id,
        enabled=bool(st.session_state["main_show_aoi_overlay"]),
        clear_match=(
            proposal is None
            and confirmed_interaction is None
        ),
        key=(
            "main_live_debug_bridge_"
            f"{view.deck_id}_{view.active_slide_id}"
        ),
    )
    if st.session_state.pop("main_live_full_rerun_requested", False):
        st.rerun(scope="app")



def _render_manual_interaction(
    view: MainUIViewModel,
    *,
    live_resources: MainLiveResources | None = None,
) -> None:
    """Route every flow through one stable Attention & Voice panel."""
    if live_resources is None:
        return
    if _media_runtime_requested():
        _render_live_periodic(live_resources, view)
        return
    _render_unified_interaction(view, live_resources)



def _render_lower_workspace(
    view: MainUIViewModel,
    live_resources: MainLiveResources,
) -> None:
    """Keep the Tutor explanation stable below the working row."""
    with st.container(key="main_tutor_answer"):
        st.markdown("## Tutor explanation")
        _render_unified_answer(view, live_resources)
    with st.expander(
        "Conversation history",
        expanded=False,
    ):
        _render_conversation_history(
            view,
            live_resources.single_turn_tts,
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
