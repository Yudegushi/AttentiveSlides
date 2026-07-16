#!/usr/bin/env python3
"""Download, verify, and convert the two pinned official EmotiEff artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import torch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from modules.learner_state.emotieff_estimator import (  # noqa: E402
    EMOTION_LABELS,
    ENGAGEMENT_LABELS,
    EngagementAttentionHead,
)


SOURCE_COMMIT = "520a051c64cd191521e5934655314e769a319684"
EMOTION_URL = (
    "https://raw.githubusercontent.com/sb-ai-lab/EmotiEffLib/"
    f"{SOURCE_COMMIT}/models/affectnet_emotions/enet_b0_8_best_vgaf.pt"
)
ENGAGEMENT_URL = (
    "https://raw.githubusercontent.com/sb-ai-lab/EmotiEffLib/"
    f"{SOURCE_COMMIT}/models/engagement_classification/engagement_single_attention.h5"
)
EMOTION_SHA256 = "95aafb39b8bb87964f45e208b9ab31e276e3e5278678db4961d18e6a1b42a141"
EMOTION_BYTES = 16_419_305
ENGAGEMENT_SHA256 = "243b4699eec398a335d32774849f65b2f0e2d63e358df479c5ee95a002cac30d"
ENGAGEMENT_BYTES = 5_282_144
DEFAULT_OUTPUT_DIR = Path(
    "/home/charles/.local/share/attentiveslides/models/learner_state/emotieff"
)
H5_TENSORS = {
    "attention.weight": "e/e/kernel:0",
    "attention.bias": "e/e/bias:0",
    "hidden.weight": "hidden_FC/hidden_FC/kernel:0",
    "hidden.bias": "hidden_FC/hidden_FC/bias:0",
    "output.weight": "dense/dense/kernel:0",
    "output.bias": "dense/dense/bias:0",
}
EXPECTED_STATE_SHAPES = {
    "attention.weight": (1, 2560),
    "attention.bias": (1,),
    "hidden.weight": (512, 2560),
    "hidden.bias": (512,),
    "output.weight": (2, 512),
    "output.bias": (2,),
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(
    path: str | Path, *, expected_bytes: int, expected_sha256: str, label: str
) -> Path:
    artifact = Path(path)
    if not artifact.is_file():
        raise FileNotFoundError(f"{label} artifact not found: {artifact}")
    actual_bytes = artifact.stat().st_size
    if actual_bytes != expected_bytes:
        raise ValueError(
            f"{label} size mismatch: expected {expected_bytes}, got {actual_bytes}"
        )
    actual_sha256 = sha256_file(artifact)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"{label} checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    return artifact


def _download_verified(
    *, url: str, destination: Path, expected_bytes: int, expected_sha256: str, label: str
) -> Path:
    if destination.exists():
        return verify_file(
            destination,
            expected_bytes=expected_bytes,
            expected_sha256=expected_sha256,
            label=label,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f"{destination.name}.part")
    partial.unlink(missing_ok=True)
    try:
        with urllib.request.urlopen(url) as response, partial.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        verify_file(
            partial,
            expected_bytes=expected_bytes,
            expected_sha256=expected_sha256,
            label=label,
        )
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)
    return verify_file(
        destination,
        expected_bytes=expected_bytes,
        expected_sha256=expected_sha256,
        label=label,
    )


def _find_dataset(handle: h5py.File, official_name: str) -> np.ndarray:
    matches: list[str] = []

    def visitor(name: str, value: Any) -> None:
        if isinstance(value, h5py.Dataset) and (
            name == official_name or name.endswith(f"/{official_name}")
        ):
            matches.append(name)

    handle.visititems(visitor)
    if len(matches) != 1:
        raise ValueError(
            f"expected one H5 dataset named {official_name!r}, found {matches}"
        )
    return np.asarray(handle[matches[0]][()], dtype=np.float32)


def read_engagement_tensors(path: str | Path) -> dict[str, np.ndarray]:
    with h5py.File(path, "r") as handle:
        return {key: _find_dataset(handle, name) for key, name in H5_TENSORS.items()}


def convert_engagement_tensors(
    source_tensors: dict[str, np.ndarray],
) -> dict[str, torch.Tensor]:
    if set(source_tensors) != set(H5_TENSORS):
        raise ValueError("engagement H5 tensor set is incomplete")
    state: dict[str, torch.Tensor] = {}
    for key, value in source_tensors.items():
        converted = value.T if value.ndim == 2 else value
        tensor = torch.from_numpy(np.ascontiguousarray(converted, dtype=np.float32))
        if tuple(tensor.shape) != EXPECTED_STATE_SHAPES[key]:
            raise ValueError(
                f"engagement tensor {key} has shape {tuple(tensor.shape)}, "
                f"expected {EXPECTED_STATE_SHAPES[key]}"
            )
        state[key] = tensor
    return state


def _numpy_engagement(
    features: np.ndarray, source_tensors: dict[str, np.ndarray]
) -> np.ndarray:
    standard_deviation = np.std(features, axis=0, ddof=0)
    repeated_std = np.repeat(standard_deviation[None, :], 128, axis=0)
    combined = np.concatenate((repeated_std, features), axis=1)
    scores = combined @ source_tensors["attention.weight"] + source_tensors[
        "attention.bias"
    ]
    scores = scores - np.max(scores, axis=0, keepdims=True)
    attention = np.exp(scores) / np.sum(np.exp(scores), axis=0, keepdims=True)
    context = np.sum(attention * combined, axis=0)
    hidden = np.maximum(
        context @ source_tensors["hidden.weight"] + source_tensors["hidden.bias"],
        0.0,
    )
    logits = hidden @ source_tensors["output.weight"] + source_tensors["output.bias"]
    logits = logits - np.max(logits)
    return np.exp(logits) / np.sum(np.exp(logits))


def restore_timm_pickle_compatibility(source: torch.nn.Module) -> int:
    """Restore optional fields added after the pinned model was pickled.

    The official artifact predates timm's optional space-to-depth convolution.
    Current timm forwards read ``conv_s2d`` unconditionally, while a freshly
    constructed equivalent block sets it to ``None`` when the feature is off.
    """

    restored = 0
    compatible_types = {"DepthwiseSeparableConv", "InvertedResidual"}
    optional_defaults = {
        "conv_s2d": None,
        "bn_s2d": None,
        "aa": torch.nn.Identity,
    }
    for module in source.modules():
        if type(module).__name__ not in compatible_types:
            continue
        for name, default in optional_defaults.items():
            if not hasattr(module, name):
                setattr(module, name, default() if callable(default) else default)
                restored += 1
    return restored


class _EmotionFeatureWrapper(torch.nn.Module):
    def __init__(self, backbone: torch.nn.Module, classifier: torch.nn.Module) -> None:
        super().__init__()
        self.backbone = backbone
        self.classifier = classifier

    def forward(self, inputs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        features = self.backbone(inputs)
        return self.classifier(features), features


def _atomic_torch_save(value: Any, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    torch.save(value, temporary)
    os.replace(temporary, destination)


def _atomic_json_write(payload: dict[str, Any], destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def prepare(output_dir: str | Path, *, force: bool = False) -> dict[str, Any]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    emotion_source = output / "enet_b0_8_best_vgaf.pt"
    engagement_source = output / "engagement_single_attention.h5"
    emotion_prepared = output / "enet_b0_8_best_vgaf_features.ts"
    engagement_prepared = output / "engagement_single_attention.pt"
    manifest_path = output / "manifest.json"
    prepared_outputs = (emotion_prepared, engagement_prepared, manifest_path)
    if not force and any(path.exists() for path in prepared_outputs):
        if not all(path.is_file() for path in prepared_outputs):
            raise FileExistsError("prepared EmotiEff output set is incomplete; use --force")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    emotion_source = _download_verified(
        url=EMOTION_URL,
        destination=emotion_source,
        expected_bytes=EMOTION_BYTES,
        expected_sha256=EMOTION_SHA256,
        label="EmotiEff emotion source",
    )
    engagement_source = _download_verified(
        url=ENGAGEMENT_URL,
        destination=engagement_source,
        expected_bytes=ENGAGEMENT_BYTES,
        expected_sha256=ENGAGEMENT_SHA256,
        label="EmotiEff engagement source",
    )

    source = torch.load(emotion_source, map_location="cpu", weights_only=False)
    compatibility_fields_restored = restore_timm_pickle_compatibility(source)
    source.eval()
    if source.__class__.__name__ != "EfficientNet":
        raise ValueError("official EmotiEff source must be a timm EfficientNet")
    classifier = getattr(source, "classifier", None)
    if (
        not isinstance(classifier, torch.nn.Sequential)
        or len(classifier) != 1
        or not isinstance(classifier[0], torch.nn.Linear)
        or classifier[0].in_features != 1280
        or classifier[0].out_features != 8
    ):
        raise ValueError("official EmotiEff classifier must be Sequential(Linear(1280, 8))")
    dummy = torch.zeros((1, 3, 224, 224), dtype=torch.float32)
    with torch.inference_mode():
        original_logits = source(dummy).detach().clone()
    preserved_classifier = classifier[0]
    source.classifier = torch.nn.Identity()
    wrapper = _EmotionFeatureWrapper(source, preserved_classifier).eval()
    with torch.inference_mode():
        wrapper_logits, wrapper_features = wrapper(dummy)
    torch.testing.assert_close(wrapper_logits, original_logits)
    if wrapper_logits.shape != (1, 8) or wrapper_features.shape != (1, 1280):
        raise ValueError("prepared EmotiEff wrapper returned unexpected shapes")
    traced = torch.jit.freeze(torch.jit.trace(wrapper, dummy))
    with torch.inference_mode():
        traced_logits, traced_features = traced(dummy)
    torch.testing.assert_close(traced_logits, wrapper_logits)
    torch.testing.assert_close(traced_features, wrapper_features)
    temporary_script = emotion_prepared.with_name(f".{emotion_prepared.name}.tmp")
    torch.jit.save(traced, str(temporary_script))
    os.replace(temporary_script, emotion_prepared)

    source_tensors = read_engagement_tensors(engagement_source)
    state = convert_engagement_tensors(source_tensors)
    _atomic_torch_save(state, engagement_prepared)
    reloaded = torch.load(engagement_prepared, map_location="cpu", weights_only=True)
    head = EngagementAttentionHead().eval()
    head.load_state_dict(reloaded, strict=True)
    generator = np.random.default_rng(20260716)
    features = generator.normal(size=(128, 1280)).astype(np.float32)
    population_std = np.std(features, axis=0, ddof=0)
    combined = np.concatenate(
        (np.repeat(population_std[None, :], 128, axis=0), features), axis=1
    )
    with torch.inference_mode():
        actual = torch.softmax(
            head(torch.from_numpy(combined).unsqueeze(0)), dim=1
        )[0].numpy()
    expected = _numpy_engagement(features, source_tensors)
    np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-6)

    manifest = {
        "source_commit": SOURCE_COMMIT,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "emotion_labels": list(EMOTION_LABELS),
        "engagement_labels": list(ENGAGEMENT_LABELS),
        "sources": {
            "emotion": {
                "url": EMOTION_URL,
                "filename": emotion_source.name,
                "bytes": EMOTION_BYTES,
                "sha256": EMOTION_SHA256,
            },
            "engagement": {
                "url": ENGAGEMENT_URL,
                "filename": engagement_source.name,
                "bytes": ENGAGEMENT_BYTES,
                "sha256": ENGAGEMENT_SHA256,
            },
        },
        "prepared": {
            "emotion_torchscript": {
                "filename": emotion_prepared.name,
                "sha256": sha256_file(emotion_prepared),
                "logits_shape": [1, 8],
                "feature_shape": [1, 1280],
            },
            "engagement_state": {
                "filename": engagement_prepared.name,
                "sha256": sha256_file(engagement_prepared),
                "tensor_shapes": {
                    key: list(shape) for key, shape in EXPECTED_STATE_SHAPES.items()
                },
            },
        },
        "preparation_compatibility": {
            "restored_optional_block_fields": compatibility_fields_restored,
        },
    }
    _atomic_json_write(manifest, manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = prepare(args.output_dir, force=args.force)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
