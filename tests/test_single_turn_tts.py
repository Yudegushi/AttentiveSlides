from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modules.system.single_turn_tts import SingleTurnTTSController


class FakeTTSClient:
    def __init__(self, calls: list[tuple[str, Path]], *, failure: Exception | None = None):
        self.calls = calls
        self.failure = failure

    def synthesize(self, request, *, output_path):
        destination = Path(output_path)
        self.calls.append((request.text, destination))
        if self.failure is not None:
            raise self.failure
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"RIFF" + b"\0" * 64)
        return SimpleNamespace(path=destination)


class SingleTurnTTSControllerTests(unittest.TestCase):
    def test_disabled_and_empty_inputs_do_not_construct_a_client(self) -> None:
        factories = []
        with tempfile.TemporaryDirectory() as directory:
            controller = SingleTurnTTSController(
                output_dir=directory,
                client_factory=lambda: factories.append(True),
            )
            disabled = controller.synthesize_once(
                interaction_id="turn", text="answer", enabled=False
            )
            empty = controller.synthesize_once(
                interaction_id="turn", text="   ", enabled=True
            )
        self.assertIsNone(disabled.audio_path)
        self.assertIsNone(empty.audio_path)
        self.assertEqual(factories, [])

    def test_normalized_interaction_and_text_are_synthesized_once(self) -> None:
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            controller = SingleTurnTTSController(
                output_dir=directory,
                client_factory=lambda: FakeTTSClient(calls),
            )
            first = controller.synthesize_once(
                interaction_id=" turn-1 ", text="Hello   learner", enabled=True
            )
            second = controller.synthesize_once(
                interaction_id="turn-1", text="Hello learner", enabled=True
            )
            self.assertEqual(first, second)
            self.assertTrue(first.audio_path.is_file())
        self.assertEqual(len(calls), 1)

    def test_failure_is_cached_and_does_not_expose_provider_details(self) -> None:
        calls = []
        secret = "Authorization: Bearer private-api-key"
        with tempfile.TemporaryDirectory() as directory:
            controller = SingleTurnTTSController(
                output_dir=directory,
                client_factory=lambda: FakeTTSClient(
                    calls, failure=RuntimeError(secret)
                ),
            )
            first = controller.synthesize_once(
                interaction_id="turn-1", text="answer", enabled=True
            )
            second = controller.synthesize_once(
                interaction_id="turn-1", text="answer", enabled=True
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(first, second)
        self.assertIn("tts_failed", first.error_message)
        self.assertNotIn(secret, first.error_message)

    def test_clear_allows_a_new_request_without_deleting_old_artifact(self) -> None:
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            controller = SingleTurnTTSController(
                output_dir=directory,
                client_factory=lambda: FakeTTSClient(calls),
            )
            first = controller.synthesize_once(
                interaction_id="turn-1", text="answer", enabled=True
            )
            controller.clear()
            second = controller.synthesize_once(
                interaction_id="turn-1", text="answer", enabled=True
            )
            self.assertTrue(first.audio_path.is_file())
            self.assertEqual(first.audio_path, second.audio_path)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
