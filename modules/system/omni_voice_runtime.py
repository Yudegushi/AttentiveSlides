"""Persistent Omni conversation runtime owned by the ingress asyncio loop."""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from threading import RLock
from typing import Any
from uuid import uuid4

from modules.realtime.bailian_omni_realtime_client import (
    BailianOmniRealtimeClient,
    RealtimeEvent,
)
from modules.realtime.realtime_contracts import (
    OmniSessionState,
    OmniTurnResult,
    SpeechMode,
    TargetBinding,
)
from modules.system.target_switching import SwitchIntent, TargetSwitchController
from modules.system.voice_event_hub import VoiceEventHub


class OmniVoiceRuntime:
    """Keep one provider socket alive across turns for one confirmed target."""

    def __init__(
        self,
        *,
        events: VoiceEventHub,
        target_switching: TargetSwitchController,
        client_factory: Callable[[], BailianOmniRealtimeClient],
        begin_gaze_window: Callable[[TargetBinding, float], object],
        resolve_gaze_window: Callable[[object, float, TargetBinding], TargetBinding | None],
        on_fallback: Callable[[str, str | None], Awaitable[None]],
        on_target_confirmed: Callable[[TargetBinding], None] | None = None,
        build_instructions: Callable[[TargetBinding], str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._events = events
        self._target_switching = target_switching
        self._client_factory = client_factory
        self._begin_gaze_window = begin_gaze_window
        self._resolve_gaze_window = resolve_gaze_window
        self._on_fallback = on_fallback
        self._on_target_confirmed = on_target_confirmed or (lambda target: None)
        self._build_instructions = build_instructions or self._default_instructions
        self._clock = clock
        self._snapshot_lock = RLock()

        self._client: BailianOmniRealtimeClient | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._target: TargetBinding | None = None
        self._speech_mode = SpeechMode.CONTINUOUS
        self._state = OmniSessionState.OFF
        self._answer_audio_enabled = True
        self._stopping = False
        self._fallback_triggered = False

        self._ptt_active = False
        self._ptt_has_audio = False
        self._gaze_window: object | None = None
        self._turn_id = ""
        self._turn_started_at = 0.0
        self._transcript = ""
        self._final_transcript = ""
        self._answer_text = ""
        self._response_audio_bytes = 0
        self._last_transcript = ""
        self._last_answer_text = ""
        self._active_response_id = ""
        self._cancelled_response_ids: set[str] = set()
        self._ignore_unidentified_response_done = False
        self._pending_speech_mode_update: SpeechMode | None = None

    async def start_session(self, *, target: TargetBinding, speech_mode: SpeechMode) -> None:
        if self._client is not None and self._target is not None:
            if self._target.signature == target.signature:
                if self._speech_mode is not speech_mode:
                    await self.set_speech_mode(speech_mode)
                return
            await self.stop_session("target_changed")

        self._target_switching.bind(target)
        self._target = target
        self._speech_mode = speech_mode
        self._fallback_triggered = False
        self._stopping = False
        self._pending_speech_mode_update = None
        self._cancelled_response_ids.clear()
        self._ignore_unidentified_response_done = False
        self._reset_turn(clear_last=True)
        client = self._client_factory()
        self._client = client
        await self._set_state(OmniSessionState.CONNECTING)
        try:
            await client.connect(
                instructions=self._build_instructions(target),
                speech_mode=speech_mode,
            )
        except Exception:
            await self._trigger_fallback("omni_connect_failed")
            return
        if client is not self._client:
            await client.close()
            return
        await self._set_state(
            OmniSessionState.LISTENING
            if speech_mode is SpeechMode.CONTINUOUS
            else OmniSessionState.READY
        )
        self._receiver_task = asyncio.create_task(
            self._receiver_loop(client), name="attentiveslides-omni-receiver"
        )

    async def set_speech_mode(self, mode: SpeechMode) -> None:
        if self._speech_mode is mode:
            return
        client = self._require_client()
        previous_mode = self._speech_mode
        self._speech_mode = mode
        self._pending_speech_mode_update = mode
        try:
            await client.update_speech_mode(mode)
        except Exception:
            if self._pending_speech_mode_update is mode:
                self._pending_speech_mode_update = None
                self._speech_mode = previous_mode
            raise
        self._ptt_active = False
        self._ptt_has_audio = False
        self._gaze_window = None
        await self._set_state(
            OmniSessionState.LISTENING
            if mode is SpeechMode.CONTINUOUS
            else OmniSessionState.READY
        )

    async def set_answer_audio_enabled(self, enabled: bool) -> None:
        self._answer_audio_enabled = bool(enabled)
        if not enabled:
            await self._events.clear_playback()

    async def accept_pcm(self, session_id: str, pcm: bytes) -> None:
        del session_id
        if not pcm or self._client is None:
            return
        if self._speech_mode is SpeechMode.PUSH_TO_TALK:
            if not self._ptt_active:
                return
            self._ptt_has_audio = True
        await self._client.append_pcm(pcm)

    async def start_push_to_talk(self) -> None:
        if self._speech_mode is not SpeechMode.PUSH_TO_TALK or self._client is None:
            return
        if self._ptt_active:
            return
        if self._state in {OmniSessionState.RESPONDING, OmniSessionState.PLAYING}:
            await self.interrupt()
        self._ensure_turn()
        self._ptt_active = True
        self._ptt_has_audio = False
        self._begin_turn_gaze_window()
        await self._set_state(OmniSessionState.LISTENING)

    async def stop_push_to_talk(self) -> None:
        if not self._ptt_active:
            return
        self._ptt_active = False
        self._finish_turn_gaze_window()
        if not self._ptt_has_audio or self._client is None:
            await self._set_state(OmniSessionState.READY)
            return
        self._ptt_has_audio = False
        await self._client.commit_input()

    async def confirm_target_switch(self) -> None:
        decision = self._target_switching.confirm()
        if decision.intent is not SwitchIntent.CONFIRM:
            await self._events.publish_json(
                "target.switch.completed",
                {"switched": False, "message": decision.user_message or ""},
            )
            return
        await self._switch_to_confirmed_target(
            decision.active_target,
            decision.user_message or "",
        )

    async def reject_target_switch(self) -> None:
        decision = self._target_switching.reject()
        await self._events.publish_json(
            "target.switch.completed",
            {"switched": False, "message": decision.user_message or ""},
        )
        await self._set_state(
            OmniSessionState.LISTENING
            if self._speech_mode is SpeechMode.CONTINUOUS
            else OmniSessionState.READY
        )

    async def interrupt(self) -> None:
        client = self._client
        if client is not None:
            await client.cancel_response()
        if self._active_response_id:
            self._cancelled_response_ids.add(self._active_response_id)
        else:
            self._ignore_unidentified_response_done = True
        self._reset_turn(clear_last=False)
        await self._events.clear_playback()
        await self._set_state(
            OmniSessionState.LISTENING
            if self._speech_mode is SpeechMode.CONTINUOUS or self._ptt_active
            else OmniSessionState.READY
        )

    async def stop_session(self, reason: str) -> None:
        del reason
        self._stopping = True
        self._ptt_active = False
        self._ptt_has_audio = False
        self._gaze_window = None
        await self._events.clear_playback()
        await self._close_client()
        self._client = None
        self._target = None
        self._pending_speech_mode_update = None
        self._cancelled_response_ids.clear()
        self._ignore_unidentified_response_done = False
        self._reset_turn(clear_last=True)
        await self._set_state(OmniSessionState.OFF)
        self._stopping = False

    def snapshot(self) -> dict[str, object]:
        with self._snapshot_lock:
            pending = self._target_switching.pending
            return {
                "state": self._state.value,
                "speech_mode": self._speech_mode.value,
                "target_signature": self._target.signature if self._target else None,
                "user_transcript": self._transcript or self._last_transcript,
                "answer_text": self._answer_text or self._last_answer_text,
                "answer_audio_enabled": self._answer_audio_enabled,
                "ptt_active": self._ptt_active,
                "pending_target": (
                    {
                        "signature": pending.candidate.signature,
                        "label": pending.candidate.label,
                    }
                    if pending is not None
                    else None
                ),
                "fallback_triggered": self._fallback_triggered,
            }

    async def _receiver_loop(self, client: BailianOmniRealtimeClient) -> None:
        try:
            async for event in client.events():
                if client is not self._client:
                    return
                await self._handle_event(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._stopping and client is self._client:
                await self._trigger_fallback("omni_protocol_error")
        else:
            if not self._stopping and client is self._client and not self._fallback_triggered:
                await self._trigger_fallback("omni_connection_closed")

    async def _handle_event(self, event: RealtimeEvent) -> None:
        event_type = event.type
        payload = event.payload
        response_id = self._response_id(payload)
        if (
            event_type.startswith("response.")
            and event_type != "response.created"
            and response_id
            and response_id in self._cancelled_response_ids
        ):
            if event_type == "response.done":
                self._cancelled_response_ids.discard(response_id)
            return
        if event_type == "input_audio_buffer.speech_started":
            await self._handle_speech_started()
            return
        if event_type == "input_audio_buffer.speech_stopped":
            self._finish_turn_gaze_window()
            return
        if event_type == "conversation.item.input_audio_transcription.delta":
            self._ensure_turn()
            delta = str(payload.get("delta") or payload.get("text") or "")
            stash = str(payload.get("stash") or "")
            self._transcript += delta
            await self._events.publish_json(
                "user.transcript.delta", {"text": self._transcript + stash}
            )
            return
        if event_type in {
            "conversation.item.input_audio_transcription.completed",
            "conversation.item.input_audio_transcription.done",
        }:
            await self._handle_transcript_done(
                str(payload.get("transcript") or payload.get("text") or self._transcript)
            )
            return
        if event_type == "response.created":
            self._ensure_turn()
            self._active_response_id = response_id
            await self._set_state(OmniSessionState.RESPONDING)
            return
        if event_type in {"response.audio_transcript.delta", "response.text.delta"}:
            self._ensure_turn()
            delta = str(payload.get("delta") or "")
            self._answer_text += delta
            await self._events.publish_json(
                "assistant.text.delta", {"delta": delta, "text": self._answer_text}
            )
            return
        if event_type in {"response.audio_transcript.done", "response.text.done"}:
            completed = str(payload.get("transcript") or payload.get("text") or "")
            if completed:
                self._answer_text = completed
            await self._events.publish_json(
                "assistant.text.done", {"text": self._answer_text}
            )
            return
        if event_type == "response.audio.delta":
            self._ensure_turn()
            audio = base64.b64decode(str(payload.get("delta") or ""), validate=True)
            self._response_audio_bytes += len(audio)
            if self._answer_audio_enabled and audio:
                await self._set_state(OmniSessionState.PLAYING)
                await self._events.publish_audio(audio)
            return
        if event_type == "response.done":
            if not response_id and self._ignore_unidentified_response_done:
                self._ignore_unidentified_response_done = False
                return
            if (
                self._active_response_id
                and response_id
                and response_id != self._active_response_id
            ):
                return
            await self._finish_response()
            return
        if event_type == "session.updated":
            self._pending_speech_mode_update = None
            return
        if event_type == "error":
            if await self._recover_rejected_speech_mode_update():
                return
            await self._trigger_fallback("omni_protocol_error")

    async def _handle_speech_started(self) -> None:
        if self._state in {OmniSessionState.RESPONDING, OmniSessionState.PLAYING}:
            await self.interrupt()
        self._ensure_turn()
        self._begin_turn_gaze_window()
        await self._set_state(OmniSessionState.LISTENING)

    async def _handle_transcript_done(self, transcript: str) -> None:
        self._ensure_turn()
        self._final_transcript = " ".join(transcript.strip().split())
        self._transcript = self._final_transcript
        self._finish_turn_gaze_window()
        await self._events.publish_json(
            "user.transcript.done", {"text": self._final_transcript}
        )
        decision = self._target_switching.handle_transcript(self._final_transcript)
        if decision.intent is SwitchIntent.PROPOSE:
            await self._set_state(OmniSessionState.SWITCH_PENDING)
            await self._events.publish_json(
                "target.switch.pending",
                {
                    "target_signature": decision.pending.candidate.signature,
                    "label": decision.pending.candidate.label,
                    "message": decision.user_message or "",
                },
            )
            return
        if decision.intent is SwitchIntent.CONFIRM:
            await self._switch_to_confirmed_target(
                decision.active_target,
                decision.user_message or "",
            )
            return
        if decision.should_create_response:
            await self._set_state(OmniSessionState.RESPONDING)
            await self._require_client().create_response()
            return
        await self._events.publish_json(
            "voice.notice", {"message": decision.user_message or ""}
        )
        await self._set_state(
            OmniSessionState.LISTENING
            if self._speech_mode is SpeechMode.CONTINUOUS
            else OmniSessionState.READY
        )

    async def _finish_response(self) -> None:
        if not self._turn_id:
            return
        elapsed_ms = max(0, int((self._clock() - self._turn_started_at) * 1000))
        target_signature = self._target.signature if self._target else ""
        result = OmniTurnResult(
            turn_id=self._turn_id,
            user_transcript=self._final_transcript or self._transcript,
            answer_text=self._answer_text,
            target_signature=target_signature,
            response_audio_bytes=self._response_audio_bytes,
            elapsed_ms=elapsed_ms,
        )
        await self._events.publish_json("turn.done", asdict(result))
        self._last_transcript = result.user_transcript
        self._last_answer_text = result.answer_text
        self._reset_turn(clear_last=False)
        await self._set_state(
            OmniSessionState.LISTENING
            if self._speech_mode is SpeechMode.CONTINUOUS
            else OmniSessionState.READY
        )

    def _ensure_turn(self) -> None:
        if self._turn_id:
            return
        self._turn_id = "turn_" + uuid4().hex
        self._turn_started_at = self._clock()

    def _reset_turn(self, *, clear_last: bool) -> None:
        self._turn_id = ""
        self._turn_started_at = 0.0
        self._transcript = ""
        self._final_transcript = ""
        self._answer_text = ""
        self._response_audio_bytes = 0
        self._gaze_window = None
        self._active_response_id = ""
        if clear_last:
            self._last_transcript = ""
            self._last_answer_text = ""

    def _begin_turn_gaze_window(self) -> None:
        if self._gaze_window is not None or self._target is None:
            return
        self._gaze_window = self._begin_gaze_window(self._target, self._clock())

    def _finish_turn_gaze_window(self) -> None:
        window = self._gaze_window
        target = self._target
        if window is None or target is None:
            return
        self._gaze_window = None
        candidate = self._resolve_gaze_window(window, self._clock(), target)
        self._target_switching.observe_candidate(candidate)

    async def _set_state(self, state: OmniSessionState) -> None:
        with self._snapshot_lock:
            self._state = state
        await self._events.publish_json("voice.state", {"state": state.value})

    async def _trigger_fallback(self, reason: str) -> None:
        if self._fallback_triggered:
            return
        self._fallback_triggered = True
        transcript = self._final_transcript or None
        await self._set_state(OmniSessionState.ERROR)
        await self._events.clear_playback()
        await self._events.publish_json(
            "voice.error",
            {
                "code": reason,
                "message": "Omni 不可用，已切换到 Grounded Tutor 单轮模式。",
            },
        )
        await self._close_client()
        await self._on_fallback(reason, transcript)

    async def _switch_to_confirmed_target(
        self,
        target: TargetBinding,
        message: str,
    ) -> None:
        mode = self._speech_mode
        self._on_target_confirmed(target)
        await self._events.publish_json(
            "target.switch.completed",
            {
                "switched": True,
                "target_signature": target.signature,
                "message": message,
            },
        )
        await self._close_client()
        self._client = None
        self._target = None
        await self.start_session(target=target, speech_mode=mode)

    async def _recover_rejected_speech_mode_update(self) -> bool:
        if self._pending_speech_mode_update is None or self._target is None:
            return False
        target = self._target
        mode = self._speech_mode
        self._pending_speech_mode_update = None
        await self._events.publish_json(
            "voice.notice",
            {"message": "说话方式已切换，对话上下文已重置。"},
        )
        await self._close_client()
        self._client = None
        self._target = None
        await self.start_session(target=target, speech_mode=mode)
        return True

    async def _close_client(self) -> None:
        task = self._receiver_task
        self._receiver_task = None
        current = asyncio.current_task()
        if task is not None and task is not current:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        client = self._client
        self._client = None
        if client is not None:
            await client.close()

    def _require_client(self) -> BailianOmniRealtimeClient:
        if self._client is None:
            raise RuntimeError("Omni session is not active")
        return self._client

    @staticmethod
    def _response_id(payload: dict[str, Any]) -> str:
        response = payload.get("response")
        if isinstance(response, dict):
            return str(response.get("id") or "")
        return str(payload.get("response_id") or "")

    @staticmethod
    def _default_instructions(target: TargetBinding) -> str:
        return (
            "Answer concisely about only the confirmed target.\n"
            f"Confirmed target: {target.label or target.target_id}\n"
            f"Target context: {target.text}"
        )
