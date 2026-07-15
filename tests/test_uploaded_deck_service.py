"""Tests for runtime PDF upload and slide preparation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from modules.slide.aoi_manager import AUTO_AOI_SCHEMA_VERSION
from modules.system.uploaded_deck_service import (
    UploadedDeckWorkspace,
)


def make_test_pdf() -> bytes:
    document = fitz.open()

    page = document.new_page(
        width=960,
        height=540,
    )

    page.insert_textbox(
        fitz.Rect(
            80,
            70,
            880,
            200,
        ),
        (
            "Fixation maintains gaze "
            "on a location while saccades "
            "are rapid movements between "
            "fixations."
        ),
        fontsize=22,
    )

    data = document.tobytes()
    document.close()

    return data


class TestUploadedDeckService(
    unittest.TestCase
):
    def test_ingest_and_prepare_pdf(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = (
                UploadedDeckWorkspace(
                    directory
                )
            )

            summary = workspace.ingest_pdf(
                filename="lecture.pdf",
                content=make_test_pdf(),
            )

            self.assertEqual(
                summary.page_count,
                1,
            )

            browser = (
                workspace.open_browser(
                    summary.deck_id
                )
            )

            self.assertEqual(
                browser.slide_ids,
                (1,),
            )

            slide = browser.get_slide(1)

            self.assertTrue(
                slide.image_available
            )

            self.assertIn(
                "Fixation",
                slide.slide_text,
            )

            self.assertGreaterEqual(
                len(slide.aois),
                1,
            )

            self.assertTrue(
                any(
                    aoi.aoi_id
                    == "whole_slide"
                    for aoi
                    in slide.aois
                )
            )

    def test_identical_upload_is_reused(
        self,
    ) -> None:
        content = make_test_pdf()

        with tempfile.TemporaryDirectory() as directory:
            workspace = (
                UploadedDeckWorkspace(
                    directory
                )
            )

            first = workspace.ingest_pdf(
                filename="first.pdf",
                content=content,
            )

            second = workspace.ingest_pdf(
                filename="second.pdf",
                content=content,
            )

            self.assertEqual(
                first.deck_id,
                second.deck_id,
            )

    def test_non_pdf_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = (
                UploadedDeckWorkspace(
                    directory
                )
            )

            with self.assertRaises(
                ValueError
            ):
                workspace.ingest_pdf(
                    filename="notes.txt",
                    content=b"not a pdf",
                )

    def test_prepare_llm_aoi_uses_one_worker_and_reloads_manager(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            deck_id = "deck"
            workspace.slide_parser.metadata[deck_id] = {
                "deck_id": deck_id,
                "original_name": "deck.pdf",
                "pdf_path": str(Path(directory) / "uploaded_decks" / "deck.pdf"),
                "page_count": 1,
            }
            commands = []
            old_manager = workspace.aoi_manager

            def fake_worker(arguments, *, timeout_seconds):
                commands.append((list(arguments), timeout_seconds))
                old_manager.manifest["deck:1"] = {
                    "slide_id": 1,
                    "slide_image_path": "deck_slide_001_220dpi.png",
                    "ocr_text": "anchors",
                    "aois": [{"aoi_id": "whole_slide", "bbox": [0, 0, 1, 1], "type": "whole_slide", "source": "rule"}],
                    "llm_aois": [],
                    "llm_aoi_status": "fallback_used",
                    "llm_aoi_model": "fake-vlm",
                    "llm_aoi_profile": None,
                    "llm_aoi_error": "TimeoutError: timeout",
                }
                old_manager._save_manifest()
                return {"status": "fallback_used"}

            with patch.object(workspace, "_run_native_worker", side_effect=fake_worker):
                state = workspace.prepare_llm_aoi(deck_id, 1, force=True)

            self.assertEqual(commands[0][0][0], "prepare-llm-aoi")
            self.assertIn("--force", commands[0][0])
            self.assertEqual(commands[0][1], 300)
            self.assertIsNot(workspace.aoi_manager, old_manager)
            self.assertEqual(state["status"], "fallback_used")

    def test_slide_lookup_never_calls_prepare_llm_aoi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            deck_id = "deck"
            workspace.slide_parser.metadata[deck_id] = {
                "deck_id": deck_id,
                "original_name": "deck.pdf",
                "pdf_path": str(Path(directory) / "uploaded_decks" / "deck.pdf"),
                "page_count": 1,
            }
            workspace.aoi_manager.manifest["deck:1"] = {
                "slide_id": 1,
                "slide_image_path": "",
                "ocr_text": "anchors",
                "auto_aoi_version": AUTO_AOI_SCHEMA_VERSION,
                "aois": [{"aoi_id": "whole_slide", "bbox": [0, 0, 1, 1], "type": "whole_slide", "source": "rule"}],
            }
            browser = workspace.open_browser(deck_id)
            with patch.object(workspace, "prepare_llm_aoi") as prepare, \
                 patch.object(workspace, "_get_or_process_slide", return_value=workspace.aoi_manager.manifest["deck:1"]):
                browser.get_slide(1)
                browser.get_slide(1)
            prepare.assert_not_called()

    def test_uploaded_browser_automatically_uses_eligible_cached_llm_aoi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            deck_id = "deck"
            workspace.slide_parser.metadata[deck_id] = {
                "deck_id": deck_id,
                "original_name": "deck.pdf",
                "pdf_path": str(Path(directory) / "uploaded_decks" / "deck.pdf"),
                "page_count": 1,
            }
            slide_data = {
                "slide_id": 1,
                "slide_image_path": "",
                "ocr_text": "anchors",
                "auto_aoi_version": AUTO_AOI_SCHEMA_VERSION,
                "aois": [{
                    "aoi_id": "whole_slide",
                    "bbox": [0, 0, 1, 1],
                    "type": "whole_slide",
                    "source": "rule",
                }],
                "llm_aois": [{
                    "aoi_id": "llm_aoi_1",
                    "bbox": [0.2, 0.2, 0.8, 0.7],
                    "type": "diagram",
                    "source": "llm_guided",
                }],
                "llm_aoi_status": "used",
                "llm_aoi_profile": "eligible-profile",
            }
            workspace.aoi_manager.manifest["deck:1"] = slide_data

            with patch.object(
                workspace.aoi_manager.llm_aoi_generator,
                "is_configured",
                return_value=True,
            ), patch.object(
                workspace.aoi_manager.llm_aoi_generator,
                "profile",
                return_value="eligible-profile",
            ), patch.object(
                workspace,
                "_get_or_process_slide",
                return_value=slide_data,
            ):
                slide = workspace.open_browser(deck_id).get_slide(1)

            self.assertEqual(slide.aoi_profile, "eligible-profile")
            self.assertEqual(
                [aoi.aoi_id for aoi in slide.aois],
                ["llm_aoi_1", "whole_slide"],
            )

    def test_uploaded_browser_uses_deterministic_aoi_when_page_has_no_eligible_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            deck_id = "deck"
            workspace.slide_parser.metadata[deck_id] = {
                "deck_id": deck_id,
                "original_name": "deck.pdf",
                "pdf_path": str(Path(directory) / "uploaded_decks" / "deck.pdf"),
                "page_count": 1,
            }
            slide_data = {
                "slide_id": 1,
                "slide_image_path": "",
                "ocr_text": "anchors",
                "auto_aoi_version": AUTO_AOI_SCHEMA_VERSION,
                "aois": [{
                    "aoi_id": "pdf_paragraph_1",
                    "bbox": [0.1, 0.2, 0.8, 0.4],
                    "type": "text",
                    "source": "pdf_text_semantic",
                    "role": "paragraph",
                }],
                "llm_aois": [],
                "llm_aoi_status": "not_requested",
                "llm_aoi_profile": None,
            }
            workspace.aoi_manager.manifest["deck:1"] = slide_data

            with patch.object(
                workspace.aoi_manager.llm_aoi_generator,
                "is_configured",
                return_value=True,
            ), patch.object(
                workspace,
                "_get_or_process_slide",
                return_value=slide_data,
            ), patch.object(workspace, "prepare_llm_aoi") as prepare:
                slide = workspace.open_browser(deck_id).get_slide(1)

            prepare.assert_not_called()
            self.assertEqual(slide.aoi_profile, "deterministic")
            self.assertEqual(
                [aoi.aoi_id for aoi in slide.aois],
                ["pdf_paragraph_1", "whole_slide"],
            )

    def test_prepare_llm_aoi_hides_native_worker_exception_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            with patch.object(
                workspace,
                "_run_native_worker",
                side_effect=RuntimeError(
                    "Worker stderr: endpoint=SECRET_ENDPOINT_TOKEN response=private"
                ),
            ):
                with self.assertRaises(RuntimeError) as raised:
                    workspace.prepare_llm_aoi("deck", 1)
            message = str(raised.exception)
            self.assertEqual(message, "Unable to prepare LLM AOIs for this slide.")
            self.assertNotIn("SECRET_ENDPOINT_TOKEN", message)

    def test_missing_llm_state_read_is_stable_and_side_effect_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            manager = workspace.aoi_manager

            with patch.object(
                manager.llm_aoi_generator,
                "is_configured",
                return_value=True,
            ), patch.object(manager, "process_slide") as process_slide, patch.object(
                manager,
                "_save_manifest",
            ) as save_manifest:
                state = manager.get_llm_aoi_state("missing-deck", 4)

            process_slide.assert_not_called()
            save_manifest.assert_not_called()
            self.assertNotIn("missing-deck:4", manager.manifest)
            self.assertEqual(
                state,
                {
                    "configured": True,
                    "status": "not_requested",
                    "model": None,
                    "profile": None,
                    "expected_profile": None,
                    "eligible": False,
                    "aoi_count": 0,
                    "visual_count": 0,
                    "visual_context_status": "empty",
                    "error": None,
                },
            )


if __name__ == "__main__":
    unittest.main()
