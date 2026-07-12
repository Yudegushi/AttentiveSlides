"""Deterministic fallback responses for failed API generation."""

from __future__ import annotations

from modules.common.llm_schemas import (
    ClaimEvidence,
    StructuredTutorResponse,
    TutorLLMRequest,
)


class TemplateFallback:
    """Build a validator-compatible response without an LLM."""

    def build(
        self,
        request: TutorLLMRequest,
        *,
        reason: str,
    ) -> StructuredTutorResponse:
        if request.response_mode == "break":
            return StructuredTutorResponse(
                response_mode="break",
                answer="好的，我们暂停一下。",
                decision_summary=(
                    "API generation 未产生可验证结果；"
                    "系统使用 deterministic break response。"
                ),
                claims=[],
                external_knowledge_used=False,
            )

        source = self._preferred_source(request)

        if source is None:
            return StructuredTutorResponse(
                response_mode=request.response_mode,
                answer=(
                    "当前没有足够的 slide context "
                    "支持可靠回答。"
                ),
                decision_summary=(
                    "API response 未通过验证，且没有"
                    "可用于 fallback 的 slide source。"
                ),
                claims=[
                    ClaimEvidence(
                        claim=(
                            "当前 sources 不足以支持"
                            "具体教学结论。"
                        ),
                        support="insufficient",
                    )
                ],
                external_knowledge_used=False,
                uncertainty_note=(
                    "需要更多 slide text 或已确认的 AOI。"
                ),
                active_recall_question=(
                    self._active_recall_question(
                        request
                    )
                ),
            )

        return StructuredTutorResponse(
            response_mode=request.response_mode,
            answer=(
                "基于当前可验证的 slide context，"
                f"可以确认：{source.text}"
            ),
            decision_summary=(
                "API response 未通过 parsing 或 grounding "
                f"validation；系统直接返回 source "
                f"{source.source_id} 中的内容。"
            ),
            claims=[
                ClaimEvidence(
                    claim=source.text,
                    support="direct",
                    source_ids=[
                        source.source_id
                    ],
                )
            ],
            external_knowledge_used=False,
            uncertainty_note=None,
            active_recall_question=(
                self._active_recall_question(
                    request
                )
            ),
        )

    def build_confirmation_required(
        self,
        request: TutorLLMRequest,
    ) -> StructuredTutorResponse:
        return StructuredTutorResponse(
            response_mode=request.response_mode,
            answer=(
                "我还不能确定你指的是哪个 slide 区域。"
                "请先确认目标区域，再生成针对性回答。"
            ),
            decision_summary=(
                "目标 AOI 尚未确认，因此 confirmation "
                "gate 阻止了 API generation。"
            ),
            claims=[
                ClaimEvidence(
                    claim=(
                        "当前目标区域尚未得到用户确认。"
                    ),
                    support="insufficient",
                )
            ],
            external_knowledge_used=False,
            uncertainty_note=(
                "需要用户确认 AOI 或选择候选区域。"
            ),
            active_recall_question=(
                self._active_recall_question(
                    request
                )
            ),
        )

    @staticmethod
    def _preferred_source(
        request: TutorLLMRequest,
    ):
        confirmed_sources = [
            source
            for source in request.sources
            if source.source_kind == "confirmed_aoi"
        ]

        if confirmed_sources:
            return confirmed_sources[0]

        if request.sources:
            return request.sources[0]

        return None

    @staticmethod
    def _active_recall_question(
        request: TutorLLMRequest,
    ) -> str | None:
        if request.response_mode not in {
            "quiz",
            "review",
        }:
            return None

        return (
            "根据当前已提供的 slide context，"
            "你能复述其中最核心的信息吗？"
        )
