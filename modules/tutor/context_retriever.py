"""Retrieve slide and AOI context from the mock deck manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.common.schemas import AOI, ResolvedQuery, TutorContext
from modules.interaction.interaction_history import InteractionHistory


DEFAULT_MANIFEST_PATH = Path("data/mock_deck/mock_aoi_manifest.json")


class MockDeckStore:
    def __init__(self, manifest_path: str | Path = DEFAULT_MANIFEST_PATH) -> None:
        self.manifest_path = Path(manifest_path)
        self._manifest = self._load_manifest()

    @property
    def deck_id(self) -> str:
        return self._manifest["deck_id"]

    def get_slide(self, slide_id: int) -> dict[str, Any]:
        for slide in self._manifest["slides"]:
            if slide["slide_id"] == slide_id:
                return slide
        raise KeyError(f"Slide {slide_id} not found in {self.manifest_path}.")

    def get_aois(self, slide_id: int) -> list[AOI]:
        slide = self.get_slide(slide_id)
        return [AOI(**aoi) for aoi in slide["aois"]]

    def _load_manifest(self) -> dict[str, Any]:
        with self.manifest_path.open("r", encoding="utf-8") as file:
            return json.load(file)


class ContextRetriever:
    def __init__(self, deck_store: MockDeckStore | None = None) -> None:
        self.deck_store = deck_store or MockDeckStore()

    def retrieve_context(
        self,
        resolved_query: ResolvedQuery,
        history: InteractionHistory | None = None,
    ) -> TutorContext:
        slide = self.deck_store.get_slide(resolved_query.slide_id)
        aois = [AOI(**aoi) for aoi in slide["aois"]]
        current_aoi = _find_aoi(aois, resolved_query.resolved_aoi_id)

        if current_aoi:
            current_aoi_text = current_aoi.text
        elif resolved_query.confirmation_mode == "click_required":
            current_aoi_text = "Target AOI is unresolved; user correction is required."
        else:
            current_aoi_text = ""

        return TutorContext(
            deck_id=resolved_query.deck_id,
            slide_id=resolved_query.slide_id,
            current_slide_text=slide["ocr_text"],
            current_aoi=current_aoi,
            current_aoi_text=current_aoi_text,
            neighbor_slide_text=slide.get("neighbor_slide_text", ""),
            resolved_query=resolved_query,
            interaction_history=history.recent() if history else [],
            adaptive_strategy=resolved_query.adaptive_strategy,
        )


def retrieve_context(
    deck_id: str,
    slide_id: int,
    resolved_aoi_id: str | None,
    history: InteractionHistory | None = None,
) -> TutorContext:
    del deck_id
    placeholder_query = ResolvedQuery(
        query_id="q_context",
        deck_id="mock_deck",
        slide_id=slide_id,
        transcript="",
        intent="unknown",
        resolved_aoi_id=resolved_aoi_id,
        target_confidence=0.0,
        needs_confirmation=False,
        confirmation_mode="none",
        adaptive_strategy="normal",
    )
    return ContextRetriever().retrieve_context(placeholder_query, history)


def _find_aoi(aois: list[AOI], aoi_id: str | None) -> AOI | None:
    for aoi in aois:
        if aoi.aoi_id == aoi_id:
            return aoi
    return None
