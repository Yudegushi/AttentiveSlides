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


def prepare_previews(
    *,
    data_dir: Path,
    deck_id: str,
    max_width: int,
    max_height: int,
) -> dict[str, Any]:
    """Render lightweight rail previews in one sequential PDF pass."""
    import pymupdf

    from modules.slide.slide_parser import SlideParser

    if max_width <= 0 or max_height <= 0:
        raise ValueError("Preview dimensions must be positive.")

    parser = SlideParser(str(data_dir))
    deck_info = parser.get_deck_info(deck_id)
    if deck_info is None:
        raise ValueError(f"Unknown deck_id: {deck_id}")

    pdf_path = Path(str(deck_info["pdf_path"]))
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Stored PDF is missing: {pdf_path}")

    preview_dir = data_dir / "slide_previews" / deck_id
    preview_dir.mkdir(parents=True, exist_ok=True)
    rendered_slide_ids: list[int] = []

    with pymupdf.open(str(pdf_path)) as document:
        page_count = int(document.page_count)
        for page_index in range(page_count):
            slide_id = page_index + 1
            target_path = preview_dir / f"slide_{slide_id:03d}.png"
            if target_path.is_file() and target_path.stat().st_size > 0:
                rendered_slide_ids.append(slide_id)
                continue

            page = document.load_page(page_index)
            page_width = max(float(page.rect.width), 1.0)
            page_height = max(float(page.rect.height), 1.0)
            scale = min(max_width / page_width, max_height / page_height)
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                alpha=False,
            )
            temporary_path = preview_dir / f"slide_{slide_id:03d}.tmp.png"
            temporary_path.write_bytes(pixmap.tobytes("png"))
            temporary_path.replace(target_path)
            rendered_slide_ids.append(slide_id)

    completion_path = preview_dir / ".complete.json"
    write_payload(
        completion_path,
        {
            "deck_id": deck_id,
            "page_count": page_count,
            "ready": rendered_slide_ids,
        },
    )
    return {
        "deck_id": deck_id,
        "page_count": page_count,
        "preview_dir": str(preview_dir),
    }


def prepare_llm_aoi(
    *,
    data_dir: Path,
    deck_id: str,
    slide_id: int,
    dpi: int,
    enable_ocr: bool,
    force: bool,
) -> dict[str, Any]:
    from modules.slide.aoi_manager import AOIManager

    slide_data = AOIManager(str(data_dir)).process_llm_aoi(
        deck_id,
        slide_id,
        dpi=dpi,
        allow_ocr=enable_ocr,
        force=force,
    )
    return {
        "deck_id": deck_id,
        "slide_id": slide_id,
        "status": slide_data.get("llm_aoi_status", "fallback_used"),
        "model": slide_data.get("llm_aoi_model"),
        "profile": slide_data.get("llm_aoi_profile"),
        "aoi_count": len(slide_data.get("llm_aois", [])),
        "error": slide_data.get("llm_aoi_error"),
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

    preview_parser = subparsers.add_parser(
        "prepare-previews"
    )
    preview_parser.add_argument(
        "--data-dir",
        required=True,
    )
    preview_parser.add_argument(
        "--deck-id",
        required=True,
    )
    preview_parser.add_argument(
        "--max-width",
        default=220,
        type=int,
    )
    preview_parser.add_argument(
        "--max-height",
        default=124,
        type=int,
    )

    llm_parser = subparsers.add_parser("prepare-llm-aoi")
    llm_parser.add_argument("--data-dir", required=True)
    llm_parser.add_argument("--deck-id", required=True)
    llm_parser.add_argument("--slide-id", required=True, type=int)
    llm_parser.add_argument("--dpi", default=220, type=int)
    llm_parser.add_argument("--enable-ocr", action="store_true")
    llm_parser.add_argument("--force", action="store_true")

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

        elif arguments.action == "prepare-llm-aoi":
            result = prepare_llm_aoi(
                data_dir=Path(arguments.data_dir).resolve(),
                deck_id=arguments.deck_id,
                slide_id=arguments.slide_id,
                dpi=arguments.dpi,
                enable_ocr=arguments.enable_ocr,
                force=arguments.force,
            )

        elif arguments.action == "prepare-previews":
            result = prepare_previews(
                data_dir=Path(arguments.data_dir).resolve(),
                deck_id=arguments.deck_id,
                max_width=arguments.max_width,
                max_height=arguments.max_height,
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
