"""Run one AttentiveSlides interaction from terminal text with mock sensing."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.common.schemas import GazePrediction, LearningState
from modules.system.pipeline import run_interaction


GAZE_PRESETS = {
    "right_figure_high": GazePrediction(5, "middle_right", "right_figure", 0.76, stable_duration_sec=2.3),
    "right_figure_medium": GazePrediction(
        5,
        "bottom_right",
        "right_figure",
        0.55,
        stable_duration_sec=1.8,
        alternative_targets=[
            {"aoi_id": "right_figure", "score": 0.55},
            {"aoi_id": "bottom_caption", "score": 0.51},
        ],
    ),
    "low_confidence_formula": GazePrediction(5, "bottom_left", "bottom_formula", 0.2, stable_duration_sec=0.4),
    "none": GazePrediction(5, "middle_center", None, 0.0),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one local mock AttentiveSlides interaction.")
    parser.add_argument("transcript", nargs="?", help="User transcript text. If omitted, read from stdin.")
    parser.add_argument("--gaze", choices=sorted(GAZE_PRESETS), default="right_figure_high")
    parser.add_argument("--confirmed-aoi-id")
    parser.add_argument("--screen-facing-score", type=float, default=1.0)
    args = parser.parse_args()

    transcript = args.transcript or input("Transcript: ").strip()
    result = run_interaction(
        transcript=transcript,
        gaze_prediction=GAZE_PRESETS[args.gaze],
        learning_state=LearningState(screen_facing_score=args.screen_facing_score),
        confirmed_aoi_id=args.confirmed_aoi_id,
    )

    print(
        json.dumps(
            {
                "resolved_query": asdict(result.resolved_query),
                "tutor_response": asdict(result.tutor_response),
                "ui_state": asdict(result.ui_state),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
