"""Stable domain contracts for realtime voice integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class VoiceEngine(str, Enum):
    SINGLE_TURN = "single_turn"
    OMNI = "omni"


class SpeechMode(str, Enum):
    PUSH_TO_TALK = "push_to_talk"
    CONTINUOUS = "continuous"


class OmniSessionState(str, Enum):
    OFF = "off"
    CONNECTING = "connecting"
    READY = "ready"
    LISTENING = "listening"
    RESPONDING = "responding"
    PLAYING = "playing"
    SWITCH_PENDING = "switch_pending"
    ERROR = "error"


@dataclass(frozen=True)
class VoicePreferences:
    engine: VoiceEngine = VoiceEngine.SINGLE_TURN
    speech_mode: SpeechMode = SpeechMode.CONTINUOUS
    answer_audio_enabled: bool = True


@dataclass(frozen=True)
class TargetBinding:
    deck_id: str
    slide_id: int
    target_id: str
    label: str
    text: str
    bbox: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        deck_id = self.deck_id.strip()
        target_id = self.target_id.strip()
        if not deck_id:
            raise ValueError("deck_id must not be empty")
        if not target_id:
            raise ValueError("target_id must not be empty")
        if isinstance(self.slide_id, bool) or not isinstance(self.slide_id, int) or self.slide_id <= 0:
            raise ValueError("slide_id must be a positive integer")
        object.__setattr__(self, "deck_id", deck_id)
        object.__setattr__(self, "target_id", target_id)

        if self.bbox is None:
            return
        if len(self.bbox) != 4:
            raise ValueError("bbox must contain four coordinates")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in self.bbox):
            raise ValueError("bbox coordinates must be finite numbers")
        values = tuple(float(value) for value in self.bbox)
        if not all(isfinite(value) for value in values):
            raise ValueError("bbox coordinates must be finite numbers")
        left, top, right, bottom = values
        if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
            raise ValueError("bbox must be normalized with positive area")
        object.__setattr__(self, "bbox", values)

    @property
    def signature(self) -> str:
        return f"{self.deck_id}:{self.slide_id}:{self.target_id}"


@dataclass(frozen=True)
class OmniTurnResult:
    turn_id: str
    user_transcript: str
    answer_text: str
    target_signature: str
    response_audio_bytes: int
    elapsed_ms: int
