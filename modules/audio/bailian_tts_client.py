"""Alibaba Cloud Bailian Qwen-TTS client."""

from __future__ import annotations

import base64
import hashlib
import os
import time
import wave
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

import requests

from modules.audio.speech_contracts import (
    SpeechSynthesisError,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
)


DEFAULT_BASE_HTTP_API_URL = (
    "https://dashscope.aliyuncs.com/api/v1"
)

# This is an application guard rather than the provider's
# tokenizer-level limit. Long tutor answers should be summarized
# or chunked in a later stage.
MAX_BASELINE_TEXT_CHARACTERS = 900


def _field(
    value: Any,
    name: str,
    default: Any = None,
) -> Any:
    """Read a field from either an object or mapping response."""

    if isinstance(
        value,
        Mapping,
    ):
        return value.get(
            name,
            default,
        )

    return getattr(
        value,
        name,
        default,
    )


def _validate_request(
    request: SpeechSynthesisRequest,
) -> None:
    text = request.text.strip()

    if not text:
        raise ValueError(
            "Speech synthesis text cannot be empty."
        )

    if (
        len(text)
        > MAX_BASELINE_TEXT_CHARACTERS
    ):
        raise ValueError(
            "Speech baseline text is too long: "
            f"{len(text)} characters. "
            "Maximum application limit is "
            f"{MAX_BASELINE_TEXT_CHARACTERS}."
        )

    if not request.model.strip():
        raise ValueError(
            "Speech model cannot be empty."
        )

    if not request.voice.strip():
        raise ValueError(
            "Speech voice cannot be empty."
        )


def _validate_wav(
    path: Path,
) -> None:
    if not path.is_file():
        raise SpeechSynthesisError(
            "Downloaded audio file is missing."
        )

    if path.stat().st_size <= 44:
        raise SpeechSynthesisError(
            "Downloaded WAV file is empty "
            "or incomplete."
        )

    try:
        with wave.open(
            str(path),
            "rb",
        ) as audio:
            if audio.getnframes() <= 0:
                raise SpeechSynthesisError(
                    "Downloaded WAV has no frames."
                )

            if audio.getframerate() <= 0:
                raise SpeechSynthesisError(
                    "Downloaded WAV has an invalid "
                    "sample rate."
                )

    except wave.Error as error:
        raise SpeechSynthesisError(
            "Provider output is not a valid WAV file."
        ) from error


class BailianTTSClient:
    """Generate tutor speech through Qwen3-TTS."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_http_api_url: str | None = None,
        timeout_seconds: int = 120,
        call_function: Callable[..., Any]
        | None = None,
        download_function: Callable[..., Any]
        | None = None,
    ) -> None:
        self._api_key = (
            os.environ.get(
                "DASHSCOPE_API_KEY"
            )
            if api_key is None
            else api_key
        )

        self._base_http_api_url = (
            base_http_api_url
            or os.environ.get(
                "DASHSCOPE_BASE_HTTP_API_URL"
            )
            or DEFAULT_BASE_HTTP_API_URL
        )

        self._timeout_seconds = int(
            timeout_seconds
        )

        self._call_function = (
            call_function
        )

        self._download_function = (
            download_function
            or requests.get
        )

    def _provider_call(
        self,
        request: SpeechSynthesisRequest,
    ) -> Any:
        if not self._api_key:
            raise SpeechSynthesisError(
                "DASHSCOPE_API_KEY is not configured."
            )

        if self._call_function is not None:
            return self._call_function(
                model=request.model,
                api_key=self._api_key,
                text=request.text,
                voice=request.voice,
                language_type=(
                    request.language_type
                ),
                instructions=(
                    request.instructions
                ),
                optimize_instructions=(
                    request.optimize_instructions
                ),
            )

        try:
            import dashscope

        except ImportError as error:
            raise SpeechSynthesisError(
                "The dashscope package is not installed."
            ) from error

        dashscope.base_http_api_url = (
            self._base_http_api_url
        )

        try:
            return (
                dashscope
                .MultiModalConversation
                .call(
                    model=request.model,
                    api_key=self._api_key,
                    text=request.text,
                    voice=request.voice,
                    language_type=(
                        request.language_type
                    ),
                    instructions=(
                        request.instructions
                    ),
                    optimize_instructions=(
                        request.optimize_instructions
                    ),
                )
            )

        except Exception as error:
            raise SpeechSynthesisError(
                "Bailian speech API request failed: "
                f"{type(error).__name__}: {error}"
            ) from error

    def _write_audio(
        self,
        *,
        response: Any,
        destination: Path,
    ) -> int:
        output = _field(
            response,
            "output",
        )

        audio = _field(
            output,
            "audio",
        )

        audio_url = _field(
            audio,
            "url",
        )

        audio_data = _field(
            audio,
            "data",
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with NamedTemporaryFile(
            mode="wb",
            prefix=(
                destination.stem
                + "_"
            ),
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(
                temporary.name
            )

            try:
                if audio_url:
                    provider_response = (
                        self._download_function(
                            audio_url,
                            timeout=(
                                10,
                                self._timeout_seconds,
                            ),
                        )
                    )

                    if hasattr(
                        provider_response,
                        "raise_for_status",
                    ):
                        provider_response.raise_for_status()

                    content = getattr(
                        provider_response,
                        "content",
                        b"",
                    )

                    if not content:
                        raise SpeechSynthesisError(
                            "Provider audio download "
                            "returned no content."
                        )

                    temporary.write(
                        content
                    )

                elif audio_data:
                    try:
                        temporary.write(
                            base64.b64decode(
                                audio_data,
                                validate=True,
                            )
                        )

                    except (
                        ValueError,
                        TypeError,
                    ) as error:
                        raise SpeechSynthesisError(
                            "Provider returned invalid "
                            "Base64 audio data."
                        ) from error

                else:
                    raise SpeechSynthesisError(
                        "Provider response contains "
                        "neither audio URL nor audio data."
                    )

            except Exception:
                temporary_path.unlink(
                    missing_ok=True
                )
                raise

        try:
            _validate_wav(
                temporary_path
            )

            temporary_path.replace(
                destination
            )

        except Exception:
            temporary_path.unlink(
                missing_ok=True
            )
            raise

        return destination.stat().st_size

    def synthesize(
        self,
        request: SpeechSynthesisRequest,
        *,
        output_path: str | Path,
    ) -> SpeechSynthesisResult:
        """Synthesize one complete tutor answer."""

        _validate_request(
            request
        )

        destination = Path(
            output_path
        ).expanduser().resolve()

        if (
            destination.suffix.lower()
            != ".wav"
        ):
            raise ValueError(
                "Speech output path must use "
                "the .wav extension."
            )

        started = time.perf_counter()

        response = self._provider_call(
            request
        )

        status_code = _field(
            response,
            "status_code",
            200,
        )

        if status_code != 200:
            code = _field(
                response,
                "code",
                "unknown_error",
            )

            message = _field(
                response,
                "message",
                "No provider error message.",
            )

            raise SpeechSynthesisError(
                "Bailian speech API returned "
                f"status={status_code}, "
                f"code={code}, "
                f"message={message}"
            )

        audio_bytes = self._write_audio(
            response=response,
            destination=destination,
        )

        elapsed_ms = round(
            (
                time.perf_counter()
                - started
            )
            * 1000
        )

        normalized_text = (
            request.text.strip()
        )

        return SpeechSynthesisResult(
            audio_path=str(
                destination
            ),
            model=request.model,
            voice=request.voice,
            language_type=(
                request.language_type
            ),
            text_character_count=len(
                normalized_text
            ),
            text_sha256=hashlib.sha256(
                normalized_text.encode(
                    "utf-8"
                )
            ).hexdigest(),
            audio_bytes=audio_bytes,
            elapsed_ms=elapsed_ms,
        )
