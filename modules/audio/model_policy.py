"""Shared faster-whisper model profiles for demo audio paths."""

from __future__ import annotations

from modules.audio.transcriber import TranscriptionConfig


_PROFILE_CONFIGS = {
    "fast": {
        "model_size": "small",
        "device": "cuda",
        "compute_type": "int8_float16",
        "language": "zh",
    },
    "balanced": {
        "model_size": "medium",
        "device": "cuda",
        "compute_type": "int8_float16",
        "language": "zh",
    },
    "accurate": {
        "model_size": "large-v3",
        "device": "cuda",
        "compute_type": "int8_float16",
        "language": "zh",
    },
    "cpu": {
        "model_size": "small",
        "device": "cpu",
        "compute_type": "int8",
        "language": "zh",
    },
}


def transcription_config_for_profile(profile: str) -> TranscriptionConfig:
    try:
        fields = _PROFILE_CONFIGS[profile]
    except KeyError as exc:
        names = ", ".join(sorted(_PROFILE_CONFIGS))
        raise ValueError(f"Unknown audio model profile: {profile}. Expected one of: {names}") from exc

    return TranscriptionConfig(engine="faster_whisper", beam_size=1, vad_filter=True, **fields)


def available_profiles() -> tuple[str, ...]:
    return tuple(sorted(_PROFILE_CONFIGS))
