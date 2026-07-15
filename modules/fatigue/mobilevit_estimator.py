"""Strict local MobileViT-v2 fatigue estimator and artifact validation."""

from __future__ import annotations

import hashlib
import importlib
import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch


MODEL_REPOSITORY = "mosesb/drowsiness-detection-mobileViT-v2"
MODEL_REVISION = "1aa87742178ae3a57b259d797b318bec696b02e1"
MODEL_FILENAME = "best_model.pt"
MODEL_SIZE_BYTES = 69_935_051
MODEL_SHA256 = "fcbe35c8e0c8149bed84189ab3cf0a06429107a968667a9f681ff113bed35867"
MODEL_ARCHITECTURE = "mobilevitv2_200"
DEFAULT_MODEL_PATH = Path(
    "/home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2/best_model.pt"
)
DROWSY_LABEL_INDEX = 0
NON_DROWSY_LABEL_INDEX = 1
IMAGENET_MEAN = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
IMAGENET_STD = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)


def artifact_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(path: str | Path) -> None:
    artifact = Path(path)
    if not artifact.is_file():
        raise FileNotFoundError(f"fatigue model artifact not found: {artifact}")
    actual_size = artifact.stat().st_size
    if actual_size != MODEL_SIZE_BYTES:
        raise ValueError(
            f"fatigue model size mismatch: expected {MODEL_SIZE_BYTES}, got {actual_size}"
        )
    actual_sha = artifact_sha256(artifact)
    if actual_sha != MODEL_SHA256:
        raise ValueError(
            f"fatigue model checksum mismatch: expected {MODEL_SHA256}, got {actual_sha}"
        )


def _unwrap_state_dict(checkpoint: Any) -> Mapping[str, Any]:
    if not isinstance(checkpoint, Mapping):
        raise ValueError("fatigue checkpoint must contain a state dict")
    for wrapper in ("state_dict", "model_state_dict", "model"):
        if wrapper in checkpoint:
            checkpoint = checkpoint[wrapper]
            break
    if not isinstance(checkpoint, Mapping) or not all(
        isinstance(key, str) for key in checkpoint
    ):
        raise ValueError("fatigue checkpoint state dict is invalid")
    return checkpoint


def _normalize_state_dict(checkpoint: Any) -> dict[str, Any]:
    state_dict = _unwrap_state_dict(checkpoint)
    normalized: dict[str, Any] = {}
    for key, value in state_dict.items():
        normalized_key = key
        while normalized_key.startswith(("module.", "model.")):
            if normalized_key.startswith("module."):
                normalized_key = normalized_key[len("module.") :]
            elif normalized_key.startswith("model."):
                normalized_key = normalized_key[len("model.") :]
        if not normalized_key or normalized_key in normalized:
            raise ValueError("fatigue checkpoint contains duplicate or empty keys")
        normalized[normalized_key] = value
    return normalized


class MobileViTFatigueEstimator:
    """Run the pinned binary classifier without any runtime network access."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        *,
        device: str | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        verify_artifact(self.model_path)

        requested_device = device or os.environ.get(
            "ATTENTIVE_FATIGUE_DEVICE", "cuda"
        )
        self.device = torch.device(requested_device)
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the configured fatigue estimator")

        timm = importlib.import_module("timm")
        model = timm.create_model(
            MODEL_ARCHITECTURE,
            pretrained=False,
            num_classes=2,
        )
        checkpoint = torch.load(
            self.model_path,
            map_location="cpu",
            weights_only=True,
        )
        model.load_state_dict(_normalize_state_dict(checkpoint), strict=True)
        self.model = model.to(self.device)
        self.model.eval()
        self.use_fp16 = self.device.type == "cuda"

    def predict(self, face_bgr: np.ndarray) -> float:
        if (
            not isinstance(face_bgr, np.ndarray)
            or face_bgr.dtype != np.uint8
            or face_bgr.shape != (224, 224, 3)
        ):
            raise ValueError("fatigue face crop must be uint8 BGR with shape (224, 224, 3)")

        rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_AREA)
        normalized = resized.astype(np.float32) / 255.0
        normalized = (normalized - IMAGENET_MEAN) / IMAGENET_STD
        tensor = torch.from_numpy(
            np.ascontiguousarray(np.transpose(normalized, (2, 0, 1)))
        ).unsqueeze(0)
        tensor = tensor.to(self.device)

        with torch.inference_mode():
            with torch.autocast(
                device_type="cuda",
                dtype=torch.float16,
                enabled=self.use_fp16,
            ):
                logits = self.model(tensor)
            if not isinstance(logits, torch.Tensor) or logits.shape != (1, 2):
                raise ValueError("fatigue model must return logits shaped (1, 2)")
            probability = float(
                torch.softmax(logits.float(), dim=1)[0, DROWSY_LABEL_INDEX].item()
            )
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("fatigue model returned a non-finite probability")
        return probability
