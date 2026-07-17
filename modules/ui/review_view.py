"""Pure presentation mapping for stored AttentiveSlides Study Reviews."""

from __future__ import annotations

from dataclasses import dataclass

from modules.learner_state import EMOTION_LABELS
from modules.review import StudyReviewSession


UNAVAILABLE = "Unavailable"


@dataclass(frozen=True)
class ReviewMetric:
    label: str
    value: str
    detail: str = ""


@dataclass(frozen=True)
class ReviewSlideRowView:
    slide_id: int
    study_time: str
    interaction_count: int
    engagement: str
    fatigue: str
    top_emotion: str


@dataclass(frozen=True)
class ReviewAoiDwellView:
    aoi_id: str
    label: str
    dwell_seconds: str


@dataclass(frozen=True)
class ReviewSlideDetailView:
    slide_id: int
    study_time: str
    interaction_count: int
    engagement: str
    fatigue: str
    top_emotion_label: str
    top_emotion_probability: str
    distraction_alert_duration: str
    distraction_alert_count: int | None
    fatigue_alert_duration: str
    fatigue_alert_count: int | None
    learner_coverage: str
    valid_gaze_duration: str
    gaze_coverage: str
    aoi_dwell: tuple[ReviewAoiDwellView, ...]


@dataclass(frozen=True)
class ReviewSessionView:
    summary: tuple[ReviewMetric, ...]
    emotion_distribution: tuple[ReviewMetric, ...]
    slide_rows: tuple[ReviewSlideRowView, ...]
    slide_details: dict[int, ReviewSlideDetailView]
    alert_summary: tuple[ReviewMetric, ...] = ()


def _duration(seconds: float) -> str:
    total = max(0, round(float(seconds)))
    minutes, remainder = divmod(total, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _seconds(seconds: float) -> str:
    return f"{max(0.0, float(seconds)):.1f} s"


def _percent(value: float | None) -> str:
    return UNAVAILABLE if value is None else f"{float(value):.0%}"


def _coverage(observed: float, total: float) -> str:
    if total <= 0.0:
        return UNAVAILABLE
    return f"{min(1.0, max(0.0, observed / total)):.0%}"


def _top_emotion(label: str | None, probability: float | None) -> str:
    if label is None or probability is None:
        return UNAVAILABLE
    return f"{label} · {probability:.0%}"


def build_review_view(review: StudyReviewSession) -> ReviewSessionView:
    """Join learner-state and gaze summaries by slide ID for rendering."""
    learner_summary = review.learner_state_summary
    learner_by_id = {slide.slide_id: slide for slide in learner_summary.slides}
    gaze_by_id = {slide.slide_id: slide for slide in review.gaze_review.slides}
    slide_ids = sorted(set(learner_by_id) | set(gaze_by_id))

    study_seconds = learner_summary.study_seconds
    observed_seconds = sum(
        slide.observed_seconds for slide in learner_summary.slides
    )
    summary = (
        ReviewMetric("Study duration", _duration(study_seconds)),
        ReviewMetric("Interactions", str(learner_summary.interaction_count)),
        ReviewMetric("Mean engagement", _percent(
            learner_summary.mean_engaged_probability
        )),
        ReviewMetric("Mean fatigue", _percent(
            learner_summary.mean_fatigue_probability
        )),
        ReviewMetric("Top emotion", _top_emotion(
            learner_summary.top_emotion,
            learner_summary.top_emotion_probability,
        )),
        ReviewMetric(
            "Learner coverage",
            _coverage(observed_seconds, study_seconds),
            f"{_seconds(observed_seconds)} observed",
        ),
    )

    emotion_values = learner_summary.emotion_probabilities
    emotion_distribution = tuple(
        ReviewMetric(
            label,
            _percent(emotion_values[index] if emotion_values else None),
        )
        for index, label in enumerate(EMOTION_LABELS)
    )
    engagement_observed = sum(
        slide.engagement_observed_seconds for slide in learner_summary.slides
    )
    fatigue_observed = sum(
        slide.fatigue_observed_seconds for slide in learner_summary.slides
    )
    alert_summary = (
        ReviewMetric(
            "Distraction alert duration",
            _seconds(learner_summary.distraction_alert_seconds)
            if engagement_observed > 0.0 else UNAVAILABLE,
        ),
        ReviewMetric(
            "Distraction alert count",
            str(learner_summary.distraction_alert_count)
            if engagement_observed > 0.0 else UNAVAILABLE,
        ),
        ReviewMetric(
            "Fatigue alert duration",
            _seconds(learner_summary.fatigue_alert_seconds)
            if fatigue_observed > 0.0 else UNAVAILABLE,
        ),
        ReviewMetric(
            "Fatigue alert count",
            str(learner_summary.fatigue_alert_count)
            if fatigue_observed > 0.0 else UNAVAILABLE,
        ),
    )

    rows: list[ReviewSlideRowView] = []
    details: dict[int, ReviewSlideDetailView] = {}
    for slide_id in slide_ids:
        learner = learner_by_id.get(slide_id)
        gaze = gaze_by_id.get(slide_id)
        study_time = _duration(learner.study_seconds) if learner else UNAVAILABLE
        interaction_count = learner.interaction_count if learner else 0
        engagement = _percent(
            learner.mean_engaged_probability
            if learner and learner.engagement_observed_seconds > 0.0 else None
        )
        fatigue = _percent(
            learner.mean_fatigue_probability
            if learner and learner.fatigue_observed_seconds > 0.0 else None
        )
        top_label = (
            learner.top_emotion
            if learner and learner.emotion_observed_seconds > 0.0 else None
        )
        top_probability = (
            learner.top_emotion_probability
            if learner and learner.emotion_observed_seconds > 0.0 else None
        )
        rows.append(ReviewSlideRowView(
            slide_id=slide_id,
            study_time=study_time,
            interaction_count=interaction_count,
            engagement=engagement,
            fatigue=fatigue,
            top_emotion=_top_emotion(top_label, top_probability),
        ))

        aoi_dwell: list[ReviewAoiDwellView] = []
        if gaze is not None:
            aoi_dwell.extend(
                ReviewAoiDwellView(item.aoi_id, item.label, _seconds(item.dwell_seconds))
                for item in gaze.aoi_dwell
            )
            if gaze.other_slide_seconds > 0.05:
                aoi_dwell.append(ReviewAoiDwellView(
                    "other_slide_area",
                    "Other slide area",
                    _seconds(gaze.other_slide_seconds),
                ))
        details[slide_id] = ReviewSlideDetailView(
            slide_id=slide_id,
            study_time=study_time,
            interaction_count=interaction_count,
            engagement=engagement,
            fatigue=fatigue,
            top_emotion_label=top_label or UNAVAILABLE,
            top_emotion_probability=_percent(top_probability),
            distraction_alert_duration=(
                _seconds(learner.distraction_alert_seconds)
                if learner and learner.engagement_observed_seconds > 0.0
                else UNAVAILABLE
            ),
            distraction_alert_count=(
                learner.distraction_alert_count
                if learner and learner.engagement_observed_seconds > 0.0
                else None
            ),
            fatigue_alert_duration=(
                _seconds(learner.fatigue_alert_seconds)
                if learner and learner.fatigue_observed_seconds > 0.0
                else UNAVAILABLE
            ),
            fatigue_alert_count=(
                learner.fatigue_alert_count
                if learner and learner.fatigue_observed_seconds > 0.0
                else None
            ),
            learner_coverage=(
                _coverage(learner.observed_seconds, learner.study_seconds)
                if learner else UNAVAILABLE
            ),
            valid_gaze_duration=(
                _seconds(gaze.valid_gaze_seconds)
                if gaze is not None and gaze.observed_seconds > 0.0
                else UNAVAILABLE
            ),
            gaze_coverage=(
                _percent(gaze.coverage)
                if gaze is not None and gaze.observed_seconds > 0.0
                else UNAVAILABLE
            ),
            aoi_dwell=tuple(aoi_dwell),
        )

    return ReviewSessionView(
        summary=summary,
        emotion_distribution=emotion_distribution,
        slide_rows=tuple(rows),
        slide_details=details,
        alert_summary=alert_summary,
    )
