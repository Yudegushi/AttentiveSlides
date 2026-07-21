"""Streaming PCM conversion and optional transport diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
import wave

import av
import numpy as np


class Pcm16StreamResampler:
    """Convert one continuous mono signed-16 stream to 16 kHz with PyAV."""

    TARGET_RATE = 16_000

    def __init__(self) -> None:
        self._source_rate: int | None = None
        self._resampler: av.AudioResampler | None = None

    def convert(self, pcm: bytes, *, source_rate: int) -> bytes:
        if not pcm:
            return b""
        if len(pcm) % np.dtype("<i2").itemsize:
            raise ValueError("PCM must be aligned signed-16 mono audio")
        source_rate = int(source_rate)
        if source_rate <= 0:
            raise ValueError("source_rate must be positive")
        if self._source_rate not in {None, source_rate}:
            self.reset()
        self._source_rate = source_rate
        if source_rate == self.TARGET_RATE:
            return bytes(pcm)
        if self._resampler is None:
            self._resampler = av.AudioResampler(
                format="s16",
                layout="mono",
                rate=self.TARGET_RATE,
            )
        samples = np.frombuffer(pcm, dtype="<i2")
        frame = av.AudioFrame.from_ndarray(
            samples.reshape(1, -1),
            format="s16",
            layout="mono",
        )
        frame.sample_rate = source_rate
        return self._frames_to_bytes(self._resampler.resample(frame))

    def convert_array(self, samples: np.ndarray, *, source_rate: int) -> np.ndarray:
        mono = np.asarray(samples, dtype="<i2").reshape(-1)
        converted = self.convert(mono.tobytes(), source_rate=source_rate)
        return np.frombuffer(converted, dtype="<i2").astype(np.int16, copy=True)

    def flush(self) -> bytes:
        if self._resampler is None:
            self.reset()
            return b""
        output = self._frames_to_bytes(self._resampler.resample(None))
        self.reset()
        return output

    def reset(self) -> None:
        self._source_rate = None
        self._resampler = None

    @staticmethod
    def _frames_to_bytes(frames: list[av.AudioFrame]) -> bytes:
        chunks = [
            np.asarray(frame.to_ndarray(), dtype="<i2").reshape(-1).tobytes()
            for frame in frames
        ]
        return b"".join(chunks)


class PcmWaveDebugRecorder:
    """Append named PCM streams to WAV files when diagnostics are enabled."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._writers: dict[tuple[str, str, int], wave.Wave_write] = {}
        self._paths: dict[tuple[str, str, int], Path] = {}

    def write(
        self,
        session_id: str,
        stream_name: str,
        pcm: bytes,
        *,
        sample_rate: int,
    ) -> None:
        if not pcm:
            return
        key = (session_id, stream_name, int(sample_rate))
        with self._lock:
            writer = self._writers.get(key)
            if writer is None:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                session_digest = sha256(session_id.encode("utf-8")).hexdigest()[:12]
                path = self.output_dir / (
                    f"{timestamp}_{session_digest}_{stream_name}_{sample_rate}hz.wav"
                )
                writer = wave.open(str(path), "wb")
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(int(sample_rate))
                self._writers[key] = writer
                self._paths[key] = path
            writer.writeframes(pcm)

    def paths(self) -> tuple[Path, ...]:
        with self._lock:
            return tuple(self._paths.values())

    def close_session(self, session_id: str) -> None:
        with self._lock:
            keys = [key for key in self._writers if key[0] == session_id]
            for key in keys:
                self._writers.pop(key).close()

    def close(self) -> None:
        with self._lock:
            writers = tuple(self._writers.values())
            self._writers.clear()
            for writer in writers:
                writer.close()
