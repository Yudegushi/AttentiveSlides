"""Pure learner-facing state mapping for the unified voice panel."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoicePanelView:
    state: str
    title: str
    detail: str
    transcript: str
    target_label: str | None
    target_state: str
    busy: bool
    retryable: bool


def build_voice_panel_view(
    *,
    speech_mode: str,
    turn_phase: str,
    transcript: str,
    target_label: str | None,
    target_needs_confirmation: bool,
    error_code: str | None = None,
) -> VoicePanelView:
    phase = str(turn_phase or "").strip().lower()
    if not phase:
        phase = "listening" if speech_mode == "continuous" else "ready"
    copy = {
        "study_paused": ("Study paused", ""),
        "typed": ("Typed input ready", "Choose a prompt or ask below"),
        "ready": ("Ready", "Hold V or the button to speak"),
        "listening": ("Listening for speech", "Hands-free input is active"),
        "paused": ("Listening paused", "Resume when you are ready"),
        "sampling": ("Recording", "Sampling attention"),
        "recording": ("Recording", "Sampling attention"),
        "speech_detected": ("Speech detected", "Sampling attention"),
        "transcribing": ("Transcribing", "Preparing your question"),
        "resolving": ("Resolving target", "Matching gaze evidence to this slide"),
        "confirmation": ("Target needs confirmation", "Choose the intended region"),
        "locked": ("Target locked", "Attention evidence is resolved"),
        "answering": ("Answering", "Generating a grounded explanation"),
        "playing": ("Tutor speaking", "You can interrupt in Realtime"),
    }
    if error_code:
        title, detail = {
            "too_short": ("Try again", "Hold V and speak a little longer"),
            "empty_transcript": ("Try again", "No speech was detected"),
            "stt_failed": ("Try again", "Speech could not be transcribed"),
            "tutor_failed": ("Tutor unavailable", "Retry the answer below"),
        }.get(
            str(error_code),
            ("Voice input needs attention", "Check the input and try again"),
        )
        phase = "error"
    else:
        title, detail = copy.get(
            phase,
            ("Preparing voice", "Connecting the current input mode"),
        )
    target_state = (
        "needs_confirmation"
        if target_needs_confirmation
        else "locked"
        if target_label
        else "sampling"
        if phase in {"sampling", "recording", "speech_detected"}
        else "waiting"
    )
    return VoicePanelView(
        state=phase or "preparing",
        title=title,
        detail=detail,
        transcript=" ".join(str(transcript or "").split()),
        target_label=target_label,
        target_state=target_state,
        busy=phase in {
            "sampling",
            "recording",
            "speech_detected",
            "transcribing",
            "resolving",
            "answering",
            "playing",
        },
        retryable=error_code in {
            "too_short",
            "empty_transcript",
            "stt_failed",
        },
    )
