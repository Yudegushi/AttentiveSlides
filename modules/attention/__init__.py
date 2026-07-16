"""Privacy-preserving gaze study review."""

from .gaze_heatmap import (
    AOIDwellSnapshot,
    GazeHeatmapAccumulator,
    GazeReviewSession,
    SlideHeatmapSnapshot,
    normalized_slide_point,
)

__all__ = [
    "AOIDwellSnapshot",
    "GazeHeatmapAccumulator",
    "GazeReviewSession",
    "SlideHeatmapSnapshot",
    "normalized_slide_point",
]
