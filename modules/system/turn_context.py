"""Frozen speech-turn context and pure sensing aggregation."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json

from modules.common.schemas import GazePrediction, LearningState
from modules.system.adapters import SensingFrame, SlideFrame, SlideProvider
from modules.system.sensing_snapshot_store import SensingSnapshotStore


@dataclass(frozen=True)
class FrozenTurnContext:
    deck_id: str
    slide_id: int
    speech_started_at: float
    sensing_window_start: float
    manifest_identity: str
    speech_ended_at: float | None = None
    slide_changed_during_turn: bool = False


@dataclass(frozen=True)
class AggregatedSensing:
    frame: SensingFrame
    evidence: list[str]


def manifest_identity_for_frame(frame: SlideFrame) -> str:
    payload = {
        "deck_id": frame.deck_id,
        "slide_id": frame.slide_id,
        "aois": [
            {
                "aoi_id": aoi.aoi_id,
                "bbox": list(aoi.bbox),
                "type": aoi.type,
                "text": aoi.text,
                "name": aoi.name,
            }
            for aoi in frame.aois
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class TurnContextCollector:
    """Freeze start-time slide identity and aggregate only matching snapshots."""

    def __init__(
        self,
        *,
        slide_provider: SlideProvider,
        snapshot_store: SensingSnapshotStore,
        sensing_lookback_seconds: float = 0.5,
        minimum_dwell_seconds: float = 0.15,
        max_sample_dwell_seconds: float = 0.5,
    ) -> None:
        if sensing_lookback_seconds < 0:
            raise ValueError("sensing_lookback_seconds must be non-negative")
        if minimum_dwell_seconds <= 0 or max_sample_dwell_seconds <= 0:
            raise ValueError("dwell thresholds must be positive")
        self.slide_provider = slide_provider
        self.snapshot_store = snapshot_store
        self.sensing_lookback_seconds = float(sensing_lookback_seconds)
        self.minimum_dwell_seconds = float(minimum_dwell_seconds)
        self.max_sample_dwell_seconds = float(max_sample_dwell_seconds)

    def freeze_start(self, *, slide_id: int, speech_started_at: float) -> FrozenTurnContext:
        frame = self.slide_provider.get_slide_frame(slide_id)
        return FrozenTurnContext(
            deck_id=frame.deck_id,
            slide_id=frame.slide_id,
            speech_started_at=float(speech_started_at),
            sensing_window_start=float(speech_started_at) - self.sensing_lookback_seconds,
            manifest_identity=manifest_identity_for_frame(frame),
        )

    def freeze_end(
        self,
        context: FrozenTurnContext,
        *,
        speech_ended_at: float,
        current_slide_id: int,
    ) -> FrozenTurnContext:
        if speech_ended_at < context.speech_started_at:
            raise ValueError("speech_ended_at must not precede speech_started_at")
        return replace(
            context,
            speech_ended_at=float(speech_ended_at),
            slide_changed_during_turn=current_slide_id != context.slide_id,
        )

    def aggregate(self, context: FrozenTurnContext) -> AggregatedSensing:
        if context.speech_ended_at is None:
            raise ValueError("turn context must be frozen at speech end before aggregation")
        snapshots = self.snapshot_store.snapshots_in_window(
            context.slide_id,
            start_processed_at=context.sensing_window_start,
            end_processed_at=context.speech_ended_at,
        )
        valid = [
            snapshot
            for snapshot in snapshots
            if snapshot.is_valid
            and snapshot.invalid_reason is None
            and snapshot.manifest_identity == context.manifest_identity
            and snapshot.frame.gaze_prediction.gaze_grid != "unknown"
            and snapshot.frame.gaze_prediction.predicted_aoi_id not in {None, "whole_slide"}
            and snapshot.frame.gaze_prediction.confidence > 0.0
        ]
        valid.sort(key=lambda snapshot: snapshot.processed_at)
        weights: dict[str, float] = {}
        for index, snapshot in enumerate(valid):
            next_at = (
                valid[index + 1].processed_at
                if index + 1 < len(valid)
                else context.speech_ended_at
            )
            dwell = min(
                self.max_sample_dwell_seconds,
                max(0.0, next_at - snapshot.processed_at),
            )
            target = snapshot.frame.gaze_prediction.predicted_aoi_id
            assert target is not None
            contribution = round(snapshot.frame.gaze_prediction.confidence * dwell, 9)
            weights[target] = round(weights.get(target, 0.0) + contribution, 9)

        total_weight = sum(weights.values())
        ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
        if total_weight < self.minimum_dwell_seconds or not ranked:
            gaze = GazePrediction(
                slide_id=context.slide_id,
                gaze_grid="aggregated",
                predicted_aoi_id=None,
                confidence=0.0,
                stable_duration_sec=round(total_weight, 3),
                alternative_targets=[],
            )
            learning = LearningState(face_detected=False, screen_facing_score=0.0)
            return AggregatedSensing(
                frame=SensingFrame(gaze_prediction=gaze, learning_state=learning),
                evidence=["insufficient matching valid gaze dwell"],
            )

        alternatives = [
            {"aoi_id": target, "score": round(weight / total_weight, 3)}
            for target, weight in ranked[:2]
        ]
        top_target, top_weight = ranked[0]
        latest_learning = valid[-1].frame.learning_state
        gaze = GazePrediction(
            slide_id=context.slide_id,
            gaze_grid="aggregated",
            predicted_aoi_id=top_target,
            confidence=round(top_weight / total_weight, 3),
            stable_duration_sec=round(total_weight, 3),
            alternative_targets=alternatives,
        )
        return AggregatedSensing(
            frame=SensingFrame(gaze_prediction=gaze, learning_state=latest_learning),
            evidence=[
                f"dwell-weighted gaze evidence={total_weight:.3f}s",
                *(
                    ["slide changed during speech; start-time slide remains frozen"]
                    if context.slide_changed_during_turn
                    else []
                ),
            ],
        )
