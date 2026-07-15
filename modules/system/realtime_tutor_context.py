"""Build bounded, grounded instructions for an Omni tutor session."""

from __future__ import annotations

from dataclasses import dataclass

from modules.realtime.realtime_contracts import TargetBinding


_MAX_TARGET_CHARS = 4_000
_MAX_SLIDE_CHARS = 6_000
_MAX_VISUAL_CHARS = 3_000


def _bounded(value: str, limit: int) -> str:
    normalized = " ".join(str(value).strip().split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


@dataclass(frozen=True)
class RealtimeTutorContext:
    deck_id: str
    slide_number: int
    slide_text: str
    target: TargetBinding
    visual_observation: str = ""
    visual_observation_is_model_derived: bool = False

    def __post_init__(self) -> None:
        if not self.deck_id.strip():
            raise ValueError("deck_id must not be empty")
        if isinstance(self.slide_number, bool) or self.slide_number <= 0:
            raise ValueError("slide_number must be positive")


def build_realtime_tutor_instructions(context: RealtimeTutorContext) -> str:
    target_label = _bounded(context.target.label or context.target.target_id, 500)
    target_text = _bounded(context.target.text, _MAX_TARGET_CHARS)
    slide_text = _bounded(context.slide_text, _MAX_SLIDE_CHARS)
    visual = _bounded(context.visual_observation, _MAX_VISUAL_CHARS)

    sections = [
        "You are a concise, grounded tutor in a persistent spoken conversation.",
        f"Slide number: {context.slide_number}",
        f"Confirmed target: {target_label}",
        f"Confirmed target text: {target_text or '[no native target text provided]'}",
        f"Necessary slide context: {slide_text or '[no additional slide text provided]'}",
    ]
    if visual:
        sections.append(f"Visual observation: {visual}")
    if context.visual_observation_is_model_derived:
        sections.append(
            "The visual observation was produced by a vision model and may contain transcription errors. "
            "If it conflicts with PDF-native or AOI-native text, prefer the native text."
        )
    sections.extend(
        [
            "Answer only about the confirmed target unless the application explicitly confirms a target switch.",
            "Keep answers concise, support natural follow-up questions, and say when the supplied context is insufficient.",
            "Do not claim to see content that was not supplied. Do not infer the learner's attention, cognition, confusion, or other mental state.",
            "Return the answer, not hidden reasoning or chain-of-thought.",
        ]
    )
    return "\n".join(sections)
