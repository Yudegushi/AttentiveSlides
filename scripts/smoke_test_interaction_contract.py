"""Recorded smoke test for the unified interaction contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_smoke_common import (
    base_record,
    write_record,
)
from modules.common.interaction_contracts import (
    ConfirmationInput,
    InteractionInput,
    IntentInput,
    TargetCandidate,
    TargetInput,
)
from modules.common.schemas import AOI
from modules.interaction.interaction_contract_adapter import (
    resolve_interaction_input,
)


def make_aois() -> list[AOI]:
    return [
        AOI(
            aoi_id="left_text",
            bbox=[0.05, 0.1, 0.45, 0.8],
            type="text",
            text="Fixation definition.",
        ),
        AOI(
            aoi_id="right_figure",
            bbox=[0.5, 0.1, 0.95, 0.8],
            type="figure",
            text="Saccade diagram.",
        ),
        AOI(
            aoi_id="whole_slide",
            bbox=[0.0, 0.0, 1.0, 1.0],
            type="whole_slide",
            text="Whole slide text.",
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        required=True,
    )
    args = parser.parse_args()

    aois = make_aois()

    manual = InteractionInput(
        interaction_id="smoke_manual_001",
        deck_id="demo_deck",
        slide_id=5,
        mode="manual",
        target=TargetInput(
            source="manual_rectangle",
            slide_id=5,
            bbox=(0.5, 0.1, 0.95, 0.8),
            selected_aoi_id="right_figure",
        ),
        intent=IntentInput(
            source="typed_text",
            text="explain this",
        ),
        confirmation=ConfirmationInput(
            confirmed=True,
            source="explicit_user_confirmation",
            confirmed_aoi_id="right_figure",
        ),
    )

    sensor = InteractionInput(
        interaction_id="smoke_sensor_001",
        deck_id="demo_deck",
        slide_id=5,
        mode="sensor_assisted",
        target=TargetInput(
            source="gaze_prediction",
            slide_id=5,
            predicted_aoi_id="right_figure",
            confidence=0.84,
            alternatives=(
                TargetCandidate(
                    aoi_id="right_figure",
                    score=0.84,
                ),
            ),
        ),
        intent=IntentInput(
            source="speech_transcript",
            text="explain this",
            source_confidence=0.95,
        ),
        confirmation=ConfirmationInput(
            confirmed=True,
            source="automatic_high_confidence",
        ),
    )

    correction = InteractionInput(
        interaction_id="smoke_correction_001",
        deck_id="demo_deck",
        slide_id=5,
        mode="manual",
        target=TargetInput(
            source="manual_rectangle",
            slide_id=5,
            bbox=(0.4, 0.1, 0.7, 0.8),
            selected_aoi_id="right_figure",
        ),
        intent=IntentInput(
            source="typed_text",
            text="explain this",
        ),
        confirmation=ConfirmationInput(
            confirmed=True,
            source="manual_correction",
            confirmed_aoi_id="left_text",
            corrected_from_aoi_id="right_figure",
        ),
    )

    manual_result = resolve_interaction_input(
        manual,
        aois=aois,
    )
    sensor_result = resolve_interaction_input(
        sensor,
        aois=aois,
    )
    correction_result = (
        resolve_interaction_input(
            correction,
            aois=aois,
        )
    )

    checks = {
        "manual_resolved": (
            manual_result.resolved_query
            .resolved_aoi_id
            == "right_figure"
        ),
        "manual_intent_parsed": (
            manual_result.resolved_query.intent
            == "explain"
        ),
        "manual_provenance_preserved": (
            manual_result.provenance
            .target_source
            == "manual_rectangle"
        ),
        "sensor_same_resolved_query_contract": (
            sensor_result.resolved_query
            .resolved_aoi_id
            == "right_figure"
        ),
        "automatic_confidence_preserved": (
            sensor_result.resolved_query
            .target_confidence
            == 0.84
        ),
        "manual_correction_applied": (
            correction_result.resolved_query
            .resolved_aoi_id
            == "left_text"
        ),
        "correction_recorded": (
            correction_result.provenance
            .user_corrected
            is True
        ),
    }

    payload = base_record(
        "interaction_contract_smoke"
    )

    payload.update({
        "passed": all(checks.values()),
        "checks": checks,
        "manual_result": (
            manual_result.to_dict()
        ),
        "sensor_result": (
            sensor_result.to_dict()
        ),
        "correction_result": (
            correction_result.to_dict()
        ),
    })

    write_record(
        args.output,
        payload,
    )

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
