from __future__ import annotations

from collections.abc import Callable, Sequence
import json
import os
from pathlib import Path
from threading import RLock
import time
import uuid

from modules.attention.gaze_heatmap import (
    GazeHeatmapAccumulator,
    GazeReviewSession,
    normalized_slide_point,
)
from modules.common.schemas import AOI
from modules.media.browser_gaze_source import BrowserPointGazeSample


class GazeReviewStore:
    def __init__(
        self,
        path: str | Path,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self.path = Path(path)
        self._monotonic_clock = monotonic_clock
        self._wall_clock = wall_clock
        self._id_factory = id_factory
        self._lock = RLock()
        self._registered: dict[tuple[str, int], tuple[AOI, ...]] = {}
        self._active: GazeHeatmapAccumulator | None = None
        self._latest: GazeReviewSession | None = None
        self._load_error: str | None = None
        self._load_latest()
        self._armed = self._latest is None and self._load_error is None

    def register_slide(self, deck_id: str, slide_id: int, aois: Sequence[AOI]) -> None:
        with self._lock:
            key = (str(deck_id), int(slide_id))
            self._registered[key] = tuple(aois)
            if self._active is not None:
                self._active.register_slide(key[0], key[1], aois)

    def accept(self, sample: BrowserPointGazeSample) -> bool:
        with self._lock:
            if not self._armed:
                return False
            geometry = sample.geometry.geometry if sample.geometry is not None else None
            usable = normalized_slide_point(sample) is not None
            if (
                self._active is not None
                and geometry is not None
                and geometry.deck_id != self._active.deck_id
            ):
                self._active.pause()
                return False
            if self._active is None:
                if not usable or geometry is None:
                    return False
                self._active = GazeHeatmapAccumulator(
                    session_id=self._id_factory(),
                    deck_id=geometry.deck_id,
                    started_at_epoch=self._wall_clock(),
                )
                for (deck_id, slide_id), aois in self._registered.items():
                    self._active.register_slide(deck_id, slide_id, aois)
            return self._active.accept(sample)

    def pause(self) -> None:
        with self._lock:
            if self._active is not None:
                self._active.pause()

    def finish(self, *, deck_id: str) -> GazeReviewSession:
        with self._lock:
            if not self._armed and self._active is None:
                raise RuntimeError(
                    "Start a new study before replacing the completed review."
                )
            if self._active is not None and self._active.deck_id != str(deck_id):
                raise RuntimeError(
                    "The active gaze study belongs to another deck. "
                    "Start a new study before collecting this deck."
                )
            now_epoch = self._wall_clock()
            if self._active is None:
                accumulator = GazeHeatmapAccumulator(
                    session_id=self._id_factory(),
                    deck_id=str(deck_id),
                    started_at_epoch=now_epoch,
                )
            else:
                accumulator = self._active
            review = accumulator.finish(
                ended_received_at=self._monotonic_clock(),
                ended_at_epoch=now_epoch,
            )
            self._write(review)
            self._latest = review
            self._active = None
            self._armed = False
            self._load_error = None
            return review

    def latest(self) -> GazeReviewSession | None:
        with self._lock:
            return self._latest

    def has_active(self) -> bool:
        with self._lock:
            return self._active is not None

    def active_deck_id(self) -> str | None:
        with self._lock:
            return self._active.deck_id if self._active is not None else None

    def is_armed(self) -> bool:
        with self._lock:
            return self._armed

    def load_error(self) -> str | None:
        with self._lock:
            return self._load_error

    def start_new(self) -> None:
        with self._lock:
            self._delete_latest()
            self._active = None
            self._latest = None
            self._load_error = None
            self._armed = True

    def clear(self) -> None:
        self.start_new()

    def _write(self, review: GazeReviewSession) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(review.to_json() + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    def _load_latest(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._latest = GazeReviewSession.from_dict(payload)
        except (
            OSError,
            TypeError,
            ValueError,
            KeyError,
            AttributeError,
            OverflowError,
            json.JSONDecodeError,
        ) as exc:
            self._load_error = f"{type(exc).__name__}: {exc}"

    def _delete_latest(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
