"""System adapter boundary for file-based audio transcripts."""

from __future__ import annotations

from modules.audio.transcriber import SpeechToTextTranscriber
from modules.common.schemas import Transcript


class AudioFileTranscriptProvider:
    def __init__(self, audio_path: str, transcriber: SpeechToTextTranscriber) -> None:
        self.audio_path = audio_path
        self.transcriber = transcriber
        self._transcript: Transcript | None = None

    def get_transcript(self) -> Transcript:
        if self._transcript is None:
            self._transcript = self.transcriber.transcribe(self.audio_path)
        return self._transcript
