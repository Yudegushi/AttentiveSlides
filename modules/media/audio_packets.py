"""Immutable browser audio packet contracts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AudioPacket:
    """Interleaved signed-16 PCM shaped as (samples, channels)."""

    samples: np.ndarray
    timestamp: float
    sample_rate: int
    channels: int
    sample_format: str = "s16"
    timestamp_clock: str = "browser_performance_seconds"

    def __post_init__(
        self,
    ) -> None:
        samples = np.array(
            self.samples,
            dtype=np.int16,
            copy=True,
            order="C",
        )

        if samples.ndim != 2:
            raise ValueError(
                "audio samples must have shape "
                "(samples, channels)"
            )

        if (
            self.channels <= 0
            or samples.shape[1] != self.channels
        ):
            raise ValueError(
                "audio channel metadata does not "
                "match sample shape"
            )

        if self.sample_rate <= 0:
            raise ValueError(
                "sample_rate must be positive"
            )

        samples.setflags(
            write=False
        )

        object.__setattr__(
            self,
            "samples",
            samples,
        )

        object.__setattr__(
            self,
            "timestamp",
            float(self.timestamp),
        )

        object.__setattr__(
            self,
            "sample_rate",
            int(self.sample_rate),
        )

        object.__setattr__(
            self,
            "channels",
            int(self.channels),
        )
