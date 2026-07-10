"""Rule-based intent parsing for the first AttentiveSlides dry-run."""

from __future__ import annotations

import re

from modules.common.schemas import IntentName, IntentResult, Transcript


INTENT_PATTERNS: list[tuple[IntentName, tuple[str, ...], float]] = [
    ("step_by_step", ("一步一步", "逐步", "step by step", "walk me through"), 0.92),
    ("simplify", ("简单", "更简单", "讲简单", "simplify", "simpler"), 0.9),
    ("compare", ("比较", "区别", "相比", "compare", "difference", "versus", "vs"), 0.9),
    ("quiz", ("考我", "测验", "测试我", "quiz", "test me", "question me"), 0.9),
    ("summarize", ("总结", "概括", "这一页", "整页", "summarize", "summary", "main point"), 0.88),
    ("review", ("复习", "review", "recap", "哪里需要看"), 0.86),
    ("break", ("休息", "累了", "break", "pause", "tired"), 0.86),
    ("explain", ("解释", "讲一下", "讲讲", "说明", "什么意思", "是什么意思", "explain", "what is", "why is"), 0.86),
]

DEICTIC_PATTERNS = (
    "这个",
    "那个",
    "这里",
    "这块",
    "这部分",
    "this",
    "that",
    "here",
    "this figure",
    "this formula",
    "this concept",
)

TARGET_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("right_figure", ("右边这个图", "右边的图", "右图", "右侧图", "right figure", "figure on the right")),
    ("left_text", ("左边文字", "左侧文字", "左边这段", "left text", "left block")),
    ("bottom_formula", ("底部公式", "下面公式", "这个公式", "bottom formula", "formula")),
    ("bottom_caption", ("底部说明", "下面说明", "caption", "bottom caption")),
    ("whole_slide", ("这一页", "整页", "this slide", "whole slide", "current slide")),
]


def parse_intent(transcript: Transcript | str) -> IntentResult:
    text = transcript.text if isinstance(transcript, Transcript) else transcript
    normalized = _normalize(text)

    intent, confidence = _match_intent(normalized)
    explicit_target_hint = _match_explicit_target(normalized)
    has_deictic_reference = any(pattern in normalized for pattern in DEICTIC_PATTERNS)

    if explicit_target_hint and explicit_target_hint != "whole_slide":
        has_deictic_reference = True

    return IntentResult(
        intent=intent,
        confidence=confidence,
        has_deictic_reference=has_deictic_reference,
        explicit_target_hint=explicit_target_hint,
        transcript=text,
    )


def detect_deictic_reference(transcript: Transcript | str) -> bool:
    return parse_intent(transcript).has_deictic_reference


def _match_intent(normalized: str) -> tuple[IntentName, float]:
    for intent, patterns, confidence in INTENT_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return intent, confidence
    return "unknown", 0.35


def _match_explicit_target(normalized: str) -> str | None:
    for target, patterns in TARGET_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return target
    return None


def _normalize(text: str) -> str:
    lowered = text.strip().lower()
    return re.sub(r"\s+", " ", lowered)
