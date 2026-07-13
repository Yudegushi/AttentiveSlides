from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from modules.common.schemas import InteractionLogEvent, ResolvedQuery, TutorResponse
from modules.logging.interaction_logger import InteractionLogger
from modules.system.live_tutor_adapter import LiveTelemetryLogger, LiveTutorAdapter
from tests.test_xai_view_model import make_grounded_result


class FakeDeterministicTutor:
    def __init__(self) -> None:
        self.calls = 0

    def answer(self, resolved_query, deck_state=None, history=None) -> TutorResponse:
        del deck_state, history
        self.calls += 1
        return TutorResponse(
            query_id=resolved_query.query_id,
            response_mode="explain",
            answer="deterministic response",
        )


class FakeGroundedTutor:
    def __init__(self) -> None:
        self.calls = 0
        self.result = make_grounded_result()

    def answer(self, resolved_query, deck_state=None, history=None):
        del resolved_query, deck_state, history
        self.calls += 1
        return self.result


def resolved_query() -> ResolvedQuery:
    return ResolvedQuery(
        query_id="live_query_1",
        deck_id="mock_deck",
        slide_id=2,
        transcript="explain this",
        intent="explain",
        resolved_aoi_id="fixation",
        target_confidence=1.0,
        needs_confirmation=False,
        confirmation_mode="none",
        adaptive_strategy="normal",
    )


def log_event() -> InteractionLogEvent:
    return InteractionLogEvent(
        query_id="live_query_1",
        timestamp=1.0,
        deck_id="mock_deck",
        slide_id=2,
        transcript="explain this",
        intent="explain",
        predicted_aoi_id="fixation",
        resolved_aoi_id="fixation",
        confirmed_aoi_id="fixation",
        target_confidence=1.0,
        needs_confirmation=False,
        confirmation_mode="none",
        user_corrected=False,
        adaptive_strategy="normal",
        response_mode="explain",
        latency_ms=12.0,
    )


class LiveTutorAdapterTest(unittest.TestCase):
    def test_default_mode_uses_deterministic_tutor(self) -> None:
        deterministic = FakeDeterministicTutor()
        adapter = LiveTutorAdapter(deterministic_tutor=deterministic)

        response = adapter.answer(resolved_query())

        self.assertEqual(response.answer, "deterministic response")
        self.assertEqual(deterministic.calls, 1)
        self.assertEqual(adapter.status()["selection"], "deterministic")

    def test_grounded_mode_reuses_agent_and_exposes_sanitized_xai(self) -> None:
        grounded = FakeGroundedTutor()
        adapter = LiveTutorAdapter(
            deterministic_tutor=FakeDeterministicTutor(),
            grounded_agent=grounded,
        )

        self.assertTrue(adapter.enable_grounded())
        response = adapter.answer(resolved_query())
        xai = adapter.latest_xai_view()

        self.assertEqual(grounded.calls, 1)
        self.assertEqual(response.used_context["provider"], "dashscope")
        self.assertEqual(xai["telemetry"]["model"], "qwen3.7-plus")
        serialized = json.dumps(xai, ensure_ascii=False)
        self.assertNotIn("PRIVATE RAW PROVIDER RESPONSE", serialized)
        self.assertNotIn("private_request_id", serialized)

    def test_missing_grounded_configuration_keeps_deterministic_mode(self) -> None:
        adapter = LiveTutorAdapter(
            deterministic_tutor=FakeDeterministicTutor(),
            grounded_factory=lambda: (_ for _ in ()).throw(RuntimeError("missing key")),
        )

        self.assertFalse(adapter.enable_grounded())
        self.assertEqual(adapter.status()["selection"], "deterministic")
        self.assertEqual(adapter.status()["configuration_error"], "missing key")

    def test_jsonl_telemetry_records_safe_provider_context_and_validation(self) -> None:
        adapter = LiveTutorAdapter(
            deterministic_tutor=FakeDeterministicTutor(),
            grounded_agent=FakeGroundedTutor(),
        )
        adapter.enable_grounded()
        adapter.answer(resolved_query())

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.jsonl"
            logger = LiveTelemetryLogger(InteractionLogger(path), adapter)
            logger.log_interaction(log_event())

            payload = json.loads(path.read_text(encoding="utf-8"))

        telemetry = payload["live_tutor"]
        self.assertEqual(telemetry["provider"], "dashscope")
        self.assertEqual(telemetry["model"], "qwen3.7-plus")
        self.assertEqual(telemetry["resolved_aoi_id"], "fixation")
        self.assertEqual(telemetry["context_source_ids"], ["slide_02_aoi_01", "slide_02_aoi_02"])
        self.assertTrue(telemetry["validation"]["is_valid"])
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("PRIVATE RAW PROVIDER RESPONSE", serialized)
        self.assertNotIn("private_request_id", serialized)


if __name__ == "__main__":
    unittest.main()
