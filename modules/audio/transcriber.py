"""Shared speech-to-text interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modules.common.schemas import Transcript


@dataclass(frozen=True)
class TranscriptionConfig:
    engine: str = "faster_whisper"
    model_size: str = "small"
    device: str = "auto"
    compute_type: str = "auto"
    language: str | None = None
    beam_size: int = 1
    vad_filter: bool = True


class SpeechToTextTranscriber(Protocol):
    def transcribe(self, audio_path: str) -> Transcript:
        ...

