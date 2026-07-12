"""Tests for GroundedTutorAgent orchestration."""

from __future__ import annotations

import json
import unittest

from modules.common.llm_schemas import LLMUsage
from modules.tutor.api_llm_client import (
    RawLLMResponse,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
)
from tests.test_tutor_request_adapter import (
    make_context,
)


def valid_response_payload() -> dict:
    return {
        "response_mode": "compare",
        "answer": (
            "Fixation 保持视线在单一位置；"
            "Saccade 是 fixation 之间的快速眼动。"
        ),
        "decision_summary": (
            "回答使用已确认 AOI 和当前 slide text。"
        ),
        "claims": [
            {
                "claim": (
                    "Fixation 保持视线在单一位置。"
                ),
                "support": "direct",
                "source_ids": [
                    "slide_002_aoi_fixation"
                ],
            },
            {
                "claim": (
                    "Saccade 是 fixation 之间的快速眼动。"
                ),
                "support": "direct",
                "source_ids": [
                    "slide_002_full_text"
                ],
            },
        ],
        "external_knowledge_used": False,
        "uncertainty_note": None,
        "active_recall_question": None,
    }


class SequenceClient:
    provider = "test_provider"
    model = "test_model"

    def __init__(self, items) -> None:
        self.items = list(items)
        self.calls = 0

    def generate(self, messages):
        del messages
        self.calls += 1

        item = self.items.pop(0)

        if isinstance(item, Exception):
            raise item

        return RawLLMResponse(
            provider=self.provider,
            model=self.model,
            raw_text=item,
            latency_ms=100.0,
            usage=LLMUsage(
                prompt_tokens=100,
                completion_tokens=30,
                total_tokens=130,
            ),
            request_id=(
                f"request_{self.calls}"
            ),
        )


class TestGroundedTutorAgent(unittest.TestCase):
    def test_successful_generation(self) -> None:
        client = SequenceClient([
            json.dumps(
                valid_response_payload(),
                ensure_ascii=False,
            )
        ])

        result = GroundedTutorAgent(
            llm_client=client
        ).answer_context(make_context())

        self.assertEqual(
            result.status,
            "success",
        )
        self.assertTrue(
            result.validation.is_valid
        )
        self.assertFalse(
            result.call_result.fallback_used
        )
        self.assertEqual(client.calls, 1)

    def test_parse_failure_is_retried(self) -> None:
        client = SequenceClient([
            '{"response_mode": "compare",}',
            json.dumps(
                valid_response_payload()
            ),
        ])

        result = GroundedTutorAgent(
            llm_client=client,
            max_retries=1,
        ).answer_context(make_context())

        self.assertEqual(
            result.status,
            "success",
        )
        self.assertEqual(
            result.call_result.retry_count,
            1,
        )
        self.assertEqual(client.calls, 2)
        self.assertEqual(
            result.call_result.usage.total_tokens,
            260,
        )

    def test_validation_failure_is_retried(
        self,
    ) -> None:
        invalid_payload = (
            valid_response_payload()
        )

        invalid_payload["claims"] = [
            {
                "claim": "Invented citation.",
                "support": "direct",
                "source_ids": [
                    "invented_source"
                ],
            }
        ]

        client = SequenceClient([
            json.dumps(invalid_payload),
            json.dumps(
                valid_response_payload()
            ),
        ])

        result = GroundedTutorAgent(
            llm_client=client,
            max_retries=1,
        ).answer_context(make_context())

        self.assertEqual(
            result.status,
            "success",
        )
        self.assertEqual(client.calls, 2)
        self.assertIn(
            "unknown_source_id",
            [
                issue["code"]
                for issue
                in result.attempts[0]
                .validation["issues"]
            ],
        )

    def test_repeated_failure_uses_fallback(
        self,
    ) -> None:
        client = SequenceClient([
            "not json",
            "still not json",
        ])

        result = GroundedTutorAgent(
            llm_client=client,
            max_retries=1,
        ).answer_context(make_context())

        self.assertEqual(
            result.status,
            "fallback",
        )
        self.assertTrue(
            result.call_result.fallback_used
        )
        self.assertTrue(
            result.validation.is_valid
        )
        self.assertEqual(client.calls, 2)

    def test_confirmation_gate_skips_api(
        self,
    ) -> None:
        client = SequenceClient([
            json.dumps(
                valid_response_payload()
            )
        ])

        result = GroundedTutorAgent(
            llm_client=client
        ).answer_context(
            make_context(
                needs_confirmation=True
            )
        )

        self.assertEqual(
            result.status,
            "confirmation_required",
        )
        self.assertEqual(client.calls, 0)
        self.assertTrue(
            result.validation.is_valid
        )
        self.assertEqual(
            result.call_result.provider,
            "local_policy",
        )

    def test_legacy_response_contains_xai_data(
        self,
    ) -> None:
        client = SequenceClient([
            json.dumps(
                valid_response_payload()
            )
        ])

        result = GroundedTutorAgent(
            llm_client=client
        ).answer_context(make_context())

        legacy = result.to_legacy_response()

        self.assertEqual(
            legacy.answer,
            result.call_result.response.answer,
        )

        self.assertIn(
            "validation",
            legacy.used_context,
        )

        self.assertIn(
            "claims",
            legacy.used_context,
        )

        self.assertFalse(
            legacy.used_context[
                "external_knowledge_used"
            ]
        )


if __name__ == "__main__":
    unittest.main()
