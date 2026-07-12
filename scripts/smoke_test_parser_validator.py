"""Recorded smoke test for response parser and grounding validator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_smoke_common import base_record, write_record
from modules.common.llm_schemas import (
    ContextSource,
    TutorLLMRequest,
)
from modules.tutor.grounding_validator import (
    GroundingValidator,
)
from modules.tutor.response_parser import (
    ResponseParseError,
    StructuredResponseParser,
)


def main() -> None:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--output",
        required=True,
    )
    args = argument_parser.parse_args()

    request = TutorLLMRequest(
        query_id="parser_smoke_001",
        deck_id="lecture_2",
        slide_id=2,
        question="fixation 和 saccade 有什么区别？",
        intent="compare",
        response_mode="compare",
        confirmed_aoi_id="aoi_fixation",
        sources=[
            ContextSource(
                source_id="slide_02_aoi_01",
                slide_id=2,
                source_kind="confirmed_aoi",
                aoi_id="aoi_fixation",
                text=(
                    "Fixation is maintaining gaze "
                    "on a single location."
                ),
            ),
            ContextSource(
                source_id="slide_02_aoi_02",
                slide_id=2,
                source_kind="current_slide",
                aoi_id="aoi_saccade",
                text=(
                    "Saccade is a rapid eye movement "
                    "between fixations."
                ),
            ),
        ],
    )

    valid_payload = {
        "response_mode": "compare",
        "answer": (
            "Fixation 是保持视线在单一位置；"
            "Saccade 是 fixation 之间的快速眼动。"
        ),
        "decision_summary": (
            "回答仅使用两个提供的 slide sources。"
        ),
        "claims": [
            {
                "claim": (
                    "Fixation 是保持视线在单一位置。"
                ),
                "support": "direct",
                "source_ids": [
                    "slide_02_aoi_01"
                ],
            },
            {
                "claim": (
                    "Saccade 是 fixation 之间的快速眼动。"
                ),
                "support": "direct",
                "source_ids": [
                    "slide_02_aoi_02"
                ],
            },
        ],
        "external_knowledge_used": False,
        "uncertainty_note": None,
        "active_recall_question": None,
    }

    raw_valid = (
        "```json\n"
        + json.dumps(
            valid_payload,
            ensure_ascii=False,
        )
        + "\n```"
    )

    response_parser = StructuredResponseParser()
    validator = GroundingValidator()

    parse_result = response_parser.parse(raw_valid)
    validation_result = validator.validate(
        request,
        parse_result.response,
    )

    invalid_source_payload = dict(valid_payload)
    invalid_source_payload["claims"] = [
        {
            "claim": "Invented citation.",
            "support": "direct",
            "source_ids": ["invented_source"],
        }
    ]

    invalid_source_result = validator.validate(
        request,
        response_parser.parse(
            json.dumps(invalid_source_payload)
        ).response,
    )

    malformed_json = {
        "raised": False,
        "code": None,
        "message": None,
    }

    try:
        response_parser.parse(
            '{"response_mode": "compare",}'
        )
    except ResponseParseError as exc:
        malformed_json = {
            "raised": True,
            "code": exc.code,
            "message": exc.message,
        }

    checks = {
        "valid_response_parsed": (
            parse_result.response.response_mode
            == "compare"
        ),
        "code_fence_recovered": (
            "markdown_code_fence_removed"
            in parse_result.warnings
        ),
        "valid_grounding": (
            validation_result.is_valid
        ),
        "full_citation_coverage": (
            validation_result.citation_coverage
            == 1.0
        ),
        "confirmed_aoi_cited": (
            validation_result.confirmed_aoi_cited
            is True
        ),
        "invalid_source_rejected": (
            not invalid_source_result.is_valid
            and any(
                issue.code == "unknown_source_id"
                for issue
                in invalid_source_result.errors
            )
        ),
        "malformed_json_rejected": (
            malformed_json["raised"]
            and malformed_json["code"]
            == "invalid_json"
        ),
    }

    payload = base_record(
        "parser_validator_smoke"
    )
    payload.update({
        "passed": all(checks.values()),
        "checks": checks,
        "valid_parse_result": (
            parse_result.to_dict()
        ),
        "valid_grounding_result": (
            validation_result.to_dict()
        ),
        "invalid_source_result": (
            invalid_source_result.to_dict()
        ),
        "malformed_json_result": malformed_json,
    })

    write_record(args.output, payload)

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
