"""Low-level persistent Qwen Omni Realtime WebSocket client."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import websockets

from modules.realtime.realtime_contracts import SpeechMode


@dataclass(frozen=True)
class RealtimeEvent:
    type: str
    payload: dict[str, Any]


class RealtimeProtocolError(RuntimeError):
    """A provider message could not be decoded safely."""


ConnectFunction = Callable[..., Awaitable[Any]]


class BailianOmniRealtimeClient:
    """Own one provider conversation until an explicit session boundary."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        workspace_id: str | None = None,
        model: str | None = None,
        region: str | None = None,
        voice: str | None = None,
        base_url: str | None = None,
        vad_threshold: float | None = None,
        silence_ms: int | None = None,
        connect_function: ConnectFunction | None = None,
    ) -> None:
        self.api_key = os.environ.get("DASHSCOPE_API_KEY") if api_key is None else api_key
        self.workspace_id = workspace_id or os.environ.get("DASHSCOPE_WORKSPACE_ID")
        self.model = model or os.environ.get(
            "ATTENTIVE_REALTIME_MODEL", "qwen3.5-omni-plus-realtime"
        )
        self.region = region or os.environ.get("ATTENTIVE_REALTIME_REGION", "beijing")
        self.voice = voice or os.environ.get("ATTENTIVE_REALTIME_VOICE", "Tina")
        self.base_url = (
            os.environ.get("ATTENTIVE_REALTIME_BASE_URL", "")
            if base_url is None
            else base_url
        )
        self.vad_threshold = (
            float(os.environ.get("ATTENTIVE_REALTIME_VAD_THRESHOLD", "0.5"))
            if vad_threshold is None
            else float(vad_threshold)
        )
        self.silence_ms = (
            int(os.environ.get("ATTENTIVE_REALTIME_SILENCE_MS", "800"))
            if silence_ms is None
            else int(silence_ms)
        )
        self._connect_function = connect_function or websockets.connect
        self._socket: Any = None
        self._send_lock = asyncio.Lock()
        self._instructions = ""

    @property
    def connected(self) -> bool:
        return self._socket is not None

    def endpoint(self) -> str:
        configured_base = self.base_url.strip()
        workspace_id = (self.workspace_id or "").strip()
        region = (self.region or "beijing").strip().casefold()
        placeholders = {
            "<your_workspace_id>",
            "your_workspace_id",
            "{workspaceid}",
            "<workspaceid>",
            "workspaceid",
            "none",
            "null",
        }
        workspace_valid = bool(
            workspace_id
            and workspace_id.casefold() not in placeholders
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", workspace_id)
        )
        international = region in {"singapore", "ap-southeast-1"}
        if configured_base:
            base_url = configured_base
        elif workspace_valid:
            zone = "ap-southeast-1" if international else "cn-beijing"
            base_url = f"wss://{workspace_id}.{zone}.maas.aliyuncs.com/api-ws/v1/realtime"
        else:
            host = "dashscope-intl.aliyuncs.com" if international else "dashscope.aliyuncs.com"
            base_url = f"wss://{host}/api-ws/v1/realtime"

        if any(token in base_url for token in ("<", ">", "{", "}")):
            raise RuntimeError("Realtime base URL contains an unresolved placeholder")
        parts = urlsplit(base_url)
        if parts.scheme != "wss":
            raise RuntimeError("Realtime base URL must use wss")
        if not parts.hostname:
            raise RuntimeError("Realtime base URL has no hostname")
        path = parts.path.rstrip("/") or "/api-ws/v1/realtime"
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["model"] = self.model
        return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))

    async def connect(self, *, instructions: str, speech_mode: SpeechMode) -> None:
        if self._socket is not None:
            raise RuntimeError("Realtime WebSocket is already connected")
        if not (self.api_key or "").strip():
            raise RuntimeError("DASHSCOPE_API_KEY is not configured")
        socket = await self._connect_function(
            self.endpoint(),
            additional_headers={"Authorization": "Bearer " + self.api_key.strip()},
            max_size=16 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        )
        self._socket = socket
        self._instructions = instructions
        try:
            await self._send_session_update(speech_mode, include_instructions=True)
        except BaseException:
            self._socket = None
            await socket.close()
            raise

    async def update_speech_mode(self, speech_mode: SpeechMode) -> None:
        await self._send_session_update(speech_mode, include_instructions=False)

    async def append_pcm(self, pcm: bytes) -> None:
        if not pcm:
            return
        await self.send(
            {
                "event_id": self._event_id(),
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm).decode("ascii"),
            }
        )

    async def commit_input(self) -> None:
        await self.send({"event_id": self._event_id(), "type": "input_audio_buffer.commit"})

    async def create_response(self) -> None:
        await self.send({"event_id": self._event_id(), "type": "response.create"})

    async def cancel_response(self) -> None:
        if self._socket is not None:
            await self.send({"event_id": self._event_id(), "type": "response.cancel"})

    async def send(self, payload: dict[str, Any]) -> None:
        socket = self._socket
        if socket is None:
            raise RuntimeError("Realtime WebSocket is not connected")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        async with self._send_lock:
            if socket is not self._socket:
                raise RuntimeError("Realtime WebSocket session changed")
            await socket.send(encoded)

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        socket = self._socket
        if socket is None:
            raise RuntimeError("Realtime WebSocket is not connected")
        async for raw_message in socket:
            if isinstance(raw_message, bytes):
                continue
            try:
                payload = json.loads(raw_message)
            except (TypeError, json.JSONDecodeError) as exc:
                raise RealtimeProtocolError("invalid provider JSON event") from exc
            if not isinstance(payload, dict):
                raise RealtimeProtocolError("provider event must be an object")
            yield RealtimeEvent(type=str(payload.get("type", "")), payload=payload)

    async def close(self) -> None:
        socket = self._socket
        self._socket = None
        if socket is not None:
            await socket.close()

    async def _send_session_update(
        self, speech_mode: SpeechMode, *, include_instructions: bool
    ) -> None:
        session: dict[str, Any] = {
            "modalities": ["text", "audio"],
            "voice": self.voice,
            "input_audio_format": "pcm",
            "output_audio_format": "pcm",
            "input_audio_transcription": {"model": "qwen3-asr-flash-realtime"},
            "turn_detection": self._turn_detection(speech_mode),
        }
        if include_instructions:
            session.update(
                {
                    "instructions": self._instructions,
                    "temperature": 0.4,
                    "max_tokens": 900,
                }
            )
        await self.send(
            {"event_id": self._event_id(), "type": "session.update", "session": session}
        )

    def _turn_detection(self, speech_mode: SpeechMode) -> dict[str, Any] | None:
        if speech_mode is SpeechMode.PUSH_TO_TALK:
            return None
        return {
            "type": "semantic_vad",
            "threshold": self.vad_threshold,
            "silence_duration_ms": self.silence_ms,
            "create_response": False,
            "interrupt_response": True,
        }

    @staticmethod
    def _event_id() -> str:
        return "event_" + uuid4().hex
