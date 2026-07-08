"""Run the first mock-driven AttentiveSlides system loop."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.common.schemas import GazePrediction, InteractionLogEvent, LearningState, Transcript
from modules.interaction.intent_parser import parse_intent
from modules.interaction.interaction_history import InteractionHistory
from modules.interaction.reference_resolver import resolve_reference
from modules.logging.interaction_logger import InteractionLogger
from modules.tutor.context_retriever import MockDeckStore
from modules.tutor.tutor_agent import TutorAgent


def main() -> None:
    deck_store = MockDeckStore()
    aois = deck_store.get_aois(slide_id=5)
    demo_log_history = InteractionHistory()
    tutor = TutorAgent()
    logger = InteractionLogger("data/logs/demo_interactions.jsonl")

    cases = [
        {
            "name": "high-confidence explain this",
            "transcript": "解释这个",
            "gaze": GazePrediction(
                slide_id=5,
                gaze_grid="middle_right",
                predicted_aoi_id="right_figure",
                confidence=0.76,
                stable_duration_sec=2.3,
            ),
            "learning_state": LearningState(),
        },
        {
            "name": "summarize whole slide",
            "transcript": "总结这一页",
            "gaze": GazePrediction(
                slide_id=5,
                gaze_grid="middle_center",
                predicted_aoi_id=None,
                confidence=0.0,
            ),
            "learning_state": LearningState(),
        },
        {
            "name": "medium-confidence quiz this concept",
            "transcript": "考我一下这个概念",
            "gaze": GazePrediction(
                slide_id=5,
                gaze_grid="bottom_right",
                predicted_aoi_id="right_figure",
                confidence=0.55,
                stable_duration_sec=1.8,
                alternative_targets=[
                    {"aoi_id": "right_figure", "score": 0.55},
                    {"aoi_id": "bottom_caption", "score": 0.51},
                ],
            ),
            "learning_state": LearningState(),
        },
        {
            "name": "explicit target overrides low gaze",
            "transcript": "解释右边这个图",
            "gaze": GazePrediction(
                slide_id=5,
                gaze_grid="bottom_left",
                predicted_aoi_id="bottom_caption",
                confidence=0.30,
            ),
            "learning_state": LearningState(),
        },
        {
            "name": "low screen-facing score asks confirmation",
            "transcript": "解释这个",
            "gaze": GazePrediction(
                slide_id=5,
                gaze_grid="middle_right",
                predicted_aoi_id="right_figure",
                confidence=0.78,
                stable_duration_sec=2.0,
            ),
            "learning_state": LearningState(screen_facing_score=0.35),
        },
    ]

    results = []
    for case in cases:
        history = InteractionHistory()
        start = time.perf_counter()
        intent = parse_intent(Transcript(case["transcript"]))
        resolved = resolve_reference(
            intent_result=intent,
            gaze_prediction=case["gaze"],
            learning_state=case["learning_state"],
            aois=aois,
            history=history,
            deck_id=deck_store.deck_id,
        )
        response = tutor.answer(resolved, deck_state=deck_store, history=history)
        latency_ms = (time.perf_counter() - start) * 1000

        log_event = InteractionLogEvent(
            query_id=resolved.query_id,
            timestamp=time.time(),
            deck_id=resolved.deck_id,
            slide_id=resolved.slide_id,
            transcript=resolved.transcript,
            intent=resolved.intent,
            predicted_aoi_id=case["gaze"].predicted_aoi_id,
            resolved_aoi_id=resolved.resolved_aoi_id,
            confirmed_aoi_id=resolved.resolved_aoi_id if not resolved.needs_confirmation else None,
            target_confidence=resolved.target_confidence,
            needs_confirmation=resolved.needs_confirmation,
            confirmation_mode=resolved.confirmation_mode,
            user_corrected=False,
            adaptive_strategy=resolved.adaptive_strategy,
            response_mode=response.response_mode,
            latency_ms=round(latency_ms, 2),
        )
        logger.log_interaction(log_event)
        demo_log_history.add(log_event)

        results.append(
            {
                "case": case["name"],
                "resolved_query": asdict(resolved),
                "tutor_response": asdict(response),
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nWrote demo log to {Path('data/logs/demo_interactions.jsonl').resolve()}")


if __name__ == "__main__":
    main()
