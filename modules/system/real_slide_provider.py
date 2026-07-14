"""Production PDF-backed implementation of the system SlideProvider boundary."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from modules.common.schemas import AOI
from modules.slide.aoi_manager import AOIManager
from modules.slide.slide_parser import SlideParser
from modules.system.adapters import SlideFrame


class RealSlideProvider:
    """Load one PDF deck and expose normalized, canonical slide frames."""

    _AUTO_SOURCES = {"pdf_text_semantic", "ocr"}
    _TYPE_PRIORITY = {
        "title": 0,
        "text": 1,
        "mixed": 2,
        "figure": 3,
        "diagram": 4,
        "table": 5,
        "formula": 6,
        "code": 7,
        "caption": 8,
        "axis_label": 9,
    }

    def __init__(self, *, data_dir: str | Path = "data/live_decks") -> None:
        self.data_dir = Path(data_dir)
        self._parser = SlideParser(str(self.data_dir))
        self._aoi_manager = AOIManager(str(self.data_dir))
        self._deck_id: str | None = None
        self._frames: dict[tuple[int, bool], SlideFrame] = {}

    @property
    def deck_id(self) -> str:
        if self._deck_id is None:
            raise RuntimeError("load_deck() must complete before the explicit deck_id is available")
        return self._deck_id

    @property
    def page_count(self) -> int:
        return self._parser.get_page_count(self.deck_id)

    def load_deck(
        self,
        pdf_path: str | Path | bytes,
        *,
        filename: str = "uploaded_deck.pdf",
    ) -> str:
        """Load a path or uploaded PDF bytes through the Member 1 parser."""

        temporary_path: Path | None = None
        if isinstance(pdf_path, bytes):
            upload_name = Path(filename).name
            if Path(upload_name).suffix.lower() != ".pdf":
                raise ValueError("uploaded filename must end in .pdf")
            with NamedTemporaryFile(
                mode="wb",
                suffix=".pdf",
                prefix=f"{Path(upload_name).stem}-",
                dir=self.data_dir,
                delete=False,
            ) as upload:
                upload.write(pdf_path)
                temporary_path = Path(upload.name)
            source_path = temporary_path
        else:
            source_path = Path(pdf_path)

        try:
            self._deck_id = self._parser.load_deck(str(source_path))
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        self._frames.clear()
        return self._deck_id

    def get_slide_frame(self, slide_id: int, *, use_llm_aoi: bool = False) -> SlideFrame:
        """Return the rendered slide, neighbor text, and deterministic canonical AOIs."""

        if not isinstance(slide_id, int):
            raise TypeError("slide_id must be an integer")
        if slide_id < 1 or slide_id > self.page_count:
            raise ValueError(f"slide_id out of range: {slide_id}; page_count={self.page_count}")
        cache_key = (slide_id, use_llm_aoi)
        if cache_key not in self._frames:
            payload = self._aoi_manager.process_slide(self.deck_id, slide_id)
            neighbors = []
            if slide_id > 1:
                neighbors.append(self._slide_text(slide_id - 1))
            if slide_id < self.page_count:
                neighbors.append(self._slide_text(slide_id + 1))
            self._frames[cache_key] = SlideFrame(
                deck_id=self.deck_id,
                slide_id=slide_id,
                aois=self._canonical_aois(payload, use_llm_aoi=use_llm_aoi),
                slide_text=str(payload.get("ocr_text", "")),
                neighbor_slide_text="\n".join(text for text in neighbors if text),
                slide_image_path=str(payload["slide_image_path"]),
            )
        return self._frames[cache_key]

    def _slide_text(self, slide_id: int) -> str:
        return str(self._aoi_manager.process_slide(self.deck_id, slide_id).get("ocr_text", ""))

    def _canonical_aois(self, payload: dict[str, Any], *, use_llm_aoi: bool = False) -> list[AOI]:
        deterministic_aois = list(payload.get("aois", []))
        raw_aois = list(payload.get("llm_aois", [])) if use_llm_aoi else deterministic_aois
        if use_llm_aoi:
            chosen = [
                raw
                for raw in raw_aois
                if self._is_eligible(raw) and str(raw.get("source", "")) == "llm_guided"
            ]
            if not chosen:
                raw_aois = deterministic_aois
            else:
                canonical = [self._to_canonical(raw) for raw in chosen]
                canonical.sort(key=self._aoi_priority)
                whole = next((raw for raw in raw_aois if isinstance(raw, dict) and raw.get("aoi_id") == "whole_slide" and self._valid_bbox(raw.get("bbox"))), None)
                if whole is None:
                    whole = {"aoi_id": "whole_slide", "bbox": [0, 0, 1, 1], "type": "whole_slide", "text": str(payload.get("ocr_text", ""))}
                canonical.append(self._to_canonical(whole))
                return canonical
        automatic = [
            raw
            for raw in raw_aois
            if self._is_eligible(raw) and str(raw.get("source", "")) in self._AUTO_SOURCES
        ]
        chosen = automatic or [
            raw
            for raw in raw_aois
            if self._is_eligible(raw) and str(raw.get("source", "")) == "rule"
        ]
        canonical = [self._to_canonical(raw) for raw in chosen]
        canonical.sort(key=self._aoi_priority)

        whole_slide = next(
            (
                raw
                for raw in raw_aois
                if isinstance(raw, dict)
                and raw.get("aoi_id") == "whole_slide"
                and self._valid_bbox(raw.get("bbox"))
            ),
            None,
        )
        if whole_slide is None:
            whole_slide = {
                "aoi_id": "whole_slide",
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "type": "whole_slide",
                "text": str(payload.get("ocr_text", "")),
            }
        canonical.append(self._to_canonical(whole_slide))
        return canonical

    @staticmethod
    def _is_eligible(raw: object) -> bool:
        return (
            isinstance(raw, dict)
            and raw.get("aoi_id") != "whole_slide"
            and raw.get("type") != "footer"
            and raw.get("include_in_learning", True) is not False
            and RealSlideProvider._valid_bbox(raw.get("bbox"))
        )

    @staticmethod
    def _valid_bbox(value: object) -> bool:
        if not isinstance(value, list) or len(value) != 4:
            return False
        try:
            x1, y1, x2, y2 = (float(item) for item in value)
        except (TypeError, ValueError):
            return False
        return 0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0

    @staticmethod
    def _to_canonical(raw: dict[str, Any]) -> AOI:
        return AOI(
            aoi_id=str(raw["aoi_id"]),
            bbox=[float(value) for value in raw["bbox"]],
            type=str(raw["type"]),
            text=str(raw.get("text", "")),
            name=str(raw["name"]) if raw.get("name") is not None else None,
        )

    def _aoi_priority(self, aoi: AOI) -> tuple[int, float, float, float, str]:
        x1, y1, x2, y2 = aoi.bbox
        area = (x2 - x1) * (y2 - y1)
        return (
            self._TYPE_PRIORITY.get(aoi.type, 99),
            area,
            y1,
            x1,
            aoi.aoi_id,
        )
