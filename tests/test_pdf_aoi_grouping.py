from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz

from modules.slide.aoi_grouping import group_pdf_text
from modules.slide.aoi_manager import AUTO_AOI_SCHEMA_VERSION, AOIManager
from modules.slide.ocr import TextBox
from modules.slide.slide_parser import SlideParser, _extract_pdf_text_boxes_from_page_dict


PDF_PAGE_DICT = {
    "blocks": [
        {
            "type": 0,
            "number": 12,
            "bbox": [40.0, 20.0, 190.0, 60.0],
            "lines": [
                {
                    "bbox": [40.0, 20.0, 180.0, 36.0],
                    "dir": [1.0, 0.0],
                    "spans": [
                        {
                            "text": "❒ ",
                            "bbox": [40.0, 20.0, 48.0, 36.0],
                            "font": "ZapfDingbats",
                            "size": 9.0,
                            "flags": 0,
                        },
                        {
                            "text": "Wrapped body text",
                            "bbox": [48.0, 20.0, 180.0, 36.0],
                            "font": "NimbusSanL-Regu",
                            "size": 8.432389,
                            "flags": 4,
                        },
                    ],
                },
                {
                    "bbox": [48.0, 40.0, 190.0, 56.0],
                    "dir": [1.0, 0.0],
                    "spans": [
                        {
                            "text": "continues on another line",
                            "bbox": [48.0, 40.0, 190.0, 56.0],
                            "font": "NimbusSanL-Regu",
                            "size": 8.432389,
                            "flags": 4,
                        }
                    ],
                },
            ],
        }
    ]
}


class PDFMetadataExtractionTest(unittest.TestCase):
    def test_text_box_defaults_preserve_ocr_construction(self) -> None:
        box = TextBox("body", [0.1, 0.2, 0.4, 0.3], 0.9, "ocr")
        self.assertIsNone(box.block_id)
        self.assertFalse(box.starts_bullet)

    def test_pdf_line_keeps_block_style_direction_and_bullet_metadata(self) -> None:
        boxes = _extract_pdf_text_boxes_from_page_dict(PDF_PAGE_DICT, 200.0, 100.0)
        first = boxes[0]
        self.assertEqual(first.block_id, 12)
        self.assertEqual(first.line_id, 0)
        self.assertEqual(first.font_family, "NimbusSanL-Regu")
        self.assertAlmostEqual(first.font_size or 0.0, 8.432389, places=5)
        self.assertEqual(first.font_flags, 4)
        self.assertEqual(first.direction, (1.0, 0.0))
        self.assertTrue(first.starts_bullet)
        self.assertEqual(first.block_bbox, [0.2, 0.2, 0.95, 0.6])
        self.assertEqual(first.bbox, [0.2, 0.2, 0.9, 0.36])

    def test_margin_profile_requires_recurrence_in_same_band(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "margin-profile.pdf"
            document = fitz.open()
            for page_index in range(3):
                page = document.new_page(width=200.0, height=100.0)
                if page_index < 2:
                    page.insert_text((10.0, 8.0), "Course Header", fontsize=5.0)
                    page.insert_text((10.0, 97.0), "7/55", fontsize=5.0)
                if page_index == 0:
                    page.insert_text((100.0, 8.0), "Unique Slide Body", fontsize=5.0)
            document.save(pdf_path)
            document.close()

            parser = SlideParser(str(root / "data"))
            parser.metadata["deck"] = {
                "deck_id": "deck",
                "pdf_path": str(pdf_path),
                "page_count": 3,
            }
            top, bottom = parser.extract_pdf_margin_profile("deck")

        self.assertIn("course header", top)
        self.assertIn("7/55", bottom)
        self.assertNotIn("unique slide body", top | bottom)


def pdf_line(
    text: str,
    bbox: list[float],
    *,
    block_id: int,
    line_id: int = 0,
    font_size: float = 10.0,
    font_family: str = "Body",
    font_flags: int = 0,
    starts_bullet: bool = False,
) -> TextBox:
    return TextBox(
        text,
        bbox,
        1.0,
        "pdf_text",
        block_id=block_id,
        line_id=line_id,
        block_bbox=list(bbox),
        font_size=font_size,
        font_family=font_family,
        font_flags=font_flags,
        direction=(1.0, 0.0),
        starts_bullet=starts_bullet,
    )


class PDFParagraphGroupingTest(unittest.TestCase):
    def test_same_block_wrapped_lines_form_one_paragraph(self) -> None:
        lines = [
            pdf_line("A paragraph wraps onto", [0.10, 0.30, 0.55, 0.34], block_id=1, line_id=0),
            pdf_line("the following rendered line.", [0.10, 0.345, 0.62, 0.385], block_id=1, line_id=1),
        ]

        result = group_pdf_text(lines)

        self.assertEqual(len(result.content_groups), 1)
        self.assertEqual(result.content_groups[0].role, "paragraph")
        self.assertEqual(result.content_groups[0].text, "A paragraph wraps onto the following rendered line.")
        self.assertEqual(result.content_groups[0].bbox, [0.10, 0.30, 0.62, 0.385])

    def test_multiple_sentences_in_same_block_remain_one_paragraph(self) -> None:
        lines = [
            pdf_line("First sentence is complete.", [0.10, 0.30, 0.55, 0.34], block_id=2, line_id=0),
            pdf_line("Second sentence is complete. Third sentence too.", [0.10, 0.345, 0.80, 0.385], block_id=2, line_id=1),
        ]

        result = group_pdf_text(lines)

        self.assertEqual(len(result.content_groups), 1)
        self.assertEqual(
            result.content_groups[0].text,
            "First sentence is complete. Second sentence is complete. Third sentence too.",
        )

    def test_new_bullet_in_same_block_starts_new_aoi(self) -> None:
        lines = [
            pdf_line("• First item", [0.10, 0.30, 0.50, 0.34], block_id=3, line_id=0, starts_bullet=True),
            pdf_line("continues here", [0.13, 0.345, 0.52, 0.385], block_id=3, line_id=1),
            pdf_line("• Second item", [0.10, 0.405, 0.50, 0.445], block_id=3, line_id=2, starts_bullet=True),
        ]

        result = group_pdf_text(lines)

        self.assertEqual([group.role for group in result.content_groups], ["list_item", "list_item"])
        self.assertEqual(result.content_groups[0].text, "• First item continues here")
        self.assertEqual(result.content_groups[1].text, "• Second item")

    def test_real_slide_8_cross_block_continuation_merges(self) -> None:
        first = pdf_line(
            "❒ It encompasses a wide variety of states, such as",
            [0.4813228811, 0.3113853053, 0.9228071452, 0.3662475159],
            block_id=13,
            font_size=8.518,
            font_family="NimbusSanL-Regu",
            font_flags=4,
            starts_bullet=True,
        )
        second = pdf_line(
            "perception, thinking, fantasizing, dreaming, and altered",
            [0.5083544846, 0.3689701320, 0.9759829030, 0.4100],
            block_id=14,
            font_size=8.518,
            font_family="NimbusSanL-Regu",
            font_flags=4,
        )

        result = group_pdf_text([first, second])

        self.assertEqual(len(result.content_groups), 1)
        self.assertEqual(result.content_groups[0].role, "list_item")
        self.assertEqual(result.content_groups[0].bbox, [first.x_min, first.y_min, second.x_max, second.y_max])
        self.assertEqual(result.content_groups[0].text, f"{first.text} {second.text}")

    def test_adjacent_columns_do_not_merge(self) -> None:
        lines = [
            pdf_line("Left column paragraph", [0.08, 0.30, 0.43, 0.35], block_id=4),
            pdf_line("Right column paragraph", [0.57, 0.30, 0.92, 0.35], block_id=5),
        ]

        result = group_pdf_text(lines)

        self.assertEqual(len(result.content_groups), 2)
        self.assertEqual([group.text for group in result.content_groups], ["Left column paragraph", "Right column paragraph"])

    def test_title_heading_header_footer_and_page_number_are_excluded(self) -> None:
        lines = [
            pdf_line("Course Header", [0.10, 0.03, 0.40, 0.07], block_id=6, font_size=8.0),
            pdf_line("Slide Title", [0.10, 0.14, 0.70, 0.20], block_id=7, font_size=16.0, font_flags=16),
            pdf_line("Section Heading", [0.10, 0.30, 0.55, 0.35], block_id=8, font_size=13.0, font_flags=16),
            pdf_line("Body paragraph content", [0.10, 0.42, 0.75, 0.47], block_id=9, font_size=10.0),
            pdf_line("Body paragraph continuation", [0.10, 0.475, 0.72, 0.525], block_id=9, line_id=1, font_size=10.0),
            pdf_line("Course Footer", [0.10, 0.90, 0.40, 0.94], block_id=10, font_size=8.0),
            pdf_line("7/55", [0.80, 0.92, 0.90, 0.96], block_id=11, font_size=8.0),
        ]

        result = group_pdf_text(
            lines,
            repeated_top_text=frozenset({"course header"}),
            repeated_bottom_text=frozenset({"course footer"}),
        )

        self.assertEqual(
            [group.text for group in result.content_groups],
            ["Body paragraph content Body paragraph continuation"],
        )
        self.assertEqual(
            {group.role for group in result.excluded_groups},
            {"header", "title", "heading", "footer", "page_number"},
        )

    def test_inline_bold_body_text_is_retained(self) -> None:
        lines = [
            pdf_line("Regular body baseline", [0.10, 0.30, 0.65, 0.35], block_id=12),
            pdf_line("Important term remains inline with body prose", [0.10, 0.355, 0.80, 0.405], block_id=12, line_id=1),
        ]

        result = group_pdf_text(lines)

        self.assertEqual(len(result.content_groups), 1)
        self.assertEqual(result.content_groups[0].role, "paragraph")
        self.assertIn("Important term", result.content_groups[0].text)

    def test_stale_auto_aoi_version_forces_reprocessing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = AOIManager(directory)
            stale = {
                "slide_id": 1,
                "slide_image_path": str(Path(directory) / "deck_slide_001_250dpi.png"),
                "ocr_text": "stale",
                "aois": [],
                "auto_aoi_method": "pdf_text_semantic",
                "auto_aoi_version": "pdf-semantic-v1",
            }
            refreshed = dict(stale, auto_aoi_version=AUTO_AOI_SCHEMA_VERSION)
            manager.manifest["deck:1"] = stale
            with patch.object(manager, "process_slide", return_value=refreshed) as process_slide, patch.object(
                manager,
                "build_llm_guided_aois",
                side_effect=ValueError("stop after regeneration"),
            ):
                manager.process_llm_aoi("deck", 1, allow_ocr=False)

        process_slide.assert_called_once_with("deck", 1, dpi=250, allow_ocr=False)


if __name__ == "__main__":
    unittest.main()
