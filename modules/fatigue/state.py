"""Thread-safe temporal state for the informational fatigue reminder."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Literal


FatigueStatus = Literal["waiting", "ready", "unavailable"]


@dataclass(frozen=True)
class FatigueSnapshot:
    status: FatigueStatus = "waiting"
    raw_probability: float | None = None
    smoothed_probability: float | None = None
    alert_active: bool = False
    updated_at: float | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"waiting", "ready", "unavailable"}:
            raise ValueError("invalid fatigue status")
        for value in (self.raw_probability, self.smoothed_probability):
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError("fatigue probabilities must be normalized")
        if self.alert_active and self.status != "ready":
            raise ValueError("only a ready fatigue snapshot may alert")


@dataclass(frozen=True)
class FatigueTemporalConfig:
    ema_time_constant_seconds: float = 1.5
    enter_threshold: float = 0.75
    enter_duration_seconds: float = 3.0
    exit_threshold: float = 0.45
    exit_duration_seconds: float = 5.0
    stale_after_seconds: float = 2.0

    def __post_init__(self) -> None:
        for value in (
            self.ema_time_constant_seconds,
            self.enter_duration_seconds,
            self.exit_duration_seconds,
            self.stale_after_seconds,
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("fatigue timing values must be positive and finite")
        if not (
            math.isfinite(self.exit_threshold)
            and math.isfinite(self.enter_threshold)
            and 0.0 <= self.exit_threshold < self.enter_threshold <= 1.0
        ):
            raise ValueError("fatigue thresholds must satisfy 0 <= exit < enter <= 1")


class FatigueTemporalTracker:
    """Apply a time-based EMA and sustained enter/exit gates."""

    def __init__(self, config: FatigueTemporalConfig | None = None) -> None:
        self.config = config or FatigueTemporalConfig()
        self.reset()

    def reset(self) -> None:
        self._ema: float | None = None
        self._last_update_at: float | None = None
        self._high_since: float | None = None
        self._low_since: float | None = None
        self._alert_active = False

    def update(self, probability: float, now: float) -> FatigueSnapshot:
        probability = float(probability)
        now = float(now)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("fatigue probability must be normalized and finite")
        if not math.isfinite(now):
            raise ValueError("fatigue timestamp must be finite")

        if (
            self._last_update_at is not None
            and now - self._last_update_at > self.config.stale_after_seconds
        ):
            self.reset()

        if self._ema is None:
            self._ema = probability
        else:
            dt = max(0.0, now - self._last_update_at)
            alpha = 1.0 - math.exp(
                -dt / self.config.ema_time_constant_seconds
            )
            self._ema += alpha * (probability - self._ema)
        self._last_update_at = now

        if not self._alert_active:
            self._low_since = None
            if self._ema >= self.config.enter_threshold:
                if self._high_since is None:
                    self._high_since = now
                elif now - self._high_since >= self.config.enter_duration_seconds:
                    self._alert_active = True
                    self._high_since = None
            else:
                self._high_since = None
        else:
            self._high_since = None
            if self._ema <= self.config.exit_threshold:
                if self._low_since is None:
                    self._low_since = now
                elif now - self._low_since >= self.config.exit_duration_seconds:
                    self._alert_active = False
                    self._low_since = None
            else:
                self._low_since = None

        return FatigueSnapshot(
            status="ready",
            raw_probability=probability,
            smoothed_probability=self._ema,
            alert_active=self._alert_active,
            updated_at=now,
        )


class FatigueStateStore:
    """Keep only the newest fatigue snapshot in memory."""

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
        self._snapshot = FatigueSnapshot()

    def publish(self, snapshot: FatigueSnapshot) -> None:
        if not isinstance(snapshot, FatigueSnapshot):
            raise TypeError("snapshot must be a FatigueSnapshot")
        with self._lock:
            self._snapshot = snapshot

    def snapshot(self, now: float | None = None) -> FatigueSnapshot:
        checked_at = self._clock() if now is None else float(now)
        with self._lock:
            current = self._snapshot
        if (
            current.status == "ready"
            and current.updated_at is not None
            and checked_at - current.updated_at > self._stale_after_seconds
        ):
            return FatigueSnapshot()
        return current

    def clear(self) -> None:
        with self._lock:
            self._snapshot = FatigueSnapshot()
