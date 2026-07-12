"""OpenAI-compatible API client for grounded tutor generation."""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from modules.common.llm_schemas import LLMUsage


class LLMProviderError(RuntimeError):
    """Raised when an API provider call fails."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class RawLLMResponse:
    """Provider response before structured parsing."""

    provider: str
    model: str
    raw_text: str
    latency_ms: float

    usage: LLMUsage | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must not be blank.")

        if not self.model.strip():
            raise ValueError("model must not be blank.")

        if not isinstance(self.raw_text, str):
            raise TypeError("raw_text must be a string.")

        if self.latency_ms < 0:
            raise ValueError(
                "latency_ms must be non-negative."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpenAICompatibleLLMClient:
    """OpenAI-compatible client configured for DashScope."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider: str = "dashscope",
        temperature: float = 0.2,
        max_tokens: int = 700,
        timeout_seconds: float = 120.0,
        transport_retries: int = 1,
        enable_thinking: bool | None = False,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be blank.")

        if not base_url.strip():
            raise ValueError("base_url must not be blank.")

        if not model.strip():
            raise ValueError("model must not be blank.")

        if max_tokens <= 0:
            raise ValueError(
                "max_tokens must be greater than zero."
            )

        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero."
            )

        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_thinking = enable_thinking

        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "The openai package is required for "
                    "OpenAICompatibleLLMClient."
                ) from exc

            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout_seconds,
                max_retries=transport_retries,
            )
        else:
            self._client = client

    @classmethod
    def from_env(
        cls,
    ) -> "OpenAICompatibleLLMClient":
        """Create a DashScope client from environment variables."""
        api_key = os.environ.get(
            "DASHSCOPE_API_KEY",
            "",
        )

        if not api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY is not configured."
            )

        return cls(
            api_key=api_key,
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL",
                (
                    "https://dashscope.aliyuncs.com/"
                    "compatible-mode/v1"
                ),
            ),
            model=os.environ.get(
                "DASHSCOPE_MODEL",
                "qwen3.7-plus",
            ),
            provider="dashscope",
            temperature=float(
                os.environ.get(
                    "DASHSCOPE_TEMPERATURE",
                    "0.2",
                )
            ),
            max_tokens=int(
                os.environ.get(
                    "DASHSCOPE_MAX_TOKENS",
                    "700",
                )
            ),
            timeout_seconds=float(
                os.environ.get(
                    "DASHSCOPE_TIMEOUT_SECONDS",
                    "120",
                )
            ),
            transport_retries=int(
                os.environ.get(
                    "DASHSCOPE_TRANSPORT_RETRIES",
                    "1",
                )
            ),
            enable_thinking=False,
        )

    def generate(
        self,
        messages: list[dict[str, str]],
    ) -> RawLLMResponse:
        """Generate one JSON-mode provider response."""
        self._validate_messages(messages)

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {
                "type": "json_object",
            },
        }

        if self.enable_thinking is not None:
            request_kwargs["extra_body"] = {
                "enable_thinking": (
                    self.enable_thinking
                ),
            }

        started = time.perf_counter()

        try:
            response = (
                self._client
                .chat
                .completions
                .create(**request_kwargs)
            )
        except Exception as exc:
            raise LLMProviderError(
                "provider_request_failed",
                str(exc),
            ) from exc

        latency_ms = (
            time.perf_counter() - started
        ) * 1000

        choices = getattr(response, "choices", None)

        if not choices:
            raise LLMProviderError(
                "missing_choice",
                "Provider response contains no choices.",
            )

        message = choices[0].message
        content = getattr(message, "content", None)

        if not isinstance(content, str):
            raise LLMProviderError(
                "missing_content",
                "Provider response contains no text content.",
            )

        return RawLLMResponse(
            provider=self.provider,
            model=(
                getattr(response, "model", None)
                or self.model
            ),
            raw_text=content,
            latency_ms=latency_ms,
            usage=self._extract_usage(
                getattr(response, "usage", None)
            ),
            request_id=getattr(response, "id", None),
        )

    @staticmethod
    def _validate_messages(
        messages: list[dict[str, str]],
    ) -> None:
        if not messages:
            raise ValueError(
                "messages must not be empty."
            )

        allowed_roles = {
            "system",
            "user",
            "assistant",
        }

        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise TypeError(
                    f"messages[{index}] must be a dictionary."
                )

            role = message.get("role")
            content = message.get("content")

            if role not in allowed_roles:
                raise ValueError(
                    f"Unsupported message role: {role!r}."
                )

            if (
                not isinstance(content, str)
                or not content.strip()
            ):
                raise ValueError(
                    f"messages[{index}].content "
                    "must not be blank."
                )

    @staticmethod
    def _extract_usage(
        usage: Any,
    ) -> LLMUsage | None:
        if usage is None:
            return None

        prompt_tokens = getattr(
            usage,
            "prompt_tokens",
            None,
        )
        completion_tokens = getattr(
            usage,
            "completion_tokens",
            None,
        )
        total_tokens = getattr(
            usage,
            "total_tokens",
            None,
        )

        if not all(
            isinstance(value, int)
            for value in {
                prompt_tokens,
                completion_tokens,
                total_tokens,
            }
        ):
            return None

        cached_prompt_tokens = None
        prompt_details = getattr(
            usage,
            "prompt_tokens_details",
            None,
        )

        if prompt_details is not None:
            cached_value = getattr(
                prompt_details,
                "cached_tokens",
                None,
            )

            if isinstance(cached_value, int):
                cached_prompt_tokens = cached_value

        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_prompt_tokens=(
                cached_prompt_tokens
            ),
        )
