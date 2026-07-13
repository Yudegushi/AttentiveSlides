"""Background microphone turn and transcription worker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
from tempfile import NamedTemporaryFile
from threading import (
    Event,
    RLock,
    Thread,
    current_thread,
)
import time
from typing import Callable
import wave

import numpy as np

from modules.audio.voice_turn_detector import (
    SpeechTurn,
    VoiceTurnDetector,
)
from modules.common.schemas import Transcript
from modules.media.audio_packets import (
    AudioPacket,
)
from modules.media.browser_audio_source import (
    BrowserAudioSource,
)


@dataclass(frozen=True)
class VoiceInputResult:
    turn: SpeechTurn
    transcript: Transcript | None
    status: str
    error: str | None = None


class VoiceInputWorker:
    """Drain browser PCM and produce completed transcripts."""

    def __init__(
        self,
        *,
        source: BrowserAudioSource,
        detector: VoiceTurnDetector,
        transcribe: Callable[
            [str],
            Transcript,
        ],
        poll_interval_seconds: (
            float
        ) = 0.02,
        result_queue_size: int = 8,
    ) -> None:
        self.source = source
        self.detector = detector
        self.transcribe = transcribe

        self.poll_interval_seconds = (
            float(
                poll_interval_seconds
            )
        )

        self._results: queue.Queue[
            VoiceInputResult
        ] = queue.Queue(
            maxsize=result_queue_size
        )

        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None

        self._running_requested = False
        self._state = "idle"

        self.last_error: (
            Exception | None
        ) = None

        self.result_drops = 0

        self._source_origin: (
            float | None
        ) = None

        self._server_origin: (
            float | None
        ) = None

        self._last_source_timestamp: (
            float | None
        ) = None

    @property
    def is_running(
        self,
    ) -> bool:
        with self._lock:
            return bool(
                self._thread is not None
                and self._thread.is_alive()
            )

    @property
    def state(
        self,
    ) -> str:
        with self._lock:
            return self._state

    def start(
        self,
    ) -> None:
        with self._lock:
            if self._running_requested:
                return

            self._stop_event.clear()
            self.last_error = None
            self._running_requested = True
            self._state = "waiting"

            self._thread = Thread(
                target=self._run,
                name=(
                    "attentive-voice-input"
                ),
                daemon=True,
            )

            self._thread.start()

    def stop(
        self,
    ) -> None:
        with self._lock:
            self._running_requested = (
                False
            )
            self._stop_event.set()
            thread = self._thread

        if (
            thread is not None
            and thread
            is not current_thread()
        ):
            thread.join(
                timeout=3
            )

        self.detector.cancel()

        self.source.stop(
            reason="voice worker stopped"
        )

        with self._lock:
            self._state = "idle"

    def get_result_nowait(
        self,
    ) -> VoiceInputResult:
        return self._results.get_nowait()

    def process_available_audio(
        self,
    ) -> list[VoiceInputResult]:
        results: list[
            VoiceInputResult
        ] = []

        while True:
            try:
                packet = (
                    self.source
                    .audio_queue
                    .get_nowait()
                )

            except queue.Empty:
                break

            pcm = self._normalize_packet(
                packet
            )

            start_at = (
                self._normalize_timestamp(
                    packet.timestamp
                )
            )

            turns = self.detector.feed(
                pcm,
                start_at=start_at,
            )

            with self._lock:
                self._state = (
                    "speech_active"
                    if (
                        self.detector
                        .has_active_turn
                    )
                    else "listening"
                )

            for turn in turns:
                result = (
                    self._result_for_turn(
                        turn
                    )
                )

                self._publish(
                    result
                )

                results.append(
                    result
                )

        return results

    def _run(
        self,
    ) -> None:
        try:
            while not (
                self._stop_event
                .is_set()
            ):
                self.process_available_audio()

                self._stop_event.wait(
                    self.poll_interval_seconds
                )

        except Exception as error:
            with self._lock:
                self.last_error = error
                self._state = "error"
                self._running_requested = (
                    False
                )

            self._stop_event.set()

    def _result_for_turn(
        self,
        turn: SpeechTurn,
    ) -> VoiceInputResult:
        if turn.is_degraded:
            return VoiceInputResult(
                turn=turn,
                transcript=None,
                status="invalid",
                error=(
                    turn.degradation_reason
                    or "audio_degraded"
                ),
            )

        path = self._write_wav(
            turn
        )

        with self._lock:
            self._state = (
                "transcribing"
            )

        try:
            transcript = (
                self.transcribe(
                    str(path)
                )
            )

        except Exception as error:
            return VoiceInputResult(
                turn=turn,
                transcript=None,
                status="stt_error",
                error=(
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )

        finally:
            path.unlink(
                missing_ok=True
            )

            with self._lock:
                self._state = "listening"

        if not transcript.text.strip():
            return VoiceInputResult(
                turn=turn,
                transcript=None,
                status="invalid",
                error="empty_transcript",
            )

        return VoiceInputResult(
            turn=turn,
            transcript=transcript,
            status="completed",
        )

    def _write_wav(
        self,
        turn: SpeechTurn,
    ) -> Path:
        with NamedTemporaryFile(
            prefix="attentive-voice-",
            suffix=".wav",
            delete=False,
        ) as temporary:
            path = Path(
                temporary.name
            )

        with wave.open(
            str(path),
            "wb",
        ) as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(
                turn.sample_rate
            )
            output.writeframes(
                turn.samples.tobytes()
            )

        return path

    def _publish(
        self,
        result: VoiceInputResult,
    ) -> None:
        try:
            self._results.put_nowait(
                result
            )

        except queue.Full:
            try:
                self._results.get_nowait()

            except queue.Empty:
                pass

            self._results.put_nowait(
                result
            )

            self.result_drops += 1

    def _normalize_packet(
        self,
        packet: AudioPacket,
    ) -> np.ndarray:
        source = np.asarray(
            packet.samples,
            dtype=np.int16,
        )

        mono = np.rint(
            source
            .astype(np.float64)
            .mean(axis=1)
        ).astype(
            np.int16
        )

        target_rate = (
            self.detector
            .config
            .sample_rate
        )

        if (
            packet.sample_rate
            == target_rate
        ):
            return mono

        target_size = max(
            1,
            round(
                mono.size
                * target_rate
                / packet.sample_rate
            ),
        )

        positions = np.linspace(
            0,
            mono.size - 1,
            num=target_size,
        )

        resampled = np.interp(
            positions,
            np.arange(
                mono.size
            ),
            mono.astype(
                np.float64
            ),
        )

        return np.rint(
            resampled
        ).astype(
            np.int16
        )

    def _normalize_timestamp(
        self,
        source_timestamp: float,
    ) -> float:
        source_timestamp = float(
            source_timestamp
        )

        if (
            self._source_origin is None
            or self._server_origin
            is None
            or self
            ._last_source_timestamp
            is None
            or source_timestamp
            < self
            ._last_source_timestamp
        ):
            self._source_origin = (
                source_timestamp
            )

            self._server_origin = (
                time.monotonic()
            )

        self._last_source_timestamp = (
            source_timestamp
        )

        return (
            self._server_origin
            + source_timestamp
            - self._source_origin
        )
