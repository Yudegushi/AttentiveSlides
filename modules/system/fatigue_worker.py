"""Optional latest-only worker for local fatigue inference."""

from __future__ import annotations

import queue
from threading import Event, RLock, Thread, current_thread
import time
from typing import Any, Callable

from modules.fatigue import FatigueSnapshot, FatigueStateStore, FatigueTemporalTracker


class FatigueWorker:
    """Classify newest face crops without participating in controller health."""

    def __init__(
        self,
        face_crop_queue: Any,
        *,
        estimator_factory: Callable[[], Any],
        tracker: FatigueTemporalTracker,
        store: FatigueStateStore,
        clock: Callable[[], float] = time.monotonic,
        empty_wait_seconds: float = 0.05,
    ) -> None:
        if empty_wait_seconds <= 0:
            raise ValueError("empty_wait_seconds must be positive")
        self.face_crop_queue = face_crop_queue
        self.estimator_factory = estimator_factory
        self.tracker = tracker
        self.store = store
        self._clock = clock
        self._empty_wait_seconds = float(empty_wait_seconds)
        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._estimator: Any | None = None
        self._last_success_at: float | None = None
        self._last_error: str | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._last_error = None
            self._last_success_at = None
            self.tracker.reset()
            self.store.clear()
            self._thread = Thread(
                target=self._run,
                name="attentive-fatigue-worker",
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
            if self._thread is thread and (
                thread is None or not thread.is_alive()
            ):
                self._thread = None
            self._last_success_at = None
            self.tracker.reset()
            self.store.clear()

    def record_external_error(self, exc: BaseException) -> None:
        error = self._format_error(exc)
        with self._lock:
            self._last_error = error
        self.store.publish(
            FatigueSnapshot(
                status="unavailable",
                updated_at=float(self._clock()),
                error=error,
            )
        )

    def _run(self) -> None:
        try:
            with self._lock:
                estimator = self._estimator
            if estimator is None:
                estimator = self.estimator_factory()
                with self._lock:
                    self._estimator = estimator

            while not self._stop_event.is_set():
                packet = self._newest_packet()
                if packet is None:
                    self._stop_event.wait(self._empty_wait_seconds)
                    continue
                now = float(self._clock())
                with self._lock:
                    last_success_at = self._last_success_at
                if (
                    last_success_at is not None
                    and now - last_success_at > self.tracker.config.stale_after_seconds
                ):
                    self.tracker.reset()
                probability = estimator.predict(packet.image)
                if self._stop_event.is_set():
                    break
                snapshot = self.tracker.update(probability, now)
                with self._lock:
                    if self._stop_event.is_set():
                        break
                    self.store.publish(snapshot)
                    self._last_success_at = now
        except Exception as exc:
            if not self._stop_event.is_set():
                self.record_external_error(exc)

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
