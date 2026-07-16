"""Serializable privacy-preserving integrated Study Review contracts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from modules.attention.gaze_heatmap import GazeReviewSession
from modules.learner_state import EMOTION_LABELS


STUDY_REVIEW_SCHEMA_VERSION = 1
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TOLERANCE = 1e-4


def is_safe_session_id(value: str) -> bool:
    return bool(_SESSION_ID.fullmatch(value))


def _finite_nonnegative(value: float, label: str) -> float:
    checked = float(value)
    if not math.isfinite(checked) or checked < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return checked


def _probability(value: float | None, label: str) -> float | None:
    if value is None:
        return None
    checked = float(value)
    if not math.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise ValueError(f"{label} must be a finite probability")
    return checked


@dataclass(frozen=True)
class SlideLearnerStateSummary:
    slide_id: int
    study_seconds: float
    observed_seconds: float
    emotion_observed_seconds: float
    engagement_observed_seconds: float
    fatigue_observed_seconds: float
    interaction_count: int
    mean_engaged_probability: float | None
    mean_fatigue_probability: float | None
    emotion_probabilities: tuple[float, ...]
    top_emotion: str | None
    top_emotion_probability: float | None
    distraction_alert_seconds: float
    distraction_alert_count: int
    fatigue_alert_seconds: float
    fatigue_alert_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.slide_id, int) or self.slide_id < 1:
            raise ValueError("review slide ID must be positive")
        durations = {
            "study seconds": self.study_seconds,
            "observed seconds": self.observed_seconds,
            "emotion observed seconds": self.emotion_observed_seconds,
            "engagement observed seconds": self.engagement_observed_seconds,
            "fatigue observed seconds": self.fatigue_observed_seconds,
            "distraction alert seconds": self.distraction_alert_seconds,
            "fatigue alert seconds": self.fatigue_alert_seconds,
        }
        for label, value in durations.items():
            _finite_nonnegative(value, label)
        if self.observed_seconds > self.study_seconds + _TOLERANCE:
            raise ValueError("state-observed seconds cannot exceed study seconds")
        for value in (
            self.emotion_observed_seconds,
            self.engagement_observed_seconds,
            self.fatigue_observed_seconds,
        ):
            if value > self.observed_seconds + _TOLERANCE:
                raise ValueError("modality coverage cannot exceed union coverage")
        if self.distraction_alert_seconds > self.engagement_observed_seconds + _TOLERANCE:
            raise ValueError("distraction alert time cannot exceed engagement coverage")
        if self.fatigue_alert_seconds > self.fatigue_observed_seconds + _TOLERANCE:
            raise ValueError("fatigue alert time cannot exceed fatigue coverage")
        for value, label in (
            (self.interaction_count, "interaction count"),
            (self.distraction_alert_count, "distraction alert count"),
            (self.fatigue_alert_count, "fatigue alert count"),
        ):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} must be a non-negative integer")
        _probability(self.mean_engaged_probability, "mean engagement")
        _probability(self.mean_fatigue_probability, "mean fatigue")
        _probability(self.top_emotion_probability, "top emotion")
        if self.engagement_observed_seconds > 0.0:
            if self.mean_engaged_probability is None:
                raise ValueError("engagement coverage requires an engagement mean")
        elif self.mean_engaged_probability is not None:
            raise ValueError("engagement mean requires engagement coverage")
        if self.fatigue_observed_seconds > 0.0:
            if self.mean_fatigue_probability is None:
                raise ValueError("fatigue coverage requires a fatigue mean")
        elif self.mean_fatigue_probability is not None:
            raise ValueError("fatigue mean requires fatigue coverage")
        if self.emotion_observed_seconds > 0.0:
            if len(self.emotion_probabilities) != len(EMOTION_LABELS):
                raise ValueError("emotion coverage requires eight probabilities")
            if any(_probability(value, "emotion") is None for value in self.emotion_probabilities):
                raise ValueError("emotion probabilities are invalid")
            if not math.isclose(sum(self.emotion_probabilities), 1.0, abs_tol=_TOLERANCE):
                raise ValueError("emotion probabilities must sum to one")
            if self.top_emotion not in EMOTION_LABELS or self.top_emotion_probability is None:
                raise ValueError("emotion coverage requires one official top emotion")
            index = EMOTION_LABELS.index(self.top_emotion)
            if not math.isclose(
                self.emotion_probabilities[index],
                self.top_emotion_probability,
                abs_tol=1e-6,
            ):
                raise ValueError("top emotion probability does not match its label")
        elif (
            self.emotion_probabilities
            or self.top_emotion is not None
            or self.top_emotion_probability is not None
        ):
            raise ValueError("emotion summary requires emotion coverage")

    def to_dict(self) -> dict[str, object]:
        rounded_emotions = [round(value, 4) for value in self.emotion_probabilities]
        if rounded_emotions:
            rounded_emotions[-1] = round(1.0 - sum(rounded_emotions[:-1]), 4)
        rounded_top = None
        if self.top_emotion is not None:
            rounded_top = rounded_emotions[EMOTION_LABELS.index(self.top_emotion)]
        return {
            "slide_id": self.slide_id,
            "study_seconds": round(self.study_seconds, 4),
            "observed_seconds": round(self.observed_seconds, 4),
            "emotion_observed_seconds": round(self.emotion_observed_seconds, 4),
            "engagement_observed_seconds": round(self.engagement_observed_seconds, 4),
            "fatigue_observed_seconds": round(self.fatigue_observed_seconds, 4),
            "interaction_count": self.interaction_count,
            "mean_engaged_probability": (
                None
                if self.mean_engaged_probability is None
                else round(self.mean_engaged_probability, 4)
            ),
            "mean_fatigue_probability": (
                None
                if self.mean_fatigue_probability is None
                else round(self.mean_fatigue_probability, 4)
            ),
            "emotion_probabilities": rounded_emotions,
            "top_emotion": self.top_emotion,
            "top_emotion_probability": rounded_top,
            "distraction_alert_seconds": round(self.distraction_alert_seconds, 4),
            "distraction_alert_count": self.distraction_alert_count,
            "fatigue_alert_seconds": round(self.fatigue_alert_seconds, 4),
            "fatigue_alert_count": self.fatigue_alert_count,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SlideLearnerStateSummary":
        return cls(
            slide_id=int(payload["slide_id"]),
            study_seconds=float(payload["study_seconds"]),
            observed_seconds=float(payload["observed_seconds"]),
            emotion_observed_seconds=float(payload["emotion_observed_seconds"]),
            engagement_observed_seconds=float(payload["engagement_observed_seconds"]),
            fatigue_observed_seconds=float(payload["fatigue_observed_seconds"]),
            interaction_count=int(payload["interaction_count"]),
            mean_engaged_probability=(
                None
                if payload.get("mean_engaged_probability") is None
                else float(payload["mean_engaged_probability"])
            ),
            mean_fatigue_probability=(
                None
                if payload.get("mean_fatigue_probability") is None
                else float(payload["mean_fatigue_probability"])
            ),
            emotion_probabilities=tuple(
                float(value) for value in payload.get("emotion_probabilities", [])
            ),
            top_emotion=(
                None if payload.get("top_emotion") is None else str(payload["top_emotion"])
            ),
            top_emotion_probability=(
                None
                if payload.get("top_emotion_probability") is None
                else float(payload["top_emotion_probability"])
            ),
            distraction_alert_seconds=float(payload["distraction_alert_seconds"]),
            distraction_alert_count=int(payload["distraction_alert_count"]),
            fatigue_alert_seconds=float(payload["fatigue_alert_seconds"]),
            fatigue_alert_count=int(payload["fatigue_alert_count"]),
        )


@dataclass(frozen=True)
class LearnerStateReviewSummary:
    slides: tuple[SlideLearnerStateSummary, ...] = ()

    def __post_init__(self) -> None:
        slide_ids = [slide.slide_id for slide in self.slides]
        if len(slide_ids) != len(set(slide_ids)):
            raise ValueError("learner-state review contains duplicate slide IDs")

    @property
    def study_seconds(self) -> float:
        return sum(slide.study_seconds for slide in self.slides)

    @property
    def interaction_count(self) -> int:
        return sum(slide.interaction_count for slide in self.slides)

    @staticmethod
    def _weighted_mean(slides, value_name: str, weight_name: str) -> float | None:
        total_weight = sum(getattr(slide, weight_name) for slide in slides)
        if total_weight <= 0.0:
            return None
        return sum(
            float(getattr(slide, value_name)) * getattr(slide, weight_name)
            for slide in slides
            if getattr(slide, value_name) is not None
        ) / total_weight

    @property
    def mean_engaged_probability(self) -> float | None:
        return self._weighted_mean(
            self.slides, "mean_engaged_probability", "engagement_observed_seconds"
        )

    @property
    def mean_fatigue_probability(self) -> float | None:
        return self._weighted_mean(
            self.slides, "mean_fatigue_probability", "fatigue_observed_seconds"
        )

    @property
    def emotion_probabilities(self) -> tuple[float, ...]:
        total = sum(slide.emotion_observed_seconds for slide in self.slides)
        if total <= 0.0:
            return ()
        values = [0.0] * len(EMOTION_LABELS)
        for slide in self.slides:
            for index, probability in enumerate(slide.emotion_probabilities):
                values[index] += probability * slide.emotion_observed_seconds
        normalized = [value / total for value in values]
        normalization = sum(normalized)
        return tuple(value / normalization for value in normalized)

    @property
    def top_emotion(self) -> str | None:
        values = self.emotion_probabilities
        return EMOTION_LABELS[max(range(len(values)), key=values.__getitem__)] if values else None

    @property
    def top_emotion_probability(self) -> float | None:
        values = self.emotion_probabilities
        return max(values) if values else None

    @property
    def distraction_alert_seconds(self) -> float:
        return sum(slide.distraction_alert_seconds for slide in self.slides)

    @property
    def distraction_alert_count(self) -> int:
        return sum(slide.distraction_alert_count for slide in self.slides)

    @property
    def fatigue_alert_seconds(self) -> float:
        return sum(slide.fatigue_alert_seconds for slide in self.slides)

    @property
    def fatigue_alert_count(self) -> int:
        return sum(slide.fatigue_alert_count for slide in self.slides)

    def to_dict(self) -> dict[str, object]:
        return {"slides": [slide.to_dict() for slide in self.slides]}

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "LearnerStateReviewSummary":
        return cls(
            tuple(
                SlideLearnerStateSummary.from_dict(item)
                for item in payload.get("slides", [])
            )
        )


@dataclass(frozen=True)
class StudyReviewSession:
    schema_version: int
    session_id: str
    deck_id: str
    started_at_epoch: float
    ended_at_epoch: float
    gaze_review: GazeReviewSession
    learner_state_summary: LearnerStateReviewSummary

    def __post_init__(self) -> None:
        if self.schema_version != STUDY_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported Study Review schema")
        if not is_safe_session_id(self.session_id):
            raise ValueError("Study Review session ID is unsafe")
        if not isinstance(self.deck_id, str) or not self.deck_id.strip():
            raise ValueError("Study Review deck ID is required")
        if (
            not math.isfinite(self.started_at_epoch)
            or not math.isfinite(self.ended_at_epoch)
            or self.ended_at_epoch < self.started_at_epoch
        ):
            raise ValueError("Study Review timestamps are invalid")
        if (
            self.gaze_review.session_id != self.session_id
            or self.gaze_review.deck_id != self.deck_id
            or abs(self.gaze_review.started_at_epoch - self.started_at_epoch) > _TOLERANCE
            or abs(self.gaze_review.ended_at_epoch - self.ended_at_epoch) > _TOLERANCE
            or any(slide.deck_id != self.deck_id for slide in self.gaze_review.slides)
        ):
            raise ValueError("gaze review identity does not match Study Review")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "deck_id": self.deck_id,
            "started_at_epoch": round(self.started_at_epoch, 4),
            "ended_at_epoch": round(self.ended_at_epoch, 4),
            "gaze_review": self.gaze_review.to_dict(),
            "learner_state_summary": self.learner_state_summary.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "StudyReviewSession":
        return cls(
            schema_version=int(payload.get("schema_version", -1)),
            session_id=str(payload["session_id"]),
            deck_id=str(payload["deck_id"]),
            started_at_epoch=float(payload["started_at_epoch"]),
            ended_at_epoch=float(payload["ended_at_epoch"]),
            gaze_review=GazeReviewSession.from_dict(payload["gaze_review"]),
            learner_state_summary=LearnerStateReviewSummary.from_dict(
                payload.get("learner_state_summary", {"slides": []})
            ),
        )
