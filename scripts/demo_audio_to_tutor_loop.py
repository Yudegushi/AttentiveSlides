"""Run file-based audio through the existing AttentiveSlides tutor pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.audio.faster_whisper_transcriber import FasterWhisperTranscriber
from modules.audio.model_policy import available_profiles, transcription_config_for_profile
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


def main() -> None:
    args = _parse_args()
    config = _build_config(args)
    transcriber = _build_transcriber(config)
    transcript_provider = AudioFileTranscriptProvider(args.audio, transcriber)
    bundle = build_pipeline_input_bundle(
        slide_provider=MockManifestSlideProvider(),
        transcript_provider=transcript_provider,
        sensing_provider=PresetSensingProvider(args.sensing_preset, args.screen_facing_score),
        slide_id=args.slide_id,
    )
    result = run_interaction_from_bundle(bundle, confirmed_aoi_id=args.confirmed_aoi_id)
    transcript = transcript_provider.get_transcript()
    payload = {
        "transcript": {
            **asdict(transcript),
            "source": "audio_file",
            "audio_path": args.audio,
            "engine": config.engine,
            "model_size": config.model_size,
            "device": config.device,
            "compute_type": config.compute_type,
            "language": config.language,
            "beam_size": config.beam_size,
        },
        "resolved_query": asdict(result.resolved_query),
        "tutor_response": asdict(result.tutor_response),
        "ui_state": asdict(result.ui_state),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run audio -> Transcript -> tutor pipeline with mock sensing.")
    parser.add_argument("--audio", required=True, help="Path to .wav/.mp3/.m4a audio.")
    parser.add_argument("--engine", choices=["mock", "faster_whisper"], default="faster_whisper")
    parser.add_argument("--profile", choices=available_profiles(), default="balanced")
    parser.add_argument("--model", dest="model_size")
    parser.add_argument("--device")
    parser.add_argument("--compute-type")
    parser.add_argument("--language")
    parser.add_argument("--beam-size", type=int)
    parser.add_argument("--no-vad-filter", action="store_true")
    parser.add_argument("--sensing-preset", choices=sorted(SENSING_PRESETS), default="high_confidence_right_figure")
    parser.add_argument("--screen-facing-score", type=float, default=1.0)
    parser.add_argument("--slide-id", type=int, default=5)
    parser.add_argument("--confirmed-aoi-id")
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> TranscriptionConfig:
    profile_config = transcription_config_for_profile(args.profile)
    return TranscriptionConfig(
        engine=args.engine,
        model_size=args.model_size or profile_config.model_size,
        device=args.device or profile_config.device,
        compute_type=args.compute_type or profile_config.compute_type,
        language=args.language or profile_config.language,
        beam_size=args.beam_size if args.beam_size is not None else profile_config.beam_size,
        vad_filter=not args.no_vad_filter,
    )


def _build_transcriber(config: TranscriptionConfig) -> SpeechToTextTranscriber:
    if config.engine == "mock":
        return MockTranscriber()
    if config.engine == "faster_whisper":
        return FasterWhisperTranscriber(config)
    raise ValueError(f"Unsupported STT engine: {config.engine}")


if __name__ == "__main__":
    main()
