"""Run PyMuPDF and optional OCR outside the Streamlit process."""

from __future__ import annotations

import argparse
import faulthandler
import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(
    __file__
).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPOSITORY_ROOT),
    )


faulthandler.enable(all_threads=True)


def write_payload(
    output_path: Path,
    payload: dict[str, Any],
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = output_path.with_suffix(
        output_path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(output_path)


def probe_pdf(
    input_path: Path,
) -> dict[str, Any]:
    import pymupdf

    if not input_path.is_file():
        raise FileNotFoundError(
            f"PDF does not exist: {input_path}"
        )

    with pymupdf.open(
        str(input_path)
    ) as document:
        if document.needs_pass:
            raise ValueError(
                "Password-protected PDFs "
                "are not currently supported."
            )

        page_count = int(
            document.page_count
        )

        if page_count <= 0:
            raise ValueError(
                "PDF contains no pages."
            )

        first_page = document.load_page(0)

        embedded_text_length = len(
            first_page.get_text("text").strip()
        )

    return {
        "page_count": page_count,
        "first_page_embedded_text_length": (
            embedded_text_length
        ),
    }


def prepare_slide(
    *,
    data_dir: Path,
    deck_id: str,
    slide_id: int,
    dpi: int,
    enable_ocr: bool,
) -> dict[str, Any]:
    from modules.slide.aoi_manager import (
        AOIManager,
    )

    manager = AOIManager(
        str(data_dir)
    )

    slide_data = manager.process_slide(
        deck_id,
        slide_id,
        dpi=dpi,
        allow_ocr=enable_ocr,
    )

    return {
        "deck_id": deck_id,
        "slide_id": slide_id,
        "slide_image_path": (
            slide_data.get(
                "slide_image_path"
            )
        ),
        "text_source": slide_data.get(
            "text_source"
        ),
        "auto_aoi_method": slide_data.get(
            "auto_aoi_method"
        ),
        "aoi_count": len(
            slide_data.get("aois", [])
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    subparsers = parser.add_subparsers(
        dest="action",
        required=True,
    )

    probe_parser = subparsers.add_parser(
        "probe"
    )

    probe_parser.add_argument(
        "--input-path",
        required=True,
    )

    prepare_parser = subparsers.add_parser(
        "prepare-slide"
    )

    prepare_parser.add_argument(
        "--data-dir",
        required=True,
    )

    prepare_parser.add_argument(
        "--deck-id",
        required=True,
    )

    prepare_parser.add_argument(
        "--slide-id",
        required=True,
        type=int,
    )

    prepare_parser.add_argument(
        "--dpi",
        default=220,
        type=int,
    )

    prepare_parser.add_argument(
        "--enable-ocr",
        action="store_true",
    )

    arguments = parser.parse_args()

    output_path = Path(
        arguments.output
    ).resolve()

    try:
        if arguments.action == "probe":
            result = probe_pdf(
                Path(
                    arguments.input_path
                ).resolve()
            )

        elif arguments.action == "prepare-slide":
            result = prepare_slide(
                data_dir=Path(
                    arguments.data_dir
                ).resolve(),
                deck_id=arguments.deck_id,
                slide_id=arguments.slide_id,
                dpi=arguments.dpi,
                enable_ocr=(
                    arguments.enable_ocr
                ),
            )

        else:
            raise ValueError(
                f"Unsupported action: "
                f"{arguments.action!r}"
            )

    except Exception as exc:
        write_payload(
            output_path,
            {
                "ok": False,
                "error_type": (
                    type(exc).__name__
                ),
                "error": str(exc),
            },
        )
        raise

    write_payload(
        output_path,
        {
            "ok": True,
            "result": result,
        },
    )


if __name__ == "__main__":
    main()
