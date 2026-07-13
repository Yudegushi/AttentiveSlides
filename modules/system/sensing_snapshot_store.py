"""Thread-safe, timestamped sensing snapshots for live turn queries."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
import time
from typing import Callable

from modules.system.adapters import SensingFrame


@dataclass(frozen=True)
class SensingSnapshot:
    slide_id: int
    source_timestamp: float
    source_timestamp_clock: str
    processed_at: float
    frame: SensingFrame
    is_valid: bool
    invalid_reason: str | None
    manifest_identity: str | None = None


class SensingSnapshotStore:
    """Keep bounded sensing results and reject stale or mismatched observations."""

    def __init__(
        self,
        *,
        stale_after_seconds: float = 1.0,
        max_snapshots: int = 120,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if max_snapshots <= 0:
            raise ValueError("max_snapshots must be positive")
        self.stale_after_seconds = float(stale_after_seconds)
        self._clock = clock
        self._snapshots: deque[SensingSnapshot] = deque(maxlen=max_snapshots)
        self._lock = RLock()

    def snapshot(
        self,
        *,
        slide_id: int,
        source_timestamp: float,
        source_timestamp_clock: str,
        frame: SensingFrame,
        is_valid: bool,
        invalid_reason: str | None,
        manifest_identity: str | None = None,
    ) -> SensingSnapshot:
        return SensingSnapshot(
            slide_id=int(slide_id),
            source_timestamp=float(source_timestamp),
            source_timestamp_clock=str(source_timestamp_clock),
            processed_at=float(self._clock()),
            frame=frame,
            is_valid=bool(is_valid),
            invalid_reason=invalid_reason,
            manifest_identity=manifest_identity,
        )

    def put(self, snapshot: SensingSnapshot) -> None:
        if snapshot.frame.gaze_prediction.slide_id != snapshot.slide_id:
            raise ValueError("snapshot slide_id must match its canonical gaze prediction")
        with self._lock:
            self._snapshots.append(snapshot)

    def latest_valid_for_slide(
        self,
        slide_id: int,
        *,
        now: float | None = None,
    ) -> SensingSnapshot | None:
        current_time = self._clock() if now is None else float(now)
        with self._lock:
            for snapshot in reversed(self._snapshots):
                if snapshot.slide_id != slide_id:
                    continue
                if not snapshot.is_valid or snapshot.invalid_reason is not None:
                    continue
                if current_time - snapshot.processed_at > self.stale_after_seconds:
                    return None
                return snapshot
        return None

    def snapshots_in_window(
        self,
        slide_id: int,
        *,
        start_processed_at: float,
        end_processed_at: float,
    ) -> list[SensingSnapshot]:
        if end_processed_at < start_processed_at:
            raise ValueError("end_processed_at must not precede start_processed_at")
        with self._lock:
            return [
                snapshot
                for snapshot in self._snapshots
                if snapshot.slide_id == slide_id
                and start_processed_at <= snapshot.processed_at <= end_processed_at
            ]

    def get_sensing_frame(self, slide_id: int) -> SensingFrame:
        snapshot = self.latest_valid_for_slide(slide_id)
        if snapshot is None:
            raise LookupError(f"No current valid sensing snapshot for slide {slide_id}.")
        return snapshot.frame

    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()
