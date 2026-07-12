"""Recorded real-API smoke test for GroundedTutorAgent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_smoke_common import base_record, write_record
from modules.tutor.api_llm_client import (
    OpenAICompatibleLLMClient,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
)
from tests.test_tutor_request_adapter import (
    make_context,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    client = (
        OpenAICompatibleLLMClient.from_env()
    )

    result = GroundedTutorAgent(
        llm_client=client,
        max_retries=1,
    ).answer_context(make_context())

    cited_sources = (
        result.call_result
        .response
        .cited_source_ids()
    )

    checks = {
        "status_success": (
            result.status == "success"
        ),
        "validation_valid": (
            result.validation.is_valid
        ),
        "fallback_not_used": (
            not result.call_result.fallback_used
        ),
        "confirmed_aoi_cited": (
            "slide_002_aoi_fixation"
            in cited_sources
        ),
        "external_knowledge_not_used": (
            not result.call_result
            .response
            .external_knowledge_used
        ),
    }

    payload = base_record(
        "dashscope_tutor_agent_smoke"
    )

    payload.update({
        "passed": all(checks.values()),
        "checks": checks,
        "result": result.to_dict(),
    })

    write_record(args.output, payload)

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
