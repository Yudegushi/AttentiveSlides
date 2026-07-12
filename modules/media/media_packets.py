"""Immutable packet contracts produced by browser media callbacks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _readonly_copy(value: np.ndarray, dtype: np.dtype) -> np.ndarray:
    array = np.array(value, dtype=dtype, copy=True, order="C")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class VideoPacket:
    """One BGR video frame with a source-relative timestamp in seconds."""

    frame: np.ndarray
    timestamp: float
    pixel_format: str = "bgr24"
    timestamp_clock: str = "media_time_seconds"

    def __post_init__(self) -> None:
        frame = _readonly_copy(self.frame, np.uint8)
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("video frame must have shape (height, width, 3)")
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "timestamp", float(self.timestamp))


@dataclass(frozen=True)
class AudioPacket:
    """Interleaved signed-16 PCM shaped ``(samples, channels)``."""

    samples: np.ndarray
    timestamp: float
    sample_rate: int
    channels: int
    sample_format: str = "s16"
    layout: str = "interleaved"
    timestamp_clock: str = "media_time_seconds"

    def __post_init__(self) -> None:
        samples = _readonly_copy(self.samples, np.int16)
        if samples.ndim != 2:
            raise ValueError("audio samples must have shape (samples, channels)")
        if self.channels <= 0 or samples.shape[1] != self.channels:
            raise ValueError("audio channel metadata does not match sample shape")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(self, "sample_rate", int(self.sample_rate))
        object.__setattr__(self, "channels", int(self.channels))
