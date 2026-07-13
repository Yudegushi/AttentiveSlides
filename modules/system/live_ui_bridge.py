"""Thin bridge from continuous live turns to the official Streamlit UI."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, replace
import math
import queue
from typing import Callable, Sequence
import uuid

from modules.common.interaction_contracts import TargetCandidate
from modules.common.schemas import AOI
from modules.human_sensing.contracts import AOIPrediction as MemberAOIPrediction
from modules.system.runtime_state import RuntimeState
from modules.system.slide_geometry import SlideViewportGeometry, ViewportBBox


@dataclass(frozen=True)
class LiveInteractionProposal:
    interaction_id: str
    deck_id: str
    slide_id: int
    layout_revision: int
    transcript: str
    gaze_grid: str
    gaze_confidence: float
    stable_duration_sec: float
    predicted_aoi_id: str | None = None
    target_confidence: float = 0.0
    alternatives: tuple[TargetCandidate, ...] = ()
    original_speech_transcript: str = ""


@dataclass(frozen=True)
class ProposalTurnOutcome:
    pending_confirmation: bool
    error: str | None = None


class LatestProposalInbox:
    def __init__(self) -> None:
        self._queue: queue.Queue[LiveInteractionProposal] = queue.Queue(maxsize=1)

    def publish(self, proposal: LiveInteractionProposal) -> None:
        with suppress(queue.Empty):
            self._queue.get_nowait()
        self._queue.put_nowait(proposal)

    def pop(self) -> LiveInteractionProposal | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def clear(self) -> None:
        while self.pop() is not None:
            pass


_GRID_INDEX = {
    "top_left": (0, 0),
    "top_center": (0, 1),
    "top_right": (0, 2),
    "middle_left": (1, 0),
    "middle_center": (1, 1),
    "middle_right": (1, 2),
    "bottom_left": (2, 0),
    "bottom_center": (2, 1),
    "bottom_right": (2, 2),
}
_EXCLUDED_TYPES = {"footer", "page_number", "decoration", "background"}


def resolve_grid_target(
    proposal: LiveInteractionProposal,
    geometry: SlideViewportGeometry,
    aois: Sequence[AOI],
) -> LiveInteractionProposal:
    if (
        proposal.deck_id != geometry.deck_id
        or proposal.slide_id != geometry.slide_id
        or proposal.layout_revision not in {-1, geometry.layout_revision}
        or proposal.gaze_grid not in _GRID_INDEX
    ):
        return replace(
            proposal,
            predicted_aoi_id=None,
            target_confidence=0.0,
            alternatives=(),
        )

    row, column = _GRID_INDEX[proposal.gaze_grid]
    cell_width = geometry.viewport_width / 3.0
    cell_height = geometry.viewport_height / 3.0
    cell = ViewportBBox(
        column * cell_width,
        row * cell_height,
        (column + 1) * cell_width,
        (row + 1) * cell_height,
    )
    eligible = {
        aoi.aoi_id
        for aoi in aois
        if aoi.aoi_id != "whole_slide"
        and _normalized_type(aoi.type) not in _EXCLUDED_TYPES
    }
    ranked: list[tuple[float, str, float]] = []
    for aoi_id in eligible:
        rect = geometry.aoi_rects.get(aoi_id)
        if rect is None:
            continue
        overlap_ratio = _intersection_area(cell, rect) / _area(rect)
        center_proximity = _center_proximity(cell, rect)
        spatial_score = 0.7 * overlap_ratio + 0.3 * center_proximity
        target_confidence = max(
            0.0,
            min(1.0, proposal.gaze_confidence * spatial_score),
        )
        if spatial_score > 0:
            ranked.append((target_confidence, aoi_id, spatial_score))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    alternatives = tuple(
        TargetCandidate(
            aoi_id=aoi_id,
            score=round(confidence, 3),
            evidence=(
                f"gaze grid={proposal.gaze_grid}",
                f"viewport spatial score={spatial_score:.3f}",
            ),
        )
        for confidence, aoi_id, spatial_score in ranked[:3]
    )
    top_confidence = ranked[0][0] if ranked else 0.0
    return replace(
        proposal,
        layout_revision=geometry.layout_revision,
        predicted_aoi_id=(
            ranked[0][1] if ranked and top_confidence >= 0.35 else None
        ),
        target_confidence=round(top_confidence, 3),
        alternatives=alternatives,
    )


def map_gaze_grid_only(gaze, _aois) -> MemberAOIPrediction:
    target = gaze.gaze_grid if gaze.gaze_grid != "unknown" else None
    return MemberAOIPrediction(
        timestamp=gaze.timestamp,
        slide_id=gaze.slide_id,
        gaze_grid=gaze.gaze_grid,
        predicted_aoi_id=target,
        confidence=gaze.confidence,
        stable_duration_sec=gaze.stable_duration_sec,
        candidate_scores={target: gaze.confidence} if target is not None else {},
        evidence=list(gaze.evidence),
    )


class ProposalTurnRunner:
    def __init__(
        self,
        *,
        context_collector,
        inbox: LatestProposalInbox,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.context_collector = context_collector
        self.inbox = inbox
        self.id_factory = id_factory

    def run(self, audio_result, context) -> ProposalTurnOutcome:
        if audio_result.status != "completed" or audio_result.transcript is None:
            return ProposalTurnOutcome(
                pending_confirmation=False,
                error=audio_result.error or audio_result.status,
            )
        gaze = self.context_collector.aggregate(context).frame.gaze_prediction
        transcript = audio_result.transcript.text
        self.inbox.publish(
            LiveInteractionProposal(
                interaction_id=self.id_factory(),
                deck_id=context.deck_id,
                slide_id=context.slide_id,
                layout_revision=-1,
                transcript=transcript,
                gaze_grid=gaze.gaze_grid,
                gaze_confidence=gaze.confidence,
                stable_duration_sec=gaze.stable_duration_sec,
                original_speech_transcript=transcript,
            )
        )
        return ProposalTurnOutcome(pending_confirmation=False)


class MainUILiveRuntime:
    def __init__(self, *, controller, inbox, snapshot_store) -> None:
        self.controller = controller
        self.inbox = inbox
        self.snapshot_store = snapshot_store

    @property
    def is_running(self) -> bool:
        return self.controller.state not in {
            RuntimeState.STOPPED,
            RuntimeState.ERROR,
        }

    def start(self) -> None:
        self.controller.start()

    def stop(self, *, reason: str = "requested") -> None:
        self.controller.stop(reason=reason)

    def handle_disconnect(self) -> None:
        self.controller.handle_disconnect()

    def set_slide(self, slide_id: int) -> None:
        self.inbox.clear()
        self.snapshot_store.clear()
        self.controller.set_slide(slide_id)

    def poll(self):
        return self.controller.poll()


def _normalized_type(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _area(rect: ViewportBBox) -> float:
    return (rect.x2 - rect.x1) * (rect.y2 - rect.y1)


def _intersection_area(left: ViewportBBox, right: ViewportBBox) -> float:
    width = max(0.0, min(left.x2, right.x2) - max(left.x1, right.x1))
    height = max(0.0, min(left.y2, right.y2) - max(left.y1, right.y1))
    return width * height


def _center_proximity(cell: ViewportBBox, rect: ViewportBBox) -> float:
    cell_center = ((cell.x1 + cell.x2) / 2.0, (cell.y1 + cell.y2) / 2.0)
    rect_center = ((rect.x1 + rect.x2) / 2.0, (rect.y1 + rect.y2) / 2.0)
    distance = math.hypot(
        rect_center[0] - cell_center[0], rect_center[1] - cell_center[1]
    )
    half_diagonal = math.hypot(
        cell.x2 - cell.x1, cell.y2 - cell.y1
    ) / 2.0
    return max(0.0, 1.0 - distance / half_diagonal)
