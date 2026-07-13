"""Compact Streamlit microphone input surface."""

from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

from modules.system.voice_input_controller import (
    VoiceInputController,
    build_default_voice_input_controller,
)


VOICE_DISABLE_ENV = (
    "ATTENTIVE_DISABLE_MICROPHONE_FOR_APPTEST"
)


@st.cache_resource
def get_voice_input_controller(
) -> VoiceInputController:
    return (
        build_default_voice_input_controller()
    )


def _initialize_voice_state(
) -> None:
    defaults = {
        "main_voice_enabled": False,
        "main_voice_status": "off",
        "main_voice_transcript": "",
        "main_voice_language": None,
        "main_voice_error": None,
        "main_voice_accepted": False,
        "main_voice_last_accepted_text": "",
        "main_pending_intent_source": (
            "typed_text"
        ),
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = (
                value
            )


def _on_voice_enabled_change(
) -> None:
    controller = (
        get_voice_input_controller()
    )

    if st.session_state[
        "main_voice_enabled"
    ]:
        try:
            controller.enable()

        except Exception as error:
            st.session_state[
                "main_voice_enabled"
            ] = False

            st.session_state[
                "main_voice_status"
            ] = "error"

            st.session_state[
                "main_voice_error"
            ] = (
                f"{type(error).__name__}: "
                f"{error}"
            )

    else:
        controller.disable()

        st.session_state[
            "main_voice_status"
        ] = "off"


def _accept_voice_transcript(
    command_key: str,
) -> None:
    text = str(
        st.session_state.get(
            "main_voice_transcript",
            "",
        )
    ).strip()

    if not text:
        return

    st.session_state[
        command_key
    ] = text

    st.session_state[
        "main_voice_accepted"
    ] = True

    st.session_state[
        "main_voice_last_accepted_text"
    ] = text

    st.session_state[
        "main_pending_intent_source"
    ] = "speech_transcript"


def _poll_voice_input(
) -> None:
    _initialize_voice_state()

    if not st.session_state[
        "main_voice_enabled"
    ]:
        return

    controller = (
        get_voice_input_controller()
    )

    controller.poll()

    snapshot = (
        controller.snapshot()
    )

    st.session_state[
        "main_voice_status"
    ] = snapshot.status

    st.session_state[
        "main_voice_error"
    ] = snapshot.latest_error

    if snapshot.latest_transcript:
        st.session_state[
            "main_voice_transcript"
        ] = (
            snapshot
            .latest_transcript
        )

        st.session_state[
            "main_voice_language"
        ] = (
            snapshot
            .latest_language
        )


if hasattr(
    st,
    "fragment",
):
    _voice_poll_fragment = (
        st.fragment(
            run_every=0.5
        )(
            _poll_voice_input
        )
    )

else:
    _voice_poll_fragment = (
        _poll_voice_input
    )


def voice_sidebar_status(
) -> str:
    status = str(
        st.session_state.get(
            "main_voice_status",
            "off",
        )
    )

    labels = {
        "off": "Off",
        "waiting_permission": (
            "Waiting"
        ),
        "listening": "Listening",
        "speech_active": "Speech",
        "transcribing": (
            "Transcribing"
        ),
        "ready": "Ready",
        "error": "Error",
    }

    return labels.get(
        status,
        status.replace(
            "_",
            " ",
        ).title(),
    )


def render_voice_input_panel(
    *,
    command_key: str,
) -> None:
    """Render microphone and transcript acceptance controls."""

    _initialize_voice_state()

    if os.environ.get(
        VOICE_DISABLE_ENV
    ) == "1":
        st.caption(
            "Voice input is disabled "
            "during automated AppTest."
        )
        return

    st.toggle(
        "Microphone input",
        key="main_voice_enabled",
        help=(
            "Microphone audio is transcribed "
            "locally. It is not sent to the "
            "cloud tutor in Stage 2."
        ),
        on_change=(
            _on_voice_enabled_change
        ),
    )

    if not st.session_state[
        "main_voice_enabled"
    ]:
        return

    controller = (
        get_voice_input_controller()
    )

    try:
        controller.enable()

    except Exception as error:
        st.session_state[
            "main_voice_status"
        ] = "error"

        st.session_state[
            "main_voice_error"
        ] = (
            f"{type(error).__name__}: "
            f"{error}"
        )

        st.error(
            st.session_state[
                "main_voice_error"
            ]
        )

        return

    components.iframe(
        controller
        .service
        .capture_url,
        height=145,
        scrolling=False,
    )

    _voice_poll_fragment()

    status = voice_sidebar_status()

    st.caption(
        f"Microphone status: {status}"
    )

    error = st.session_state.get(
        "main_voice_error"
    )

    if error:
        st.warning(
            error
        )

    transcript = str(
        st.session_state.get(
            "main_voice_transcript",
            "",
        )
    ).strip()

    if transcript:
        st.markdown(
            "**Latest transcript**"
        )

        st.write(
            transcript
        )

        st.button(
            "Use transcript",
            key=(
                "main_use_voice_"
                "transcript_button"
            ),
            width="stretch",
            on_click=(
                _accept_voice_transcript
            ),
            args=(
                command_key,
            ),
        )
