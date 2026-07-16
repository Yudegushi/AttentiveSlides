"""Atomic multi-session Study Review store and learner-state aggregation."""

from __future__ import annotations

import copy
import json
import math
import os
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from modules.attention.gaze_heatmap import (
    GazeHeatmapAccumulator,
    GazeReviewSession,
    normalized_slide_point,
)
from modules.common.schemas import AOI
from modules.learner_state import EMOTION_LABELS, LearnerStateSnapshot
from modules.media.browser_gaze_source import BrowserPointGazeSample

from .contracts import (
    STUDY_REVIEW_SCHEMA_VERSION,
    LearnerStateReviewSummary,
    SlideLearnerStateSummary,
    StudyReviewSession,
    is_safe_session_id,
)


MAX_STATE_INTERVAL_SECONDS = 1.0


@dataclass
class _MutableSlideState:
    study_seconds: float = 0.0
    observed_seconds: float = 0.0
    emotion_observed_seconds: float = 0.0
    engagement_observed_seconds: float = 0.0
    fatigue_observed_seconds: float = 0.0
    interaction_count: int = 0
    engaged_weighted_sum: float = 0.0
    fatigue_weighted_sum: float = 0.0
    emotion_weighted_sums: list[float] = field(
        default_factory=lambda: [0.0] * len(EMOTION_LABELS)
    )
    distraction_alert_seconds: float = 0.0
    distraction_alert_count: int = 0
    fatigue_alert_seconds: float = 0.0
    fatigue_alert_count: int = 0
    distraction_active: bool = False
    fatigue_active: bool = False


@dataclass(frozen=True)
class _PreviousState:
    deck_id: str
    slide_id: int
    snapshot: LearnerStateSnapshot
    received_at: float


class LearnerStateReviewAccumulator:
    """Aggregate only time-weighted derived values; never retain frame histories."""

    def __init__(self, *, deck_id: str) -> None:
        self.deck_id = str(deck_id)
        self._slides: dict[int, _MutableSlideState] = {}
        self._interaction_ids: set[str] = set()
        self._current_context: tuple[str, int] | None = None
        self._context_started_at: float | None = None
        self._previous: _PreviousState | None = None

    def set_context(self, deck_id: str, slide_id: int, now: float) -> None:
        context = (str(deck_id), int(slide_id))
        if context == self._current_context:
            return
        self._close_study_time(now)
        self._close_observation(now)
        self._current_context = context
        self._context_started_at = now if context[0] == self.deck_id else None
        self._slides.setdefault(context[1], _MutableSlideState())

    def activate_context(
        self, context: tuple[str, int] | None, now: float
    ) -> None:
        if context is None or context[0] != self.deck_id:
            return
        self._current_context = context
        self._context_started_at = now
        self._slides.setdefault(context[1], _MutableSlideState())

    def accept(
        self,
        deck_id: str,
        slide_id: int,
        snapshot: LearnerStateSnapshot,
        received_at: float,
    ) -> None:
        self._close_observation(received_at)
        state = self._slides.setdefault(int(slide_id), _MutableSlideState())
        engagement_active = (
            snapshot.engagement.status == "ready"
            and snapshot.engagement.alert_active
        )
        fatigue_active = (
            snapshot.fatigue.status == "ready" and snapshot.fatigue.alert_active
        )
        if engagement_active and not state.distraction_active:
            state.distraction_alert_count += 1
        if fatigue_active and not state.fatigue_active:
            state.fatigue_alert_count += 1
        state.distraction_active = engagement_active
        state.fatigue_active = fatigue_active
        self._previous = _PreviousState(
            str(deck_id), int(slide_id), snapshot, float(received_at)
        )

    def record_interaction(self, interaction_id: str, slide_id: int) -> bool:
        if interaction_id in self._interaction_ids:
            return False
        self._interaction_ids.add(interaction_id)
        self._slides.setdefault(int(slide_id), _MutableSlideState()).interaction_count += 1
        return True

    def pause(self, now: float) -> None:
        self._close_observation(now)

    def finish(self, now: float) -> LearnerStateReviewSummary:
        self._close_observation(now)
        self._close_study_time(now)
        self._context_started_at = None
        return LearnerStateReviewSummary(self._snapshots(self._slides))

    def active_slide_summary(self, slide_id: int, now: float) -> SlideLearnerStateSummary:
        slides = copy.deepcopy(self._slides)
        if (
            self._current_context == (self.deck_id, int(slide_id))
            and self._context_started_at is not None
        ):
            slides.setdefault(int(slide_id), _MutableSlideState()).study_seconds += max(
                0.0, now - self._context_started_at
            )
        if self._previous is not None and self._previous.slide_id == int(slide_id):
            self._apply_interval(
                slides.setdefault(int(slide_id), _MutableSlideState()),
                self._previous.snapshot,
                min(
                    MAX_STATE_INTERVAL_SECONDS,
                    max(0.0, now - self._previous.received_at),
                ),
            )
        state = slides.get(int(slide_id), _MutableSlideState())
        return self._summary(int(slide_id), state)

    def _close_study_time(self, now: float) -> None:
        if self._current_context is None or self._context_started_at is None:
            return
        if self._current_context[0] == self.deck_id:
            state = self._slides.setdefault(
                self._current_context[1], _MutableSlideState()
            )
            state.study_seconds += max(0.0, float(now) - self._context_started_at)
        self._context_started_at = float(now)

    def _close_observation(self, now: float) -> None:
        previous = self._previous
        if previous is None:
            return
        interval = min(
            MAX_STATE_INTERVAL_SECONDS,
            max(0.0, float(now) - previous.received_at),
        )
        state = self._slides.setdefault(previous.slide_id, _MutableSlideState())
        self._apply_interval(state, previous.snapshot, interval)
        self._previous = None

    @staticmethod
    def _apply_interval(
        state: _MutableSlideState,
        snapshot: LearnerStateSnapshot,
        interval: float,
    ) -> None:
        if interval <= 0.0:
            return
        emotion_ready = snapshot.emotion.status == "ready"
        engagement_ready = snapshot.engagement.status == "ready"
        fatigue_ready = snapshot.fatigue.status == "ready"
        if emotion_ready or engagement_ready or fatigue_ready:
            state.observed_seconds += interval
        if emotion_ready:
            state.emotion_observed_seconds += interval
            for index, probability in enumerate(snapshot.emotion.probabilities):
                state.emotion_weighted_sums[index] += probability * interval
        if engagement_ready:
            state.engagement_observed_seconds += interval
            state.engaged_weighted_sum += (
                float(snapshot.engagement.engaged_probability) * interval
            )
            if snapshot.engagement.alert_active:
                state.distraction_alert_seconds += interval
        if fatigue_ready:
            state.fatigue_observed_seconds += interval
            state.fatigue_weighted_sum += (
                float(snapshot.fatigue.smoothed_probability) * interval
            )
            if snapshot.fatigue.alert_active:
                state.fatigue_alert_seconds += interval

    @classmethod
    def _summary(
        cls, slide_id: int, state: _MutableSlideState
    ) -> SlideLearnerStateSummary:
        if state.emotion_observed_seconds > 0.0:
            emotion_probabilities = tuple(
                value / state.emotion_observed_seconds
                for value in state.emotion_weighted_sums
            )
            normalization = sum(emotion_probabilities)
            emotion_probabilities = tuple(
                value / normalization for value in emotion_probabilities
            )
            top_index = max(
                range(len(emotion_probabilities)),
                key=emotion_probabilities.__getitem__,
            )
            top_emotion = EMOTION_LABELS[top_index]
            top_probability = emotion_probabilities[top_index]
        else:
            emotion_probabilities = ()
            top_emotion = None
            top_probability = None
        return SlideLearnerStateSummary(
            slide_id=slide_id,
            study_seconds=state.study_seconds,
            observed_seconds=min(state.observed_seconds, state.study_seconds),
            emotion_observed_seconds=min(
                state.emotion_observed_seconds, state.observed_seconds, state.study_seconds
            ),
            engagement_observed_seconds=min(
                state.engagement_observed_seconds, state.observed_seconds, state.study_seconds
            ),
            fatigue_observed_seconds=min(
                state.fatigue_observed_seconds, state.observed_seconds, state.study_seconds
            ),
            interaction_count=state.interaction_count,
            mean_engaged_probability=(
                None
                if state.engagement_observed_seconds <= 0.0
                else state.engaged_weighted_sum / state.engagement_observed_seconds
            ),
            mean_fatigue_probability=(
                None
                if state.fatigue_observed_seconds <= 0.0
                else state.fatigue_weighted_sum / state.fatigue_observed_seconds
            ),
            emotion_probabilities=emotion_probabilities,
            top_emotion=top_emotion,
            top_emotion_probability=top_probability,
            distraction_alert_seconds=min(
                state.distraction_alert_seconds,
                state.engagement_observed_seconds,
                state.study_seconds,
            ),
            distraction_alert_count=state.distraction_alert_count,
            fatigue_alert_seconds=min(
                state.fatigue_alert_seconds,
                state.fatigue_observed_seconds,
                state.study_seconds,
            ),
            fatigue_alert_count=state.fatigue_alert_count,
        )

    @classmethod
    def _snapshots(
        cls, slides: dict[int, _MutableSlideState]
    ) -> tuple[SlideLearnerStateSummary, ...]:
        return tuple(cls._summary(slide_id, slides[slide_id]) for slide_id in sorted(slides))


@dataclass
class _ActiveStudy:
    session_id: str
    deck_id: str
    started_at_epoch: float
    gaze: GazeHeatmapAccumulator
    learner: LearnerStateReviewAccumulator


class StudyReviewStore:
    def __init__(
        self,
        root_dir: str | Path,
        *,
        legacy_gaze_path: str | Path | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.sessions_dir = self.root_dir / "sessions"
        self.latest_path = self.root_dir / "latest.json"
        self.legacy_gaze_path = (
            None if legacy_gaze_path is None else Path(legacy_gaze_path)
        )
        self._monotonic_clock = monotonic_clock
        self._wall_clock = wall_clock
        self._id_factory = id_factory
        self._lock = RLock()
        self._registered: dict[tuple[str, int], tuple[AOI, ...]] = {}
        self._current_context: tuple[str, int] | None = None
        self._active: _ActiveStudy | None = None
        self._pending_finish: StudyReviewSession | None = None
        self._sessions: dict[str, StudyReviewSession] = {}
        self._warnings: list[str] = []
        self._legacy_session_id: str | None = None
        self._load_history()
        self._armed = not bool(self._sessions)
        self._repair_latest_cache()

    def register_slide(
        self, deck_id: str, slide_id: int, aois: Sequence[AOI]
    ) -> None:
        with self._lock:
            key = (str(deck_id), int(slide_id))
            self._registered[key] = tuple(aois)
            if self._active is not None:
                self._active.gaze.register_slide(key[0], key[1], aois)

    def set_context(
        self, deck_id: str, slide_id: int, received_at: float | None = None
    ) -> None:
        context = (str(deck_id), int(slide_id))
        now = self._checked_time(
            self._monotonic_clock() if received_at is None else received_at,
            "context",
        )
        with self._lock:
            if context == self._current_context:
                return
            self._current_context = context
            if self._active is not None:
                self._active.learner.set_context(context[0], context[1], now)

    def accept_gaze(self, sample: BrowserPointGazeSample) -> bool:
        with self._lock:
            if not self._armed:
                return False
            geometry = sample.geometry.geometry if sample.geometry is not None else None
            usable = normalized_slide_point(sample) is not None
            if geometry is None:
                if self._active is not None:
                    self._active.gaze.accept(sample)
                return False
            if self._current_context is None:
                self._current_context = (geometry.deck_id, geometry.slide_id)
            if self._current_context != (geometry.deck_id, geometry.slide_id):
                return False
            if self._active is None:
                if not usable:
                    return False
                self._ensure_active(geometry.deck_id, sample.received_at)
            if geometry.deck_id != self._active.deck_id:
                self._active.gaze.pause()
                return False
            return self._active.gaze.accept(sample)

    def accept_learner_state(
        self,
        deck_id: str,
        slide_id: int,
        snapshot: LearnerStateSnapshot,
        received_at: float,
    ) -> bool:
        received_at = self._checked_time(received_at, "learner-state")
        context = (str(deck_id), int(slide_id))
        with self._lock:
            if not self._armed or context != self._current_context:
                return False
            any_ready = any(
                status == "ready"
                for status in (
                    snapshot.emotion.status,
                    snapshot.engagement.status,
                    snapshot.fatigue.status,
                )
            )
            if self._active is None:
                if not any_ready:
                    return False
                self._ensure_active(context[0], received_at)
            if self._active.deck_id != context[0]:
                return False
            self._active.learner.accept(
                context[0], context[1], snapshot, received_at
            )
            return True

    def record_completed_interaction(
        self, interaction_id: str, deck_id: str, slide_id: int
    ) -> bool:
        checked_id = str(interaction_id).strip()
        context = (str(deck_id), int(slide_id))
        if not checked_id:
            raise ValueError("interaction ID is required")
        now = self._checked_time(self._monotonic_clock(), "interaction")
        with self._lock:
            if not self._armed or context != self._current_context:
                return False
            if self._active is None:
                self._ensure_active(context[0], now)
            if self._active.deck_id != context[0]:
                return False
            return self._active.learner.record_interaction(checked_id, context[1])

    def pause(self) -> None:
        now = self._checked_time(self._monotonic_clock(), "pause")
        with self._lock:
            if self._active is not None:
                self._active.gaze.pause()
                self._active.learner.pause(now)

    def finish(self, *, deck_id: str) -> StudyReviewSession:
        checked_deck = str(deck_id)
        with self._lock:
            if self._pending_finish is not None:
                if self._pending_finish.deck_id != checked_deck:
                    raise RuntimeError("The frozen Study Review belongs to another deck.")
                frozen = self._pending_finish
            else:
                if not self._armed and self._active is None:
                    raise RuntimeError(
                        "Start a new study before replacing the completed review."
                    )
                if self._active is not None and self._active.deck_id != checked_deck:
                    raise RuntimeError(
                        "The active study belongs to another deck. Start a new study first."
                    )
                now_received = self._checked_time(self._monotonic_clock(), "finish")
                now_epoch = self._checked_time(self._wall_clock(), "finish wall-clock")
                if self._active is None:
                    self._active = self._new_active(checked_deck, now_received, now_epoch)
                gaze = self._active.gaze.finish(
                    ended_received_at=now_received,
                    ended_at_epoch=now_epoch,
                )
                learner = self._active.learner.finish(now_received)
                frozen = StudyReviewSession(
                    schema_version=STUDY_REVIEW_SCHEMA_VERSION,
                    session_id=self._active.session_id,
                    deck_id=self._active.deck_id,
                    started_at_epoch=self._active.started_at_epoch,
                    ended_at_epoch=now_epoch,
                    gaze_review=gaze,
                    learner_state_summary=learner,
                )
                self._pending_finish = frozen
                self._active = None
                self._armed = False
            self._migrate_legacy_before_finish()
            self._write_canonical(frozen)
            self._sessions[frozen.session_id] = frozen
            self._pending_finish = None
            self._refresh_latest_cache_recoverably()
            return frozen

    def start_new(self) -> None:
        with self._lock:
            if self._pending_finish is not None:
                raise RuntimeError(
                    "Retry saving the frozen Study Review before starting a new study."
                )
            self._active = None
            self._armed = True

    def has_active(self) -> bool:
        with self._lock:
            return self._active is not None

    def active_deck_id(self) -> str | None:
        with self._lock:
            return self._active.deck_id if self._active is not None else None

    def is_armed(self) -> bool:
        with self._lock:
            return self._armed

    def latest(self) -> StudyReviewSession | None:
        with self._lock:
            sessions = self._sorted_sessions()
            return sessions[0] if sessions else None

    def get(self, session_id: str) -> StudyReviewSession | None:
        with self._lock:
            return self._sessions.get(str(session_id))

    def list_sessions(self) -> tuple[StudyReviewSession, ...]:
        with self._lock:
            return self._sorted_sessions()

    def load_warnings(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._warnings)

    def delete(self, session_id: str) -> None:
        checked_id = str(session_id)
        with self._lock:
            session = self._sessions.get(checked_id)
            if session is None:
                raise KeyError("unknown Study Review session")
            canonical = self.sessions_dir / f"{checked_id}.json"
            is_legacy = checked_id == self._legacy_session_id
            if is_legacy and self.legacy_gaze_path is not None:
                self._unlink_and_fsync(self.legacy_gaze_path, missing_ok=True)
            if canonical.exists():
                self._unlink_and_fsync(canonical)
            elif not is_legacy:
                raise OSError("canonical Study Review session is missing")
            del self._sessions[checked_id]
            if is_legacy:
                self._legacy_session_id = None
            self._refresh_latest_cache_recoverably()

    def active_slide_summary(
        self, deck_id: str, slide_id: int, now: float | None = None
    ) -> SlideLearnerStateSummary:
        checked_now = self._checked_time(
            self._monotonic_clock() if now is None else now,
            "active slide summary",
        )
        with self._lock:
            if self._active is None or self._active.deck_id != str(deck_id):
                return SlideLearnerStateSummary(
                    slide_id=int(slide_id),
                    study_seconds=0.0,
                    observed_seconds=0.0,
                    emotion_observed_seconds=0.0,
                    engagement_observed_seconds=0.0,
                    fatigue_observed_seconds=0.0,
                    interaction_count=0,
                    mean_engaged_probability=None,
                    mean_fatigue_probability=None,
                    emotion_probabilities=(),
                    top_emotion=None,
                    top_emotion_probability=None,
                    distraction_alert_seconds=0.0,
                    distraction_alert_count=0,
                    fatigue_alert_seconds=0.0,
                    fatigue_alert_count=0,
                )
            return self._active.learner.active_slide_summary(int(slide_id), checked_now)

    def _ensure_active(self, deck_id: str, received_at: float) -> None:
        if self._active is not None:
            if self._active.deck_id != str(deck_id):
                raise RuntimeError("active Study Review belongs to another deck")
            return
        self._active = self._new_active(
            str(deck_id), received_at, self._checked_time(self._wall_clock(), "start wall-clock")
        )

    def _new_active(
        self, deck_id: str, received_at: float, started_at_epoch: float
    ) -> _ActiveStudy:
        session_id = str(self._id_factory())
        if not is_safe_session_id(session_id):
            raise ValueError("generated Study Review session ID is unsafe")
        gaze = GazeHeatmapAccumulator(
            session_id=session_id,
            deck_id=deck_id,
            started_at_epoch=started_at_epoch,
        )
        for (registered_deck, slide_id), aois in self._registered.items():
            gaze.register_slide(registered_deck, slide_id, aois)
        learner = LearnerStateReviewAccumulator(deck_id=deck_id)
        learner.activate_context(self._current_context, received_at)
        return _ActiveStudy(session_id, deck_id, started_at_epoch, gaze, learner)

    def _sorted_sessions(self) -> tuple[StudyReviewSession, ...]:
        return tuple(
            sorted(
                self._sessions.values(),
                key=lambda session: (session.ended_at_epoch, session.session_id),
                reverse=True,
            )
        )

    def _load_history(self) -> None:
        if self.sessions_dir.is_dir():
            for path in sorted(self.sessions_dir.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    session = StudyReviewSession.from_dict(payload)
                    if session.session_id != path.stem:
                        raise ValueError("payload session ID differs from canonical filename")
                    self._sessions[session.session_id] = session
                except Exception as exc:
                    self._warn(f"Skipped {path.name}: {type(exc).__name__}: {exc}")
        if self.legacy_gaze_path is None or not self.legacy_gaze_path.is_file():
            return
        try:
            payload = json.loads(self.legacy_gaze_path.read_text(encoding="utf-8"))
            gaze = GazeReviewSession.from_dict(payload)
            wrapper = StudyReviewSession(
                schema_version=STUDY_REVIEW_SCHEMA_VERSION,
                session_id=gaze.session_id,
                deck_id=gaze.deck_id,
                started_at_epoch=gaze.started_at_epoch,
                ended_at_epoch=gaze.ended_at_epoch,
                gaze_review=gaze,
                learner_state_summary=LearnerStateReviewSummary(),
            )
            self._legacy_session_id = wrapper.session_id
            self._sessions.setdefault(wrapper.session_id, wrapper)
        except Exception as exc:
            self._warn(f"Skipped legacy gaze review: {type(exc).__name__}: {exc}")

    def _migrate_legacy_before_finish(self) -> None:
        if self._legacy_session_id is None:
            return
        legacy = self._sessions.get(self._legacy_session_id)
        if legacy is None:
            return
        path = self.sessions_dir / f"{legacy.session_id}.json"
        if not path.exists():
            self._write_canonical(legacy)

    def _write_canonical(self, session: StudyReviewSession) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        destination = self.sessions_dir / f"{session.session_id}.json"
        if destination.exists():
            existing = StudyReviewSession.from_dict(
                json.loads(destination.read_text(encoding="utf-8"))
            )
            if existing.to_dict() == session.to_dict():
                return
            raise FileExistsError("canonical Study Review session already exists")
        self._atomic_write(session.to_json() + "\n", destination)

    def _refresh_latest_cache_recoverably(self) -> None:
        try:
            self._refresh_latest_cache()
        except OSError as exc:
            self._warn(f"latest.json cache refresh failed: {type(exc).__name__}: {exc}")

    def _repair_latest_cache(self) -> None:
        try:
            self._refresh_latest_cache()
        except OSError as exc:
            self._warn(f"latest.json cache repair failed: {type(exc).__name__}: {exc}")

    def _refresh_latest_cache(self) -> None:
        sessions = self._sorted_sessions()
        if sessions:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            self._atomic_write(sessions[0].to_json() + "\n", self.latest_path)
        elif self.latest_path.exists():
            self._unlink_and_fsync(self.latest_path)

    @staticmethod
    def _atomic_write(content: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _unlink_and_fsync(path: Path, *, missing_ok: bool = False) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            if missing_ok:
                return
            raise
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _checked_time(value: float, label: str) -> float:
        checked = float(value)
        if not math.isfinite(checked):
            raise ValueError(f"{label} time must be finite")
        return checked

    def _warn(self, warning: str) -> None:
        self._warnings.append(str(warning)[:320])
        if len(self._warnings) > 20:
            self._warnings = self._warnings[-20:]
