"""Prompt templates for the task-bounded slide tutor."""

from __future__ import annotations

from modules.common.schemas import TutorContext


MODE_BY_STRATEGY = {
    "normal": None,
    "short_recap": "short_recap",
    "simpler_explanation": "simplify",
    "step_by_step": "step_by_step",
    "ask_confirmation": None,
    "review_question": "review",
}


def response_mode(intent: str, adaptive_strategy: str) -> str:
    return MODE_BY_STRATEGY.get(adaptive_strategy) or intent


def build_prompt(context: TutorContext) -> str:
    resolved = context.resolved_query
    mode = response_mode(resolved.intent, context.adaptive_strategy)
    target = context.current_aoi.aoi_id if context.current_aoi else "unresolved_target"

    return "\n".join(
        [
            "You are a slide-based tutor for AttentiveSlides.",
            "Use only the provided slide context. If external background is needed, label it explicitly.",
            "Do not claim to know the learner's true emotion, fatigue, confusion, or attention.",
            "Answer in English, regardless of the language used in the learner's question.",
            f"Response mode: {mode}",
            f"Adaptive strategy: {context.adaptive_strategy}",
            f"User transcript: {resolved.transcript}",
            f"Confirmed or resolved AOI: {target}",
            f"AOI confidence: {resolved.target_confidence}",
            f"Current AOI text: {context.current_aoi_text}",
            f"Current slide text: {context.current_slide_text}",
            f"Neighbor slide text: {context.neighbor_slide_text}",
            "Return a direct answer, why it matters, and one active-recall question.",
        ]
    )
