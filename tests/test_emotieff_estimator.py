import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import h5py
import numpy as np
import torch

from modules.learner_state.emotieff_estimator import (
    EMOTION_LABELS,
    EmotiEffEstimator,
    EngagementAttentionHead,
)
from scripts.prepare_emotieff_learner_state import (
    EXPECTED_STATE_SHAPES,
    H5_TENSORS,
    _numpy_engagement,
    convert_engagement_tensors,
    read_engagement_tensors,
    restore_timm_pickle_compatibility,
    verify_file,
)


class TinyEmotionModel(torch.nn.Module):
    def forward(self, inputs):
        means = inputs.mean(dim=(2, 3))
        padding = torch.zeros(
            (inputs.shape[0], 1277), dtype=inputs.dtype, device=inputs.device
        )
        features = torch.cat((means, padding), dim=1)
        logits = features[:, :8]
        return logits, features


def save_tiny_emotion_model(path: Path) -> None:
    model = TinyEmotionModel().eval()
    example = torch.zeros((1, 3, 224, 224), dtype=torch.float32)
    torch.jit.save(torch.jit.trace(model, example), str(path))


def source_tensors(seed: int = 7) -> dict[str, np.ndarray]:
    generator = np.random.default_rng(seed)
    return {
        "attention.weight": generator.normal(size=(2560, 1)).astype(np.float32) * 0.01,
        "attention.bias": generator.normal(size=(1,)).astype(np.float32) * 0.01,
        "hidden.weight": generator.normal(size=(2560, 512)).astype(np.float32) * 0.01,
        "hidden.bias": generator.normal(size=(512,)).astype(np.float32) * 0.01,
        "output.weight": generator.normal(size=(512, 2)).astype(np.float32) * 0.01,
        "output.bias": generator.normal(size=(2,)).astype(np.float32) * 0.01,
    }


def write_h5(path: Path, tensors: dict[str, np.ndarray]) -> None:
    with h5py.File(path, "w") as handle:
        prefix = handle.create_group("model_weights")
        for state_name, official_name in H5_TENSORS.items():
            parts = official_name.split("/")
            group = prefix
            for part in parts[:-1]:
                group = group.require_group(part)
            group.create_dataset(parts[-1], data=tensors[state_name])


class CapturingHead(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.combined = None

    def forward(self, combined):
        self.combined = combined.detach().cpu().numpy()
        return torch.tensor([[1.0, 2.0]], device=combined.device)


class DepthwiseSeparableConv(torch.nn.Module):
    pass


class InvertedResidual(torch.nn.Module):
    pass


class EmotiEffEstimatorTest(unittest.TestCase):
    def test_restores_only_missing_optional_timm_pickle_fields(self):
        source = torch.nn.Sequential(DepthwiseSeparableConv(), InvertedResidual())
        source[1].conv_s2d = "preserved"
        source[1].bn_s2d = "preserved"
        source[1].aa = "preserved"

        restored = restore_timm_pickle_compatibility(source)

        self.assertEqual(restored, 3)
        self.assertIsNone(source[0].conv_s2d)
        self.assertIsNone(source[0].bn_s2d)
        self.assertIsInstance(source[0].aa, torch.nn.Identity)
        self.assertEqual(source[1].conv_s2d, "preserved")
        self.assertEqual(source[1].bn_s2d, "preserved")
        self.assertEqual(source[1].aa, "preserved")

    def test_source_artifact_size_and_sha_are_both_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.bin"
            artifact.write_bytes(b"verified bytes")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual(
                verify_file(
                    artifact,
                    expected_bytes=len(b"verified bytes"),
                    expected_sha256=digest,
                    label="test",
                ),
                artifact,
            )
            with self.assertRaisesRegex(ValueError, "size mismatch"):
                verify_file(
                    artifact,
                    expected_bytes=1,
                    expected_sha256=digest,
                    label="test",
                )
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                verify_file(
                    artifact,
                    expected_bytes=len(b"verified bytes"),
                    expected_sha256="0" * 64,
                    label="test",
                )

    def test_reads_exact_official_h5_names_and_transposes_kernels(self):
        tensors = source_tensors()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "engagement.h5"
            write_h5(path, tensors)
            read = read_engagement_tensors(path)
            state = convert_engagement_tensors(read)

        self.assertEqual(set(read), set(H5_TENSORS))
        for key, shape in EXPECTED_STATE_SHAPES.items():
            self.assertEqual(tuple(state[key].shape), shape)
            expected = tensors[key].T if tensors[key].ndim == 2 else tensors[key]
            np.testing.assert_array_equal(state[key].numpy(), expected)

    def test_engagement_population_std_precedes_features(self):
        estimator = EmotiEffEstimator("unused.ts", "unused.pt", device="cpu")
        head = CapturingHead()
        estimator._engagement_head = head
        features = np.arange(128 * 1280, dtype=np.float32).reshape(128, 1280)

        probabilities = estimator.infer_engagement(features)

        expected_std = np.std(features, axis=0, ddof=0)
        expected_std_rows = np.repeat(expected_std[None, :], 128, axis=0)
        np.testing.assert_allclose(head.combined[0, :, :1280], expected_std_rows)
        np.testing.assert_array_equal(head.combined[0, :, 1280:], features)
        self.assertAlmostEqual(sum(probabilities), 1.0, places=6)

    def test_converted_head_matches_numpy_reference(self):
        tensors = source_tensors(seed=19)
        state = convert_engagement_tensors(tensors)
        head = EngagementAttentionHead().eval()
        head.load_state_dict(state, strict=True)
        generator = np.random.default_rng(23)
        features = generator.normal(size=(128, 1280)).astype(np.float32)
        std = np.std(features, axis=0, ddof=0)
        combined = np.concatenate((np.repeat(std[None, :], 128, axis=0), features), axis=1)

        with torch.inference_mode():
            actual = torch.softmax(
                head(torch.from_numpy(combined).unsqueeze(0)), dim=1
            )[0].numpy()
        expected = _numpy_engagement(features, tensors)

        self.assertEqual(tuple(combined[None, ...].shape), (1, 128, 2560))
        self.assertEqual(tuple(actual.shape), (2,))
        np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-6)
        self.assertAlmostEqual(float(actual.sum()), 1.0, places=6)

    def test_engagement_rejects_wrong_shape_or_nonfinite_features(self):
        estimator = EmotiEffEstimator("unused.ts", "unused.pt", device="cpu")
        with self.assertRaisesRegex(ValueError, "\(128, 1280\)"):
            estimator.infer_engagement(np.zeros((127, 1280), dtype=np.float32))
        invalid = np.zeros((128, 1280), dtype=np.float32)
        invalid[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            estimator.infer_engagement(invalid)

    def test_preprocesses_bgr_to_resized_rgb_imagenet_tensor(self):
        crop = np.empty((16, 12, 3), dtype=np.uint8)
        crop[:] = (0, 128, 255)

        tensor = EmotiEffEstimator._preprocess(crop)

        self.assertEqual(tuple(tensor.shape), (1, 3, 224, 224))
        expected_rgb = np.asarray((255, 128, 0), dtype=np.float32) / 255.0
        mean = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
        std = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)
        np.testing.assert_allclose(
            tensor[0, :, 0, 0].numpy(), (expected_rgb - mean) / std, rtol=1e-6
        )

    def test_infer_frame_returns_eight_probabilities_and_copied_feature(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "emotion.ts"
            save_tiny_emotion_model(model_path)
            estimator = EmotiEffEstimator(model_path, "missing.pt", device="cpu")
            output = estimator.infer_frame(
                np.zeros((224, 224, 3), dtype=np.uint8)
            )

        self.assertEqual(len(output.emotion_probabilities), len(EMOTION_LABELS))
        self.assertAlmostEqual(sum(output.emotion_probabilities), 1.0, places=6)
        self.assertEqual(output.feature.shape, (1280,))
        self.assertEqual(output.feature.dtype, np.float32)
        self.assertTrue(output.feature.flags.owndata)

    def test_missing_engagement_state_does_not_hide_emotion(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "emotion.ts"
            save_tiny_emotion_model(model_path)
            estimator = EmotiEffEstimator(
                model_path, Path(directory) / "missing.pt", device="cpu"
            )

            output = estimator.infer_frame(np.zeros((224, 224, 3), dtype=np.uint8))
            with self.assertRaises(FileNotFoundError):
                estimator.infer_engagement(
                    np.zeros((128, 1280), dtype=np.float32)
                )

        self.assertEqual(len(output.emotion_probabilities), 8)

    def test_runtime_missing_or_corrupt_model_is_concise_and_has_no_network_path(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.ts"
            estimator = EmotiEffEstimator(missing, "unused.pt", device="cpu")
            with self.assertRaisesRegex(FileNotFoundError, "TorchScript not found"):
                estimator.infer_frame(np.zeros((224, 224, 3), dtype=np.uint8))
            corrupt = Path(directory) / "corrupt.ts"
            corrupt.write_bytes(b"not torchscript")
            estimator = EmotiEffEstimator(corrupt, "unused.pt", device="cpu")
            with patch("urllib.request.urlopen") as network:
                with self.assertRaisesRegex(RuntimeError, "cannot load"):
                    estimator.infer_frame(np.zeros((224, 224, 3), dtype=np.uint8))
                network.assert_not_called()

    def test_emotion_and_engagement_are_loaded_separately_and_lazily(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "emotion.ts"
            state_path = Path(directory) / "engagement.pt"
            save_tiny_emotion_model(model_path)
            torch.save(EngagementAttentionHead().state_dict(), state_path)
            estimator = EmotiEffEstimator(model_path, state_path, device="cpu")

            self.assertIsNone(estimator._emotion_model)
            self.assertIsNone(estimator._engagement_head)
            estimator.infer_frame(np.zeros((224, 224, 3), dtype=np.uint8))
            self.assertIsNotNone(estimator._emotion_model)
            self.assertIsNone(estimator._engagement_head)
            estimator.infer_engagement(np.zeros((128, 1280), dtype=np.float32))
            self.assertIsNotNone(estimator._engagement_head)


if __name__ == "__main__":
    unittest.main()
