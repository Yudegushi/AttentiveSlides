"""Run one real Qwen Omni Realtime manual audio turn.

Input:
    16 kHz, mono, signed-16 PCM WAV.

Output:
    24 kHz, mono, signed-16 PCM WAV and sanitized JSON metadata.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time
import wave
from typing import Any


ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from modules.realtime.bailian_omni_realtime_client import (  # noqa: E402
    BailianOmniRealtimeClient,
)


INPUT_SAMPLE_RATE = 16_000
OUTPUT_SAMPLE_RATE = 24_000
SAMPLE_WIDTH_BYTES = 2


def read_input_wav(
    path: Path,
) -> bytes:
    """Read and validate one provider-compatible input WAV."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Input WAV does not exist: {path}"
        )

    with wave.open(
        str(path),
        "rb",
    ) as audio:
        channels = audio.getnchannels()
        sample_width = (
            audio.getsampwidth()
        )
        sample_rate = (
            audio.getframerate()
        )
        frame_count = (
            audio.getnframes()
        )

        if channels != 1:
            raise ValueError(
                "Input WAV must be mono; "
                f"received channels={channels}."
            )

        if sample_width != SAMPLE_WIDTH_BYTES:
            raise ValueError(
                "Input WAV must use signed-16 PCM; "
                f"received sample_width={sample_width}."
            )

        if sample_rate != INPUT_SAMPLE_RATE:
            raise ValueError(
                "Input WAV must use a 16000 Hz "
                f"sample rate; received {sample_rate}."
            )

        if frame_count <= 0:
            raise ValueError(
                "Input WAV contains no audio frames."
            )

        pcm = audio.readframes(
            frame_count
        )

    if not pcm:
        raise ValueError(
            "Input WAV contains no PCM bytes."
        )

    if len(pcm) % SAMPLE_WIDTH_BYTES:
        raise ValueError(
            "Input PCM byte count is not "
            "aligned to signed-16 samples."
        )

    duration_seconds = (
        len(pcm)
        / SAMPLE_WIDTH_BYTES
        / INPUT_SAMPLE_RATE
    )

    if duration_seconds < 0.4:
        raise ValueError(
            "Input speech is too short for this "
            f"smoke test: {duration_seconds:.3f}s."
        )

    return pcm


def write_output_wav(
    path: Path,
    pcm: bytes,
) -> None:
    """Write model PCM output as a playable WAV."""

    if not pcm:
        raise ValueError(
            "The model returned no audio data."
        )

    if len(pcm) % SAMPLE_WIDTH_BYTES:
        raise ValueError(
            "Output PCM byte count is not "
            "aligned to signed-16 samples."
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with wave.open(
        str(path),
        "wb",
    ) as audio:
        audio.setnchannels(1)
        audio.setsampwidth(
            SAMPLE_WIDTH_BYTES
        )
        audio.setframerate(
            OUTPUT_SAMPLE_RATE
        )
        audio.writeframes(
            pcm
        )


def provider_error_message(
    payload: dict[str, Any],
) -> str:
    error = payload.get(
        "error",
        payload,
    )

    if isinstance(
        error,
        dict,
    ):
        return json.dumps(
            error,
            ensure_ascii=False,
            sort_keys=True,
        )

    return str(
        error
    )


async def run_manual_turn(
    *,
    input_pcm: bytes,
    instructions: str,
    timeout_seconds: float,
    chunk_ms: int,
) -> dict[str, Any]:
    """Send one manual audio turn and collect final outputs."""

    if chunk_ms <= 0:
        raise ValueError(
            "chunk_ms must be positive."
        )

    client = (
        BailianOmniRealtimeClient()
    )

    event_counts: Counter[str] = (
        Counter()
    )

    session_ready = asyncio.Event()

    input_preview = ""
    input_transcript = ""

    answer_deltas: list[str] = []
    final_answer = ""

    output_audio = bytearray()

    response_done = False
    response_status: str | None = None

    started = time.perf_counter()

    async def collect_events() -> None:
        nonlocal input_preview
        nonlocal input_transcript
        nonlocal final_answer
        nonlocal response_done
        nonlocal response_status

        async for event in client.events():
            event_counts[
                event.type
            ] += 1

            payload = event.payload

            if event.type == "session.updated":
                session_ready.set()

            elif (
                event.type
                == (
                    "conversation.item."
                    "input_audio_transcription."
                    "delta"
                )
            ):
                input_preview = (
                    str(
                        payload.get(
                            "text",
                            "",
                        )
                    )
                    + str(
                        payload.get(
                            "stash",
                            "",
                        )
                    )
                )

            elif (
                event.type
                == (
                    "conversation.item."
                    "input_audio_transcription."
                    "completed"
                )
            ):
                input_transcript = str(
                    payload.get(
                        "transcript",
                        payload.get(
                            "text",
                            "",
                        ),
                    )
                ).strip()

            elif (
                event.type
                == (
                    "response."
                    "audio_transcript."
                    "delta"
                )
            ):
                answer_deltas.append(
                    str(
                        payload.get(
                            "delta",
                            "",
                        )
                    )
                )

            elif (
                event.type
                == (
                    "response."
                    "audio_transcript."
                    "done"
                )
            ):
                final_answer = str(
                    payload.get(
                        "transcript",
                        payload.get(
                            "text",
                            "",
                        ),
                    )
                ).strip()

            elif (
                event.type
                == "response.text.delta"
            ):
                answer_deltas.append(
                    str(
                        payload.get(
                            "delta",
                            "",
                        )
                    )
                )

            elif (
                event.type
                == "response.text.done"
            ):
                final_answer = str(
                    payload.get(
                        "text",
                        "",
                    )
                ).strip()

            elif (
                event.type
                == "response.audio.delta"
            ):
                encoded = payload.get(
                    "delta",
                    "",
                )

                if encoded:
                    try:
                        output_audio.extend(
                            base64.b64decode(
                                encoded,
                                validate=True,
                            )
                        )

                    except (
                        ValueError,
                        TypeError,
                    ) as error:
                        raise RuntimeError(
                            "Provider returned invalid "
                            "Base64 audio."
                        ) from error

            elif event.type == "response.done":
                response = payload.get(
                    "response",
                    {},
                )

                if isinstance(
                    response,
                    dict,
                ):
                    raw_status = (
                        response.get(
                            "status"
                        )
                    )

                    if raw_status is not None:
                        response_status = str(
                            raw_status
                        )

                response_done = True
                return

            elif event.type == "error":
                raise RuntimeError(
                    "Realtime provider error: "
                    + provider_error_message(
                        payload
                    )
                )

    await client.connect(
        instructions=instructions,
        continuous=False,
    )

    collector = asyncio.create_task(
        collect_events()
    )

    try:
        await asyncio.wait_for(
            session_ready.wait(),
            timeout=min(
                15.0,
                timeout_seconds,
            ),
        )

        samples_per_chunk = max(
            1,
            round(
                INPUT_SAMPLE_RATE
                * chunk_ms
                / 1000
            ),
        )

        bytes_per_chunk = (
            samples_per_chunk
            * SAMPLE_WIDTH_BYTES
        )

        for start in range(
            0,
            len(input_pcm),
            bytes_per_chunk,
        ):
            chunk = input_pcm[
                start:
                start + bytes_per_chunk
            ]

            await client.append_pcm(
                chunk
            )

            await asyncio.sleep(
                chunk_ms
                / 1000
            )

        # Manual mode requires both commit and response.create.
        await (
            client
            .commit_and_respond()
        )

        await asyncio.wait_for(
            collector,
            timeout=timeout_seconds,
        )

    finally:
        if not collector.done():
            collector.cancel()

            try:
                await collector

            except asyncio.CancelledError:
                pass

        await client.close()

    elapsed_ms = round(
        (
            time.perf_counter()
            - started
        )
        * 1000
    )

    answer = (
        final_answer
        or "".join(
            answer_deltas
        ).strip()
    )

    transcript = (
        input_transcript
        or input_preview.strip()
    )

    if not response_done:
        raise RuntimeError(
            "The provider connection ended "
            "before response.done."
        )

    if not transcript:
        raise RuntimeError(
            "No input transcription was returned."
        )

    if not answer:
        raise RuntimeError(
            "No answer text was returned."
        )

    if not output_audio:
        raise RuntimeError(
            "No answer audio was returned."
        )

    return {
        "input_transcript": transcript,
        "answer_text": answer,
        "response_audio": bytes(
            output_audio
        ),
        "response_audio_bytes": len(
            output_audio
        ),
        "elapsed_ms": elapsed_ms,
        "response_status": (
            response_status
        ),
        "event_counts": dict(
            sorted(
                event_counts.items()
            )
        ),
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one Qwen Omni Realtime "
            "manual audio turn."
        )
    )

    parser.add_argument(
        "--input-wav",
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=150.0,
    )

    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--instructions",
        default=(
            "你是 AttentiveSlides 的教学助手。"
            "请简洁回答用户问题，"
            "专业名词保留英文，"
            "不要输出隐藏推理过程。"
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    for name in (
        "DASHSCOPE_API_KEY",
    ):
        if not os.environ.get(
            name
        ):
            print(
                f"{name} is not configured.",
                file=sys.stderr,
            )

            return 2

    input_path = Path(
        arguments.input_wav
    ).expanduser().resolve()

    output_dir = Path(
        arguments.output_dir
    ).expanduser().resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    input_pcm = read_input_wav(
        input_path
    )

    result = asyncio.run(
        run_manual_turn(
            input_pcm=input_pcm,
            instructions=(
                arguments.instructions
            ),
            timeout_seconds=(
                arguments.timeout
            ),
            chunk_ms=(
                arguments.chunk_ms
            ),
        )
    )

    response_audio = result.pop(
        "response_audio"
    )

    audio_path = (
        output_dir
        / "omni_realtime_answer.wav"
    )

    metadata_path = (
        output_dir
        / "omni_realtime_result.json"
    )

    write_output_wav(
        audio_path,
        response_audio,
    )

    public_payload = {
        **result,
        "provider": (
            "aliyun_bailian"
        ),
        "model": os.environ.get(
            "ATTENTIVE_REALTIME_MODEL",
            (
                "qwen3.5-omni-"
                "plus-realtime"
            ),
        ),
        "voice": os.environ.get(
            "ATTENTIVE_REALTIME_VOICE",
            "Tina",
        ),
        "input_audio_format": (
            "pcm_16000hz_mono_16bit"
        ),
        "output_audio_format": (
            "pcm_24000hz_mono_16bit"
        ),
        "audio_path": str(
            audio_path
        ),
        "history_persisted": False,
    }

    metadata_path.write_text(
        json.dumps(
            public_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            public_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
