"""Bounded browser microphone source."""

from __future__ import annotations

from dataclasses import dataclass
import queue
from threading import RLock
from typing import Callable
import time

import numpy as np

from modules.media.audio_packets import (
    AudioPacket,
)


class BoundedAudioQueue:
    """Drop the oldest packet instead of blocking browser callbacks."""

    def __init__(
        self,
        *,
        max_items: int = 100,
    ) -> None:
        if max_items <= 0:
            raise ValueError(
                "max_items must be positive"
            )

        self._queue: queue.Queue[
            AudioPacket
        ] = queue.Queue(
            maxsize=max_items
        )

        self._lock = RLock()
        self._active = False

        self.accepted_count = 0
        self.dropped_count = 0
        self.overrun_count = 0
        self.last_timestamp: float | None = None

    def activate(
        self,
        *,
        reset_counters: bool = False,
    ) -> None:
        with self._lock:
            self._active = True

            if reset_counters:
                self.accepted_count = 0
                self.dropped_count = 0
                self.overrun_count = 0
                self.last_timestamp = None

            self.clear()

    def close(
        self,
    ) -> None:
        with self._lock:
            self._active = False
            self.clear()

    def push(
        self,
        packet: AudioPacket,
    ) -> bool:
        with self._lock:
            if not self._active:
                return False

            if self._queue.full():
                try:
                    self._queue.get_nowait()
                    self.dropped_count += 1
                    self.overrun_count += 1

                except queue.Empty:
                    pass

            self._queue.put_nowait(
                packet
            )

            self.accepted_count += 1
            self.last_timestamp = (
                packet.timestamp
            )

            return True

    def get_nowait(
        self,
    ) -> AudioPacket:
        return self._queue.get_nowait()

    def qsize(
        self,
    ) -> int:
        return self._queue.qsize()

    def clear(
        self,
    ) -> None:
        while True:
            try:
                self._queue.get_nowait()

            except queue.Empty:
                break


@dataclass(frozen=True)
class BrowserAudioStats:
    chunks_per_second: float
    queue_depth: int
    accepted_chunks: int
    dropped_chunks: int
    overruns: int
    last_audio_timestamp: float | None
    is_running: bool
    cleanup_state: str


class BrowserAudioSource:
    """Convert browser PCM into bounded immutable packets."""

    def __init__(
        self,
        *,
        queue_size: int = 100,
        clock: Callable[
            [],
            float,
        ] = time.monotonic,
    ) -> None:
        self.audio_queue = (
            BoundedAudioQueue(
                max_items=queue_size
            )
        )

        self._clock = clock
        self._lock = RLock()

        self._running = False
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._cleanup_state = "idle"

    @property
    def is_running(
        self,
    ) -> bool:
        with self._lock:
            return self._running

    def start(
        self,
    ) -> None:
        with self._lock:
            if self._running:
                return

            self.audio_queue.activate(
                reset_counters=True
            )

            self._running = True
            self._started_at = (
                self._clock()
            )
            self._stopped_at = None
            self._cleanup_state = (
                "running"
            )

    def stop(
        self,
        *,
        reason: str = "requested",
    ) -> None:
        with self._lock:
            self._running = False
            self._stopped_at = (
                self._clock()
            )

            self.audio_queue.close()

            self._cleanup_state = (
                f"stopped: {reason}"
            )

    def accept_audio_samples(
        self,
        samples: np.ndarray,
        *,
        timestamp: float,
        sample_rate: int,
        channels: int,
    ) -> bool:
        packet = AudioPacket(
            samples=samples,
            timestamp=timestamp,
            sample_rate=sample_rate,
            channels=channels,
        )

        return self.audio_queue.push(
            packet
        )

    def stats(
        self,
    ) -> BrowserAudioStats:
        with self._lock:
            end = (
                self._clock()
                if self._running
                else self._stopped_at
            )

            if (
                self._started_at is None
                or end is None
            ):
                elapsed = 0.0

            else:
                elapsed = max(
                    end - self._started_at,
                    1e-9,
                )

            return BrowserAudioStats(
                chunks_per_second=(
                    self.audio_queue
                    .accepted_count
                    / elapsed
                    if elapsed
                    else 0.0
                ),
                queue_depth=(
                    self.audio_queue.qsize()
                ),
                accepted_chunks=(
                    self.audio_queue
                    .accepted_count
                ),
                dropped_chunks=(
                    self.audio_queue
                    .dropped_count
                ),
                overruns=(
                    self.audio_queue
                    .overrun_count
                ),
                last_audio_timestamp=(
                    self.audio_queue
                    .last_timestamp
                ),
                is_running=self._running,
                cleanup_state=(
                    self._cleanup_state
                ),
            )
