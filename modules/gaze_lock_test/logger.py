"""Privacy-bounded JSONL logging for the gaze-lock test."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Mapping

from modules.gaze_lock_test.contracts import LockedGazeTarget


SCHEMA_VERSION = "gaze-lock-test.v1"


def gaze_lock_log_path(
    runtime_data_dir: str | Path,
    *,
    session_id: str,
) -> Path:
    safe_session_id = "".join(
        character
        for character in str(session_id)
        if character.isalnum() or character in {"-", "_"}
    )
    if not safe_session_id:
        raise ValueError("session_id must contain a safe filename character.")
    return (
        Path(runtime_data_dir).resolve()
        / "gaze_lock_tests"
        / f"{safe_session_id}.jsonl"
    )


def build_gaze_lock_log_row(
    *,
    session_id: str,
    request_id: str,
    target: LockedGazeTarget,
    question_text: str,
    tutor_response: Mapping[str, object],
    completed_at_server: str,
) -> dict[str, object]:
    """Build an allowlisted row without raw gaze or provider-private data."""
    question = str(question_text).strip()
    if not question:
        raise ValueError("question_text must not be blank.")
    response_status = str(tutor_response.get("status", "")).strip()
    if not response_status:
        raise ValueError("tutor_response requires status.")
    row: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": str(session_id),
        "request_id": str(request_id),
        "lock_id": target.lock_id,
        "deck_id": target.deck_id,
        "slide_id": target.slide_id,
        "aoi_id": target.aoi_id,
        "aoi_label": target.aoi_label,
        "layout_revision": target.layout_revision,
        "target_confidence": target.target_confidence,
        "stable_duration_sec": target.stable_duration_sec,
        "clicked_at_browser_ms": target.clicked_at_browser_ms,
        "question_text": question,
        "intent_source": "typed_text",
        "target_source": "gaze_prediction",
        "response_status": response_status,
        "completed_at_server": str(completed_at_server),
    }
    for name in ("provider", "model", "latency_ms"):
        value = tutor_response.get(name)
        if value is not None:
            row[name] = value
    return row


class GazeLockTestLogger:
    """Append one allowlisted JSON object at most once per request ID."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._logged_request_ids = self._load_request_ids()

    def append_once(self, row: Mapping[str, object]) -> bool:
        request_id = str(row.get("request_id", "")).strip()
        if not request_id:
            raise ValueError("log row requires request_id.")
        if row.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("log row has an unsupported schema_version.")
        with self._lock:
            if request_id in self._logged_request_ids:
                return False
            with self.path.open("a", encoding="utf-8") as file:
                file.write(
                    json.dumps(
                        dict(row),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                file.flush()
            self._logged_request_ids.add(request_id)
            return True

    def _load_request_ids(self) -> set[str]:
        if not self.path.is_file():
            return set()
        request_ids: set[str] = set()
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return request_ids
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            request_id = payload.get("request_id")
            if isinstance(request_id, str) and request_id.strip():
                request_ids.add(request_id)
        return request_ids
