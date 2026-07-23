import json
from pathlib import Path
import tempfile
import unittest

from modules.gaze_lock_test.contracts import (
    GazeLockScope,
    LockedGazeTarget,
)
from modules.gaze_lock_test.logger import (
    GazeLockTestLogger,
    build_gaze_lock_log_row,
    gaze_lock_log_path,
)


def make_target():
    return LockedGazeTarget(
        lock_id="lock-a",
        scope=GazeLockScope(
            deck_id="deck-a",
            slide_id=2,
            layout_revision=7,
            capture_session_id="generation-1",
            aoi_identity="identity-a",
        ),
        aoi_id="alpha",
        aoi_label="Alpha",
        target_confidence=0.8,
        stable_duration_sec=0.4,
        alternatives=({"aoi_id": "alpha", "score": 1.0},),
        clicked_at_browser_ms=1000.0,
        locked_at_server=123.0,
    )


class GazeLockLoggerTest(unittest.TestCase):
    def test_path_is_isolated_under_gaze_lock_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = gaze_lock_log_path(
                directory,
                session_id="session-a",
            )

            self.assertEqual(path.parent.name, "gaze_lock_tests")
            self.assertEqual(path.name, "session-a.jsonl")
            self.assertNotIn("main_interactions", str(path))

    def test_row_is_allowlisted_and_contains_no_raw_biometrics(self):
        row = build_gaze_lock_log_row(
            session_id="session-a",
            request_id="request-a",
            target=make_target(),
            question_text="Explain this",
            tutor_response={
                "status": "ok",
                "provider": "dashscope",
                "model": "qwen",
                "latency_ms": 12.5,
                "answer": "private from test logger",
                "query_id": "provider-private",
            },
            completed_at_server="2026-07-23T00:00:00+00:00",
        )

        self.assertEqual(row["intent_source"], "typed_text")
        self.assertEqual(row["target_source"], "gaze_prediction")
        self.assertNotIn("answer", row)
        self.assertNotIn("query_id", row)
        serialized = json.dumps(row).lower()
        for forbidden in ("x_css", "y_css", "landmark", "frame", "audio"):
            self.assertNotIn(forbidden, serialized)

    def test_request_id_is_deduplicated_across_logger_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            row = build_gaze_lock_log_row(
                session_id="session-a",
                request_id="request-a",
                target=make_target(),
                question_text="Explain this",
                tutor_response={"status": "ok"},
                completed_at_server="now",
            )

            self.assertTrue(GazeLockTestLogger(path).append_once(row))
            self.assertFalse(GazeLockTestLogger(path).append_once(row))
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_writer_rejects_non_allowlisted_raw_gaze_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            row = build_gaze_lock_log_row(
                session_id="session-a",
                request_id="request-a",
                target=make_target(),
                question_text="Explain this",
                tutor_response={"status": "ok"},
                completed_at_server="now",
            )
            row["x_css"] = 150.0

            with self.assertRaisesRegex(ValueError, "non-allowlisted"):
                GazeLockTestLogger(path).append_once(row)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
