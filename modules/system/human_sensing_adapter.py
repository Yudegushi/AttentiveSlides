"""Convert Member 2 sensing contracts at the system boundary."""

from __future__ import annotations

from dataclasses import dataclass

from modules.common.schemas import GazePrediction, LearningState
from modules.human_sensing.contracts import (
    AOIPrediction as MemberAOIPrediction,
    LearningState as MemberLearningState,
)
from modules.system.adapters import SensingFrame


@dataclass(frozen=True)
class AdaptedSensingFrame:
    """Canonical sensing data plus its validity for a live interaction turn."""

    frame: SensingFrame
    is_valid: bool
    invalid_reason: str | None


class HumanSensingAdapter:
    """Keep Member 2 dataclasses outside the system pipeline."""

    def __init__(self, *, min_confidence: float = 0.35) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be normalized to [0, 1]")
        self.min_confidence = float(min_confidence)

    def adapt(
        self,
        gaze: MemberAOIPrediction,
        learning_state: MemberLearningState,
    ) -> AdaptedSensingFrame:
        if gaze.slide_id is None:
            raise ValueError("Member 2 AOIPrediction must include the current slide_id")

        invalid_reason = self._invalid_reason(gaze, learning_state)
        is_valid = invalid_reason is None
        alternatives = (
            self._alternative_targets(gaze.candidate_scores) if is_valid else []
        )
        predicted_aoi_id = gaze.predicted_aoi_id if is_valid else None
        confidence = gaze.confidence if is_valid else 0.0

        return AdaptedSensingFrame(
            frame=SensingFrame(
                gaze_prediction=GazePrediction(
                    slide_id=int(gaze.slide_id),
                    gaze_grid=gaze.gaze_grid,
                    predicted_aoi_id=predicted_aoi_id,
                    confidence=float(confidence),
                    stable_duration_sec=float(gaze.stable_duration_sec),
                    alternative_targets=alternatives,
                ),
                learning_state=LearningState(
                    face_detected=learning_state.face_detected,
                    screen_facing_score=float(learning_state.screen_facing_score),
                    yawn_detected=learning_state.yawn_detected,
                    yawn_count_last_3min=int(learning_state.yawn_count_last_3min),
                    eyes_closed=learning_state.eyes_closed,
                    eye_closure_duration_sec=float(learning_state.eye_closure_duration_sec),
                    head_down=learning_state.head_down,
                    fatigue_signal_score=float(learning_state.fatigue_signal_score),
                    possible_review_needed=learning_state.possible_review_needed,
                ),
            ),
            is_valid=is_valid,
            invalid_reason=invalid_reason,
        )

    def _invalid_reason(
        self,
        gaze: MemberAOIPrediction,
        learning_state: MemberLearningState,
    ) -> str | None:
        if not learning_state.face_detected:
            return "no_face"
        if gaze.gaze_grid == "unknown":
            return "unknown_grid"
        if gaze.predicted_aoi_id is None:
            return "no_target"
        if gaze.confidence < self.min_confidence:
            return "low_confidence"
        return None

    @staticmethod
    def _alternative_targets(candidate_scores: dict[str, float]) -> list[dict[str, float | str]]:
        return [
            {"aoi_id": aoi_id, "score": float(score)}
            for aoi_id, score in sorted(
                candidate_scores.items(),
                key=lambda item: (-float(item[1]), item[0]),
            )
        ]
