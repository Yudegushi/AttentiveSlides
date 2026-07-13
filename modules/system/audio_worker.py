"""Background audio turn worker for BrowserMediaSource packets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
from tempfile import NamedTemporaryFile
from threading import Event, RLock, Thread, current_thread
import time
from typing import Callable
import wave

import numpy as np

from modules.audio.voice_turn_detector import SpeechTurn, VoiceTurnDetector
from modules.common.schemas import Transcript
from modules.interaction.speech_to_text import transcribe_audio
from modules.media.browser_media_source import BrowserMediaSource
from modules.media.media_packets import AudioPacket


@dataclass(frozen=True)
class AudioWorkerConfig:
    poll_interval_seconds: float = 0.02
    result_queue_size: int = 4

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.result_queue_size <= 0:
            raise ValueError("result_queue_size must be positive")


@dataclass(frozen=True)
class AudioTurnResult:
    turn: SpeechTurn
    transcript: Transcript | None
    status: str
    error: str | None = None


class _AudioClockNormalizer:
    """Map one source clock onto the worker's server-monotonic clock."""

    def __init__(self) -> None:
        self._source_clock: str | None = None
        self._source_origin: float | None = None
        self._monotonic_origin: float | None = None
        self._last_source_timestamp: float | None = None
        self._last_end_at: float | None = None

    def normalize_start(self, packet: AudioPacket, *, received_at: float) -> float:
        source_timestamp = float(packet.timestamp)
        if (
            self._source_clock != packet.timestamp_clock
            or self._source_origin is None
            or self._last_source_timestamp is None
            or source_timestamp < self._last_source_timestamp
        ):
            self._source_clock = packet.timestamp_clock
            self._source_origin = source_timestamp
            self._monotonic_origin = max(
                float(received_at),
                self._last_end_at if self._last_end_at is not None else float(received_at),
            )
        assert self._source_origin is not None
        assert self._monotonic_origin is not None
        start_at = self._monotonic_origin + (source_timestamp - self._source_origin)
        self._last_source_timestamp = source_timestamp
        return start_at

    def record_end(self, start_at: float, samples: int, sample_rate: int) -> None:
        self._last_end_at = float(start_at) + samples / sample_rate


class AudioWorker:
    """Drain bounded browser audio outside callbacks and emit recoverable results."""

    def __init__(
        self,
        *,
        media_source: BrowserMediaSource,
        detector: VoiceTurnDetector,
        transcribe: Callable[[str], Transcript] = transcribe_audio,
        clock: Callable[[], float] = time.monotonic,
        config: AudioWorkerConfig | None = None,
    ) -> None:
        self.media_source = media_source
        self.detector = detector
        self.transcribe = transcribe
        self._clock = clock
        self.config = config or AudioWorkerConfig()
        self._normalizer = _AudioClockNormalizer()
        self._results: queue.Queue[AudioTurnResult] = queue.Queue(
            maxsize=self.config.result_queue_size
        )
        self._last_audio_overruns = self.media_source.audio_queue.overrun_count
        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._running_requested = False
        self.last_error: Exception | None = None
        self.start_count = 0
        self.stop_count = 0
        self.result_drops = 0

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self._running_requested:
                return
            self._stop_event.clear()
            self.last_error = None
            self._running_requested = True
            self.start_count += 1
            self._thread = Thread(target=self._run, name="attentive-audio", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            was_running = self._running_requested
            self._running_requested = False
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=2.0)
        self.detector.cancel()
        self.media_source.audio_queue.clear()
        if was_running:
            self.stop_count += 1

    def get_result_nowait(self) -> AudioTurnResult:
        return self._results.get_nowait()

    def process_available_audio(self) -> list[AudioTurnResult]:
        self._mark_overrun()
        results: list[AudioTurnResult] = []
        while True:
            try:
                packet = self.media_source.audio_queue.get_nowait()
            except queue.Empty:
                break
            received_at = float(self._clock())
            pcm = self._normalize_packet(packet)
            start_at = self._normalizer.normalize_start(packet, received_at=received_at)
            self._normalizer.record_end(
                start_at,
                samples=pcm.size,
                sample_rate=self.detector.config.sample_rate,
            )
            for turn in self.detector.feed(pcm, start_at=start_at):
                result = self._result_for_turn(turn)
                self._publish(result)
                results.append(result)
        return results

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self.process_available_audio()
                self._stop_event.wait(self.config.poll_interval_seconds)
        except Exception as exc:
            with self._lock:
                self.last_error = exc
                self._running_requested = False
            self._stop_event.set()

    def _mark_overrun(self) -> None:
        overruns = self.media_source.audio_queue.overrun_count
        if overruns > self._last_audio_overruns:
            self.detector.mark_degraded("audio_overrun")
        self._last_audio_overruns = overruns

    def _result_for_turn(self, turn: SpeechTurn) -> AudioTurnResult:
        if turn.is_degraded:
            return AudioTurnResult(
                turn=turn,
                transcript=None,
                status="invalid",
                error=turn.degradation_reason or "audio_degraded",
            )
        path = self._write_temporary_wav(turn)
        try:
            transcript = self.transcribe(str(path))
        except Exception as exc:
            return AudioTurnResult(
                turn=turn,
                transcript=None,
                status="stt_error",
                error=str(exc),
            )
        finally:
            path.unlink(missing_ok=True)
        return AudioTurnResult(turn=turn, transcript=transcript, status="completed")

    def _write_temporary_wav(self, turn: SpeechTurn) -> Path:
        with NamedTemporaryFile(prefix="attentive-turn-", suffix=".wav", delete=False) as file:
            path = Path(file.name)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(turn.sample_rate)
            wav.writeframes(turn.samples.tobytes())
        return path

    def _publish(self, result: AudioTurnResult) -> None:
        try:
            self._results.put_nowait(result)
        except queue.Full:
            try:
                self._results.get_nowait()
            except queue.Empty:
                pass
            self._results.put_nowait(result)
            self.result_drops += 1

    def _normalize_packet(self, packet: AudioPacket) -> np.ndarray:
        source = np.asarray(packet.samples, dtype=np.int16)
        mono = np.rint(source.astype(np.float64).mean(axis=1)).astype(np.int16)
        target_rate = self.detector.config.sample_rate
        if packet.sample_rate == target_rate:
            return mono
        target_size = max(1, round(mono.size * target_rate / packet.sample_rate))
        positions = np.linspace(0, mono.size - 1, num=target_size)
        resampled = np.interp(positions, np.arange(mono.size), mono.astype(np.float64))
        return np.rint(resampled).astype(np.int16)
