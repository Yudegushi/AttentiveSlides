"""Thread-safe selection and routing for the two voice engines."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from threading import RLock
from typing import Any

from aiohttp import web

from modules.realtime.realtime_contracts import (
    SpeechMode,
    TargetBinding,
    VoiceEngine,
    VoicePreferences,
)
from modules.system.omni_voice_runtime import OmniVoiceRuntime
from modules.system.single_turn_ptt_runtime import SingleTurnPTTRuntime
from modules.system.target_switching import TargetSwitchController
from modules.system.voice_event_hub import VoiceEventHub, VoiceJSONEvent


class VoiceOrchestrator:
    """Expose a synchronous UI facade and loop-owned async voice transport."""

    def __init__(
        self,
        *,
        events: VoiceEventHub,
        omni: OmniVoiceRuntime,
        single_turn_ptt: SingleTurnPTTRuntime,
        target_switching: TargetSwitchController,
        publish_single_turn_transcript: Callable[[str], None],
        on_target_changed: Callable[[TargetBinding], None] | None = None,
    ) -> None:
        self._events = events
        self._omni = omni
        self._single_turn_ptt = single_turn_ptt
        self._target_switching = target_switching
        self._publish_single_turn_transcript = publish_single_turn_transcript
        self._on_target_changed = on_target_changed or (lambda target: None)
        self._lock = RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._preferences = VoicePreferences()
        self._target: TargetBinding | None = None
        self._active_session_id: str | None = None
        self._continuous_requested = False
        self._status_message: str | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            if self._loop is not None and self._loop is not loop:
                raise RuntimeError("voice orchestrator is already attached to another loop")
            self._loop = loop

    def update_preferences(self, preferences: VoicePreferences) -> None:
        with self._lock:
            previous = self._preferences
            if previous == preferences:
                return
            self._preferences = preferences
        self._submit(lambda: self._apply_preferences(previous, preferences))

    def update_target(self, target: TargetBinding) -> None:
        with self._lock:
            previous = self._target
            if previous is not None and previous.signature == target.signature:
                self._target = target
                return
            self._target = target
        self._submit(lambda: self._apply_target_change(previous, target))

    def clear_target(self, reason: str = "target unavailable") -> None:
        """Remove a stale target and stop any session that depended on it."""
        with self._lock:
            previous = self._target
            self._target = None
        self._target_switching.clear()
        if previous is not None:
            self._submit(lambda: self._stop_for_missing_target(reason))

    def should_consume_audio(self) -> bool:
        with self._lock:
            preferences = self._preferences
        return (
            preferences.engine is VoiceEngine.OMNI
            or preferences.speech_mode is SpeechMode.PUSH_TO_TALK
        )

    async def accept_pcm(self, session_id: str, pcm: bytes) -> None:
        with self._lock:
            preferences = self._preferences
            active_session_id = self._active_session_id
        if session_id != active_session_id:
            return
        if preferences.engine is VoiceEngine.SINGLE_TURN:
            if preferences.speech_mode is SpeechMode.PUSH_TO_TALK:
                await self._single_turn_ptt.accept_pcm(session_id=session_id, pcm=pcm)
            return
        await self._omni.accept_pcm(session_id, pcm)

    async def handle_http_command(
        self, command: str, session_id: str
    ) -> dict[str, object]:
        preferences = self._preferences_snapshot()
        if command == "ptt/start":
            if preferences.speech_mode is not SpeechMode.PUSH_TO_TALK:
                raise ValueError("push to talk is not selected")
            await self._adopt_session(session_id)
            target = self._require_target()
            if preferences.engine is VoiceEngine.SINGLE_TURN:
                await self._single_turn_ptt.start(session_id=session_id, target=target)
            else:
                await self._ensure_omni(target, preferences)
                await self._omni.start_push_to_talk()
        elif command == "ptt/stop":
            if preferences.engine is VoiceEngine.SINGLE_TURN:
                await self._single_turn_ptt.stop(session_id=session_id)
            else:
                await self._omni.stop_push_to_talk()
        elif command == "continuous/start":
            if preferences.speech_mode is not SpeechMode.CONTINUOUS:
                raise ValueError("continuous speaking is not selected")
            target = (
                self._require_target()
                if preferences.engine is VoiceEngine.OMNI
                else None
            )
            with self._lock:
                already_requested = (
                    self._active_session_id == session_id
                    and self._continuous_requested
                )
            await self._adopt_session(session_id)
            with self._lock:
                self._continuous_requested = True
            if preferences.engine is VoiceEngine.OMNI and not already_requested:
                assert target is not None
                await self._ensure_omni(target, preferences)
        elif command == "continuous/stop":
            self._continuous_requested = False
            if preferences.engine is VoiceEngine.OMNI:
                await self._omni.stop_session("continuous stopped")
        elif command == "target/confirm":
            if preferences.engine is not VoiceEngine.OMNI:
                raise ValueError("target switching belongs to Omni mode")
            await self._omni.confirm_target_switch()
            active = self._target_switching.active_target
            if active is not None:
                with self._lock:
                    self._target = active
                self._on_target_changed(active)
        elif command == "target/reject":
            if preferences.engine is not VoiceEngine.OMNI:
                raise ValueError("target switching belongs to Omni mode")
            await self._omni.reject_target_switch()
        else:
            raise ValueError("unknown voice command")
        return self.snapshot()

    async def fallback_to_single_turn(
        self, reason: str, transcript: str | None = None
    ) -> None:
        del reason
        with self._lock:
            current = self._preferences
            self._preferences = VoicePreferences(
                engine=VoiceEngine.SINGLE_TURN,
                speech_mode=current.speech_mode,
                answer_audio_enabled=current.answer_audio_enabled,
            )
            self._status_message = "Omni 不可用，已切换到 Grounded Tutor 单轮模式。"
        await self._omni.stop_session("fallback")
        await self._events.clear_playback()
        if transcript and transcript.strip():
            self._publish_single_turn_transcript(transcript.strip())
        await self._events.publish_json(
            "voice.fallback",
            {
                "engine": VoiceEngine.SINGLE_TURN.value,
                "message": self._status_message,
                "transcript_recovered": bool(transcript and transcript.strip()),
            },
        )

    async def stop(self, reason: str) -> None:
        with self._lock:
            self._active_session_id = None
            self._continuous_requested = False
        await self._single_turn_ptt.cancel(reason)
        await self._omni.stop_session(reason)
        await self._events.clear_playback()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            preferences = self._preferences
            target = self._target
            active_session_id = self._active_session_id
            status_message = self._status_message
        if preferences.engine is VoiceEngine.OMNI:
            engine_state = self._omni.snapshot()
            state = str(engine_state.get("state", "off"))
        else:
            ptt = self._single_turn_ptt.snapshot()
            if preferences.speech_mode is SpeechMode.PUSH_TO_TALK:
                state = "listening" if ptt["recording"] else ("ready" if active_session_id else "off")
            else:
                state = "listening" if active_session_id else "off"
            engine_state = {"ptt": ptt}
        return {
            **engine_state,
            "engine": preferences.engine.value,
            "speech_mode": preferences.speech_mode.value,
            "answer_audio_enabled": preferences.answer_audio_enabled,
            "state": state,
            "session_id": active_session_id,
            "target_signature": target.signature if target else None,
            "target_label": target.label if target else None,
            "status_message": status_message,
        }

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        session_id = request.query.get("session", "")
        subscription = await self._events.subscribe(session_id)
        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        try:
            await socket.send_json(
                {
                    "type": "audio.config",
                    "payload": {"sample_rate": 24000, "channels": 1, "sample_width": 2},
                }
            )
            await socket.send_json({"type": "voice.snapshot", "payload": self.snapshot()})
            while not socket.closed:
                message = await subscription.receive()
                if isinstance(message, bytes):
                    await socket.send_bytes(message)
                else:
                    await socket.send_json(
                        {
                            "sequence": message.sequence,
                            "type": message.type,
                            "payload": message.payload,
                        }
                    )
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            await self._events.unsubscribe(subscription)
        return socket

    async def _apply_preferences(
        self, previous: VoicePreferences, current: VoicePreferences
    ) -> None:
        if previous.engine is not current.engine:
            await self._single_turn_ptt.cancel("voice engine changed")
            await self._omni.stop_session("voice engine changed")
            if current.engine is VoiceEngine.OMNI:
                with self._lock:
                    session_id = self._active_session_id
                    target = self._target
                    continuous = self._continuous_requested
                if session_id and target and continuous:
                    await self._ensure_omni(target, current)
        elif current.engine is VoiceEngine.OMNI:
            omni_state = self._omni.snapshot().get("state")
            if previous.speech_mode is not current.speech_mode and omni_state != "off":
                try:
                    await self._omni.set_speech_mode(current.speech_mode)
                except Exception:
                    await self._omni.stop_session("speech mode update failed")
                    with self._lock:
                        target = self._target
                        active = self._active_session_id is not None
                    if target is not None and active:
                        await self._ensure_omni(target, current)
                    await self._events.publish_json(
                        "voice.notice",
                        {"message": "说话方式已切换，对话上下文已重置。"},
                    )
        await self._omni.set_answer_audio_enabled(current.answer_audio_enabled)

    async def _apply_target_change(
        self, previous: TargetBinding | None, target: TargetBinding
    ) -> None:
        preferences = self._preferences_snapshot()
        if preferences.engine is not VoiceEngine.OMNI:
            return
        with self._lock:
            active = self._active_session_id is not None
            continuous = self._continuous_requested
        if previous is None:
            if active and continuous:
                await self._ensure_omni(target, preferences)
            return
        await self._omni.stop_session("confirmed target changed")
        if active and (continuous or preferences.speech_mode is SpeechMode.PUSH_TO_TALK):
            await self._ensure_omni(target, preferences)

    async def _stop_for_missing_target(self, reason: str) -> None:
        await self._single_turn_ptt.cancel(reason)
        await self._omni.stop_session(reason)
        await self._events.clear_playback()

    async def _adopt_session(self, session_id: str) -> None:
        with self._lock:
            previous = self._active_session_id
            if previous == session_id:
                return
            self._active_session_id = session_id
        if previous is not None:
            await self._single_turn_ptt.cancel("browser session replaced")
            await self._omni.stop_session("browser session replaced")
            await self._events.clear_playback()

    async def _ensure_omni(
        self, target: TargetBinding, preferences: VoicePreferences
    ) -> None:
        await self._omni.start_session(target=target, speech_mode=preferences.speech_mode)
        await self._omni.set_answer_audio_enabled(preferences.answer_audio_enabled)

    def _require_target(self) -> TargetBinding:
        with self._lock:
            target = self._target
        if target is None:
            raise ValueError("confirm a target before starting voice")
        return target

    def _preferences_snapshot(self) -> VoicePreferences:
        with self._lock:
            return self._preferences

    def _submit(
        self, factory: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        with self._lock:
            loop = self._loop
        if loop is None or not loop.is_running():
            return

        def schedule() -> None:
            asyncio.create_task(factory())

        loop.call_soon_threadsafe(schedule)
