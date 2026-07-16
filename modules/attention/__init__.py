"""Privacy-preserving gaze study review."""

from .gaze_heatmap import (
    AOIDwellSnapshot,
    GazeHeatmapAccumulator,
    GazeReviewSession,
    SlideHeatmapSnapshot,
    normalized_slide_point,
)
from .gaze_review_store import GazeReviewStore
from .heatmap_renderer import render_review_slide, review_png_bytes

__all__ = [
    "AOIDwellSnapshot",
    "GazeHeatmapAccumulator",
    "GazeReviewSession",
    "GazeReviewStore",
    "SlideHeatmapSnapshot",
    "normalized_slide_point",
    "render_review_slide",
    "review_png_bytes",
]
