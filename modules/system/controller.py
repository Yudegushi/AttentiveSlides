"""Own live worker lifecycle and serialize one active speech turn."""

from __future__ import annotations

import queue
from threading import RLock
from typing import Any

from modules.system.runtime_state import RuntimeState


class SystemController:
    """Coordinate media, sensing, audio, frozen context, and confirmation."""

    def __init__(
        self,
        *,
        media_source: Any,
        sensing_worker: Any,
        audio_worker: Any,
        context_collector: Any,
        turn_runner: Any,
        fatigue_worker: Any | None = None,
    ) -> None:
        self.media_source = media_source
        self.sensing_worker = sensing_worker
        self.audio_worker = audio_worker
        self.context_collector = context_collector
        self.turn_runner = turn_runner
        self.fatigue_worker = fatigue_worker
        self._lock = RLock()
        self._state = RuntimeState.STOPPED
        self._current_slide_id: int | None = None
        self._deferred_sensing_slide_id: int | None = None
        self._active_context: Any | None = None
        self._ignored_started_at: set[float] = set()
        self.busy_turn_count = 0
        register = getattr(self.audio_worker, "set_turn_callbacks", None)
        if callable(register):
            register(on_started=self._on_turn_started, on_discarded=self._on_turn_discarded)

    @property
    def state(self) -> RuntimeState:
        with self._lock:
            return self._state

    def set_slide(self, slide_id: int) -> None:
        if not isinstance(slide_id, int) or slide_id < 1:
            raise ValueError("slide_id must be a positive integer")
        with self._lock:
            self._current_slide_id = slide_id
            if self._state == RuntimeState.SPEECH_ACTIVE:
                self._deferred_sensing_slide_id = slide_id
                return
        if self.state != RuntimeState.STOPPED:
            self.sensing_worker.set_slide(slide_id)

    def start(self) -> None:
        with self._lock:
            if self._state != RuntimeState.STOPPED:
                return
            if self._current_slide_id is None:
                raise RuntimeError("set_slide() is required before start()")
            self._state = RuntimeState.STARTING
        try:
            self.media_source.start()
            self._start_fatigue_best_effort()
            self.sensing_worker.set_slide(self._current_slide_id)
            self.sensing_worker.start()
            self.audio_worker.start()
        except Exception:
            with self._lock:
                self._state = RuntimeState.ERROR
            self.stop(reason="startup error")
            return
        with self._lock:
            self._state = RuntimeState.MONITORING

    def stop(self, *, reason: str = "requested") -> None:
        with self._lock:
            if self._state == RuntimeState.STOPPED:
                return
            self._state = RuntimeState.STOPPED
            self._active_context = None
            self._ignored_started_at.clear()
        self.audio_worker.stop()
        self.sensing_worker.stop()
        if self.fatigue_worker is not None:
            try:
                self.fatigue_worker.stop()
            except Exception:
                pass
        self.media_source.stop(reason=reason)

    def _start_fatigue_best_effort(self) -> None:
        if self.fatigue_worker is None:
            return
        try:
            self.fatigue_worker.start()
        except Exception as exc:
            try:
                self.fatigue_worker.record_external_error(exc)
            except Exception:
                pass

    def handle_disconnect(self) -> None:
        with self._lock:
            if self._state == RuntimeState.STOPPED:
                return
            self._state = RuntimeState.ERROR
        self.stop(reason="browser disconnected")

    def poll(self) -> list[Any]:
        outcomes: list[Any] = []
        while True:
            try:
                audio_result = self.audio_worker.get_result_nowait()
            except queue.Empty:
                break
            with self._lock:
                if audio_result.turn.started_at in self._ignored_started_at:
                    self._ignored_started_at.remove(audio_result.turn.started_at)
                    continue
                context = self._active_context
                if context is None or context.speech_started_at != audio_result.turn.started_at:
                    self.busy_turn_count += 1
                    continue
                self._state = RuntimeState.FINALIZING_AUDIO
                self._active_context = self.context_collector.freeze_end(
                    context,
                    speech_ended_at=audio_result.turn.ended_at,
                    current_slide_id=self._current_slide_id or context.slide_id,
                )
                frozen = self._active_context
            if audio_result.status != "completed" or audio_result.transcript is None:
                self._return_to_monitoring()
                continue
            with self._lock:
                self._state = RuntimeState.PROCESSING_TURN
            outcome = self.turn_runner.run(audio_result, frozen)
            outcomes.append(outcome)
            with self._lock:
                self._state = (
                    RuntimeState.WAITING_CONFIRMATION
                    if outcome.pending_confirmation
                    else RuntimeState.MONITORING
                )
                if self._state == RuntimeState.MONITORING:
                    self._active_context = None
            self._apply_deferred_sensing_slide()
        return outcomes

    def confirm(self, query_id: str, confirmed_aoi_id: str) -> Any:
        with self._lock:
            if self._state != RuntimeState.WAITING_CONFIRMATION:
                raise RuntimeError("no pending confirmation")
        outcome = self.turn_runner.resume_confirmation(query_id, confirmed_aoi_id)
        with self._lock:
            self._state = RuntimeState.MONITORING
            self._active_context = None
        self._apply_deferred_sensing_slide()
        return outcome

    def _on_turn_started(self, started_at: float) -> None:
        with self._lock:
            if self._state != RuntimeState.MONITORING or self._current_slide_id is None:
                self.busy_turn_count += 1
                self._ignored_started_at.add(float(started_at))
                return
            self._active_context = self.context_collector.freeze_start(
                slide_id=self._current_slide_id,
                speech_started_at=float(started_at),
            )
            self._state = RuntimeState.SPEECH_ACTIVE

    def _on_turn_discarded(self, started_at: float, _reason: str) -> None:
        with self._lock:
            if (
                self._state == RuntimeState.SPEECH_ACTIVE
                and self._active_context is not None
                and self._active_context.speech_started_at == started_at
            ):
                self._active_context = None
                self._state = RuntimeState.MONITORING

    def _return_to_monitoring(self) -> None:
        with self._lock:
            self._active_context = None
            if self._state != RuntimeState.STOPPED:
                self._state = RuntimeState.MONITORING
        self._apply_deferred_sensing_slide()

    def _apply_deferred_sensing_slide(self) -> None:
        with self._lock:
            slide_id = self._deferred_sensing_slide_id
            self._deferred_sensing_slide_id = None
        if slide_id is not None and self.state != RuntimeState.STOPPED:
            self.sensing_worker.set_slide(slide_id)
