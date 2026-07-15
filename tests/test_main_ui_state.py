"""Tests for Main UI deck browsing and view state."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.common.schemas import VisualContextItem
from modules.slide.aoi_manager import AUTO_AOI_SCHEMA_VERSION
from modules.system.uploaded_deck_service import UploadedDeckWorkspace

from modules.system.main_ui_state import (
    ManifestDeckBrowser,
    build_main_conversation_defaults,
    build_main_live_defaults,
    build_main_turn_defaults,
    build_main_ui_view_model,
    reset_main_conversation_state,
    reset_main_live_turn_state,
    reset_main_turn_state,
    write_main_interaction_once,
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
    def test_main_ui_slide_serializes_default_and_selected_aoi_profile(self) -> None:
        from modules.system.main_ui_state import MainUISlide

        default = MainUISlide(1, "text", "", ())
        selected = MainUISlide(1, "text", "", (), aoi_profile="profile-a")
        self.assertEqual(default.aoi_profile, "deterministic")
        self.assertEqual(default.to_dict()["aoi_profile"], "deterministic")
        self.assertEqual(selected.to_dict()["aoi_profile"], "profile-a")

    def test_uploaded_slide_exposes_visual_context_only_for_eligible_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            workspace.slide_parser.metadata["deck"] = {
                "deck_id": "deck",
                "original_name": "deck.pdf",
                "pdf_path": str(Path(directory) / "deck.pdf"),
                "page_count": 1,
            }
            visual = VisualContextItem(
                visual_id="visual_1",
                type="formula",
                bbox=[0.2, 0.3, 0.7, 0.45],
                description="A conditional-probability formula.",
                transcription="p(y | x)",
                confidence=0.91,
                linked_aoi_id="llm_aoi_1",
            )
            slide_data = {
                "slide_id": 1,
                "slide_image_path": "",
                "ocr_text": "Slide text",
                "auto_aoi_version": AUTO_AOI_SCHEMA_VERSION,
                "llm_visual_context": [{
                    **visual.to_dict(),
                    "description": 42,
                }, visual.to_dict()],
                "llm_visual_context_status": "used",
            }
            raw_aois = [{
                "aoi_id": "llm_aoi_1",
                "bbox": [0.2, 0.3, 0.7, 0.45],
                "type": "formula",
                "text": "",
            }]

            with patch.object(
                workspace,
                "_get_or_process_slide",
                return_value=slide_data,
            ), patch.object(
                workspace.aoi_manager,
                "get_effective_aois",
                return_value=(raw_aois, "eligible-profile"),
            ):
                enhanced = workspace.get_slide("deck", 1, use_llm_aoi=True)

            with patch.object(
                workspace,
                "_get_or_process_slide",
                return_value=slide_data,
            ), patch.object(
                workspace.aoi_manager,
                "get_effective_aois",
                return_value=(raw_aois, "deterministic"),
            ):
                deterministic = workspace.get_slide("deck", 1, use_llm_aoi=True)

            corrupt_data = dict(
                slide_data,
                llm_visual_context=None,
            )
            with patch.object(
                workspace,
                "_get_or_process_slide",
                return_value=corrupt_data,
            ), patch.object(
                workspace.aoi_manager,
                "get_effective_aois",
                return_value=(raw_aois, "eligible-profile"),
            ):
                corrupt = workspace.get_slide("deck", 1, use_llm_aoi=True)

            self.assertEqual(enhanced.visual_context, (visual,))
            self.assertEqual(deterministic.visual_context, ())
            self.assertEqual(corrupt.visual_context, ())

    def test_slide_width_is_clamped_and_snapped(self) -> None:
        from modules.system.main_ui_state import (
            normalize_main_slide_width_percent,
        )

        self.assertEqual(normalize_main_slide_width_percent(None), 100)
        self.assertEqual(normalize_main_slide_width_percent(49), 50)
        self.assertEqual(normalize_main_slide_width_percent(73), 75)
        self.assertEqual(normalize_main_slide_width_percent(101), 100)

    def test_main_interaction_log_is_exactly_once(self) -> None:
        logged: list[str] = []
        payloads: list[dict] = []

        first = write_main_interaction_once(
            logged,
            interaction_id="turn-1",
            payload={"interaction_id": "turn-1"},
            write=payloads.append,
        )
        second = write_main_interaction_once(
            logged,
            interaction_id="turn-1",
            payload={"interaction_id": "turn-1"},
            write=payloads.append,
        )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(logged, ["turn-1"])
        self.assertEqual(payloads, [{"interaction_id": "turn-1"}])

    def test_failed_log_write_does_not_mark_interaction(self) -> None:
        logged: list[str] = []

        def fail(_payload: dict) -> None:
            raise OSError("disk unavailable")

        with self.assertRaisesRegex(OSError, "disk unavailable"):
            write_main_interaction_once(
                logged,
                interaction_id="turn-2",
                payload={"interaction_id": "turn-2"},
                write=fail,
            )

        self.assertEqual(logged, [])

    def test_main_live_defaults_are_minimal_and_fresh(
        self,
    ) -> None:
        first = build_main_live_defaults()
        second = build_main_live_defaults()

        self.assertEqual(
            first,
            {
                "main_interaction_mode": "Manual",
                "main_live_master_enabled": False,
                "main_confirmation_policy": (
                    "Always confirm"
                ),
                "main_auto_confirm_threshold": 0.80,
                "main_live_proposal": None,
                "main_live_original_transcript": None,
                "main_live_predicted_aoi_id": None,
                "main_live_layout_revision": None,
                "main_logged_interaction_ids": [],
            },
        )
        self.assertIsNot(
            first["main_logged_interaction_ids"],
            second["main_logged_interaction_ids"],
        )

    def test_live_turn_reset_preserves_preferences(
        self,
    ) -> None:
        state = {
            **build_main_live_defaults(),
            **build_main_turn_defaults(),
            "main_interaction_mode": "Live",
            "main_live_master_enabled": True,
            "main_confirmation_policy": (
                "Confidence-based auto"
            ),
            "main_auto_confirm_threshold": 0.91,
            "main_live_proposal": {"interaction_id": "live-1"},
            "main_live_original_transcript": "original",
            "main_live_predicted_aoi_id": "aoi-1",
            "main_live_layout_revision": 7,
            "main_logged_interaction_ids": ["logged-1"],
            "main_typed_command": "explain this",
            "main_confirmed": True,
        }

        reset_main_live_turn_state(state)

        self.assertEqual(state["main_interaction_mode"], "Live")
        self.assertTrue(state["main_live_master_enabled"])
        self.assertEqual(
            state["main_confirmation_policy"],
            "Confidence-based auto",
        )
        self.assertEqual(
            state["main_auto_confirm_threshold"],
            0.91,
        )
        self.assertEqual(
            state["main_logged_interaction_ids"],
            ["logged-1"],
        )
        self.assertIsNone(state["main_live_proposal"])
        self.assertIsNone(
            state["main_live_original_transcript"]
        )
        self.assertIsNone(
            state["main_live_predicted_aoi_id"]
        )
        self.assertIsNone(
            state["main_live_layout_revision"]
        )
        self.assertEqual(state["main_typed_command"], "")
        self.assertFalse(state["main_confirmed"])

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
            "main_slide_width_percent": 75,
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

        self.assertEqual(
            state["main_slide_width_percent"],
            75,
        )


    def test_reset_clears_intent_state(
        self,
    ) -> None:
        state = {
            "main_target_scope": "Manual region",
            "main_typed_command": "explain this",
            "main_manual_bbox": [
                0.1,
                0.1,
                0.8,
                0.8,
            ],
            "main_selected_aoi_ids": [
                "aoi_1"
            ],
            "main_selection_matches": [
                {
                    "aoi_id": "aoi_1"
                }
            ],
            "main_selection_text": "Example",
            "main_selection_error": "temporary",
            "main_intent_source": "ui_action",
            "main_explicit_intent": "explain",
            "main_intent_result": {
                "intent": "explain"
            },
            "main_intent_error": "temporary",
            "main_confirmed": True,
            "main_tutor_result": {
                "answer": "temporary"
            },
            "main_xai_result": {
                "status": "temporary"
            },
            "main_active_slide_id": 3,
        }

        reset_main_turn_state(state)

        self.assertEqual(
            state["main_typed_command"],
            "",
        )

        self.assertIsNone(
            state["main_intent_source"]
        )

        self.assertIsNone(
            state["main_explicit_intent"]
        )

        self.assertIsNone(
            state["main_intent_result"]
        )

        self.assertIsNone(
            state["main_intent_error"]
        )

        self.assertEqual(
            state["main_active_slide_id"],
            3,
        )


    def test_reset_clears_confirmation_state(
        self,
    ) -> None:
        state = {
            **build_main_turn_defaults(),
            "main_confirmed": True,
            "main_confirmation_target_choice": (
                "aoi_1"
            ),
            "main_confirmation_source": (
                "manual_correction"
            ),
            "main_confirmed_aoi_id": "aoi_1",
            "main_corrected_from_aoi_id": (
                "aoi_2"
            ),
            "main_confirmed_interaction": {
                "interaction": {
                    "interaction_id": "temporary"
                }
            },
            "main_confirmation_error": (
                "temporary"
            ),
            "main_active_slide_id": 7,
        }

        reset_main_turn_state(state)

        self.assertFalse(
            state["main_confirmed"]
        )

        self.assertIsNone(
            state[
                "main_confirmation_target_choice"
            ]
        )

        self.assertIsNone(
            state["main_confirmation_source"]
        )

        self.assertIsNone(
            state["main_confirmed_aoi_id"]
        )

        self.assertIsNone(
            state[
                "main_corrected_from_aoi_id"
            ]
        )

        self.assertIsNone(
            state[
                "main_confirmed_interaction"
            ]
        )

        self.assertIsNone(
            state["main_confirmation_error"]
        )

        self.assertEqual(
            state["main_active_slide_id"],
            7,
        )


    def test_reset_clears_tutor_state(
        self,
    ) -> None:
        state = {
            **build_main_turn_defaults(),
            "main_tutor_result": {
                "answer": "temporary"
            },
            "main_tutor_error": (
                "temporary error"
            ),
            "main_xai_result": {
                "validation": {
                    "is_valid": True
                }
            },
            "main_active_slide_id": 4,
        }

        reset_main_turn_state(state)

        self.assertIsNone(
            state["main_tutor_result"]
        )

        self.assertIsNone(
            state["main_tutor_error"]
        )

        self.assertIsNone(
            state["main_xai_result"]
        )

        self.assertEqual(
            state["main_active_slide_id"],
            4,
        )


    def test_turn_reset_preserves_conversation(
        self,
    ) -> None:
        state = {
            **build_main_turn_defaults(),
            **build_main_conversation_defaults(),
            "main_typed_command": "explain this",
            "main_conversation_turns": [
                {
                    "turn_id": "turn_001"
                }
            ],
        }

        reset_main_turn_state(state)

        self.assertEqual(
            state["main_typed_command"],
            "",
        )

        self.assertEqual(
            state["main_conversation_turns"],
            [
                {
                    "turn_id": "turn_001"
                }
            ],
        )

    def test_conversation_reset_preserves_preferences(
        self,
    ) -> None:
        state = {
            **build_main_turn_defaults(),
            **build_main_conversation_defaults(),
            "main_typed_command": "explain this",
            "main_history_enabled": False,
            "main_history_max_items": 2,
            "main_conversation_turns": [
                {
                    "turn_id": "turn_001"
                }
            ],
        }

        reset_main_conversation_state(
            state,
            deck_id="deck_a",
        )

        self.assertEqual(
            state["main_conversation_turns"],
            [],
        )

        self.assertEqual(
            state["main_conversation_deck_id"],
            "deck_a",
        )

        self.assertFalse(
            state["main_history_enabled"]
        )

        self.assertEqual(
            state["main_history_max_items"],
            2,
        )

        self.assertEqual(
            state["main_typed_command"],
            "explain this",
        )



if __name__ == "__main__":
    unittest.main()
