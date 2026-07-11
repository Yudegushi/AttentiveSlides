"""Compare project-specific STT evaluation summaries and recommend a demo profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SEMANTIC_METRICS = (
    "intent_accuracy",
    "deictic_detection_accuracy",
    "explicit_target_hint_accuracy",
    "confirmation_mode_accuracy",
    "response_mode_accuracy",
)
METRIC_LABELS = {
    "intent_accuracy": "Intent accuracy",
    "deictic_detection_accuracy": "Deictic detection",
    "explicit_target_hint_accuracy": "Explicit target hint",
    "confirmation_mode_accuracy": "Confirmation mode",
    "response_mode_accuracy": "Response mode",
    "mean_transcription_latency_ms": "Mean transcription latency (ms)",
    "mean_end_to_end_latency_ms": "Mean end-to-end latency (ms)",
}
PROFILE_ORDER = ("fast", "balanced", "accurate", "cpu")
SEMANTIC_TOLERANCE = 0.05
FAST_LATENCY_RATIO = 0.85
ACCURATE_MAX_LATENCY_RATIO = 2.0


def load_summaries(input_paths: list[str | Path]) -> list[dict[str, Any]]:
    summaries = []
    for input_path in input_paths:
        with Path(input_path).open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        if not isinstance(summary, dict) or not summary.get("profile"):
            raise ValueError(f"Invalid STT summary: {input_path}")
        summaries.append(summary)
    return summaries


def compare_profiles(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    by_profile = {str(summary["profile"]): summary for summary in summaries}
    if len(by_profile) != len(summaries):
        raise ValueError("Each STT profile may appear only once.")

    ordered_profiles = [profile for profile in PROFILE_ORDER if profile in by_profile]
    ordered_profiles.extend(sorted(set(by_profile) - set(ordered_profiles)))
    return {
        "profiles": [{"profile": profile, **by_profile[profile]} for profile in ordered_profiles],
        "recommendation": _recommend(by_profile),
    }


def _recommend(by_profile: dict[str, dict[str, Any]]) -> dict[str, str | None]:
    balanced = by_profile.get("balanced")
    fast = by_profile.get("fast")
    accurate = by_profile.get("accurate")

    if fast and balanced and _fast_is_close_and_faster(fast, balanced):
        return {
            "live_profile": "fast",
            "recorded_demo_profile": "fast",
            "reason": "fast keeps key semantic metrics close to balanced while lowering end-to-end latency.",
        }

    if balanced:
        recorded_profile = "balanced"
        reason = "balanced protects key semantic metrics when fast is not close enough."
        if accurate and _accurate_is_materially_better(accurate, balanced):
            recorded_profile = "accurate"
            reason += " accurate materially improves a key semantic metric within the recorded-demo latency limit."
        return {
            "live_profile": "balanced",
            "recorded_demo_profile": recorded_profile,
            "reason": reason,
        }

    if fast:
        return {
            "live_profile": "fast",
            "recorded_demo_profile": "fast",
            "reason": "balanced was not evaluated, so fast is the available GPU profile.",
        }

    if accurate:
        return {
            "live_profile": "accurate",
            "recorded_demo_profile": "accurate",
            "reason": "accurate is the only evaluated GPU profile.",
        }

    return {
        "live_profile": None,
        "recorded_demo_profile": None,
        "reason": "No GPU STT profile was evaluated; cpu remains fallback-only.",
    }


def _fast_is_close_and_faster(fast: dict[str, Any], balanced: dict[str, Any]) -> bool:
    semantic_close = all(
        float(fast[metric]) >= float(balanced[metric]) - SEMANTIC_TOLERANCE
        for metric in SEMANTIC_METRICS
    )
    balanced_latency = float(balanced["mean_end_to_end_latency_ms"])
    fast_latency = float(fast["mean_end_to_end_latency_ms"])
    clearly_faster = fast_latency <= balanced_latency * FAST_LATENCY_RATIO
    return semantic_close and clearly_faster


def _accurate_is_materially_better(accurate: dict[str, Any], balanced: dict[str, Any]) -> bool:
    semantic_improvement = any(
        float(accurate[metric]) >= float(balanced[metric]) + SEMANTIC_TOLERANCE
        for metric in SEMANTIC_METRICS
    )
    latency_acceptable = float(accurate["mean_end_to_end_latency_ms"]) <= (
        float(balanced["mean_end_to_end_latency_ms"]) * ACCURATE_MAX_LATENCY_RATIO
    )
    return semantic_improvement and latency_acceptable


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    profiles = comparison["profiles"]
    profile_names = [str(summary["profile"]) for summary in profiles]
    lines = ["# STT profile comparison", "", "| Metric | " + " | ".join(profile_names) + " |", "|---|" + "|".join("---:" for _ in profiles) + "|"]
    for metric in (*SEMANTIC_METRICS, "mean_transcription_latency_ms", "mean_end_to_end_latency_ms"):
        values = []
        for summary in profiles:
            value = summary[metric]
            values.append(f"{float(value):.1f}" if metric.endswith("_ms") else f"{float(value):.3f}")
        lines.append(f"| {METRIC_LABELS[metric]} | " + " | ".join(values) + " |")

    recommendation = comparison["recommendation"]
    lines.extend(
        [
            "",
            f"Recommended live profile: **{recommendation['live_profile'] or 'none'}**",
            "",
            f"Recommended recorded-demo profile: **{recommendation['recorded_demo_profile'] or 'none'}**",
            "",
            f"Rationale: {recommendation['reason']}",
            "",
            "CPU is fallback-only and is never selected as the primary demo profile.",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare project-specific STT profile summaries.")
    parser.add_argument("--inputs", nargs="+", required=True, help="JSON output files from eval_audio_usability.py.")
    parser.add_argument("--output", required=True, help="Markdown comparison output.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comparison = compare_profiles(load_summaries(args.inputs))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_comparison_markdown(comparison), encoding="utf-8")
    print(comparison["recommendation"]["reason"])


if __name__ == "__main__":
    main()
