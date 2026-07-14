"""Streamlit integration for Stage 3 realtime voice."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from modules.system.realtime_tutor_context import (
    RealtimeTutorContext,
)
from modules.system.realtime_voice_controller import (
    RealtimeVoiceController,
    build_realtime_voice_controller,
)


DISABLE_ENV = (
    "ATTENTIVE_DISABLE_REALTIME_VOICE_FOR_APPTEST"
)

LEGACY_DISABLE_ENV = (
    "ATTENTIVE_DISABLE_MICROPHONE_FOR_APPTEST"
)


def _disabled_for_test() -> bool:
    """Return True when browser and network features must remain inert."""

    return bool(
        os.environ.get(
            DISABLE_ENV
        )
        == "1"
        or os.environ.get(
            LEGACY_DISABLE_ENV
        )
        == "1"
    )


def _set_apptest_defaults() -> None:
    """Populate deterministic state without creating widgets."""

    defaults = {
        "main_camera_enabled": False,
        "main_microphone_enabled": False,
        "main_microphone_permission": (
            "unknown"
        ),
        "main_interaction_mode": "manual",
        "main_realtime_enabled": False,
        "main_realtime_state": "off",
        "main_realtime_turn_id": "",
        "main_realtime_user_transcript": "",
        "main_realtime_answer_text": "",
        "main_realtime_error": None,
        "main_realtime_rejection_reason": None,
        "main_realtime_speaker_enabled": False,
    }

    for key, value in defaults.items():
        st.session_state.setdefault(
            key,
            value,
        )


@st.cache_resource
def get_realtime_voice_controller(
) -> RealtimeVoiceController:
    """Create one gateway/controller resource for the real UI."""

    return (
        build_realtime_voice_controller()
    )


def _extract_view_value(
    view: Any,
    names: tuple[str, ...],
    default: Any,
) -> Any:
    for name in names:
        if isinstance(
            view,
            dict,
        ):
            value = view.get(
                name
            )

            if value is not None:
                return value

        if (
            view is not None
            and hasattr(
                view,
                name,
            )
        ):
            value = getattr(
                view,
                name,
            )

            if value is not None:
                return value

        if name in st.session_state:
            value = (
                st.session_state[
                    name
                ]
            )

            if value is not None:
                return value

    return default


def update_realtime_grounding(
    view: Any = None,
) -> None:
    """Update the next realtime turn with current slide/AOI context."""

    if _disabled_for_test():
        _set_apptest_defaults()
        return

    controller = (
        get_realtime_voice_controller()
    )

    slide_number = int(
        _extract_view_value(
            view,
            (
                "slide_number",
                "current_slide_number",
                "main_current_slide_number",
            ),
            1,
        )
    )

    slide_text = str(
        _extract_view_value(
            view,
            (
                "slide_text",
                "current_slide_text",
                "main_current_slide_text",
            ),
            "",
        )
    )

    region_text = str(
        _extract_view_value(
            view,
            (
                "selected_region_text",
                "manual_region_text",
                "main_selected_region_text",
            ),
            "",
        )
    )

    target_scope = str(
        _extract_view_value(
            view,
            (
                "target_scope",
                "main_target_scope",
            ),
            "Whole slide",
        )
    )

    controller.update_context(
        RealtimeTutorContext(
            slide_number=(
                slide_number
            ),
            slide_text=slide_text,
            selected_region_text=(
                region_text
            ),
            target_scope=target_scope,
        )
    )


def render_sidebar_device_controls(
) -> None:
    """Render all four device-status cards in the real Streamlit sidebar."""

    if _disabled_for_test():
        _set_apptest_defaults()

        with st.sidebar:
            st.caption(
                "MODE: Manual · "
                "CAMERA: Off · "
                "MICROPHONE: Off · "
                "CLOUD TUTOR: Offline"
            )

        return

    controller = (
        get_realtime_voice_controller()
    )

    controller.refresh_cloud_status()

    # Placement is controlled here rather than at the
    # call site. The iframe therefore cannot render in the
    # main content area.
    with st.sidebar:
        components.iframe(
            controller.capture_url(
                view="device"
            ),
            height=220,
            scrolling=False,
        )


def _write_snapshot_to_state(
    snapshot: dict[str, Any],
) -> None:
    mappings = {
        "main_camera_enabled": (
            "camera_enabled"
        ),
        "main_microphone_enabled": (
            "microphone_enabled"
        ),
        "main_microphone_permission": (
            "microphone_permission"
        ),
        "main_interaction_mode": (
            "interaction_mode"
        ),
        "main_realtime_enabled": (
            "continuous_enabled"
        ),
        "main_realtime_state": (
            "voice_state"
        ),
        "main_realtime_turn_id": (
            "turn_id"
        ),
        "main_realtime_user_transcript": (
            "latest_user_transcript"
        ),
        "main_realtime_answer_text": (
            "latest_answer_text"
        ),
        "main_realtime_error": (
            "latest_error"
        ),
        "main_realtime_rejection_reason": (
            "latest_rejection_reason"
        ),
        "main_realtime_speaker_enabled": (
            "speaker_enabled"
        ),
    }

    for session_key, source_key in (
        mappings.items()
    ):
        st.session_state[
            session_key
        ] = snapshot.get(
            source_key
        )


def _render_result_body() -> None:
    controller = (
        get_realtime_voice_controller()
    )

    snapshot = (
        controller.snapshot()
    )

    _write_snapshot_to_state(
        snapshot
    )

    transcript = str(
        snapshot.get(
            "latest_user_transcript",
            "",
        )
    ).strip()

    answer = str(
        snapshot.get(
            "latest_answer_text",
            "",
        )
    ).strip()

    rejection = snapshot.get(
        "latest_rejection_reason"
    )

    error = snapshot.get(
        "latest_error"
    )

    if transcript:
        st.caption(
            "Voice transcript: "
            + transcript
        )

    if answer:
        st.markdown(
            "**Generated grounded answer**"
        )

        st.write(
            answer
        )

        st.caption(
            "Answer source: "
            "Qwen3.5-Omni-Realtime"
        )

    if rejection:
        st.caption(
            "Ignored voice input: "
            + str(rejection)
        )

    if error:
        st.warning(
            str(error)
        )


if hasattr(
    st,
    "fragment",
):
    @st.fragment(
        run_every=0.5
    )
    def _render_realtime_result(
    ) -> None:
        _render_result_body()

else:
    def _render_realtime_result(
    ) -> None:
        _render_result_body()


def render_grounded_tutor_voice(
    view: Any = None,
) -> None:
    """Render push-to-talk inside Grounded Tutor."""

    if _disabled_for_test():
        _set_apptest_defaults()
        return

    update_realtime_grounding(
        view
    )

    st.markdown(
        "**Voice question**"
    )

    controller = (
        get_realtime_voice_controller()
    )

    components.iframe(
        controller.capture_url(
            view="ptt"
        ),
        height=145,
        scrolling=False,
    )

    _render_realtime_result()


def render_continuous_voice_panel(
    view: Any = None,
) -> None:
    """Render continuous dialogue and speaker controls."""

    if _disabled_for_test():
        _set_apptest_defaults()
        return

    update_realtime_grounding(
        view
    )

    st.markdown(
        "### Continuous Conversation"
    )

    st.caption(
        "Each voice turn uses a fresh provider "
        "session and is not added to conversation history."
    )

    controller = (
        get_realtime_voice_controller()
    )

    components.iframe(
        controller.capture_url(
            view="continuous"
        ),
        height=145,
        scrolling=False,
    )


def render_realtime_voice_xai(
) -> None:
    """Add sanitized realtime metadata to the existing XAI area."""

    if _disabled_for_test():
        _set_apptest_defaults()
        return

    snapshot = (
        get_realtime_voice_controller()
        .snapshot()
    )

    st.markdown(
        "**Realtime voice trace**"
    )

    rows = {
        "Mode": snapshot.get(
            "interaction_mode"
        ),
        "Microphone permission": (
            snapshot.get(
                "microphone_permission"
            )
        ),
        "Speaker enabled": snapshot.get(
            "speaker_enabled"
        ),
        "Voice state": snapshot.get(
            "voice_state"
        ),
        "Turn ID": snapshot.get(
            "turn_id"
        ),
        "Continuous": snapshot.get(
            "continuous_enabled"
        ),
        "Gate rejection": snapshot.get(
            "latest_rejection_reason"
        ),
        "Latency (ms)": snapshot.get(
            "latest_elapsed_ms"
        ),
        "History persisted": False,
        "Realtime model": os.environ.get(
            "ATTENTIVE_REALTIME_MODEL",
            (
                "qwen3.5-omni-"
                "plus-realtime"
            ),
        ),
    }

    for key, value in rows.items():
        st.write(
            f"{key}: {value}"
        )
