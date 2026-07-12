"""Recorded smoke test for grounded prompt construction."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_smoke_common import base_record, write_record
from modules.common.llm_schemas import (
    ContextSource,
    TutorLLMRequest,
)
from modules.tutor.grounded_prompt import (
    GroundedPromptBuilder,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    request = TutorLLMRequest(
        query_id="prompt_smoke_001",
        deck_id="lecture_2",
        slide_id=2,
        question="fixation 和 saccade 有什么区别？",
        intent="compare",
        response_mode="compare",
        confirmed_aoi_id="aoi_fixation",
        sources=[
            ContextSource(
                source_id="slide_02_aoi_01",
                slide_id=2,
                source_kind="confirmed_aoi",
                aoi_id="aoi_fixation",
                text=(
                    "Fixation is maintaining gaze "
                    "on a single location."
                ),
            ),
            ContextSource(
                source_id="slide_02_aoi_02",
                slide_id=2,
                source_kind="current_slide",
                aoi_id="aoi_saccade",
                text=(
                    "Saccade is a rapid eye movement "
                    "between fixations."
                ),
            ),
        ],
        allow_external_knowledge=False,
        response_language="zh-CN",
    )

    prompt = GroundedPromptBuilder().build(request)
    messages = prompt.messages()

    confirmed_position = prompt.user_prompt.index(
        "slide_02_aoi_01"
    )
    current_slide_position = prompt.user_prompt.index(
        "slide_02_aoi_02"
    )

    checks = {
        "two_messages": len(messages) == 2,
        "system_role": messages[0]["role"] == "system",
        "user_role": messages[1]["role"] == "user",
        "json_only_instruction": (
            "Return exactly one valid JSON object"
            in prompt.system_prompt
        ),
        "chain_of_thought_not_requested": (
            "Do not reveal hidden chain-of-thought"
            in prompt.system_prompt
        ),
        "external_knowledge_disabled": (
            '"allow_external_knowledge": false'
            in prompt.user_prompt
        ),
        "confirmed_source_first": (
            confirmed_position
            < current_slide_position
        ),
        "source_ids_present": all(
            source_id in prompt.user_prompt
            for source_id in {
                "slide_02_aoi_01",
                "slide_02_aoi_02",
            }
        ),
        "prompt_injection_defense_present": (
            "untrusted educational content"
            in prompt.system_prompt
        ),
    }

    payload = base_record("grounded_prompt_smoke")
    payload.update({
        "passed": all(checks.values()),
        "checks": checks,
        "character_count": prompt.character_count(),
        "messages": messages,
    })

    write_record(args.output, payload)

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
