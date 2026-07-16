"""Learner-state inference and temporal presentation contracts."""

from .emotieff_estimator import (
    EMOTION_LABELS,
    ENGAGEMENT_LABELS,
    AffectFrameOutput,
    EmotiEffEstimator,
    EngagementAttentionHead,
)
from .contracts import (
    EmotionSnapshot,
    EngagementSnapshot,
    LearnerStateSnapshot,
    LearnerStateStatus,
    LearnerStateStore,
)
from .temporal import (
    EmotionTemporalConfig,
    EmotionTemporalTracker,
    EngagementTemporalConfig,
    EngagementTemporalTracker,
)

__all__ = [
    "AffectFrameOutput",
    "EMOTION_LABELS",
    "ENGAGEMENT_LABELS",
    "EmotiEffEstimator",
    "EngagementAttentionHead",
    "EmotionSnapshot",
    "EmotionTemporalConfig",
    "EmotionTemporalTracker",
    "EngagementSnapshot",
    "EngagementTemporalConfig",
    "EngagementTemporalTracker",
    "LearnerStateSnapshot",
    "LearnerStateStatus",
    "LearnerStateStore",
]
