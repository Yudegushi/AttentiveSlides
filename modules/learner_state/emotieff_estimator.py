"""Runtime-only EmotiEff emotion/features and engagement inference."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch


EMOTION_LABELS = (
    "Anger",
    "Contempt",
    "Disgust",
    "Fear",
    "Happiness",
    "Neutral",
    "Sadness",
    "Surprise",
)
ENGAGEMENT_LABELS = ("Distracted", "Engaged")
IMAGENET_MEAN = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
IMAGENET_STD = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)
ENGAGEMENT_FRAMES = 128
FEATURE_DIMENSIONS = 1280


@dataclass(frozen=True)
class AffectFrameOutput:
    emotion_probabilities: tuple[float, ...]
    feature: np.ndarray

    def __post_init__(self) -> None:
        probabilities = self.emotion_probabilities
        if len(probabilities) != len(EMOTION_LABELS):
            raise ValueError("emotion output must contain eight probabilities")
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities):
            raise ValueError("emotion probabilities must be finite values in [0, 1]")
        if not math.isclose(sum(probabilities), 1.0, abs_tol=1e-4):
            raise ValueError("emotion probabilities must sum to one")
        if not isinstance(self.feature, np.ndarray) or self.feature.shape != (
            FEATURE_DIMENSIONS,
        ):
            raise ValueError("EmotiEff feature must have shape (1280,)")
        if self.feature.dtype != np.float32 or not np.isfinite(self.feature).all():
            raise ValueError("EmotiEff feature must be finite float32")


class EngagementAttentionHead(torch.nn.Module):
    """PyTorch equivalent of the pinned three-layer Keras attention head."""

    def __init__(self) -> None:
        super().__init__()
        self.attention = torch.nn.Linear(FEATURE_DIMENSIONS * 2, 1)
        self.hidden = torch.nn.Linear(FEATURE_DIMENSIONS * 2, 512)
        self.output = torch.nn.Linear(512, len(ENGAGEMENT_LABELS))

    def forward(self, combined_features: torch.Tensor) -> torch.Tensor:
        if combined_features.ndim != 3 or combined_features.shape[1:] != (
            ENGAGEMENT_FRAMES,
            FEATURE_DIMENSIONS * 2,
        ):
            raise ValueError("engagement head input must have shape [batch, 128, 2560]")
        attention = torch.softmax(self.attention(combined_features), dim=1)
        context = torch.sum(attention * combined_features, dim=1)
        hidden = torch.relu(self.hidden(context))
        return self.output(hidden)


class EmotiEffEstimator:
    """Lazily load prepared local artifacts; runtime never downloads or unpickles."""

    def __init__(
        self,
        emotion_model_path: str | Path,
        engagement_state_path: str | Path,
        *,
        device: str = "cuda",
    ) -> None:
        self.emotion_model_path = Path(emotion_model_path)
        self.engagement_state_path = Path(engagement_state_path)
        self.device = torch.device(device)
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the configured EmotiEff estimator")
        self._emotion_model: torch.jit.ScriptModule | None = None
        self._engagement_head: EngagementAttentionHead | None = None

    def _load_emotion_model(self) -> torch.jit.ScriptModule:
        if self._emotion_model is not None:
            return self._emotion_model
        if not self.emotion_model_path.is_file():
            raise FileNotFoundError(
                f"EmotiEff emotion TorchScript not found: {self.emotion_model_path}"
            )
        try:
            model = torch.jit.load(str(self.emotion_model_path), map_location=self.device)
            model.eval()
        except Exception as exc:
            raise RuntimeError(f"cannot load EmotiEff emotion TorchScript: {exc}") from exc
        self._emotion_model = model
        return model

    def _load_engagement_head(self) -> EngagementAttentionHead:
        if self._engagement_head is not None:
            return self._engagement_head
        if not self.engagement_state_path.is_file():
            raise FileNotFoundError(
                f"EmotiEff engagement state not found: {self.engagement_state_path}"
            )
        try:
            state = torch.load(
                self.engagement_state_path,
                map_location="cpu",
                weights_only=True,
            )
            if not isinstance(state, dict):
                raise ValueError("engagement artifact must contain a state dict")
            head = EngagementAttentionHead()
            head.load_state_dict(state, strict=True)
            head.to(self.device).eval()
        except Exception as exc:
            raise RuntimeError(f"cannot load EmotiEff engagement state: {exc}") from exc
        self._engagement_head = head
        return head

    @staticmethod
    def _preprocess(bgr_face: np.ndarray) -> torch.Tensor:
        if (
            not isinstance(bgr_face, np.ndarray)
            or bgr_face.dtype != np.uint8
            or bgr_face.ndim != 3
            or bgr_face.shape[2] != 3
            or bgr_face.shape[0] < 1
            or bgr_face.shape[1] < 1
        ):
            raise ValueError("EmotiEff face crop must be non-empty uint8 BGR")
        rgb = cv2.cvtColor(bgr_face, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_LINEAR)
        normalized = resized.astype(np.float32) / 255.0
        normalized = (normalized - IMAGENET_MEAN) / IMAGENET_STD
        chw = np.ascontiguousarray(np.transpose(normalized, (2, 0, 1)))
        return torch.from_numpy(chw).unsqueeze(0)

    def infer_frame(self, bgr_face: np.ndarray) -> AffectFrameOutput:
        model = self._load_emotion_model()
        tensor = self._preprocess(bgr_face).to(self.device)
        with torch.inference_mode():
            output = model(tensor)
        if not isinstance(output, tuple) or len(output) != 2:
            raise ValueError("EmotiEff TorchScript must return logits and features")
        logits, features = output
        if logits.shape != (1, len(EMOTION_LABELS)) or features.shape != (
            1,
            FEATURE_DIMENSIONS,
        ):
            raise ValueError("EmotiEff TorchScript returned unexpected shapes")
        probabilities_array = torch.softmax(logits.float(), dim=1)[0].cpu().numpy()
        probabilities = tuple(float(value) for value in probabilities_array)
        feature = features.float()[0].detach().cpu().numpy().astype(np.float32, copy=True)
        return AffectFrameOutput(probabilities, feature)

    def infer_engagement(self, features: np.ndarray) -> tuple[float, float]:
        if (
            not isinstance(features, np.ndarray)
            or features.shape != (ENGAGEMENT_FRAMES, FEATURE_DIMENSIONS)
            or not np.issubdtype(features.dtype, np.floating)
            or not np.isfinite(features).all()
        ):
            raise ValueError("engagement features must be finite floats shaped (128, 1280)")
        values = features.astype(np.float32, copy=False)
        population_std = np.std(values, axis=0, ddof=0, dtype=np.float32)
        repeated_std = np.repeat(population_std[None, :], ENGAGEMENT_FRAMES, axis=0)
        combined = np.concatenate((repeated_std, values), axis=1)
        tensor = torch.from_numpy(np.ascontiguousarray(combined)).unsqueeze(0)
        tensor = tensor.to(self.device)
        head = self._load_engagement_head()
        with torch.inference_mode():
            logits = head(tensor)
            probabilities_array = torch.softmax(logits.float(), dim=1)[0].cpu().numpy()
        if probabilities_array.shape != (len(ENGAGEMENT_LABELS),):
            raise ValueError("engagement head must return two probabilities")
        probabilities = tuple(float(value) for value in probabilities_array)
        if any(not math.isfinite(value) for value in probabilities):
            raise ValueError("engagement head returned non-finite probabilities")
        return probabilities  # type: ignore[return-value]
