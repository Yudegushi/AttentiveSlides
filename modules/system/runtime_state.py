"""Explicit lifecycle states for the continuous live runtime."""

from __future__ import annotations

from enum import Enum


class RuntimeState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    MONITORING = "monitoring"
    SPEECH_ACTIVE = "speech_active"
    FINALIZING_AUDIO = "finalizing_audio"
    PROCESSING_TURN = "processing_turn"
    WAITING_CONFIRMATION = "waiting_confirmation"
    ERROR = "error"
