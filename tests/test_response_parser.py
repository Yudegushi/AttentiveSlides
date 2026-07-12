"""Tests for structured LLM response parsing."""

from __future__ import annotations

import json
import unittest

from modules.tutor.response_parser import (
    ResponseParseError,
    StructuredResponseParser,
)


def valid_payload() -> dict:
    return {
        "response_mode": "compare",
        "answer": (
            "Fixation 保持视线在单一位置；"
            "Saccade 是 fixation 之间的快速眼动。"
        ),
        "decision_summary": (
            "回答使用两个 slide sources。"
        ),
        "claims": [
            {
                "claim": (
                    "Fixation 保持视线在单一位置。"
                ),
                "support": "direct",
                "source_ids": ["slide_02_aoi_01"],
            },
            {
                "claim": (
                    "Saccade 是 fixation 之间的快速眼动。"
                ),
                "support": "direct",
                "source_ids": ["slide_02_aoi_02"],
            },
        ],
        "external_knowledge_used": False,
        "uncertainty_note": None,
        "active_recall_question": None,
    }


class TestStructuredResponseParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = StructuredResponseParser()

    def test_parses_valid_json(self) -> None:
        result = self.parser.parse(
            json.dumps(
                valid_payload(),
                ensure_ascii=False,
            )
        )

        self.assertFalse(result.recovered)
        self.assertEqual(
            result.response.response_mode,
            "compare",
        )
        self.assertEqual(
            len(result.response.claims),
            2,
        )

    def test_recovers_markdown_code_fence(self) -> None:
        raw = (
            "```json\n"
            + json.dumps(
                valid_payload(),
                ensure_ascii=False,
            )
            + "\n```"
        )

        result = self.parser.parse(raw)

        self.assertTrue(result.recovered)
        self.assertIn(
            "markdown_code_fence_removed",
            result.warnings,
        )

    def test_recovers_surrounding_text(self) -> None:
        raw = (
            "Here is the result:\n"
            + json.dumps(valid_payload())
            + "\nDone."
        )

        result = self.parser.parse(raw)

        self.assertIn(
            "surrounding_text_removed",
            result.warnings,
        )

    def test_empty_response_is_rejected(self) -> None:
        with self.assertRaises(
            ResponseParseError
        ) as context:
            self.parser.parse("   ")

        self.assertEqual(
            context.exception.code,
            "empty_response",
        )

    def test_invalid_json_is_rejected(self) -> None:
        with self.assertRaises(
            ResponseParseError
        ) as context:
            self.parser.parse(
                '{"response_mode": "compare",}'
            )

        self.assertEqual(
            context.exception.code,
            "invalid_json",
        )

    def test_missing_required_field_is_rejected(self) -> None:
        payload = valid_payload()
        del payload["answer"]

        with self.assertRaises(
            ResponseParseError
        ) as context:
            self.parser.parse(
                json.dumps(payload)
            )

        self.assertEqual(
            context.exception.code,
            "missing_field",
        )

    def test_unknown_field_is_rejected(self) -> None:
        payload = valid_payload()
        payload["hidden_reasoning"] = "not allowed"

        with self.assertRaises(
            ResponseParseError
        ) as context:
            self.parser.parse(
                json.dumps(payload)
            )

        self.assertEqual(
            context.exception.code,
            "unknown_field",
        )

    def test_claims_must_be_array(self) -> None:
        payload = valid_payload()
        payload["claims"] = {}

        with self.assertRaises(
            ResponseParseError
        ) as context:
            self.parser.parse(
                json.dumps(payload)
            )

        self.assertEqual(
            context.exception.code,
            "invalid_field_type",
        )

    def test_source_ids_must_be_strings(self) -> None:
        payload = valid_payload()
        payload["claims"][0]["source_ids"] = [123]

        with self.assertRaises(
            ResponseParseError
        ) as context:
            self.parser.parse(
                json.dumps(payload)
            )

        self.assertEqual(
            context.exception.code,
            "invalid_field_type",
        )

    def test_schema_inconsistency_is_rejected(self) -> None:
        payload = valid_payload()
        payload["external_knowledge_used"] = True

        with self.assertRaises(
            ResponseParseError
        ) as context:
            self.parser.parse(
                json.dumps(payload)
            )

        self.assertEqual(
            context.exception.code,
            "schema_validation_error",
        )

    def test_strict_parser_rejects_code_fence(self) -> None:
        parser = StructuredResponseParser(
            allow_code_fences=False
        )

        raw = (
            "```json\n"
            + json.dumps(valid_payload())
            + "\n```"
        )

        with self.assertRaises(
            ResponseParseError
        ) as context:
            parser.parse(raw)

        self.assertEqual(
            context.exception.code,
            "code_fence_not_allowed",
        )


if __name__ == "__main__":
    unittest.main()
