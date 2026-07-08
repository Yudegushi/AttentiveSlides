"""Scenario fixture loading for local Member 3/4 demos and evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.common.schemas import GazePrediction, LearningState


DEFAULT_SCENARIO_PATH = Path("data/scenarios/member3_4_demo_cases.json")


@dataclass(frozen=True)
class InteractionScenario:
    name: str
    transcript: str
    gaze_prediction: GazePrediction
    learning_state: LearningState
    expected: dict[str, Any]
    confirmed_aoi_id: str | None = None


def load_scenarios(path: str | Path = DEFAULT_SCENARIO_PATH) -> list[InteractionScenario]:
    with Path(path).open("r", encoding="utf-8") as file:
        payload = json.load(file)
    return [_scenario_from_dict(item) for item in payload]


def _scenario_from_dict(item: dict[str, Any]) -> InteractionScenario:
    return InteractionScenario(
        name=item["name"],
        transcript=item["transcript"],
        gaze_prediction=GazePrediction(**item["gaze_prediction"]),
        learning_state=LearningState(**item.get("learning_state", {})),
        expected=dict(item.get("expected", {})),
        confirmed_aoi_id=item.get("confirmed_aoi_id"),
    )
