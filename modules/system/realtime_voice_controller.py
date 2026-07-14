"""Thread-safe Streamlit boundary for realtime voice."""

from __future__ import annotations

import os
from typing import Any

from modules.media.realtime_voice_gateway import (
    RealtimeVoiceGateway,
)
from modules.system.realtime_tutor_context import (
    RealtimeTutorContext,
)


class RealtimeVoiceController:
    def __init__(
        self,
        gateway: RealtimeVoiceGateway,
    ) -> None:
        self.gateway = gateway

    def ensure_started(
        self,
    ) -> None:
        self.gateway.ensure_started()

    def capture_url(
        self,
        *,
        view: str,
    ) -> str:
        self.ensure_started()

        return self.gateway.capture_url(
            view=view
        )

    def snapshot(
        self,
    ) -> dict[str, Any]:
        return self.gateway.snapshot()

    def update_context(
        self,
        context: RealtimeTutorContext,
    ) -> None:
        self.gateway.runtime.update_context(
            context
        )

    def refresh_cloud_status(
        self,
    ) -> None:
        self.gateway.runtime.set_cloud_available(
            bool(
                os.environ.get(
                    "DASHSCOPE_API_KEY"
                )
            )
        )


def build_realtime_voice_controller(
) -> RealtimeVoiceController:
    return RealtimeVoiceController(
        RealtimeVoiceGateway()
    )
