import json
import unittest

from modules.realtime.bailian_omni_realtime_client import (
    BailianOmniRealtimeClient,
    RealtimeProtocolError,
)
from modules.realtime.realtime_contracts import SpeechMode


class FakeSocket:
    def __init__(self, messages=()) -> None:
        self.messages = list(messages)
        self.sent = []
        self.close_calls = 0

    async def send(self, value: str) -> None:
        self.sent.append(json.loads(value))

    async def close(self) -> None:
        self.close_calls += 1

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)


class BailianOmniRealtimeClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.socket = FakeSocket()
        self.connect_calls = []

        async def connect(url, **kwargs):
            self.connect_calls.append((url, kwargs))
            return self.socket

        self.client = BailianOmniRealtimeClient(
            api_key="secret",
            model="model-a",
            connect_function=connect,
            vad_threshold=0.6,
            silence_ms=700,
        )

    def test_endpoint_resolution_and_validation(self) -> None:
        workspace = BailianOmniRealtimeClient(
            api_key="x", workspace_id="workspace-1", model="m", region="singapore"
        )
        self.assertIn("workspace-1.ap-southeast-1.maas.aliyuncs.com", workspace.endpoint())
        self.assertIn("model=m", workspace.endpoint())
        with self.assertRaises(RuntimeError):
            BailianOmniRealtimeClient(api_key="x", base_url="http://example.test").endpoint()
        with self.assertRaises(RuntimeError):
            BailianOmniRealtimeClient(api_key="x", base_url="wss://<workspace>/v1").endpoint()

    async def test_connect_configures_ptt_without_turn_detection(self) -> None:
        await self.client.connect(instructions="grounded", speech_mode=SpeechMode.PUSH_TO_TALK)
        update = self.socket.sent[0]
        self.assertEqual(update["type"], "session.update")
        self.assertIsNone(update["session"]["turn_detection"])
        self.assertEqual(update["session"]["input_audio_transcription"]["model"], "qwen3-asr-flash-realtime")
        self.assertEqual(self.connect_calls[0][1]["additional_headers"]["Authorization"], "Bearer secret")

    async def test_continuous_mode_is_application_gated_and_interruptible(self) -> None:
        await self.client.connect(instructions="grounded", speech_mode=SpeechMode.CONTINUOUS)
        turn = self.socket.sent[0]["session"]["turn_detection"]
        self.assertFalse(turn["create_response"])
        self.assertTrue(turn["interrupt_response"])
        self.assertEqual(turn["threshold"], 0.6)
        await self.client.update_speech_mode(SpeechMode.PUSH_TO_TALK)
        self.assertIsNone(self.socket.sent[-1]["session"]["turn_detection"])

    async def test_audio_commit_response_and_cancel_are_separate_events(self) -> None:
        await self.client.connect(instructions="grounded", speech_mode=SpeechMode.PUSH_TO_TALK)
        await self.client.append_pcm(b"\x01\x02")
        await self.client.commit_input()
        await self.client.create_response()
        await self.client.cancel_response()
        self.assertEqual(
            [item["type"] for item in self.socket.sent[1:]],
            ["input_audio_buffer.append", "input_audio_buffer.commit", "response.create", "response.cancel"],
        )
        self.assertEqual(self.socket.sent[1]["audio"], "AQI=")

    async def test_response_done_does_not_close_the_socket(self) -> None:
        self.socket.messages = [json.dumps({"type": "response.done"})]
        await self.client.connect(instructions="grounded", speech_mode=SpeechMode.CONTINUOUS)
        events = [event async for event in self.client.events()]
        self.assertEqual(events[0].type, "response.done")
        self.assertEqual(self.socket.close_calls, 0)
        self.assertTrue(self.client.connected)

    async def test_close_is_idempotent(self) -> None:
        await self.client.connect(instructions="grounded", speech_mode=SpeechMode.CONTINUOUS)
        await self.client.close()
        await self.client.close()
        self.assertEqual(self.socket.close_calls, 1)

    async def test_malformed_event_is_a_sanitized_protocol_error(self) -> None:
        self.socket.messages = ["not-json"]
        await self.client.connect(instructions="grounded", speech_mode=SpeechMode.CONTINUOUS)
        with self.assertRaisesRegex(RealtimeProtocolError, "invalid provider JSON"):
            async for _ in self.client.events():
                pass


if __name__ == "__main__":
    unittest.main()
