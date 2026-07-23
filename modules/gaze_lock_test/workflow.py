"""Pure gaze-lock acquisition and typed-interaction workflow."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable, Mapping, Sequence
from uuid import uuid4

from modules.common.interaction_contracts import (
    ConfirmationInput,
    InteractionInput,
    IntentInput,
    TargetCandidate,
    TargetInput,
)
from modules.common.schemas import AOI
from modules.gaze_lock_test.contracts import (
    GazeLockEvent,
    GazeLockScope,
    LockedGazeTarget,
)
from modules.media.browser_gaze_source import BrowserPointGazeSample
from modules.system.point_gaze import (
    AggregatedPointGaze,
    match_point_to_visible_aois,
)


LOCK_WINDOW_SECONDS = 1.0
MINIMUM_DWELL_SECONDS = 0.15
MAX_SAMPLE_DWELL_SECONDS = 0.5


@dataclass(frozen=True)
class GazeLockAttempt:
    """Idempotent result returned for one component event."""

    status: str
    message: str
    event_id: str | None = None
    target: LockedGazeTarget | None = None


def canonical_aoi_identity(
    aois: Sequence[AOI],
    *,
    aoi_profile: str,
) -> str:
    """Return a stable identity for the AOI set and active profile."""
    payload = {
        "aoi_profile": str(aoi_profile).strip(),
        "aois": [
            {
                "aoi_id": aoi.aoi_id,
                "bbox": list(aoi.bbox),
                "type": aoi.type,
                "text": aoi.text,
                "name": aoi.name,
            }
            for aoi in sorted(aois, key=lambda item: item.aoi_id)
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def lock_is_current(
    target: LockedGazeTarget | None,
    scope: GazeLockScope | None,
) -> bool:
    """A lock survives reruns and gaze changes, but not identity changes."""
    return target is not None and scope is not None and target.scope == scope


def aggregate_preclick_gaze(
    samples: Sequence[BrowserPointGazeSample],
    aois: Sequence[AOI],
    *,
    clicked_at_browser_ms: float,
    scope: GazeLockScope,
    window_seconds: float = LOCK_WINDOW_SECONDS,
    minimum_dwell_seconds: float = MINIMUM_DWELL_SECONDS,
    max_sample_dwell_seconds: float = MAX_SAMPLE_DWELL_SECONDS,
) -> AggregatedPointGaze | None:
    """Aggregate only browser-time gaze at or before the lock click."""
    for name, value in (
        ("clicked_at_browser_ms", clicked_at_browser_ms),
        ("window_seconds", window_seconds),
        ("minimum_dwell_seconds", minimum_dwell_seconds),
        ("max_sample_dwell_seconds", max_sample_dwell_seconds),
    ):
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite.")
    if clicked_at_browser_ms < 0:
        raise ValueError("clicked_at_browser_ms must be non-negative.")
    if (
        window_seconds <= 0
        or minimum_dwell_seconds <= 0
        or max_sample_dwell_seconds <= 0
    ):
        raise ValueError("Gaze-lock dwell thresholds must be positive.")

    window_start_ms = clicked_at_browser_ms - window_seconds * 1000.0
    eligible = [
        sample
        for sample in samples
        if window_start_ms
        <= sample.browser_timestamp_ms
        <= clicked_at_browser_ms
        and _sample_matches_scope(sample, scope)
    ]
    eligible.sort(key=lambda sample: sample.browser_timestamp_ms)
    if not eligible:
        return None

    dwell_by_target: dict[str, float] = {}
    spatial_weight_by_target: dict[str, float] = {}
    for index, sample in enumerate(eligible):
        next_timestamp_ms = (
            eligible[index + 1].browser_timestamp_ms
            if index + 1 < len(eligible)
            else clicked_at_browser_ms
        )
        dwell = min(
            max_sample_dwell_seconds,
            max(
                0.0,
                (next_timestamp_ms - sample.browser_timestamp_ms) / 1000.0,
            ),
        )
        candidates = match_point_to_visible_aois(sample, aois)
        if not candidates or dwell <= 0:
            continue
        candidate = candidates[0]
        dwell_by_target[candidate.aoi_id] = (
            dwell_by_target.get(candidate.aoi_id, 0.0) + dwell
        )
        spatial_weight_by_target[candidate.aoi_id] = (
            spatial_weight_by_target.get(candidate.aoi_id, 0.0)
            + dwell * candidate.spatial_score
        )

    total_matched_dwell = sum(dwell_by_target.values())
    if total_matched_dwell < minimum_dwell_seconds:
        return None
    ranked = sorted(
        dwell_by_target.items(),
        key=lambda item: (-item[1], item[0]),
    )
    top_target, top_dwell = ranked[0]
    confidence = (
        top_dwell
        / total_matched_dwell
        * spatial_weight_by_target[top_target]
        / top_dwell
    )
    return AggregatedPointGaze(
        predicted_aoi_id=top_target,
        target_confidence=round(confidence, 3),
        stable_duration_sec=round(total_matched_dwell, 3),
        layout_revision=scope.layout_revision,
        alternatives=tuple(
            {
                "aoi_id": aoi_id,
                "score": round(dwell / total_matched_dwell, 3),
            }
            for aoi_id, dwell in ranked[:2]
        ),
        evidence=(
            f"pre-click point-gaze matched dwell={total_matched_dwell:.3f}s",
        ),
    )


def consume_lock_event(
    payload: Mapping[str, object] | None,
    *,
    seen_event_ids: Sequence[str],
    current_target: LockedGazeTarget | None,
    scope: GazeLockScope | None,
    samples: Sequence[BrowserPointGazeSample],
    aois: Sequence[AOI],
    server_clock: Callable[[], float] = time.time,
    lock_id_factory: Callable[[], str] = lambda: f"lock-{uuid4().hex}",
) -> GazeLockAttempt:
    """Consume one lock event without allowing an existing lock to drift."""
    if payload is None:
        return GazeLockAttempt(
            status="idle",
            message="Look steadily at an AOI, then lock the target.",
        )
    try:
        event = GazeLockEvent.from_component_value(payload)
    except (TypeError, ValueError) as exc:
        return GazeLockAttempt(status="invalid_event", message=str(exc))
    if event.event_id in set(seen_event_ids):
        return GazeLockAttempt(
            status="duplicate",
            message="This lock click was already processed.",
            event_id=event.event_id,
            target=current_target,
        )
    if current_target is not None:
        return GazeLockAttempt(
            status="already_locked",
            message="Retarget before acquiring a different AOI.",
            event_id=event.event_id,
            target=current_target,
        )
    if scope is None:
        return GazeLockAttempt(
            status="scope_unavailable",
            message="Current slide geometry is not ready. Look and retry.",
            event_id=event.event_id,
        )

    aggregate = aggregate_preclick_gaze(
        samples,
        aois,
        clicked_at_browser_ms=event.clicked_at_browser_ms,
        scope=scope,
    )
    if aggregate is None:
        return GazeLockAttempt(
            status="insufficient_gaze",
            message="No stable current AOI was found. Look steadily and retry.",
            event_id=event.event_id,
        )
    aoi_by_id = {aoi.aoi_id: aoi for aoi in aois}
    matched_aoi = aoi_by_id.get(aggregate.predicted_aoi_id)
    if matched_aoi is None:
        return GazeLockAttempt(
            status="insufficient_gaze",
            message="The gaze target is no longer in the current AOI set.",
            event_id=event.event_id,
        )
    target = LockedGazeTarget(
        lock_id=lock_id_factory(),
        scope=scope,
        aoi_id=matched_aoi.aoi_id,
        aoi_label=_aoi_label(matched_aoi),
        target_confidence=aggregate.target_confidence,
        stable_duration_sec=aggregate.stable_duration_sec,
        alternatives=tuple(dict(item) for item in aggregate.alternatives),
        clicked_at_browser_ms=event.clicked_at_browser_ms,
        locked_at_server=float(server_clock()),
    )
    return GazeLockAttempt(
        status="locked",
        message=f"Locked gaze target: {target.aoi_label}",
        event_id=event.event_id,
        target=target,
    )


def build_typed_interaction(
    target: LockedGazeTarget,
    *,
    question_text: str,
    interaction_id: str,
) -> InteractionInput:
    """Build the canonical B-mode typed/gaze interaction."""
    question = str(question_text).strip()
    if not question:
        raise ValueError("question_text must not be blank.")
    interaction_key = str(interaction_id).strip()
    if not interaction_key:
        raise ValueError("interaction_id must not be blank.")
    alternatives = tuple(
        TargetCandidate(
            aoi_id=str(item["aoi_id"]),
            score=float(item["score"]),
            evidence=("pre-click gaze dwell share",),
        )
        for item in target.alternatives
    )
    return InteractionInput(
        interaction_id=interaction_key,
        deck_id=target.deck_id,
        slide_id=target.slide_id,
        mode="hybrid",
        target=TargetInput(
            source="gaze_prediction",
            slide_id=target.slide_id,
            predicted_aoi_id=target.aoi_id,
            confidence=target.target_confidence,
            alternatives=alternatives,
            stable_duration_sec=target.stable_duration_sec,
        ),
        intent=IntentInput(
            source="typed_text",
            text=question,
        ),
        confirmation=ConfirmationInput(
            confirmed=True,
            source="explicit_user_confirmation",
            confirmed_aoi_id=target.aoi_id,
        ),
        metadata={
            "gaze_lock": {
                "lock_id": target.lock_id,
                "layout_revision": target.layout_revision,
                "target_confidence": target.target_confidence,
                "stable_duration_sec": target.stable_duration_sec,
                "clicked_at_browser_ms": target.clicked_at_browser_ms,
            }
        },
    )


def _sample_matches_scope(
    sample: BrowserPointGazeSample,
    scope: GazeLockScope,
) -> bool:
    if not sample.valid or not sample.face_detected or sample.geometry is None:
        return False
    geometry = sample.geometry.geometry
    return (
        geometry.deck_id == scope.deck_id
        and geometry.slide_id == scope.slide_id
        and geometry.layout_revision == scope.layout_revision
        and abs(geometry.viewport_width - sample.viewport_width) <= 1.0
        and abs(geometry.viewport_height - sample.viewport_height) <= 1.0
    )


def _aoi_label(aoi: AOI) -> str:
    for value in (aoi.name, aoi.text, aoi.type, aoi.aoi_id):
        if value is not None and str(value).strip():
            return str(value).strip()
    return aoi.aoi_id
