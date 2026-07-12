"""Streamlit XAI demo for the grounded AttentiveSlides tutor."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

# Streamlit executes this file with apps/ as the script directory.
# Add the repository root so project packages such as modules.* can
# be imported consistently from CLI, AppTest, and remote deployment.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import streamlit as st

from modules.system.demo_view_model import (
    build_interaction_view_model,
    run_scenario_turn,
)
from modules.system.scenarios import (
    InteractionScenario,
    load_scenarios,
)
from modules.system.xai_view_model import (
    build_xai_view_model,
)
from modules.tutor.api_llm_client import (
    OpenAICompatibleLLMClient,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
    GroundedTutorResult,
)


def main() -> None:
    st.set_page_config(
        page_title="AttentiveSlides Grounded XAI",
        page_icon="AS",
        layout="wide",
    )

    st.title("AttentiveSlides · Grounded Tutor XAI")
    st.caption(
        "Gaze proposes a target, the learner confirms it, "
        "and the tutor exposes verifiable claim–source mappings."
    )

    scenarios = _load_scenarios()
    base_scenario = _select_scenario(scenarios)

    _ensure_session_state(base_scenario)

    transcript = st.sidebar.text_area(
        "Learner utterance",
        key="xai_transcript",
        height=100,
    )

    scenario = replace(
        base_scenario,
        transcript=transcript,
    )

    interaction = run_scenario_turn(
        scenario,
        confirmed_aoi_id=(
            st.session_state.xai_confirmed_aoi_id
        ),
    )

    interaction_view = (
        build_interaction_view_model(
            interaction,
            scenario,
        )
    )

    signature = _interaction_signature(
        scenario,
        interaction_view,
    )

    if (
        st.session_state.xai_result_signature
        != signature
    ):
        st.session_state.xai_grounded_result = None
        st.session_state.xai_api_error = None
        st.session_state.xai_result_signature = (
            signature
        )

    left, right = st.columns(
        [1.05, 0.95],
        gap="large",
    )

    with left:
        _render_interaction_context(
            interaction_view
        )
        _render_confirmation(
            interaction_view
        )

    with right:
        _render_generation_controls(
            interaction=interaction,
            interaction_view=interaction_view,
        )

        grounded_result = (
            st.session_state.xai_grounded_result
        )

        if grounded_result is not None:
            _render_xai_result(
                grounded_result
            )

    st.divider()

    st.caption(
        "The XAI surface displays source provenance, "
        "validation results and uncertainty. It does not "
        "display raw Chain-of-Thought, API credentials, "
        "or raw provider responses."
    )


@st.cache_data
def _load_scenarios() -> list[InteractionScenario]:
    return load_scenarios()


def _select_scenario(
    scenarios: list[InteractionScenario],
) -> InteractionScenario:
    names = [
        scenario.name
        for scenario in scenarios
    ]

    selected_name = st.sidebar.selectbox(
        "Scenario",
        names,
    )

    return scenarios[
        names.index(selected_name)
    ]


def _ensure_session_state(
    scenario: InteractionScenario,
) -> None:
    active_name = st.session_state.get(
        "xai_active_scenario"
    )

    if active_name != scenario.name:
        st.session_state.xai_active_scenario = (
            scenario.name
        )
        st.session_state.xai_transcript = (
            scenario.transcript
        )
        st.session_state.xai_confirmed_aoi_id = (
            None
        )
        st.session_state.xai_grounded_result = (
            None
        )
        st.session_state.xai_api_error = None
        st.session_state.xai_result_signature = (
            None
        )

    defaults = {
        "xai_transcript": scenario.transcript,
        "xai_confirmed_aoi_id": None,
        "xai_grounded_result": None,
        "xai_api_error": None,
        "xai_result_signature": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _interaction_signature(
    scenario: InteractionScenario,
    view: dict[str, Any],
) -> str:
    payload = {
        "scenario": scenario.name,
        "transcript": scenario.transcript,
        "confirmed_aoi_id": (
            st.session_state
            .xai_confirmed_aoi_id
        ),
        "resolved_aoi_id": (
            view["actual"].get(
                "resolved_aoi_id"
            )
        ),
        "intent": view["intent"],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )


def _render_interaction_context(
    view: dict[str, Any],
) -> None:
    st.subheader("Interaction context")

    metric_columns = st.columns(3)

    metric_columns[0].metric(
        "Intent",
        view["intent"],
    )

    metric_columns[1].metric(
        "Confirmation",
        (
            view["confirmation_mode"]
            or "none"
        ),
    )

    metric_columns[2].metric(
        "Resolved AOI",
        (
            view["actual"].get(
                "resolved_aoi_id"
            )
            or "unresolved"
        ),
    )

    st.markdown("#### Observable evidence")

    for evidence in view["evidence"]:
        st.write(f"- {evidence}")

    st.markdown("#### Slide AOIs")

    aoi_rows = [
        {
            "aoi_id": aoi["aoi_id"],
            "name": aoi.get("name"),
            "type": aoi.get("type"),
            "candidate": aoi.get(
                "is_candidate"
            ),
            "highlighted": aoi.get(
                "is_highlighted"
            ),
            "text": aoi.get("text"),
        }
        for aoi in view["aois"]
    ]

    st.dataframe(
        aoi_rows,
        hide_index=True,
        width="stretch",
    )

    with st.expander(
        "Observable learning-state signals",
        expanded=False,
    ):
        st.json(
            view["learning_state_summary"]
        )


def _render_confirmation(
    view: dict[str, Any],
) -> None:
    st.subheader("Target confirmation")

    if not view["pending_confirmation"]:
        confirmed = (
            st.session_state
            .xai_confirmed_aoi_id
            or view["actual"].get(
                "resolved_aoi_id"
            )
        )

        st.success(
            "Target available for grounded generation: "
            f"{confirmed or 'whole slide'}"
        )

        if st.button(
            "Reopen confirmation",
            width="stretch",
        ):
            st.session_state.xai_confirmed_aoi_id = (
                None
            )
            st.session_state.xai_grounded_result = (
                None
            )
            st.rerun()

        return

    options = view["confirmation_options"]

    if not options:
        st.warning(
            "No target candidates are available."
        )
        return

    labels = [
        _confirmation_label(option)
        for option in options
    ]

    selected_label = st.selectbox(
        "Select the intended region",
        labels,
    )

    selected_index = labels.index(
        selected_label
    )

    selected_aoi_id = options[
        selected_index
    ]["aoi_id"]

    st.warning(
        view["confirmation_message"]
        or "Please confirm the intended region."
    )

    if st.button(
        f"Confirm {selected_aoi_id}",
        type="primary",
        width="stretch",
    ):
        st.session_state.xai_confirmed_aoi_id = (
            selected_aoi_id
        )
        st.session_state.xai_grounded_result = (
            None
        )
        st.rerun()


def _render_generation_controls(
    *,
    interaction: Any,
    interaction_view: dict[str, Any],
) -> None:
    st.subheader("Grounded API tutor")

    if interaction_view["pending_confirmation"]:
        st.info(
            "API generation is gated until the "
            "learner confirms or corrects the AOI."
        )
        return

    st.caption(
        "The API is called only when the button is "
        "pressed. Streamlit reruns do not automatically "
        "consume additional tokens."
    )

    if st.button(
        "Generate grounded API answer",
        type="primary",
        width="stretch",
    ):
        st.session_state.xai_api_error = None

        try:
            with st.spinner(
                "Generating and validating answer..."
            ):
                client = (
                    OpenAICompatibleLLMClient
                    .from_env()
                )

                agent = GroundedTutorAgent(
                    llm_client=client,
                    max_retries=1,
                )

                result = agent.answer(
                    interaction.resolved_query
                )

        except Exception as exc:
            st.session_state.xai_api_error = (
                f"{type(exc).__name__}: {exc}"
            )
            st.session_state.xai_grounded_result = (
                None
            )

        else:
            st.session_state.xai_grounded_result = (
                result
            )

    if st.session_state.xai_api_error:
        st.error(
            st.session_state.xai_api_error
        )


def _render_xai_result(
    result: GroundedTutorResult,
) -> None:
    view = build_xai_view_model(result)

    st.markdown("### Tutor answer")
    st.markdown(view["answer"])

    if view["active_recall_question"]:
        st.info(
            "Active recall: "
            + view["active_recall_question"]
        )

    if view["uncertainty_note"]:
        st.warning(
            "Uncertainty: "
            + view["uncertainty_note"]
        )

    telemetry = view["telemetry"]
    validation = view["validation"]

    metric_columns = st.columns(4)

    metric_columns[0].metric(
        "Status",
        view["status"],
    )

    metric_columns[1].metric(
        "Validation",
        (
            "PASS"
            if validation["is_valid"]
            else "FAIL"
        ),
    )

    metric_columns[2].metric(
        "Latency",
        f"{telemetry['latency_ms']:.0f} ms",
    )

    metric_columns[3].metric(
        "Total tokens",
        (
            telemetry["total_tokens"]
            if telemetry["total_tokens"]
            is not None
            else "—"
        ),
    )

    st.markdown("#### Why this answer")
    st.write(view["decision_summary"])

    policy_columns = st.columns(3)

    policy_columns[0].metric(
        "Confirmed AOI",
        view["confirmed_aoi_id"] or "None",
    )

    policy_columns[1].metric(
        "External knowledge",
        (
            "Used"
            if view[
                "external_knowledge_used"
            ]
            else "Not used"
        ),
    )

    coverage = validation[
        "citation_coverage"
    ]

    policy_columns[2].metric(
        "Citation coverage",
        (
            f"{coverage:.0%}"
            if coverage is not None
            else "N/A"
        ),
    )

    st.markdown("#### Claim–source mapping")

    if view["claims"]:
        st.dataframe(
            view["claims"],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption(
            "This response contains no educational claims."
        )

    st.markdown("#### Sources used")

    st.dataframe(
        view["sources"],
        hide_index=True,
        width="stretch",
    )

    with st.expander(
        "Validation details",
        expanded=False,
    ):
        st.json(validation)

    with st.expander(
        "Sanitized generation attempts",
        expanded=False,
    ):
        if view["attempts"]:
            st.dataframe(
                view["attempts"],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption(
                "No provider attempt was made. "
                "A local policy handled this turn."
            )

    with st.expander(
        "Model telemetry",
        expanded=False,
    ):
        st.json(telemetry)

    st.download_button(
        "Download sanitized XAI record",
        data=json.dumps(
            view,
            ensure_ascii=False,
            indent=2,
        ),
        file_name=(
            f"{view['query_id']}_xai.json"
        ),
        mime="application/json",
        width="stretch",
    )


def _confirmation_label(
    option: dict[str, Any],
) -> str:
    name = (
        option.get("name")
        or option["aoi_id"]
    )

    score = option.get("score")

    if score is None:
        return (
            f"{name} ({option['aoi_id']})"
        )

    return (
        f"{name} ({option['aoi_id']}) "
        f"· {float(score):.2f}"
    )


if __name__ == "__main__":
    main()
