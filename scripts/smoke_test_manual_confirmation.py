"""Recorded smoke test for manual confirmation and correction."""

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
from modules.common.schemas import AOI
from modules.system.manual_confirmation import (
    assess_manual_confirmation,
    build_manual_confirmation_preview,
    confirm_manual_interaction,
)
from modules.system.manual_intent import (
    make_typed_intent_input,
    resolve_manual_intent,
)


def make_aois() -> list[AOI]:
    return [
        AOI(
            aoi_id="definition",
            bbox=[
                0.05,
                0.10,
                0.45,
                0.80,
            ],
            type="text",
            text="Fixation definition.",
            name="Definition",
        ),
        AOI(
            aoi_id="diagram",
            bbox=[
                0.50,
                0.10,
                0.95,
                0.80,
            ],
            type="figure",
            text="Saccade diagram.",
            name="Diagram",
        ),
        AOI(
            aoi_id="whole_slide",
            bbox=[
                0.0,
                0.0,
                1.0,
                1.0,
            ],
            type="whole_slide",
            text=(
                "Fixation definition. "
                "Saccade diagram."
            ),
            name="Whole slide",
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    resolution = resolve_manual_intent(
        make_typed_intent_input(
            "explain this"
        )
    )

    preview = build_manual_confirmation_preview(
        deck_id="smoke_deck",
        slide_id=1,
        target_scope="Manual region",
        bbox=[
            0.10,
            0.10,
            0.90,
            0.80,
        ],
        selected_aoi_ids=[
            "definition",
            "diagram",
        ],
        selection_matches=[
            {
                "aoi_id": "definition",
                "score": 0.85,
            },
            {
                "aoi_id": "diagram",
                "score": 0.72,
            },
        ],
        slide_text=(
            "Fixation definition. "
            "Saccade diagram."
        ),
        aois=make_aois(),
        intent_resolution=resolution,
    )

    explicit_assessment = (
        assess_manual_confirmation(
            preview,
            selected_target_id=(
                "definition"
            ),
        )
    )

    explicit_result = (
        confirm_manual_interaction(
            preview,
            selected_target_id=(
                "definition"
            ),
            interaction_id=(
                "smoke_confirm_001"
            ),
        )
    )

    correction_result = (
        confirm_manual_interaction(
            preview,
            selected_target_id=(
                "diagram"
            ),
            interaction_id=(
                "smoke_confirm_002"
            ),
        )
    )

    whole_slide_result = (
        confirm_manual_interaction(
            preview,
            selected_target_id=(
                "whole_slide"
            ),
            interaction_id=(
                "smoke_confirm_003"
            ),
        )
    )

    checks = {
        "preview_ready": (
            explicit_assessment.ready
        ),
        "explicit_confirmation_created": (
            explicit_result
            .interaction
            .confirmation
            .source
            == "explicit_user_confirmation"
        ),
        "explicit_target_preserved": (
            explicit_result
            .interaction
            .confirmation
            .confirmed_aoi_id
            == "definition"
        ),
        "manual_correction_created": (
            correction_result
            .interaction
            .confirmation
            .source
            == "manual_correction"
        ),
        "correction_origin_recorded": (
            correction_result
            .interaction
            .confirmation
            .corrected_from_aoi_id
            == "definition"
        ),
        "whole_slide_override_created": (
            whole_slide_result
            .interaction
            .target
            .source
            == "whole_slide"
        ),
        "typed_intent_preserved": (
            explicit_result
            .interaction
            .intent
            .source
            == "typed_text"
        ),
        "privacy_metadata_preserved": (
            explicit_result
            .interaction
            .metadata[
                "privacy_mode"
            ]
            == (
                "camera_and_microphone_disabled"
            )
        ),
    }

    payload = base_record(
        "manual_confirmation_smoke"
    )

    payload.update(
        {
            "passed": all(
                checks.values()
            ),
            "checks": checks,
            "preview": preview.to_dict(),
            "assessment": (
                explicit_assessment.to_dict()
            ),
            "explicit_result": (
                explicit_result.to_dict()
            ),
            "correction_result": (
                correction_result.to_dict()
            ),
            "whole_slide_result": (
                whole_slide_result.to_dict()
            ),
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
