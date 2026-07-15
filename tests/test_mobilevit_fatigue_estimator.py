import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from modules.fatigue.mobilevit_estimator import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    MODEL_ARCHITECTURE,
    MobileViTFatigueEstimator,
    verify_artifact,
)


class FakeModel:
    def __init__(self, logits=(2.0, 1.0)):
        self.logits = logits
        self.loaded_state = None
        self.strict = None
        self.input_tensor = None
        self.device = None
        self.eval_called = False

    def load_state_dict(self, state, strict):
        self.loaded_state = state
        self.strict = strict

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        self.eval_called = True
        return self

    def __call__(self, tensor):
        self.input_tensor = tensor.detach().cpu()
        return torch.tensor([self.logits], dtype=torch.float32, device=tensor.device)


class FakeTimm(types.ModuleType):
    def __init__(self, model):
        super().__init__("timm")
        self.model = model
        self.calls = []

    def create_model(self, architecture, *, pretrained, num_classes):
        self.calls.append((architecture, pretrained, num_classes))
        return self.model


class MobileViTFatigueEstimatorTest(unittest.TestCase):
    def build_estimator(self, checkpoint=None, logits=(2.0, 1.0)):
        model = FakeModel(logits=logits)
        timm = FakeTimm(model)
        checkpoint = checkpoint or {"state_dict": {"module.head.weight": object()}}
        with (
            patch.dict(sys.modules, {"timm": timm}),
            patch(
                "modules.fatigue.mobilevit_estimator.verify_artifact"
            ) as verify,
            patch(
                "modules.fatigue.mobilevit_estimator.torch.load",
                return_value=checkpoint,
            ) as torch_load,
        ):
            estimator = MobileViTFatigueEstimator("unused.pt", device="cpu")
        return estimator, model, timm, verify, torch_load

    def test_constructs_expected_architecture_and_loads_strictly(self):
        estimator, model, timm, verify, torch_load = self.build_estimator()

        self.assertEqual(timm.calls, [(MODEL_ARCHITECTURE, False, 2)])
        verify.assert_called_once_with(Path("unused.pt"))
        torch_load.assert_called_once_with(
            Path("unused.pt"), map_location="cpu", weights_only=True
        )
        self.assertEqual(set(model.loaded_state), {"head.weight"})
        self.assertTrue(model.strict)
        self.assertTrue(model.eval_called)
        self.assertFalse(estimator.use_fp16)

    def test_normalizes_only_known_leading_prefixes(self):
        _, model, _, _, _ = self.build_estimator(
            {"model_state_dict": {"model.module.layer.weight": object()}}
        )

        self.assertEqual(set(model.loaded_state), {"layer.weight"})

    def test_preprocesses_bgr_as_rgb_imagenet_tensor(self):
        estimator, model, _, _, _ = self.build_estimator()
        crop = np.empty((224, 224, 3), dtype=np.uint8)
        crop[:] = (0, 128, 255)

        estimator.predict(crop)

        self.assertEqual(tuple(model.input_tensor.shape), (1, 3, 224, 224))
        self.assertEqual(model.input_tensor.dtype, torch.float32)
        expected_rgb = np.asarray((255, 128, 0), dtype=np.float32) / 255.0
        expected = (expected_rgb - IMAGENET_MEAN) / IMAGENET_STD
        np.testing.assert_allclose(
            model.input_tensor[0, :, 0, 0].numpy(), expected, rtol=1e-6
        )

    def test_returns_class_zero_softmax_probability(self):
        estimator, _, _, _, _ = self.build_estimator(logits=(2.0, 1.0))

        probability = estimator.predict(
            np.zeros((224, 224, 3), dtype=np.uint8)
        )

        self.assertAlmostEqual(probability, 0.7310586, places=6)

    def test_runtime_loader_never_calls_huggingface_download(self):
        fake_hub = types.ModuleType("huggingface_hub")
        fake_hub.hf_hub_download = unittest.mock.Mock()
        with patch.dict(sys.modules, {"huggingface_hub": fake_hub}):
            self.build_estimator()

        fake_hub.hf_hub_download.assert_not_called()

    def test_missing_or_corrupt_artifact_is_rejected_before_model_creation(self):
        model = FakeModel()
        timm = FakeTimm(model)
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.pt"
            with patch.dict(sys.modules, {"timm": timm}):
                with self.assertRaises(FileNotFoundError):
                    MobileViTFatigueEstimator(missing, device="cpu")
            corrupt = Path(directory) / "corrupt.pt"
            corrupt.write_bytes(b"not the pinned artifact")
            with self.assertRaises(ValueError):
                verify_artifact(corrupt)

        self.assertEqual(timm.calls, [])

    def test_rejects_invalid_face_crop_shape_and_dtype(self):
        estimator, _, _, _, _ = self.build_estimator()

        with self.assertRaises(ValueError):
            estimator.predict(np.zeros((223, 224, 3), dtype=np.uint8))
        with self.assertRaises(ValueError):
            estimator.predict(np.zeros((224, 224, 3), dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
