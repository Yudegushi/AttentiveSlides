"""Temporal smoothing and sustained engagement alert policy."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, replace
from typing import Callable

import numpy as np

from .contracts import EmotionSnapshot, EngagementSnapshot
from .emotieff_estimator import EMOTION_LABELS, FEATURE_DIMENSIONS


def _finite_time(now: float, label: str) -> float:
    value = float(now)
    if not math.isfinite(value):
        raise ValueError(f"{label} timestamp must be finite")
    return value


@dataclass(frozen=True)
class EmotionTemporalConfig:
    ema_time_constant_seconds: float = 2.0
    stale_after_seconds: float = 2.0

    def __post_init__(self) -> None:
        if any(
            not math.isfinite(value) or value <= 0
            for value in (self.ema_time_constant_seconds, self.stale_after_seconds)
        ):
            raise ValueError("emotion timing values must be positive and finite")


class EmotionTemporalTracker:
    def __init__(self, config: EmotionTemporalConfig | None = None) -> None:
        self.config = config or EmotionTemporalConfig()
        self.reset()

    def reset(self) -> None:
        self._ema: np.ndarray | None = None
        self._last_update_at: float | None = None

    def update(self, probabilities, now: float) -> EmotionSnapshot:
        values = np.asarray(probabilities, dtype=np.float64)
        now = _finite_time(now, "emotion")
        if (
            values.shape != (len(EMOTION_LABELS),)
            or not np.isfinite(values).all()
            or np.any(values < 0.0)
            or np.any(values > 1.0)
            or not math.isclose(float(values.sum()), 1.0, abs_tol=1e-4)
        ):
            raise ValueError("emotion probabilities must be eight normalized finite values")
        if self._last_update_at is not None and now < self._last_update_at:
            raise ValueError("emotion timestamps must be monotonic")
        if (
            self._last_update_at is not None
            and now - self._last_update_at > self.config.stale_after_seconds
        ):
            self.reset()
        if self._ema is None:
            self._ema = values.copy()
        else:
            dt = now - self._last_update_at
            alpha = 1.0 - math.exp(-dt / self.config.ema_time_constant_seconds)
            self._ema += alpha * (values - self._ema)
            self._ema /= self._ema.sum()
        self._last_update_at = now
        index = int(np.argmax(self._ema))
        smoothed = tuple(float(value) for value in self._ema)
        return EmotionSnapshot(
            status="ready",
            probabilities=smoothed,
            top_label=EMOTION_LABELS[index],
            top_probability=smoothed[index],
            updated_at=now,
        )


@dataclass(frozen=True)
class EngagementTemporalConfig:
    window_frames: int = 128
    stride_frames: int = 16
    enter_threshold: float = 0.75
    exit_threshold: float = 0.45
    enter_updates: int = 2
    exit_updates: int = 2
    reset_gap_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.window_frames, int) or self.window_frames <= 0:
            raise ValueError("engagement window must be positive")
        if (
            not isinstance(self.stride_frames, int)
            or self.stride_frames <= 0
            or self.stride_frames > self.window_frames
        ):
            raise ValueError("engagement stride is invalid")
        if not (
            0.0 <= self.exit_threshold < self.enter_threshold <= 1.0
            and math.isfinite(self.exit_threshold)
            and math.isfinite(self.enter_threshold)
        ):
            raise ValueError("engagement thresholds must satisfy 0 <= exit < enter <= 1")
        if self.enter_updates <= 0 or self.exit_updates <= 0:
            raise ValueError("engagement alert gates must be positive")
        if not math.isfinite(self.reset_gap_seconds) or self.reset_gap_seconds <= 0:
            raise ValueError("engagement reset gap must be positive and finite")


class EngagementTemporalTracker:
    def __init__(self, config: EngagementTemporalConfig | None = None) -> None:
        self.config = config or EngagementTemporalConfig()
        self.reset()

    def reset(self) -> None:
        self._features: deque[np.ndarray] = deque(maxlen=self.config.window_frames)
        self._last_feature_at: float | None = None
        self._new_since_inference = 0
        self._enter_count = 0
        self._exit_count = 0
        self._alert_active = False
        self._reminder_suppressed = False
        self._snapshot = EngagementSnapshot(required_frames=self.config.window_frames)

    def add(
        self,
        feature: np.ndarray,
        now: float,
        infer: Callable[[np.ndarray], tuple[float, float]],
    ) -> EngagementSnapshot:
        now = _finite_time(now, "engagement")
        if self._last_feature_at is not None and now < self._last_feature_at:
            raise ValueError("engagement timestamps must be monotonic")
        if (
            not isinstance(feature, np.ndarray)
            or feature.shape != (FEATURE_DIMENSIONS,)
            or not np.issubdtype(feature.dtype, np.floating)
            or not np.isfinite(feature).all()
        ):
            raise ValueError("engagement feature must be finite and shaped (1280,)")
        if (
            self._last_feature_at is not None
            and now - self._last_feature_at > self.config.reset_gap_seconds
        ):
            self.reset()
        self._last_feature_at = now
        self._features.append(feature.astype(np.float32, copy=True))
        self._new_since_inference += 1
        buffered = len(self._features)
        if buffered < self.config.window_frames:
            self._snapshot = EngagementSnapshot(
                status="warming",
                buffered_frames=buffered,
                required_frames=self.config.window_frames,
                updated_at=now,
            )
            return self._snapshot
        should_infer = (
            self._snapshot.status != "ready"
            or self._new_since_inference >= self.config.stride_frames
        )
        if not should_infer:
            return self._snapshot
        distracted, engaged = (float(value) for value in infer(np.stack(self._features)))
        if (
            not math.isfinite(distracted)
            or not math.isfinite(engaged)
            or not 0.0 <= distracted <= 1.0
            or not 0.0 <= engaged <= 1.0
            or not math.isclose(distracted + engaged, 1.0, abs_tol=1e-4)
        ):
            raise ValueError("engagement inference must return two normalized probabilities")
        self._new_since_inference = 0
        if not self._alert_active:
            self._exit_count = 0
            self._enter_count = self._enter_count + 1 if distracted >= self.config.enter_threshold else 0
            if self._enter_count >= self.config.enter_updates:
                self._alert_active = True
                self._enter_count = 0
        else:
            self._enter_count = 0
            self._exit_count = self._exit_count + 1 if distracted <= self.config.exit_threshold else 0
            if self._exit_count >= self.config.exit_updates:
                self._alert_active = False
                self._reminder_suppressed = False
                self._exit_count = 0
        self._snapshot = EngagementSnapshot(
            status="ready",
            distracted_probability=distracted,
            engaged_probability=engaged,
            alert_active=self._alert_active,
            reminder_suppressed=self._reminder_suppressed,
            buffered_frames=self.config.window_frames,
            required_frames=self.config.window_frames,
            updated_at=now,
        )
        return self._snapshot

    def dismiss(self) -> EngagementSnapshot:
        if self._snapshot.status == "ready" and self._alert_active:
            self._reminder_suppressed = True
            self._snapshot = replace(self._snapshot, reminder_suppressed=True)
        return self._snapshot

    def snapshot(self) -> EngagementSnapshot:
        return self._snapshot
