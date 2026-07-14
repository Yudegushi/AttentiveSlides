"""Tests for runtime PDF upload and slide preparation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

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

    def test_llm_browser_selection_never_prepares_during_slide_lookup(self) -> None:
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
                "aois": [{"aoi_id": "whole_slide", "bbox": [0, 0, 1, 1], "type": "whole_slide", "source": "rule"}],
            }
            browser = workspace.open_browser(deck_id, use_llm_aoi=True)
            with patch.object(workspace, "prepare_llm_aoi") as prepare, \
                 patch.object(workspace, "_get_or_process_slide", return_value=workspace.aoi_manager.manifest["deck:1"]):
                browser.get_slide(1)
                browser.get_slide(1)
            prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
