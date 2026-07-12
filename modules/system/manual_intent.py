"""Typed and explicit UI intent resolution for manual interaction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from modules.common.interaction_contracts import (
    IntentInput,
)
from modules.common.schemas import (
    IntentName,
    IntentResult,
)
from modules.interaction.intent_parser import (
    parse_intent,
)


IntentReadinessStatus = Literal[
    "ready",
    "warning",
    "blocked",
]


@dataclass(frozen=True)
class QuickIntentAction:
    """One explicit intent action displayed in the Main UI."""

    label: str
    intent: IntentName
    command: str
    description: str

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError(
                "QuickIntentAction.label must not be blank."
            )

        if not self.command.strip():
            raise ValueError(
                "QuickIntentAction.command must not be blank."
            )

        if self.intent == "unknown":
            raise ValueError(
                "A quick action cannot use unknown intent."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


QUICK_INTENT_ACTIONS: tuple[
    QuickIntentAction,
    ...,
] = (
    QuickIntentAction(
        label="Explain",
        intent="explain",
        command="explain this",
        description=(
            "Explain the selected slide content."
        ),
    ),
    QuickIntentAction(
        label="Summarize",
        intent="summarize",
        command="summarize this",
        description=(
            "Provide a concise summary."
        ),
    ),
    QuickIntentAction(
        label="Simplify",
        intent="simplify",
        command="make this simpler",
        description=(
            "Use simpler language and structure."
        ),
    ),
    QuickIntentAction(
        label="Step by step",
        intent="step_by_step",
        command="explain this step by step",
        description=(
            "Explain the content sequentially."
        ),
    ),
    QuickIntentAction(
        label="Compare",
        intent="compare",
        command="compare this",
        description=(
            "Compare the selected content."
        ),
    ),
    QuickIntentAction(
        label="Quiz",
        intent="quiz",
        command="quiz me on this",
        description=(
            "Generate an active-recall question."
        ),
    ),
)


_QUICK_ACTION_BY_INTENT = {
    action.intent: action
    for action in QUICK_INTENT_ACTIONS
}


@dataclass(frozen=True)
class ManualIntentResolution:
    """Resolved intent with user-input provenance."""

    intent_input: IntentInput
    intent_result: IntentResult
    recognized: bool
    provenance: tuple[str, ...]

    @property
    def intent(self) -> IntentName:
        return self.intent_result.intent

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_input": (
                self.intent_input.to_dict()
            ),
            "intent_result": asdict(
                self.intent_result
            ),
            "recognized": self.recognized,
            "provenance": list(
                self.provenance
            ),
        }


@dataclass(frozen=True)
class IntentTargetAssessment:
    """Readiness of an intent for the current target state."""

    ready: bool
    status: IntentReadinessStatus
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_typed_intent_input(
    text: str,
    *,
    language: str | None = None,
) -> IntentInput:
    """Create an IntentInput from manually typed text."""
    return IntentInput(
        source="typed_text",
        text=text,
        language=language,
    )


def make_quick_action_intent_input(
    intent: IntentName,
) -> IntentInput:
    """Create an explicit IntentInput from a UI action."""
    try:
        action = _QUICK_ACTION_BY_INTENT[
            intent
        ]
    except KeyError as exc:
        raise ValueError(
            f"No quick action is defined for "
            f"intent {intent!r}."
        ) from exc

    return IntentInput(
        source="ui_action",
        text=action.command,
        explicit_intent=action.intent,
        source_confidence=1.0,
        language="en",
    )


def get_quick_action(
    intent: IntentName,
) -> QuickIntentAction:
    """Return the UI action associated with an intent."""
    try:
        return _QUICK_ACTION_BY_INTENT[
            intent
        ]
    except KeyError as exc:
        raise ValueError(
            f"No quick action is defined for "
            f"intent {intent!r}."
        ) from exc


def resolve_manual_intent(
    intent_input: IntentInput,
) -> ManualIntentResolution:
    """Resolve typed text or an explicit UI action."""
    if not isinstance(
        intent_input,
        IntentInput,
    ):
        raise TypeError(
            "intent_input must be an IntentInput."
        )

    parsed = parse_intent(
        intent_input.text
        or intent_input.explicit_intent
        or ""
    )

    if intent_input.explicit_intent is None:
        result = parsed
    else:
        transcript = (
            intent_input.text.strip()
            or intent_input.explicit_intent
        )

        result = IntentResult(
            intent=(
                intent_input.explicit_intent
            ),
            confidence=1.0,
            has_deictic_reference=(
                parsed.has_deictic_reference
            ),
            explicit_target_hint=(
                parsed.explicit_target_hint
            ),
            transcript=transcript,
        )

    provenance = [
        (
            "intent source = "
            f"{intent_input.source}"
        ),
        (
            "resolved intent = "
            f"{result.intent}"
        ),
        (
            "intent confidence = "
            f"{result.confidence:.3f}"
        ),
    ]

    if (
        intent_input.explicit_intent
        is not None
    ):
        provenance.append(
            "intent was explicitly selected "
            "through a UI action"
        )
    else:
        provenance.append(
            "intent was inferred from typed text"
        )

    if result.has_deictic_reference:
        provenance.append(
            "deictic reference detected"
        )

    if result.explicit_target_hint:
        provenance.append(
            "explicit target hint = "
            f"{result.explicit_target_hint}"
        )

    return ManualIntentResolution(
        intent_input=intent_input,
        intent_result=result,
        recognized=(
            result.intent != "unknown"
        ),
        provenance=tuple(provenance),
    )


def assess_intent_target(
    resolution: ManualIntentResolution | None,
    *,
    target_available: bool,
    selected_aoi_count: int,
) -> IntentTargetAssessment:
    """Assess whether the resolved intent can continue."""
    if resolution is None:
        return IntentTargetAssessment(
            ready=False,
            status="blocked",
            message=(
                "Enter a command or select "
                "a quick action."
            ),
        )

    if not resolution.recognized:
        return IntentTargetAssessment(
            ready=False,
            status="blocked",
            message=(
                "The command was not recognized. "
                "Use a quick action or rewrite it."
            ),
        )

    if resolution.intent == "break":
        return IntentTargetAssessment(
            ready=True,
            status="ready",
            message=(
                "Break intent does not require "
                "a slide target."
            ),
        )

    if not target_available:
        return IntentTargetAssessment(
            ready=False,
            status="blocked",
            message=(
                "Select a slide target before "
                "continuing."
            ),
        )

    if (
        resolution.intent == "compare"
        and selected_aoi_count < 2
    ):
        return IntentTargetAssessment(
            ready=True,
            status="warning",
            message=(
                "Compare intent was recognized, "
                "but only one target is currently "
                "available. Multi-region selection "
                "will be added later."
            ),
        )

    return IntentTargetAssessment(
        ready=True,
        status="ready",
        message=(
            "Intent and target are ready "
            "for confirmation."
        ),
    )
