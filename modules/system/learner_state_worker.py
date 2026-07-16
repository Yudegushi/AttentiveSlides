"""Latest-only unified emotion, engagement, and fatigue inference worker."""

from __future__ import annotations

import queue
import time
from dataclasses import replace
from threading import Event, RLock, Thread, current_thread
from typing import Any, Callable

from modules.fatigue import FatigueSnapshot, FatigueTemporalTracker
from modules.learner_state import (
    EmotionSnapshot,
    EmotionTemporalTracker,
    EngagementSnapshot,
    EngagementTemporalTracker,
    LearnerStateSnapshot,
    LearnerStateStore,
)


class LearnerStateWorker:
    """Run three isolated modalities over the newest shared browser face crop."""

    def __init__(
        self,
        face_crop_queue: Any,
        *,
        affect_estimator_factory: Callable[[], Any],
        fatigue_estimator_factory: Callable[[], Any],
        emotion_tracker: EmotionTemporalTracker,
        engagement_tracker: EngagementTemporalTracker,
        fatigue_tracker: FatigueTemporalTracker,
        store: LearnerStateStore,
        on_snapshot: Callable[[str, int, LearnerStateSnapshot, float], Any] | None = None,
        fatigue_interval_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
        empty_wait_seconds: float = 0.05,
    ) -> None:
        if fatigue_interval_seconds <= 0:
            raise ValueError("fatigue_interval_seconds must be positive")
        if empty_wait_seconds <= 0:
            raise ValueError("empty_wait_seconds must be positive")
        self.face_crop_queue = face_crop_queue
        self.affect_estimator_factory = affect_estimator_factory
        self.fatigue_estimator_factory = fatigue_estimator_factory
        self.emotion_tracker = emotion_tracker
        self.engagement_tracker = engagement_tracker
        self.fatigue_tracker = fatigue_tracker
        self.store = store
        self.on_snapshot = on_snapshot
        self._fatigue_interval_seconds = float(fatigue_interval_seconds)
        self._clock = clock
        self._empty_wait_seconds = float(empty_wait_seconds)
        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._affect_estimator: Any | None = None
        self._fatigue_estimator: Any | None = None
        self._last_fatigue_attempt_at: float | None = None
        self._last_error: str | None = None
        self._deck_id: str | None = None
        self._slide_id: int | None = None
        self._emotion = EmotionSnapshot()
        self._engagement = EngagementSnapshot(
            required_frames=self.engagement_tracker.config.window_frames
        )
        self._fatigue = FatigueSnapshot()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def set_context(self, deck_id: str | None, slide_id: int | None) -> None:
        if deck_id is None and slide_id is None:
            checked_deck = None
            checked_slide = None
        elif (
            not isinstance(deck_id, str)
            or not deck_id.strip()
            or not isinstance(slide_id, int)
            or slide_id < 1
        ):
            raise ValueError("learner-state context requires deck ID and positive slide ID")
        else:
            checked_deck = deck_id.strip()
            checked_slide = slide_id
        with self._lock:
            self._deck_id = checked_deck
            self._slide_id = checked_slide

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._last_error = None
            self._reset_live_locked()
            self.store.clear()
            self._thread = Thread(
                target=self._run,
                name="attentive-learner-state-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread is not None and thread is not current_thread() and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None
            self._reset_live_locked()
            self.store.clear()

    def dismiss_distraction(self) -> None:
        with self._lock:
            self._engagement = self.engagement_tracker.dismiss()
            snapshot = self._unified_snapshot_locked()
            self.store.publish(snapshot)

    def record_external_error(self, exc: BaseException) -> None:
        now = float(self._clock())
        error = self._format_error(exc)
        with self._lock:
            self._last_error = error
            self._emotion = EmotionSnapshot(status="unavailable", updated_at=now, error=error)
            self._engagement = EngagementSnapshot(
                status="unavailable",
                required_frames=self.engagement_tracker.config.window_frames,
                updated_at=now,
                error=error,
            )
            self._fatigue = FatigueSnapshot(status="unavailable", updated_at=now, error=error)
            self.store.publish(self._unified_snapshot_locked(now))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            packet = self._newest_packet()
            if packet is None:
                self._stop_event.wait(self._empty_wait_seconds)
                continue
            now = float(self._clock())
            with self._lock:
                captured_deck_id = self._deck_id
                captured_slide_id = self._slide_id

            affect_output = None
            try:
                affect_estimator = self._get_affect_estimator()
                affect_output = affect_estimator.infer_frame(packet.image)
                emotion = self.emotion_tracker.update(
                    affect_output.emotion_probabilities, now
                )
            except Exception as exc:
                error = self._format_error(exc)
                emotion = EmotionSnapshot(
                    status="unavailable", updated_at=now, error=error
                )
                engagement = EngagementSnapshot(
                    status="unavailable",
                    required_frames=self.engagement_tracker.config.window_frames,
                    updated_at=now,
                    error=error,
                )
                self._remember_error(error)
            else:
                try:
                    engagement = self.engagement_tracker.add(
                        affect_output.feature,
                        now,
                        affect_estimator.infer_engagement,
                    )
                except Exception as exc:
                    error = self._format_error(exc)
                    engagement = EngagementSnapshot(
                        status="unavailable",
                        required_frames=self.engagement_tracker.config.window_frames,
                        updated_at=now,
                        error=error,
                    )
                    self._remember_error(error)

            fatigue = None
            with self._lock:
                last_fatigue_attempt_at = self._last_fatigue_attempt_at
                current_fatigue = self._fatigue
            fatigue_due = (
                last_fatigue_attempt_at is None
                or now - last_fatigue_attempt_at >= self._fatigue_interval_seconds
            )
            if fatigue_due:
                with self._lock:
                    self._last_fatigue_attempt_at = now
                try:
                    fatigue_estimator = self._get_fatigue_estimator()
                    fatigue_probability = fatigue_estimator.predict(packet.image)
                    fatigue = self.fatigue_tracker.update(fatigue_probability, now)
                except Exception as exc:
                    error = self._format_error(exc)
                    fatigue = FatigueSnapshot(
                        status="unavailable", updated_at=now, error=error
                    )
                    self._remember_error(error)
            else:
                fatigue = current_fatigue

            if self._stop_event.is_set():
                break
            with self._lock:
                if self._stop_event.is_set():
                    break
                self._emotion = emotion
                self._engagement = engagement
                self._fatigue = fatigue
                snapshot = self._unified_snapshot_locked(now)
                self.store.publish(snapshot)
            if (
                self.on_snapshot is not None
                and captured_deck_id is not None
                and captured_slide_id is not None
            ):
                try:
                    self.on_snapshot(
                        captured_deck_id,
                        captured_slide_id,
                        snapshot,
                        now,
                    )
                except Exception as exc:
                    self._remember_error(self._format_error(exc))

    def _get_affect_estimator(self) -> Any:
        with self._lock:
            estimator = self._affect_estimator
        if estimator is None:
            estimator = self.affect_estimator_factory()
            with self._lock:
                if self._affect_estimator is None:
                    self._affect_estimator = estimator
                else:
                    estimator = self._affect_estimator
        return estimator

    def _get_fatigue_estimator(self) -> Any:
        with self._lock:
            estimator = self._fatigue_estimator
        if estimator is None:
            estimator = self.fatigue_estimator_factory()
            with self._lock:
                if self._fatigue_estimator is None:
                    self._fatigue_estimator = estimator
                else:
                    estimator = self._fatigue_estimator
        return estimator

    def _reset_live_locked(self) -> None:
        self.emotion_tracker.reset()
        self.engagement_tracker.reset()
        self.fatigue_tracker.reset()
        self._last_fatigue_attempt_at = None
        self._emotion = EmotionSnapshot()
        self._engagement = EngagementSnapshot(
            required_frames=self.engagement_tracker.config.window_frames
        )
        self._fatigue = FatigueSnapshot()

    def _unified_snapshot_locked(self, now: float | None = None) -> LearnerStateSnapshot:
        updated = now
        if updated is None:
            candidates = (
                self._emotion.updated_at,
                self._engagement.updated_at,
                self._fatigue.updated_at,
            )
            present = [value for value in candidates if value is not None]
            updated = max(present) if present else None
        return LearnerStateSnapshot(
            emotion=self._emotion,
            engagement=self._engagement,
            fatigue=self._fatigue,
            updated_at=updated,
        )

    def _remember_error(self, error: str) -> None:
        with self._lock:
            self._last_error = error

    def _newest_packet(self) -> Any | None:
        try:
            newest = self.face_crop_queue.get_nowait()
        except queue.Empty:
            return None
        while True:
            try:
                newest = self.face_crop_queue.get_nowait()
            except queue.Empty:
                return newest

    @staticmethod
    def _format_error(exc: BaseException) -> str:
        detail = str(exc).strip() or "unknown error"
        return f"{type(exc).__name__}: {detail}"[:240]
