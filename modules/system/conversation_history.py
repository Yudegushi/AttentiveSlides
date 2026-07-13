"""Sanitized conversation history for multi-turn tutoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


MAX_STORED_TURNS = 20
MAX_LLM_HISTORY_TURNS = 4
MAX_HISTORY_COMMAND_CHARS = 600
MAX_HISTORY_ANSWER_CHARS = 1200


@dataclass(frozen=True)
class ConversationTurn:
    """One public, sanitized tutoring turn."""

    turn_id: str
    interaction_id: str
    deck_id: str
    slide_id: int
    timestamp_utc: str

    user_command: str
    intent: str
    intent_source: str

    target_source: str
    confirmed_aoi_id: str | None
    confirmation_source: str | None
    corrected_from_aoi_id: str | None

    answer: str
    response_mode: str
    decision_summary: str
    active_recall_question: str | None

    source_ids: tuple[str, ...]
    reliability_level: str
    validation_is_valid: bool | None
    fallback_used: bool

    def __post_init__(self) -> None:
        required = {
            "turn_id": self.turn_id,
            "interaction_id": self.interaction_id,
            "deck_id": self.deck_id,
            "timestamp_utc": self.timestamp_utc,
            "user_command": self.user_command,
            "intent": self.intent,
            "intent_source": self.intent_source,
            "target_source": self.target_source,
            "answer": self.answer,
            "response_mode": self.response_mode,
            "reliability_level": self.reliability_level,
        }

        for name, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{name} must be a non-blank string."
                )

        if self.slide_id < 0:
            raise ValueError(
                "slide_id must be non-negative."
            )

        if len(self.source_ids) != len(
            set(self.source_ids)
        ):
            raise ValueError(
                "source_ids must be unique."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "interaction_id": self.interaction_id,
            "deck_id": self.deck_id,
            "slide_id": self.slide_id,
            "timestamp_utc": self.timestamp_utc,
            "user_command": self.user_command,
            "intent": self.intent,
            "intent_source": self.intent_source,
            "target_source": self.target_source,
            "confirmed_aoi_id": self.confirmed_aoi_id,
            "confirmation_source": self.confirmation_source,
            "corrected_from_aoi_id": (
                self.corrected_from_aoi_id
            ),
            "answer": self.answer,
            "response_mode": self.response_mode,
            "decision_summary": self.decision_summary,
            "active_recall_question": (
                self.active_recall_question
            ),
            "source_ids": list(self.source_ids),
            "reliability_level": (
                self.reliability_level
            ),
            "validation_is_valid": (
                self.validation_is_valid
            ),
            "fallback_used": self.fallback_used,
        }

    def to_llm_history_item(
        self,
        *,
        max_command_chars: int = (
            MAX_HISTORY_COMMAND_CHARS
        ),
        max_answer_chars: int = (
            MAX_HISTORY_ANSWER_CHARS
        ),
    ) -> dict[str, Any]:
        """Return the bounded history item supplied to the LLM."""
        return {
            "turn_id": self.turn_id,
            "interaction_id": self.interaction_id,
            "slide_id": self.slide_id,
            "user_command": _clip(
                self.user_command,
                max_command_chars,
            ),
            "intent": self.intent,
            "intent_source": self.intent_source,
            "confirmed_aoi_id": (
                self.confirmed_aoi_id
            ),
            "assistant_answer": _clip(
                self.answer,
                max_answer_chars,
            ),
            "response_mode": self.response_mode,
            "source_ids": list(self.source_ids),
            "validation_is_valid": (
                self.validation_is_valid
            ),
            "fallback_used": self.fallback_used,
        }


def build_conversation_turn(
    *,
    confirmed_interaction: Mapping[str, Any],
    tutor_result: Mapping[str, Any],
    llm_xai: Mapping[str, Any] | None = None,
    integrated_xai: Mapping[str, Any] | None = None,
    timestamp_utc: str | None = None,
) -> ConversationTurn:
    """Build one turn using an explicit field whitelist."""
    wrapper = _as_mapping(
        confirmed_interaction
    )

    raw_interaction = wrapper.get(
        "interaction"
    )

    interaction = (
        _as_mapping(raw_interaction)
        if isinstance(raw_interaction, Mapping)
        else wrapper
    )

    tutor = _as_mapping(tutor_result)
    xai = _as_mapping(llm_xai)
    integrated = _as_mapping(
        integrated_xai
    )

    target = _as_mapping(
        interaction.get("target")
    )
    intent = _as_mapping(
        interaction.get("intent")
    )
    confirmation = _as_mapping(
        interaction.get("confirmation")
    )

    interaction_id = _required_text(
        interaction.get("interaction_id"),
        "interaction_id",
    )

    answer = _required_text(
        tutor.get("answer"),
        "tutor answer",
    )

    response_mode = (
        _text(
            tutor.get("response_mode")
        )
        or "unknown"
    )

    resolved_intent = (
        _text(
            intent.get("explicit_intent")
        )
        or response_mode
    )

    validation = _as_mapping(
        xai.get("validation")
    )

    validation_value = validation.get(
        "is_valid",
        tutor.get("validation_is_valid"),
    )

    validation_is_valid = (
        bool(validation_value)
        if validation_value is not None
        else None
    )

    reliability = _as_mapping(
        _as_mapping(
            integrated.get("questions")
        ).get("reliability")
    )

    reliability_level = (
        _text(
            reliability.get("level")
        )
        or (
            "supported"
            if validation_is_valid is True
            else (
                "unsupported"
                if validation_is_valid is False
                else "pending"
            )
        )
    )

    source_ids = _collect_source_ids(
        xai
    )

    turn = ConversationTurn(
        turn_id=(
            _text(
                tutor.get("query_id")
            )
            or interaction_id
        ),
        interaction_id=interaction_id,
        deck_id=_required_text(
            interaction.get("deck_id"),
            "deck_id",
        ),
        slide_id=int(
            interaction["slide_id"]
        ),
        timestamp_utc=(
            timestamp_utc
            or datetime.now(
                timezone.utc
            ).isoformat()
        ),
        user_command=_required_text(
            intent.get("text"),
            "user command",
        ),
        intent=resolved_intent,
        intent_source=_required_text(
            intent.get("source"),
            "intent source",
        ),
        target_source=_required_text(
            target.get("source"),
            "target source",
        ),
        confirmed_aoi_id=(
            _text(
                confirmation.get(
                    "confirmed_aoi_id"
                )
            )
            or None
        ),
        confirmation_source=(
            _text(
                confirmation.get("source")
            )
            or None
        ),
        corrected_from_aoi_id=(
            _text(
                confirmation.get(
                    "corrected_from_aoi_id"
                )
            )
            or None
        ),
        answer=answer,
        response_mode=response_mode,
        decision_summary=_text(
            tutor.get("decision_summary")
        ),
        active_recall_question=(
            _text(
                tutor.get(
                    "active_recall_question"
                )
            )
            or None
        ),
        source_ids=tuple(source_ids),
        reliability_level=(
            reliability_level
        ),
        validation_is_valid=(
            validation_is_valid
        ),
        fallback_used=bool(
            tutor.get(
                "fallback_used",
                False,
            )
        ),
    )

    assert_public_conversation_payload(
        turn.to_dict()
    )

    return turn


def conversation_turn_from_dict(
    payload: Mapping[str, Any],
) -> ConversationTurn:
    """Restore a ConversationTurn from session-state data."""
    return ConversationTurn(
        turn_id=str(payload["turn_id"]),
        interaction_id=str(
            payload["interaction_id"]
        ),
        deck_id=str(payload["deck_id"]),
        slide_id=int(payload["slide_id"]),
        timestamp_utc=str(
            payload["timestamp_utc"]
        ),
        user_command=str(
            payload["user_command"]
        ),
        intent=str(payload["intent"]),
        intent_source=str(
            payload["intent_source"]
        ),
        target_source=str(
            payload["target_source"]
        ),
        confirmed_aoi_id=(
            str(payload["confirmed_aoi_id"])
            if payload.get(
                "confirmed_aoi_id"
            )
            is not None
            else None
        ),
        confirmation_source=(
            str(payload["confirmation_source"])
            if payload.get(
                "confirmation_source"
            )
            is not None
            else None
        ),
        corrected_from_aoi_id=(
            str(
                payload[
                    "corrected_from_aoi_id"
                ]
            )
            if payload.get(
                "corrected_from_aoi_id"
            )
            is not None
            else None
        ),
        answer=str(payload["answer"]),
        response_mode=str(
            payload["response_mode"]
        ),
        decision_summary=str(
            payload.get(
                "decision_summary",
                "",
            )
        ),
        active_recall_question=(
            str(
                payload[
                    "active_recall_question"
                ]
            )
            if payload.get(
                "active_recall_question"
            )
            is not None
            else None
        ),
        source_ids=tuple(
            str(source_id)
            for source_id in payload.get(
                "source_ids",
                (),
            )
        ),
        reliability_level=str(
            payload["reliability_level"]
        ),
        validation_is_valid=(
            bool(
                payload[
                    "validation_is_valid"
                ]
            )
            if payload.get(
                "validation_is_valid"
            )
            is not None
            else None
        ),
        fallback_used=bool(
            payload.get(
                "fallback_used",
                False,
            )
        ),
    )


def upsert_conversation_turn(
    turns: Sequence[
        ConversationTurn | Mapping[str, Any]
    ],
    turn: ConversationTurn,
    *,
    max_stored_turns: int = MAX_STORED_TURNS,
) -> list[dict[str, Any]]:
    """Insert or replace a turn using interaction_id."""
    if max_stored_turns <= 0:
        raise ValueError(
            "max_stored_turns must be positive."
        )

    normalized = [
        _normalize_turn(item)
        for item in turns
    ]

    retained = [
        item
        for item in normalized
        if item.interaction_id
        != turn.interaction_id
    ]

    retained.append(turn)

    result = [
        item.to_dict()
        for item in retained[
            -max_stored_turns:
        ]
    ]

    assert_public_conversation_payload(
        result
    )

    return result


def build_llm_interaction_history(
    turns: Sequence[
        ConversationTurn | Mapping[str, Any]
    ],
    *,
    deck_id: str,
    exclude_interaction_id: str | None = None,
    max_items: int = MAX_LLM_HISTORY_TURNS,
) -> list[dict[str, Any]]:
    """Build bounded, same-deck history for TutorContext."""
    if max_items < 0:
        raise ValueError(
            "max_items must be non-negative."
        )

    if max_items == 0:
        return []

    normalized = [
        _normalize_turn(item)
        for item in turns
    ]

    eligible = [
        turn
        for turn in normalized
        if (
            turn.deck_id == deck_id
            and (
                exclude_interaction_id
                is None
                or turn.interaction_id
                != exclude_interaction_id
            )
        )
    ]

    history = [
        turn.to_llm_history_item()
        for turn in eligible[-max_items:]
    ]

    assert_public_conversation_payload(
        history
    )

    return history


def export_conversation(
    *,
    deck_id: str,
    turns: Sequence[
        ConversationTurn | Mapping[str, Any]
    ],
) -> dict[str, Any]:
    """Build a user-downloadable public conversation export."""
    normalized_all = [
        _normalize_turn(item)
        for item in turns
    ]

    normalized = [
        turn
        for turn in normalized_all
        if turn.deck_id == deck_id
    ]

    payload = {
        "schema_version": "1.0",
        "deck_id": deck_id,
        "turn_count": len(normalized),
        "turns": [
            turn.to_dict()
            for turn in normalized
        ],
    }

    assert_public_conversation_payload(
        payload
    )

    return payload


def assert_public_conversation_payload(
    payload: Any,
) -> None:
    """Reject private fields by key name."""
    forbidden = _find_forbidden_keys(
        payload
    )

    if forbidden:
        raise ValueError(
            "Conversation payload contains "
            f"forbidden fields: "
            f"{sorted(forbidden)}"
        )


def _normalize_turn(
    value: ConversationTurn | Mapping[str, Any],
) -> ConversationTurn:
    if isinstance(
        value,
        ConversationTurn,
    ):
        return value

    if isinstance(value, Mapping):
        return conversation_turn_from_dict(
            value
        )

    raise TypeError(
        "Conversation history accepts "
        "ConversationTurn or mapping values."
    )


def _collect_source_ids(
    xai: Mapping[str, Any],
) -> list[str]:
    source_ids: set[str] = set()

    claims = xai.get("claims", [])

    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(
                claim,
                Mapping,
            ):
                continue

            values = claim.get(
                "source_ids",
                [],
            )

            if isinstance(
                values,
                (list, tuple),
            ):
                source_ids.update(
                    str(value)
                    for value in values
                    if str(value).strip()
                )

    return sorted(source_ids)


def _clip(
    value: str,
    max_chars: int,
) -> str:
    if max_chars <= 0:
        return ""

    if len(value) <= max_chars:
        return value

    suffix = " [TRUNCATED]"

    available = max_chars - len(suffix)

    if available <= 0:
        return suffix[:max_chars]

    return value[:available] + suffix


def _required_text(
    value: Any,
    field_name: str,
) -> str:
    text = _text(value)

    if not text:
        raise ValueError(
            f"{field_name} must not be blank."
        )

    return text


def _text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _as_mapping(
    value: Any,
) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value

    return {}


_FORBIDDEN_PUBLIC_KEYS = {
    "api_key",
    "authorization",
    "prompt",
    "prompts",
    "prompt_messages",
    "system_prompt",
    "user_prompt",
    "raw_response",
    "raw_provider_response",
    "provider_request_id",
    "request_id",
    "chain_of_thought",
    "hidden_reasoning",
    "reasoning_content",
}


def _find_forbidden_keys(
    value: Any,
) -> set[str]:
    found: set[str] = set()

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = (
                str(key)
                .strip()
                .casefold()
            )

            if normalized in (
                _FORBIDDEN_PUBLIC_KEYS
            ):
                found.add(normalized)

            found.update(
                _find_forbidden_keys(
                    child
                )
            )

    elif isinstance(
        value,
        (list, tuple),
    ):
        for child in value:
            found.update(
                _find_forbidden_keys(
                    child
                )
            )

    return found
