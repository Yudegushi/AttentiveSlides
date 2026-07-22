"""Paired local timing experiment state and durable JSONL records."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, MutableMapping
import uuid


FULL_SYSTEM = "full_system_ptt"
BASELINE = "baseline_select_region_typed"


def build_timing_experiment_defaults() -> dict[str, Any]:
    """Return fresh session defaults for the opt-in timing mode."""
    return {
        "main_timing_enabled": False,
        "main_timing_session_id": None,
        "main_timing_pair_index": 1,
        "main_timing_condition": FULL_SYSTEM,
        "main_timing_trial_revision": 0,
        "main_timing_started_at_browser_ms": None,
        "main_timing_intermediate_at_browser_ms": None,
        "main_timing_start_event_id": None,
        "main_timing_seen_start_event_ids": [],
        "main_timing_completed": False,
        "main_timing_last_record": None,
        "main_timing_logged_submit_ids": [],
        "main_timing_seen_submit_event_ids": [],
        "main_timing_error": None,
        "main_timing_saved_preferences": None,
        "main_timing_runtime_reset_needed": False,
    }


def new_timing_session_id(now: datetime | None = None) -> str:
    """Build a readable ID with a suffix for same-second starts."""
    current = now or datetime.now(timezone.utc)
    return current.strftime("timing-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6]


def reset_timing_trial(state: MutableMapping[str, Any]) -> None:
    """Clear one trial without changing its pair or condition."""
    state["main_timing_trial_revision"] = int(
        state.get("main_timing_trial_revision", 0)
    ) + 1
    state["main_timing_started_at_browser_ms"] = None
    state["main_timing_intermediate_at_browser_ms"] = None
    state["main_timing_start_event_id"] = None
    state["main_timing_completed"] = False
    state["main_timing_last_record"] = None
    state["main_timing_error"] = None


def capture_timing_start(
    state: MutableMapping[str, Any],
    *,
    event_id: str,
    started_at_browser_ms: float,
    intermediate_at_browser_ms: float | None = None,
) -> bool:
    """Capture the first valid start in a trial and ignore later retries."""
    if not state.get("main_timing_enabled") or state.get("main_timing_completed"):
        return False
    seen = state.setdefault("main_timing_seen_start_event_ids", [])
    if event_id in seen:
        return False
    if state.get("main_timing_started_at_browser_ms") is not None:
        return False
    started = float(started_at_browser_ms)
    if started <= 0 or not event_id:
        raise ValueError("A positive browser start time and event ID are required")
    intermediate = (
        float(intermediate_at_browser_ms)
        if intermediate_at_browser_ms is not None
        else None
    )
    if intermediate is not None and intermediate < started:
        raise ValueError("The intermediate time cannot precede the start")
    state["main_timing_started_at_browser_ms"] = started
    state["main_timing_intermediate_at_browser_ms"] = intermediate
    state["main_timing_start_event_id"] = str(event_id)
    seen.append(str(event_id))
    state["main_timing_error"] = None
    return True


def build_timing_record(
    state: MutableMapping[str, Any],
    *,
    submit_event_id: str,
    submitted_at_browser_ms: float,
    deck_id: str,
    slide_id: int,
    question_text: str,
    original_transcript: str | None,
    confirmed_aoi_id: str | None,
    target_source: str | None,
    manual_bbox: list[float] | tuple[float, ...] | None,
) -> dict[str, Any]:
    """Validate and construct one JSONL-safe timing result."""
    if not state.get("main_timing_enabled"):
        raise ValueError("Timing mode is not enabled")
    if state.get("main_timing_completed"):
        raise ValueError("The current timing trial is already complete")
    started_raw = state.get("main_timing_started_at_browser_ms")
    if started_raw is None:
        raise ValueError("Start the required interaction before submitting")
    started = float(started_raw)
    submitted = float(submitted_at_browser_ms)
    if not submit_event_id or submitted < started:
        raise ValueError("The submit event must follow the trial start")
    condition = str(state.get("main_timing_condition") or "")
    if condition not in {FULL_SYSTEM, BASELINE}:
        raise ValueError("Unknown timing experiment condition")
    intermediate_raw = state.get("main_timing_intermediate_at_browser_ms")
    intermediate = float(intermediate_raw) if intermediate_raw is not None else None
    return {
        "schema_version": 1,
        "session_id": str(state.get("main_timing_session_id") or ""),
        "pair_index": int(state.get("main_timing_pair_index", 1)),
        "condition": condition,
        "start_event_id": str(state.get("main_timing_start_event_id") or ""),
        "submit_event_id": str(submit_event_id),
        "started_at_browser_ms": started,
        "intermediate_at_browser_ms": intermediate,
        "submitted_at_browser_ms": submitted,
        "duration_ms": round(submitted - started, 3),
        "post_intermediate_duration_ms": (
            round(submitted - intermediate, 3)
            if intermediate is not None
            else None
        ),
        "deck_id": str(deck_id),
        "slide_id": int(slide_id),
        "question_text": str(question_text),
        "original_transcript": (
            str(original_transcript) if original_transcript is not None else None
        ),
        "confirmed_aoi_id": (
            str(confirmed_aoi_id) if confirmed_aoi_id is not None else None
        ),
        "target_source": str(target_source) if target_source is not None else None,
        "manual_bbox": (
            [float(value) for value in manual_bbox]
            if manual_bbox is not None
            else None
        ),
        "completed_at_server": datetime.now(timezone.utc).isoformat(),
    }


def mark_timing_recorded(
    state: MutableMapping[str, Any],
    record: dict[str, Any],
) -> None:
    """Mark the current trial complete after its durable append succeeds."""
    submit_id = str(record["submit_event_id"])
    logged = state.setdefault("main_timing_logged_submit_ids", [])
    if submit_id not in logged:
        logged.append(submit_id)
    state["main_timing_completed"] = True
    state["main_timing_last_record"] = dict(record)
    state["main_timing_error"] = None


def advance_timing_condition(state: MutableMapping[str, Any]) -> None:
    """Advance full system to its baseline, then start the next pair."""
    if not state.get("main_timing_completed"):
        raise ValueError("Complete the current trial before advancing")
    condition = state.get("main_timing_condition")
    if condition == FULL_SYSTEM:
        state["main_timing_condition"] = BASELINE
    elif condition == BASELINE:
        state["main_timing_condition"] = FULL_SYSTEM
        state["main_timing_pair_index"] = int(
            state.get("main_timing_pair_index", 1)
        ) + 1
    else:
        raise ValueError("Unknown timing experiment condition")
    reset_timing_trial(state)


class TimingExperimentLogger:
    """Append timing results outside the repository."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, session_id: str) -> Path:
        safe = "".join(
            character
            for character in str(session_id)
            if character.isalnum() or character in {"-", "_"}
        )
        if not safe:
            raise ValueError("A session ID is required")
        return self.root / f"{safe}.jsonl"

    def append(self, record: dict[str, Any]) -> Path:
        path = self.path_for(str(record.get("session_id") or ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def read(self, session_id: str) -> list[dict[str, Any]]:
        path = self.path_for(session_id)
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
