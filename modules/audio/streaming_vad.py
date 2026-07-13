"""Injectable voice-activity backends for streaming PCM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class VadBackend(Protocol):
    """Classify one mono signed-16 PCM frame."""

    def is_speech(self, pcm_frame: np.ndarray, sample_rate: int) -> bool:
        ...


@dataclass(frozen=True)
class EnergyVadBackend:
    """Deterministic no-download fallback used when WebRTC VAD is unavailable."""

    speech_threshold: int = 450

    def __post_init__(self) -> None:
        if self.speech_threshold <= 0:
            raise ValueError("speech_threshold must be positive")

    def is_speech(self, pcm_frame: np.ndarray, sample_rate: int) -> bool:
        del sample_rate
        samples = np.asarray(pcm_frame, dtype=np.int16).reshape(-1)
        if samples.size == 0:
            return False
        return bool(np.max(np.abs(samples.astype(np.int32))) >= self.speech_threshold)


class WebRtcVadBackend:
    """Optional adapter around the WebRTC-VAD-compatible package."""

    def __init__(self, *, aggressiveness: int = 2) -> None:
        if aggressiveness not in {0, 1, 2, 3}:
            raise ValueError("aggressiveness must be in [0, 3]")
        try:
            import webrtcvad
        except ModuleNotFoundError as exc:
            raise RuntimeError("Install webrtcvad to use WebRtcVadBackend.") from exc
        self._vad = webrtcvad.Vad(aggressiveness)

    def is_speech(self, pcm_frame: np.ndarray, sample_rate: int) -> bool:
        samples = np.asarray(pcm_frame, dtype=np.int16).reshape(-1)
        return bool(self._vad.is_speech(samples.tobytes(), int(sample_rate)))


def default_vad_backend() -> VadBackend:
    """Prefer the optional WebRTC backend without making it a test dependency."""

    try:
        return WebRtcVadBackend()
    except RuntimeError:
        return EnergyVadBackend()
