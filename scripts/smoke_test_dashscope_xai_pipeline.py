"""Recorded real-API smoke test for grounded tutor XAI output."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_smoke_common import (
    base_record,
    write_record,
)
from modules.system.demo_view_model import (
    run_scenario_turn,
)
from modules.system.scenarios import (
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
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        required=True,
    )
    args = parser.parse_args()

    scenario = load_scenarios()[0]

    confirmed_aoi_id = (
        scenario.confirmed_aoi_id
        or scenario.gaze_prediction
        .predicted_aoi_id
    )

    interaction = run_scenario_turn(
        scenario,
        confirmed_aoi_id=confirmed_aoi_id,
    )

    client = (
        OpenAICompatibleLLMClient
        .from_env()
    )

    result = GroundedTutorAgent(
        llm_client=client,
        max_retries=1,
    ).answer(
        interaction.resolved_query
    )

    view = build_xai_view_model(result)

    checks = {
        "agent_success": (
            result.status == "success"
        ),
        "fallback_not_used": (
            not result.call_result.fallback_used
        ),
        "validation_valid": (
            view["validation"]["is_valid"]
        ),
        "claims_available": (
            len(view["claims"]) >= 1
        ),
        "sources_available": (
            len(view["sources"]) >= 1
        ),
        "external_knowledge_not_used": (
            not view["external_knowledge_used"]
        ),
        "raw_response_not_exposed": (
            view["safety"][
                "raw_provider_response_exposed"
            ]
            is False
        ),
    }

    payload = base_record(
        "dashscope_streamlit_xai_smoke"
    )

    payload.update({
        "passed": all(checks.values()),
        "checks": checks,
        "xai_view_model": view,
    })

    write_record(
        args.output,
        payload,
    )

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
