"""faster-whisper backed file transcription."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
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

        model = self._get_model()
        try:
            return self._transcribe_path(model, path)
        except Exception:
            if path.suffix.lower() != ".m4a":
                raise

        converted_path = self._convert_m4a_to_wav(path)
        try:
            return self._transcribe_path(model, converted_path)
        finally:
            converted_path.unlink(missing_ok=True)

    def _transcribe_path(self, model: Any, path: Path) -> Transcript:
        segments, info = model.transcribe(str(path), **self._transcribe_kwargs())
        text = _merge_segment_text(segments)
        language = getattr(info, "language", None) or self.config.language
        return Transcript(text=text, language=language, confidence=None)

    def _convert_m4a_to_wav(self, path: Path) -> Path:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError(
                "Could not decode .m4a directly and ffmpeg is unavailable for WAV fallback. "
                "Install ffmpeg or provide a .wav file."
            )

        with tempfile.NamedTemporaryFile(prefix=f"{path.stem}-", suffix=".wav", delete=False) as file:
            converted_path = Path(file.name)
        try:
            subprocess.run(
                [ffmpeg, "-nostdin", "-y", "-i", str(path), "-ac", "1", "-ar", "16000", str(converted_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            converted_path.unlink(missing_ok=True)
            raise RuntimeError("Could not convert .m4a to a temporary WAV fallback.") from exc
        return converted_path

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
                "pip install -r requirements.txt"
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
