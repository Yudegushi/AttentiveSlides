"""Grounded system instructions for realtime tutor turns."""

from __future__ import annotations

from dataclasses import dataclass


MAX_CONTEXT_CHARACTERS = 8_000


@dataclass(frozen=True)
class RealtimeTutorContext:
    slide_number: int
    slide_text: str
    selected_region_text: str
    target_scope: str


def build_realtime_tutor_instructions(
    context: RealtimeTutorContext,
) -> str:
    selected_text = (
        context
        .selected_region_text
        .strip()
    )

    slide_text = (
        context.slide_text.strip()
    )

    use_region = bool(
        context.target_scope
        == "Manual region"
        and selected_text
    )

    grounded_text = (
        selected_text
        if use_region
        else slide_text
    )

    grounded_text = (
        grounded_text[
            :MAX_CONTEXT_CHARACTERS
        ]
    )

    return f"""
你是 AttentiveSlides 的教学助手。

当前幻灯片：第 {context.slide_number} 页
Grounding scope：{context.target_scope}

只允许使用以下幻灯片内容作为主要依据：
---
{grounded_text}
---

要求：
1. 回答用户当前的语音问题。
2. 优先依据以上幻灯片内容。
3. 不要声称幻灯片包含未提供的信息。
4. 内容适合本科专业课程。
5. 专业名词保留英文。
6. 回答简洁，适合直接朗读。
7. 不输出隐藏推理过程。
8. 不依赖之前的语音对话历史。
""".strip()
