"""Focused tests for observable-signal response adaptation."""

from modules.common.schemas import IntentResult, LearningState
from modules.interaction.adaptive_policy import select_adaptive_strategy


def test_long_gaze_dwell_does_not_override_explain_mode() -> None:
    strategy = select_adaptive_strategy(
        LearningState(),
        IntentResult(
            intent="explain",
            confidence=0.86,
            has_deictic_reference=False,
            explicit_target_hint=None,
            transcript="Explain this concept.",
        ),
        history=None,
        resolved_aoi_id="llm_aoi_2",
        stable_duration_sec=6.082,
    )

    assert strategy == "normal"
