"""Tests for the OpenAI-compatible API client."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from modules.tutor.api_llm_client import (
    OpenAICompatibleLLMClient,
)


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs

        return SimpleNamespace(
            id="request_test_001",
            model="qwen3.7-plus",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"answer": "ok"}'
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_tokens_details=(
                    SimpleNamespace(
                        cached_tokens=10
                    )
                ),
            ),
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(
            completions=self.completions
        )


class TestOpenAICompatibleLLMClient(
    unittest.TestCase
):
    def test_json_mode_request_and_usage(self) -> None:
        fake_client = FakeOpenAIClient()

        client = OpenAICompatibleLLMClient(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="qwen3.7-plus",
            client=fake_client,
        )

        response = client.generate([
            {
                "role": "system",
                "content": "Return JSON.",
            },
            {
                "role": "user",
                "content": "Test.",
            },
        ])

        kwargs = fake_client.completions.kwargs

        self.assertEqual(
            kwargs["response_format"],
            {"type": "json_object"},
        )

        self.assertEqual(
            kwargs["extra_body"],
            {"enable_thinking": False},
        )

        self.assertEqual(
            response.request_id,
            "request_test_001",
        )

        self.assertEqual(
            response.usage.total_tokens,
            120,
        )

        self.assertEqual(
            response.usage.cached_prompt_tokens,
            10,
        )

    def test_empty_messages_are_rejected(self) -> None:
        client = OpenAICompatibleLLMClient(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
            client=FakeOpenAIClient(),
        )

        with self.assertRaises(ValueError):
            client.generate([])


if __name__ == "__main__":
    unittest.main()
