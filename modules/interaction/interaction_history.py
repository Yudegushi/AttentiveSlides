"""Small in-memory interaction history for deterministic dry-run behavior."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


class InteractionHistory:
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self._events: list[dict[str, Any]] = list(events or [])

    def add(self, event: Any) -> None:
        if is_dataclass(event):
            self._events.append(asdict(event))
        elif isinstance(event, dict):
            self._events.append(dict(event))
        else:
            raise TypeError("InteractionHistory only accepts dataclasses or dictionaries.")

    def same_aoi_question_count(self, aoi_id: str) -> int:
        return sum(1 for event in self._events if event.get("resolved_aoi_id") == aoi_id)

    def recent(self, limit: int = 5) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return self._events[-limit:]

    def as_list(self) -> list[dict[str, Any]]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)
