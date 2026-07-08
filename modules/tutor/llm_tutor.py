"""LLM client abstractions and a deterministic MockLLM for tests and demos."""

from __future__ import annotations

from abc import ABC, abstractmethod

from modules.common.schemas import TutorContext, TutorResponse
from modules.tutor.prompt_template import response_mode


class LLMClient(ABC):
    @abstractmethod
    def generate(self, context: TutorContext, prompt: str) -> TutorResponse:
        raise NotImplementedError


class MockLLM(LLMClient):
    def generate(self, context: TutorContext, prompt: str) -> TutorResponse:
        del prompt
        resolved = context.resolved_query
        mode = response_mode(resolved.intent, context.adaptive_strategy)
        target_name = context.current_aoi.name if context.current_aoi and context.current_aoi.name else resolved.resolved_aoi_id
        target_name = target_name or "未确认区域"

        answer = _answer_for_mode(mode, target_name, context)
        adaptive_suggestion = _adaptive_suggestion(context.adaptive_strategy)

        return TutorResponse(
            query_id=resolved.query_id,
            response_mode=mode,
            answer=answer,
            active_recall_question=_active_recall_question(mode, context),
            adaptive_suggestion=adaptive_suggestion,
            used_context={
                "slide_id": context.slide_id,
                "aoi_id": resolved.resolved_aoi_id,
                "aoi_text": context.current_aoi_text,
            },
            safety_notes=[
                "Response is generated from provided mock slide context.",
                "Observable learning-state signals are not treated as true emotion or cognition.",
            ],
        )


def _answer_for_mode(mode: str, target_name: str, context: TutorContext) -> str:
    aoi_text = context.current_aoi_text or "当前目标区域尚未确认。"

    if mode == "summarize":
        return f"这一页主要讲 SHAP values 如何解释单个预测。核心信息是：{context.current_slide_text}"
    if mode == "quiz":
        return f"围绕 {target_name}，你可以先回答一个问题：{_active_recall_question(mode, context)}"
    if mode == "compare":
        return f"{target_name} 和相邻内容的区别在于：这里聚焦当前 AOI，邻近页强调背景或后续可视化。依据是：{context.neighbor_slide_text}"
    if mode == "simplify":
        return f"简单说，{target_name} 表示每个 feature 对最终预测的推动方向和大小。依据区域文本：{aoi_text}"
    if mode == "step_by_step":
        return f"一步一步看：第一，找到 base value；第二，看每个 feature 的 SHAP contribution；第三，把贡献相加得到最终预测。对应区域是 {target_name}：{aoi_text}"
    if mode == "review":
        return f"可以把 {target_name} 当作复习点：先确认 SHAP value 的含义，再解释正负贡献如何影响预测。依据区域文本：{aoi_text}"
    if mode == "short_recap":
        return f"简短 recap：{target_name} 说明 SHAP 将预测差异分配给各个 feature。"
    if mode == "break":
        return "可以先暂停当前讲解。等你准备好后，我可以继续用更短的 recap 或 quiz 帮你回到这一页。"
    return f"{target_name} 主要说明：{aoi_text} 它的重要性在于帮助学习者把模型输出和具体 feature contribution 联系起来。"


def _active_recall_question(mode: str, context: TutorContext) -> str:
    del mode
    if context.current_aoi and context.current_aoi.aoi_id == "bottom_formula":
        return "在公式中，base value 和 SHAP feature contributions 分别表示什么？"
    return "如果一个 feature 的 SHAP value 为正，它通常表示什么？"


def _adaptive_suggestion(strategy: str) -> str | None:
    if strategy == "ask_confirmation":
        return "我会先保持回答谨慎；你可以确认目标区域后再继续。"
    if strategy == "short_recap":
        return "我可以先给一个更短的 recap。"
    if strategy == "simpler_explanation":
        return "这个区域可能值得换一种更简单的方式解释。"
    if strategy == "review_question":
        return "这个区域可以转成一个复习问题来检查理解。"
    return None
