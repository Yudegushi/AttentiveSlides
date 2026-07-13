"""Live boundary adapter for the existing grounded tutor pipeline."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from modules.logging.interaction_logger import InteractionLogger
from modules.system.xai_view_model import build_xai_view_model
from modules.tutor.grounded_tutor_agent import GroundedTutorAgent, GroundedTutorResult
from modules.tutor.tutor_agent import TutorAgent


class LiveTutorAdapter:
    """Select deterministic or grounded tutoring without changing the canonical pipeline."""

    def __init__(
        self,
        *,
        deterministic_tutor: Any | None = None,
        grounded_agent: Any | None = None,
        grounded_factory: Callable[[], Any] = GroundedTutorAgent,
    ) -> None:
        self._deterministic_tutor = deterministic_tutor or TutorAgent()
        self._grounded_agent = grounded_agent
        self._grounded_factory = grounded_factory
        self._selection = "deterministic"
        self._configuration_error: str | None = None
        self._last_grounded_result: GroundedTutorResult | None = None
        self._last_provider_error: str | None = None

    @property
    def selection(self) -> str:
        return self._selection

    def enable_grounded(self) -> bool:
        """Enable the existing API-backed agent only when it can be constructed."""

        if self._grounded_agent is None:
            try:
                self._grounded_agent = self._grounded_factory()
            except Exception as exc:
                self._selection = "deterministic"
                self._configuration_error = str(exc)
                return False
        self._selection = "grounded"
        self._configuration_error = None
        self._last_provider_error = None
        return True

    def disable_grounded(self) -> None:
        self._selection = "deterministic"
        self._configuration_error = None
        self._last_provider_error = None

    def answer(self, resolved_query: Any, deck_state: Any = None, history: Any = None):
        if self._selection != "grounded":
            return self._deterministic_tutor.answer(
                resolved_query,
                deck_state=deck_state,
                history=history,
            )

        assert self._grounded_agent is not None
        try:
            result = self._grounded_agent.answer(
                resolved_query,
                deck_state=deck_state,
                history=history,
            )
        except Exception as exc:
            self._last_provider_error = str(exc)
            return self._deterministic_tutor.answer(
                resolved_query,
                deck_state=deck_state,
                history=history,
            )

        if not isinstance(result, GroundedTutorResult):
            raise TypeError("grounded agent must return GroundedTutorResult")
        self._last_grounded_result = result
        self._last_provider_error = None
        return result.to_legacy_response()

    def latest_xai_view(self) -> dict[str, Any] | None:
        if self._last_grounded_result is None:
            return None
        return build_xai_view_model(self._last_grounded_result)

    def status(self) -> dict[str, Any]:
        telemetry = self.telemetry()
        return {
            "selection": self._selection,
            "configuration_error": self._configuration_error,
            "provider_error": self._last_provider_error,
            "last_status": telemetry["status"],
            "provider": telemetry["provider"],
            "model": telemetry["model"],
            "fallback_used": telemetry["fallback_used"],
        }

    def telemetry(self) -> dict[str, Any]:
        """Return a JSONL-safe subset with no prompt or raw provider material."""

        result = self._last_grounded_result
        if result is None:
            return {
                "selection": self._selection,
                "status": "deterministic",
                "provider": "deterministic_mock",
                "model": "mock",
                "latency_ms": None,
                "usage": None,
                "resolved_aoi_id": None,
                "grounded_confirmed_aoi_id": None,
                "context_source_ids": [],
                "validation": None,
                "fallback_used": False,
            }

        call = result.call_result
        return {
            "selection": self._selection,
            "status": result.status,
            "provider": call.provider,
            "model": call.model,
            "latency_ms": round(call.latency_ms, 2),
            "usage": asdict(call.usage) if call.usage is not None else None,
            "resolved_aoi_id": None,
            "grounded_confirmed_aoi_id": result.request.confirmed_aoi_id,
            "context_source_ids": [source.source_id for source in result.request.sources],
            "validation": result.validation.to_dict(),
            "fallback_used": call.fallback_used,
        }


class LiveTelemetryLogger:
    """Enrich one existing JSONL interaction event with sanitized live telemetry."""

    def __init__(self, logger: InteractionLogger, tutor_adapter: LiveTutorAdapter) -> None:
        self._logger = logger
        self._tutor_adapter = tutor_adapter

    def log_interaction(self, event: Any) -> None:
        if is_dataclass(event):
            payload = asdict(event)
        else:
            payload = dict(event)
        telemetry = self._tutor_adapter.telemetry()
        telemetry["resolved_aoi_id"] = payload.get("resolved_aoi_id")
        telemetry["confirmed_aoi_id"] = payload.get("confirmed_aoi_id")
        payload["live_tutor"] = telemetry
        self._logger.log_interaction(payload)
