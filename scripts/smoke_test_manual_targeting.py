"""Recorded smoke test for PDF upload and manual targeting."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz

ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )

from llm_smoke_common import (
    base_record,
    write_record,
)
from modules.system.manual_targeting import (
    extract_latest_rectangle,
)
from modules.system.uploaded_deck_service import (
    UploadedDeckWorkspace,
)


def create_sample_pdf(
    path: Path,
) -> None:
    document = fitz.open()

    page = document.new_page(
        width=960,
        height=540,
    )

    page.insert_textbox(
        fitz.Rect(
            100,
            100,
            860,
            260,
        ),
        (
            "Manual selection provides "
            "a privacy-preserving alternative "
            "to gaze-based reference resolution."
        ),
        fontsize=24,
    )

    document.save(
        str(path)
    )
    document.close()


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    output_path = Path(
        arguments.output
    ).resolve()

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    sample_pdf_path = (
        output_path.parent
        / "manual_targeting_sample.pdf"
    )

    create_sample_pdf(
        sample_pdf_path
    )

    workspace = UploadedDeckWorkspace(
        output_path.parent
        / "runtime"
    )

    summary = workspace.ingest_pdf(
        filename="sample.pdf",
        content=sample_pdf_path.read_bytes(),
    )

    browser = workspace.open_browser(
        summary.deck_id
    )

    slide = browser.get_slide(1)

    candidate = next(
        aoi
        for aoi in slide.aois
        if (
            aoi.aoi_id
            != "whole_slide"
            and aoi.type
            != "footer"
            and aoi.text.strip()
        )
    )

    x_min, y_min, x_max, y_max = (
        candidate.bbox
    )

    canvas_width = 720
    canvas_height = 405

    canvas_json = {
        "objects": [
            {
                "type": "rect",
                "left": (
                    x_min
                    * canvas_width
                ),
                "top": (
                    y_min
                    * canvas_height
                ),
                "width": (
                    (x_max - x_min)
                    * canvas_width
                ),
                "height": (
                    (y_max - y_min)
                    * canvas_height
                ),
                "scaleX": 1.0,
                "scaleY": 1.0,
                "angle": 0,
            }
        ]
    }

    selection = (
        extract_latest_rectangle(
            canvas_json,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            aois=slide.aois,
        )
    )

    checks = {
        "pdf_ingested": (
            summary.page_count == 1
        ),
        "slide_rendered": (
            slide.image_available
        ),
        "slide_text_extracted": bool(
            slide.slide_text.strip()
        ),
        "aois_generated": (
            len(slide.aois) >= 1
        ),
        "manual_selection_created": (
            selection is not None
        ),
        "candidate_mapped": (
            selection is not None
            and candidate.aoi_id
            in {
                match.aoi_id
                for match
                in selection.matches
            }
        ),
        "normalized_bbox": (
            selection is not None
            and all(
                0.0 <= value <= 1.0
                for value
                in selection.bbox
            )
        ),
        "selected_text_available": (
            selection is not None
            and bool(
                selection
                .selected_text
                .strip()
            )
        ),
    }

    payload = base_record(
        "manual_targeting_smoke"
    )

    payload.update(
        {
            "passed": all(
                checks.values()
            ),
            "checks": checks,
            "deck": summary.to_dict(),
            "slide": slide.to_dict(),
            "selection": (
                selection.to_dict()
                if selection
                is not None
                else None
            ),
        }
    )

    write_record(
        str(output_path),
        payload,
    )

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
