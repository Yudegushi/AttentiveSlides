"""Unit tests for the Bailian speech client."""

from __future__ import annotations

import base64
import io
import tempfile
import unittest
import wave
from pathlib import Path
from typing import Any

from modules.audio.bailian_tts_client import (
    BailianTTSClient,
)
from modules.audio.speech_contracts import (
    SpeechSynthesisError,
    SpeechSynthesisRequest,
)


def make_wav_bytes() -> bytes:
    buffer = io.BytesIO()

    with wave.open(
        buffer,
        "wb",
    ) as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(
            b"\x00\x00" * 1600
        )

    return buffer.getvalue()


class FakeDownloadResponse:
    def __init__(
        self,
        content: bytes,
    ) -> None:
        self.content = content

    def raise_for_status(
        self,
    ) -> None:
        return None


class TestBailianTTSClient(
    unittest.TestCase
):
    def test_url_response_is_downloaded(
        self,
    ) -> None:
        captured: dict[
            str,
            Any,
        ] = {}

        def fake_call(
            **kwargs: Any,
        ) -> dict[str, Any]:
            captured.update(
                kwargs
            )

            return {
                "status_code": 200,
                "output": {
                    "audio": {
                        "url": (
                            "https://example.test/"
                            "audio.wav"
                        ),
                        "data": "",
                    }
                },
            }

        def fake_download(
            url: str,
            **kwargs: Any,
        ) -> FakeDownloadResponse:
            self.assertEqual(
                url,
                (
                    "https://example.test/"
                    "audio.wav"
                ),
            )

            return FakeDownloadResponse(
                make_wav_bytes()
            )

        with tempfile.TemporaryDirectory() as directory:
            destination = (
                Path(directory)
                / "answer.wav"
            )

            client = BailianTTSClient(
                api_key="test-key",
                call_function=fake_call,
                download_function=(
                    fake_download
                ),
            )

            result = client.synthesize(
                SpeechSynthesisRequest(
                    text="这是测试回答。",
                ),
                output_path=destination,
            )

            self.assertTrue(
                destination.is_file()
            )

            self.assertGreater(
                result.audio_bytes,
                44,
            )

            self.assertEqual(
                captured["model"],
                (
                    "qwen3-tts-"
                    "instruct-flash"
                ),
            )

            self.assertEqual(
                captured["voice"],
                "Cherry",
            )

    def test_base64_response_is_saved(
        self,
    ) -> None:
        encoded = base64.b64encode(
            make_wav_bytes()
        ).decode(
            "ascii"
        )

        def fake_call(
            **_: Any,
        ) -> dict[str, Any]:
            return {
                "status_code": 200,
                "output": {
                    "audio": {
                        "url": "",
                        "data": encoded,
                    }
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            destination = (
                Path(directory)
                / "answer.wav"
            )

            result = (
                BailianTTSClient(
                    api_key="test-key",
                    call_function=(
                        fake_call
                    ),
                )
                .synthesize(
                    SpeechSynthesisRequest(
                        text="测试。",
                    ),
                    output_path=(
                        destination
                    ),
                )
            )

            self.assertTrue(
                result.path.is_file()
            )

    def test_empty_text_is_rejected(
        self,
    ) -> None:
        client = BailianTTSClient(
            api_key="test-key",
            call_function=lambda **_: {},
        )

        with self.assertRaises(
            ValueError
        ):
            client.synthesize(
                SpeechSynthesisRequest(
                    text="   ",
                ),
                output_path=(
                    "/tmp/unused.wav"
                ),
            )

    def test_explicit_empty_key_does_not_fall_back_to_environment(
        self,
    ) -> None:
        from unittest.mock import patch

        with patch.dict(
            "os.environ",
            {
                "DASHSCOPE_API_KEY": (
                    "environment-key"
                ),
            },
            clear=False,
        ):
            client = BailianTTSClient(
                api_key="",
            )

            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(
                    SpeechSynthesisError
                ):
                    client.synthesize(
                        SpeechSynthesisRequest(
                            text="测试。",
                        ),
                        output_path=(
                            Path(directory)
                            / "answer.wav"
                        ),
                    )


    def test_missing_key_is_rejected(
        self,
    ) -> None:
        client = BailianTTSClient(
            api_key="",
        )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(
                SpeechSynthesisError
            ):
                client.synthesize(
                    SpeechSynthesisRequest(
                        text="测试。",
                    ),
                    output_path=(
                        Path(directory)
                        / "answer.wav"
                    ),
                )

    def test_public_result_excludes_private_fields(
        self,
    ) -> None:
        temporary_url = (
            "https://temporary-url/"
            "provider-audio.wav"
        )

        def fake_call(
            **_: Any,
        ) -> dict[str, Any]:
            return {
                "status_code": 200,
                "request_id": (
                    "provider-request-id"
                ),
                "output": {
                    "audio": {
                        "url": temporary_url,
                        "data": "",
                    }
                },
            }

        def fake_download(
            url: str,
            **kwargs: Any,
        ) -> FakeDownloadResponse:
            self.assertEqual(
                url,
                temporary_url,
            )

            self.assertIn(
                "timeout",
                kwargs,
            )

            return FakeDownloadResponse(
                make_wav_bytes()
            )

        with tempfile.TemporaryDirectory() as directory:
            result = (
                BailianTTSClient(
                    api_key="private-key",
                    call_function=(
                        fake_call
                    ),
                    download_function=(
                        fake_download
                    ),
                )
                .synthesize(
                    SpeechSynthesisRequest(
                        text="测试。",
                    ),
                    output_path=(
                        Path(directory)
                        / "answer.wav"
                    ),
                )
            )

            public_payload = (
                result.to_public_dict()
            )

            serialized = repr(
                public_payload
            )

            self.assertTrue(
                result.path.is_file()
            )

            self.assertGreater(
                result.audio_bytes,
                44,
            )

            self.assertNotIn(
                "private-key",
                serialized,
            )

            self.assertNotIn(
                temporary_url,
                serialized,
            )

            self.assertNotIn(
                "provider-request-id",
                serialized,
            )

            self.assertNotIn(
                "request_id",
                public_payload,
            )

            self.assertNotIn(
                "audio_url",
                public_payload,
            )




if __name__ == "__main__":
    unittest.main()
