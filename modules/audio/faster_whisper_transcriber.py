"""faster-whisper backed file transcription."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.audio.transcriber import TranscriptionConfig
from modules.common.schemas import Transcript


class FasterWhisperTranscriber:
    def __init__(self, config: TranscriptionConfig | None = None) -> None:
        self.config = config or TranscriptionConfig(engine="faster_whisper")
        self._model: Any | None = None

    def transcribe(self, audio_path: str) -> Transcript:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        segments, info = self._get_model().transcribe(str(path), **self._transcribe_kwargs())
        text = _merge_segment_text(segments)
        language = getattr(info, "language", None) or self.config.language
        return Transcript(text=text, language=language, confidence=None)

    def _get_model(self) -> Any:
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def _load_model(self) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Install optional audio dependencies before using faster_whisper: "
                "pip install -r requirements-audio.txt"
            ) from exc

        kwargs: dict[str, Any] = {"device": self.config.device}
        if self.config.compute_type != "auto":
            kwargs["compute_type"] = self.config.compute_type
        return WhisperModel(self.config.model_size, **kwargs)

    def _transcribe_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "beam_size": self.config.beam_size,
            "vad_filter": self.config.vad_filter,
        }
        if self.config.language is not None:
            kwargs["language"] = self.config.language
        return kwargs


def _merge_segment_text(segments: Any) -> str:
    parts = []
    for segment in segments:
        text = getattr(segment, "text", "")
        stripped = str(text).strip()
        if stripped:
            parts.append(stripped)
    return " ".join(parts).strip()
