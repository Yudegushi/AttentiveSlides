"""Adapt legacy TutorContext into an API TutorLLMRequest."""

from __future__ import annotations

import re

from modules.common.llm_schemas import (
    ContextSource,
    TutorLLMRequest,
)
from modules.common.schemas import TutorContext
from modules.tutor.prompt_template import response_mode


class TutorRequestAdapter:
    """Create grounded API requests from existing tutor context."""

    def __init__(
        self,
        *,
        allow_external_knowledge: bool = True,
        response_language: str = "en",
    ) -> None:
        self.allow_external_knowledge = (
            allow_external_knowledge
        )
        self.response_language = response_language

    def from_context(
        self,
        context: TutorContext,
    ) -> TutorLLMRequest:
        if not isinstance(context, TutorContext):
            raise TypeError(
                "context must be a TutorContext."
            )

        resolved = context.resolved_query

        mode = response_mode(
            resolved.intent,
            context.adaptive_strategy,
        )

        sources = self._build_sources(context)

        confirmed_aoi_id = self._confirmed_aoi_id(
            context
        )

        question = (
            resolved.transcript.strip()
            or "Continue the explanation using the current slide context."
        )

        return TutorLLMRequest(
            query_id=resolved.query_id,
            deck_id=context.deck_id,
            slide_id=context.slide_id,
            question=question,
            intent=resolved.intent,
            response_mode=mode,
            sources=sources,
            confirmed_aoi_id=confirmed_aoi_id,
            adaptive_strategy=(
                context.adaptive_strategy
            ),
            interaction_history=list(
                context.interaction_history
            ),
            allow_external_knowledge=(
                self.allow_external_knowledge
            ),
            response_language=(
                self.response_language
            ),
        )

    def _build_sources(
        self,
        context: TutorContext,
    ) -> list[ContextSource]:
        sources: list[ContextSource] = []

        current_aoi = context.current_aoi
        resolved = context.resolved_query

        confirmed_aoi_id = self._confirmed_aoi_id(
            context
        )

        if (
            current_aoi is not None
            and context.current_aoi_text.strip()
        ):
            is_confirmed = (
                confirmed_aoi_id
                == current_aoi.aoi_id
            )

            sources.append(
                ContextSource(
                    source_id=self._aoi_source_id(
                        context.slide_id,
                        current_aoi.aoi_id,
                    ),
                    slide_id=context.slide_id,
                    source_kind=(
                        "confirmed_aoi"
                        if is_confirmed
                        else "current_slide"
                    ),
                    text=context.current_aoi_text,
                    aoi_id=current_aoi.aoi_id,
                    title=(
                        current_aoi.name
                        or current_aoi.aoi_id
                    ),
                    metadata={
                        "aoi_type": current_aoi.type,
                        "bbox": current_aoi.bbox,
                        "target_confidence": (
                            resolved.target_confidence
                        ),
                        "confirmed": is_confirmed,
                    },
                )
            )

        if context.current_slide_text.strip():
            sources.append(
                ContextSource(
                    source_id=(
                        f"slide_{context.slide_id:03d}"
                        "_full_text"
                    ),
                    slide_id=context.slide_id,
                    source_kind="current_slide",
                    text=context.current_slide_text,
                    title="Current slide text",
                    metadata={
                        "provenance": "slide_text",
                    },
                )
            )

        for index, item in enumerate(
            context.visual_context,
            start=1,
        ):
            text_parts = [
                f"Description: {item.description.strip()}"
            ]
            if item.transcription.strip():
                text_parts.append(
                    "Visible transcription: "
                    f"{item.transcription.strip()}"
                )
            sources.append(ContextSource(
                source_id=(
                    f"slide_{context.slide_id:03d}"
                    f"_visual_{index:02d}"
                ),
                slide_id=context.slide_id,
                source_kind="visual_observation",
                text="\n".join(text_parts),
                aoi_id=item.linked_aoi_id,
                title=f"Visual observation {index}",
                metadata={
                    "visual_type": item.type,
                    "bbox": list(item.bbox),
                    "confidence": item.confidence,
                    "provenance": item.provenance,
                },
            ))

        if context.neighbor_slide_text.strip():
            sources.append(
                ContextSource(
                    source_id=(
                        f"slide_{context.slide_id:03d}"
                        "_neighbor_context"
                    ),
                    slide_id=context.slide_id,
                    source_kind="neighbor_slide",
                    text=context.neighbor_slide_text,
                    title="Neighbor slide context",
                    metadata={
                        "provenance": (
                            "neighbor_slide_text"
                        ),
                    },
                )
            )

        return sources

    @staticmethod
    def _confirmed_aoi_id(
        context: TutorContext,
    ) -> str | None:
        resolved = context.resolved_query

        if resolved.needs_confirmation:
            return None

        if (
            context.current_aoi is None
            or resolved.resolved_aoi_id is None
        ):
            return None

        if (
            context.current_aoi.aoi_id
            != resolved.resolved_aoi_id
        ):
            return None

        return context.current_aoi.aoi_id

    @staticmethod
    def _aoi_source_id(
        slide_id: int,
        aoi_id: str,
    ) -> str:
        normalized = re.sub(
            r"[^a-zA-Z0-9_-]+",
            "_",
            aoi_id.strip(),
        ).strip("_")

        if normalized.startswith("aoi_"):
            normalized = normalized[4:]

        normalized = normalized or "unknown"

        return (
            f"slide_{slide_id:03d}"
            f"_aoi_{normalized}"
        )
