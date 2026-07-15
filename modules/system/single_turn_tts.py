"""Synthesize one optional audio artifact for a completed tutor turn."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from modules.audio.bailian_tts_client import BailianTTSClient
from modules.audio.speech_contracts import SpeechSynthesisRequest


@dataclass(frozen=True)
class SingleTurnSpeechResult:
    interaction_id: str
    audio_path: Path | None
    error_message: str | None


class SingleTurnTTSController:
    """Cache TTS success or failure for one interaction/text pair."""

    def __init__(
        self,
        *,
        output_dir: str | Path,
        client_factory: Callable[[], BailianTTSClient] = BailianTTSClient,
    ) -> None:
        self._output_dir = Path(output_dir).expanduser()
        self._client_factory = client_factory
        self._lock = RLock()
        self._cache: dict[tuple[str, str], SingleTurnSpeechResult] = {}

    def synthesize_once(
        self,
        *,
        interaction_id: str,
        text: str,
        enabled: bool,
    ) -> SingleTurnSpeechResult:
        normalized_id = str(interaction_id).strip()
        normalized_text = " ".join(str(text).strip().split())
        empty = SingleTurnSpeechResult(normalized_id, None, None)
        if not enabled or not normalized_id or not normalized_text:
            return empty

        key = (normalized_id, normalized_text)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

            digest = hashlib.sha256(
                f"{normalized_id}\0{normalized_text}".encode("utf-8")
            ).hexdigest()
            destination = self._output_dir / f"{digest}.wav"
            try:
                speech = self._client_factory().synthesize(
                    SpeechSynthesisRequest(text=normalized_text),
                    output_path=destination,
                )
                result = SingleTurnSpeechResult(
                    normalized_id,
                    speech.path,
                    None,
                )
            except Exception:
                result = SingleTurnSpeechResult(
                    normalized_id,
                    None,
                    "tts_failed: 回答朗读暂时不可用；文字回答不受影响。",
                )
            self._cache[key] = result
            return result

    def clear(self) -> None:
        """Forget session-level request results without deleting runtime WAVs."""
        with self._lock:
            self._cache.clear()
