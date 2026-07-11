"""Deterministic transcription for tests and dry-run demos."""

from __future__ import annotations

from pathlib import Path

from modules.common.schemas import Transcript


DEFAULT_MOCK_TRANSCRIPTS: dict[str, str] = {
    "explain_this": "解释一下这个",
    "right_figure": "讲讲右边这个图",
    "meaning_this_figure": "这个图是什么意思",
    "summarize_slide": "总结一下这一页",
    "quiz_concept": "考我一下这个概念",
}


class MockTranscriber:
    def __init__(self, transcripts: dict[str, str] | None = None, language: str = "zh") -> None:
        self.transcripts = transcripts or DEFAULT_MOCK_TRANSCRIPTS
        self.language = language

    def transcribe(self, audio_path: str) -> Transcript:
        sample_id = Path(audio_path).stem
        text = self.transcripts.get(sample_id)
        if text is None:
            known = ", ".join(sorted(self.transcripts))
            raise ValueError(f"No mock transcript configured for '{sample_id}'. Known samples: {known}.")
        return Transcript(text=text, language=self.language, confidence=None)

