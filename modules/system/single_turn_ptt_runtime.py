"""Button-bounded single-turn STT routed into the existing proposal flow."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
import time
import wave

import numpy as np

from modules.audio.voice_turn_detector import SpeechTurn
from modules.common.schemas import Transcript
from modules.realtime.realtime_contracts import TargetBinding
from modules.system.audio_worker import AudioTurnResult


class SingleTurnPTTRuntime:
    SAMPLE_RATE = 16_000
    CHANNELS = 1
    SAMPLE_WIDTH = 2

    def __init__(
        self,
        *,
        transcribe: Callable[[str], Transcript],
        context_collector,
        proposal_runner,
        on_status: Callable[[str, str | None], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        maximum_seconds: float = 20.0,
        minimum_seconds: float = 0.3,
    ) -> None:
        if maximum_seconds <= 0 or minimum_seconds <= 0:
            raise ValueError("PTT duration limits must be positive")
        if minimum_seconds > maximum_seconds:
            raise ValueError("minimum_seconds must not exceed maximum_seconds")
        self._transcribe = transcribe
        self._context_collector = context_collector
        self._proposal_runner = proposal_runner
        self._on_status = on_status or (lambda status, message: None)
        self._clock = clock
        self.maximum_seconds = float(maximum_seconds)
        self.minimum_seconds = float(minimum_seconds)
        self._maximum_bytes = int(
            self.maximum_seconds * self.SAMPLE_RATE * self.SAMPLE_WIDTH
        )
        self._lock = asyncio.Lock()
        self._generation = 0
        self._recording = False
        self._session_id: str | None = None
        self._target: TargetBinding | None = None
        self._started_at = 0.0
        self._context = None
        self._buffer = bytearray()
        self._overflowed = False
        self._last_status = "idle"
        self._last_message: str | None = None

    async def start(self, *, session_id: str, target: TargetBinding) -> None:
        async with self._lock:
            if self._recording and self._session_id == session_id:
                return
            self._generation += 1
            self._recording = True
            self._session_id = session_id
            self._target = target
            self._started_at = self._clock()
            self._context = self._context_collector.freeze_start(
                slide_id=target.slide_id,
                speech_started_at=self._started_at,
            )
            self._buffer = bytearray()
            self._overflowed = False
            self._set_status("recording", None)

    async def accept_pcm(self, *, session_id: str, pcm: bytes) -> None:
        if not pcm:
            return
        if len(pcm) % self.SAMPLE_WIDTH:
            raise ValueError("PTT PCM must be aligned signed-16 audio")
        async with self._lock:
            if not self._recording or session_id != self._session_id:
                return
            if self._overflowed:
                return
            if len(self._buffer) + len(pcm) > self._maximum_bytes:
                self._overflowed = True
                self._buffer.clear()
                self._set_status("too_long", "PTT input exceeded 20 seconds.")
                return
            self._buffer.extend(pcm)

    async def stop(self, *, session_id: str) -> None:
        async with self._lock:
            if not self._recording or session_id != self._session_id:
                return
            generation = self._generation
            self._recording = False
            target = self._target
            context = self._context
            started_at = self._started_at
            ended_at = self._clock()
            pcm = bytes(self._buffer)
            overflowed = self._overflowed
            self._buffer.clear()
            self._context = None
        assert target is not None and context is not None
        duration = len(pcm) / (self.SAMPLE_RATE * self.SAMPLE_WIDTH)
        if overflowed:
            self._set_status("too_long", "PTT input exceeded 20 seconds.")
            return
        if duration < self.minimum_seconds:
            self._set_status("too_short", "PTT input was too short.")
            return

        frozen = self._context_collector.freeze_end(
            context,
            speech_ended_at=ended_at,
            current_slide_id=target.slide_id,
        )
        self._set_status("transcribing", None)
        try:
            transcript = await asyncio.to_thread(self._transcribe_pcm, pcm)
        except Exception:
            self._set_status("stt_failed", "Speech transcription failed.")
            return
        text = " ".join(transcript.text.strip().split())
        if not text:
            self._set_status("empty_transcript", "No speech was recognized.")
            return
        normalized_transcript = Transcript(
            text=text,
            language=transcript.language,
            confidence=transcript.confidence,
        )
        async with self._lock:
            if generation != self._generation:
                return
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.int16, copy=True)
        turn = SpeechTurn(
            samples=samples,
            sample_rate=self.SAMPLE_RATE,
            started_at=started_at,
            ended_at=ended_at,
            finalization_reason="push_to_talk_release",
        )
        self._proposal_runner.run(
            AudioTurnResult(
                turn=turn,
                transcript=normalized_transcript,
                status="completed",
            ),
            frozen,
        )
        self._set_status("published", None)

    async def cancel(self, reason: str) -> None:
        async with self._lock:
            self._generation += 1
            self._recording = False
            self._session_id = None
            self._target = None
            self._context = None
            self._buffer.clear()
            self._overflowed = False
            self._set_status("cancelled", str(reason))

    def snapshot(self) -> dict[str, object]:
        return {
            "recording": self._recording,
            "session_id": self._session_id,
            "status": self._last_status,
            "message": self._last_message,
        }

    def _transcribe_pcm(self, pcm: bytes) -> Transcript:
        with NamedTemporaryFile(prefix="attentiveslides-ptt-", suffix=".wav", delete=False) as handle:
            path = Path(handle.name)
        try:
            with wave.open(str(path), "wb") as output:
                output.setnchannels(self.CHANNELS)
                output.setsampwidth(self.SAMPLE_WIDTH)
                output.setframerate(self.SAMPLE_RATE)
                output.writeframes(pcm)
            return self._transcribe(str(path))
        finally:
            path.unlink(missing_ok=True)

    def _set_status(self, status: str, message: str | None) -> None:
        self._last_status = status
        self._last_message = message
        self._on_status(status, message)
