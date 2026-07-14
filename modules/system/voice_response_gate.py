"""Application-level filtering for realtime voice turns."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class VoiceGateDecision:
    accepted: bool
    reason: str | None


FILLER_ONLY = {
    "嗯",
    "啊",
    "呃",
    "额",
    "哦",
    "唔",
    "hm",
    "hmm",
    "uh",
    "um",
    "er",
}

NOISE_MARKERS = {
    "[noise]",
    "[music]",
    "[silence]",
    "背景音乐",
    "字幕",
    "感谢观看",
}


def evaluate_voice_turn(
    *,
    transcript: str,
    voiced_duration_ms: int,
    audio_rms: float,
) -> VoiceGateDecision:
    normalized = re.sub(
        r"\s+",
        " ",
        transcript,
    ).strip()

    semantic = re.sub(
        r"[^\w\u4e00-\u9fff]",
        "",
        normalized,
    ).casefold()

    if voiced_duration_ms < 350:
        return VoiceGateDecision(
            accepted=False,
            reason=(
                "utterance_too_short"
            ),
        )

    if audio_rms < 120:
        return VoiceGateDecision(
            accepted=False,
            reason=(
                "audio_energy_too_low"
            ),
        )

    if not semantic:
        return VoiceGateDecision(
            accepted=False,
            reason="empty_transcript",
        )

    if semantic in FILLER_ONLY:
        return VoiceGateDecision(
            accepted=False,
            reason="filler_only",
        )

    lowered = normalized.casefold()

    if any(
        marker in lowered
        for marker in NOISE_MARKERS
    ):
        return VoiceGateDecision(
            accepted=False,
            reason="noise_transcript",
        )

    if len(semantic) < 2:
        return VoiceGateDecision(
            accepted=False,
            reason=(
                "insufficient_"
                "semantic_content"
            ),
        )

    return VoiceGateDecision(
        accepted=True,
        reason=None,
    )
