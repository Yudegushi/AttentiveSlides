"""
PDF loading, metadata management, slide rendering, and embedded text extraction.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from json import JSONDecodeError
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz
except ImportError as exc:
    raise ImportError(
        "PyMuPDF is required: "
        "python -m pip install pymupdf"
    ) from exc

from .ocr import TextBox, clamp


BULLET_PREFIXES = ("•", "❒", "▪", "◦", "‣", "–", "—")
NUMBERED_LIST_PATTERN = re.compile(r"^\s*\d+[.)](?:\s|$)")


def _normalized_bbox(
    bbox: list[float] | tuple[float, ...],
    page_width: float,
    page_height: float,
) -> list[float]:
    x1, y1, x2, y2 = (float(value) for value in bbox)
    return [
        clamp(x1 / page_width),
        clamp(y1 / page_height),
        clamp(x2 / page_width),
        clamp(y2 / page_height),
    ]


def _dominant_text_span(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        span
        for span in spans
        if str(span.get("text", "")).strip()
        and "dingbat" not in str(span.get("font", "")).casefold()
        and not str(span.get("text", "")).strip().startswith(BULLET_PREFIXES)
    ]
    if not candidates:
        candidates = [span for span in spans if str(span.get("text", "")).strip()]
    return max(
        candidates,
        key=lambda span: len(str(span.get("text", "")).strip()),
        default=None,
    )


def _starts_list_marker(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith(BULLET_PREFIXES) or bool(NUMBERED_LIST_PATTERN.match(text))


def _line_bbox(line: dict[str, Any], spans: list[dict[str, Any]]) -> list[float] | tuple[float, ...] | None:
    bbox = line.get("bbox")
    if bbox and len(bbox) == 4:
        return bbox
    span_boxes = [span.get("bbox") for span in spans if span.get("bbox") and len(span["bbox"]) == 4]
    if not span_boxes:
        return None
    return [
        min(float(item[0]) for item in span_boxes),
        min(float(item[1]) for item in span_boxes),
        max(float(item[2]) for item in span_boxes),
        max(float(item[3]) for item in span_boxes),
    ]


def _extract_pdf_text_boxes_from_page_dict(
    page_dict: dict[str, Any],
    page_width: float,
    page_height: float,
) -> list[TextBox]:
    boxes: list[TextBox] = []
    for block_index, block in enumerate(page_dict.get("blocks", [])):
        if block.get("type") != 0:
            continue
        block_bbox = block.get("bbox")
        normalized_block_bbox = (
            _normalized_bbox(block_bbox, page_width, page_height)
            if block_bbox and len(block_bbox) == 4
            else None
        )
        for line_index, line in enumerate(block.get("lines", [])):
            spans = list(line.get("spans", []))
            text_parts = [" ".join(str(span.get("text", "")).split()) for span in spans]
            text = " ".join(part for part in text_parts if part).strip()
            bbox = _line_bbox(line, spans)
            if not text or bbox is None:
                continue
            line_bbox = _normalized_bbox(bbox, page_width, page_height)
            if line_bbox[2] <= line_bbox[0] or line_bbox[3] <= line_bbox[1]:
                continue
            dominant = _dominant_text_span(spans)
            direction = line.get("dir", (1.0, 0.0))
            boxes.append(
                TextBox(
                    text=text,
                    bbox=line_bbox,
                    confidence=1.0,
                    source="pdf_text",
                    block_id=int(block.get("number", block_index)),
                    line_id=line_index,
                    block_bbox=normalized_block_bbox,
                    font_size=float(dominant.get("size", 0.0)) if dominant else None,
                    font_family=str(dominant.get("font", "")) if dominant else None,
                    font_flags=int(dominant.get("flags", 0)) if dominant else None,
                    direction=tuple(float(value) for value in direction),
                    starts_bullet=_starts_list_marker(text),
                )
            )
    return sorted(boxes, key=lambda box: (box.y_min, box.x_min))


def _normalized_margin_text(text: str) -> str:
    return " ".join(text.casefold().split())


@lru_cache(maxsize=16)
def _scan_pdf_margin_profile(
    resolved_pdf_path: str,
    modification_time_ns: int,
) -> tuple[frozenset[str], frozenset[str]]:
    del modification_time_ns
    document = fitz.open(resolved_pdf_path)
    top_counts: Counter[str] = Counter()
    bottom_counts: Counter[str] = Counter()
    try:
        for page in document:
            page_height = float(page.rect.height)
            page_top: set[str] = set()
            page_bottom: set[str] = set()
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = list(line.get("spans", []))
                    text = " ".join(
                        " ".join(str(span.get("text", "")).split())
                        for span in spans
                        if str(span.get("text", "")).strip()
                    ).strip()
                    bbox = _line_bbox(line, spans)
                    normalized = _normalized_margin_text(text)
                    if not normalized or bbox is None:
                        continue
                    y_min, y_max = float(bbox[1]) / page_height, float(bbox[3]) / page_height
                    if y_max <= 0.12:
                        page_top.add(normalized)
                    if y_min >= 0.88:
                        page_bottom.add(normalized)
            top_counts.update(page_top)
            bottom_counts.update(page_bottom)
        threshold = max(2, math.ceil(document.page_count * 0.30))
        return (
            frozenset(text for text, count in top_counts.items() if count >= threshold),
            frozenset(text for text, count in bottom_counts.items() if count >= threshold),
        )
    finally:
        document.close()


class SlideParser:
    def __init__(self, data_dir: str = "data") -> None:
        self.data_dir = Path(data_dir)
        self.uploaded_dir = self.data_dir / "uploaded_decks"
        self.images_dir = self.data_dir / "slide_images"
        self.metadata_file = self.data_dir / "deck_metadata.json"
        self.uploaded_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.metadata: dict[str, dict[str, Any]] = self._load_metadata()

    def _load_metadata(self) -> dict[str, dict[str, Any]]:
        if not self.metadata_file.exists():
            return {}
        try:
            with self.metadata_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except JSONDecodeError as exc:
            raise ValueError(f"Invalid deck metadata JSON: {self.metadata_file}") from exc
        if not isinstance(data, dict):
            raise ValueError("Deck metadata must be a JSON object")
        return data

    def _save_metadata(self) -> None:
        tmp_path = self.metadata_file.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(self.metadata, file, ensure_ascii=False, indent=2)
        tmp_path.replace(self.metadata_file)

    def load_deck(self, pdf_path: str) -> str:
        source_path = Path(pdf_path).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {source_path}")
        if not source_path.is_file():
            raise ValueError(f"PDF path is not a file: {source_path}")
        if source_path.suffix.lower() != ".pdf":
            raise ValueError(f"Expected a .pdf file, got: {source_path.suffix}")

        try:
            document = fitz.open(str(source_path))
            page_count = document.page_count
            document.close()
        except Exception as exc:
            raise ValueError(f"Unable to open PDF: {source_path}") from exc

        if page_count <= 0:
            raise ValueError("PDF has no pages")

        deck_id = uuid.uuid4().hex[:12]
        stored_pdf_path = self.uploaded_dir / f"{deck_id}.pdf"
        shutil.copy2(source_path, stored_pdf_path)

        self.metadata[deck_id] = {
            "deck_id": deck_id,
            "original_name": source_path.name,
            "pdf_path": str(stored_pdf_path),
            "page_count": page_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_metadata()
        return deck_id

    def render_slide(self, deck_id: str, slide_id: int, dpi: int = 250) -> str:
        deck_info = self.metadata.get(deck_id)
        if deck_info is None:
            raise ValueError(f"Unknown deck_id: {deck_id}")
        if not isinstance(slide_id, int):
            raise TypeError("slide_id must be an integer")
        if dpi <= 0:
            raise ValueError("dpi must be positive")

        page_count = int(deck_info["page_count"])
        if slide_id < 1 or slide_id > page_count:
            raise ValueError(f"slide_id out of range: {slide_id}; page_count={page_count}")

        pdf_path = Path(str(deck_info["pdf_path"]))
        if not pdf_path.exists():
            raise FileNotFoundError(f"Stored PDF is missing: {pdf_path}")

        image_path = self.images_dir / f"{deck_id}_slide_{slide_id:03d}_{dpi}dpi.png"
        document = fitz.open(str(pdf_path))
        try:
            page = document.load_page(slide_id - 1)
            zoom = dpi / 72.0
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pixmap.save(str(image_path))
        finally:
            document.close()
        return str(image_path)

    def extract_pdf_text_boxes(self, deck_id: str, slide_id: int) -> list[TextBox]:
        deck_info = self.metadata.get(deck_id)
        if deck_info is None:
            raise ValueError(f"Unknown deck_id: {deck_id}")

        pdf_path = Path(str(deck_info["pdf_path"]))
        document = fitz.open(str(pdf_path))
        try:
            page = document.load_page(slide_id - 1)
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            page_dict = page.get_text("dict")
            boxes = _extract_pdf_text_boxes_from_page_dict(page_dict, page_width, page_height)
        finally:
            document.close()
        return boxes

    def extract_pdf_margin_profile(self, deck_id: str) -> tuple[frozenset[str], frozenset[str]]:
        deck_info = self.metadata.get(deck_id)
        if deck_info is None:
            raise ValueError(f"Unknown deck_id: {deck_id}")
        pdf_path = Path(str(deck_info["pdf_path"])).expanduser().resolve()
        if not pdf_path.exists():
            raise FileNotFoundError(f"Stored PDF is missing: {pdf_path}")
        return _scan_pdf_margin_profile(str(pdf_path), pdf_path.stat().st_mtime_ns)

    def extract_pdf_image_boxes(self, deck_id: str, slide_id: int) -> list[list[float]]:
        deck_info = self.metadata.get(deck_id)
        if deck_info is None:
            raise ValueError(f"Unknown deck_id: {deck_id}")
        document = fitz.open(str(deck_info["pdf_path"]))
        boxes: list[list[float]] = []
        try:
            page = document.load_page(slide_id - 1)
            width, height = float(page.rect.width), float(page.rect.height)
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 1 or not block.get("bbox"):
                    continue
                x1, y1, x2, y2 = (float(value) for value in block["bbox"])
                bbox = [clamp(x1 / width), clamp(y1 / height), clamp(x2 / width), clamp(y2 / height)]
                area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                footer_asset = bbox[1] >= 0.82 and bbox[3] - bbox[1] <= 0.08
                if bbox[2] > bbox[0] and bbox[3] > bbox[1] and 0.002 <= area <= 0.75 and not footer_asset:
                    boxes.append(bbox)
        finally:
            document.close()
        return boxes

    def get_page_count(self, deck_id: str) -> int:
        deck_info = self.metadata.get(deck_id)
        if deck_info is None:
            raise ValueError(f"Unknown deck_id: {deck_id}")
        return int(deck_info["page_count"])

    def get_deck_info(self, deck_id: str) -> dict[str, Any] | None:
        return self.metadata.get(deck_id)


def load_deck(pdf_path: str) -> str:
    return SlideParser().load_deck(pdf_path)


def render_slide(deck_id: str, slide_id: int) -> str:
    return SlideParser().render_slide(deck_id, slide_id)
