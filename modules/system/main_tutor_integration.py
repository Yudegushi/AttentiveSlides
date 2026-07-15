"""Bridge confirmed Main UI interactions to GroundedTutorAgent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from modules.common.interaction_contracts import (
    InteractionInput,
    interaction_input_from_dict,
)
from modules.common.schemas import (
    AOI,
    TutorContext,
)
from modules.interaction.interaction_contract_adapter import (
    InteractionResolution,
    resolve_interaction_input,
)
from modules.system.conversation_history import (
    MAX_LLM_HISTORY_TURNS,
    build_llm_interaction_history,
)
from modules.system.main_ui_state import (
    MainUISlide,
)
from modules.system.xai_view_model import (
    build_xai_view_model,
)
from modules.tutor.grounded_tutor_agent import (
    GroundedTutorAgent,
    GroundedTutorResult,
)


TutorGenerationStatus = Literal[
    "ready",
    "blocked",
]


def _linked_visual_context_text(
    slide: MainUISlide,
    aoi_id: str,
) -> str:
    for item in slide.visual_context:
        if item.linked_aoi_id != aoi_id:
            continue
        parts = []
        if item.transcription.strip():
            parts.append(
                f"Visible transcription: {item.transcription.strip()}"
            )
        if item.description.strip():
            parts.append(
                f"Visual description: {item.description.strip()}"
            )
        return "\n".join(parts)
    return ""


@dataclass(frozen=True)
class TutorGenerationAssessment:
    """Whether the current Main UI turn can call the tutor."""

    ready: bool
    status: TutorGenerationStatus
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MainTutorContextBuild:
    """Confirmed interaction converted into TutorContext."""

    interaction: InteractionInput
    resolution: InteractionResolution
    context: TutorContext
    confirmed_context: str

    def to_public_dict(self) -> dict[str, Any]:
        """Return context metadata without provider-private data."""
        return {
            "interaction_id": (
                self.interaction.interaction_id
            ),
            "deck_id": self.context.deck_id,
            "slide_id": self.context.slide_id,
            "intent": (
                self.context.resolved_query.intent
            ),
            "resolved_aoi_id": (
                self.context
                .resolved_query
                .resolved_aoi_id
            ),
            "needs_confirmation": (
                self.context
                .resolved_query
                .needs_confirmation
            ),
            "adaptive_strategy": (
                self.context.adaptive_strategy
            ),
            "confirmed_context": (
                self.confirmed_context
            ),
            "history_item_count": len(
                self.context.interaction_history
            ),
            "history_item_count": len(
                self.context
                .interaction_history
            ),
            "evidence": list(
                self.context
                .resolved_query
                .evidence
            ),
            "interaction_provenance": (
                self.resolution
                .provenance
                .to_dict()
            ),
        }


@dataclass(frozen=True)
class MainTutorGeneration:
    """Grounded result prepared for Main UI session state."""

    context_build: MainTutorContextBuild
    result: GroundedTutorResult
    public_response: dict[str, Any]
    xai_view: dict[str, Any]

    def to_session_payload(
        self,
    ) -> dict[str, Any]:
        """Return only public and sanitized information."""
        return {
            "context": (
                self.context_build
                .to_public_dict()
            ),
            "tutor": self.public_response,
            "xai": self.xai_view,
        }


def retryable_generation_error_message(
    result: GroundedTutorResult,
) -> str:
    """Describe the final exhausted provider/parse/validation failure."""
    detail = "No generation attempt returned a usable response."

    if result.attempts:
        final_attempt = result.attempts[-1]

        if final_attempt.provider_error:
            error = final_attempt.provider_error
            detail = (
                f"{error.get('type', 'ProviderError')}: "
                f"{error.get('message', 'provider request failed')}"
            )
        elif final_attempt.parse_error:
            error = final_attempt.parse_error
            detail = (
                f"{error.get('code', 'parse_error')}: "
                f"{error.get('message', 'response parsing failed')}"
            )
        elif final_attempt.validation:
            errors = [
                item
                for item in final_attempt.validation.get(
                    "issues",
                    [],
                )
                if isinstance(item, Mapping)
                and item.get("severity") == "error"
            ]
            messages = [
                (
                    f"{item.get('code', 'validation_error')}: "
                    f"{item.get('message', 'response validation failed')}"
                )
                for item in errors
            ]
            detail = (
                "; ".join(messages)
                or "Response validation failed."
            )

    return (
        "Tutor generation exhausted all attempts; retry is safe. "
        f"Final failure: {detail}"
    )


def assess_tutor_generation(
    confirmed_interaction: (
        Mapping[str, Any] | None
    ),
    *,
    cloud_text_allowed: bool,
    api_configured: bool,
) -> TutorGenerationAssessment:
    """Assess all gates before an external API request."""
    if confirmed_interaction is None:
        return TutorGenerationAssessment(
            ready=False,
            status="blocked",
            code="confirmation_missing",
            message=(
                "Confirm the target and intent "
                "before generating an answer."
            ),
        )

    try:
        interaction = (
            parse_confirmed_interaction(
                confirmed_interaction
            )
        )
    except Exception as exc:
        return TutorGenerationAssessment(
            ready=False,
            status="blocked",
            code="invalid_confirmation_payload",
            message=(
                "The confirmed interaction is invalid: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    if not interaction.confirmation.confirmed:
        return TutorGenerationAssessment(
            ready=False,
            status="blocked",
            code="confirmation_missing",
            message=(
                "The current interaction has not "
                "been explicitly confirmed."
            ),
        )

    if not cloud_text_allowed:
        return TutorGenerationAssessment(
            ready=False,
            status="blocked",
            code="cloud_permission_required",
            message=(
                "Cloud tutor permission is disabled. "
                "Enable permission before sending "
                "selected slide text."
            ),
        )

    if not api_configured:
        return TutorGenerationAssessment(
            ready=False,
            status="blocked",
            code="api_not_configured",
            message=(
                "DASHSCOPE_API_KEY is not configured "
                "in the current process."
            ),
        )

    return TutorGenerationAssessment(
        ready=True,
        status="ready",
        code="ready",
        message=(
            "The confirmed interaction is ready "
            "for grounded TutorAgent generation."
        ),
    )


def parse_confirmed_interaction(
    confirmed_interaction: Mapping[str, Any],
) -> InteractionInput:
    """Deserialize either a wrapper or a raw InteractionInput."""
    if not isinstance(
        confirmed_interaction,
        Mapping,
    ):
        raise TypeError(
            "confirmed_interaction must be a mapping."
        )

    raw_interaction = (
        confirmed_interaction.get(
            "interaction"
        )
        if "interaction"
        in confirmed_interaction
        else confirmed_interaction
    )

    if not isinstance(
        raw_interaction,
        Mapping,
    ):
        raise ValueError(
            "Confirmed interaction payload does not "
            "contain an interaction object."
        )

    return interaction_input_from_dict(
        dict(raw_interaction)
    )


def build_main_tutor_context(
    confirmed_interaction: Mapping[str, Any],
    *,
    slide: MainUISlide,
    conversation_turns: Sequence[
        Mapping[str, Any]
    ] = (),
    history_max_items: int = (
        MAX_LLM_HISTORY_TURNS
    ),
) -> MainTutorContextBuild:
    """Build TutorContext from one confirmed manual turn."""
    interaction = parse_confirmed_interaction(
        confirmed_interaction
    )

    if not interaction.confirmation.confirmed:
        raise ValueError(
            "TutorContext requires an explicitly "
            "confirmed InteractionInput."
        )

    if interaction.slide_id != slide.slide_id:
        raise ValueError(
            "Confirmed interaction slide_id does not "
            "match the active Main UI slide."
        )

    aois = ensure_whole_slide_aoi(
        slide.aois,
        slide_text=slide.slide_text,
    )

    resolution = resolve_interaction_input(
        interaction,
        aois=aois,
    )

    resolved_query = (
        resolution.resolved_query
    )

    if resolved_query.needs_confirmation:
        raise ValueError(
            "ResolvedQuery is still awaiting "
            "confirmation."
        )

    resolved_aoi_id = (
        resolved_query.resolved_aoi_id
    )

    current_aoi = next(
        (
            aoi
            for aoi in aois
            if aoi.aoi_id
            == resolved_aoi_id
        ),
        None,
    )

    if current_aoi is None:
        raise ValueError(
            "The confirmed AOI is not available "
            "on the active slide."
        )

    wrapper_context = str(
        confirmed_interaction.get(
            "confirmed_context",
            "",
        )
    ).strip()

    metadata_context = str(
        interaction.metadata.get(
            "confirmed_context",
            "",
        )
    ).strip()

    confirmed_context = (
        wrapper_context
        or metadata_context
        or current_aoi.text.strip()
        or _linked_visual_context_text(
            slide,
            current_aoi.aoi_id,
        )
        or slide.slide_text.strip()
    )

    if not confirmed_context:
        raise ValueError(
            "The confirmed target contains no "
            "usable text context."
        )

    history_items = build_llm_interaction_history(
        conversation_turns,
        deck_id=interaction.deck_id,
        exclude_interaction_id=(
            interaction.interaction_id
        ),
        max_items=history_max_items,
    )

    context = TutorContext(
        deck_id=interaction.deck_id,
        slide_id=interaction.slide_id,
        current_slide_text=(
            slide.slide_text
        ),
        current_aoi=current_aoi,
        current_aoi_text=(
            confirmed_context
        ),
        neighbor_slide_text=(
            slide.neighbor_slide_text
        ),
        resolved_query=resolved_query,
        interaction_history=history_items,
        adaptive_strategy=(
            resolved_query.adaptive_strategy
        ),
        visual_context=list(
            slide.visual_context
        ),
    )

    return MainTutorContextBuild(
        interaction=interaction,
        resolution=resolution,
        context=context,
        confirmed_context=(
            confirmed_context
        ),
    )


def generate_main_tutor_response(
    confirmed_interaction: Mapping[str, Any],
    *,
    slide: MainUISlide,
    agent: GroundedTutorAgent,
    cloud_text_allowed: bool,
    api_configured: bool,
    conversation_turns: Sequence[
        Mapping[str, Any]
    ] = (),
    history_max_items: int = (
        MAX_LLM_HISTORY_TURNS
    ),
) -> MainTutorGeneration:
    """Run the grounded agent after all gates pass."""
    assessment = assess_tutor_generation(
        confirmed_interaction,
        cloud_text_allowed=(
            cloud_text_allowed
        ),
        api_configured=api_configured,
    )

    if not assessment.ready:
        raise PermissionError(
            f"{assessment.code}: "
            f"{assessment.message}"
        )

    context_build = (
        build_main_tutor_context(
            confirmed_interaction,
            slide=slide,
            conversation_turns=(
                conversation_turns
            ),
            history_max_items=(
                history_max_items
            ),
        )
    )

    result = agent.answer_context(
        context_build.context
    )

    if result.status == "fallback":
        raise RuntimeError(
            retryable_generation_error_message(
                result
            )
        )

    if result.status == "confirmation_required":
        raise RuntimeError(
            "TutorAgent returned confirmation_required "
            "for an explicitly confirmed interaction."
        )

    xai_view = build_xai_view_model(
        result
    )

    response = result.call_result.response
    usage = result.call_result.usage

    public_response = {
        "status": result.status,
        "query_id": result.request.query_id,
        "response_mode": (
            response.response_mode
        ),
        "answer": response.answer,
        "active_recall_question": (
            response
            .active_recall_question
        ),
        "uncertainty_note": (
            response.uncertainty_note
        ),
        "decision_summary": (
            response.decision_summary
        ),
        "external_knowledge_used": (
            response
            .external_knowledge_used
        ),
        "confirmed_aoi_id": (
            result.request
            .confirmed_aoi_id
        ),
        "validation_is_valid": (
            result.validation.is_valid
        ),
        "provider": (
            result.call_result.provider
        ),
        "model": result.call_result.model,
        "latency_ms": round(
            result.call_result.latency_ms,
            2,
        ),
        "retry_count": (
            result.call_result.retry_count
        ),
        "fallback_used": (
            result.call_result.fallback_used
        ),
        "prompt_tokens": (
            usage.prompt_tokens
            if usage is not None
            else None
        ),
        "completion_tokens": (
            usage.completion_tokens
            if usage is not None
            else None
        ),
        "total_tokens": (
            usage.total_tokens
            if usage is not None
            else None
        ),
    }

    return MainTutorGeneration(
        context_build=context_build,
        result=result,
        public_response=(
            public_response
        ),
        xai_view=xai_view,
    )


def ensure_whole_slide_aoi(
    aois: Sequence[AOI],
    *,
    slide_text: str,
) -> list[AOI]:
    """Ensure whole-slide confirmation has a valid AOI."""
    result: list[AOI] = []
    whole_slide_found = False

    for aoi in aois:
        if aoi.aoi_id != "whole_slide":
            result.append(aoi)
            continue

        whole_slide_found = True

        if aoi.text.strip():
            result.append(aoi)
        else:
            result.append(
                AOI(
                    aoi_id="whole_slide",
                    bbox=[
                        0.0,
                        0.0,
                        1.0,
                        1.0,
                    ],
                    type="whole_slide",
                    text=slide_text,
                    name=(
                        aoi.name
                        or "Whole slide"
                    ),
                )
            )

    if not whole_slide_found:
        result.append(
            AOI(
                aoi_id="whole_slide",
                bbox=[
                    0.0,
                    0.0,
                    1.0,
                    1.0,
                ],
                type="whole_slide",
                text=slide_text,
                name="Whole slide",
            )
        )

    return result
