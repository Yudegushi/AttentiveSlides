"""Recorded deterministic smoke test for the public XAI payload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_smoke_common import (
    base_record,
    write_record,
)
from modules.system.xai_view_model import (
    build_xai_view_model,
)
from tests.test_xai_view_model import (
    make_grounded_result,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        required=True,
    )
    args = parser.parse_args()

    view = build_xai_view_model(
        make_grounded_result()
    )

    serialized = json.dumps(
        view,
        ensure_ascii=False,
    )

    checks = {
        "validation_valid": (
            view["validation"]["is_valid"]
        ),
        "citation_coverage_complete": (
            view["validation"][
                "citation_coverage"
            ]
            == 1.0
        ),
        "confirmed_aoi_cited": (
            view["validation"][
                "confirmed_aoi_cited"
            ]
            is True
        ),
        "two_claims_exposed": (
            len(view["claims"]) == 2
        ),
        "two_sources_exposed": (
            len(view["sources"]) == 2
        ),
        "raw_response_not_exposed": (
            "raw_response" not in serialized
        ),
        "request_id_not_exposed": (
            "private_request_id"
            not in serialized
        ),
        "chain_of_thought_not_exposed": (
            not view["safety"][
                "raw_chain_of_thought_exposed"
            ]
        ),
    }

    payload = base_record(
        "streamlit_xai_view_model_smoke"
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
