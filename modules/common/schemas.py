"""Stable dataclasses shared across the mock-driven AttentiveSlides pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


IntentName = Literal[
    "explain",
    "compare",
    "quiz",
    "summarize",
    "simplify",
    "step_by_step",
    "review",
    "break",
    "unknown",
]

ConfirmationMode = Literal["none", "confirm_one", "choose_top2", "click_required"]

AdaptiveStrategy = Literal[
    "normal",
    "short_recap",
    "simpler_explanation",
    "step_by_step",
    "ask_confirmation",
    "review_question",
]


@dataclass(frozen=True)
class AOI:
    aoi_id: str
    bbox: list[float]
    type: str
    text: str = ""
    name: str | None = None

    def __post_init__(self) -> None:
        if len(self.bbox) != 4:
            raise ValueError("AOI bbox must be [x1, y1, x2, y2].")
        if any(value < 0 or value > 1 for value in self.bbox):
            raise ValueError("AOI bbox values must be normalized to [0, 1].")


@dataclass(frozen=True)
class GazePrediction:
    slide_id: int
    gaze_grid: str
    predicted_aoi_id: str | None
    confidence: float
    stable_duration_sec: float = 0.0
    alternative_targets: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class LearningState:
    face_detected: bool = True
    screen_facing_score: float = 1.0
    yawn_detected: bool = False
    yawn_count_last_3min: int = 0
    eyes_closed: bool = False
    eye_closure_duration_sec: float = 0.0
    head_down: bool = False
    fatigue_signal_score: float = 0.0
    possible_review_needed: bool = False


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class IntentResult:
    intent: IntentName
    confidence: float
    has_deictic_reference: bool
    explicit_target_hint: str | None
    transcript: str


@dataclass(frozen=True)
class ResolvedQuery:
    query_id: str
    deck_id: str
    slide_id: int
    transcript: str
    intent: IntentName
    resolved_aoi_id: str | None
    target_confidence: float
    needs_confirmation: bool
    confirmation_mode: ConfirmationMode
    adaptive_strategy: AdaptiveStrategy
    evidence: list[str] = field(default_factory=list)
    alternative_targets: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class TutorContext:
    deck_id: str
    slide_id: int
    current_slide_text: str
    current_aoi: AOI | None
    current_aoi_text: str
    neighbor_slide_text: str
    resolved_query: ResolvedQuery
    interaction_history: list[dict[str, Any]] = field(default_factory=list)
    adaptive_strategy: AdaptiveStrategy = "normal"


@dataclass(frozen=True)
class TutorResponse:
    query_id: str
    response_mode: str
    answer: str
    active_recall_question: str | None = None
    adaptive_suggestion: str | None = None
    used_context: dict[str, Any] = field(default_factory=dict)
    safety_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InteractionLogEvent:
    query_id: str
    timestamp: float
    deck_id: str
    slide_id: int
    transcript: str
    intent: str
    predicted_aoi_id: str | None
    resolved_aoi_id: str | None
    confirmed_aoi_id: str | None
    target_confidence: float
    needs_confirmation: bool
    confirmation_mode: str
    user_corrected: bool
    adaptive_strategy: str
    response_mode: str
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
