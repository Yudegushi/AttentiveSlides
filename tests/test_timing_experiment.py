import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.system.timing_experiment import (
    BASELINE,
    FULL_SYSTEM,
    TimingExperimentLogger,
    advance_timing_condition,
    build_timing_experiment_defaults,
    build_timing_record,
    capture_timing_start,
    mark_timing_recorded,
    new_timing_session_id,
    reset_timing_trial,
)


class TimingExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = build_timing_experiment_defaults()
        self.state["main_timing_enabled"] = True
        self.state["main_timing_session_id"] = "session-1"

    def test_pair_advances_full_then_baseline_then_next_pair(self) -> None:
        self.assertEqual(self.state["main_timing_condition"], FULL_SYSTEM)
        self.state["main_timing_completed"] = True
        advance_timing_condition(self.state)
        self.assertEqual(self.state["main_timing_condition"], BASELINE)
        self.assertEqual(self.state["main_timing_pair_index"], 1)
        self.state["main_timing_completed"] = True
        advance_timing_condition(self.state)
        self.assertEqual(self.state["main_timing_condition"], FULL_SYSTEM)
        self.assertEqual(self.state["main_timing_pair_index"], 2)

    def test_first_start_is_retained_and_record_uses_browser_duration(self) -> None:
        self.assertTrue(
            capture_timing_start(
                self.state,
                event_id="start-1",
                started_at_browser_ms=1000.0,
                intermediate_at_browser_ms=2500.0,
            )
        )
        self.assertFalse(
            capture_timing_start(
                self.state,
                event_id="start-2",
                started_at_browser_ms=4000.0,
            )
        )
        self.assertEqual(self.state["main_timing_seen_start_event_ids"], ["start-1"])
        record = build_timing_record(
            self.state,
            submit_event_id="submit-1",
            submitted_at_browser_ms=7000.0,
            deck_id="deck",
            slide_id=4,
            question_text="Explain this.",
            original_transcript="Explain this.",
            confirmed_aoi_id="aoi-1",
            target_source="eyetheia_local",
            manual_bbox=None,
        )
        self.assertEqual(record["duration_ms"], 6000.0)
        self.assertEqual(record["post_intermediate_duration_ms"], 4500.0)

    def test_reset_changes_trial_revision_to_prevent_stale_component_events(self) -> None:
        self.assertEqual(self.state["main_timing_trial_revision"], 0)
        reset_timing_trial(self.state)
        self.assertEqual(self.state["main_timing_trial_revision"], 1)
        reset_timing_trial(self.state)
        self.assertEqual(self.state["main_timing_trial_revision"], 2)

    def test_logger_writes_one_jsonl_row(self) -> None:
        record = {
            "session_id": "session-1",
            "submit_event_id": "submit-1",
            "duration_ms": 10.0,
        }
        with TemporaryDirectory() as directory:
            logger = TimingExperimentLogger(directory)
            path = logger.append(record)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), record)
            self.assertEqual(logger.read("session-1"), [record])

    def test_session_id_is_readable_and_unique_suffix_is_present(self) -> None:
        value = new_timing_session_id(
            datetime(2026, 7, 22, 1, 2, 3, tzinfo=timezone.utc)
        )
        self.assertRegex(value, r"^timing-20260722T010203Z-[0-9a-f]{6}$")

    def test_mark_recorded_deduplicates_submit_id(self) -> None:
        record = {"submit_event_id": "submit-1"}
        mark_timing_recorded(self.state, record)
        mark_timing_recorded(self.state, record)
        self.assertEqual(self.state["main_timing_logged_submit_ids"], ["submit-1"])
        self.assertTrue(self.state["main_timing_completed"])
        self.assertEqual(self.state["main_timing_seen_submit_event_ids"], [])


if __name__ == "__main__":
    unittest.main()
