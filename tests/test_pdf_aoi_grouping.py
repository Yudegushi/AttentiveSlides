from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

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


if __name__ == "__main__":
    unittest.main()
