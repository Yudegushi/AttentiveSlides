"""Low-level Qwen3.5-Omni-Realtime WebSocket client."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
)
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import websockets


@dataclass(frozen=True)
class RealtimeEvent:
    type: str
    payload: dict[str, Any]


ConnectFunction = Callable[
    ...,
    Awaitable[Any],
]


class BailianOmniRealtimeClient:
    """One stateless Qwen-Omni realtime session."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        workspace_id: str | None = None,
        model: str | None = None,
        region: str | None = None,
        voice: str | None = None,
        connect_function: (
            ConnectFunction | None
        ) = None,
    ) -> None:
        self.api_key = (
            os.environ.get(
                "DASHSCOPE_API_KEY"
            )
            if api_key is None
            else api_key
        )

        self.workspace_id = (
            workspace_id
            or os.environ.get(
                "DASHSCOPE_WORKSPACE_ID"
            )
        )

        self.model = (
            model
            or os.environ.get(
                "ATTENTIVE_REALTIME_MODEL",
                (
                    "qwen3.5-omni-"
                    "plus-realtime"
                ),
            )
        )

        self.region = (
            region
            or os.environ.get(
                "ATTENTIVE_REALTIME_REGION",
                "beijing",
            )
        )

        self.voice = (
            voice
            or os.environ.get(
                "ATTENTIVE_REALTIME_VOICE",
                "Tina",
            )
        )

        self._connect_function = (
            connect_function
            or websockets.connect
        )

        self._socket: Any = None

    def endpoint(self) -> str:
        """Return a validated provider WebSocket URL.

        Resolution order:
        1. ATTENTIVE_REALTIME_BASE_URL
        2. Workspace-specific domain
        3. Legacy regional DashScope domain
        """

        import re
        from urllib.parse import (
            parse_qsl,
            urlencode,
            urlsplit,
            urlunsplit,
        )

        configured_base = (
            os.environ.get(
                "ATTENTIVE_REALTIME_BASE_URL",
                "",
            )
            .strip()
        )

        workspace_id = (
            self.workspace_id or ""
        ).strip()

        region = (
            self.region
            or "beijing"
        ).strip().casefold()

        placeholder_values = {
            "<your_workspace_id>",
            "your_workspace_id",
            "{workspaceid}",
            "<workspaceid>",
            "workspaceid",
            "none",
            "null",
        }

        workspace_normalized = (
            workspace_id.casefold()
        )

        workspace_is_valid = bool(
            workspace_id
            and workspace_normalized
            not in placeholder_values
            and re.fullmatch(
                r"[A-Za-z0-9]"
                r"[A-Za-z0-9-]{0,62}",
                workspace_id,
            )
        )

        if configured_base:
            base_url = configured_base

        elif workspace_is_valid:
            if region in {
                "singapore",
                "ap-southeast-1",
            }:
                host = (
                    f"{workspace_id}."
                    "ap-southeast-1."
                    "maas.aliyuncs.com"
                )

            else:
                host = (
                    f"{workspace_id}."
                    "cn-beijing."
                    "maas.aliyuncs.com"
                )

            base_url = (
                f"wss://{host}"
                "/api-ws/v1/realtime"
            )

        else:
            if region in {
                "singapore",
                "ap-southeast-1",
            }:
                host = (
                    "dashscope-intl."
                    "aliyuncs.com"
                )

            else:
                host = (
                    "dashscope.aliyuncs.com"
                )

            base_url = (
                f"wss://{host}"
                "/api-ws/v1/realtime"
            )

        if any(
            token in base_url
            for token in (
                "<",
                ">",
                "{",
                "}",
            )
        ):
            raise RuntimeError(
                "Realtime base URL still contains "
                "an unresolved placeholder."
            )

        parts = urlsplit(
            base_url
        )

        if parts.scheme != "wss":
            raise RuntimeError(
                "Realtime base URL must use "
                "the wss scheme."
            )

        if not parts.hostname:
            raise RuntimeError(
                "Realtime base URL has no hostname."
            )

        path = (
            parts.path.rstrip("/")
            or "/api-ws/v1/realtime"
        )

        query = dict(
            parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
        )

        query["model"] = self.model

        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                path,
                urlencode(query),
                "",
            )
        )

    async def connect(
        self,
        *,
        instructions: str,
        continuous: bool,
    ) -> None:
        if not self.api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY "
                "is not configured."
            )

        self._socket = (
            await self._connect_function(
                self.endpoint(),
                additional_headers={
                    "Authorization": (
                        "Bearer "
                        + self.api_key
                    )
                },
                max_size=(
                    16 * 1024 * 1024
                ),
                ping_interval=20,
                ping_timeout=20,
            )
        )

        if continuous:
            turn_detection: (
                dict[str, Any] | None
            ) = {
                "type": "semantic_vad",
                "threshold": float(
                    os.environ.get(
                        (
                            "ATTENTIVE_"
                            "REALTIME_VAD_"
                            "THRESHOLD"
                        ),
                        "0.5",
                    )
                ),
                "silence_duration_ms": int(
                    os.environ.get(
                        (
                            "ATTENTIVE_"
                            "REALTIME_"
                            "SILENCE_MS"
                        ),
                        "800",
                    )
                ),
                "create_response": True,
                "interrupt_response": (
                    False
                ),
            }

        else:
            turn_detection = None

        await self.send(
            {
                "event_id": (
                    "event_"
                    + uuid4().hex
                ),
                "type": "session.update",
                "session": {
                    "modalities": [
                        "text",
                        "audio",
                    ],
                    "voice": self.voice,
                    "input_audio_format": (
                        "pcm"
                    ),
                    "output_audio_format": (
                        "pcm"
                    ),
                    "input_audio_transcription": {
                        "model": (
                            "qwen3-asr-"
                            "flash-realtime"
                        )
                    },
                    "instructions": (
                        instructions
                    ),
                    "turn_detection": (
                        turn_detection
                    ),
                    "temperature": 0.4,
                    "max_tokens": 900,
                },
            }
        )

    async def append_pcm(
        self,
        pcm: bytes,
    ) -> None:
        if not pcm:
            return

        await self.send(
            {
                "event_id": (
                    "event_"
                    + uuid4().hex
                ),
                "type": (
                    "input_audio_buffer"
                    ".append"
                ),
                "audio": (
                    base64.b64encode(
                        pcm
                    ).decode(
                        "ascii"
                    )
                ),
            }
        )

    async def commit_and_respond(
        self,
    ) -> None:
        await self.send(
            {
                "event_id": (
                    "event_"
                    + uuid4().hex
                ),
                "type": (
                    "input_audio_buffer"
                    ".commit"
                ),
            }
        )

        await self.send(
            {
                "event_id": (
                    "event_"
                    + uuid4().hex
                ),
                "type": "response.create",
            }
        )

    async def cancel_response(
        self,
    ) -> None:
        if self._socket is None:
            return

        await self.send(
            {
                "event_id": (
                    "event_"
                    + uuid4().hex
                ),
                "type": "response.cancel",
            }
        )

    async def clear_input(
        self,
    ) -> None:
        if self._socket is None:
            return

        await self.send(
            {
                "event_id": (
                    "event_"
                    + uuid4().hex
                ),
                "type": (
                    "input_audio_buffer"
                    ".clear"
                ),
            }
        )

    async def send(
        self,
        payload: dict[str, Any],
    ) -> None:
        if self._socket is None:
            raise RuntimeError(
                "Realtime WebSocket "
                "is not connected."
            )

        await self._socket.send(
            json.dumps(
                payload,
                ensure_ascii=False,
            )
        )

    async def events(
        self,
    ) -> AsyncIterator[
        RealtimeEvent
    ]:
        if self._socket is None:
            raise RuntimeError(
                "Realtime WebSocket "
                "is not connected."
            )

        async for raw_message in (
            self._socket
        ):
            if isinstance(
                raw_message,
                bytes,
            ):
                continue

            payload = json.loads(
                raw_message
            )

            yield RealtimeEvent(
                type=str(
                    payload.get(
                        "type",
                        "",
                    )
                ),
                payload=payload,
            )

    async def close(
        self,
    ) -> None:
        socket = self._socket
        self._socket = None

        if socket is not None:
            await socket.close()
