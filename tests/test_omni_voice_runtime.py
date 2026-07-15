import asyncio
import base64
import unittest

from modules.realtime.bailian_omni_realtime_client import RealtimeEvent
from modules.realtime.realtime_contracts import SpeechMode, TargetBinding
from modules.system.omni_voice_runtime import OmniVoiceRuntime
from modules.system.target_switching import TargetSwitchController
from modules.system.voice_event_hub import VoiceEventHub, VoiceJSONEvent


STOP = object()


class FakeClient:
    def __init__(self, *, connect_error: bool = False) -> None:
        self.connect_error = connect_error
        self.calls = []
        self.events_queue = asyncio.Queue()
        self.closed = 0

    async def connect(self, *, instructions, speech_mode) -> None:
        self.calls.append(("connect", speech_mode, instructions))
        if self.connect_error:
            raise RuntimeError("secret provider details")

    async def update_speech_mode(self, mode) -> None:
        self.calls.append(("update", mode))

    async def append_pcm(self, pcm) -> None:
        self.calls.append(("append", pcm))

    async def commit_input(self) -> None:
        self.calls.append(("commit",))

    async def create_response(self) -> None:
        self.calls.append(("create",))

    async def cancel_response(self) -> None:
        self.calls.append(("cancel",))

    async def close(self) -> None:
        self.closed += 1
        await self.events_queue.put(STOP)

    async def events(self):
        while True:
            value = await self.events_queue.get()
            if value is STOP:
                return
            yield value

    async def emit(self, type, **payload) -> None:
        await self.events_queue.put(RealtimeEvent(type=type, payload={"type": type, **payload}))


def make_target(target_id: str) -> TargetBinding:
    return TargetBinding("deck", 1, target_id, target_id.upper(), f"context {target_id}")


class OmniVoiceRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.hub = VoiceEventHub(queue_size=32)
        self.subscription = await self.hub.subscribe("session")
        self.controller = TargetSwitchController()
        self.clients = []
        self.fallbacks = []
        self.gaze_starts = []
        self.gaze_candidate = None

        def factory():
            client = FakeClient()
            self.clients.append(client)
            return client

        def begin(target, timestamp):
            token = (target.signature, timestamp, len(self.gaze_starts))
            self.gaze_starts.append(token)
            return token

        def resolve(token, timestamp, target):
            del token, timestamp, target
            return self.gaze_candidate

        async def fallback(reason, transcript):
            self.fallbacks.append((reason, transcript))

        self.runtime = OmniVoiceRuntime(
            events=self.hub,
            target_switching=self.controller,
            client_factory=factory,
            begin_gaze_window=begin,
            resolve_gaze_window=resolve,
            on_fallback=fallback,
        )
        self.a = make_target("a")
        self.addAsyncCleanup(self.runtime.stop_session, "test_cleanup")

    async def drain(self) -> list[object]:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        values = []
        while not self.subscription.queue.empty():
            values.append(self.subscription.queue.get_nowait())
        return values

    async def test_ptt_two_turns_keep_one_provider_conversation(self) -> None:
        await self.runtime.start_session(target=self.a, speech_mode=SpeechMode.PUSH_TO_TALK)
        client = self.clients[0]
        for number in (1, 2):
            await self.runtime.start_push_to_talk()
            await self.runtime.accept_pcm("session", bytes([number, 0]))
            await self.runtime.stop_push_to_talk()
            await client.emit("conversation.item.input_audio_transcription.completed", transcript=f"question {number}")
            await client.emit("response.text.delta", delta=f"answer {number}")
            await client.emit("response.done")
            await self.drain()
        self.assertEqual(len(self.clients), 1)
        self.assertEqual(sum(call[0] == "connect" for call in client.calls), 1)
        self.assertEqual(sum(call[0] == "commit" for call in client.calls), 2)
        self.assertEqual(sum(call[0] == "create" for call in client.calls), 2)
        self.assertEqual(client.closed, 0)

    async def test_continuous_transcript_is_gated_before_response_create(self) -> None:
        await self.runtime.start_session(target=self.a, speech_mode=SpeechMode.CONTINUOUS)
        client = self.clients[0]
        self.assertFalse(any(call[0] == "create" for call in client.calls))
        await client.emit("conversation.item.input_audio_transcription.completed", transcript="why")
        await self.drain()
        self.assertEqual(sum(call[0] == "create" for call in client.calls), 1)

    async def test_target_candidate_is_frozen_at_ptt_boundary_and_confirm_reconnects(self) -> None:
        b = make_target("b")
        c = make_target("c")
        self.gaze_candidate = b
        await self.runtime.start_session(target=self.a, speech_mode=SpeechMode.PUSH_TO_TALK)
        first_client = self.clients[0]
        await self.runtime.start_push_to_talk()
        await self.runtime.accept_pcm("session", b"\x00\x01")
        await self.runtime.stop_push_to_talk()
        self.gaze_candidate = c
        await first_client.emit("conversation.item.input_audio_transcription.completed", transcript="换到这个")
        await self.drain()
        self.assertEqual(self.runtime.snapshot()["pending_target"]["signature"], b.signature)
        self.assertFalse(any(call[0] == "create" for call in first_client.calls))
        await self.runtime.confirm_target_switch()
        self.assertEqual(first_client.closed, 1)
        self.assertEqual(len(self.clients), 2)
        self.assertEqual(self.runtime.snapshot()["target_signature"], b.signature)

    async def test_continuous_speech_boundaries_resolve_gaze_and_barge_in(self) -> None:
        self.gaze_candidate = make_target("b")
        await self.runtime.start_session(target=self.a, speech_mode=SpeechMode.CONTINUOUS)
        client = self.clients[0]
        await client.emit("response.created")
        await client.emit("input_audio_buffer.speech_started")
        await client.emit("input_audio_buffer.speech_stopped")
        events = await self.drain()
        self.assertTrue(any(call[0] == "cancel" for call in client.calls))
        self.assertEqual(len(self.gaze_starts), 1)
        self.assertTrue(any(isinstance(item, VoiceJSONEvent) and item.type == "playback.clear" for item in events))

    async def test_audio_off_keeps_answer_text_without_binary_playback(self) -> None:
        await self.runtime.start_session(target=self.a, speech_mode=SpeechMode.CONTINUOUS)
        await self.runtime.set_answer_audio_enabled(False)
        client = self.clients[0]
        await client.emit("response.text.delta", delta="visible answer")
        await client.emit("response.audio.delta", delta=base64.b64encode(b"audio").decode("ascii"))
        events = await self.drain()
        self.assertFalse(any(isinstance(item, bytes) for item in events))
        self.assertTrue(any(isinstance(item, VoiceJSONEvent) and item.type == "assistant.text.delta" for item in events))
        self.assertEqual(self.runtime.snapshot()["answer_text"], "visible answer")

    async def test_response_done_retains_display_text_but_not_turn_state(self) -> None:
        await self.runtime.start_session(target=self.a, speech_mode=SpeechMode.CONTINUOUS)
        client = self.clients[0]
        await client.emit("conversation.item.input_audio_transcription.completed", transcript="question")
        await client.emit("response.text.done", text="answer")
        await client.emit("response.done")
        await self.drain()
        self.assertEqual(self.runtime.snapshot()["user_transcript"], "question")
        self.assertEqual(self.runtime.snapshot()["answer_text"], "answer")
        self.assertEqual(client.closed, 0)

    async def test_provider_error_falls_back_once_with_final_transcript(self) -> None:
        await self.runtime.start_session(target=self.a, speech_mode=SpeechMode.CONTINUOUS)
        client = self.clients[0]
        await client.emit("conversation.item.input_audio_transcription.completed", transcript="recover this")
        await client.emit("error", error={"message": "Authorization secret"})
        await client.emit("error", error={"message": "again"})
        events = await self.drain()
        self.assertEqual(self.fallbacks, [("omni_protocol_error", "recover this")])
        errors = [item for item in events if isinstance(item, VoiceJSONEvent) and item.type == "voice.error"]
        self.assertEqual(len(errors), 1)
        self.assertNotIn("Authorization", str(errors[0].payload))

    async def test_connect_failure_uses_sanitized_fallback(self) -> None:
        async def fallback(reason, transcript):
            self.fallbacks.append((reason, transcript))

        failing = OmniVoiceRuntime(
            events=self.hub,
            target_switching=TargetSwitchController(),
            client_factory=lambda: FakeClient(connect_error=True),
            begin_gaze_window=lambda target, timestamp: object(),
            resolve_gaze_window=lambda token, timestamp, target: None,
            on_fallback=fallback,
        )
        await failing.start_session(target=self.a, speech_mode=SpeechMode.CONTINUOUS)
        events = await self.drain()
        self.assertEqual(self.fallbacks[-1], ("omni_connect_failed", None))
        self.assertTrue(any(isinstance(item, VoiceJSONEvent) and item.type == "voice.error" for item in events))


if __name__ == "__main__":
    unittest.main()
