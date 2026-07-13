"""Recorded real DashScope smoke test for the Main UI tutor bridge."""

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
from modules.common.interaction_contracts import (
    ConfirmationInput,
    InteractionInput,
    IntentInput,
    TargetInput,
)
from modules.common.schemas import (
    AOI,
)
from modules.system.main_tutor_integration import (
    generate_main_tutor_response,
)
from modules.system.main_ui_state import (
    MainUISlide,
)
from modules.tutor.api_llm_client import (
    OpenAICompatibleLLMClient,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    slide = MainUISlide(
        slide_id=2,
        slide_text=(
            "Fixation is maintaining gaze "
            "on a single location."
        ),
        neighbor_slide_text="",
        aois=(
            AOI(
                aoi_id="fixation",
                bbox=[
                    0.1,
                    0.1,
                    0.9,
                    0.8,
                ],
                type="text",
                text=(
                    "Fixation is maintaining gaze "
                    "on a single location."
                ),
                name="Fixation",
            ),
        ),
    )

    interaction = InteractionInput(
        interaction_id="dashscope_main_001",
        deck_id="lecture_2",
        slide_id=2,
        mode="manual",
        target=TargetInput(
            source="manual_aoi",
            slide_id=2,
            selected_aoi_id="fixation",
        ),
        intent=IntentInput(
            source="typed_text",
            text="请解释 fixation。",
            language="zh-CN",
        ),
        confirmation=ConfirmationInput(
            confirmed=True,
            source=(
                "explicit_user_confirmation"
            ),
            confirmed_aoi_id="fixation",
        ),
        metadata={
            "confirmed_context": (
                "Fixation is maintaining gaze "
                "on a single location."
            ),
        },
    )

    client = (
        OpenAICompatibleLLMClient
        .from_env()
    )

    generation = generate_main_tutor_response(
        {
            "interaction": (
                interaction.to_dict()
            ),
            "confirmed_context": (
                "Fixation is maintaining gaze "
                "on a single location."
            ),
        },
        slide=slide,
        agent=GroundedTutorAgent(
            llm_client=client,
            max_retries=1,
        ),
        cloud_text_allowed=True,
        api_configured=True,
    )

    session_payload = (
        generation.to_session_payload()
    )

    checks = {
        "status_success": (
            generation.result.status
            == "success"
        ),
        "validation_valid": (
            generation.result
            .validation
            .is_valid
        ),
        "fallback_not_used": (
            not generation.result
            .call_result
            .fallback_used
        ),
        "confirmed_aoi_cited": (
            generation.xai_view[
                "validation"
            ][
                "confirmed_aoi_cited"
            ]
            is True
        ),
        "external_knowledge_not_used": (
            not generation.result
            .call_result
            .response
            .external_knowledge_used
        ),
        "answer_available": bool(
            generation.public_response[
                "answer"
            ]
        ),
    }

    payload = base_record(
        "dashscope_main_tutor_smoke"
    )

    payload.update(
        {
            "passed": all(
                checks.values()
            ),
            "checks": checks,
            "session_payload": (
                session_payload
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
