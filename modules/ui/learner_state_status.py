"""Pure learner-state status and reminder presentation mapping."""

from __future__ import annotations

import html
from dataclasses import dataclass

from modules.learner_state import LearnerStateSnapshot
from modules.review import SlideLearnerStateSummary


FATIGUE_ALERT = "Fatigue has stayed high — consider a short break."
DISTRACTION_ALERT = "Attention appears distracted — return to the slide when ready."
COMBINED_ALERT = "Fatigue and distraction are elevated — consider a short reset."
DISCLAIMER = "Model estimates; not a diagnosis."


@dataclass(frozen=True)
class LearnerStateView:
    emotion_text: str
    engagement_text: str
    fatigue_text: str
    slide_text: str
    alert_text: str | None
    can_dismiss_distraction: bool
    unavailable_details: tuple[str, ...]


def _percent(value: float) -> str:
    return f"{round(float(value) * 100)}%"


def _duration(seconds: float) -> str:
    total = max(0, round(float(seconds)))
    minutes, remainder = divmod(total, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _safe_error(label: str, error: str | None) -> str | None:
    if not error:
        return None
    escaped = html.escape(str(error).strip()[:160])
    if len(escaped) > 160:
        escaped = escaped[:157] + "..."
    return f"{label}: {escaped}"


def build_learner_state_view(
    snapshot: LearnerStateSnapshot,
    slide: SlideLearnerStateSummary,
    *,
    live_enabled: bool,
) -> LearnerStateView:
    details = []
    for label, state in (
        ("Emotion", snapshot.emotion),
        ("Engagement", snapshot.engagement),
        ("Fatigue", snapshot.fatigue),
    ):
        if state.status == "unavailable":
            detail = _safe_error(label, state.error)
            if detail:
                details.append(detail)

    if not live_enabled:
        emotion_text = "Live off"
        engagement_text = "Live off"
        fatigue_text = "Live off"
    else:
        emotion = snapshot.emotion
        if (
            emotion.status in {"ready", "stale"}
            and emotion.top_label is not None
            and emotion.top_probability is not None
        ):
            suffix = " · stale" if emotion.status == "stale" else ""
            emotion_text = (
                f"{html.escape(str(emotion.top_label))} "
                f"{_percent(float(emotion.top_probability))}{suffix}"
            )
        elif emotion.status == "unavailable":
            emotion_text = "Unavailable"
        else:
            emotion_text = "Waiting for face"

        engagement = snapshot.engagement
        if (
            engagement.status in {"ready", "stale"}
            and engagement.engaged_probability is not None
            and engagement.distracted_probability is not None
        ):
            engaged = float(engagement.engaged_probability)
            distracted = float(engagement.distracted_probability)
            if engaged >= distracted:
                engagement_text = f"Engaged {_percent(engaged)}"
            else:
                engagement_text = f"Distracted {_percent(distracted)}"
            if engagement.status == "stale":
                engagement_text += " · stale"
        elif engagement.status == "warming":
            engagement_text = (
                "Learning pattern · "
                f"{engagement.buffered_frames} / {engagement.required_frames} frames"
            )
        elif engagement.status == "unavailable":
            engagement_text = "Unavailable"
        else:
            engagement_text = "Waiting for face"

        fatigue = snapshot.fatigue
        if (
            fatigue.status in {"ready", "stale"}
            and fatigue.smoothed_probability is not None
        ):
            fatigue_text = _percent(float(fatigue.smoothed_probability))
            if fatigue.status == "stale":
                fatigue_text += " · stale"
        elif fatigue.status == "unavailable":
            fatigue_text = "Unavailable"
        else:
            fatigue_text = "Waiting for face"

    fatigue_alert = bool(
        live_enabled
        and snapshot.fatigue.status == "ready"
        and snapshot.fatigue.alert_active
    )
    distraction_alert = bool(
        live_enabled
        and snapshot.engagement.status == "ready"
        and snapshot.engagement.alert_active
        and not snapshot.engagement.reminder_suppressed
    )
    if fatigue_alert and distraction_alert:
        alert_text = COMBINED_ALERT
    elif fatigue_alert:
        alert_text = FATIGUE_ALERT
    elif distraction_alert:
        alert_text = DISTRACTION_ALERT
    else:
        alert_text = None

    interactions = (
        "1 interaction" if slide.interaction_count == 1 else f"{slide.interaction_count} interactions"
    )
    return LearnerStateView(
        emotion_text=emotion_text,
        engagement_text=engagement_text,
        fatigue_text=fatigue_text,
        slide_text=f"{_duration(slide.study_seconds)} · {interactions}",
        alert_text=alert_text,
        can_dismiss_distraction=bool(
            live_enabled
            and snapshot.engagement.status == "ready"
            and snapshot.engagement.alert_active
            and not snapshot.engagement.reminder_suppressed
        ),
        unavailable_details=tuple(details),
    )
