"""Run scenario-driven AttentiveSlides Member 3/4 local demo."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.logging.interaction_logger import InteractionLogger
from modules.system.adapters import (
    MockManifestSlideProvider,
    ScenarioSensingProvider,
    ScenarioTranscriptProvider,
    build_pipeline_input_bundle,
    run_interaction_from_bundle,
)
from modules.system.scenarios import load_scenarios


def main() -> None:
    log_path = Path("data/logs/demo_interactions.jsonl")
    if log_path.exists():
        log_path.unlink()

    logger = InteractionLogger(log_path)
    results = []
    slide_provider = MockManifestSlideProvider()

    for scenario in load_scenarios():
        bundle = build_pipeline_input_bundle(
            slide_provider=slide_provider,
            transcript_provider=ScenarioTranscriptProvider(scenario),
            sensing_provider=ScenarioSensingProvider(scenario),
            slide_id=scenario.gaze_prediction.slide_id,
        )
        result = run_interaction_from_bundle(
            bundle,
            confirmed_aoi_id=scenario.confirmed_aoi_id,
            logger=logger,
        )
        results.append(
            {
                "case": scenario.name,
                "intent": result.resolved_query.intent,
                "resolved_aoi_id": result.resolved_query.resolved_aoi_id,
                "confirmation_mode": result.resolved_query.confirmation_mode,
                "adaptive_strategy": result.resolved_query.adaptive_strategy,
                "response_mode": result.tutor_response.response_mode,
                "confirmed_aoi_id": result.log_event.confirmed_aoi_id,
                "user_corrected": result.log_event.user_corrected,
                "ui_state": asdict(result.ui_state),
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nWrote demo log to {log_path.resolve()}")


if __name__ == "__main__":
    main()
