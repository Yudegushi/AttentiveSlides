"""Stateful UI boundary for the continuous live runtime.

The view model owns no media callback work. It only sends commands to the
existing controller, polls completed turns, and returns rendering-safe state.
"""

from __future__ import annotations

from dataclasses import asdict
from threading import RLock
import time
from typing import Any, Callable

from modules.system.demo_view_model import build_interaction_view_model
from modules.system.live_turn_runner import LiveTurnOutcome
from modules.system.runtime_state import RuntimeState


class LiveViewModel:
    """Serialize UI commands while preserving controller ownership of workers."""

    def __init__(
        self,
        *,
        controller: Any,
        media_source: Any,
        slide_provider: Any,
        snapshot_store: Any,
        tutor_adapter: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.controller = controller
        self.media_source = media_source
        self.slide_provider = slide_provider
        self.snapshot_store = snapshot_store
        self.tutor_adapter = tutor_adapter
        self._clock = clock
        self._lock = RLock()
        self._slide_id: int | None = None
        self._last_outcome: LiveTurnOutcome | None = None
        self._last_error: str | None = None
        self._status_copy = "Stopped; live workers are not running."

    @property
    def slide_id(self) -> int | None:
        with self._lock:
            return self._slide_id

    @property
    def is_running(self) -> bool:
        return self.controller.state != RuntimeState.STOPPED

    def load_deck(self, pdf: bytes, *, filename: str) -> str:
        """Replace a deck only after stopping the existing live runtime."""

        loader = getattr(self.slide_provider, "load_deck", None)
        if not callable(loader):
            raise RuntimeError("The configured slide provider does not support PDF loading.")
        self.stop(reason="deck reload")
        deck_id = loader(pdf, filename=filename)
        self.set_slide(1)
        return deck_id

    def set_slide(self, slide_id: int) -> None:
        frame = self.slide_provider.get_slide_frame(slide_id)
        with self._lock:
            self._slide_id = frame.slide_id
        self.controller.set_slide(frame.slide_id)

    def start(self) -> None:
        with self._lock:
            if self.controller.state != RuntimeState.STOPPED:
                return
            if self._slide_id is None:
                raise RuntimeError("Load a PDF deck before starting the runtime.")
            self._last_error = None
            self._status_copy = "Starting live browser media and workers."
        self.controller.start()
        with self._lock:
            if self.controller.state == RuntimeState.MONITORING:
                self._status_copy = "Monitoring browser media for one active speech turn."
            elif self.controller.state == RuntimeState.STOPPED:
                self._last_error = "Runtime startup did not complete."
                self._status_copy = "Runtime startup failed; workers were stopped."

    def stop(self, *, reason: str = "requested") -> None:
        with self._lock:
            already_stopped = self.controller.state == RuntimeState.STOPPED
        if not already_stopped:
            self.controller.stop(reason=reason)
        with self._lock:
            self._last_outcome = None
            self._status_copy = "Stopped; live workers and media queues were cleaned up."

    def handle_disconnect(self) -> None:
        self.controller.handle_disconnect()
        with self._lock:
            self._last_outcome = None
            self._status_copy = "Browser disconnected; live workers were stopped."

    def configure_grounded_tutor(self, enabled: bool) -> bool:
        if self.tutor_adapter is None:
            self._last_error = "The live runtime has no configurable grounded tutor."
            return not enabled
        if enabled:
            enabled_now = bool(self.tutor_adapter.enable_grounded())
            if not enabled_now:
                self._last_error = self.tutor_adapter.status().get("configuration_error")
            return enabled_now
        self.tutor_adapter.disable_grounded()
        return True

    def poll(self) -> list[LiveTurnOutcome]:
        outcomes = self.controller.poll()
        with self._lock:
            for outcome in outcomes:
                self._record_outcome(outcome)
        return outcomes

    def confirm(self, query_id: str, confirmed_aoi_id: str) -> LiveTurnOutcome:
        if not query_id:
            raise ValueError("A pending query ID is required for confirmation.")
        outcome = self.controller.confirm(query_id, confirmed_aoi_id)
        with self._lock:
            self._record_outcome(outcome)
        return outcome

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            slide_id = self._slide_id
            outcome = self._last_outcome
            error = self._last_error
            status_copy = self._status_copy

        stats = self.media_source.stats()
        interaction = (
            build_interaction_view_model(outcome.interaction_result)
            if outcome is not None and outcome.interaction_result is not None
            else None
        )
        frame = self._frame(slide_id)
        gaze = self._gaze_payload(slide_id)
        pending = bool(outcome and outcome.pending_confirmation and interaction is not None)
        query_id = (
            outcome.interaction_result.resolved_query.query_id
            if pending and outcome is not None and outcome.interaction_result is not None
            else None
        )
        turn_started_at = outcome.turn_started_at if outcome else None
        turn_ended_at = outcome.turn_ended_at if outcome else None
        duration = (
            round(turn_ended_at - turn_started_at, 3)
            if turn_started_at is not None and turn_ended_at is not None
            else None
        )

        return {
            "deck": {
                "deck_id": getattr(self.slide_provider, "deck_id", None) if slide_id is not None else None,
                "page_count": getattr(self.slide_provider, "page_count", None) if slide_id is not None else None,
                "loaded": slide_id is not None,
            },
            "slide": {
                "id": frame.slide_id if frame is not None else None,
                "image_path": frame.slide_image_path if frame is not None else None,
                "aois": [asdict(aoi) for aoi in frame.aois] if frame is not None else [],
            },
            "runtime": {
                "state": self.controller.state.value,
                "status_copy": status_copy,
                "busy_turn_count": getattr(self.controller, "busy_turn_count", 0),
                "error": error,
            },
            "transport": {
                "is_running": stats.is_running,
                "cleanup_state": stats.cleanup_state,
                "video_fps": round(stats.video_fps, 2),
                "audio_chunks_per_second": round(stats.audio_chunks_per_second, 2),
                "video_queue_depth": stats.video_queue_depth,
                "audio_queue_depth": stats.audio_queue_depth,
                "video_drops": stats.video_drops,
                "audio_drops": stats.audio_drops,
                "audio_overruns": stats.audio_overruns,
            },
            "gaze": gaze,
            "turn": {
                "transcript": outcome.transcript if outcome else None,
                "started_at": turn_started_at,
                "ended_at": turn_ended_at,
                "duration_seconds": duration,
                "error": outcome.error if outcome else None,
            },
            "confirmation": {
                "pending": pending,
                "query_id": query_id,
                "candidates": interaction["confirmation_options"] if pending and interaction else [],
            },
            "interaction": interaction,
            "tutor": self._tutor_status(),
            "grounded_xai": self._grounded_xai(),
            "developer": {
                "media_running": stats.is_running,
                "source_cleanup_state": stats.cleanup_state,
                "queue_drops": stats.video_drops + stats.audio_drops,
                "audio_worker_running": _worker_is_running(
                    getattr(self.controller, "audio_worker", None)
                ),
                "sensing_worker_running": _worker_is_running(
                    getattr(self.controller, "sensing_worker", None)
                ),
            },
        }

    def _tutor_status(self) -> dict[str, Any]:
        if self.tutor_adapter is None:
            return {
                "selection": "deterministic",
                "configuration_error": None,
                "provider_error": None,
                "last_status": "deterministic",
                "provider": "deterministic_mock",
                "model": "mock",
                "fallback_used": False,
            }
        return dict(self.tutor_adapter.status())

    def _grounded_xai(self) -> dict[str, Any] | None:
        if self.tutor_adapter is None:
            return None
        return self.tutor_adapter.latest_xai_view()

    def _frame(self, slide_id: int | None) -> Any | None:
        if slide_id is None:
            return None
        try:
            return self.slide_provider.get_slide_frame(slide_id)
        except (LookupError, RuntimeError, ValueError):
            return None

    def _gaze_payload(self, slide_id: int | None) -> dict[str, Any]:
        if slide_id is None:
            return _unknown_gaze("No deck is loaded.")
        try:
            sensing = self.snapshot_store.latest_valid_for_slide(slide_id)
        except AttributeError:
            sensing = None
        if sensing is None:
            return _unknown_gaze("No fresh valid gaze evidence is available.")
        prediction = sensing.frame.gaze_prediction
        return {
            "gaze_grid": prediction.gaze_grid,
            "predicted_aoi_id": prediction.predicted_aoi_id,
            "confidence": prediction.confidence,
            "freshness_seconds": round(max(0.0, self._clock() - sensing.processed_at), 3),
            "status_copy": "Coarse AOI evidence only; it is not eye tracking.",
        }

    def _record_outcome(self, outcome: LiveTurnOutcome) -> None:
        self._last_outcome = outcome
        if outcome.error:
            self._last_error = outcome.error
            self._status_copy = "The last live turn was recoverably degraded."
        elif outcome.pending_confirmation:
            self._status_copy = "Target confirmation is required before a final tutor response."
        else:
            self._status_copy = "Live turn completed; runtime returned to monitoring."


def _unknown_gaze(status_copy: str) -> dict[str, Any]:
    return {
        "gaze_grid": "unknown",
        "predicted_aoi_id": None,
        "confidence": 0.0,
        "freshness_seconds": None,
        "status_copy": status_copy,
    }


def _worker_is_running(worker: Any | None) -> bool:
    state = getattr(worker, "is_running", False)
    return bool(state() if callable(state) else state)
