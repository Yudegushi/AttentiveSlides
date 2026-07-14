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
                    "error": None,
                },
            )

    def test_llm_deck_batch_is_sequential_skips_success_and_continues_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            state_reads = []
            processed = []
            events = []

            states = {
                1: {"eligible": True, "status": "used"},
                2: {"eligible": False, "status": "not_requested"},
                3: {"eligible": False, "status": "not_requested"},
            }

            def read_state(deck_id, slide_id):
                self.assertEqual(deck_id, "deck")
                state_reads.append(slide_id)
                return states[slide_id]

            def prepare(deck_id, slide_id, *, force):
                self.assertEqual(deck_id, "deck")
                processed.append((slide_id, force))
                return {
                    "eligible": slide_id == 3,
                    "status": "used" if slide_id == 3 else "fallback_used",
                }

            with patch.object(
                workspace.slide_parser,
                "get_page_count",
                return_value=3,
            ), patch.object(
                workspace,
                "get_llm_aoi_state",
                side_effect=read_state,
            ), patch.object(
                workspace,
                "prepare_llm_aoi",
                side_effect=prepare,
            ):
                summary = workspace.prepare_llm_deck(
                    "deck",
                    progress_callback=lambda completed, total, result: events.append(
                        (completed, total, result["slide_id"], result["status"])
                    ),
                )

            self.assertEqual(state_reads, [1, 2, 3])
            self.assertEqual(processed, [(2, True), (3, True)])
            self.assertEqual(
                events,
                [
                    (1, 3, 1, "skipped"),
                    (2, 3, 2, "fallback_used"),
                    (3, 3, 3, "used"),
                ],
            )
            self.assertEqual(
                summary,
                {"successful": 1, "fallback": 1, "skipped": 1, "total": 3},
            )

    def test_llm_deck_batch_sanitizes_page_exceptions_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            prepared = []
            events = []

            def read_state(_deck_id, slide_id):
                if slide_id == 1:
                    raise RuntimeError("state SECRET_STATE_TOKEN")
                return {"eligible": slide_id == 4, "status": "used"}

            def prepare(_deck_id, slide_id, *, force):
                prepared.append((slide_id, force))
                if slide_id == 2:
                    raise RuntimeError("worker SECRET_WORKER_TOKEN")
                return {"eligible": True, "status": "used"}

            with patch.object(
                workspace.slide_parser,
                "get_page_count",
                return_value=4,
            ), patch.object(
                workspace,
                "get_llm_aoi_state",
                side_effect=read_state,
            ), patch.object(
                workspace,
                "prepare_llm_aoi",
                side_effect=prepare,
            ):
                summary = workspace.prepare_llm_deck(
                    "deck",
                    progress_callback=lambda completed, total, result: events.append(
                        (completed, total, dict(result))
                    ),
                )

            self.assertEqual(prepared, [(2, True), (3, True)])
            self.assertEqual(
                summary,
                {"successful": 1, "fallback": 2, "skipped": 1, "total": 4},
            )
            self.assertEqual(
                [(completed, total) for completed, total, _result in events],
                [(1, 4), (2, 4), (3, 4), (4, 4)],
            )
            self.assertEqual(
                [result["status"] for _completed, _total, result in events],
                ["fallback_used", "fallback_used", "used", "skipped"],
            )
            for _completed, _total, result in events[:2]:
                self.assertEqual(result["eligible"], False)
                self.assertEqual(
                    result["error"],
                    "Unable to prepare LLM AOIs for this slide.",
                )
                self.assertNotIn("SECRET", str(result))

    def test_llm_deck_batch_does_not_swallow_progress_callback_exception(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = UploadedDeckWorkspace(directory)
            callback_error = RuntimeError("callback failed")

            with patch.object(
                workspace.slide_parser,
                "get_page_count",
                return_value=2,
            ), patch.object(
                workspace,
                "get_llm_aoi_state",
                return_value={"eligible": True, "status": "used"},
            ) as state_read:
                with self.assertRaises(RuntimeError) as raised:
                    workspace.prepare_llm_deck(
                        "deck",
                        progress_callback=lambda *_args: (_ for _ in ()).throw(
                            callback_error
                        ),
                    )

            self.assertIs(raised.exception, callback_error)
            self.assertEqual(state_read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
