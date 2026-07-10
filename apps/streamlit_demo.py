"""Streamlit demo for the mock-driven AttentiveSlides Member 3/4 pipeline."""

from __future__ import annotations

from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from modules.audio.model_policy import transcription_config_for_profile
from modules.common.schemas import GazePrediction, LearningState
from modules.interaction.speech_to_text import transcribe_audio
from modules.logging.interaction_logger import InteractionLogger
from modules.system.demo_view_model import (
    build_interaction_view_model,
    run_scenario_turn,
    scenario_to_dict,
)
from modules.system.pipeline import load_interaction_log
from modules.system.scenarios import InteractionScenario, load_scenarios


LOG_PATH = Path("data/logs/streamlit_demo_interactions.jsonl")
RECORDED_AUDIO_DIR = Path("data/audio_samples/recorded")
GAZE_GRIDS = [
    "top_left",
    "top_center",
    "top_right",
    "middle_left",
    "middle_center",
    "middle_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
]


def main() -> None:
    st.set_page_config(page_title="AttentiveSlides Demo", page_icon="AS", layout="wide")
    _inject_css()

    scenarios = _load_scenarios()
    scenario = _select_scenario(scenarios)
    _ensure_session_state(scenario)
    edited_scenario = _sidebar_controls(scenario)

    st.html(_app_header_html())

    result = run_scenario_turn(edited_scenario, confirmed_aoi_id=st.session_state.confirmed_aoi_id)
    view_model = build_interaction_view_model(result, edited_scenario)

    primary_left, primary_right = st.columns([1.65, 0.9], gap="large")
    with primary_left:
        st.html(_section_heading_html("Learning surface", "Slide / Learning Surface"))
        st.html(_slide_html(view_model))

    with primary_right:
        _render_response(view_model)
        _render_confirmation(view_model, edited_scenario)

    st.html(_section_heading_html("Grounding trace", "Signals used for this turn"))
    _render_evidence(view_model, edited_scenario)

    st.divider()
    st.html(_section_heading_html("Developer trace", "Evaluation and recent JSONL log"))
    _render_evaluation(view_model)
    _render_log_viewer()


@st.cache_data
def _load_scenarios() -> list[InteractionScenario]:
    return load_scenarios()


def _select_scenario(scenarios: list[InteractionScenario]) -> InteractionScenario:
    names = [scenario.name for scenario in scenarios]
    selected = st.sidebar.selectbox("Scenario", names, index=0)
    return scenarios[names.index(selected)]


def _ensure_session_state(scenario: InteractionScenario) -> None:
    if "confirmed_aoi_id" not in st.session_state:
        st.session_state.confirmed_aoi_id = None
    if "active_scenario_name" not in st.session_state:
        st.session_state.active_scenario_name = scenario.name
    if "learner_utterance" not in st.session_state:
        st.session_state.learner_utterance = scenario.transcript
    if "latest_audio_path" not in st.session_state:
        st.session_state.latest_audio_path = None
    if "audio_transcript_text" not in st.session_state:
        st.session_state.audio_transcript_text = ""
    if "audio_error" not in st.session_state:
        st.session_state.audio_error = None
    if "audio_profile" not in st.session_state:
        st.session_state.audio_profile = "balanced"

    if st.session_state.active_scenario_name != scenario.name:
        st.session_state.active_scenario_name = scenario.name
        st.session_state.confirmed_aoi_id = None
        st.session_state.learner_utterance = scenario.transcript


def _sidebar_controls(scenario: InteractionScenario) -> InteractionScenario:
    st.sidebar.header("Input desk")
    _render_audio_input_controls()
    transcript = st.sidebar.text_area("Learner utterance", height=96, key="learner_utterance")

    aoi_ids = [aoi["aoi_id"] for aoi in _scenario_aois()]
    predicted_options = ["None", *aoi_ids]
    default_predicted = scenario.gaze_prediction.predicted_aoi_id or "None"
    if default_predicted not in predicted_options:
        default_predicted = "None"

    with st.sidebar.expander("Gaze hint", expanded=True):
        gaze_grid = st.selectbox(
            "Gaze grid",
            GAZE_GRIDS,
            index=GAZE_GRIDS.index(scenario.gaze_prediction.gaze_grid)
            if scenario.gaze_prediction.gaze_grid in GAZE_GRIDS
            else 0,
        )
        predicted = st.selectbox(
            "Gaze-indicated region",
            predicted_options,
            index=predicted_options.index(default_predicted),
        )
        confidence = st.slider("Confidence", 0.0, 1.0, float(scenario.gaze_prediction.confidence), 0.01)
        stable_duration = st.slider(
            "Stable for",
            0.0,
            5.0,
            float(scenario.gaze_prediction.stable_duration_sec),
            0.1,
        )

    with st.sidebar.expander("Observable learning signals", expanded=False):
        screen_facing_score = st.slider(
            "Screen-facing score",
            0.0,
            1.0,
            float(scenario.learning_state.screen_facing_score),
            0.01,
        )
        fatigue_signal_score = st.slider(
            "Fatigue signal score",
            0.0,
            1.0,
            float(scenario.learning_state.fatigue_signal_score),
            0.01,
        )
        yawn_count = st.number_input(
            "Yawn count, last 3 min",
            min_value=0,
            max_value=20,
            value=int(scenario.learning_state.yawn_count_last_3min),
            step=1,
        )
        eyes_closed = st.checkbox("Eyes closed", value=scenario.learning_state.eyes_closed)
        head_down = st.checkbox("Head down", value=scenario.learning_state.head_down)
        possible_review_needed = st.checkbox(
            "Possible review needed",
            value=scenario.learning_state.possible_review_needed,
        )

    if st.sidebar.button("Clear confirmation", use_container_width=True):
        st.session_state.confirmed_aoi_id = None

    gaze_prediction = GazePrediction(
        slide_id=scenario.gaze_prediction.slide_id,
        gaze_grid=gaze_grid,
        predicted_aoi_id=None if predicted == "None" else predicted,
        confidence=confidence,
        stable_duration_sec=stable_duration,
        alternative_targets=list(scenario.gaze_prediction.alternative_targets),
    )
    learning_state = LearningState(
        face_detected=scenario.learning_state.face_detected,
        screen_facing_score=screen_facing_score,
        yawn_detected=yawn_count > 0,
        yawn_count_last_3min=int(yawn_count),
        eyes_closed=eyes_closed,
        eye_closure_duration_sec=scenario.learning_state.eye_closure_duration_sec,
        head_down=head_down,
        fatigue_signal_score=fatigue_signal_score,
        possible_review_needed=possible_review_needed,
    )
    return replace(
        scenario,
        transcript=transcript,
        gaze_prediction=gaze_prediction,
        learning_state=learning_state,
    )


def _render_audio_input_controls() -> None:
    mode = st.sidebar.radio(
        "Input mode",
        ["Mock scenario text", "Audio file upload", "Recorded wav path"],
        key="audio_input_mode",
    )
    selected_label = st.sidebar.selectbox(
        "STT profile",
        _audio_profile_options(),
        index=0,
        key="audio_profile_label",
    )
    profile = _profile_from_audio_label(selected_label)
    st.session_state.audio_profile = profile

    uploaded_audio = None
    recorded_path = ""
    if mode == "Audio file upload":
        with st.sidebar:
            if hasattr(st, "audio_input"):
                uploaded_audio = st.audio_input("Record command")
            if uploaded_audio is None:
                uploaded_audio = st.file_uploader("Upload audio file", type=["wav", "mp3", "m4a"])
    elif mode == "Recorded wav path":
        recorded_path = st.sidebar.text_input(
            "Audio path",
            value=str(st.session_state.latest_audio_path or "data/audio_samples/recorded/latest.wav"),
        )

    if mode != "Mock scenario text" and st.sidebar.button("Transcribe audio", use_container_width=True):
        try:
            audio_path = _audio_path_from_input(uploaded_audio, recorded_path)
            transcript_text = _transcribe_audio_for_ui(audio_path, profile)
        except Exception as exc:  # pragma: no cover - Streamlit surface for runtime model/device errors
            st.session_state.audio_error = str(exc)
        else:
            st.session_state.latest_audio_path = audio_path
            st.session_state.audio_transcript_text = transcript_text
            st.session_state.learner_utterance = transcript_text
            st.session_state.confirmed_aoi_id = None
            st.session_state.audio_error = None

    if st.session_state.audio_error:
        st.sidebar.error(
            f"{st.session_state.audio_error} "
            "Try the balanced profile, cpu fallback, or edit the transcript manually."
        )
    if st.session_state.latest_audio_path:
        st.sidebar.caption(f"Latest audio: {st.session_state.latest_audio_path}")


def _audio_path_from_input(uploaded_audio: Any, recorded_path: str) -> str:
    if uploaded_audio is not None:
        return _save_uploaded_audio(uploaded_audio)
    if recorded_path.strip():
        return recorded_path.strip()
    raise ValueError("Record, upload, or provide a wav path before transcription.")


def _audio_profile_options() -> list[str]:
    return ["balanced (medium)", "accurate (large-v3)", "fast (small)", "cpu fallback"]


def _profile_from_audio_label(label: str) -> str:
    mapping = {
        "balanced (medium)": "balanced",
        "accurate (large-v3)": "accurate",
        "fast (small)": "fast",
        "cpu fallback": "cpu",
    }
    return mapping[label]


def _save_uploaded_audio(uploaded_audio: Any, output_dir: Path = RECORDED_AUDIO_DIR) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(getattr(uploaded_audio, "name", "latest.wav")).name or "latest.wav"
    output_path = output_dir / filename
    output_path.write_bytes(bytes(uploaded_audio.getbuffer()))
    return output_path.as_posix()


def _transcribe_audio_for_ui(audio_path: str, profile: str) -> str:
    config = transcription_config_for_profile(profile)
    transcript = transcribe_audio(audio_path, config)
    return transcript.text


def _scenario_aois() -> list[dict[str, Any]]:
    scenario = _load_scenarios()[0]
    result = run_scenario_turn(scenario)
    return build_interaction_view_model(result, scenario)["aois"]


def _render_confirmation(view_model: dict[str, Any], scenario: InteractionScenario) -> None:
    st.html(_section_heading_html("Confirmation", "Confirm before answering"))
    if not view_model["pending_confirmation"]:
        confirmed = view_model["actual"].get("confirmed_aoi_id") or view_model["highlighted_aoi_id"]
        st.html(
            _confirmation_status_html(
                pending_confirmation=False,
                target_name=_target_name_for_id(view_model, confirmed),
                target_id=confirmed,
            )
        )
        if st.button("Reopen confirmation", use_container_width=True):
            st.session_state.confirmed_aoi_id = None
            st.rerun()
        return

    options = view_model["confirmation_options"]
    labels = [_format_option(option) for option in options]
    preferred_aoi_id = scenario.gaze_prediction.predicted_aoi_id or view_model["highlighted_aoi_id"]
    default_index = _default_confirmation_index(options, preferred_aoi_id)
    suggested = options[default_index]["aoi_id"] if options else view_model["highlighted_aoi_id"]
    selected_label = (
        st.selectbox("Choose another region", labels, index=default_index) if labels else None
    )
    selected = options[labels.index(selected_label)]["aoi_id"] if selected_label else suggested
    target_name = _target_name_for_id(view_model, selected)
    st.html(
        _confirmation_status_html(
            pending_confirmation=True,
            target_name=target_name,
            target_id=selected,
        )
    )

    action_col, correction_col = st.columns([1, 1], gap="medium")
    if action_col.button(f"Confirm {target_name}", type="primary", use_container_width=True):
        st.session_state.confirmed_aoi_id = selected
        st.rerun()
    if scenario.confirmed_aoi_id and correction_col.button("Use fixture correction", use_container_width=True):
        st.session_state.confirmed_aoi_id = scenario.confirmed_aoi_id
        st.rerun()


def _render_response(view_model: dict[str, Any]) -> None:
    st.html(_section_heading_html("Tutor note", "Answer draft"))
    response = view_model["response"]
    if response["answer"] is None:
        st.html(
            """
            <div class="as-note as-note-pending">
              Waiting for target confirmation before giving an AOI-specific answer.
            </div>
            """
        )
    else:
        st.html('<div class="as-note-label">Grounded answer</div>')
        st.markdown(response["answer"])
    if response.get("active_recall_question"):
        st.markdown(f"**Active recall:** {response['active_recall_question']}")
    if response.get("adaptive_suggestion"):
        st.markdown(f"**Adaptive suggestion:** {response['adaptive_suggestion']}")


def _render_evidence(view_model: dict[str, Any], scenario: InteractionScenario) -> None:
    st.html('<div class="as-grounding-panel" aria-hidden="true"></div>')
    summary_col, detail_col = st.columns([0.82, 1.18], gap="large")
    with summary_col:
        st.html(_grounding_chips_html(view_model, scenario))
        if st.button("Append current turn to JSONL log", use_container_width=True):
            InteractionLogger(LOG_PATH).log_interaction(view_model["log_event"])
            st.toast("Logged current interaction turn.")
    with detail_col:
        with st.expander("Evidence details", expanded=False):
            for item in view_model["evidence"]:
                st.write(f"- {item}")
        with st.expander("Learning-state signals", expanded=False):
            st.json(view_model["learning_state_summary"])
        with st.expander("Scenario fixture", expanded=False):
            st.json(scenario_to_dict(scenario))


def _render_evaluation(view_model: dict[str, Any]) -> None:
    st.markdown("#### Expected vs Actual")
    rows = [
        {
            "field": field,
            "expected": _display_value(values["expected"]),
            "actual": _display_value(values["actual"]),
            "matches": values["matches"],
        }
        for field, values in view_model["expected_actual"].items()
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_log_viewer() -> None:
    st.markdown("#### Recent JSONL Log")
    log_rows = load_interaction_log(LOG_PATH)
    if not log_rows:
        st.caption("No Streamlit demo log has been written in this session.")
        return
    st.dataframe(log_rows[-10:], hide_index=True, use_container_width=True)


def _slide_html(view_model: dict[str, Any]) -> str:
    boxes = "\n".join(_aoi_box_html(aoi) for aoi in view_model["aois"] if aoi["aoi_id"] != "whole_slide")
    return f"""
    <div class="as-slide-shell">
      <div class="as-slide-meta">
        <span>slide_05 · SHAP explanation · AOI manifest</span>
        <span class="as-slide-legend" aria-label="AOI state legend">
          <span class="as-legend-item as-legend-candidate">candidate</span>
          <span class="as-legend-item as-legend-confirmed">confirmed</span>
          <span class="as-legend-item as-legend-available">available region</span>
        </span>
      </div>
      <div class="as-slide">
        <div class="as-slide-title">SHAP Values for Local Model Explanation</div>
        <div class="as-slide-subtitle">Mock slide 5 · AOI boxes use normalized manifest coordinates</div>
        {boxes}
      </div>
    </div>
    """


def _aoi_box_html(aoi: dict[str, Any]) -> str:
    x1, y1, x2, y2 = aoi["bbox"]
    classes = ["as-aoi"]
    state = "available region"
    if aoi["is_highlighted"]:
        classes.append("is-highlighted")
        state = "confirmed"
    elif aoi["is_candidate"]:
        classes.append("is-candidate")
        state = "candidate"
    style = (
        f"left:{x1 * 100:.2f}%;top:{y1 * 100:.2f}%;"
        f"width:{(x2 - x1) * 100:.2f}%;height:{(y2 - y1) * 100:.2f}%;"
    )
    label = escape(str(aoi.get("name") or aoi["aoi_id"]))
    text = escape(str(aoi.get("text") or ""))
    state_label = escape(state)
    return f"""
    <div class="{' '.join(classes)}" style="{style}" data-state="{state_label}">
      <div class="as-aoi-state">{state_label}</div>
      <div class="as-aoi-label">{label}</div>
      <div class="as-aoi-text">{text}</div>
    </div>
    """


def _app_header_html() -> str:
    return """
    <header class="as-app-header">
      <h1>AttentiveSlides · A slide tutor that asks before it assumes.</h1>
      <p>Gaze gives a hint, voice gives intent, confirmation keeps the answer grounded.</p>
    </header>
    """


def _section_heading_html(kicker: str, title: str) -> str:
    return f"""
    <div class="as-section-heading">
      <div class="as-section-label">{escape(kicker.upper())}</div>
      <h2>{escape(title)}</h2>
    </div>
    """


def _confirmation_status_html(
    pending_confirmation: bool,
    target_name: str | None,
    target_id: str | None,
) -> str:
    target_name = target_name or "the selected region"
    target_id = target_id or "unresolved"
    if pending_confirmation:
        message = f"I think you mean the {target_name}. Please confirm before I answer."
        detail = "The tutor note stays gated until the learner confirms or corrects the region."
        state_class = "is-pending"
    else:
        message = f"Target confirmed · {target_id}"
        detail = f"The next answer is grounded to the {target_name}."
        state_class = "is-confirmed"
    return f"""
    <div class="as-confirmation {state_class}">
      <div class="as-confirmation-message">{escape(message)}</div>
      <div class="as-confirmation-detail">{escape(detail)}</div>
    </div>
    """


def _grounding_chips_html(view_model: dict[str, Any], scenario: InteractionScenario) -> str:
    gaze = scenario.gaze_prediction
    chips = [
        ("intent", view_model["intent"]),
        ("gaze hint", gaze.predicted_aoi_id or "None"),
        ("confidence", f"{gaze.confidence:.2f}"),
        ("strategy", view_model["actual"]["adaptive_strategy"]),
    ]
    chip_html = "\n".join(
        f'<span class="as-chip" aria-label="{escape(label)}: {escape(str(value))}">'
        f'<span>{escape(label)}:</span> <code>{escape(str(value))}</code></span>'
        for label, value in chips
    )
    return f'<div class="as-chip-row">{chip_html}</div>'


def _target_name_for_id(view_model: dict[str, Any], target_id: str | None) -> str:
    if not target_id:
        return "selected region"
    for aoi in view_model["aois"]:
        if aoi["aoi_id"] == target_id:
            return str(aoi.get("name") or target_id).strip().lower().replace("_", " ")
    for option in view_model["confirmation_options"]:
        if option["aoi_id"] == target_id:
            return str(option.get("name") or target_id).strip().lower().replace("_", " ")
    return str(target_id).strip().lower().replace("_", " ")


def _default_confirmation_index(options: list[dict[str, Any]], preferred_aoi_id: str | None) -> int:
    if not options:
        return 0
    if preferred_aoi_id:
        for index, option in enumerate(options):
            if option["aoi_id"] == preferred_aoi_id:
                return index
    for index, option in enumerate(options):
        if option["aoi_id"] != "whole_slide":
            return index
    return 0


def _format_option(option: dict[str, Any]) -> str:
    score = option.get("score")
    suffix = "" if score is None else f" · {float(score):.2f}"
    return f"{option.get('name') or option['aoi_id']} ({option['aoi_id']}){suffix}"


def _display_value(value: Any) -> str:
    if value is None:
        return "None"
    return str(value)


def _inject_css() -> None:
    st.html(
        """
        <style>
        :root {
            --as-bg: #F6F0E6;
            --as-sidebar: #EFE6D7;
            --as-surface: #FFFCF5;
            --as-slide: #FBFAF7;
            --as-text: #241F1A;
            --as-muted: #6F675D;
            --as-border: #DDD2C1;
            --as-border-strong: #CBBDA8;
            --as-candidate: #B86B3C;
            --as-candidate-text: #7B442B;
            --as-candidate-fill: rgba(184, 107, 60, 0.12);
            --as-confirmed: #6F8A6A;
            --as-confirmed-text: #405A3D;
            --as-confirmed-fill: rgba(111, 138, 106, 0.14);
            --as-info: #6E7F91;
            --as-danger: #A84A3F;
            --as-focus: #7E6A50;
            --as-radius: 8px;
        }

        .stApp {
            background: var(--as-bg);
            color: var(--as-text);
        }

        [data-testid="stHeader"] {
            background: rgba(246, 240, 230, 0.94);
            border-bottom: 1px solid rgba(221, 210, 193, 0.72);
        }

        .block-container {
            padding-top: 1.6rem;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
            padding-bottom: 3rem;
            max-width: min(1600px, calc(100vw - 3rem));
        }

        [data-testid="stSidebar"] {
            background: var(--as-sidebar);
            border-right: 1px solid var(--as-border);
        }

        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--as-text);
        }

        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        label,
        [data-testid="stWidgetLabel"] {
            color: var(--as-muted);
        }

        [data-baseweb="select"] > div,
        .stTextArea textarea,
        .stNumberInput input {
            background: var(--as-surface) !important;
            border-color: var(--as-border-strong) !important;
            color: var(--as-text) !important;
            border-radius: var(--as-radius) !important;
        }

        [data-baseweb="select"] span,
        [data-baseweb="select"] svg,
        .stTextArea textarea,
        .stNumberInput input {
            color: var(--as-text) !important;
        }

        div[data-testid="stButton"] > button,
        div[data-testid="stFormSubmitButton"] > button {
            min-height: 44px;
            border-radius: var(--as-radius);
            border: 1px solid var(--as-border-strong);
            color: var(--as-text);
            background: var(--as-surface);
            transition: border-color 180ms ease, background 180ms ease, transform 180ms ease;
        }

        div[data-testid="stButton"] > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {
            border-color: var(--as-focus);
            background: #FFF7E9;
            transform: translateY(-1px);
        }

        div[data-testid="stButton"] > button:focus-visible,
        div[data-testid="stFormSubmitButton"] > button:focus-visible,
        textarea:focus,
        input:focus {
            outline: 3px solid rgba(126, 106, 80, 0.28);
            outline-offset: 2px;
        }

        .as-app-header {
            padding: 0.2rem 0 1.15rem;
            border-bottom: 1px solid var(--as-border);
            margin-top: 2.2rem;
            margin-bottom: 1.25rem;
        }

        .as-kicker {
            color: var(--as-muted);
            font-size: 0.78rem;
            font-weight: 650;
            letter-spacing: 0;
            margin-bottom: 0.35rem;
        }

        .as-app-header h1 {
            color: var(--as-text);
            font-size: clamp(1.55rem, 2.6vw, 2.35rem);
            line-height: 1.12;
            letter-spacing: 0;
            margin: 0;
            max-width: none;
        }

        .as-app-header p {
            color: var(--as-muted);
            font-family: Georgia, "Times New Roman", serif;
            font-size: 1.02rem;
            line-height: 1.6;
            max-width: 680px;
            margin: 0.85rem 0 0;
        }

        .as-section-heading {
            margin: 0.35rem 0 0.75rem;
        }

        .as-section-heading h2 {
            color: var(--as-text);
            font-size: 1.08rem;
            line-height: 1.25;
            letter-spacing: 0;
            margin: 0.55rem 0 0;
        }

        .as-section-label {
            display: inline-flex;
            align-items: center;
            width: fit-content;
            border: 1px solid rgba(203, 189, 168, 0.82);
            border-radius: 999px;
            background: #FFF4DE;
            color: #9A6734;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 0.68rem;
            font-weight: 750;
            letter-spacing: 0.18em;
            line-height: 1;
            padding: 8px 18px;
        }

        .as-note {
            border: 1px solid var(--as-border);
            border-radius: var(--as-radius);
            background: var(--as-surface);
            color: var(--as-muted);
            line-height: 1.55;
            padding: 0.95rem 1rem;
            margin-bottom: 0.85rem;
        }

        .as-note-pending {
            border-color: var(--as-border-strong);
            background: #FFF8EA;
        }

        .as-note-label {
            color: var(--as-muted);
            font-size: 0.82rem;
            font-weight: 650;
            margin: 0 0 0.35rem;
        }

        .as-slide-shell {
            border: 1px solid var(--as-border);
            border-radius: var(--as-radius);
            background: var(--as-surface);
            padding: 0.85rem;
            box-shadow: 0 10px 26px rgba(65, 48, 30, 0.06);
        }

        .as-slide-meta {
            display: flex;
            justify-content: space-between;
            gap: 0.75rem;
            align-items: center;
            color: var(--as-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: 0.78rem;
            margin-bottom: 0.65rem;
        }

        .as-slide-legend {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: 0.4rem;
        }

        .as-legend-item {
            border: 1px solid var(--as-border);
            border-radius: 999px;
            padding: 0.15rem 0.45rem;
            background: #FFF9EF;
            white-space: nowrap;
        }

        .as-legend-candidate {
            border-color: rgba(184, 107, 60, 0.35);
            color: var(--as-candidate-text);
        }

        .as-legend-confirmed {
            border-color: rgba(111, 138, 106, 0.42);
            color: var(--as-confirmed-text);
        }

        .as-slide {
            position: relative;
            width: 100%;
            aspect-ratio: 16 / 9;
            min-height: clamp(390px, 36vw, 640px);
            border: 1px solid var(--as-border-strong);
            border-radius: 6px;
            background:
                linear-gradient(90deg, rgba(221, 210, 193, 0.18) 1px, transparent 1px),
                linear-gradient(rgba(221, 210, 193, 0.16) 1px, transparent 1px),
                var(--as-slide);
            background-size: 34px 34px;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .as-slide-title {
            position: absolute;
            left: 5%;
            top: 3%;
            right: 5%;
            height: 11%;
            display: flex;
            align-items: center;
            color: var(--as-text);
            font-size: 22px;
            font-weight: 650;
            line-height: 1.2;
        }

        .as-slide-subtitle {
            position: absolute;
            left: 5%;
            top: 13%;
            color: var(--as-muted);
            font-size: 13px;
        }

        .as-aoi {
            position: absolute;
            border: 1.5px dashed var(--as-info);
            border-radius: 6px;
            background: rgba(255, 252, 245, 0.76);
            padding: 8px;
            overflow: hidden;
            box-sizing: border-box;
            transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
        }

        .as-aoi:hover {
            transform: translateY(-1px);
            background: rgba(255, 252, 245, 0.94);
        }

        .as-aoi.is-candidate {
            border-style: solid;
            border-color: var(--as-candidate);
            background: var(--as-candidate-fill);
        }

        .as-aoi.is-highlighted {
            border-style: solid;
            border-color: var(--as-confirmed);
            background: var(--as-confirmed-fill);
        }

        .as-aoi-state {
            display: inline-block;
            color: var(--as-muted);
            background: rgba(255, 252, 245, 0.82);
            border: 1px solid var(--as-border);
            border-radius: 999px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: 10px;
            line-height: 1.1;
            padding: 2px 6px;
            margin-bottom: 5px;
        }

        .as-aoi.is-candidate .as-aoi-state {
            color: var(--as-candidate-text);
            border-color: rgba(184, 107, 60, 0.38);
        }

        .as-aoi.is-highlighted .as-aoi-state {
            color: var(--as-confirmed-text);
            border-color: rgba(111, 138, 106, 0.45);
        }

        .as-aoi-label {
            color: var(--as-text);
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .as-aoi-text {
            color: #4D453D;
            font-size: 12px;
            line-height: 1.35;
        }

        .as-confirmation {
            border: 1px solid var(--as-border);
            border-radius: var(--as-radius);
            background: var(--as-surface);
            padding: 0.9rem 1rem;
            margin-bottom: 0.8rem;
        }

        .as-confirmation.is-pending {
            border-color: rgba(184, 107, 60, 0.38);
            background: #FFF8EA;
        }

        .as-confirmation.is-confirmed {
            border-color: rgba(111, 138, 106, 0.45);
            background: #F3F7EF;
        }

        .as-confirmation-message {
            color: var(--as-text);
            font-size: 0.96rem;
            font-weight: 650;
            line-height: 1.45;
        }

        .as-confirmation-detail {
            color: var(--as-muted);
            font-size: 0.86rem;
            line-height: 1.45;
            margin-top: 0.35rem;
        }

        .as-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.1rem 0 0.85rem;
        }

        .as-chip {
            display: inline-flex;
            gap: 0.25rem;
            align-items: center;
            border: 1px solid var(--as-border);
            border-radius: 999px;
            background: var(--as-surface);
            color: var(--as-muted);
            font-size: 0.82rem;
            line-height: 1.3;
            padding: 0.32rem 0.58rem;
        }

        .as-chip code {
            color: var(--as-text);
            font-size: 0.8rem;
            background: transparent;
            padding: 0;
        }

        .as-grounding-panel {
            display: grid;
            grid-template-columns: minmax(0, 0.82fr) minmax(0, 1.18fr);
            gap: 1.5rem;
            min-height: 0;
            margin: 0 0 0.15rem;
        }

        [data-testid="stExpander"] {
            border-color: var(--as-border);
            background: rgba(255, 252, 245, 0.48);
        }

        hr {
            border-color: var(--as-border);
        }

        @media (max-width: 760px) {
            .block-container {
                padding-top: 1.2rem;
                padding-left: 1rem;
                padding-right: 1rem;
                max-width: calc(100vw - 2rem);
            }

            .as-app-header h1 {
                font-size: 1.8rem;
            }

            .as-app-header {
                margin-top: 0.6rem;
            }

            .as-slide-meta {
                align-items: flex-start;
                flex-direction: column;
            }

            .as-slide {
                min-height: 300px;
            }

            .as-grounding-panel {
                grid-template-columns: 1fr;
                gap: 0.8rem;
            }

            .as-slide-title {
                font-size: 16px;
            }

            .as-aoi {
                padding: 5px;
            }

            .as-aoi-label {
                font-size: 11px;
            }

            .as-aoi-text {
                display: none;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            div[data-testid="stButton"] > button,
            div[data-testid="stFormSubmitButton"] > button,
            .as-aoi {
                transition: none;
            }

            div[data-testid="stButton"] > button:hover,
            div[data-testid="stFormSubmitButton"] > button:hover,
            .as-aoi:hover {
                transform: none;
            }
        }
        </style>
        """
    )


if __name__ == "__main__":
    main()
