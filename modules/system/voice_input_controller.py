"""Application controller for microphone input and local STT."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import queue

from modules.audio.faster_whisper_transcriber import (
    FasterWhisperTranscriber,
)
from modules.audio.streaming_vad import (
    default_vad_backend,
)
from modules.audio.transcriber import (
    TranscriptionConfig,
)
from modules.audio.voice_turn_detector import (
    VoiceTurnDetector,
    VoiceTurnDetectorConfig,
)
from modules.media.browser_audio_source import (
    BrowserAudioSource,
)
from modules.media.microphone_ingress import (
    MicrophoneIngress,
    MicrophoneIngressService,
)
from modules.system.voice_input_worker import (
    VoiceInputResult,
    VoiceInputWorker,
)


@dataclass(frozen=True)
class VoiceInputSnapshot:
    enabled: bool
    status: str
    capture_url: str
    latest_transcript: str
    latest_language: str | None
    latest_error: str | None
    source_running: bool
    queue_depth: int
    dropped_chunks: int
    worker_state: str


class VoiceInputController:
    """Stable boundary used by Stage 2 and Stage 3."""

    def __init__(
        self,
        *,
        source: BrowserAudioSource,
        ingress: MicrophoneIngress,
        service: MicrophoneIngressService,
        worker: VoiceInputWorker,
    ) -> None:
        self.source = source
        self.ingress = ingress
        self.service = service
        self.worker = worker

        self.enabled = False
        self.latest_result: (
            VoiceInputResult | None
        ) = None
        self.latest_error: (
            str | None
        ) = None

    def enable(
        self,
    ) -> None:
        if self.enabled:
            return

        self.service.ensure_started()
        self.ingress.set_enabled(
            True
        )
        self.worker.start()

        self.enabled = True
        self.latest_error = None

    def disable(
        self,
    ) -> None:
        self.ingress.set_enabled(
            False
        )
        self.worker.stop()

        self.enabled = False

    def poll(
        self,
    ) -> list[VoiceInputResult]:
        completed: list[
            VoiceInputResult
        ] = []

        while True:
            try:
                result = (
                    self.worker
                    .get_result_nowait()
                )

            except queue.Empty:
                break

            self.latest_result = result

            if result.error:
                self.latest_error = (
                    result.error
                )

            completed.append(
                result
            )

        if self.worker.last_error:
            self.latest_error = (
                f"{type(self.worker.last_error).__name__}: "
                f"{self.worker.last_error}"
            )

        return completed

    def snapshot(
        self,
    ) -> VoiceInputSnapshot:
        source_stats = (
            self.source.stats()
        )

        transcript = ""
        language = None

        if (
            self.latest_result
            is not None
            and self.latest_result
            .transcript
            is not None
        ):
            transcript = (
                self.latest_result
                .transcript
                .text
            )

            language = (
                self.latest_result
                .transcript
                .language
            )

        if not self.enabled:
            status = "off"

        elif self.latest_error:
            status = "error"

        elif (
            self.worker.state
            == "transcribing"
        ):
            status = "transcribing"

        elif (
            self.worker.state
            == "speech_active"
        ):
            status = "speech_active"

        elif source_stats.is_running:
            status = "listening"

        elif transcript:
            status = "ready"

        else:
            status = (
                "waiting_permission"
            )

        return VoiceInputSnapshot(
            enabled=self.enabled,
            status=status,
            capture_url=(
                self.service
                .capture_url
            ),
            latest_transcript=(
                transcript
            ),
            latest_language=language,
            latest_error=(
                self.latest_error
            ),
            source_running=(
                source_stats
                .is_running
            ),
            queue_depth=(
                source_stats
                .queue_depth
            ),
            dropped_chunks=(
                source_stats
                .dropped_chunks
            ),
            worker_state=(
                self.worker.state
            ),
        )

    def public_snapshot(
        self,
    ) -> dict[str, object]:
        return asdict(
            self.snapshot()
        )


def build_default_voice_input_controller(
) -> VoiceInputController:
    source = BrowserAudioSource(
        queue_size=100
    )

    detector = VoiceTurnDetector(
        default_vad_backend(),
        config=(
            VoiceTurnDetectorConfig(
                sample_rate=16_000,
                frame_ms=30,
                pre_roll_ms=300,
                speech_start_window_ms=150,
                speech_end_silence_ms=800,
                minimum_utterance_ms=300,
                maximum_utterance_sec=20,
            )
        ),
    )

    transcriber = (
        FasterWhisperTranscriber(
            TranscriptionConfig(
                engine="faster_whisper",
                model_size=os.environ.get(
                    "ATTENTIVE_WHISPER_MODEL",
                    "small",
                ),
                device=os.environ.get(
                    "ATTENTIVE_WHISPER_DEVICE",
                    "cuda",
                ),
                compute_type=(
                    os.environ.get(
                        "ATTENTIVE_WHISPER_COMPUTE_TYPE",
                        "float16",
                    )
                ),
                language=os.environ.get(
                    "ATTENTIVE_WHISPER_LANGUAGE",
                    "zh",
                ),
                beam_size=1,
                vad_filter=False,
            )
        )
    )

    worker = VoiceInputWorker(
        source=source,
        detector=detector,
        transcribe=(
            transcriber.transcribe
        ),
    )

    ingress = MicrophoneIngress(
        source
    )

    service = (
        MicrophoneIngressService(
            ingress
        )
    )

    return VoiceInputController(
        source=source,
        ingress=ingress,
        service=service,
        worker=worker,
    )
