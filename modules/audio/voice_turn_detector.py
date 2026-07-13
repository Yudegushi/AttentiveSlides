"""Fixed-frame VAD state machine that emits bounded speech turns."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math

import numpy as np

from modules.audio.audio_ring_buffer import AudioRingBuffer
from modules.audio.streaming_vad import VadBackend


@dataclass(frozen=True)
class VoiceTurnDetectorConfig:
    sample_rate: int = 16_000
    frame_ms: int = 30
    pre_roll_ms: int = 300
    speech_start_window_ms: int = 150
    speech_end_silence_ms: int = 800
    minimum_utterance_ms: int = 300
    maximum_utterance_sec: float = 20.0

    def __post_init__(self) -> None:
        if self.sample_rate <= 0 or self.frame_ms <= 0:
            raise ValueError("sample_rate and frame_ms must be positive")
        if self.pre_roll_ms < 0 or self.speech_start_window_ms <= 0:
            raise ValueError("speech windows must be positive")
        if self.speech_end_silence_ms <= 0 or self.minimum_utterance_ms <= 0:
            raise ValueError("speech end and minimum duration must be positive")
        if self.maximum_utterance_sec <= 0:
            raise ValueError("maximum_utterance_sec must be positive")
        if self.sample_rate * self.frame_ms % 1_000:
            raise ValueError("sample_rate and frame_ms must form whole PCM frames")


@dataclass(frozen=True)
class SpeechTurn:
    samples: np.ndarray
    sample_rate: int
    started_at: float
    ended_at: float
    finalization_reason: str
    is_degraded: bool = False
    degradation_reason: str | None = None

    def __post_init__(self) -> None:
        samples = np.array(self.samples, dtype=np.int16, copy=True, order="C").reshape(-1)
        samples.setflags(write=False)
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "sample_rate", int(self.sample_rate))
        object.__setattr__(self, "started_at", float(self.started_at))
        object.__setattr__(self, "ended_at", float(self.ended_at))


class VoiceTurnDetector:
    """Consume mono PCM in arbitrary chunks and produce one turn at a time."""

    def __init__(self, vad: VadBackend, *, config: VoiceTurnDetectorConfig | None = None) -> None:
        self.vad = vad
        self.config = config or VoiceTurnDetectorConfig()
        self.frame_samples = self.config.sample_rate * self.config.frame_ms // 1_000
        self._frame_seconds = self.config.frame_ms / 1_000
        self._start_frames = math.ceil(self.config.speech_start_window_ms / self.config.frame_ms)
        self._end_silence_frames = math.ceil(
            self.config.speech_end_silence_ms / self.config.frame_ms
        )
        self._pre_roll_samples = max(
            self.frame_samples,
            math.ceil(self.config.pre_roll_ms * self.config.sample_rate / 1_000),
        )
        self._ring = AudioRingBuffer(max_samples=self._pre_roll_samples)
        self._pending = np.empty(0, dtype=np.int16)
        self._pending_start_at: float | None = None
        self._speech_history: deque[bool] = deque(maxlen=self._start_frames)
        self._active_chunks: list[np.ndarray] | None = None
        self._started_at: float | None = None
        self._last_speech_end_at: float | None = None
        self._silence_frames = 0
        self._degradation_reason: str | None = None
        self._started_events: deque[float] = deque()
        self._discarded_events: deque[tuple[float, str]] = deque()
        self.dropped_utterance_count = 0

    @property
    def has_active_turn(self) -> bool:
        return self._active_chunks is not None

    def drain_started_turns(self) -> list[float]:
        events = list(self._started_events)
        self._started_events.clear()
        return events

    def drain_discarded_turns(self) -> list[tuple[float, str]]:
        events = list(self._discarded_events)
        self._discarded_events.clear()
        return events

    def feed(self, samples: np.ndarray, *, start_at: float) -> list[SpeechTurn]:
        incoming = np.asarray(samples, dtype=np.int16).reshape(-1)
        if incoming.size == 0:
            return []
        if self._pending.size == 0:
            self._pending_start_at = float(start_at)
        self._pending = np.concatenate((self._pending, incoming))
        turns: list[SpeechTurn] = []

        while self._pending.size >= self.frame_samples:
            assert self._pending_start_at is not None
            frame_start = self._pending_start_at
            frame = self._pending[: self.frame_samples]
            self._pending = self._pending[self.frame_samples :]
            self._pending_start_at = frame_start + self._frame_seconds
            turn = self._consume_frame(frame, frame_start)
            if turn is not None:
                turns.append(turn)

        return turns

    def mark_degraded(self, reason: str) -> None:
        if self.has_active_turn:
            self._degradation_reason = str(reason)

    def cancel(self) -> None:
        self._pending = np.empty(0, dtype=np.int16)
        self._pending_start_at = None
        self._reset_turn_state()

    def _consume_frame(self, frame: np.ndarray, frame_start: float) -> SpeechTurn | None:
        is_speech = self.vad.is_speech(frame, self.config.sample_rate)
        frame_end = frame_start + self._frame_seconds

        if not self.has_active_turn:
            self._ring.append(frame)
            self._speech_history.append(is_speech)
            if len(self._speech_history) == self._start_frames and all(self._speech_history):
                self._active_chunks = [self._ring.samples()]
                self._started_at = frame_start - (self._start_frames - 1) * self._frame_seconds
                self._last_speech_end_at = frame_end
                self._silence_frames = 0
                self._started_events.append(self._started_at)
            return None

        assert self._active_chunks is not None
        assert self._started_at is not None
        self._active_chunks.append(np.array(frame, dtype=np.int16, copy=True))
        if is_speech:
            self._last_speech_end_at = frame_end
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        if frame_end - self._started_at + 1e-9 >= self.config.maximum_utterance_sec:
            return self._finalize(frame_end, "maximum_duration")
        if self._silence_frames >= self._end_silence_frames:
            assert self._last_speech_end_at is not None
            return self._finalize(self._last_speech_end_at, "silence")
        return None

    def _finalize(self, ended_at: float, reason: str) -> SpeechTurn | None:
        assert self._active_chunks is not None
        assert self._started_at is not None
        started_at = self._started_at
        samples = np.concatenate(self._active_chunks)
        speech_duration = max(0.0, ended_at - started_at)
        degraded_reason = self._degradation_reason
        self._reset_turn_state()
        if speech_duration + 1e-9 < self.config.minimum_utterance_ms / 1_000:
            self.dropped_utterance_count += 1
            self._discarded_events.append((started_at, "short_utterance"))
            return None
        return SpeechTurn(
            samples=samples,
            sample_rate=self.config.sample_rate,
            started_at=started_at,
            ended_at=ended_at,
            finalization_reason=reason,
            is_degraded=degraded_reason is not None,
            degradation_reason=degraded_reason,
        )

    def _reset_turn_state(self) -> None:
        self._ring.clear()
        self._speech_history.clear()
        self._active_chunks = None
        self._started_at = None
        self._last_speech_end_at = None
        self._silence_frames = 0
        self._degradation_reason = None
