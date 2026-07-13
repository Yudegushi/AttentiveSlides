"""Recorded deterministic smoke test for Main UI Tutor integration."""

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
from modules.common.llm_schemas import (
    LLMUsage,
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
    RawLLMResponse,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
)


class StaticClient:
    provider = "smoke_provider"
    model = "smoke_model"

    def generate(
        self,
        messages,
    ) -> RawLLMResponse:
        del messages

        payload = {
            "response_mode": "explain",
            "answer": (
                "AOI means Area of Interest."
            ),
            "decision_summary": (
                "The answer used the confirmed AOI."
            ),
            "claims": [
                {
                    "claim": (
                        "AOI means Area of Interest."
                    ),
                    "support": "direct",
                    "source_ids": [
                        "slide_001_aoi_definition"
                    ],
                }
            ],
            "external_knowledge_used": False,
            "uncertainty_note": None,
            "active_recall_question": None,
        }

        return RawLLMResponse(
            provider=self.provider,
            model=self.model,
            raw_text=json.dumps(payload),
            latency_ms=80.0,
            usage=LLMUsage(
                prompt_tokens=90,
                completion_tokens=30,
                total_tokens=120,
            ),
            request_id="private_smoke_id",
        )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

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
                name="AOI definition",
            ),
        ),
    )

    interaction = InteractionInput(
        interaction_id="main_smoke_001",
        deck_id="smoke_deck",
        slide_id=1,
        mode="manual",
        target=TargetInput(
            source="manual_aoi",
            slide_id=1,
            selected_aoi_id="definition",
        ),
        intent=IntentInput(
            source="typed_text",
            text="explain this",
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

    generation = generate_main_tutor_response(
        {
            "interaction": (
                interaction.to_dict()
            ),
            "confirmed_context": (
                "AOI means Area of Interest."
            ),
        },
        slide=slide,
        agent=GroundedTutorAgent(
            llm_client=StaticClient(),
            max_retries=1,
        ),
        cloud_text_allowed=True,
        api_configured=True,
    )

    session_payload = (
        generation.to_session_payload()
    )

    serialized = json.dumps(
        session_payload,
        ensure_ascii=False,
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
        "confirmed_aoi_preserved": (
            generation.result
            .request
            .confirmed_aoi_id
            == "definition"
        ),
        "confirmed_aoi_cited": (
            generation.xai_view[
                "validation"
            ][
                "confirmed_aoi_cited"
            ]
            is True
        ),
        "answer_available": bool(
            generation.public_response[
                "answer"
            ]
        ),
        "raw_response_not_exposed": (
            "raw_response"
            not in serialized
        ),
        "request_id_not_exposed": (
            "private_smoke_id"
            not in serialized
        ),
    }

    payload = base_record(
        "main_tutor_integration_smoke"
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
