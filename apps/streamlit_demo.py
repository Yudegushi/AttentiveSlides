"""Streamlit demo for the mock-driven AttentiveSlides Member 3/4 pipeline."""

from __future__ import annotations

from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from modules.common.schemas import GazePrediction, LearningState
from modules.logging.interaction_logger import InteractionLogger
from modules.system.demo_view_model import (
    build_interaction_view_model,
    run_scenario_turn,
    scenario_to_dict,
)
from modules.system.pipeline import load_interaction_log
from modules.system.scenarios import InteractionScenario, load_scenarios


LOG_PATH = Path("data/logs/streamlit_demo_interactions.jsonl")
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
    edited_scenario = _sidebar_controls(scenario)

    if "confirmed_aoi_id" not in st.session_state:
        st.session_state.confirmed_aoi_id = None
    if "active_scenario_name" not in st.session_state:
        st.session_state.active_scenario_name = edited_scenario.name
    if st.session_state.active_scenario_name != edited_scenario.name:
        st.session_state.active_scenario_name = edited_scenario.name
        st.session_state.confirmed_aoi_id = None

    st.title("AttentiveSlides")
    st.caption("Mock-driven system demo for gaze-grounded, confirmation-gated slide tutoring.")

    result = run_scenario_turn(edited_scenario, confirmed_aoi_id=st.session_state.confirmed_aoi_id)
    view_model = build_interaction_view_model(result, edited_scenario)

    left, right = st.columns([1.25, 1.0], gap="large")
    with left:
        st.subheader("Slide AOI Grounding")
        st.html(_slide_html(view_model))
        _render_confirmation(view_model, edited_scenario)

    with right:
        _render_response(view_model)
        _render_evidence(view_model, edited_scenario)

    st.divider()
    _render_evaluation(view_model)
    _render_log_viewer()


@st.cache_data
def _load_scenarios() -> list[InteractionScenario]:
    return load_scenarios()


def _select_scenario(scenarios: list[InteractionScenario]) -> InteractionScenario:
    names = [scenario.name for scenario in scenarios]
    selected = st.sidebar.selectbox("Scenario", names, index=0)
    return scenarios[names.index(selected)]


def _sidebar_controls(scenario: InteractionScenario) -> InteractionScenario:
    st.sidebar.header("Mock Inputs")
    transcript = st.sidebar.text_area("Transcript", scenario.transcript, height=96)

    aoi_ids = [aoi["aoi_id"] for aoi in _scenario_aois()]
    predicted_options = ["None", *aoi_ids]
    default_predicted = scenario.gaze_prediction.predicted_aoi_id or "None"
    if default_predicted not in predicted_options:
        default_predicted = "None"

    with st.sidebar.expander("Gaze prediction", expanded=True):
        gaze_grid = st.selectbox(
            "Gaze grid",
            GAZE_GRIDS,
            index=GAZE_GRIDS.index(scenario.gaze_prediction.gaze_grid)
            if scenario.gaze_prediction.gaze_grid in GAZE_GRIDS
            else 0,
        )
        predicted = st.selectbox(
            "Predicted AOI",
            predicted_options,
            index=predicted_options.index(default_predicted),
        )
        confidence = st.slider("Confidence", 0.0, 1.0, float(scenario.gaze_prediction.confidence), 0.01)
        stable_duration = st.slider(
            "Stable duration",
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

    if st.sidebar.button("Reset confirmation", use_container_width=True):
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


def _scenario_aois() -> list[dict[str, Any]]:
    scenario = _load_scenarios()[0]
    result = run_scenario_turn(scenario)
    return build_interaction_view_model(result, scenario)["aois"]


def _render_confirmation(view_model: dict[str, Any], scenario: InteractionScenario) -> None:
    st.subheader("Confirmation")
    if not view_model["pending_confirmation"]:
        confirmed = view_model["actual"].get("confirmed_aoi_id") or view_model["highlighted_aoi_id"]
        st.success(f"Target resolved: {confirmed}")
        if st.button("Reopen confirmation", use_container_width=True):
            st.session_state.confirmed_aoi_id = None
            st.rerun()
        return

    st.warning(view_model["confirmation_message"])
    options = view_model["confirmation_options"]
    labels = [_format_option(option) for option in options]
    selected_label = st.selectbox("Confirm or correct target", labels)
    selected = options[labels.index(selected_label)]["aoi_id"]

    confirm_col, fixture_col = st.columns(2)
    if confirm_col.button("Confirm target", type="primary", use_container_width=True):
        st.session_state.confirmed_aoi_id = selected
        st.rerun()
    if scenario.confirmed_aoi_id and fixture_col.button("Use fixture correction", use_container_width=True):
        st.session_state.confirmed_aoi_id = scenario.confirmed_aoi_id
        st.rerun()


def _render_response(view_model: dict[str, Any]) -> None:
    st.subheader("Tutor Response")
    response = view_model["response"]
    if response["answer"] is None:
        st.info("Final AOI-specific answer is waiting for target confirmation.")
    else:
        st.markdown(response["answer"])
    if response.get("active_recall_question"):
        st.markdown(f"**Active recall:** {response['active_recall_question']}")
    if response.get("adaptive_suggestion"):
        st.markdown(f"**Adaptive suggestion:** {response['adaptive_suggestion']}")


def _render_evidence(view_model: dict[str, Any], scenario: InteractionScenario) -> None:
    st.subheader("System Evidence")
    gaze = scenario.gaze_prediction
    metric_cols = st.columns(4)
    metric_cols[0].metric("Intent", view_model["intent"])
    metric_cols[1].metric("Predicted AOI", gaze.predicted_aoi_id or "None")
    metric_cols[2].metric("Confidence", f"{gaze.confidence:.2f}")
    metric_cols[3].metric("Strategy", view_model["actual"]["adaptive_strategy"])

    with st.expander("Evidence details", expanded=True):
        for item in view_model["evidence"]:
            st.write(f"- {item}")
    with st.expander("Learning-state signals", expanded=False):
        st.json(view_model["learning_state_summary"])
    with st.expander("Scenario fixture", expanded=False):
        st.json(scenario_to_dict(scenario))
    if st.button("Append current turn to JSONL log", use_container_width=True):
        InteractionLogger(LOG_PATH).log_interaction(view_model["log_event"])
        st.toast("Logged current interaction turn.")


def _render_evaluation(view_model: dict[str, Any]) -> None:
    st.subheader("Expected vs Actual")
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
    st.subheader("Recent JSONL Log")
    log_rows = load_interaction_log(LOG_PATH)
    if not log_rows:
        st.caption("No Streamlit demo log has been written in this session.")
        return
    st.dataframe(log_rows[-10:], hide_index=True, use_container_width=True)


def _slide_html(view_model: dict[str, Any]) -> str:
    boxes = "\n".join(_aoi_box_html(aoi) for aoi in view_model["aois"] if aoi["aoi_id"] != "whole_slide")
    return f"""
    <div class="as-slide">
      <div class="as-slide-title">SHAP Values for Local Model Explanation</div>
      <div class="as-slide-subtitle">Mock slide 5 · AOI boxes use normalized manifest coordinates</div>
      {boxes}
    </div>
    """


def _aoi_box_html(aoi: dict[str, Any]) -> str:
    x1, y1, x2, y2 = aoi["bbox"]
    classes = ["as-aoi"]
    if aoi["is_candidate"]:
        classes.append("is-candidate")
    if aoi["is_highlighted"]:
        classes.append("is-highlighted")
    style = (
        f"left:{x1 * 100:.2f}%;top:{y1 * 100:.2f}%;"
        f"width:{(x2 - x1) * 100:.2f}%;height:{(y2 - y1) * 100:.2f}%;"
    )
    label = escape(str(aoi.get("name") or aoi["aoi_id"]))
    text = escape(str(aoi.get("text") or ""))
    return f"""
    <div class="{' '.join(classes)}" style="{style}">
      <div class="as-aoi-label">{label}</div>
      <div class="as-aoi-text">{text}</div>
    </div>
    """


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
        .as-slide {
            position: relative;
            width: 100%;
            aspect-ratio: 16 / 9;
            min-height: 430px;
            border: 1px solid #d0d7de;
            background: #f8fafc;
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
            color: #1f2937;
            font-size: 22px;
            font-weight: 650;
        }
        .as-slide-subtitle {
            position: absolute;
            left: 5%;
            top: 13%;
            color: #64748b;
            font-size: 13px;
        }
        .as-aoi {
            position: absolute;
            border: 2px solid #94a3b8;
            background: rgba(255, 255, 255, 0.74);
            padding: 8px;
            overflow: hidden;
            box-sizing: border-box;
        }
        .as-aoi.is-candidate {
            border-color: #c2410c;
            background: rgba(255, 237, 213, 0.82);
        }
        .as-aoi.is-highlighted {
            border-color: #047857;
            background: rgba(209, 250, 229, 0.88);
        }
        .as-aoi-label {
            color: #111827;
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .as-aoi-text {
            color: #334155;
            font-size: 12px;
            line-height: 1.35;
        }
        @media (max-width: 760px) {
            .as-slide {
                min-height: 320px;
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
        </style>
        """
    )


if __name__ == "__main__":
    main()
