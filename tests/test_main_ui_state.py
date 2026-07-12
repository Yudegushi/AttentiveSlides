"""Tests for Main UI deck browsing and view state."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modules.system.main_ui_state import (
    ManifestDeckBrowser,
    build_main_turn_defaults,
    build_main_ui_view_model,
    reset_main_turn_state,
)


REPOSITORY_ROOT = Path(
    __file__
).resolve().parents[1]

REPOSITORY_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "mock_deck"
    / "mock_aoi_manifest.json"
)


def write_manifest(
    directory: str,
    payload: dict,
) -> Path:
    """Write a temporary manifest and return its path."""
    manifest_path = (
        Path(directory)
        / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    return manifest_path


def make_slide_payload(
    slide_id: int,
    text: str,
) -> dict:
    """Create one deterministic slide payload."""
    return {
        "slide_id": slide_id,
        "ocr_text": text,
        "neighbor_slide_text": "",
        "aois": [
            {
                "aoi_id": f"slide_{slide_id}_text",
                "bbox": [
                    0.1,
                    0.1,
                    0.9,
                    0.8,
                ],
                "type": "text",
                "text": text,
                "name": f"Slide {slide_id} text",
            }
        ],
    }


class TestMainUIState(unittest.TestCase):
    def test_repository_manifest_loads(
        self,
    ) -> None:
        browser = ManifestDeckBrowser(
            REPOSITORY_MANIFEST_PATH,
            asset_root=REPOSITORY_ROOT,
        )

        self.assertTrue(
            browser.deck_id.strip()
        )

        self.assertGreaterEqual(
            len(browser.slide_ids),
            1,
        )

        first_slide = browser.get_slide(
            browser.slide_ids[0]
        )

        self.assertEqual(
            first_slide.slide_id,
            browser.slide_ids[0],
        )

        self.assertIsInstance(
            first_slide.slide_text,
            str,
        )

        self.assertIsInstance(
            first_slide.aois,
            tuple,
        )

    def test_view_model_uses_manual_privacy_mode(
        self,
    ) -> None:
        payload = {
            "deck_id": "privacy_test",
            "title": "Privacy test",
            "slides": [
                make_slide_payload(
                    1,
                    "Privacy-preserving slide.",
                )
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            manifest_path = write_manifest(
                directory,
                payload,
            )

            browser = ManifestDeckBrowser(
                manifest_path,
                asset_root=directory,
            )

            view = build_main_ui_view_model(
                browser,
                active_slide_id=1,
                cloud_text_allowed=True,
            )

        self.assertEqual(
            view.privacy.interaction_mode,
            "manual",
        )
        self.assertFalse(
            view.privacy.camera_enabled
        )
        self.assertFalse(
            view.privacy.microphone_enabled
        )
        self.assertFalse(
            view.privacy.raw_biometrics_collected
        )
        self.assertFalse(
            view.privacy.cloud_llm_called
        )
        self.assertTrue(
            view.privacy
            .selected_slide_text_cloud_allowed
        )

    def test_navigation_preserves_manifest_order(
        self,
    ) -> None:
        payload = {
            "deck_id": "navigation_test",
            "title": "Navigation test",
            "slides": [
                make_slide_payload(
                    1,
                    "Slide one",
                ),
                make_slide_payload(
                    3,
                    "Slide three",
                ),
                make_slide_payload(
                    8,
                    "Slide eight",
                ),
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            manifest_path = write_manifest(
                directory,
                payload,
            )

            browser = ManifestDeckBrowser(
                manifest_path,
                asset_root=directory,
            )

            self.assertEqual(
                browser.slide_ids,
                (1, 3, 8),
            )
            self.assertIsNone(
                browser.previous_slide_id(1)
            )
            self.assertEqual(
                browser.next_slide_id(1),
                3,
            )
            self.assertEqual(
                browser.previous_slide_id(3),
                1,
            )
            self.assertEqual(
                browser.next_slide_id(3),
                8,
            )
            self.assertIsNone(
                browser.next_slide_id(8)
            )

    def test_view_model_navigation_flags(
        self,
    ) -> None:
        payload = {
            "deck_id": "flag_test",
            "slides": [
                make_slide_payload(
                    2,
                    "First",
                ),
                make_slide_payload(
                    5,
                    "Second",
                ),
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            manifest_path = write_manifest(
                directory,
                payload,
            )

            browser = ManifestDeckBrowser(
                manifest_path,
                asset_root=directory,
            )

            first_view = build_main_ui_view_model(
                browser,
                active_slide_id=2,
                cloud_text_allowed=False,
            )

            second_view = build_main_ui_view_model(
                browser,
                active_slide_id=5,
                cloud_text_allowed=False,
            )

        self.assertFalse(
            first_view.can_go_previous
        )
        self.assertTrue(
            first_view.can_go_next
        )
        self.assertTrue(
            second_view.can_go_previous
        )
        self.assertFalse(
            second_view.can_go_next
        )

    def test_unknown_slide_is_rejected(
        self,
    ) -> None:
        payload = {
            "deck_id": "unknown_slide_test",
            "slides": [
                make_slide_payload(
                    1,
                    "Only slide",
                )
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            manifest_path = write_manifest(
                directory,
                payload,
            )

            browser = ManifestDeckBrowser(
                manifest_path,
                asset_root=directory,
            )

            with self.assertRaises(KeyError):
                browser.get_slide(999)

            with self.assertRaises(KeyError):
                browser.slide_index(999)

    def test_duplicate_slide_ids_are_rejected(
        self,
    ) -> None:
        payload = {
            "deck_id": "duplicate_test",
            "slides": [
                make_slide_payload(
                    1,
                    "First copy",
                ),
                make_slide_payload(
                    1,
                    "Second copy",
                ),
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            manifest_path = write_manifest(
                directory,
                payload,
            )

            with self.assertRaises(ValueError):
                ManifestDeckBrowser(
                    manifest_path,
                    asset_root=directory,
                )

    def test_relative_image_path_is_resolved(
        self,
    ) -> None:
        payload = {
            "deck_id": "image_path_test",
            "slides": [
                {
                    **make_slide_payload(
                        1,
                        "Image test",
                    ),
                    "slide_image_path": (
                        "assets/slide_1.png"
                    ),
                }
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            image_directory = (
                root
                / "assets"
            )
            image_directory.mkdir()

            image_path = (
                image_directory
                / "slide_1.png"
            )
            image_path.write_bytes(b"test-image")

            manifest_path = write_manifest(
                directory,
                payload,
            )

            browser = ManifestDeckBrowser(
                manifest_path,
                asset_root=root,
            )

            slide = browser.get_slide(1)

            self.assertEqual(
                slide.image_path,
                str(image_path.resolve()),
            )
            self.assertTrue(
                slide.image_available
            )


    def test_reset_main_turn_state(
        self,
    ) -> None:
        state = {
            "main_target_scope": "Manual region",
            "main_typed_command": "explain this",
            "main_manual_bbox": [
                0.1,
                0.2,
                0.6,
                0.7,
            ],
            "main_selected_aoi_ids": [
                "aoi_test"
            ],
            "main_confirmed": True,
            "main_tutor_result": {
                "answer": "temporary"
            },
            "main_xai_result": {
                "validation": True
            },
            "main_active_slide_id": 5,
            "main_cloud_text_allowed": False,
        }

        reset_main_turn_state(state)

        defaults = build_main_turn_defaults()

        for key, expected_value in defaults.items():
            self.assertEqual(
                state[key],
                expected_value,
            )

        self.assertEqual(
            state["main_active_slide_id"],
            5,
        )

        self.assertFalse(
            state["main_cloud_text_allowed"]
        )


if __name__ == "__main__":
    unittest.main()
