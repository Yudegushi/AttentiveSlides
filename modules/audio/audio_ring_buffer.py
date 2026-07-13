"""Bounded in-memory PCM storage for speech pre-roll."""

from __future__ import annotations

from collections import deque

import numpy as np


class AudioRingBuffer:
    """Retain only the newest signed-16 mono samples."""

    def __init__(self, *, max_samples: int) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self.max_samples = int(max_samples)
        self._chunks: deque[np.ndarray] = deque()
        self._sample_count = 0

    @property
    def sample_count(self) -> int:
        return self._sample_count

    def append(self, samples: np.ndarray) -> None:
        chunk = np.asarray(samples, dtype=np.int16).reshape(-1).copy()
        if chunk.size == 0:
            return
        if chunk.size >= self.max_samples:
            self._chunks.clear()
            self._chunks.append(chunk[-self.max_samples :])
            self._sample_count = self.max_samples
            return

        self._chunks.append(chunk)
        self._sample_count += chunk.size
        while self._sample_count > self.max_samples:
            overflow = self._sample_count - self.max_samples
            oldest = self._chunks.popleft()
            if oldest.size <= overflow:
                self._sample_count -= oldest.size
                continue
            self._chunks.appendleft(oldest[overflow:])
            self._sample_count -= overflow

    def samples(self) -> np.ndarray:
        if not self._chunks:
            return np.empty(0, dtype=np.int16)
        return np.concatenate(tuple(self._chunks)).astype(np.int16, copy=False)

    def clear(self) -> None:
        self._chunks.clear()
        self._sample_count = 0
