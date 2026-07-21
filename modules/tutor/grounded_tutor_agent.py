"""Grounded TutorAgent with API, retry, validation, and fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from modules.common.llm_schemas import (
    LLMCallResult,
    LLMUsage,
    TutorLLMRequest,
)
from modules.common.schemas import (
    ResolvedQuery,
    TutorContext,
    TutorResponse,
)
from modules.interaction.interaction_history import (
    InteractionHistory,
)
from modules.tutor.api_llm_client import (
    OpenAICompatibleLLMClient,
    RawLLMResponse,
)
from modules.tutor.context_retriever import (
    ContextRetriever,
    MockDeckStore,
)
from modules.tutor.grounded_prompt import (
    GroundedPrompt,
    GroundedPromptBuilder,
)
from modules.tutor.grounding_validator import (
    GroundingValidationResult,
    GroundingValidator,
)
from modules.tutor.response_parser import (
    ResponseParseError,
    StructuredResponseParser,
)
from modules.tutor.template_fallback import (
    TemplateFallback,
)
from modules.tutor.tutor_request_adapter import (
    TutorRequestAdapter,
)


TutorAgentStatus = Literal[
    "success",
    "fallback",
    "confirmation_required",
]


class GroundedLLMClient(Protocol):
    provider: str
    model: str

    def generate(
        self,
        messages: list[dict[str, str]],
    ) -> RawLLMResponse:
        ...


@dataclass(frozen=True)
class LLMAttemptRecord:
    """One API generation attempt and its validation outcome."""

    attempt_number: int
    provider: str
    model: str

    latency_ms: float = 0.0
    request_id: str | None = None
    raw_response: str | None = None
    parse_warnings: tuple[str, ...] = ()
    parse_error: dict[str, str] | None = None
    validation: dict[str, Any] | None = None
    provider_error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GroundedTutorResult:
    """Complete result for UI, logging, evaluation, and legacy use."""

    status: TutorAgentStatus
    request: TutorLLMRequest
    call_result: LLMCallResult
    validation: GroundingValidationResult
    attempts: tuple[LLMAttemptRecord, ...]
    prompt_character_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "request": self.request.to_dict(),
            "call_result": (
                self.call_result.to_dict()
            ),
            "validation": (
                self.validation.to_dict()
            ),
            "attempts": [
                attempt.to_dict()
                for attempt in self.attempts
            ],
            "prompt_character_count": (
                self.prompt_character_count
            ),
        }

    def to_legacy_response(
        self,
    ) -> TutorResponse:
        """Convert the grounded result for the existing pipeline."""
        response = self.call_result.response

        return TutorResponse(
            query_id=self.request.query_id,
            response_mode=response.response_mode,
            answer=response.answer,
            active_recall_question=(
                response.active_recall_question
            ),
            adaptive_suggestion=(
                _adaptive_suggestion(
                    self.request.adaptive_strategy
                )
            ),
            used_context={
                "slide_id": self.request.slide_id,
                "confirmed_aoi_id": (
                    self.request.confirmed_aoi_id
                ),
                "source_ids": sorted(
                    self.request.source_ids()
                ),
                "cited_source_ids": sorted(
                    response.cited_source_ids()
                ),
                "claims": [
                    claim.to_dict()
                    for claim in response.claims
                ],
                "decision_summary": (
                    response.decision_summary
                ),
                "external_knowledge_used": (
                    response
                    .external_knowledge_used
                ),
                "uncertainty_note": (
                    response.uncertainty_note
                ),
                "provider": (
                    self.call_result.provider
                ),
                "model": self.call_result.model,
                "latency_ms": (
                    self.call_result.latency_ms
                ),
                "retry_count": (
                    self.call_result.retry_count
                ),
                "fallback_used": (
                    self.call_result.fallback_used
                ),
                "validation": (
                    self.validation.to_dict()
                ),
            },
            safety_notes=[
                (
                    "Response was checked against supplied "
                    "slide source IDs."
                ),
                (
                    "Observable signals are not treated as "
                    "true emotion, cognition, or attention."
                ),
                (
                    "Raw Chain-of-Thought is not exposed."
                ),
            ],
        )


class GroundedTutorAgent:
    """Orchestrate grounded API generation for AttentiveSlides."""

    def __init__(
        self,
        *,
        context_retriever: ContextRetriever | None = None,
        llm_client: GroundedLLMClient | None = None,
        request_adapter: TutorRequestAdapter | None = None,
        prompt_builder: GroundedPromptBuilder | None = None,
        parser: StructuredResponseParser | None = None,
        validator: GroundingValidator | None = None,
        fallback: TemplateFallback | None = None,
        max_retries: int = 1,
    ) -> None:
        if max_retries < 0:
            raise ValueError(
                "max_retries must be non-negative."
            )

        self.context_retriever = (
            context_retriever
            or ContextRetriever()
        )

        self.llm_client = (
            llm_client
            or OpenAICompatibleLLMClient.from_env()
        )

        self.request_adapter = (
            request_adapter
            or TutorRequestAdapter()
        )

        self.prompt_builder = (
            prompt_builder
            or GroundedPromptBuilder()
        )

        self.parser = (
            parser
            or StructuredResponseParser()
        )

        self.validator = (
            validator
            or GroundingValidator()
        )

        self.fallback = (
            fallback
            or TemplateFallback()
        )

        self.max_retries = max_retries

    def answer(
        self,
        resolved_query: ResolvedQuery,
        deck_state: MockDeckStore | None = None,
        history: InteractionHistory | None = None,
    ) -> GroundedTutorResult:
        retriever = self.context_retriever

        if deck_state is not None:
            retriever = ContextRetriever(
                deck_state
            )

        context = retriever.retrieve_context(
            resolved_query,
            history,
        )

        return self.answer_context(context)

    def answer_context(
        self,
        context: TutorContext,
    ) -> GroundedTutorResult:
        request = self.request_adapter.from_context(
            context
        )

        prompt = self.prompt_builder.build(
            request
        )

        if context.resolved_query.needs_confirmation:
            return self._confirmation_result(
                request,
                prompt,
            )

        return self._generate_validated(
            request,
            prompt,
        )

    def _generate_validated(
        self,
        request: TutorLLMRequest,
        prompt: GroundedPrompt,
    ) -> GroundedTutorResult:
        attempts: list[LLMAttemptRecord] = []
        usages: list[LLMUsage] = []
        total_latency_ms = 0.0
        messages = prompt.messages()

        final_raw: RawLLMResponse | None = None
        failure_reasons: list[str] = []

        total_attempts = self.max_retries + 1

        for attempt_index in range(total_attempts):
            attempt_number = attempt_index + 1

            try:
                raw = self.llm_client.generate(
                    messages
                )
            except Exception as exc:
                failure_reasons.append(
                    f"provider_error:{type(exc).__name__}"
                )

                attempts.append(
                    LLMAttemptRecord(
                        attempt_number=attempt_number,
                        provider=getattr(
                            self.llm_client,
                            "provider",
                            "unknown",
                        ),
                        model=getattr(
                            self.llm_client,
                            "model",
                            "unknown",
                        ),
                        provider_error={
                            "type": type(exc).__name__,
                            "message": str(exc),
                        },
                    )
                )

                continue

            final_raw = raw
            total_latency_ms += raw.latency_ms

            if raw.usage is not None:
                usages.append(raw.usage)

            try:
                parse_result = self.parser.parse(
                    raw.raw_text
                )
            except ResponseParseError as exc:
                failure_reasons.append(
                    f"parse_error:{exc.code}"
                )

                attempts.append(
                    LLMAttemptRecord(
                        attempt_number=attempt_number,
                        provider=raw.provider,
                        model=raw.model,
                        latency_ms=raw.latency_ms,
                        request_id=raw.request_id,
                        raw_response=raw.raw_text,
                        parse_error={
                            "code": exc.code,
                            "message": exc.message,
                        },
                    )
                )

                if attempt_index < self.max_retries:
                    messages = self._repair_messages(
                        prompt=prompt,
                        raw_response=raw.raw_text,
                        issues=[
                            (
                                f"Parser error {exc.code}: "
                                f"{exc.message}"
                            )
                        ],
                    )

                continue

            validation = self.validator.validate(
                request,
                parse_result.response,
            )

            attempts.append(
                LLMAttemptRecord(
                    attempt_number=attempt_number,
                    provider=raw.provider,
                    model=raw.model,
                    latency_ms=raw.latency_ms,
                    request_id=raw.request_id,
                    raw_response=raw.raw_text,
                    parse_warnings=(
                        parse_result.warnings
                    ),
                    validation=(
                        validation.to_dict()
                    ),
                )
            )

            if validation.is_valid:
                return GroundedTutorResult(
                    status="success",
                    request=request,
                    call_result=LLMCallResult(
                        query_id=request.query_id,
                        provider=raw.provider,
                        model=raw.model,
                        latency_ms=(
                            total_latency_ms
                        ),
                        response=(
                            parse_result.response
                        ),
                        usage=_combine_usage(
                            usages
                        ),
                        provider_request_id=(
                            raw.request_id
                        ),
                        retry_count=attempt_index,
                        fallback_used=False,
                    ),
                    validation=validation,
                    attempts=tuple(attempts),
                    prompt_character_count=(
                        prompt.character_count()
                    ),
                )

            error_codes = [
                issue.code
                for issue in validation.errors
            ]

            failure_reasons.extend(
                f"validation_error:{code}"
                for code in error_codes
            )

            if attempt_index < self.max_retries:
                messages = self._repair_messages(
                    prompt=prompt,
                    raw_response=raw.raw_text,
                    issues=[
                        (
                            f"{issue.code}: "
                            f"{issue.message}"
                        )
                        for issue in validation.errors
                    ],
                )

        return self._fallback_result(
            request=request,
            prompt=prompt,
            attempts=attempts,
            usages=usages,
            total_latency_ms=total_latency_ms,
            final_raw=final_raw,
            failure_reasons=failure_reasons,
        )

    def _fallback_result(
        self,
        *,
        request: TutorLLMRequest,
        prompt: GroundedPrompt,
        attempts: list[LLMAttemptRecord],
        usages: list[LLMUsage],
        total_latency_ms: float,
        final_raw: RawLLMResponse | None,
        failure_reasons: list[str],
    ) -> GroundedTutorResult:
        response = self.fallback.build(
            request,
            reason="; ".join(failure_reasons),
        )

        validation = self.validator.validate(
            request,
            response,
        )

        validation.require_valid()

        return GroundedTutorResult(
            status="fallback",
            request=request,
            call_result=LLMCallResult(
                query_id=request.query_id,
                provider=(
                    final_raw.provider
                    if final_raw
                    else getattr(
                        self.llm_client,
                        "provider",
                        "unknown",
                    )
                ),
                model=(
                    final_raw.model
                    if final_raw
                    else getattr(
                        self.llm_client,
                        "model",
                        "unknown",
                    )
                ),
                latency_ms=total_latency_ms,
                response=response,
                usage=_combine_usage(usages),
                provider_request_id=(
                    final_raw.request_id
                    if final_raw
                    else None
                ),
                retry_count=max(
                    0,
                    len(attempts) - 1,
                ),
                fallback_used=True,
            ),
            validation=validation,
            attempts=tuple(attempts),
            prompt_character_count=(
                prompt.character_count()
            ),
        )

    def _confirmation_result(
        self,
        request: TutorLLMRequest,
        prompt: GroundedPrompt,
    ) -> GroundedTutorResult:
        response = (
            self.fallback
            .build_confirmation_required(request)
        )

        validation = self.validator.validate(
            request,
            response,
        )

        validation.require_valid()

        return GroundedTutorResult(
            status="confirmation_required",
            request=request,
            call_result=LLMCallResult(
                query_id=request.query_id,
                provider="local_policy",
                model="confirmation_gate",
                latency_ms=0.0,
                response=response,
                usage=None,
                retry_count=0,
                fallback_used=True,
            ),
            validation=validation,
            attempts=(),
            prompt_character_count=(
                prompt.character_count()
            ),
        )

    @staticmethod
    def _repair_messages(
        *,
        prompt: GroundedPrompt,
        raw_response: str,
        issues: list[str],
    ) -> list[dict[str, str]]:
        issue_text = "\n".join(
            f"- {issue}"
            for issue in issues
        )

        clipped_response = raw_response[:8000]

        return [
            *prompt.messages(),
            {
                "role": "assistant",
                "content": clipped_response,
            },
            {
                "role": "user",
                "content": (
                    "The previous JSON response failed "
                    "deterministic validation.\n\n"
                    f"ISSUES\n{issue_text}\n\n"
                    "Return a corrected JSON object only. "
                    "Use exactly these top-level keys: "
                    "response_mode, answer, "
                    "decision_summary, claims, "
                    "uncertainty_note, and "
                    "active_recall_question. "
                    "Do not add a rules or metadata field. "
                    "Do not explain the correction."
                ),
            },
        ]


def _combine_usage(
    usages: list[LLMUsage],
) -> LLMUsage | None:
    if not usages:
        return None

    cached_values = [
        usage.cached_prompt_tokens
        for usage in usages
        if usage.cached_prompt_tokens is not None
    ]

    return LLMUsage(
        prompt_tokens=sum(
            usage.prompt_tokens
            for usage in usages
        ),
        completion_tokens=sum(
            usage.completion_tokens
            for usage in usages
        ),
        total_tokens=sum(
            usage.total_tokens
            for usage in usages
        ),
        cached_prompt_tokens=(
            sum(cached_values)
            if cached_values
            else None
        ),
    )


def _adaptive_suggestion(
    strategy: str,
) -> str | None:
    suggestions = {
        "ask_confirmation": (
            "请先确认目标区域。"
        ),
        "short_recap": (
            "当前回答采用 short recap。"
        ),
        "simpler_explanation": (
            "当前回答采用更简单的表达。"
        ),
        "step_by_step": (
            "当前回答采用 step-by-step 结构。"
        ),
        "review_question": (
            "当前回答包含 review question。"
        ),
    }

    return suggestions.get(strategy)
