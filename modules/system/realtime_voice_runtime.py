"""State machine for push-to-talk and continuous realtime voice."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import (
    Awaitable,
    Callable,
)
import math
import os
import struct
from threading import RLock
import time
from typing import Any
from uuid import uuid4

from modules.realtime.bailian_omni_realtime_client import (
    BailianOmniRealtimeClient,
)
from modules.system.device_mode_state import (
    derive_interaction_mode,
)
from modules.system.realtime_tutor_context import (
    RealtimeTutorContext,
    build_realtime_tutor_instructions,
)
from modules.system.voice_response_gate import (
    VoiceGateDecision,
    evaluate_voice_turn,
)


JsonEmitter = Callable[
    [dict[str, Any]],
    Awaitable[None],
]

AudioEmitter = Callable[
    [bytes],
    Awaitable[None],
]

ClientFactory = Callable[
    [],
    BailianOmniRealtimeClient,
]


class RealtimeVoiceRuntime:
    """Own one current speech turn and one provider session."""

    def __init__(
        self,
        *,
        emit_json: JsonEmitter,
        emit_audio: AudioEmitter,
        client_factory: (
            ClientFactory | None
        ) = None,
    ) -> None:
        self._emit_json = emit_json
        self._emit_audio = emit_audio

        self._client_factory = (
            client_factory
            or BailianOmniRealtimeClient
        )

        self._state_lock = RLock()
        self._session_lock = (
            asyncio.Lock()
        )

        self._client: (
            BailianOmniRealtimeClient
            | None
        ) = None

        self._receiver_task: (
            asyncio.Task[Any] | None
        ) = None

        self._context = (
            RealtimeTutorContext(
                slide_number=1,
                slide_text="",
                selected_region_text="",
                target_scope=(
                    "Whole slide"
                ),
            )
        )

        self._camera_enabled = False
        self._microphone_enabled = (
            False
        )

        self._microphone_permission = (
            "unknown"
        )

        self._speaker_enabled = False

        self._microphone_session: (
            str | None
        ) = None

        self._last_heartbeat_at: (
            float | None
        ) = None

        self._continuous_enabled = (
            False
        )

        self._voice_state = "off"
        self._suppress_input = False
        self._cloud_available = bool(
            os.environ.get(
                "DASHSCOPE_API_KEY"
            )
        )

        self._turn_id = ""
        self._turn_started_at = 0.0

        self._input_pcm = bytearray()
        self._input_transcript = ""
        self._answer_text = ""

        self._gate_decision: (
            VoiceGateDecision | None
        ) = None

        self._pending_audio: list[
            bytes
        ] = []

        self._latest_user_transcript = ""
        self._latest_answer_text = ""
        self._latest_rejection_reason: (
            str | None
        ) = None
        self._latest_error: (
            str | None
        ) = None
        self._latest_elapsed_ms = 0

    def update_context(
        self,
        context: RealtimeTutorContext,
    ) -> None:
        with self._state_lock:
            self._context = context

    def set_cloud_available(
        self,
        available: bool,
    ) -> None:
        with self._state_lock:
            self._cloud_available = bool(
                available
            )

    def snapshot(
        self,
    ) -> dict[str, Any]:
        with self._state_lock:
            return {
                "camera_enabled": (
                    self._camera_enabled
                ),
                "microphone_enabled": (
                    self
                    ._microphone_enabled
                ),
                "microphone_permission": (
                    self
                    ._microphone_permission
                ),
                "speaker_enabled": (
                    self._speaker_enabled
                ),
                "interaction_mode": (
                    derive_interaction_mode(
                        camera_enabled=(
                            self
                            ._camera_enabled
                        ),
                        microphone_enabled=(
                            self
                            ._microphone_enabled
                        ),
                    )
                ),
                "cloud_tutor_available": (
                    self._cloud_available
                ),
                "continuous_enabled": (
                    self
                    ._continuous_enabled
                ),
                "voice_state": (
                    self._voice_state
                ),
                "suppress_input": (
                    self._suppress_input
                ),
                "turn_id": self._turn_id,
                "latest_user_transcript": (
                    self
                    ._latest_user_transcript
                ),
                "latest_answer_text": (
                    self
                    ._latest_answer_text
                ),
                "latest_rejection_reason": (
                    self
                    ._latest_rejection_reason
                ),
                "latest_error": (
                    self._latest_error
                ),
                "latest_elapsed_ms": (
                    self
                    ._latest_elapsed_ms
                ),
                "history_persisted": False,
            }

    async def toggle_camera(
        self,
    ) -> None:
        with self._state_lock:
            self._camera_enabled = (
                not self._camera_enabled
            )

    async def set_microphone(
        self,
        *,
        enabled: bool,
        permission: str,
        session_id: str,
    ) -> None:
        effective = bool(
            enabled
            and permission == "granted"
        )

        with self._state_lock:
            self._microphone_enabled = (
                effective
            )

            self._microphone_permission = (
                permission
            )

            self._microphone_session = (
                session_id
                if effective
                else None
            )

            self._last_heartbeat_at = (
                time.monotonic()
                if effective
                else None
            )

            if not effective:
                self._voice_state = "off"
                self._speaker_enabled = False

        if not effective:
            await self.stop_all()

    async def set_speaker_enabled(
        self,
        *,
        enabled: bool,
    ) -> None:
        """Enable or disable browser audio output."""

        with self._state_lock:
            self._speaker_enabled = bool(
                enabled
            )

            if (
                not self._speaker_enabled
                and self._voice_state
                == "playing"
            ):
                self._voice_state = (
                    "responding"
                )

        if not enabled:
            await self._emit_json(
                {
                    "type": (
                        "playback.clear"
                    )
                }
            )

    async def heartbeat(
        self,
        *,
        session_id: str,
    ) -> None:
        with self._state_lock:
            if (
                session_id
                != self._microphone_session
            ):
                return

            self._last_heartbeat_at = (
                time.monotonic()
            )

    async def expire_inactive_microphone(
        self,
        *,
        timeout_seconds: float = 4.0,
    ) -> bool:
        with self._state_lock:
            last = self._last_heartbeat_at

            expired = bool(
                self._microphone_enabled
                and last is not None
                and (
                    time.monotonic()
                    - last
                    > timeout_seconds
                )
            )

        if not expired:
            return False

        await self.set_microphone(
            enabled=False,
            permission="unknown",
            session_id="",
        )

        return True

    async def accept_pcm(
        self,
        *,
        session_id: str,
        pcm: bytes,
    ) -> None:
        if not pcm:
            return

        if len(pcm) % 2:
            raise ValueError(
                "PCM payload is not "
                "aligned to signed-16."
            )

        with self._state_lock:
            active_session = (
                self._microphone_session
            )

            microphone_enabled = (
                self._microphone_enabled
            )

            suppress = (
                self._suppress_input
            )

            should_forward = bool(
                (
                    self._voice_state
                    == "recording"
                )
                or self
                ._continuous_enabled
            )

            client = self._client

        if (
            not microphone_enabled
            or session_id
            != active_session
            or suppress
            or not should_forward
            or client is None
        ):
            return

        self._input_pcm.extend(
            pcm
        )

        await client.append_pcm(
            pcm
        )

    async def start_push_to_talk(
        self,
    ) -> None:
        self._require_microphone()

        with self._state_lock:
            if self._continuous_enabled:
                raise RuntimeError(
                    "Continuous mode "
                    "is active."
                )

        await self._open_session(
            continuous=False
        )

        with self._state_lock:
            self._voice_state = (
                "recording"
            )

        await self._emit_json(
            {
                "type": "state",
                "value": "recording",
            }
        )

    async def stop_push_to_talk(
        self,
    ) -> None:
        with self._state_lock:
            if (
                self._voice_state
                != "recording"
            ):
                return

            client = self._client
            self._voice_state = (
                "transcribing"
            )

        if client is None:
            return

        await client.commit_and_respond()

        await self._emit_json(
            {
                "type": "state",
                "value": (
                    "transcribing"
                ),
            }
        )

    async def start_continuous(
        self,
    ) -> None:
        self._require_microphone()

        with self._state_lock:
            if self._continuous_enabled:
                return

            self._continuous_enabled = (
                True
            )

        await self._open_session(
            continuous=True
        )

        with self._state_lock:
            self._voice_state = (
                "listening"
            )

        await self._emit_json(
            {
                "type": "state",
                "value": "listening",
            }
        )

    async def stop_continuous(
        self,
    ) -> None:
        with self._state_lock:
            self._continuous_enabled = (
                False
            )

        await self._emit_json(
            {
                "type": "playback.clear"
            }
        )

        await self._close_session()

        with self._state_lock:
            self._suppress_input = False
            self._voice_state = (
                "ready"
                if self
                ._microphone_enabled
                else "off"
            )

    async def stop_all(
        self,
    ) -> None:
        with self._state_lock:
            self._continuous_enabled = (
                False
            )

        await self._emit_json(
            {
                "type": "playback.clear"
            }
        )

        await self._close_session()

        with self._state_lock:
            self._suppress_input = False

            self._voice_state = (
                "ready"
                if self
                ._microphone_enabled
                else "off"
            )

    async def _open_session(
        self,
        *,
        continuous: bool,
    ) -> None:
        async with self._session_lock:
            await self._close_session(
                acquire_lock=False
            )

            context = self._context

            instructions = (
                build_realtime_tutor_instructions(
                    context
                )
            )

            client = (
                self._client_factory()
            )

            await client.connect(
                instructions=(
                    instructions
                ),
                continuous=continuous,
            )

            with self._state_lock:
                self._client = client
                self._turn_id = (
                    "voice_"
                    + uuid4().hex
                )

                self._turn_started_at = (
                    time.perf_counter()
                )

                self._input_pcm.clear()
                self._input_transcript = ""
                self._answer_text = ""
                self._gate_decision = None
                self._pending_audio.clear()
                self._latest_error = None
                self._latest_rejection_reason = (
                    None
                )

            self._receiver_task = (
                asyncio.create_task(
                    self._receive_events(
                        client=client,
                        continuous=(
                            continuous
                        ),
                    )
                )
            )

    async def _close_session(
        self,
        *,
        acquire_lock: bool = True,
    ) -> None:
        if acquire_lock:
            async with self._session_lock:
                await self._close_session(
                    acquire_lock=False
                )

            return

        current = asyncio.current_task()

        with self._state_lock:
            receiver = (
                self._receiver_task
            )
            client = self._client

            self._receiver_task = None
            self._client = None

        if (
            receiver is not None
            and receiver is not current
            and not receiver.done()
        ):
            receiver.cancel()

            try:
                await receiver

            except asyncio.CancelledError:
                pass

        if client is not None:
            await client.close()

    async def _receive_events(
        self,
        *,
        client: (
            BailianOmniRealtimeClient
        ),
        continuous: bool,
    ) -> None:
        should_restart = False

        try:
            async for event in (
                client.events()
            ):
                event_type = event.type
                payload = event.payload

                if (
                    event_type
                    == (
                        "input_audio_buffer"
                        ".speech_started"
                    )
                ):
                    with self._state_lock:
                        self._voice_state = (
                            "speech_active"
                        )

                    await self._emit_json(
                        {
                            "type": "state",
                            "value": (
                                "speech_active"
                            ),
                        }
                    )

                elif (
                    event_type
                    == (
                        "conversation.item."
                        "input_audio_"
                        "transcription."
                        "completed"
                    )
                ):
                    transcript = str(
                        payload.get(
                            "transcript",
                            payload.get(
                                "text",
                                "",
                            ),
                        )
                    ).strip()

                    decision = (
                        self
                        ._evaluate_current_turn(
                            transcript
                        )
                    )

                    with self._state_lock:
                        self._input_transcript = (
                            transcript
                        )

                        self._gate_decision = (
                            decision
                        )

                        self._latest_user_transcript = (
                            transcript
                        )

                    await self._emit_json(
                        {
                            "type": (
                                "input."
                                "transcript.done"
                            ),
                            "text": transcript,
                            "accepted": (
                                decision.accepted
                            ),
                            "reason": (
                                decision.reason
                            ),
                        }
                    )

                    if (
                        not decision.accepted
                    ):
                        await client.cancel_response()

                        await self._emit_json(
                            {
                                "type": (
                                    "turn.rejected"
                                ),
                                "reason": (
                                    decision.reason
                                ),
                            }
                        )

                        with self._state_lock:
                            self._latest_rejection_reason = (
                                decision.reason
                            )

                            self._voice_state = (
                                "rejected"
                            )

                elif (
                    event_type
                    == "response.created"
                ):
                    with self._state_lock:
                        self._voice_state = (
                            "responding"
                        )

                        self._suppress_input = (
                            continuous
                        )

                    await self._emit_json(
                        {
                            "type": "state",
                            "value": "responding",
                        }
                    )

                elif (
                    event_type
                    == (
                        "response."
                        "audio_transcript."
                        "delta"
                    )
                ):
                    delta = str(
                        payload.get(
                            "delta",
                            "",
                        )
                    )

                    with self._state_lock:
                        self._answer_text += (
                            delta
                        )

                        answer = (
                            self._answer_text
                        )

                    await self._emit_json(
                        {
                            "type": (
                                "answer.text.delta"
                            ),
                            "text": answer,
                        }
                    )

                elif (
                    event_type
                    == (
                        "response."
                        "audio_transcript."
                        "done"
                    )
                ):
                    final_text = str(
                        payload.get(
                            "transcript",
                            payload.get(
                                "text",
                                self._answer_text,
                            ),
                        )
                    ).strip()

                    if final_text:
                        with self._state_lock:
                            self._answer_text = (
                                final_text
                            )

                elif (
                    event_type
                    == "response.audio.delta"
                ):
                    encoded = str(
                        payload.get(
                            "delta",
                            "",
                        )
                    )

                    if not encoded:
                        continue

                    chunk = (
                        base64.b64decode(
                            encoded
                        )
                    )

                    with self._state_lock:
                        decision = (
                            self._gate_decision
                        )

                        speaker_enabled = (
                            self._speaker_enabled
                        )

                        if (
                            continuous
                            and speaker_enabled
                        ):
                            self._voice_state = (
                                "playing"
                            )

                    if (
                        continuous
                        and speaker_enabled
                        and decision is not None
                        and decision.accepted
                    ):
                        await self._emit_audio(
                            chunk
                        )

                elif (
                    event_type
                    == "response.done"
                ):
                    await self._finalize_turn(
                        continuous=continuous
                    )

                    with self._state_lock:
                        should_restart = bool(
                            self
                            ._continuous_enabled
                            and continuous
                        )

                    break

                elif event_type == "error":
                    error_payload = (
                        payload.get(
                            "error",
                            {},
                        )
                    )

                    message = str(
                        error_payload.get(
                            "message",
                            "Unknown provider error",
                        )
                    )

                    with self._state_lock:
                        self._latest_error = (
                            message
                        )

                        self._voice_state = (
                            "error"
                        )

                    await self._emit_json(
                        {
                            "type": "error",
                            "message": message,
                        }
                    )

                    break

        except asyncio.CancelledError:
            raise

        except Exception as error:
            message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            with self._state_lock:
                self._latest_error = (
                    message
                )
                self._voice_state = "error"

            await self._emit_json(
                {
                    "type": "error",
                    "message": message,
                }
            )

        finally:
            await client.close()

            with self._state_lock:
                if self._client is client:
                    self._client = None

                if (
                    self._receiver_task
                    is asyncio.current_task()
                ):
                    self._receiver_task = (
                        None
                    )

                self._suppress_input = (
                    False
                )

            if should_restart:
                asyncio.create_task(
                    self
                    ._restart_continuous()
                )

    async def _restart_continuous(
        self,
    ) -> None:
        await asyncio.sleep(
            0.05
        )

        with self._state_lock:
            enabled = (
                self._continuous_enabled
            )

            microphone = (
                self._microphone_enabled
            )

        if not (
            enabled
            and microphone
        ):
            return

        await self._open_session(
            continuous=True
        )

        with self._state_lock:
            self._voice_state = (
                "listening"
            )

    def _evaluate_current_turn(
        self,
        transcript: str,
    ) -> VoiceGateDecision:
        pcm = bytes(
            self._input_pcm
        )

        sample_count = (
            len(pcm) // 2
        )

        duration_ms = round(
            sample_count
            / 16_000
            * 1000
        )

        if not pcm:
            rms = 0.0

        else:
            samples = struct.unpack(
                "<"
                + "h" * sample_count,
                pcm,
            )

            squared_mean = (
                sum(
                    float(sample)
                    * float(sample)
                    for sample in samples
                )
                / max(
                    len(samples),
                    1,
                )
            )

            rms = math.sqrt(
                squared_mean
            )

        return evaluate_voice_turn(
            transcript=transcript,
            voiced_duration_ms=(
                duration_ms
            ),
            audio_rms=rms,
        )

    async def _finalize_turn(
        self,
        *,
        continuous: bool,
    ) -> None:
        with self._state_lock:
            decision = (
                self._gate_decision
                or VoiceGateDecision(
                    accepted=False,
                    reason=(
                        "missing_transcript"
                    ),
                )
            )

            transcript = (
                self._input_transcript
            )

            answer = (
                self._answer_text
            ).strip()

            elapsed_ms = round(
                (
                    time.perf_counter()
                    - self._turn_started_at
                )
                * 1000
            )

            if (
                decision.accepted
                and answer
            ):
                self._latest_user_transcript = (
                    transcript
                )

                self._latest_answer_text = (
                    answer
                )

                self._latest_rejection_reason = (
                    None
                )

                self._latest_elapsed_ms = (
                    elapsed_ms
                )

                self._voice_state = (
                    "listening"
                    if continuous
                    else "ready"
                )

            else:
                self._latest_rejection_reason = (
                    decision.reason
                    or "empty_answer"
                )

                self._voice_state = (
                    "listening"
                    if continuous
                    else "ready"
                )

        if (
            decision.accepted
            and answer
        ):
            await self._emit_json(
                {
                    "type": "turn.done",
                    "turn_id": self._turn_id,
                    "user_transcript": (
                        transcript
                    ),
                    "answer_text": answer,
                    "elapsed_ms": (
                        elapsed_ms
                    ),
                    "history_persisted": (
                        False
                    ),
                }
            )

        else:
            await self._emit_json(
                {
                    "type": "turn.rejected",
                    "reason": (
                        decision.reason
                        or "empty_answer"
                    ),
                }
            )

    def _require_microphone(
        self,
    ) -> None:
        with self._state_lock:
            valid = bool(
                self._microphone_enabled
                and self
                ._microphone_permission
                == "granted"
            )

        if not valid:
            raise RuntimeError(
                "Microphone permission "
                "is not granted."
            )
