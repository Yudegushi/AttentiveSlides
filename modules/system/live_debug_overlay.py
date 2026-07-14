"""Resolve the current authoritative AOI used only by the debug overlay."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from modules.system.live_ui_bridge import LiveInteractionProposal


def resolve_live_debug_aoi_id(
    *,
    deck_id: str,
    slide_id: int,
    valid_aoi_ids: Collection[str],
    proposal: LiveInteractionProposal | None,
    confirmed_interaction: Mapping[str, object] | None,
) -> str | None:
    valid = {str(aoi_id) for aoi_id in valid_aoi_ids}
    confirmed = confirmed_interaction or {}
    interaction = confirmed.get("interaction")
    target = confirmed.get("selected_target")
    if isinstance(interaction, Mapping) and isinstance(target, Mapping):
        confirmed_id = str(target.get("aoi_id") or "")
        try:
            confirmed_slide_id = int(interaction.get("slide_id", -1))
        except (TypeError, ValueError):
            confirmed_slide_id = -1
        if (
            str(interaction.get("deck_id") or "") == deck_id
            and confirmed_slide_id == slide_id
            and confirmed_id in valid
        ):
            return confirmed_id

    if (
        isinstance(proposal, LiveInteractionProposal)
        and proposal.deck_id == deck_id
        and proposal.slide_id == slide_id
        and proposal.transcript.strip()
        and proposal.predicted_aoi_id in valid
    ):
        return proposal.predicted_aoi_id
    return None
