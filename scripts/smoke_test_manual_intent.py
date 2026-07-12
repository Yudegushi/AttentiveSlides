"""Recorded smoke test for manual typed-intent resolution."""

from __future__ import annotations

import argparse
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
from modules.system.manual_intent import (
    QUICK_INTENT_ACTIONS,
    assess_intent_target,
    make_quick_action_intent_input,
    make_typed_intent_input,
    resolve_manual_intent,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    typed = resolve_manual_intent(
        make_typed_intent_input(
            "explain this"
        )
    )

    explicit = resolve_manual_intent(
        make_quick_action_intent_input(
            "summarize"
        )
    )

    compare = resolve_manual_intent(
        make_quick_action_intent_input(
            "compare"
        )
    )

    unknown = resolve_manual_intent(
        make_typed_intent_input(
            "do something interesting"
        )
    )

    typed_assessment = (
        assess_intent_target(
            typed,
            target_available=True,
            selected_aoi_count=1,
        )
    )

    compare_assessment = (
        assess_intent_target(
            compare,
            target_available=True,
            selected_aoi_count=1,
        )
    )

    unknown_assessment = (
        assess_intent_target(
            unknown,
            target_available=True,
            selected_aoi_count=1,
        )
    )

    checks = {
        "typed_explain_resolved": (
            typed.intent == "explain"
        ),
        "typed_source_preserved": (
            typed.intent_input.source
            == "typed_text"
        ),
        "typed_ready": (
            typed_assessment.ready
        ),
        "ui_action_summarize_resolved": (
            explicit.intent
            == "summarize"
        ),
        "ui_action_source_preserved": (
            explicit.intent_input.source
            == "ui_action"
        ),
        "ui_action_confidence_one": (
            explicit.intent_result
            .confidence
            == 1.0
        ),
        "compare_warning_available": (
            compare_assessment.ready
            and compare_assessment.status
            == "warning"
        ),
        "unknown_blocked": (
            not unknown_assessment.ready
            and unknown_assessment.status
            == "blocked"
        ),
        "six_quick_actions_available": (
            len(QUICK_INTENT_ACTIONS)
            == 6
        ),
    }

    payload = base_record(
        "manual_intent_smoke"
    )

    payload.update(
        {
            "passed": all(
                checks.values()
            ),
            "checks": checks,
            "typed_resolution": (
                typed.to_dict()
            ),
            "typed_assessment": (
                typed_assessment.to_dict()
            ),
            "explicit_resolution": (
                explicit.to_dict()
            ),
            "compare_assessment": (
                compare_assessment.to_dict()
            ),
            "unknown_resolution": (
                unknown.to_dict()
            ),
            "unknown_assessment": (
                unknown_assessment.to_dict()
            ),
            "quick_actions": [
                action.to_dict()
                for action
                in QUICK_INTENT_ACTIONS
            ],
        }
    )

    write_record(
        arguments.output,
        payload,
    )

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
