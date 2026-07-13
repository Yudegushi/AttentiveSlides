"""Call the real Bailian TTS API and save one WAV file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from modules.audio import (  # noqa: E402
    BailianTTSClient,
    SpeechSynthesisRequest,
)


DEFAULT_TEXT = (
    "视觉注意力描述了人类如何选择并处理"
    "当前环境中最重要的信息。"
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--text",
        default=DEFAULT_TEXT,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
    )

    parser.add_argument(
        "--voice",
        default="Cherry",
    )

    parser.add_argument(
        "--language",
        default="Chinese",
    )

    parser.add_argument(
        "--model",
        default=(
            "qwen3-tts-instruct-flash"
        ),
    )

    arguments = parser.parse_args()

    if not os.environ.get(
        "DASHSCOPE_API_KEY"
    ):
        print(
            "DASHSCOPE_API_KEY is missing.",
            file=sys.stderr,
        )

        return 2

    output_directory = Path(
        arguments.output_dir
    ).expanduser().resolve()

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    audio_path = (
        output_directory
        / f"bailian_tutor_{timestamp}.wav"
    )

    metadata_path = (
        output_directory
        / f"bailian_tutor_{timestamp}.json"
    )

    client = BailianTTSClient()

    request = SpeechSynthesisRequest(
        text=arguments.text,
        model=arguments.model,
        voice=arguments.voice,
        language_type=(
            arguments.language
        ),
    )

    result = client.synthesize(
        request,
        output_path=audio_path,
    )

    public_payload = (
        result.to_public_dict()
    )

    metadata_path.write_text(
        json.dumps(
            public_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            public_payload,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
