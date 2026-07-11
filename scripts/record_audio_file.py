"""Record a short local microphone sample to a wav file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.audio.recording import record_wav


def main() -> None:
    args = _parse_args()
    if not args.dry_run:
        record_wav(args.output, duration_sec=args.duration, sample_rate=args.sample_rate)

    payload = {
        "audio_path": args.output,
        "duration_sec": args.duration,
        "sample_rate": args.sample_rate,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a short microphone wav file.")
    parser.add_argument("--output", default="data/audio_samples/recorded/latest.wav")
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


if __name__ == "__main__":
    main()
