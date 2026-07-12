"""Tests for runtime PDF upload and slide preparation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
