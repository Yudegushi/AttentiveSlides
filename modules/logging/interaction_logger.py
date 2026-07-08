"""JSONL interaction logger for evaluation and replay."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from modules.common.schemas import InteractionLogEvent


class InteractionLogger:
    def __init__(self, log_path: str | Path = "data/logs/interactions.jsonl") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_interaction(self, event: InteractionLogEvent | dict[str, Any]) -> None:
        if isinstance(event, InteractionLogEvent):
            payload = event.to_dict()
        elif is_dataclass(event):
            payload = asdict(event)
        else:
            payload = dict(event)

        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def log_interaction(event: InteractionLogEvent | dict[str, Any], log_path: str | Path = "data/logs/interactions.jsonl") -> None:
    InteractionLogger(log_path).log_interaction(event)
