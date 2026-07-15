"""Typed contracts for API-backed, slide-grounded tutor generation.

These schemas are intentionally separate from the existing mock-pipeline
schemas. They describe:

1. Evidence supplied to an LLM.
2. The complete tutor-generation request.
3. Structured claims returned by an LLM.
4. Provider usage and call metadata.

They do not perform prompt construction, API calls, response parsing,
or semantic grounding validation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from modules.common.schemas import AdaptiveStrategy, IntentName


SourceKind = Literal[
    "confirmed_aoi",
    "current_slide",
    "visual_observation",
    "neighbor_slide",
    "interaction_history",
]

ClaimSupport = Literal[
    "direct",
    "external",
    "insufficient",
]

TutorResponseMode = Literal[
    "explain",
    "compare",
    "quiz",
    "summarize",
    "simplify",
    "step_by_step",
    "review",
    "break",
    "short_recap",
    "unknown",
]


_ALLOWED_SOURCE_KINDS = {
    "confirmed_aoi",
    "current_slide",
    "visual_observation",
    "neighbor_slide",
    "interaction_history",
}

_ALLOWED_CLAIM_SUPPORT = {
    "direct",
    "external",
    "insufficient",
}

_ALLOWED_RESPONSE_MODES = {
    "explain",
    "compare",
    "quiz",
    "summarize",
    "simplify",
    "step_by_step",
    "review",
    "break",
    "short_recap",
    "unknown",
}


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only identifiers and text fields."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


@dataclass(frozen=True)
class ContextSource:
    """One traceable piece of evidence supplied to the tutor LLM.

    source_id:
        Stable identifier used by generated claims and XAI displays.

    source_kind:
        The source's role in the current interaction.

    text:
        Exact textual evidence available to the LLM.

    aoi_id:
        AOI identifier when the source comes from a slide region.
    """

    source_id: str
    slide_id: int
    source_kind: SourceKind
    text: str
    aoi_id: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_blank(self.source_id, "source_id")
        _require_non_blank(self.text, "text")

        if not isinstance(self.slide_id, int) or self.slide_id < 0:
            raise ValueError("slide_id must be a non-negative integer.")

        if self.source_kind not in _ALLOWED_SOURCE_KINDS:
            raise ValueError(
                f"Unsupported source_kind: {self.source_kind!r}."
            )

        if (
            self.source_kind == "confirmed_aoi"
            and not self.aoi_id
        ):
            raise ValueError(
                "A confirmed_aoi source must include aoi_id."
            )

        if self.aoi_id is not None:
            _require_non_blank(self.aoi_id, "aoi_id")

        if self.title is not None:
            _require_non_blank(self.title, "title")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TutorLLMRequest:
    """Complete input contract for one tutor-generation call.

    This object is created only after interaction resolution. It contains
    task intent, confirmation state, and all evidence made available to
    the API model.
    """

    query_id: str
    deck_id: str
    slide_id: int
    question: str
    intent: IntentName
    response_mode: TutorResponseMode
    sources: list[ContextSource]

    confirmed_aoi_id: str | None = None
    adaptive_strategy: AdaptiveStrategy = "normal"
    interaction_history: list[dict[str, Any]] = field(default_factory=list)

    allow_external_knowledge: bool = False
    response_language: str = "zh-CN"
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _require_non_blank(self.query_id, "query_id")
        _require_non_blank(self.deck_id, "deck_id")
        _require_non_blank(self.question, "question")
        _require_non_blank(
            self.response_language,
            "response_language",
        )
        _require_non_blank(self.schema_version, "schema_version")

        if not isinstance(self.slide_id, int) or self.slide_id < 0:
            raise ValueError("slide_id must be a non-negative integer.")

        if self.response_mode not in _ALLOWED_RESPONSE_MODES:
            raise ValueError(
                f"Unsupported response_mode: {self.response_mode!r}."
            )

        if any(
            not isinstance(source, ContextSource)
            for source in self.sources
        ):
            raise TypeError(
                "Every item in sources must be a ContextSource."
            )

        source_ids = [
            source.source_id
            for source in self.sources
        ]

        if len(source_ids) != len(set(source_ids)):
            raise ValueError(
                "Context source IDs must be unique within one request."
            )

        if self.confirmed_aoi_id is not None:
            _require_non_blank(
                self.confirmed_aoi_id,
                "confirmed_aoi_id",
            )

            has_confirmed_source = any(
                source.aoi_id == self.confirmed_aoi_id
                for source in self.sources
            )

            if not has_confirmed_source:
                raise ValueError(
                    "confirmed_aoi_id must match at least one "
                    "ContextSource.aoi_id."
                )

    def source_ids(self) -> set[str]:
        return {
            source.source_id
            for source in self.sources
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaimEvidence:
    """One factual or epistemic claim in a structured tutor response.

    direct:
        The claim is explicitly supported by supplied slide sources.

    external:
        The claim uses knowledge outside the supplied slide sources.

    insufficient:
        The available evidence is insufficient to support a conclusion.
    """

    claim: str
    support: ClaimSupport
    source_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_non_blank(self.claim, "claim")

        if self.support not in _ALLOWED_CLAIM_SUPPORT:
            raise ValueError(
                f"Unsupported claim support: {self.support!r}."
            )

        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError(
                "A claim cannot contain duplicate source IDs."
            )

        for source_id in self.source_ids:
            _require_non_blank(source_id, "source_id")

        if self.support == "direct" and not self.source_ids:
            raise ValueError(
                "A direct claim must cite at least one source ID."
            )

        if self.support != "direct" and self.source_ids:
            raise ValueError(
                "Only direct claims may cite slide-context source IDs."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuredTutorResponse:
    """Validated semantic structure expected from the tutor LLM.

    Parsing the raw API text into this object is handled in a later stage.
    """

    response_mode: TutorResponseMode
    answer: str
    decision_summary: str
    claims: list[ClaimEvidence]
    external_knowledge_used: bool

    uncertainty_note: str | None = None
    active_recall_question: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.answer, "answer")
        _require_non_blank(
            self.decision_summary,
            "decision_summary",
        )

        if self.response_mode not in _ALLOWED_RESPONSE_MODES:
            raise ValueError(
                f"Unsupported response_mode: {self.response_mode!r}."
            )

        if any(
            not isinstance(claim, ClaimEvidence)
            for claim in self.claims
        ):
            raise TypeError(
                "Every item in claims must be a ClaimEvidence."
            )

        has_external_claim = any(
            claim.support == "external"
            for claim in self.claims
        )

        if self.external_knowledge_used != has_external_claim:
            raise ValueError(
                "external_knowledge_used must match the presence "
                "of external claims."
            )

        has_insufficient_claim = any(
            claim.support == "insufficient"
            for claim in self.claims
        )

        if has_insufficient_claim:
            if (
                self.uncertainty_note is None
                or not self.uncertainty_note.strip()
            ):
                raise ValueError(
                    "An insufficient claim requires uncertainty_note."
                )

        if self.uncertainty_note is not None:
            _require_non_blank(
                self.uncertainty_note,
                "uncertainty_note",
            )

        if self.active_recall_question is not None:
            _require_non_blank(
                self.active_recall_question,
                "active_recall_question",
            )

    def cited_source_ids(self) -> set[str]:
        return {
            source_id
            for claim in self.claims
            for source_id in claim.source_ids
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMUsage:
    """Token usage returned by an API provider."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_prompt_tokens: int | None = None

    def __post_init__(self) -> None:
        values = {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

        for name, value in values.items():
            if not isinstance(value, int) or value < 0:
                raise ValueError(
                    f"{name} must be a non-negative integer."
                )

        minimum_total = (
            self.prompt_tokens
            + self.completion_tokens
        )

        if self.total_tokens < minimum_total:
            raise ValueError(
                "total_tokens cannot be smaller than "
                "prompt_tokens + completion_tokens."
            )

        if self.cached_prompt_tokens is not None:
            if (
                not isinstance(self.cached_prompt_tokens, int)
                or self.cached_prompt_tokens < 0
            ):
                raise ValueError(
                    "cached_prompt_tokens must be a "
                    "non-negative integer."
                )

            if self.cached_prompt_tokens > self.prompt_tokens:
                raise ValueError(
                    "cached_prompt_tokens cannot exceed prompt_tokens."
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMCallResult:
    """Provider metadata plus the structured semantic response."""

    query_id: str
    provider: str
    model: str
    latency_ms: float
    response: StructuredTutorResponse

    usage: LLMUsage | None = None
    provider_request_id: str | None = None
    retry_count: int = 0
    fallback_used: bool = False

    def __post_init__(self) -> None:
        _require_non_blank(self.query_id, "query_id")
        _require_non_blank(self.provider, "provider")
        _require_non_blank(self.model, "model")

        if self.latency_ms < 0:
            raise ValueError(
                "latency_ms must be non-negative."
            )

        if not isinstance(
            self.response,
            StructuredTutorResponse,
        ):
            raise TypeError(
                "response must be a StructuredTutorResponse."
            )

        if self.usage is not None and not isinstance(
            self.usage,
            LLMUsage,
        ):
            raise TypeError(
                "usage must be LLMUsage or None."
            )

        if self.provider_request_id is not None:
            _require_non_blank(
                self.provider_request_id,
                "provider_request_id",
            )

        if (
            not isinstance(self.retry_count, int)
            or self.retry_count < 0
        ):
            raise ValueError(
                "retry_count must be a non-negative integer."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
