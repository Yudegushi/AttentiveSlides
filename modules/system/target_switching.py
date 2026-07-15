"""Explicit, gaze-safe target switching for voice turns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from threading import RLock

from modules.realtime.realtime_contracts import TargetBinding


STRONG_SWITCH_PATTERNS = (
    "换到",
    "切换到",
    "讲这个",
    "讲这里",
    "看这里",
    "看这个",
    "switch to",
    "talk about this",
    "look at this",
)
WEAK_DEICTIC_PATTERNS = (
    "这个呢",
    "这里呢",
    "那这个",
    "what about this",
    "this one",
)
CONFIRM_PATTERNS = ("对", "是的", "确认", "切换", "yes", "confirm")
REJECT_PATTERNS = (
    "不对",
    "不是",
    "不换",
    "不用换",
    "不要切换",
    "不想换",
    "继续刚才",
    "no",
    "cancel",
)


class SwitchIntent(str, Enum):
    KEEP = "keep"
    PROPOSE = "propose"
    CONFIRM = "confirm"
    REJECT = "reject"


@dataclass(frozen=True)
class TargetSwitchProposal:
    previous: TargetBinding
    candidate: TargetBinding
    transcript: str


@dataclass(frozen=True)
class TargetDecision:
    intent: SwitchIntent
    active_target: TargetBinding
    pending: TargetSwitchProposal | None
    should_create_response: bool
    user_message: str | None


def _normalize(transcript: str) -> str:
    return " ".join(str(transcript).strip().lower().split())


def _contains_any(transcript: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern.isascii():
            if re.search(
                rf"(?<![a-z0-9_]){re.escape(pattern)}(?![a-z0-9_])",
                transcript,
            ):
                return True
        elif pattern in transcript:
            return True
    return False


class TargetSwitchController:
    """Keeps gaze candidates separate from the confirmed active target."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._active_target: TargetBinding | None = None
        self._candidate: TargetBinding | None = None
        self._pending: TargetSwitchProposal | None = None

    @property
    def active_target(self) -> TargetBinding | None:
        with self._lock:
            return self._active_target

    @property
    def candidate(self) -> TargetBinding | None:
        with self._lock:
            return self._candidate

    @property
    def pending(self) -> TargetSwitchProposal | None:
        with self._lock:
            return self._pending

    def bind(self, target: TargetBinding) -> None:
        with self._lock:
            changed = self._active_target is None or self._active_target.signature != target.signature
            self._active_target = target
            if changed:
                self._candidate = None
                self._pending = None

    def observe_candidate(self, candidate: TargetBinding | None) -> None:
        with self._lock:
            self._candidate = candidate

    def handle_transcript(self, transcript: str) -> TargetDecision:
        normalized = _normalize(transcript)
        with self._lock:
            active = self._require_active()
            if self._pending is not None:
                if _contains_any(normalized, REJECT_PATTERNS):
                    return self._reject_locked()
                if _contains_any(normalized, CONFIRM_PATTERNS):
                    return self._confirm_locked()
                return TargetDecision(
                    intent=SwitchIntent.PROPOSE,
                    active_target=active,
                    pending=self._pending,
                    should_create_response=False,
                    user_message=self._proposal_message(self._pending.candidate),
                )

            candidate = self._candidate
            is_different = candidate is not None and candidate.signature != active.signature
            if _contains_any(normalized, STRONG_SWITCH_PATTERNS):
                if is_different:
                    return self._propose_locked(active, candidate, normalized)
                return TargetDecision(
                    intent=SwitchIntent.KEEP,
                    active_target=active,
                    pending=None,
                    should_create_response=False,
                    user_message="请先注视或手动选择要切换的目标。",
                )
            if _contains_any(normalized, WEAK_DEICTIC_PATTERNS) and is_different:
                return self._propose_locked(active, candidate, normalized)
            return TargetDecision(
                intent=SwitchIntent.KEEP,
                active_target=active,
                pending=None,
                should_create_response=True,
                user_message=None,
            )

    def confirm(self) -> TargetDecision:
        with self._lock:
            return self._confirm_locked()

    def reject(self) -> TargetDecision:
        with self._lock:
            return self._reject_locked()

    def clear(self) -> None:
        with self._lock:
            self._active_target = None
            self._candidate = None
            self._pending = None

    def _require_active(self) -> TargetBinding:
        if self._active_target is None:
            raise RuntimeError("no active target is bound")
        return self._active_target

    def _propose_locked(
        self,
        active: TargetBinding,
        candidate: TargetBinding,
        transcript: str,
    ) -> TargetDecision:
        self._pending = TargetSwitchProposal(
            previous=active,
            candidate=candidate,
            transcript=transcript,
        )
        return TargetDecision(
            intent=SwitchIntent.PROPOSE,
            active_target=active,
            pending=self._pending,
            should_create_response=False,
            user_message=self._proposal_message(candidate),
        )

    def _confirm_locked(self) -> TargetDecision:
        active = self._require_active()
        if self._pending is None:
            return TargetDecision(SwitchIntent.KEEP, active, None, False, "当前没有待确认的目标切换。")
        active = self._pending.candidate
        self._active_target = active
        self._candidate = active
        self._pending = None
        return TargetDecision(
            SwitchIntent.CONFIRM,
            active,
            None,
            False,
            f"已切换到：{active.label or active.target_id}",
        )

    def _reject_locked(self) -> TargetDecision:
        active = self._require_active()
        self._pending = None
        return TargetDecision(
            SwitchIntent.REJECT,
            active,
            None,
            False,
            "已保留当前目标。",
        )

    @staticmethod
    def _proposal_message(candidate: TargetBinding) -> str:
        return f"是否切换到：{candidate.label or candidate.target_id}？"
