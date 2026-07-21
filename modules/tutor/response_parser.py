"""Parse raw LLM text into a StructuredTutorResponse.

The parser performs syntactic and schema-level validation. It may recover
from common provider formatting deviations such as Markdown code fences
or short explanatory text surrounding one JSON object.

It does not verify whether cited source IDs belong to the request. That
responsibility belongs to GroundingValidator.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from json import JSONDecodeError
from typing import Any

from modules.common.llm_schemas import (
    ClaimEvidence,
    StructuredTutorResponse,
)


_TOP_LEVEL_REQUIRED_FIELDS = {
    "response_mode",
    "answer",
    "decision_summary",
    "claims",
}

_TOP_LEVEL_OPTIONAL_FIELDS = {
    "external_knowledge_used",
    "uncertainty_note",
    "active_recall_question",
}

_CLAIM_REQUIRED_FIELDS = {
    "claim",
    "support",
    "source_ids",
}

_JSON_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json)?\s*(.*?)\s*```\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)


class ResponseParseError(ValueError):
    """Raised when an LLM response cannot be converted to the contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ResponseParseResult:
    """Structured response plus parser recovery diagnostics."""

    response: StructuredTutorResponse
    json_text: str
    warnings: tuple[str, ...] = ()

    @property
    def recovered(self) -> bool:
        return bool(self.warnings)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recovered"] = self.recovered
        return payload


class StructuredResponseParser:
    """Convert provider text into a StructuredTutorResponse."""

    def __init__(
        self,
        *,
        allow_code_fences: bool = True,
        allow_surrounding_text: bool = True,
        reject_unknown_fields: bool = True,
    ) -> None:
        self.allow_code_fences = allow_code_fences
        self.allow_surrounding_text = allow_surrounding_text
        self.reject_unknown_fields = reject_unknown_fields

    def parse(self, raw_text: str) -> ResponseParseResult:
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ResponseParseError(
                "empty_response",
                "The provider returned an empty response.",
            )

        json_text, warnings = self._extract_json_text(raw_text)

        try:
            payload = json.loads(json_text)
        except JSONDecodeError as exc:
            raise ResponseParseError(
                "invalid_json",
                (
                    f"JSON decoding failed at line {exc.lineno}, "
                    f"column {exc.colno}: {exc.msg}"
                ),
            ) from exc

        if not isinstance(payload, dict):
            raise ResponseParseError(
                "top_level_not_object",
                "The top-level JSON value must be an object.",
            )

        self._validate_object_keys(
            payload,
            required=_TOP_LEVEL_REQUIRED_FIELDS,
            optional=_TOP_LEVEL_OPTIONAL_FIELDS,
            location="response",
        )

        response = self._build_response(payload)

        return ResponseParseResult(
            response=response,
            json_text=json_text,
            warnings=tuple(warnings),
        )

    def _extract_json_text(
        self,
        raw_text: str,
    ) -> tuple[str, list[str]]:
        stripped = raw_text.strip()
        warnings: list[str] = []

        fence_match = _JSON_FENCE_PATTERN.match(stripped)

        if fence_match:
            if not self.allow_code_fences:
                raise ResponseParseError(
                    "code_fence_not_allowed",
                    "Markdown code fences are not allowed.",
                )

            stripped = fence_match.group(1).strip()
            warnings.append("markdown_code_fence_removed")

        decoder = json.JSONDecoder()

        # Preserve malformed direct JSON so json.loads can provide a useful
        # line and column error.
        if stripped.startswith(("{", "[")):
            try:
                _, end_index = decoder.raw_decode(stripped)
            except JSONDecodeError:
                return stripped, warnings

            remaining = stripped[end_index:].strip()

            if not remaining:
                return stripped[:end_index], warnings

            if not self.allow_surrounding_text:
                raise ResponseParseError(
                    "surrounding_text_not_allowed",
                    "Text was found after the JSON value.",
                )

            warnings.append("surrounding_text_removed")
            return stripped[:end_index], warnings

        if not self.allow_surrounding_text:
            raise ResponseParseError(
                "json_not_found",
                "The response does not begin with JSON.",
            )

        # Search for the first complete JSON object in surrounding prose.
        for start_index, character in enumerate(stripped):
            if character != "{":
                continue

            candidate = stripped[start_index:]

            try:
                value, relative_end = decoder.raw_decode(candidate)
            except JSONDecodeError:
                continue

            if not isinstance(value, dict):
                continue

            warnings.append("surrounding_text_removed")

            return (
                candidate[:relative_end],
                warnings,
            )

        raise ResponseParseError(
            "json_not_found",
            "No complete JSON object was found in the response.",
        )

    def _validate_object_keys(
        self,
        payload: dict[str, Any],
        *,
        required: set[str],
        optional: set[str],
        location: str,
    ) -> None:
        keys = set(payload)
        missing = required - keys

        if missing:
            raise ResponseParseError(
                "missing_field",
                (
                    f"{location} is missing required fields: "
                    f"{sorted(missing)}"
                ),
            )

        if self.reject_unknown_fields:
            unknown = keys - required - optional

            if unknown:
                raise ResponseParseError(
                    "unknown_field",
                    (
                        f"{location} contains unknown fields: "
                        f"{sorted(unknown)}"
                    ),
                )

    def _build_response(
        self,
        payload: dict[str, Any],
    ) -> StructuredTutorResponse:
        response_mode = payload["response_mode"]
        answer = payload["answer"]
        decision_summary = payload["decision_summary"]
        claims_payload = payload["claims"]

        if not isinstance(response_mode, str):
            self._raise_type_error(
                "response_mode",
                "string",
            )

        if not isinstance(answer, str):
            self._raise_type_error(
                "answer",
                "string",
            )

        if not isinstance(decision_summary, str):
            self._raise_type_error(
                "decision_summary",
                "string",
            )

        if not isinstance(claims_payload, list):
            self._raise_type_error(
                "claims",
                "array",
            )

        uncertainty_note = payload.get("uncertainty_note")
        active_recall_question = payload.get(
            "active_recall_question"
        )

        if (
            uncertainty_note is not None
            and not isinstance(uncertainty_note, str)
        ):
            self._raise_type_error(
                "uncertainty_note",
                "string or null",
            )

        if (
            active_recall_question is not None
            and not isinstance(active_recall_question, str)
        ):
            self._raise_type_error(
                "active_recall_question",
                "string or null",
            )

        claims = [
            self._build_claim(claim_payload, claim_index)
            for claim_index, claim_payload
            in enumerate(claims_payload)
        ]
        external_knowledge_used = any(
            claim.support == "external"
            for claim in claims
        )

        try:
            return StructuredTutorResponse(
                response_mode=response_mode,
                answer=answer,
                decision_summary=decision_summary,
                claims=claims,
                external_knowledge_used=(
                    external_knowledge_used
                ),
                uncertainty_note=uncertainty_note,
                active_recall_question=(
                    active_recall_question
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ResponseParseError(
                "schema_validation_error",
                str(exc),
            ) from exc

    def _build_claim(
        self,
        payload: Any,
        claim_index: int,
    ) -> ClaimEvidence:
        location = f"claims[{claim_index}]"

        if not isinstance(payload, dict):
            raise ResponseParseError(
                "invalid_field_type",
                f"{location} must be an object.",
            )

        self._validate_object_keys(
            payload,
            required=_CLAIM_REQUIRED_FIELDS,
            optional=set(),
            location=location,
        )

        claim = payload["claim"]
        support = payload["support"]
        source_ids = payload["source_ids"]

        if not isinstance(claim, str):
            self._raise_type_error(
                f"{location}.claim",
                "string",
            )

        if not isinstance(support, str):
            self._raise_type_error(
                f"{location}.support",
                "string",
            )

        if not isinstance(source_ids, list):
            self._raise_type_error(
                f"{location}.source_ids",
                "array of strings",
            )

        if any(
            not isinstance(source_id, str)
            for source_id in source_ids
        ):
            self._raise_type_error(
                f"{location}.source_ids",
                "array of strings",
            )

        try:
            return ClaimEvidence(
                claim=claim,
                support=support,
                source_ids=source_ids,
            )
        except (TypeError, ValueError) as exc:
            raise ResponseParseError(
                "schema_validation_error",
                f"{location}: {exc}",
            ) from exc

    @staticmethod
    def _raise_type_error(
        field_name: str,
        expected_type: str,
    ) -> None:
        raise ResponseParseError(
            "invalid_field_type",
            f"{field_name} must be {expected_type}.",
        )
