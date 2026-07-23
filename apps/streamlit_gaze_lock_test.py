"""Standalone B-mode test: lock an AOI with gaze, then type."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sys
import time
from typing import Any
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import streamlit as st

from modules.gaze_lock_test.contracts import (
    GazeLockScope,
    LockedGazeTarget,
)
from modules.gaze_lock_test.ingress_service import GazeOnlyIngressService
from modules.gaze_lock_test.logger import (
    GazeLockTestLogger,
    build_gaze_lock_log_row,
    gaze_lock_log_path,
)
from modules.gaze_lock_test.workflow import (
    build_typed_interaction,
    canonical_aoi_identity,
    consume_lock_event,
    lock_is_current,
)
from modules.system.main_tutor_integration import generate_main_tutor_response
from modules.system.main_ui_state import MainUISlide
from modules.system.uploaded_deck_service import UploadedDeckWorkspace
from modules.tutor.api_llm_client import OpenAICompatibleLLMClient
from modules.tutor.grounded_tutor_agent import GroundedTutorAgent
from modules.ui.design_tokens import DEFAULT_PALETTE_ID, palette_semantic
from modules.ui.gaze_lock_control_component import (
    render_gaze_lock_control_component,
)
from modules.ui.live_debug_bridge_component import render_live_debug_bridge
from modules.ui.slide_viewport_component import render_slide_viewport


RUNTIME_DATA_DIR = Path(
    os.environ.get(
        "ATTENTIVE_RUNTIME_DATA_DIR",
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "attentive_slides",
    )
).resolve()


@st.cache_resource
def _gaze_service() -> GazeOnlyIngressService:
    service = GazeOnlyIngressService()
    if os.environ.get("ATTENTIVE_DISABLE_GAZE_LOCK_INGRESS_FOR_APPTEST") != "1":
        service.ensure_started()
    return service


@st.cache_resource
def _logger(path: str) -> GazeLockTestLogger:
    return GazeLockTestLogger(path)


def _initialize_state() -> None:
    defaults: dict[str, Any] = {
        "gaze_lock_session_id": f"session-{uuid4().hex}",
        "gaze_lock_deck_id": None,
        "gaze_lock_pdf_signature": None,
        "gaze_lock_slide_id": 1,
        "gaze_lock_previous_slide_id": None,
        "gaze_lock_layout_seed": 1,
        "gaze_lock_seen_event_ids": [],
        "gaze_lock_target": None,
        "gaze_lock_question": "",
        "gaze_lock_tutor_result": None,
        "gaze_lock_error": None,
        "gaze_lock_last_request_signature": None,
        "gaze_lock_control_revision": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_lock(*, increment_control: bool = False) -> None:
    st.session_state["gaze_lock_target"] = None
    st.session_state["gaze_lock_tutor_result"] = None
    st.session_state["gaze_lock_error"] = None
    st.session_state["gaze_lock_last_request_signature"] = None
    if increment_control:
        st.session_state["gaze_lock_control_revision"] += 1


def _load_pdf(workspace: UploadedDeckWorkspace, uploaded_file: Any) -> None:
    if uploaded_file is None:
        return
    content = uploaded_file.getvalue()
    signature = hashlib.sha256(
        uploaded_file.name.encode("utf-8") + b"\0" + content
    ).hexdigest()
    if (
        signature == st.session_state["gaze_lock_pdf_signature"]
        and st.session_state["gaze_lock_deck_id"]
    ):
        return
    summary = workspace.ingest_pdf(
        filename=uploaded_file.name,
        content=content,
    )
    st.session_state["gaze_lock_deck_id"] = summary.deck_id
    st.session_state["gaze_lock_pdf_signature"] = signature
    st.session_state["gaze_lock_slide_id"] = 1
    st.session_state["gaze_lock_previous_slide_id"] = 1
    st.session_state.pop("gaze_lock_slide_selector", None)
    st.session_state["gaze_lock_layout_seed"] += 1
    _clear_lock(increment_control=True)


def _current_scope(
    service: GazeOnlyIngressService,
    *,
    deck_id: str,
    slide: MainUISlide,
) -> GazeLockScope | None:
    generation = service.capture_generation()
    geometry = service.observations.latest_geometry_for(
        deck_id,
        slide.slide_id,
    )
    if generation is None or geometry is None:
        return None
    return GazeLockScope(
        deck_id=deck_id,
        slide_id=slide.slide_id,
        layout_revision=geometry.geometry.layout_revision,
        capture_session_id=f"generation-{generation}",
        aoi_identity=canonical_aoi_identity(
            slide.aois,
            aoi_profile=slide.aoi_profile,
        ),
    )


def _confirmed_context(slide: MainUISlide, aoi_id: str) -> str:
    aoi = next(
        (candidate for candidate in slide.aois if candidate.aoi_id == aoi_id),
        None,
    )
    if aoi is None:
        raise ValueError("Locked AOI is not available on the current slide.")
    native_text = aoi.text.strip()
    if native_text:
        return native_text
    for item in slide.visual_context:
        if item.linked_aoi_id != aoi_id:
            continue
        visual_text = "\n".join(
            part
            for part in (
                item.transcription.strip(),
                item.description.strip(),
            )
            if part
        )
        if visual_text:
            return visual_text
    if slide.slide_text.strip():
        return slide.slide_text.strip()
    raise ValueError("Locked AOI has no usable tutor context.")


def _render_target(target: LockedGazeTarget | None) -> None:
    if target is None:
        st.info(
            "Look steadily at the intended AOI, then press LOCK GAZE TARGET."
        )
        return
    st.success(f"Locked: {target.aoi_label}")
    st.caption(
        f"AOI `{target.aoi_id}` · confidence {target.target_confidence:.3f} "
        f"· matched dwell {target.stable_duration_sec:.3f}s "
        f"· layout {target.layout_revision}"
    )


def _ask_tutor(
    *,
    slide: MainUISlide,
    target: LockedGazeTarget,
    question: str,
) -> None:
    request_id = f"request-{uuid4().hex}"
    interaction = build_typed_interaction(
        target,
        question_text=question,
        interaction_id=request_id,
    )
    wrapper = {
        "interaction": interaction.to_dict(),
        "confirmed_context": _confirmed_context(slide, target.aoi_id),
    }
    client = OpenAICompatibleLLMClient.from_env()
    agent = GroundedTutorAgent(llm_client=client, max_retries=1)
    generation = generate_main_tutor_response(
        wrapper,
        slide=slide,
        agent=agent,
        cloud_text_allowed=True,
        api_configured=True,
    )
    payload = generation.to_session_payload()
    completed_at = datetime.now(timezone.utc).isoformat()
    logger = _logger(
        str(
            gaze_lock_log_path(
                RUNTIME_DATA_DIR,
                session_id=st.session_state["gaze_lock_session_id"],
            )
        )
    )
    logger.append_once(
        build_gaze_lock_log_row(
            session_id=st.session_state["gaze_lock_session_id"],
            request_id=request_id,
            target=target,
            question_text=question,
            tutor_response=payload["tutor"],
            completed_at_server=completed_at,
        )
    )
    st.session_state["gaze_lock_tutor_result"] = payload
    st.session_state["gaze_lock_error"] = None


def _render_answer() -> None:
    payload = st.session_state.get("gaze_lock_tutor_result")
    if not isinstance(payload, dict):
        return
    tutor = payload.get("tutor")
    if not isinstance(tutor, dict):
        return
    st.subheader("Tutor answer")
    st.write(str(tutor.get("answer", "")))
    st.caption(
        f"Target source: gaze_prediction · Intent source: typed_text · "
        f"Provider: {tutor.get('provider', 'unknown')} · "
        f"Model: {tutor.get('model', 'unknown')}"
    )


def main() -> None:
    st.set_page_config(
        page_title="B Gaze-Lock Typed Test",
        layout="wide",
    )
    _initialize_state()
    service = _gaze_service()
    workspace = UploadedDeckWorkspace(RUNTIME_DATA_DIR / "uploaded_decks")
    palette = palette_semantic(DEFAULT_PALETTE_ID)

    st.title("B Gaze-Lock Typed Test")
    st.caption(
        "Standalone test mode: gaze locks the AOI first; typing cannot move it."
    )

    uploaded_file = st.sidebar.file_uploader(
        "Upload a PDF slide deck",
        type=["pdf"],
        key="gaze_lock_pdf_upload",
    )
    if st.sidebar.button(
        "LOAD PDF",
        disabled=uploaded_file is None,
        width="stretch",
    ):
        try:
            with st.spinner("Preparing PDF deck..."):
                _load_pdf(workspace, uploaded_file)
        except Exception:
            st.session_state["gaze_lock_error"] = (
                "The PDF could not be prepared. Check the file and retry."
            )
        else:
            st.rerun()

    deck_id = st.session_state.get("gaze_lock_deck_id")
    if not deck_id:
        st.info("Upload a PDF to begin the isolated gaze-lock test.")
        return
    try:
        browser = workspace.open_browser(str(deck_id))
    except Exception:
        st.session_state["gaze_lock_deck_id"] = None
        st.error("The saved PDF deck could not be reopened. Upload it again.")
        return

    selected_slide_id = st.sidebar.selectbox(
        "Slide",
        options=browser.slide_ids,
        index=browser.slide_index(
            int(st.session_state["gaze_lock_slide_id"])
        ),
        key="gaze_lock_slide_selector",
    )
    previous_slide_id = st.session_state.get("gaze_lock_previous_slide_id")
    if selected_slide_id != previous_slide_id:
        st.session_state["gaze_lock_slide_id"] = int(selected_slide_id)
        st.session_state["gaze_lock_previous_slide_id"] = int(selected_slide_id)
        st.session_state["gaze_lock_layout_seed"] += 1
        _clear_lock(increment_control=True)

    with st.spinner("Preparing slide and AOIs..."):
        slide = browser.get_slide(int(selected_slide_id))
    st.caption(
        f"Deck `{browser.deck_id}` · slide {slide.slide_id} "
        f"· AOI profile `{slide.aoi_profile}`"
    )

    slide_column, control_column = st.columns([1.65, 1.0], gap="large")
    with slide_column:
        render_slide_viewport(
            deck_id=browser.deck_id,
            slide=slide,
            layout_revision=int(st.session_state["gaze_lock_layout_seed"]),
            drawing_enabled=False,
            show_aoi_overlay=True,
            display_width_percent=100,
            palette_tokens=palette,
            clear_server_match=(
                st.session_state.get("gaze_lock_target") is None
            ),
            key=(
                f"gaze_lock_slide_{browser.deck_id}_{slide.slide_id}_"
                f"{st.session_state['gaze_lock_layout_seed']}"
            ),
        )
        locked_for_overlay = st.session_state.get("gaze_lock_target")
        render_live_debug_bridge(
            deck_id=browser.deck_id,
            slide_id=slide.slide_id,
            matched_aoi_id=(
                locked_for_overlay.aoi_id
                if isinstance(locked_for_overlay, LockedGazeTarget)
                else None
            ),
            enabled=True,
            clear_match=not isinstance(
                locked_for_overlay,
                LockedGazeTarget,
            ),
            key=f"gaze_lock_bridge_{browser.deck_id}_{slide.slide_id}",
        )

    with control_column:
        st.subheader("1 · Camera and gaze")
        st.iframe("/capture", height=330)
        scope = _current_scope(
            service,
            deck_id=browser.deck_id,
            slide=slide,
        )
        target = st.session_state.get("gaze_lock_target")
        if not isinstance(target, LockedGazeTarget):
            target = None
        if target is not None and not lock_is_current(target, scope):
            _clear_lock(increment_control=True)
            target = None
            st.warning(
                "The deck, slide, AOIs, layout, or camera session changed. "
                "Acquire the gaze target again."
            )

        if st.button(
            "RETARGET",
            disabled=target is None,
            width="stretch",
        ):
            _clear_lock(increment_control=True)
            st.rerun()

        lock_payload = render_gaze_lock_control_component(
            label="LOCK GAZE TARGET",
            disabled=target is not None,
            palette_tokens=palette,
            key=(
                "gaze_lock_control_"
                f"{st.session_state['gaze_lock_control_revision']}"
            ),
        )
        samples = service.observations.gaze_in_window(
            start_received_at=0.0,
            end_received_at=time.monotonic() + 1.0,
        )
        lock_event = (
            lock_payload
            if isinstance(lock_payload, dict)
            and lock_payload.get("event") == "gaze_lock"
            else None
        )
        attempt = consume_lock_event(
            lock_event,
            seen_event_ids=st.session_state["gaze_lock_seen_event_ids"],
            current_target=target,
            scope=scope,
            samples=samples,
            aois=slide.aois,
        )
        if attempt.event_id and attempt.status != "duplicate":
            seen = list(st.session_state["gaze_lock_seen_event_ids"])
            seen.append(attempt.event_id)
            st.session_state["gaze_lock_seen_event_ids"] = seen[-100:]
        if attempt.status == "locked" and attempt.target is not None:
            st.session_state["gaze_lock_target"] = attempt.target
            st.session_state["gaze_lock_tutor_result"] = None
            st.session_state["gaze_lock_error"] = None
            st.rerun()
        if attempt.status in {
            "invalid_event",
            "scope_unavailable",
            "insufficient_gaze",
        }:
            st.warning(attempt.message)

        target = st.session_state.get("gaze_lock_target")
        if not isinstance(target, LockedGazeTarget):
            target = None
        _render_target(target)

        st.subheader("2 · Type after locking")
        question = st.text_area(
            "Typed question",
            key="gaze_lock_question",
            disabled=target is None,
            placeholder="Now look at the keyboard and type your question.",
        )
        question_text = str(question or "").strip()
        request_signature = (
            hashlib.sha256(
                f"{target.lock_id}\0{question_text}".encode("utf-8")
            ).hexdigest()
            if target is not None and question_text
            else None
        )
        api_configured = bool(os.environ.get("DASHSCOPE_API_KEY"))
        ask_disabled = (
            target is None
            or not question_text
            or not api_configured
            or request_signature
            == st.session_state.get("gaze_lock_last_request_signature")
        )
        if not api_configured:
            st.caption("DASHSCOPE_API_KEY is required to call the tutor.")
        if st.button(
            "ASK TUTOR",
            disabled=ask_disabled,
            type="primary",
            width="stretch",
        ):
            current_scope = _current_scope(
                service,
                deck_id=browser.deck_id,
                slide=slide,
            )
            if not lock_is_current(target, current_scope):
                _clear_lock(increment_control=True)
                st.warning("The lock is stale. Acquire the gaze target again.")
                st.rerun()
            try:
                with st.spinner("Generating a grounded answer..."):
                    _ask_tutor(
                        slide=slide,
                        target=target,
                        question=question_text,
                    )
            except Exception as exc:
                st.session_state["gaze_lock_error"] = (
                    f"Tutor request failed ({type(exc).__name__}); retry is safe."
                )
            else:
                st.session_state[
                    "gaze_lock_last_request_signature"
                ] = request_signature

        if st.session_state.get("gaze_lock_error"):
            st.error(st.session_state["gaze_lock_error"])
        _render_answer()


main()
