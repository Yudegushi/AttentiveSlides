"""Public Member 3 speech-to-text entry point."""

from __future__ import annotations

from modules.audio.faster_whisper_transcriber import FasterWhisperTranscriber
from modules.audio.mock_transcriber import MockTranscriber
from modules.audio.transcriber import TranscriptionConfig
from modules.common.schemas import Transcript


def transcribe_audio(audio_path: str, config: TranscriptionConfig | None = None) -> Transcript:
    stt_config = config or TranscriptionConfig()
    if stt_config.engine == "mock":
        return MockTranscriber().transcribe(audio_path)
    if stt_config.engine == "faster_whisper":
        return FasterWhisperTranscriber(stt_config).transcribe(audio_path)
    raise ValueError(f"Unsupported STT engine: {stt_config.engine}")

