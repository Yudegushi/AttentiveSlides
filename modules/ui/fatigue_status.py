"""Pure presentation mapping for the informational fatigue reminder."""

from __future__ import annotations

from dataclasses import dataclass

from modules.fatigue import FatigueSnapshot


@dataclass(frozen=True)
class FatigueStatusView:
    probability_text: str
    show_alert: bool
    alert_text: str = "检测到持续疲劳迹象，建议短暂休息。"


def build_fatigue_status_view(
    snapshot: FatigueSnapshot,
    *,
    live_enabled: bool,
) -> FatigueStatusView:
    if not live_enabled:
        return FatigueStatusView(
            "疲劳概率（模型估计）：--（Live 未开启）",
            False,
        )
    if snapshot.status == "unavailable":
        return FatigueStatusView(
            "疲劳概率（模型估计）：--（模型不可用）",
            False,
        )
    if snapshot.status != "ready" or snapshot.smoothed_probability is None:
        return FatigueStatusView(
            "疲劳概率（模型估计）：--（等待有效人脸）",
            False,
        )
    percent = round(snapshot.smoothed_probability * 100)
    return FatigueStatusView(
        f"疲劳概率（模型估计）：{percent}%",
        snapshot.alert_active,
    )
