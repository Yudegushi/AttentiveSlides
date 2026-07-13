"""Thread-safe non-blocking bounded queue policy for live media."""

from __future__ import annotations

from collections import deque
import queue
from threading import Lock
from typing import Callable, Deque, Generic, Optional, Tuple, TypeVar


T = TypeVar("T")


class BoundedMediaQueue(Generic[T]):
    """Keep recent items while making every capacity overrun observable."""

    def __init__(
        self,
        max_items: int,
        *,
        max_bytes: Optional[int] = None,
        item_size: Optional[Callable[[T], int]] = None,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        if max_bytes is not None and max_bytes <= 0:
            raise ValueError("max_bytes must be positive when provided")
        self.max_items = int(max_items)
        self.max_bytes = int(max_bytes) if max_bytes is not None else None
        self._item_size = item_size or (lambda _item: 0)
        self._items: Deque[Tuple[T, int]] = deque()
        self._current_bytes = 0
        self._dropped_count = 0
        self._overrun_count = 0
        self._accepted_count = 0
        self._last_timestamp: float | None = None
        self._accepting = True
        self._lock = Lock()

    @property
    def current_bytes(self) -> int:
        with self._lock:
            return self._current_bytes

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped_count

    @property
    def overrun_count(self) -> int:
        with self._lock:
            return self._overrun_count

    @property
    def accepted_count(self) -> int:
        with self._lock:
            return self._accepted_count

    @property
    def last_timestamp(self) -> float | None:
        with self._lock:
            return self._last_timestamp

    def activate(self, *, reset_counters: bool = False) -> None:
        with self._lock:
            self._accepting = True
            self._items.clear()
            self._current_bytes = 0
            if reset_counters:
                self._dropped_count = 0
                self._overrun_count = 0
                self._accepted_count = 0
                self._last_timestamp = None

    def close(self) -> None:
        with self._lock:
            self._accepting = False
            self._items.clear()
            self._current_bytes = 0

    def push(self, item: T) -> bool:
        """Push without blocking, evicting oldest entries when necessary."""

        size = max(0, int(self._item_size(item)))
        with self._lock:
            if not self._accepting:
                return False
            if self.max_bytes is not None and size > self.max_bytes:
                self._record_drop()
                return False

            while self._items and (
                len(self._items) >= self.max_items
                or (
                    self.max_bytes is not None
                    and self._current_bytes + size > self.max_bytes
                )
            ):
                _old_item, old_size = self._items.popleft()
                self._current_bytes -= old_size
                self._record_drop()

            self._items.append((item, size))
            self._current_bytes += size
            self._accepted_count += 1
            timestamp = getattr(item, "timestamp", None)
            self._last_timestamp = float(timestamp) if timestamp is not None else None
            return True

    def get_nowait(self) -> T:
        with self._lock:
            if not self._items:
                raise queue.Empty
            item, size = self._items.popleft()
            self._current_bytes -= size
            return item

    def qsize(self) -> int:
        with self._lock:
            return len(self._items)

    def empty(self) -> bool:
        return self.qsize() == 0

    def clear(self, *, reset_counters: bool = False) -> None:
        with self._lock:
            self._items.clear()
            self._current_bytes = 0
            if reset_counters:
                self._dropped_count = 0
                self._overrun_count = 0
                self._accepted_count = 0
                self._last_timestamp = None

    def _record_drop(self) -> None:
        self._dropped_count += 1
        self._overrun_count += 1
