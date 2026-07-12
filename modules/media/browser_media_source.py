"""Browser media source with bounded queues and explicit lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import math
from threading import RLock
import time
from typing import Any, Callable, Tuple

import numpy as np

from .media_packets import AudioPacket, VideoPacket
from .queue_policy import BoundedMediaQueue


@dataclass(frozen=True)
class BrowserMediaStats:
    video_fps: float
    audio_chunks_per_second: float
    last_video_timestamp: float | None
    last_audio_timestamp: float | None
    video_queue_depth: int
    audio_queue_depth: int
    video_drops: int
    audio_drops: int
    audio_overruns: int
    is_running: bool
    cleanup_state: str


class BrowserMediaSource:
    """Convert browser frames into immutable packets and bounded queues."""

    def __init__(
        self,
        *,
        video_queue_size: int = 3,
        audio_queue_size: int = 100,
        audio_queue_max_bytes: int = 4 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.video_queue: BoundedMediaQueue[VideoPacket] = BoundedMediaQueue(
            video_queue_size,
            item_size=lambda packet: packet.frame.nbytes,
        )
        self.audio_queue: BoundedMediaQueue[AudioPacket] = BoundedMediaQueue(
            audio_queue_size,
            max_bytes=audio_queue_max_bytes,
            item_size=lambda packet: packet.samples.nbytes,
        )
        self.video_queue.close()
        self.audio_queue.close()
        self._clock = clock
        self._lock = RLock()
        self._running = False
        self._cleanup_state = "idle"
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self.start_count = 0
        self.stop_count = 0

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def cleanup_state(self) -> str:
        with self._lock:
            return self._cleanup_state

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self.video_queue.activate(reset_counters=True)
            self.audio_queue.activate(reset_counters=True)
            self._started_at = self._clock()
            self._stopped_at = None
            self._running = True
            self._cleanup_state = "running"
            self.start_count += 1

    def stop(self, reason: str = "requested") -> None:
        with self._lock:
            was_running = self._running
            self._running = False
            self._stopped_at = self._clock()
            self.video_queue.close()
            self.audio_queue.close()
            self._cleanup_state = f"stopped: {reason}"
            if was_running:
                self.stop_count += 1

    def handle_disconnect(self) -> None:
        self.stop(reason="browser disconnected")

    def handle_component_error(self, detail: str) -> None:
        self.stop(reason=f"component error: {detail}")

    def accept_video_frame(
        self,
        video_frame: np.ndarray,
        *,
        timestamp: float,
        timestamp_clock: str,
    ) -> bool:
        """Push one already-decoded browser BGR frame without blocking."""

        packet = VideoPacket(
            frame=video_frame,
            timestamp=timestamp,
            timestamp_clock=timestamp_clock,
        )
        return self.video_queue.push(packet)

    def accept_audio_samples(
        self,
        samples: np.ndarray,
        *,
        timestamp: float,
        sample_rate: int,
        channels: int,
        timestamp_clock: str,
    ) -> bool:
        """Push one already-decoded browser PCM chunk without blocking."""

        packet = AudioPacket(
            samples=samples,
            timestamp=timestamp,
            sample_rate=sample_rate,
            channels=channels,
            timestamp_clock=timestamp_clock,
        )
        return self.audio_queue.push(packet)

    def video_frame_callback(self, frame: Any) -> Any:
        timestamp, timestamp_clock = self._timestamp(frame)
        self.accept_video_frame(
            frame.to_ndarray(format="bgr24"),
            timestamp=timestamp,
            timestamp_clock=timestamp_clock,
        )
        return frame

    def audio_frame_callback(self, frame: Any) -> Any:
        timestamp, timestamp_clock = self._timestamp(frame)
        samples, sample_rate, channels = self._audio_to_s16_interleaved(frame)
        self.accept_audio_samples(
            samples=samples,
            timestamp=timestamp,
            sample_rate=sample_rate,
            channels=channels,
            timestamp_clock=timestamp_clock,
        )
        return frame

    def stats(self) -> BrowserMediaStats:
        with self._lock:
            end = self._clock() if self._running else self._stopped_at
            if self._started_at is None or end is None:
                elapsed = 0.0
            else:
                elapsed = max(end - self._started_at, 1e-9)
            return BrowserMediaStats(
                video_fps=self.video_queue.accepted_count / elapsed if elapsed else 0.0,
                audio_chunks_per_second=(
                    self.audio_queue.accepted_count / elapsed if elapsed else 0.0
                ),
                last_video_timestamp=self.video_queue.last_timestamp,
                last_audio_timestamp=self.audio_queue.last_timestamp,
                video_queue_depth=self.video_queue.qsize(),
                audio_queue_depth=self.audio_queue.qsize(),
                video_drops=self.video_queue.dropped_count,
                audio_drops=self.audio_queue.dropped_count,
                audio_overruns=self.audio_queue.overrun_count,
                is_running=self._running,
                cleanup_state=self._cleanup_state,
            )

    def _timestamp(self, frame: Any) -> Tuple[float, str]:
        timestamp = getattr(frame, "time", None)
        if timestamp is not None:
            timestamp = float(timestamp)
            if math.isfinite(timestamp):
                return timestamp, "media_time_seconds"
        return float(self._clock()), "monotonic_seconds"

    @staticmethod
    def _audio_to_s16_interleaved(frame: Any) -> Tuple[np.ndarray, int, int]:
        sample_rate = int(frame.sample_rate)
        layout = getattr(frame, "layout", None)
        channel_names = getattr(layout, "channels", ())
        channels = len(channel_names)
        converted = frame
        if hasattr(frame, "reformat"):
            converted = frame.reformat(
                format="s16",
                layout=getattr(layout, "name", None),
                rate=sample_rate,
            )
        raw = np.asarray(converted.to_ndarray())
        format_info = getattr(converted, "format", getattr(frame, "format", None))
        is_planar = bool(getattr(format_info, "is_planar", False))
        if channels == 0:
            channels = raw.shape[0] if raw.ndim == 2 else 1

        if np.issubdtype(raw.dtype, np.floating):
            raw = (np.clip(raw, -1.0, 1.0) * 32767.0).astype(np.int16)
        else:
            raw = raw.astype(np.int16, copy=False)

        if raw.ndim == 1:
            samples = raw.reshape(-1, channels)
        elif raw.ndim == 2 and is_planar and raw.shape[0] == channels:
            samples = raw.T
        elif raw.ndim == 2 and raw.shape[1] == channels:
            samples = raw
        elif raw.ndim == 2 and raw.shape[0] == channels:
            samples = raw.T
        else:
            samples = raw.reshape(-1, channels)
        return np.ascontiguousarray(samples), sample_rate, channels

    def __del__(self) -> None:
        try:
            self.stop(reason="session released")
        except Exception:
            pass
