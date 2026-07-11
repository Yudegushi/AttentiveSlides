"""Evaluate reviewed project-specific audio CSV manifests through the tutor pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.eval_audio_pipeline import PresetSensingProvider, character_error_rate
from modules.audio.faster_whisper_transcriber import FasterWhisperTranscriber
from modules.audio.mock_transcriber import MockTranscriber
from modules.audio.model_policy import available_profiles, transcription_config_for_profile
from modules.audio.transcriber import SpeechToTextTranscriber, TranscriptionConfig
from modules.common.schemas import Transcript
from modules.interaction.intent_parser import parse_intent
from modules.system.adapters import MockManifestSlideProvider, build_pipeline_input_bundle, run_interaction_from_bundle


MANIFEST_FIELDS = ("case_id", "audio_path", "expected_text", "scenario")
SCENARIO_REFERENCE_TEXTS = {
    "explain_deictic": "explain this",
    "explain_explicit_right": "explain right figure",
    "summarize_whole_slide": "summarize this slide",
    "quiz_deictic": "quiz this",
    "compare_deictic": "compare this",
    "simplify_current": "simplify this",
    "step_by_step_current": "walk me through this",
    "review_whole_slide": "review this slide",
    "break_or_short_recap": "I need a break",
}


class StaticTranscriptProvider:
    """Adapter that feeds an already-transcribed utterance into the existing pipeline."""

    def __init__(self, transcript: Transcript) -> None:
        self.transcript = transcript

    def get_transcript(self) -> Transcript:
        return self.transcript


def load_audio_usability_manifest(manifest_path: str | Path) -> list[dict[str, str]]:
    with Path(manifest_path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != MANIFEST_FIELDS:
            expected = ", ".join(MANIFEST_FIELDS)
            raise ValueError(f"Audio usability manifest must use fields: {expected}")
        rows = [{field: str(row[field]).strip() for field in MANIFEST_FIELDS} for row in reader]

    if not rows:
        raise ValueError("Audio usability manifest must contain at least one case.")
    if any(not row["case_id"] or not row["audio_path"] or not row["expected_text"] for row in rows):
        raise ValueError("Each audio usability case needs case_id, audio_path, and expected_text.")
    return rows


def evaluate_audio_usability_manifest(
    manifest_path: str | Path,
    engine: str,
    profile: str,
    *,
    audio_root: str | Path | None = None,
    language: str = "en",
    transcriber: SpeechToTextTranscriber | None = None,
) -> dict[str, Any]:
    """Compare STT-derived semantics against the user-reviewed expected transcript."""
    config = replace(transcription_config_for_profile(profile), engine=engine, language=language)
    cases = load_audio_usability_manifest(manifest_path)
    active_transcriber = transcriber or _build_transcriber(config)
    slide_provider = MockManifestSlideProvider()
    case_results = [
        _evaluate_case(case, active_transcriber, slide_provider, audio_root, language)
        for case in cases
    ]
    return _build_summary(case_results, config, profile, language)


def _evaluate_case(
    case: dict[str, str],
    transcriber: SpeechToTextTranscriber,
    slide_provider: MockManifestSlideProvider,
    audio_root: str | Path | None,
    language: str,
) -> dict[str, Any]:
    audio_path = _resolve_audio_path(case["audio_path"], audio_root)
    start = time.perf_counter()
    transcription_start = time.perf_counter()
    transcript = transcriber.transcribe(audio_path)
    transcription_latency_ms = (time.perf_counter() - transcription_start) * 1000

    expected_transcript = Transcript(text=case["expected_text"], language=language)
    semantic_reference = Transcript(
        text=SCENARIO_REFERENCE_TEXTS.get(case["scenario"], expected_transcript.text),
        language=language,
    )
    expected_result = _run_pipeline(expected_transcript, slide_provider)
    actual_result = _run_pipeline(transcript, slide_provider)
    end_to_end_latency_ms = (time.perf_counter() - start) * 1000

    expected_intent = parse_intent(semantic_reference)
    expected_text_intent = parse_intent(expected_transcript)
    actual_intent = parse_intent(transcript)
    return {
        "case_id": case["case_id"],
        "scenario": case["scenario"],
        "audio_path": audio_path,
        "expected_text": expected_transcript.text,
        "intent_reference_text": semantic_reference.text,
        "actual_transcript": transcript.text,
        "transcript_language": transcript.language,
        "transcript_usable": bool(transcript.text.strip()),
        "cer": round(character_error_rate(expected_transcript.text, transcript.text), 4),
        "intent": actual_intent.intent,
        "expected_intent": expected_intent.intent,
        "intent_match": actual_intent.intent == expected_intent.intent,
        "has_deictic_reference": actual_intent.has_deictic_reference,
        "expected_has_deictic_reference": expected_text_intent.has_deictic_reference,
        "deictic_detection_match": (
            actual_intent.has_deictic_reference == expected_text_intent.has_deictic_reference
        ),
        "explicit_target_hint": actual_intent.explicit_target_hint,
        "expected_explicit_target_hint": expected_text_intent.explicit_target_hint,
        "explicit_target_hint_match": (
            actual_intent.explicit_target_hint == expected_text_intent.explicit_target_hint
        ),
        "confirmation_mode": actual_result.resolved_query.confirmation_mode,
        "expected_confirmation_mode": expected_result.resolved_query.confirmation_mode,
        "confirmation_mode_match": (
            actual_result.resolved_query.confirmation_mode == expected_result.resolved_query.confirmation_mode
        ),
        "response_mode": actual_result.tutor_response.response_mode,
        "expected_response_mode": expected_result.tutor_response.response_mode,
        "response_mode_match": actual_result.tutor_response.response_mode == expected_result.tutor_response.response_mode,
        "transcription_latency_ms": round(transcription_latency_ms, 2),
        "end_to_end_latency_ms": round(end_to_end_latency_ms, 2),
    }


def _run_pipeline(transcript: Transcript, slide_provider: MockManifestSlideProvider):
    bundle = build_pipeline_input_bundle(
        slide_provider=slide_provider,
        transcript_provider=StaticTranscriptProvider(transcript),
        sensing_provider=PresetSensingProvider("high_confidence_right_figure"),
        slide_id=5,
    )
    return run_interaction_from_bundle(bundle)


def _resolve_audio_path(audio_path: str, audio_root: str | Path | None) -> str:
    path = Path(audio_path)
    if audio_root is not None:
        return str(Path(audio_root) / path.name)
    return str(path)


def _build_summary(
    case_results: list[dict[str, Any]],
    config: TranscriptionConfig,
    profile: str,
    language: str,
) -> dict[str, Any]:
    return {
        "engine": config.engine,
        "profile": profile,
        "language": language,
        "transcription_config": asdict(config),
        "case_count": len(case_results),
        "transcript_usable_rate": _mean_bool(item["transcript_usable"] for item in case_results),
        "mean_cer": round(_mean(item["cer"] for item in case_results), 4),
        "intent_accuracy": _mean_bool(item["intent_match"] for item in case_results),
        "deictic_detection_accuracy": _mean_bool(item["deictic_detection_match"] for item in case_results),
        "explicit_target_hint_accuracy": _mean_bool(
            item["explicit_target_hint_match"] for item in case_results
        ),
        "confirmation_mode_accuracy": _mean_bool(item["confirmation_mode_match"] for item in case_results),
        "response_mode_accuracy": _mean_bool(item["response_mode_match"] for item in case_results),
        "mean_transcription_latency_ms": round(
            _mean(item["transcription_latency_ms"] for item in case_results), 2
        ),
        "mean_end_to_end_latency_ms": round(
            _mean(item["end_to_end_latency_ms"] for item in case_results), 2
        ),
        "cases": case_results,
    }


def _build_transcriber(config: TranscriptionConfig) -> SpeechToTextTranscriber:
    if config.engine == "mock":
        return MockTranscriber(language=config.language or "en")
    if config.engine == "faster_whisper":
        return FasterWhisperTranscriber(config)
    raise ValueError(f"Unsupported STT engine: {config.engine}")


def _mean(values: Any) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _mean_bool(values: Any) -> float:
    items = list(values)
    return sum(1 for item in items if item) / len(items) if items else 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a reviewed project-specific audio CSV manifest.")
    parser.add_argument("--manifest", required=True, help="CSV with case_id,audio_path,expected_text,scenario.")
    parser.add_argument("--engine", choices=["mock", "faster_whisper"], default="faster_whisper")
    parser.add_argument("--profile", choices=available_profiles(), required=True)
    parser.add_argument("--audio-root", help="Directory holding audio after an evaluation-machine transfer.")
    parser.add_argument("--language", default="en", help="Known recording language; defaults to English.")
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary = evaluate_audio_usability_manifest(
        manifest_path=args.manifest,
        engine=args.engine,
        profile=args.profile,
        audio_root=args.audio_root,
        language=args.language,
    )
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
