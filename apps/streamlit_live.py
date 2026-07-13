"""Live Streamlit surface for the continuous AttentiveSlides runtime."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from html import escape
from io import BytesIO
import os
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import streamlit as st

from modules.audio.faster_whisper_transcriber import FasterWhisperTranscriber
from modules.audio.streaming_vad import default_vad_backend
from modules.audio.transcriber import TranscriptionConfig
from modules.audio.voice_turn_detector import VoiceTurnDetector
from modules.media import BrowserMediaSource
from modules.media.live_ingress_service import LiveIngressService
from modules.media.single_port_transport import FallbackMediaIngress
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


@dataclass(frozen=True)
class LiveResources:
    runtime: LiveViewModel
    ingress: FallbackMediaIngress
    service: LiveIngressService


def build_live_resources(*, start_ingress: bool = True) -> LiveResources:
    media_source = BrowserMediaSource()
    provider = RealSlideProvider()
    snapshots = SensingSnapshotStore()
    sensing_worker = SensingWorker(
        media_source=media_source,
        slide_provider=provider,
        snapshot_store=snapshots,
    )
    transcriber = FasterWhisperTranscriber(
        TranscriptionConfig(
            engine="faster_whisper",
            model_size=os.environ.get("ATTENTIVE_WHISPER_MODEL", "small"),
        )
    )
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
    runtime = LiveViewModel(
        controller=controller,
        media_source=media_source,
        slide_provider=provider,
        snapshot_store=snapshots,
        tutor_adapter=tutor_adapter,
    )
    ingress = FallbackMediaIngress(
        media_source,
        start_armed=False,
        coordinated_activation=True,
        media_stale_after_seconds=2.0,
        inactive_after_seconds=3.0,
    )
    capture_html = (
        REPOSITORY_ROOT / "modules/media/live_capture_component/index.html"
    ).read_text(encoding="utf-8")
    service = LiveIngressService(
        runtime=runtime,
        source=media_source,
        ingress=ingress,
        capture_html=capture_html,
    )
    if start_ingress:
        service.ensure_started()
    return LiveResources(runtime=runtime, ingress=ingress, service=service)


@st.cache_resource
def _live_resources() -> LiveResources:
    return build_live_resources()


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


def render_capture_component(*, embed: Any = st.iframe) -> None:
    embed("/capture", height=340)


def poll_live_runtime(runtime: LiveViewModel) -> None:
    runtime.poll()


def _render_media(resources: LiveResources, master_switch: bool, deck_loaded: bool) -> None:
    enabled = bool(master_switch and deck_loaded)
    resources.service.set_master_enabled(enabled)
    resources.service.reconcile_once()
    if enabled:
        render_capture_component()


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
    font_size = max(14, round(min(width, height) * 0.022))
    try:
        badge_font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except OSError:
        badge_font = ImageFont.load_default()
    for index, aoi in enumerate(aois, start=1):
        bbox = aoi.get("bbox", [])
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = (round(float(value) * axis) for value, axis in zip(bbox, (width, height, width, height)))
        highlighted = aoi.get("aoi_id") == highlighted_aoi_id
        color = "#e4572e" if highlighted else "#2b6cb0"
        draw.rectangle((x1, y1, x2, y2), outline=color, width=3)
        badge = str(index)
        left, top, right, bottom = badge_font.getbbox(badge)
        badge_width = right - left + 10
        badge_height = bottom - top + 8
        badge_x = max(1, min(x1 + 2, width - badge_width - 1))
        badge_y = max(1, min(y1 + 2, height - badge_height - 1))
        draw.rounded_rectangle(
            (badge_x, badge_y, badge_x + badge_width, badge_y + badge_height),
            radius=3,
            fill=color,
        )
        draw.text(
            (badge_x + 5, badge_y + 4 - top),
            badge,
            fill="white",
            font=badge_font,
        )
    return overlay


def build_aoi_display_label(aoi: dict[str, Any], index: int) -> str:
    """Return the slide badge number plus a useful PDF-derived AOI description."""

    aoi_id = str(aoi.get("aoi_id") or "unknown_aoi")
    kind = str(aoi.get("type") or "region").replace("_", " ")
    text = " ".join(str(aoi.get("text") or "").split())
    if not text:
        text = "Whole slide" if aoi_id == "whole_slide" else aoi_id.replace("_", " ")
    excerpt = text if len(text) <= 72 else f"{text[:69].rstrip()}..."
    return f"{index} · {excerpt} [{kind}] ({aoi_id})"


def build_slide_image_html(image: Image.Image, *, caption: str) -> str:
    renderable = image.convert("RGB")
    if renderable.width > 1600:
        height = max(1, round(renderable.height * 1600 / renderable.width))
        renderable = renderable.resize((1600, height), Image.Resampling.LANCZOS)
    output = BytesIO()
    renderable.save(output, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    safe_caption = escape(caption, quote=True)
    return (
        '<figure style="margin:0">'
        f'<img src="data:image/jpeg;base64,{encoded}" alt="{safe_caption}" '
        'style="display:block;width:100%;height:auto;border-radius:0.35rem">'
        f'<figcaption style="margin-top:0.4rem">{safe_caption}</figcaption>'
        "</figure>"
    )


def _render_slide_panel(resources: LiveResources) -> None:
    snapshot = resources.runtime.snapshot()
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
        st.markdown(
            build_slide_image_html(
                overlay,
                caption=f"Slide {snapshot['slide']['id']} with canonical AOI overlay",
            ),
            unsafe_allow_html=True,
        )
        st.caption("AOI numbers on the slide match the Target confirmation choices below.")
    else:
        st.info("Upload a PDF deck to render the current slide.")
    if snapshot["slide"]["aois"]:
        with st.expander("Canonical AOI details", expanded=False):
            for index, aoi in enumerate(snapshot["slide"]["aois"], start=1):
                st.write(build_aoi_display_label(aoi, index))


def render_live_workspace(
    resources: LiveResources,
    *,
    master_switch: bool,
    deck_loaded: bool,
    columns: Any = st.columns,
) -> None:
    capture_column, slide_column = columns((0.42, 0.58), gap="large")
    with capture_column:
        _render_media(resources, master_switch, deck_loaded)
    with slide_column:
        _render_slide_panel(resources)


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
    slide_aois = snapshot["slide"]["aois"]
    canonical = {str(aoi["aoi_id"]): (index, aoi) for index, aoi in enumerate(slide_aois, start=1)}
    labels = []
    for item in candidates:
        aoi_id = str(item["aoi_id"])
        index, aoi = canonical.get(aoi_id, (len(slide_aois) + 1, item))
        labels.append(build_aoi_display_label(aoi, index))
    selected = st.selectbox("Confirm or correct the intended target", labels, key="live_confirmation_target")
    selected_id = candidates[labels.index(selected)]["aoi_id"]
    if st.button("Confirm selected target", type="primary"):
        runtime.confirm(confirmation["query_id"], selected_id)
        st.rerun()


@st.fragment(run_every=0.5)
def _render_periodic(resources: LiveResources) -> None:
    runtime = resources.runtime
    poll_live_runtime(runtime)
    snapshot = runtime.snapshot()
    transport = dict(snapshot["transport"])
    transport["ingress"] = resources.service.stats_payload()

    status_left, status_right = st.columns(2)
    with status_left:
        st.subheader("Transport state")
        st.json(transport)
        st.caption(
            f"Runtime state: {snapshot['runtime']['state']} — "
            f"{snapshot['runtime']['status_copy']}"
        )
    with status_right:
        st.subheader("Latest gaze evidence")
        st.json(snapshot["gaze"])
        st.caption(
            "Camera preview is provided by the media component and is distinct "
            "from derived gaze evidence."
        )

    turn_column, response_column = st.columns((0.48, 0.52))
    with turn_column:
        st.subheader("Turn transcript and timing")
        st.json(snapshot["turn"])
        _render_confirmation(runtime, snapshot)
    with response_column:
        st.subheader("Grounded tutor response")
        if snapshot["interaction"] is None:
            st.caption("No completed tutor response yet.")
        else:
            st.json(snapshot["interaction"]["response"])
        if snapshot["grounded_xai"] is not None:
            st.json(snapshot["grounded_xai"])

    with st.expander("Developer transport trace", expanded=False):
        st.json(snapshot["developer"])


def main() -> None:
    st.set_page_config(page_title="AttentiveSlides Live", layout="wide")
    st.title("AttentiveSlides Live")
    st.caption(
        "Observable signals only: gaze is coarse AOI evidence, not eye tracking; "
        "no cognition or emotion claim is shown."
    )
    resources = _live_resources()
    runtime = resources.runtime

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

    render_live_workspace(
        resources,
        master_switch=master_switch,
        deck_loaded=runtime.snapshot()["deck"]["loaded"],
    )
    _render_periodic(resources)
    st.caption(
        "Manual transcript/file-audio regression workflows remain available in the existing demo apps. "
        "For AutoDL SSH forwarding, launch the formal same-origin single-port HTTP media path."
    )


if __name__ == "__main__":
    main()
