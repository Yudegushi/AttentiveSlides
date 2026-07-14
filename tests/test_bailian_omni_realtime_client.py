"""No-network tests for Qwen Omni Realtime protocol."""

from __future__ import annotations

import asyncio
import json
import unittest

from modules.realtime.bailian_omni_realtime_client import (
    BailianOmniRealtimeClient,
)


class FakeSocket:
    def __init__(
        self,
    ) -> None:
        self.sent: list[str] = []
        self.closed = False
        self._messages = iter(
            []
        )

    async def send(
        self,
        message: str,
    ) -> None:
        self.sent.append(
            message
        )

    async def close(
        self,
    ) -> None:
        self.closed = True

    def __aiter__(
        self,
    ):
        return self

    async def __anext__(
        self,
    ):
        try:
            return next(
                self._messages
            )

        except StopIteration as error:
            raise StopAsyncIteration \
                from error


class TestBailianOmniRealtimeClient(
    unittest.IsolatedAsyncioTestCase
):
    async def asyncSetUp(
        self,
    ) -> None:
        self.socket = FakeSocket()

        async def connect(
            *_args,
            **_kwargs,
        ):
            return self.socket

        self.client = (
            BailianOmniRealtimeClient(
                api_key="test-key",
                workspace_id=(
                    "test-workspace"
                ),
                connect_function=connect,
            )
        )

    async def test_manual_protocol(
        self,
    ) -> None:
        await self.client.connect(
            instructions="Tutor",
            continuous=False,
        )

        await self.client.append_pcm(
            b"\x00\x00" * 100
        )

        await (
            self.client
            .commit_and_respond()
        )

        payloads = [
            json.loads(message)
            for message
            in self.socket.sent
        ]

        types = [
            payload["type"]
            for payload in payloads
        ]

        self.assertEqual(
            types,
            [
                "session.update",
                (
                    "input_audio_buffer"
                    ".append"
                ),
                (
                    "input_audio_buffer"
                    ".commit"
                ),
                "response.create",
            ],
        )

        self.assertIsNone(
            payloads[0][
                "session"
            ][
                "turn_detection"
            ]
        )

    async def test_continuous_uses_semantic_vad(
        self,
    ) -> None:
        await self.client.connect(
            instructions="Tutor",
            continuous=True,
        )

        payload = json.loads(
            self.socket.sent[0]
        )

        self.assertEqual(
            payload[
                "session"
            ][
                "turn_detection"
            ][
                "type"
            ],
            "semantic_vad",
        )

    async def test_explicit_empty_key_is_rejected(
        self,
    ) -> None:
        client = (
            BailianOmniRealtimeClient(
                api_key="",
                workspace_id=(
                    "test-workspace"
                ),
            )
        )

        with self.assertRaises(
            RuntimeError
        ):
            await client.connect(
                instructions="Tutor",
                continuous=False,
            )


if __name__ == "__main__":
    unittest.main()
