"""Learner-state inference and temporal presentation contracts."""

from .emotieff_estimator import (
    EMOTION_LABELS,
    ENGAGEMENT_LABELS,
    AffectFrameOutput,
    EmotiEffEstimator,
    EngagementAttentionHead,
)

__all__ = [
    "AffectFrameOutput",
    "EMOTION_LABELS",
    "ENGAGEMENT_LABELS",
    "EmotiEffEstimator",
    "EngagementAttentionHead",
]
