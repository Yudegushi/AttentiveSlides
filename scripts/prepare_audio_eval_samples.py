"""Download a small public zh-CN audio evaluation set from PolyAI/minds14."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_OUTPUT_DIR = Path("data/audio_eval/minds14_zh_cn")


def prepare_minds14_zh_cn_samples(
    limit: int = 20,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    try:
        from datasets import Audio, load_dataset
        import soundfile as sf
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Install optional audio evaluation dependencies first: "
            "pip install -r requirements.txt"
        ) from exc

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    dataset = load_dataset("PolyAI/minds14", "zh-CN", split=f"train[:{limit}]")
    dataset = dataset.cast_column("audio", Audio(decode=False))

    rows = []
    for index, item in enumerate(dataset):
        case_id = f"minds14_zh_cn_{index:04d}"
        audio_path = output_path / f"{case_id}.wav"
        audio = item["audio"]
        if audio.get("bytes") is not None:
            audio_path.write_bytes(audio["bytes"])
        elif audio.get("array") is not None:
            sf.write(audio_path, audio["array"], audio["sampling_rate"])
        else:
            source_path = Path(audio["path"])
            audio_path.write_bytes(source_path.read_bytes())
        rows.append(
            {
                "case_id": case_id,
                "audio_path": audio_path.as_posix(),
                "expected_transcript": str(item["transcription"]),
            }
        )

    manifest = build_manifest(rows)
    manifest_path = output_path / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return manifest


def build_manifest(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "dataset": "PolyAI/minds14",
        "config": "zh-CN",
        "language": "zh-CN",
        "source": "https://huggingface.co/datasets/PolyAI/minds14",
        "license": "cc-by-4.0",
        "cases": [
            {
                "case_id": row["case_id"],
                "audio_path": row["audio_path"],
                "expected_transcript": row["expected_transcript"],
                "expected_intent": "unknown",
                "expected_resolved_aoi_id": None,
                "sensing_preset": "high_confidence_right_figure",
                "slide_id": 5,
            }
            for row in rows
        ],
    }


def main() -> None:
    args = _parse_args()
    manifest = prepare_minds14_zh_cn_samples(limit=args.limit, output_dir=args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download PolyAI/minds14 zh-CN samples for audio evaluation.")
    parser.add_argument("--limit", type=int, default=20, help="Number of zh-CN samples to download.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for wav files and manifest.")
    return parser.parse_args()


if __name__ == "__main__":
    main()
