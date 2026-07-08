"""Evaluate end-to-end response fields for scenario fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.system.pipeline import run_interaction
from modules.system.scenarios import load_scenarios


def evaluate_outputs() -> dict[str, Any]:
    scenarios = load_scenarios()
    rows = []
    passed = 0

    for scenario in scenarios:
        result = run_interaction(
            transcript=scenario.transcript,
            gaze_prediction=scenario.gaze_prediction,
            learning_state=scenario.learning_state,
            confirmed_aoi_id=scenario.confirmed_aoi_id,
        )
        expected_response_mode = scenario.expected.get("response_mode")
        response_mode_passed = result.tutor_response.response_mode == expected_response_mode
        pending_ui_passed = True
        if expected_response_mode == "pending_confirmation":
            pending_ui_passed = (
                result.ui_state.confirmation_message is not None
                and result.ui_state.response["answer"] is None
            )

        row_passed = response_mode_passed and pending_ui_passed
        passed += int(row_passed)
        rows.append(
            {
                "name": scenario.name,
                "response_mode": {
                    "expected": expected_response_mode,
                    "actual": result.tutor_response.response_mode,
                    "passed": response_mode_passed,
                },
                "pending_ui_passed": pending_ui_passed,
                "passed": row_passed,
            }
        )

    total = len(scenarios)
    return {
        "total_scenarios": total,
        "output_accuracy": round(passed / total, 3) if total else 0.0,
        "rows": rows,
    }


def main() -> None:
    print(json.dumps(evaluate_outputs(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
