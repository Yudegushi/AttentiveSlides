"""Evaluate file-based audio transcription through the AttentiveSlides pipeline."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.audio.faster_whisper_transcriber import FasterWhisperTranscriber
from modules.audio.mock_transcriber import MockTranscriber
from modules.audio.transcriber import SpeechToTextTranscriber, TranscriptionConfig
from modules.common.schemas import GazePrediction, LearningState
from modules.system.adapters import MockManifestSlideProvider, SensingFrame, build_pipeline_input_bundle, run_interaction_from_bundle
from modules.system.audio_adapters import AudioFileTranscriptProvider


SENSING_PRESETS = {
    "high_confidence_right_figure": GazePrediction(5, "middle_right", "right_figure", 0.76, stable_duration_sec=2.3),
    "medium_confidence_right_figure": GazePrediction(
        5,
        "bottom_right",
        "right_figure",
        0.55,
        stable_duration_sec=1.8,
        alternative_targets=[
            {"aoi_id": "right_figure", "score": 0.55},
            {"aoi_id": "bottom_caption", "score": 0.51},
        ],
    ),
    "low_confidence_formula": GazePrediction(5, "bottom_left", "bottom_formula", 0.2, stable_duration_sec=0.4),
    "no_gaze": GazePrediction(5, "middle_center", None, 0.0),
}


class PresetSensingProvider:
    def __init__(self, preset_name: str, screen_facing_score: float = 1.0) -> None:
        if preset_name not in SENSING_PRESETS:
            raise ValueError(f"Unknown sensing preset: {preset_name}")
        self.preset_name = preset_name
        self.screen_facing_score = screen_facing_score

    def get_sensing_frame(self, slide_id: int) -> SensingFrame:
        gaze = SENSING_PRESETS[self.preset_name]
        if gaze.slide_id != slide_id:
            gaze = GazePrediction(
                slide_id=slide_id,
                gaze_grid=gaze.gaze_grid,
                predicted_aoi_id=gaze.predicted_aoi_id,
                confidence=gaze.confidence,
                stable_duration_sec=gaze.stable_duration_sec,
                alternative_targets=list(gaze.alternative_targets),
            )
        return SensingFrame(
            gaze_prediction=gaze,
            learning_state=LearningState(screen_facing_score=self.screen_facing_score),
        )


def load_audio_eval_manifest(manifest_path: str | Path) -> dict[str, Any]:
    with Path(manifest_path).open("r", encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest.get("cases"), list):
        raise ValueError("Audio eval manifest must contain a cases list.")
    return manifest


def character_error_rate(reference: str, hypothesis: str) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return _edit_distance(list(reference), list(hypothesis)) / len(reference)


def evaluate_manifest(
    manifest_path: str | Path,
    engine: str,
    model_size: str,
    device: str,
    compute_type: str,
    language: str | None = None,
    beam_size: int = 1,
    vad_filter: bool = True,
) -> dict[str, Any]:
    manifest = load_audio_eval_manifest(manifest_path)
    config = TranscriptionConfig(
        engine=engine,
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        language=language,
        beam_size=beam_size,
        vad_filter=vad_filter,
    )
    transcriber = _build_transcriber(config)
    slide_provider = MockManifestSlideProvider()

    case_results = [
        _evaluate_case(case, config, transcriber, slide_provider)
        for case in manifest["cases"]
    ]
    return _build_summary(manifest, config, case_results)


def _evaluate_case(
    case: dict[str, Any],
    config: TranscriptionConfig,
    transcriber: SpeechToTextTranscriber,
    slide_provider: MockManifestSlideProvider,
) -> dict[str, Any]:
    start = time.perf_counter()
    audio_path = str(case["audio_path"])
    expected_transcript = str(case.get("expected_transcript", ""))
    transcript_provider = AudioFileTranscriptProvider(audio_path, transcriber)
    bundle = build_pipeline_input_bundle(
        slide_provider=slide_provider,
        transcript_provider=transcript_provider,
        sensing_provider=PresetSensingProvider(str(case.get("sensing_preset", "high_confidence_right_figure"))),
        slide_id=int(case.get("slide_id", 5)),
    )
    result = run_interaction_from_bundle(bundle, confirmed_aoi_id=case.get("confirmed_aoi_id"))
    transcript = transcript_provider.get_transcript()
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    expected_intent = case.get("expected_intent")
    expected_resolved_aoi_id = case.get("expected_resolved_aoi_id")
    cer = character_error_rate(expected_transcript, transcript.text)
    return {
        "case_id": str(case["case_id"]),
        "audio_path": audio_path,
        "expected_transcript": expected_transcript,
        "actual_transcript": transcript.text,
        "language": transcript.language,
        "confidence": transcript.confidence,
        "cer": round(cer, 4),
        "latency_ms": latency_ms,
        "transcript_usable": bool(transcript.text.strip()),
        "intent": result.resolved_query.intent,
        "expected_intent": expected_intent,
        "intent_match": None if expected_intent is None else result.resolved_query.intent == expected_intent,
        "resolved_aoi_id": result.resolved_query.resolved_aoi_id,
        "expected_resolved_aoi_id": expected_resolved_aoi_id,
        "resolved_aoi_match": (
            None
            if expected_resolved_aoi_id is None
            else result.resolved_query.resolved_aoi_id == expected_resolved_aoi_id
        ),
        "confirmation_mode": result.resolved_query.confirmation_mode,
        "response_mode": result.tutor_response.response_mode,
        "pipeline_success": True,
        "resolved_query": asdict(result.resolved_query),
    }


def _build_summary(
    manifest: dict[str, Any],
    config: TranscriptionConfig,
    case_results: list[dict[str, Any]],
) -> dict[str, Any]:
    case_count = len(case_results)
    return {
        "dataset": manifest.get("dataset"),
        "language": manifest.get("language"),
        "source": manifest.get("source"),
        "license": manifest.get("license"),
        "engine": config.engine,
        "model_size": config.model_size,
        "device": config.device,
        "compute_type": config.compute_type,
        "case_count": case_count,
        "pipeline_success_count": sum(1 for item in case_results if item["pipeline_success"]),
        "transcript_usable_rate": _mean_bool(item["transcript_usable"] for item in case_results),
        "intent_accuracy": _mean_optional_bool(item["intent_match"] for item in case_results),
        "resolved_aoi_accuracy": _mean_optional_bool(item["resolved_aoi_match"] for item in case_results),
        "mean_cer": round(_mean(item["cer"] for item in case_results), 4),
        "mean_latency_ms": round(_mean(item["latency_ms"] for item in case_results), 2),
        "cases": case_results,
    }


def _build_transcriber(config: TranscriptionConfig) -> SpeechToTextTranscriber:
    if config.engine == "mock":
        return MockTranscriber()
    if config.engine == "faster_whisper":
        return FasterWhisperTranscriber(config)
    raise ValueError(f"Unsupported STT engine: {config.engine}")


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for ref_index, ref_item in enumerate(reference, start=1):
        current = [ref_index]
        for hyp_index, hyp_item in enumerate(hypothesis, start=1):
            substitution_cost = 0 if ref_item == hyp_item else 1
            current.append(
                min(
                    previous[hyp_index] + 1,
                    current[hyp_index - 1] + 1,
                    previous[hyp_index - 1] + substitution_cost,
                )
            )
        previous = current
    return previous[-1]


def _mean(values: Any) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _mean_bool(values: Any) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(1 for item in items if item) / len(items)


def _mean_optional_bool(values: Any) -> float | None:
    items = [item for item in values if item is not None]
    if not items:
        return None
    return sum(1 for item in items if item) / len(items)


def main() -> None:
    args = _parse_args()
    summary = evaluate_manifest(
        manifest_path=args.manifest,
        engine=args.engine,
        model_size=args.model_size,
        device=args.device,
        compute_type=args.compute_type,
        language=args.language,
        beam_size=args.beam_size,
        vad_filter=not args.no_vad_filter,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate audio STT through the AttentiveSlides pipeline.")
    parser.add_argument("--manifest", required=True, help="Path to audio eval manifest JSON.")
    parser.add_argument("--engine", choices=["mock", "faster_whisper"], default="faster_whisper")
    parser.add_argument("--model", dest="model_size", default="small")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--language")
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--no-vad-filter", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
