"""Evaluate scenario-level intent, AOI, confirmation, and adaptive behavior."""

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


FIELDS = (
    ("intent_accuracy", "intent", lambda result: result.resolved_query.intent),
    ("resolved_aoi_accuracy", "resolved_aoi_id", lambda result: result.resolved_query.resolved_aoi_id),
    ("confirmation_mode_accuracy", "confirmation_mode", lambda result: result.resolved_query.confirmation_mode),
    ("adaptive_strategy_accuracy", "adaptive_strategy", lambda result: result.resolved_query.adaptive_strategy),
)


def evaluate_scenarios() -> dict[str, Any]:
    scenarios = load_scenarios()
    rows = []
    correct_counts = {metric: 0 for metric, _, _ in FIELDS}

    for scenario in scenarios:
        result = run_interaction(
            transcript=scenario.transcript,
            gaze_prediction=scenario.gaze_prediction,
            learning_state=scenario.learning_state,
            confirmed_aoi_id=scenario.confirmed_aoi_id,
        )
        checks = {}
        for metric, expected_key, getter in FIELDS:
            actual = getter(result)
            expected = scenario.expected.get(expected_key)
            passed = actual == expected
            checks[expected_key] = {"expected": expected, "actual": actual, "passed": passed}
            correct_counts[metric] += int(passed)

        rows.append({"name": scenario.name, "checks": checks})

    total = len(scenarios)
    metrics = {
        metric: round(correct_counts[metric] / total, 3) if total else 0.0
        for metric, _, _ in FIELDS
    }
    return {"total_scenarios": total, "metrics": metrics, "rows": rows}


def main() -> None:
    print(json.dumps(evaluate_scenarios(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
