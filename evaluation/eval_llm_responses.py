"""Evaluate grounded tutor responses with fixtures or DashScope API."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from evaluation.llm_dataset import (
    LLMEvaluationCase,
    load_llm_cases,
)
from modules.tutor.api_llm_client import (
    OpenAICompatibleLLMClient,
)
from modules.tutor.grounded_prompt import (
    GroundedPrompt,
    GroundedPromptBuilder,
)
from modules.tutor.grounding_validator import (
    GroundingValidator,
)
from modules.tutor.response_parser import (
    ResponseParseError,
    StructuredResponseParser,
)


@dataclass(frozen=True)
class ProviderOutput:
    provider: str
    model: str
    raw_text: str
    latency_ms: float
    usage: dict[str, int] | None = None
    request_id: str | None = None


class ResponseProvider(Protocol):
    def generate(
        self,
        case: LLMEvaluationCase,
        prompt: GroundedPrompt,
    ) -> ProviderOutput:
        ...


class FixtureResponseProvider:
    def generate(
        self,
        case: LLMEvaluationCase,
        prompt: GroundedPrompt,
    ) -> ProviderOutput:
        del prompt

        return ProviderOutput(
            provider="fixture",
            model="fixture-response",
            raw_text=json.dumps(
                case.fixture_response,
                ensure_ascii=False,
            ),
            latency_ms=0.0,
        )


class DashScopeResponseProvider:
    def __init__(self) -> None:
        self.client = (
            OpenAICompatibleLLMClient.from_env()
        )

    def generate(
        self,
        case: LLMEvaluationCase,
        prompt: GroundedPrompt,
    ) -> ProviderOutput:
        del case

        response = self.client.generate(
            prompt.messages()
        )

        return ProviderOutput(
            provider=response.provider,
            model=response.model,
            raw_text=response.raw_text,
            latency_ms=response.latency_ms,
            usage=(
                response.usage.to_dict()
                if response.usage is not None
                else None
            ),
            request_id=response.request_id,
        )


def _git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def evaluate_case(
    case: LLMEvaluationCase,
    provider: ResponseProvider,
    prompt_builder: GroundedPromptBuilder,
    parser: StructuredResponseParser,
    validator: GroundingValidator,
) -> dict[str, Any]:
    prompt = prompt_builder.build(case.request)

    record: dict[str, Any] = {
        "case_id": case.case_id,
        "category": case.category,
        "description": case.description,
        "query_id": case.request.query_id,
        "prompt_character_count": (
            prompt.character_count()
        ),
        "prompt_messages": prompt.messages(),
        "parse_success": False,
        "validation_success": False,
        "overall_pass": False,
    }

    try:
        provider_output = provider.generate(
            case,
            prompt,
        )
    except Exception as exc:
        record["provider_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        return record

    record.update({
        "provider": provider_output.provider,
        "model": provider_output.model,
        "latency_ms": provider_output.latency_ms,
        "usage": provider_output.usage,
        "provider_request_id": (
            provider_output.request_id
        ),
        "raw_response": provider_output.raw_text,
    })

    try:
        parse_result = parser.parse(
            provider_output.raw_text
        )
    except ResponseParseError as exc:
        record["parse_error"] = {
            "code": exc.code,
            "message": exc.message,
        }
        return record

    record["parse_success"] = True
    record["parse_warnings"] = list(
        parse_result.warnings
    )
    record["structured_response"] = (
        parse_result.response.to_dict()
    )

    validation_result = validator.validate(
        case.request,
        parse_result.response,
    )

    record["validation_success"] = (
        validation_result.is_valid
    )
    record["validation"] = (
        validation_result.to_dict()
    )

    expectations = case.expectations
    response = parse_result.response

    cited_source_ids = response.cited_source_ids()
    required_sources = set(
        expectations.required_source_ids
    )

    searchable_text = "\n".join(
        [
            response.answer,
            response.decision_summary,
            *[
                claim.claim
                for claim in response.claims
            ],
        ]
    ).casefold()

    direct_claim_count = sum(
        claim.support == "direct"
        for claim in response.claims
    )

    checks = {
        "validation_matches_expectation": (
            validation_result.is_valid
            == expectations.expected_validation_valid
        ),
        "required_sources_cited": (
            required_sources
            <= cited_source_ids
        ),
        "forbidden_phrases_absent": all(
            phrase.casefold() not in searchable_text
            for phrase
            in expectations.forbidden_phrases
        ),
        "external_knowledge_flag_matches": (
            response.external_knowledge_used
            == (
                expectations
                .expected_external_knowledge_used
            )
        ),
        "minimum_direct_claims": (
            direct_claim_count
            >= expectations.min_direct_claims
        ),
        "active_recall_requirement": (
            not (
                expectations
                .require_active_recall_question
            )
            or bool(
                response.active_recall_question
            )
        ),
    }

    record["checks"] = checks
    record["overall_pass"] = all(
        checks.values()
    )

    return record


def summarize_records(
    records: list[dict[str, Any]],
    *,
    provider_name: str,
) -> dict[str, Any]:
    total = len(records)

    parse_successes = sum(
        bool(record.get("parse_success"))
        for record in records
    )

    validation_successes = sum(
        bool(record.get("validation_success"))
        for record in records
    )

    overall_passes = sum(
        bool(record.get("overall_pass"))
        for record in records
    )

    latencies = [
        float(record["latency_ms"])
        for record in records
        if record.get("latency_ms") is not None
    ]

    token_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    for record in records:
        usage = record.get("usage")

        if not usage:
            continue

        for key in token_totals:
            token_totals[key] += int(
                usage.get(key, 0)
            )

    return {
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "provider": provider_name,
        "git_commit": _git_value(
            "rev-parse",
            "HEAD",
        ),
        "git_branch": _git_value(
            "branch",
            "--show-current",
        ),
        "total_cases": total,
        "parse_success_count": parse_successes,
        "parse_success_rate": (
            parse_successes / total
            if total
            else 0.0
        ),
        "validation_success_count": (
            validation_successes
        ),
        "validation_success_rate": (
            validation_successes / total
            if total
            else 0.0
        ),
        "overall_pass_count": overall_passes,
        "overall_pass_rate": (
            overall_passes / total
            if total
            else 0.0
        ),
        "mean_latency_ms": (
            sum(latencies) / len(latencies)
            if latencies
            else None
        ),
        **token_totals,
        "failed_case_ids": [
            record["case_id"]
            for record in records
            if not record.get("overall_pass")
        ],
    }


def write_results(
    output_dir: Path,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    details_path = output_dir / "cases.jsonl"

    with details_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    summary_path = output_dir / "summary.json"

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    csv_path = output_dir / "summary.csv"

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(summary.keys()),
        )
        writer.writeheader()
        writer.writerow(summary)


def main() -> None:
    argument_parser = argparse.ArgumentParser()

    argument_parser.add_argument(
        "--dataset",
        default="evaluation/llm_cases.json",
    )

    argument_parser.add_argument(
        "--provider",
        choices=["fixture", "dashscope"],
        default="fixture",
    )

    argument_parser.add_argument(
        "--output-dir",
        required=True,
    )

    argument_parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    argument_parser.add_argument(
        "--case-id",
        action="append",
        default=[],
    )

    args = argument_parser.parse_args()

    cases = load_llm_cases(args.dataset)

    if args.case_id:
        selected = set(args.case_id)
        cases = [
            case
            for case in cases
            if case.case_id in selected
        ]

        missing = selected - {
            case.case_id
            for case in cases
        }

        if missing:
            raise ValueError(
                f"Unknown case IDs: {sorted(missing)}"
            )

    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError(
                "--limit must be greater than zero."
            )

        cases = cases[: args.limit]

    if args.provider == "fixture":
        provider: ResponseProvider = (
            FixtureResponseProvider()
        )
    else:
        provider = DashScopeResponseProvider()

    prompt_builder = GroundedPromptBuilder()
    parser = StructuredResponseParser()
    validator = GroundingValidator()

    records = [
        evaluate_case(
            case,
            provider,
            prompt_builder,
            parser,
            validator,
        )
        for case in cases
    ]

    summary = summarize_records(
        records,
        provider_name=args.provider,
    )

    output_dir = Path(args.output_dir)

    write_results(
        output_dir,
        records,
        summary,
    )

    print(json.dumps(
        {
            "output_dir": str(output_dir),
            **summary,
        },
        ensure_ascii=False,
        indent=2,
    ))

    if summary["overall_pass_count"] != len(records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
