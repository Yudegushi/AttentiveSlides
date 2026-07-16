"""Immutable learner-state snapshots and the thread-safe live store."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Literal

from modules.fatigue.state import FatigueSnapshot

from .emotieff_estimator import EMOTION_LABELS


LearnerStateStatus = Literal["waiting", "warming", "ready", "stale", "unavailable"]
_STATUSES = {"waiting", "warming", "ready", "stale", "unavailable"}


def _validate_probability(value: float | None, label: str) -> None:
    if value is not None and (
        not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{label} must be a finite probability")


@dataclass(frozen=True)
class EmotionSnapshot:
    status: LearnerStateStatus = "waiting"
    probabilities: tuple[float, ...] = ()
    top_label: str | None = None
    top_probability: float | None = None
    updated_at: float | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError("invalid emotion status")
        for probability in self.probabilities:
            _validate_probability(probability, "emotion probability")
        _validate_probability(self.top_probability, "top emotion probability")
        if self.updated_at is not None and not math.isfinite(float(self.updated_at)):
            raise ValueError("emotion timestamp must be finite")
        if self.status in {"ready", "stale"}:
            if len(self.probabilities) != len(EMOTION_LABELS):
                raise ValueError("ready/stale emotion requires eight probabilities")
            if not math.isclose(sum(self.probabilities), 1.0, abs_tol=1e-4):
                raise ValueError("emotion probabilities must sum to one")
            if self.top_label not in EMOTION_LABELS or self.top_probability is None:
                raise ValueError("top emotion label is not official")
            index = EMOTION_LABELS.index(self.top_label)
            if not math.isclose(
                float(self.top_probability), self.probabilities[index], abs_tol=1e-6
            ):
                raise ValueError("top emotion probability does not match its label")
        elif self.probabilities or self.top_label is not None or self.top_probability is not None:
            raise ValueError("non-ready emotion snapshots cannot contain predictions")


@dataclass(frozen=True)
class EngagementSnapshot:
    status: LearnerStateStatus = "waiting"
    distracted_probability: float | None = None
    engaged_probability: float | None = None
    alert_active: bool = False
    reminder_suppressed: bool = False
    buffered_frames: int = 0
    required_frames: int = 128
    updated_at: float | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError("invalid engagement status")
        _validate_probability(self.distracted_probability, "distracted probability")
        _validate_probability(self.engaged_probability, "engaged probability")
        if not isinstance(self.required_frames, int) or self.required_frames <= 0:
            raise ValueError("required engagement frames must be positive")
        if (
            not isinstance(self.buffered_frames, int)
            or self.buffered_frames < 0
            or self.buffered_frames > self.required_frames
        ):
            raise ValueError("buffered engagement frames are invalid")
        if self.updated_at is not None and not math.isfinite(float(self.updated_at)):
            raise ValueError("engagement timestamp must be finite")
        if self.status in {"ready", "stale"}:
            if self.distracted_probability is None or self.engaged_probability is None:
                raise ValueError("ready/stale engagement requires both probabilities")
            if not math.isclose(
                self.distracted_probability + self.engaged_probability,
                1.0,
                abs_tol=1e-4,
            ):
                raise ValueError("engagement probabilities must sum to one")
            if self.buffered_frames != self.required_frames:
                raise ValueError("ready/stale engagement requires a full window")
        elif self.distracted_probability is not None or self.engaged_probability is not None:
            raise ValueError("non-ready engagement cannot contain probabilities")
        if self.alert_active and self.status != "ready":
            raise ValueError("only ready engagement may have an objective alert")
        if self.reminder_suppressed and not self.alert_active:
            raise ValueError("reminder suppression requires an objective alert")


@dataclass(frozen=True)
class LearnerStateSnapshot:
    emotion: EmotionSnapshot = EmotionSnapshot()
    engagement: EngagementSnapshot = EngagementSnapshot()
    fatigue: FatigueSnapshot = FatigueSnapshot()
    updated_at: float | None = None

    def __post_init__(self) -> None:
        if self.updated_at is not None and not math.isfinite(float(self.updated_at)):
            raise ValueError("learner-state timestamp must be finite")


class LearnerStateStore:
    """Keep the newest unified snapshot; derive stale presentation copies."""

    def __init__(
        self,
        *,
        stale_after_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(stale_after_seconds) or stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive and finite")
        self._stale_after_seconds = float(stale_after_seconds)
        self._clock = clock
        self._lock = threading.RLock()
        self._snapshot = LearnerStateSnapshot()

    def publish(self, snapshot: LearnerStateSnapshot) -> None:
        if not isinstance(snapshot, LearnerStateSnapshot):
            raise TypeError("snapshot must be a LearnerStateSnapshot")
        with self._lock:
            self._snapshot = snapshot

    def snapshot(self, now: float | None = None) -> LearnerStateSnapshot:
        checked_at = self._clock() if now is None else float(now)
        if not math.isfinite(checked_at):
            raise ValueError("snapshot timestamp must be finite")
        with self._lock:
            current = self._snapshot
        emotion = self._stale_emotion(current.emotion, checked_at)
        engagement = self._stale_engagement(current.engagement, checked_at)
        fatigue = self._stale_fatigue(current.fatigue, checked_at)
        return replace(current, emotion=emotion, engagement=engagement, fatigue=fatigue)

    def _is_stale(self, status: str, updated_at: float | None, now: float) -> bool:
        return (
            status == "ready"
            and updated_at is not None
            and now - updated_at > self._stale_after_seconds
        )

    def _stale_emotion(self, snapshot: EmotionSnapshot, now: float) -> EmotionSnapshot:
        if self._is_stale(snapshot.status, snapshot.updated_at, now):
            return replace(snapshot, status="stale")
        return snapshot

    def _stale_engagement(
        self, snapshot: EngagementSnapshot, now: float
    ) -> EngagementSnapshot:
        if self._is_stale(snapshot.status, snapshot.updated_at, now):
            return replace(
                snapshot,
                status="stale",
                alert_active=False,
                reminder_suppressed=False,
            )
        return snapshot

    def _stale_fatigue(self, snapshot: FatigueSnapshot, now: float) -> FatigueSnapshot:
        if self._is_stale(snapshot.status, snapshot.updated_at, now):
            return replace(snapshot, status="stale", alert_active=False)
        return snapshot

    def clear(self) -> None:
        with self._lock:
            self._snapshot = LearnerStateSnapshot()
