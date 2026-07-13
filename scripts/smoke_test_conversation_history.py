"""Recorded deterministic smoke test for multi-turn history."""

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
from modules.common.interaction_contracts import (
    ConfirmationInput,
    InteractionInput,
    IntentInput,
    TargetInput,
)
from modules.common.schemas import AOI
from modules.system.conversation_history import (
    build_conversation_turn,
    export_conversation,
    upsert_conversation_turn,
)
from modules.system.main_tutor_integration import (
    build_main_tutor_context,
)
from modules.system.main_ui_state import (
    MainUISlide,
)
from modules.tutor.tutor_request_adapter import (
    TutorRequestAdapter,
)


def make_interaction(
    interaction_id: str,
    command: str,
) -> dict:
    interaction = InteractionInput(
        interaction_id=interaction_id,
        deck_id="history_smoke_deck",
        slide_id=1,
        mode="manual",
        target=TargetInput(
            source="manual_aoi",
            slide_id=1,
            selected_aoi_id="definition",
        ),
        intent=IntentInput(
            source="typed_text",
            text=command,
        ),
        confirmation=ConfirmationInput(
            confirmed=True,
            source=(
                "explicit_user_confirmation"
            ),
            confirmed_aoi_id="definition",
        ),
        metadata={
            "confirmed_context": (
                "AOI means Area of Interest."
            ),
        },
    )

    return {
        "interaction": interaction.to_dict(),
        "confirmed_context": (
            "AOI means Area of Interest."
        ),
    }


def make_turn(
    interaction_id: str,
    command: str,
    answer: str,
):
    return build_conversation_turn(
        confirmed_interaction=(
            make_interaction(
                interaction_id,
                command,
            )
        ),
        tutor_result={
            "query_id": (
                f"query_{interaction_id}"
            ),
            "answer": answer,
            "response_mode": "explain",
            "decision_summary": (
                "Used confirmed AOI."
            ),
            "active_recall_question": None,
            "validation_is_valid": True,
            "fallback_used": False,
        },
        llm_xai={
            "claims": [
                {
                    "source_ids": [
                        "slide_001_aoi_definition"
                    ]
                }
            ],
            "validation": {
                "is_valid": True,
            },
        },
        integrated_xai={
            "questions": {
                "reliability": {
                    "level": "supported"
                }
            }
        },
        timestamp_utc=(
            "2026-07-13T00:00:00+00:00"
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    turns: list[dict] = []

    turns = upsert_conversation_turn(
        turns,
        make_turn(
            "turn_001",
            "explain this",
            "AOI means Area of Interest.",
        ),
    )

    turns = upsert_conversation_turn(
        turns,
        make_turn(
            "turn_002",
            "explain this more simply",
            "AOI is a selected region.",
        ),
    )

    current = make_interaction(
        "turn_003",
        "explain how this is used",
    )

    slide = MainUISlide(
        slide_id=1,
        slide_text=(
            "AOI means Area of Interest."
        ),
        neighbor_slide_text="",
        aois=(
            AOI(
                aoi_id="definition",
                bbox=[
                    0.1,
                    0.1,
                    0.9,
                    0.8,
                ],
                type="text",
                text=(
                    "AOI means Area of Interest."
                ),
                name="Definition",
            ),
        ),
    )

    context_build = build_main_tutor_context(
        current,
        slide=slide,
        conversation_turns=turns,
        history_max_items=4,
    )

    request = TutorRequestAdapter().from_context(
        context_build.context
    )

    export_payload = export_conversation(
        deck_id="history_smoke_deck",
        turns=turns,
    )

    history_serialized = json.dumps(
        request.interaction_history,
        ensure_ascii=False,
    ).casefold()

    checks = {
        "two_turns_stored": (
            len(turns) == 2
        ),
        "two_history_items_in_context": (
            len(
                context_build.context
                .interaction_history
            )
            == 2
        ),
        "history_reaches_request": (
            len(
                request.interaction_history
            )
            == 2
        ),
        "current_turn_excluded": (
            "turn_003"
            not in history_serialized
        ),
        "previous_answer_available": (
            "aoi is a selected region"
            in history_serialized
        ),
        "export_has_two_turns": (
            export_payload[
                "turn_count"
            ]
            == 2
        ),
        "raw_response_not_exposed": (
            "raw_response"
            not in history_serialized
        ),
        "provider_request_not_exposed": (
            "provider_request_id"
            not in history_serialized
        ),
        "api_key_not_exposed": (
            "api_key"
            not in history_serialized
        ),
    }

    record = base_record(
        "conversation_history_smoke"
    )

    record.update(
        {
            "passed": all(
                checks.values()
            ),
            "checks": checks,
            "stored_turns": turns,
            "llm_history": (
                request.interaction_history
            ),
            "export": export_payload,
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
