"""Device and interaction-mode state."""

from __future__ import annotations

from modules.realtime.realtime_contracts import (
    DeviceState,
)


def derive_interaction_mode(
    *,
    camera_enabled: bool,
    microphone_enabled: bool,
) -> str:
    return (
        "hybrid"
        if (
            camera_enabled
            or microphone_enabled
        )
        else "manual"
    )


def toggle_camera(
    state: DeviceState,
) -> DeviceState:
    return DeviceState(
        camera_enabled=(
            not state.camera_enabled
        ),
        microphone_enabled=(
            state.microphone_enabled
        ),
        microphone_permission=(
            state.microphone_permission
        ),
    )


def microphone_enabled_state(
    state: DeviceState,
    *,
    enabled: bool,
    permission: str,
) -> DeviceState:
    effective_enabled = bool(
        enabled
        and permission == "granted"
    )

    return DeviceState(
        camera_enabled=(
            state.camera_enabled
        ),
        microphone_enabled=(
            effective_enabled
        ),
        microphone_permission=permission,
    )
