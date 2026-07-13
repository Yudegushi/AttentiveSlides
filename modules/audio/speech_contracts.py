"""Contracts for tutor speech synthesis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_SPEECH_MODEL = (
    "qwen3-tts-instruct-flash"
)

DEFAULT_SPEECH_VOICE = "Cherry"

DEFAULT_SPEECH_LANGUAGE = "Chinese"

DEFAULT_TUTOR_SPEECH_INSTRUCTIONS = (
    "使用清晰、自然、耐心的教学语气。"
    "语速适中，重点概念适当停顿。"
    "不要加入原文中不存在的内容。"
)


@dataclass(frozen=True)
class SpeechSynthesisRequest:
    """Input sent to the speech synthesis provider."""

    text: str
    model: str = DEFAULT_SPEECH_MODEL
    voice: str = DEFAULT_SPEECH_VOICE
    language_type: str = (
        DEFAULT_SPEECH_LANGUAGE
    )
    instructions: str = (
        DEFAULT_TUTOR_SPEECH_INSTRUCTIONS
    )
    optimize_instructions: bool = True


@dataclass(frozen=True)
class SpeechSynthesisResult:
    """Sanitized result safe for application state and logs."""

    audio_path: str
    model: str
    voice: str
    language_type: str
    text_character_count: int
    text_sha256: str
    audio_bytes: int
    elapsed_ms: int
    mime_type: str = "audio/wav"
    provider: str = "aliyun_bailian"

    def to_public_dict(
        self,
    ) -> dict[str, Any]:
        """Return metadata without credentials or temporary URLs."""

        return asdict(self)

    @property
    def path(
        self,
    ) -> Path:
        return Path(
            self.audio_path
        )


class SpeechSynthesisError(
    RuntimeError
):
    """Raised when speech synthesis cannot complete."""
