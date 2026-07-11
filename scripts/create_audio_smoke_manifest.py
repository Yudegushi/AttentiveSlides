"""Create a reviewable CSV manifest for locally recorded audio smoke samples."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDNAMES = ("case_id", "audio_path", "expected_text", "scenario")


def create_manifest_rows(audio_dir: str | Path) -> list[dict[str, str]]:
    directory = Path(audio_dir)
    audio_paths = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".m4a"),
        key=lambda path: path.name.casefold(),
    )
    if not audio_paths:
        raise ValueError(f"No .m4a files found in {directory}.")

    return [_manifest_row(audio_path) for audio_path in audio_paths]


def write_manifest(rows: list[dict[str, str]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _manifest_row(audio_path: Path) -> dict[str, str]:
    filename_stem = audio_path.stem
    expected_text = filename_stem.replace("-", " ")
    return {
        "case_id": filename_stem.replace("-", "_"),
        "audio_path": audio_path.as_posix(),
        "expected_text": expected_text,
        "scenario": infer_scenario(filename_stem),
    }


def infer_scenario(filename_stem: str) -> str:
    name = filename_stem.casefold()
    if "explain" in name and "this" in name:
        return "explain_deictic"
    if "right" in name:
        return "explain_explicit_right"
    if "summarize" in name:
        return "summarize_whole_slide"
    if "quiz" in name or "test" in name:
        return "quiz_deictic"
    if "compare" in name or "difference" in name:
        return "compare_deictic"
    if "simple" in name or "simplify" in name:
        return "simplify_current"
    if "step" in name:
        return "step_by_step_current"
    if "review" in name:
        return "review_whole_slide"
    if "tired" in name or "break" in name:
        return "break_or_short_recap"
    return "unknown"


def main() -> None:
    args = _parse_args()
    rows = create_manifest_rows(args.audio_dir)
    write_manifest(rows, args.output)
    print(f"Wrote {len(rows)} audio smoke cases to {args.output}.")
    print(f"Review {args.output}: confirm expected_text and scenario before running evaluation.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a CSV manifest from local .m4a audio samples.")
    parser.add_argument("--audio-dir", required=True, help="Directory containing local .m4a recordings.")
    parser.add_argument("--output", required=True, help="Output CSV manifest path.")
    return parser.parse_args()


if __name__ == "__main__":
    main()
