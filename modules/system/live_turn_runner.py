"""Run frozen live turns through the existing canonical tutor pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.common.schemas import InteractionResult, Transcript
from modules.interaction.interaction_history import InteractionHistory
from modules.logging.interaction_logger import InteractionLogger
from modules.system.adapters import (
    SensingProvider,
    SlideProvider,
    TranscriptProvider,
    build_pipeline_input_bundle,
    run_interaction_from_bundle,
)
from modules.system.audio_worker import AudioTurnResult
from modules.system.turn_context import AggregatedSensing, FrozenTurnContext, TurnContextCollector
from modules.tutor.tutor_agent import TutorAgent


class _TranscriptProvider:
    def __init__(self, transcript: Transcript) -> None:
        self._transcript = transcript

    def get_transcript(self) -> Transcript:
        return self._transcript


class _SensingProvider:
    def __init__(self, aggregated: AggregatedSensing) -> None:
        self._frame = aggregated.frame

    def get_sensing_frame(self, slide_id: int):
        if self._frame.gaze_prediction.slide_id != slide_id:
            raise LookupError("frozen sensing frame does not match the frozen slide")
        return self._frame


@dataclass(frozen=True)
class LiveTurnOutcome:
    interaction_result: InteractionResult | None
    pending_confirmation: bool
    error: str | None = None
    transcript: str | None = None
    turn_started_at: float | None = None
    turn_ended_at: float | None = None


class LiveTurnRunner:
    """Adapt canonical live inputs without duplicating intent or tutor logic."""

    def __init__(
        self,
        *,
        slide_provider: SlideProvider,
        context_collector: TurnContextCollector,
        history: InteractionHistory | None = None,
        tutor: TutorAgent | None = None,
        logger: InteractionLogger | None = None,
    ) -> None:
        self.slide_provider = slide_provider
        self.context_collector = context_collector
        self.history = history or InteractionHistory()
        self.tutor = tutor
        self.logger = logger
        self._pending: dict[str, Any] = {}

    def run(self, audio_result: AudioTurnResult, context: FrozenTurnContext) -> LiveTurnOutcome:
        metadata = {
            "transcript": audio_result.transcript.text if audio_result.transcript is not None else None,
            "turn_started_at": audio_result.turn.started_at,
            "turn_ended_at": audio_result.turn.ended_at,
        }
        if audio_result.status != "completed" or audio_result.transcript is None:
            return LiveTurnOutcome(
                interaction_result=None,
                pending_confirmation=False,
                error=audio_result.error or audio_result.status,
                **metadata,
            )
        aggregated = self.context_collector.aggregate(context)
        bundle = build_pipeline_input_bundle(
            slide_provider=self.slide_provider,
            transcript_provider=_TranscriptProvider(audio_result.transcript),
            sensing_provider=_SensingProvider(aggregated),
            slide_id=context.slide_id,
        )
        interaction = run_interaction_from_bundle(
            bundle,
            history=self.history,
            tutor=self.tutor,
            logger=self.logger,
        )
        pending = interaction.tutor_response.response_mode == "pending_confirmation"
        if pending:
            self._pending[interaction.resolved_query.query_id] = (bundle, metadata)
        return LiveTurnOutcome(
            interaction_result=interaction,
            pending_confirmation=pending,
            **metadata,
        )

    def resume_confirmation(
        self,
        query_id: str,
        confirmed_aoi_id: str,
    ) -> LiveTurnOutcome:
        try:
            bundle, metadata = self._pending.pop(query_id)
        except KeyError as exc:
            raise LookupError(f"No pending frozen turn for query {query_id}.") from exc
        interaction = run_interaction_from_bundle(
            bundle,
            confirmed_aoi_id=confirmed_aoi_id,
            history=self.history,
            tutor=self.tutor,
            logger=self.logger,
        )
        return LiveTurnOutcome(
            interaction_result=interaction,
            pending_confirmation=False,
            **metadata,
        )
