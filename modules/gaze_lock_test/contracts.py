"""Contracts owned by the isolated gaze-lock test mode."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string.")
    return value.strip()


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number


@dataclass(frozen=True)
class GazeLockEvent:
    """One browser-timestamped request to lock the current gaze target."""

    event_id: str
    clicked_at_browser_ms: float

    @classmethod
    def from_component_value(
        cls,
        payload: Mapping[str, object],
    ) -> "GazeLockEvent":
        if not isinstance(payload, Mapping):
            raise ValueError("Gaze-lock component value must be an object.")
        if payload.get("event") != "gaze_lock":
            raise ValueError("Unsupported gaze-lock component event.")
        clicked_at = _finite_number(
            payload.get("clicked_at_browser_ms"),
            "clicked_at_browser_ms",
        )
        if clicked_at < 0:
            raise ValueError("clicked_at_browser_ms must be non-negative.")
        return cls(
            event_id=_required_text(payload.get("event_id"), "event_id"),
            clicked_at_browser_ms=clicked_at,
        )


@dataclass(frozen=True)
class GazeLockScope:
    """Identity boundary within which a lock remains valid."""

    deck_id: str
    slide_id: int
    layout_revision: int
    capture_session_id: str
    aoi_identity: str

    def __post_init__(self) -> None:
        _required_text(self.deck_id, "deck_id")
        _required_text(self.capture_session_id, "capture_session_id")
        _required_text(self.aoi_identity, "aoi_identity")
        if self.slide_id < 0:
            raise ValueError("slide_id must be non-negative.")
        if self.layout_revision < 0:
            raise ValueError("layout_revision must be non-negative.")


@dataclass(frozen=True)
class LockedGazeTarget:
    """AOI selected from gaze evidence ending at a browser click."""

    lock_id: str
    scope: GazeLockScope
    aoi_id: str
    aoi_label: str
    target_confidence: float
    stable_duration_sec: float
    alternatives: tuple[dict[str, object], ...]
    clicked_at_browser_ms: float
    locked_at_server: float

    def __post_init__(self) -> None:
        _required_text(self.lock_id, "lock_id")
        _required_text(self.aoi_id, "aoi_id")
        _required_text(self.aoi_label, "aoi_label")
        for name, value in (
            ("target_confidence", self.target_confidence),
            ("stable_duration_sec", self.stable_duration_sec),
            ("clicked_at_browser_ms", self.clicked_at_browser_ms),
            ("locked_at_server", self.locked_at_server),
        ):
            _finite_number(value, name)
        if not 0.0 <= self.target_confidence <= 1.0:
            raise ValueError("target_confidence must be in [0, 1].")
        if self.stable_duration_sec < 0:
            raise ValueError("stable_duration_sec must be non-negative.")
        if self.clicked_at_browser_ms < 0:
            raise ValueError("clicked_at_browser_ms must be non-negative.")
        if self.locked_at_server < 0:
            raise ValueError("locked_at_server must be non-negative.")

    @property
    def deck_id(self) -> str:
        return self.scope.deck_id

    @property
    def slide_id(self) -> int:
        return self.scope.slide_id

    @property
    def layout_revision(self) -> int:
        return self.scope.layout_revision

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
