"""Recorded deterministic smoke test for integrated pipeline XAI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )

from llm_smoke_common import (
    base_record,
    write_record,
)
from modules.system.integrated_pipeline_xai import (
    build_integrated_pipeline_xai,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    payload = build_integrated_pipeline_xai(
        target_scope="Manual region",
        manual_bbox=[
            0.10,
            0.12,
            0.48,
            0.82,
        ],
        selection_matches=[
            {
                "aoi_id": "definition",
                "aoi_type": "text",
                "score": 0.91,
                "selection_coverage": 0.88,
                "aoi_coverage": 0.94,
                "intersection_over_union": 0.84,
            }
        ],
        intent_result={
            "intent_input": {
                "source": "typed_text",
                "text": "explain this",
                "explicit_intent": None,
            },
            "intent_result": {
                "intent": "explain",
                "confidence": 0.9,
                "has_deictic_reference": True,
                "explicit_target_hint": None,
            },
            "recognized": True,
            "provenance": [
                "intent source = typed_text",
                "resolved intent = explain",
            ],
        },
        confirmed_interaction={
            "interaction": {
                "interaction_id": (
                    "integrated_xai_smoke"
                ),
                "deck_id": "smoke_deck",
                "slide_id": 1,
                "mode": "manual",
                "target": {
                    "source": (
                        "manual_rectangle"
                    ),
                    "slide_id": 1,
                    "bbox": [
                        0.10,
                        0.12,
                        0.48,
                        0.82,
                    ],
                    "selected_aoi_id": (
                        "definition"
                    ),
                    "alternatives": [],
                },
                "intent": {
                    "source": "typed_text",
                    "text": "explain this",
                    "explicit_intent": None,
                },
                "confirmation": {
                    "confirmed": True,
                    "source": (
                        "explicit_user_confirmation"
                    ),
                    "confirmed_aoi_id": (
                        "definition"
                    ),
                    "corrected_from_aoi_id": None,
                },
                "metadata": {},
            },
            "proposed_aoi_id": "definition",
            "corrected": False,
            "confirmed_context": (
                "AOI means Area of Interest."
            ),
        },
        tutor_result={
            "status": "success",
            "response_mode": "explain",
            "answer": (
                "AOI means Area of Interest."
            ),
            "decision_summary": (
                "The answer uses the "
                "confirmed definition AOI."
            ),
            "external_knowledge_used": False,
            "uncertainty_note": None,
            "validation_is_valid": True,
            "provider": "smoke_provider",
            "model": "smoke_model",
            "latency_ms": 80.0,
            "retry_count": 0,
            "fallback_used": False,
        },
        llm_xai={
            "decision_summary": (
                "The answer uses the "
                "confirmed definition AOI."
            ),
            "claims": [
                {
                    "claim_index": 1,
                    "claim": (
                        "AOI means Area of Interest."
                    ),
                    "support": "direct",
                    "source_ids": [
                        "slide_001_aoi_definition"
                    ],
                    "all_sources_valid": True,
                }
            ],
            "sources": [
                {
                    "source_id": (
                        "slide_001_aoi_definition"
                    ),
                    "source_kind": (
                        "confirmed_aoi"
                    ),
                    "slide_id": 1,
                    "aoi_id": "definition",
                    "title": "Definition",
                    "cited": True,
                    "text_preview": (
                        "AOI means Area of Interest."
                    ),
                }
            ],
            "validation": {
                "is_valid": True,
                "citation_coverage": 1.0,
                "confirmed_aoi_cited": True,
                "issues": [],
            },
            "telemetry": {
                "provider": "smoke_provider",
                "model": "smoke_model",
                "latency_ms": 80.0,
                "retry_count": 0,
                "fallback_used": False,
            },
        },
        cloud_text_allowed=True,
    )

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    ).casefold()

    checks = {
        "pipeline_complete": (
            payload[
                "pipeline_status"
            ]
            == "complete"
        ),
        "target_explained": (
            payload["questions"][
                "target"
            ]["status"]
            == "ready"
        ),
        "intent_explained": (
            payload["questions"][
                "intent"
            ]["recognized"]
        ),
        "answer_grounded": (
            payload["questions"][
                "answer"
            ]["claim_count"]
            == 1
        ),
        "reliability_supported": (
            payload["questions"][
                "reliability"
            ]["level"]
            == "supported"
        ),
        "citation_complete": (
            payload["questions"][
                "reliability"
            ]["citation_coverage"]
            == 1.0
        ),
        "confirmed_aoi_cited": (
            payload["questions"][
                "reliability"
            ]["confirmed_aoi_cited"]
            is True
        ),
        "raw_response_not_exposed": (
            "raw_response"
            not in serialized
        ),
        "internal_reasoning_not_exposed": (
            "chain_of_thought"
            not in serialized
        ),
        "api_key_not_exposed": (
            "api_key"
            not in serialized
        ),
    }

    record = base_record(
        "integrated_pipeline_xai_smoke"
    )

    record.update(
        {
            "passed": all(
                checks.values()
            ),
            "checks": checks,
            "integrated_xai": payload,
        }
    )

    write_record(
        arguments.output,
        record,
    )

    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
