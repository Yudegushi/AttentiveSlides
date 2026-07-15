#!/usr/bin/env python3
"""Explicitly install and validate the pinned MobileViT fatigue artifact."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from modules.fatigue.mobilevit_estimator import (  # noqa: E402
    DEFAULT_MODEL_PATH,
    MODEL_FILENAME,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MobileViTFatigueEstimator,
    artifact_sha256,
    verify_artifact,
)


def prepare_artifact(target: str | Path) -> Path:
    destination = Path(target).expanduser().resolve()
    if destination.is_file():
        verify_artifact(destination)
        return destination

    from huggingface_hub import hf_hub_download

    cached_path = Path(
        hf_hub_download(
            repo_id=MODEL_REPOSITORY,
            filename=MODEL_FILENAME,
            revision=MODEL_REVISION,
        )
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            with cached_path.open("rb") as source:
                shutil.copyfileobj(source, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        verify_artifact(temporary_path)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    verify_artifact(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="initialize the CUDA estimator and run a black dummy crop",
    )
    args = parser.parse_args()

    artifact = prepare_artifact(args.target)
    print(f"model_path={artifact}")
    print(f"size={artifact.stat().st_size}")
    print(f"sha256={artifact_sha256(artifact)}")
    if args.check:
        estimator = MobileViTFatigueEstimator(artifact)
        probability = estimator.predict(np.zeros((224, 224, 3), dtype=np.uint8))
        print(f"device={estimator.device}")
        print(f"p_drowsy={probability:.8f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
