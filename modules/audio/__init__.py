"""Audio services for AttentiveSlides."""

from modules.audio.bailian_tts_client import (
    BailianTTSClient,
)
from modules.audio.speech_contracts import (
    SpeechSynthesisError,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
)

__all__ = [
    "BailianTTSClient",
    "SpeechSynthesisError",
    "SpeechSynthesisRequest",
    "SpeechSynthesisResult",
]
