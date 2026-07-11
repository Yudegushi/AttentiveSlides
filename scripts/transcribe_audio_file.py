"""Transcribe one audio file to AttentiveSlides Transcript JSON."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.audio.model_policy import available_profiles, transcription_config_for_profile
from modules.audio.transcriber import TranscriptionConfig
from modules.interaction.speech_to_text import transcribe_audio


def main() -> None:
    args = _parse_args()
    config = _build_config(args)
    transcript = transcribe_audio(args.audio, config)
    payload = {
        **asdict(transcript),
        "source": "audio_file",
        "audio_path": args.audio,
        "engine": config.engine,
        "model_size": config.model_size,
        "device": config.device,
        "compute_type": config.compute_type,
        "language": config.language,
        "beam_size": config.beam_size,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe an audio file into Transcript JSON.")
    parser.add_argument("--audio", required=True, help="Path to .wav/.mp3/.m4a audio.")
    parser.add_argument("--engine", choices=["mock", "faster_whisper"], default="faster_whisper")
    parser.add_argument("--profile", choices=available_profiles(), default="balanced")
    parser.add_argument("--model", dest="model_size")
    parser.add_argument("--device")
    parser.add_argument("--compute-type")
    parser.add_argument("--language")
    parser.add_argument("--beam-size", type=int)
    parser.add_argument("--no-vad-filter", action="store_true")
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> TranscriptionConfig:
    profile_config = transcription_config_for_profile(args.profile)
    return TranscriptionConfig(
        engine=args.engine,
        model_size=args.model_size or profile_config.model_size,
        device=args.device or profile_config.device,
        compute_type=args.compute_type or profile_config.compute_type,
        language=args.language or profile_config.language,
        beam_size=args.beam_size if args.beam_size is not None else profile_config.beam_size,
        vad_filter=not args.no_vad_filter,
    )


if __name__ == "__main__":
    main()
