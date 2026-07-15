"""Input adapter contracts for Module 1/2 replacement boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from modules.common.schemas import (
    AOI,
    GazePrediction,
    InteractionResult,
    LearningState,
    Transcript,
    VisualContextItem,
)
from modules.interaction.interaction_history import InteractionHistory
from modules.logging.interaction_logger import InteractionLogger
from modules.system.pipeline import run_interaction
from modules.system.scenarios import InteractionScenario
from modules.tutor.context_retriever import DEFAULT_MANIFEST_PATH
from modules.tutor.tutor_agent import TutorAgent


@dataclass(frozen=True)
class SlideFrame:
    deck_id: str
    slide_id: int
    aois: list[AOI]
    slide_text: str
    neighbor_slide_text: str = ""
    slide_image_path: str | None = None
    visual_context: tuple[VisualContextItem, ...] = ()


@dataclass(frozen=True)
class SensingFrame:
    gaze_prediction: GazePrediction
    learning_state: LearningState


@dataclass(frozen=True)
class PipelineInputBundle:
    deck_id: str
    slide_id: int
    transcript: str
    gaze_prediction: GazePrediction
    learning_state: LearningState
    deck_store: "ProviderBackedDeckStore"


class SlideProvider(Protocol):
    @property
    def deck_id(self) -> str:
        ...

    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        ...


class TranscriptProvider(Protocol):
    def get_transcript(self) -> Transcript:
        ...


class SensingProvider(Protocol):
    def get_sensing_frame(self, slide_id: int) -> SensingFrame:
        ...


class MockManifestSlideProvider:
    def __init__(self, manifest_path: str | Path = DEFAULT_MANIFEST_PATH) -> None:
        self.manifest_path = Path(manifest_path)
        self._manifest = self._load_manifest()

    @property
    def deck_id(self) -> str:
        return str(self._manifest["deck_id"])

    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        slide = self._get_slide_payload(slide_id)
        return SlideFrame(
            deck_id=self.deck_id,
            slide_id=int(slide["slide_id"]),
            aois=[AOI(**aoi) for aoi in slide["aois"]],
            slide_text=str(slide["ocr_text"]),
            neighbor_slide_text=str(slide.get("neighbor_slide_text", "")),
            slide_image_path=_optional_string(slide.get("slide_image_path")),
            visual_context=tuple(
                VisualContextItem(**item)
                for item in slide.get("visual_context", [])
            ),
        )

    def _load_manifest(self) -> dict[str, Any]:
        with self.manifest_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _get_slide_payload(self, slide_id: int) -> dict[str, Any]:
        for slide in self._manifest["slides"]:
            if slide["slide_id"] == slide_id:
                return slide
        raise KeyError(f"Slide {slide_id} not found in {self.manifest_path}.")


class ScenarioTranscriptProvider:
    def __init__(self, scenario: InteractionScenario) -> None:
        self.scenario = scenario

    def get_transcript(self) -> Transcript:
        return Transcript(self.scenario.transcript)


class ScenarioSensingProvider:
    def __init__(self, scenario: InteractionScenario) -> None:
        self.scenario = scenario

    def get_sensing_frame(self, slide_id: int) -> SensingFrame:
        gaze = self.scenario.gaze_prediction
        if gaze.slide_id != slide_id:
            gaze = GazePrediction(
                slide_id=slide_id,
                gaze_grid=gaze.gaze_grid,
                predicted_aoi_id=gaze.predicted_aoi_id,
                confidence=gaze.confidence,
                stable_duration_sec=gaze.stable_duration_sec,
                alternative_targets=list(gaze.alternative_targets),
            )
        return SensingFrame(
            gaze_prediction=gaze,
            learning_state=self.scenario.learning_state,
        )


class ProviderBackedDeckStore:
    def __init__(self, slide_provider: SlideProvider) -> None:
        self.slide_provider = slide_provider
        self._deck_id: str | None = getattr(slide_provider, "deck_id", None)

    @property
    def deck_id(self) -> str:
        if self._deck_id is None:
            raise RuntimeError(
                "SlideProvider must expose an explicit deck_id after loading a deck; "
                "deck_id lookup never probes a fixed slide."
            )
        return self._deck_id

    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        frame = self.slide_provider.get_slide_frame(slide_id)
        if self._deck_id is None:
            self._deck_id = frame.deck_id
        return frame

    def get_slide(self, slide_id: int) -> dict[str, Any]:
        frame = self.get_slide_frame(slide_id)
        return {
            "slide_id": frame.slide_id,
            "slide_image_path": frame.slide_image_path,
            "ocr_text": frame.slide_text,
            "neighbor_slide_text": frame.neighbor_slide_text,
            "visual_context": [
                item.to_dict()
                for item in frame.visual_context
            ],
            "aois": [
                {
                    "aoi_id": aoi.aoi_id,
                    "bbox": list(aoi.bbox),
                    "type": aoi.type,
                    "name": aoi.name,
                    "text": aoi.text,
                }
                for aoi in frame.aois
            ],
        }

    def get_aois(self, slide_id: int) -> list[AOI]:
        return self.get_slide_frame(slide_id).aois


def build_pipeline_input_bundle(
    slide_provider: SlideProvider,
    transcript_provider: TranscriptProvider,
    sensing_provider: SensingProvider,
    slide_id: int,
) -> PipelineInputBundle:
    deck_store = ProviderBackedDeckStore(slide_provider)
    slide_frame = deck_store.get_slide_frame(slide_id)
    transcript = transcript_provider.get_transcript()
    sensing = sensing_provider.get_sensing_frame(slide_id)

    return PipelineInputBundle(
        deck_id=slide_frame.deck_id,
        slide_id=slide_frame.slide_id,
        transcript=transcript.text,
        gaze_prediction=sensing.gaze_prediction,
        learning_state=sensing.learning_state,
        deck_store=deck_store,
    )


def run_interaction_from_bundle(
    bundle: PipelineInputBundle,
    confirmed_aoi_id: str | None = None,
    history: InteractionHistory | None = None,
    tutor: TutorAgent | None = None,
    logger: InteractionLogger | None = None,
) -> InteractionResult:
    return run_interaction(
        transcript=bundle.transcript,
        gaze_prediction=bundle.gaze_prediction,
        learning_state=bundle.learning_state,
        deck_id=bundle.deck_id,
        slide_id=bundle.slide_id,
        confirmed_aoi_id=confirmed_aoi_id,
        history=history,
        deck_store=bundle.deck_store,
        tutor=tutor,
        logger=logger,
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
