"""Live Streamlit surface for the continuous AttentiveSlides runtime."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from modules.audio.faster_whisper_transcriber import FasterWhisperTranscriber
from modules.audio.streaming_vad import default_vad_backend
from modules.audio.voice_turn_detector import VoiceTurnDetector
from modules.media import BrowserMediaSource
from modules.logging.interaction_logger import InteractionLogger
from modules.system.audio_worker import AudioWorker
from modules.system.controller import SystemController
from modules.system.live_tutor_adapter import LiveTelemetryLogger, LiveTutorAdapter
from modules.system.live_turn_runner import LiveTurnRunner
from modules.system.live_view_model import LiveViewModel
from modules.system.real_slide_provider import RealSlideProvider
from modules.system.sensing_snapshot_store import SensingSnapshotStore
from modules.system.sensing_worker import SensingWorker
from modules.system.turn_context import TurnContextCollector


@st.cache_resource
def _live_runtime() -> LiveViewModel:
    media_source = BrowserMediaSource()
    provider = RealSlideProvider()
    snapshots = SensingSnapshotStore()
    sensing_worker = SensingWorker(
        media_source=media_source,
        slide_provider=provider,
        snapshot_store=snapshots,
    )
    transcriber = FasterWhisperTranscriber()
    audio_worker = AudioWorker(
        media_source=media_source,
        detector=VoiceTurnDetector(default_vad_backend()),
        transcribe=transcriber.transcribe,
    )
    collector = TurnContextCollector(
        slide_provider=provider,
        snapshot_store=snapshots,
    )
    tutor_adapter = LiveTutorAdapter()
    runner = LiveTurnRunner(
        slide_provider=provider,
        context_collector=collector,
        tutor=tutor_adapter,
        logger=LiveTelemetryLogger(
            InteractionLogger("data/logs/live_interactions.jsonl"),
            tutor_adapter,
        ),
    )
    controller = SystemController(
        media_source=media_source,
        sensing_worker=sensing_worker,
        audio_worker=audio_worker,
        context_collector=collector,
        turn_runner=runner,
    )
    return LiveViewModel(
        controller=controller,
        media_source=media_source,
        slide_provider=provider,
        snapshot_store=snapshots,
        tutor_adapter=tutor_adapter,
    )


def _load_uploaded_deck(runtime: LiveViewModel, uploaded: Any) -> str | None:
    if uploaded is None:
        return None
    payload = uploaded.getvalue()
    signature = hashlib.sha256(payload).hexdigest()
    if st.session_state.get("live_deck_signature") == signature:
        return None
    deck_id = runtime.load_deck(payload, filename=uploaded.name)
    st.session_state.live_deck_signature = signature
    return deck_id


def next_master_switch_state(current_state: bool, button_pressed: bool) -> bool:
    """Keep the media lifecycle switch stable between Streamlit reruns."""

    return not current_state if button_pressed else current_state


def _render_media(runtime: LiveViewModel, master_switch: bool, deck_loaded: bool) -> None:
    if not master_switch or not deck_loaded:
        if runtime.is_running:
            runtime.stop(reason="master switch off")
        return
    try:
        context = webrtc_streamer(
            key="attentive-slides-live-media",
            mode=WebRtcMode.SENDRECV,
            rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
            media_stream_constraints={"video": True, "audio": True},
            desired_playing_state=master_switch,
            video_frame_callback=runtime.media_source.video_frame_callback,
            audio_frame_callback=runtime.media_source.audio_frame_callback,
            on_video_ended=runtime.handle_disconnect,
            on_audio_ended=runtime.handle_disconnect,
            async_processing=False,
            sendback_video=True,
            sendback_audio=False,
            media_toggle_controls=False,
            video_html_attrs={"autoPlay": True, "controls": False, "muted": True},
        )
    except Exception as exc:  # pragma: no cover - browser component path
        runtime.handle_disconnect()
        st.error(f"Browser media component error: {exc}")
        return

    if context.state.playing:
        runtime.start()
    elif runtime.is_running:
        runtime.handle_disconnect()
    else:
        st.info("Waiting for browser camera/microphone permission and media negotiation.")


def build_aoi_overlay(
    image: Image.Image,
    aois: list[dict[str, Any]],
    *,
    highlighted_aoi_id: str | None,
) -> Image.Image:
    """Draw canonical AOI bounds without changing the persisted slide image."""

    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    width, height = overlay.size
    for aoi in aois:
        bbox = aoi.get("bbox", [])
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = (round(float(value) * axis) for value, axis in zip(bbox, (width, height, width, height)))
        highlighted = aoi.get("aoi_id") == highlighted_aoi_id
        draw.rectangle((x1, y1, x2, y2), outline="#e4572e" if highlighted else "#2b6cb0", width=3)
    return overlay


def _render_slide(snapshot: dict[str, Any]) -> None:
    st.subheader("Slide and AOI overlay")
    image_path = snapshot["slide"]["image_path"]
    if image_path:
        with Image.open(image_path) as image:
            overlay = build_aoi_overlay(
                image,
                snapshot["slide"]["aois"],
                highlighted_aoi_id=(
                    snapshot["interaction"]["highlighted_aoi_id"]
                    if snapshot["interaction"] is not None
                    else None
                ),
            )
        st.image(overlay, caption=f"Slide {snapshot['slide']['id']} with canonical AOI overlay")
    else:
        st.info("Upload a PDF deck to render the current slide.")
    if snapshot["slide"]["aois"]:
        st.dataframe(snapshot["slide"]["aois"], hide_index=True, use_container_width=True)


def _render_confirmation(runtime: LiveViewModel, snapshot: dict[str, Any]) -> None:
    st.subheader("Target confirmation")
    confirmation = snapshot["confirmation"]
    if not confirmation["pending"]:
        st.caption("No pending target confirmation.")
        return
    candidates = confirmation["candidates"]
    if not candidates:
        st.warning("No candidate AOIs are available; select a slide region after fresh evidence arrives.")
        return
    labels = [f"{item['name']} ({item['aoi_id']})" for item in candidates]
    selected = st.selectbox("Confirm or correct the intended target", labels, key="live_confirmation_target")
    selected_id = candidates[labels.index(selected)]["aoi_id"]
    if st.button("Confirm selected target", type="primary"):
        runtime.confirm(confirmation["query_id"], selected_id)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="AttentiveSlides Live", layout="wide")
    st.title("AttentiveSlides Live")
    st.caption(
        "Observable signals only: gaze is coarse AOI evidence, not eye tracking; "
        "no cognition or emotion claim is shown."
    )
    runtime = _live_runtime()

    with st.sidebar:
        st.subheader("PDF deck")
        uploaded = st.file_uploader("PDF deck", type=["pdf"])
        try:
            loaded = _load_uploaded_deck(runtime, uploaded)
        except Exception as exc:
            st.error(f"Deck load failed: {exc}")
            loaded = None
        if loaded:
            st.success(f"Loaded deck {loaded}.")
        snapshot = runtime.snapshot()
        use_grounded = st.toggle(
            "Use grounded API tutor",
            value=snapshot["tutor"]["selection"] == "grounded",
            key="live_grounded_tutor",
        )
        if use_grounded != (snapshot["tutor"]["selection"] == "grounded"):
            runtime.configure_grounded_tutor(use_grounded)
            snapshot = runtime.snapshot()
        if snapshot["tutor"]["configuration_error"]:
            st.error(f"Grounded tutor unavailable; using deterministic fallback: {snapshot['tutor']['configuration_error']}")
        st.caption(
            f"Tutor: {snapshot['tutor']['selection']} · "
            f"{snapshot['tutor']['provider']} / {snapshot['tutor']['model']}"
        )
        current_master_switch = bool(st.session_state.get("live_master_switch", False))
        master_switch = next_master_switch_state(
            current_master_switch,
            st.button(
                "Master switch: Stop live runtime"
                if current_master_switch
                else "Master switch: Start live runtime",
                key="live_master_switch_button",
                type="secondary" if current_master_switch else "primary",
            ),
        )
        st.session_state.live_master_switch = master_switch
        if snapshot["deck"]["loaded"]:
            selected_slide = st.number_input(
                "Slide",
                min_value=1,
                max_value=snapshot["deck"]["page_count"],
                value=snapshot["slide"]["id"],
                step=1,
            )
            if selected_slide != snapshot["slide"]["id"]:
                runtime.set_slide(int(selected_slide))

    _render_media(runtime, master_switch, runtime.snapshot()["deck"]["loaded"])
    runtime.poll()
    snapshot = runtime.snapshot()

    status_left, status_right = st.columns(2)
    with status_left:
        st.subheader("Transport state")
        st.json(snapshot["transport"])
        st.caption(f"Runtime state: {snapshot['runtime']['state']} — {snapshot['runtime']['status_copy']}")
    with status_right:
        st.subheader("Latest gaze evidence")
        st.json(snapshot["gaze"])
        st.caption("Camera preview is provided by the media component and is distinct from derived gaze evidence.")

    left, right = st.columns((1.15, 0.85))
    with left:
        _render_slide(snapshot)
    with right:
        st.subheader("Turn transcript and timing")
        st.json(snapshot["turn"])
        _render_confirmation(runtime, snapshot)
        st.subheader("Grounded tutor response")
        if snapshot["interaction"] is None:
            st.caption("No completed tutor response yet.")
        else:
            st.json(snapshot["interaction"]["response"])
        if snapshot["grounded_xai"] is not None:
            st.json(snapshot["grounded_xai"])

    with st.expander("Developer transport trace", expanded=False):
        st.json(snapshot["developer"])
    st.caption(
        "Manual transcript/file-audio regression workflows remain available in the existing demo apps. "
        "For AutoDL SSH forwarding, use the documented same-origin single-port fallback when WebRTC cannot play."
    )


if __name__ == "__main__":
    main()
