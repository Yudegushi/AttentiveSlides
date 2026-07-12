"""Recorded deterministic smoke tests for GroundedTutorAgent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_smoke_common import base_record, write_record
from modules.common.llm_schemas import LLMUsage
from modules.tutor.api_llm_client import RawLLMResponse
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
)
from tests.test_grounded_tutor_agent import (
    valid_response_payload,
)
from tests.test_tutor_request_adapter import (
    make_context,
)


class SequenceClient:
    provider = "smoke_provider"
    model = "smoke_model"

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = 0

    def generate(self, messages):
        del messages
        self.calls += 1
        raw_text = self.responses.pop(0)

        return RawLLMResponse(
            provider=self.provider,
            model=self.model,
            raw_text=raw_text,
            latency_ms=50.0,
            usage=LLMUsage(
                prompt_tokens=80,
                completion_tokens=20,
                total_tokens=100,
            ),
            request_id=f"smoke_{self.calls}",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    valid_json = json.dumps(
        valid_response_payload(),
        ensure_ascii=False,
    )

    success_client = SequenceClient([
        valid_json
    ])

    success_result = GroundedTutorAgent(
        llm_client=success_client
    ).answer_context(make_context())

    retry_client = SequenceClient([
        "invalid json",
        valid_json,
    ])

    retry_result = GroundedTutorAgent(
        llm_client=retry_client,
        max_retries=1,
    ).answer_context(make_context())

    fallback_client = SequenceClient([
        "invalid json",
        "still invalid",
    ])

    fallback_result = GroundedTutorAgent(
        llm_client=fallback_client,
        max_retries=1,
    ).answer_context(make_context())

    confirmation_client = SequenceClient([
        valid_json
    ])

    confirmation_result = GroundedTutorAgent(
        llm_client=confirmation_client
    ).answer_context(
        make_context(
            needs_confirmation=True
        )
    )

    checks = {
        "success_path": (
            success_result.status == "success"
            and success_result.validation.is_valid
        ),
        "retry_path": (
            retry_result.status == "success"
            and retry_result.call_result.retry_count
            == 1
        ),
        "fallback_path": (
            fallback_result.status == "fallback"
            and fallback_result.call_result
            .fallback_used
        ),
        "confirmation_gate": (
            confirmation_result.status
            == "confirmation_required"
            and confirmation_client.calls == 0
        ),
        "all_results_valid": all(
            result.validation.is_valid
            for result in (
                success_result,
                retry_result,
                fallback_result,
                confirmation_result,
            )
        ),
    }

    payload = base_record(
        "tutor_agent_integration_smoke"
    )

    payload.update({
        "passed": all(checks.values()),
        "checks": checks,
        "success_result": (
            success_result.to_dict()
        ),
        "retry_result": (
            retry_result.to_dict()
        ),
        "fallback_result": (
            fallback_result.to_dict()
        ),
        "confirmation_result": (
            confirmation_result.to_dict()
        ),
    })

    write_record(args.output, payload)

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
