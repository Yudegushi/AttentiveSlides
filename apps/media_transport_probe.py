"""Minimal Streamlit probe for browser camera/microphone transport."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

# Streamlit executes app files with apps/ as the script directory. Add the
# repository root so the modules package can be imported in remote deployment.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from modules.media import BrowserMediaSource


SOURCE_KEY = "media_transport_source"
MASTER_KEY = "media_transport_enabled"
PREVIOUS_PLAYING_KEY = "media_transport_previous_playing"
PENDING_COMPONENT_FAILURE_KEY = "media_transport_pending_component_failure"


def _source() -> BrowserMediaSource:
    source = st.session_state.get(SOURCE_KEY)
    if source is None:
        source = BrowserMediaSource()
        st.session_state[SOURCE_KEY] = source
    return source


def _master_changed() -> None:
    if not st.session_state.get(MASTER_KEY, False):
        _source().stop(reason="master switch off")


def _sync_component_failure(
    source: BrowserMediaSource,
    session_state: dict[str, Any],
    detail: str,
) -> None:
    source.handle_component_error(detail)
    session_state[PENDING_COMPONENT_FAILURE_KEY] = detail
    session_state[PREVIOUS_PLAYING_KEY] = False


def _apply_pending_component_failure(session_state: dict[str, Any]) -> str | None:
    detail = session_state.pop(PENDING_COMPONENT_FAILURE_KEY, None)
    if detail is not None:
        session_state[MASTER_KEY] = False
    return detail


def _sync_source_lifecycle(
    source: BrowserMediaSource,
    *,
    requested: bool,
    playing: bool,
) -> None:
    if requested and playing:
        source.start()
    elif requested:
        source.handle_disconnect()
    else:
        source.stop(reason="master switch off")


def _connection_label(requested: bool, playing: bool) -> str:
    if playing:
        return "connected / playing"
    if requested:
        return "requested / negotiating"
    return "off / disconnected"


@st.fragment(run_every=1.0)
def _render_runtime_stats(
    source: BrowserMediaSource,
    *,
    requested: bool,
    playing: bool,
) -> None:
    _sync_source_lifecycle(source, requested=requested, playing=playing)
    st.session_state[PREVIOUS_PLAYING_KEY] = playing

    stats = source.stats()
    st.caption(f"Transport state: {_connection_label(requested, playing)}")
    first, second, third, fourth = st.columns(4)
    first.metric("Video FPS", f"{stats.video_fps:.1f}")
    second.metric("Audio chunks/s", f"{stats.audio_chunks_per_second:.1f}")
    third.metric("Video queue", stats.video_queue_depth)
    fourth.metric("Audio queue", stats.audio_queue_depth)

    first, second, third, fourth = st.columns(4)
    first.metric("Video drops", stats.video_drops)
    second.metric("Audio drops", stats.audio_drops)
    third.metric("Audio overruns", stats.audio_overruns)
    fourth.metric("Cleanup", stats.cleanup_state)

    st.code(
        "\n".join(
            (
                f"last_video_timestamp={stats.last_video_timestamp}",
                f"last_audio_timestamp={stats.last_audio_timestamp}",
                f"source_running={stats.is_running}",
            )
        ),
        language="text",
    )


def main() -> None:
    st.set_page_config(page_title="Browser Media Transport Probe", layout="wide")
    st.title("Browser video/audio transport probe")
    st.caption(
        "Transport-only gate: callbacks convert, timestamp, and push to bounded "
        "queues. No sensing, STT, LLM, or raw-media persistence runs here."
    )

    source = _source()
    pending_failure = _apply_pending_component_failure(st.session_state)
    if MASTER_KEY not in st.session_state:
        st.session_state[MASTER_KEY] = False
    requested = st.toggle(
        "Browser camera + microphone",
        key=MASTER_KEY,
        on_change=_master_changed,
    )
    if pending_failure is not None:
        st.error(f"WebRTC component error; source cleaned up: {pending_failure}")

    if not requested:
        _render_runtime_stats(source, requested=False, playing=False)
        return

    try:
        context = webrtc_streamer(
            key="attentive-slides-media-transport",
            mode=WebRtcMode.SENDRECV,
            rtc_configuration={
                "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
            },
            media_stream_constraints={"video": True, "audio": True},
            desired_playing_state=requested,
            video_frame_callback=source.video_frame_callback,
            audio_frame_callback=source.audio_frame_callback,
            on_video_ended=source.handle_disconnect,
            on_audio_ended=source.handle_disconnect,
            async_processing=False,
            sendback_video=True,
            sendback_audio=False,
            media_toggle_controls=False,
            video_html_attrs={"autoPlay": True, "controls": False, "muted": True},
        )
    except Exception as exc:  # pragma: no cover - real component/runtime path
        _sync_component_failure(source, st.session_state, str(exc))
        st.rerun()

    playing = bool(context.state.playing)
    _render_runtime_stats(source, requested=requested, playing=playing)
    if not playing:
        st.warning(
            "Waiting for browser permission or WebRTC negotiation. The media source "
            "remains stopped until both tracks are playing."
        )


if __name__ == "__main__":
    main()
