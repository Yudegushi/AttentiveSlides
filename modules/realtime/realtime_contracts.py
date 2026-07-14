"""Contracts for realtime voice interaction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RealtimeVoiceMode(
    str,
    Enum,
):
    OFF = "off"
    PUSH_TO_TALK = "push_to_talk"
    CONTINUOUS = "continuous"


class RealtimeVoiceState(
    str,
    Enum,
):
    OFF = "off"
    PERMISSION_REQUIRED = "permission_required"
    READY = "ready"
    RECORDING = "recording"
    LISTENING = "listening"
    SPEECH_ACTIVE = "speech_active"
    TRANSCRIBING = "transcribing"
    RESPONDING = "responding"
    PLAYING = "playing"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass(frozen=True)
class DeviceState:
    camera_enabled: bool = False
    microphone_enabled: bool = False
    microphone_permission: str = "unknown"

    @property
    def interaction_mode(
        self,
    ) -> str:
        return (
            "hybrid"
            if (
                self.camera_enabled
                or self.microphone_enabled
            )
            else "manual"
        )


@dataclass(frozen=True)
class RealtimeTurnResult:
    turn_id: str
    user_transcript: str
    answer_text: str
    accepted: bool
    rejection_reason: str | None
    input_language: str | None
    input_emotion: str | None
    response_audio_bytes: int
    elapsed_ms: int

    def to_public_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "user_transcript": (
                self.user_transcript
            ),
            "answer_text": self.answer_text,
            "accepted": self.accepted,
            "rejection_reason": (
                self.rejection_reason
            ),
            "input_language": (
                self.input_language
            ),
            "input_emotion": (
                self.input_emotion
            ),
            "response_audio_bytes": (
                self.response_audio_bytes
            ),
            "elapsed_ms": self.elapsed_ms,
        }
