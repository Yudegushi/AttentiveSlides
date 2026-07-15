"""
AOI generation, persistence, retrieval, and manual correction.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from json import JSONDecodeError
from pathlib import Path
from threading import RLock
from typing import Any

from .aoi_grouping import (
    CONTENT_ROLES,
    EXCLUDED_ROLES,
    GroupingResult,
    TextGroup,
    build_page_layout_profile,
    group_pdf_text,
    text_groups_are_continuous,
)
from .ocr import OCREngine, TextBox, clamp
from .slide_parser import SlideParser
from modules.common.schemas import VisualContextItem

from .llm_aoi import LLMAOIGenerator, LLMAOIResult, sanitized_llm_error


AUTO_AOI_SCHEMA_VERSION = "pdf-semantic-v2"
TEXT_AOI_TYPES = frozenset({"title", "text", "caption", "footer", "axis_label"})
VISUAL_AOI_TYPES = frozenset({"code", "diagram", "figure", "table", "formula", "mixed"})


@dataclass
class AOI:
    aoi_id: str
    bbox: list[float]
    type: str
    text: str = ""
    source: str = "rule"
    group_confidence: float | None = None
    children: list[dict[str, Any]] | None = None
    include_in_learning: bool = True
    role: str | None = None
    anchor_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


@dataclass
class SlideAOIData:
    slide_id: int
    slide_image_path: str
    ocr_text: str
    aois: list[AOI]
    text_source: str
    auto_aoi_method: str
    excluded_text_regions: list[dict[str, Any]] | None = None
    auto_aoi_version: str = AUTO_AOI_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "slide_id": self.slide_id,
            "slide_image_path": self.slide_image_path,
            "ocr_text": self.ocr_text,
            "slide_text": self.ocr_text,
            "text_source": self.text_source,
            "auto_aoi_method": self.auto_aoi_method,
            "auto_aoi_version": self.auto_aoi_version,
            "excluded_text_regions": self.excluded_text_regions or [],
            "aois": [aoi.to_dict() for aoi in self.aois],
        }


class AOIManager:
    def __init__(
        self,
        data_dir: str = "data",
        *,
        llm_aoi_generator: LLMAOIGenerator | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.manifest_file = self.data_dir / "aoi_manifest.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.manifest: dict[str, dict[str, Any]] = self._load_manifest()
        self.llm_aoi_generator = llm_aoi_generator or LLMAOIGenerator()

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if not self.manifest_file.exists():
            return {}
        try:
            with self.manifest_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except JSONDecodeError as exc:
            raise ValueError(f"Invalid AOI manifest JSON: {self.manifest_file}") from exc
        if not isinstance(data, dict):
            raise ValueError("AOI manifest must be a JSON object")
        return data

    def _save_manifest(self) -> None:
        with self._lock:
            tmp_path = self.manifest_file.with_suffix(".json.tmp")
            with tmp_path.open("w", encoding="utf-8") as file:
                json.dump(self.manifest, file, ensure_ascii=False, indent=2)
            tmp_path.replace(self.manifest_file)

    @staticmethod
    def _slide_key(deck_id: str, slide_id: int) -> str:
        return f"{deck_id}:{slide_id}"

    def process_slide(
        self,
        deck_id: str,
        slide_id: int,
        dpi: int = 250,
        *,
        allow_ocr: bool = True,
    ) -> dict[str, Any]:
        parser = SlideParser(str(self.data_dir))
        image_path = parser.render_slide(deck_id, slide_id, dpi=dpi)
        pdf_text_boxes = parser.extract_pdf_text_boxes(deck_id, slide_id)
        pdf_text = "\n".join(box.text for box in pdf_text_boxes).strip()
        repeated_top_text: frozenset[str] = frozenset()
        repeated_bottom_text: frozenset[str] = frozenset()
        if pdf_text_boxes:
            try:
                repeated_top_text, repeated_bottom_text = parser.extract_pdf_margin_profile(deck_id)
            except Exception:
                pass
        image_text_boxes: list[TextBox] = []
        if allow_ocr:
            try:
                image_text_boxes = self.extract_image_text_boxes(
                    image_path,
                    parser.extract_pdf_image_boxes(deck_id, slide_id),
                )
            except Exception:
                image_text_boxes = []

        if len(pdf_text) >= 30:
            text_boxes = pdf_text_boxes
            text_source = "pdf_text"
            grouping = group_pdf_text(
                text_boxes,
                repeated_top_text,
                repeated_bottom_text,
            )
            auto_aois = self._aois_from_text_groups(grouping.content_groups)
            auto_aois.extend(self.build_image_region_aois(image_text_boxes))
            auto_aoi_method = "pdf_text_semantic"

        elif allow_ocr:
            text_boxes = OCREngine().extract_boxes(
                image_path
            )
            text_source = "ocr"
            auto_aois = self.build_text_block_aois(
                text_boxes
            )
            grouping = GroupingResult([], [])
            auto_aois.extend(self.build_image_region_aois(image_text_boxes))
            auto_aoi_method = "ocr_text_block"

        else:
            text_boxes = pdf_text_boxes

            text_source = (
                "pdf_text_insufficient"
                if pdf_text_boxes
                else "no_embedded_text"
            )

            grouping = group_pdf_text(
                text_boxes,
                repeated_top_text,
                repeated_bottom_text,
            ) if text_boxes else GroupingResult([], [])
            auto_aois = self._aois_from_text_groups(grouping.content_groups)

            auto_aoi_method = (
                "pdf_text_only_no_ocr"
            )

        slide_text = "\n".join(box.text for box in text_boxes).strip()
        rule_aois = self.generate_rule_aois(slide_text)
        self.populate_rule_aoi_text(rule_aois, auto_aois)
        slide_data = SlideAOIData(
            slide_id=slide_id,
            slide_image_path=image_path,
            ocr_text=slide_text,
            aois=rule_aois + auto_aois,
            text_source=text_source,
            auto_aoi_method=auto_aoi_method,
            excluded_text_regions=[
                self._excluded_text_group(group) for group in grouping.excluded_groups
            ],
            auto_aoi_version=AUTO_AOI_SCHEMA_VERSION,
        )
        return self.save_slide_data(deck_id, slide_data)

    def extract_image_text_boxes(
        self,
        image_path: str,
        image_regions: list[list[float]],
    ) -> list[TextBox]:
        engine = OCREngine()
        boxes: list[TextBox] = []
        for region in image_regions:
            try:
                boxes.extend(engine.extract_region_boxes(image_path, region))
            except Exception:
                continue
        return self.merge_text_boxes(boxes)

    def build_image_region_aois(self, text_boxes: list[TextBox]) -> list[AOI]:
        return [
            AOI(
                f"ocr_image_block_{index}",
                list(box.bbox),
                "text",
                box.text,
                source="ocr_image",
                group_confidence=round(float(box.confidence), 3),
                children=[self._text_box_child(box)],
            )
            for index, box in enumerate(text_boxes, 1)
            if self._bbox_area(box.bbox) >= 0.002
        ]

    @classmethod
    def merge_text_boxes(cls, boxes: list[TextBox]) -> list[TextBox]:
        merged: list[TextBox] = []
        seen: set[tuple[str, tuple[float, ...]]] = set()
        for box in sorted(boxes, key=lambda item: (item.y_min, item.x_min)):
            key = (cls._normalize_text(box.text), tuple(round(value, 4) for value in box.bbox))
            if key not in seen:
                seen.add(key)
                merged.append(box)
        return merged

    def generate_rule_aois(self, slide_text: str = "") -> list[AOI]:
        return [
            AOI("title", [0.05, 0.05, 0.95, 0.18], "title", source="rule"),
            AOI("top_region", [0.05, 0.18, 0.95, 0.35], "text", source="rule"),
            AOI("left_block", [0.05, 0.35, 0.48, 0.85], "text", source="rule"),
            AOI("right_block", [0.52, 0.35, 0.95, 0.85], "mixed", source="rule"),
            AOI("right_visual_region", [0.50, 0.43, 0.96, 0.80], "figure", source="rule"),
            AOI("bottom_region", [0.05, 0.85, 0.95, 0.98], "caption", source="rule"),
            AOI("whole_slide", [0.0, 0.0, 1.0, 1.0], "whole_slide", text=slide_text, source="rule"),
        ]

    def populate_rule_aoi_text(self, rule_aois: list[AOI], auto_aois: list[AOI]) -> None:
        for rule_aoi in rule_aois:
            if rule_aoi.aoi_id == "whole_slide":
                continue
            if rule_aoi.type == "figure":
                continue
            texts = []
            for auto_aoi in auto_aois:
                if auto_aoi.type == "footer":
                    continue
                if self._bbox_center_inside(auto_aoi.bbox, rule_aoi.bbox):
                    texts.append(auto_aoi.text)
            if texts:
                rule_aoi.text = "\n".join(texts)
                if rule_aoi.aoi_id == "right_block" and any(text.strip() for text in texts):
                    rule_aoi.type = "mixed"

    def build_text_block_aois(self, text_boxes: list[TextBox]) -> list[AOI]:
        blocks: list[list[TextBox]] = []
        for box in sorted(text_boxes, key=lambda item: (item.y_min, item.x_min)):
            target_block = self._find_best_block(box, blocks)
            if target_block is None:
                blocks.append([box])
            else:
                target_block.append(box)

        aois: list[AOI] = []
        for block in blocks:
            block = sorted(block, key=lambda item: (item.y_min, item.x_min))
            bbox = self._merged_bbox(block, padding=0.01)
            if self._bbox_area(bbox) < 0.002:
                continue
            aois.append(
                AOI(
                    aoi_id=f"ocr_text_block_{len(aois) + 1}",
                    bbox=bbox,
                    type="title" if bbox[1] < 0.20 and len(block) <= 3 else "text",
                    text="\n".join(item.text for item in block),
                    source="ocr",
                    children=[self._text_box_child(item) for item in block],
                )
            )
        return aois

    def merge_pdf_wrapped_aois(self, aois: list[AOI]) -> list[AOI]:
        merged: list[AOI] = []
        for candidate in sorted(aois, key=lambda aoi: (aoi.bbox[1], aoi.bbox[0])):
            current = next(
                (previous for previous in reversed(merged) if self._pdf_lines_are_continuous(previous, candidate)),
                None,
            )
            if current is None:
                merged.append(candidate)
                continue
            current.text = f"{current.text.rstrip()} {candidate.text.lstrip()}"
            current.bbox = [
                min(current.bbox[0], candidate.bbox[0]),
                min(current.bbox[1], candidate.bbox[1]),
                max(current.bbox[2], candidate.bbox[2]),
                max(current.bbox[3], candidate.bbox[3]),
            ]
            current.group_confidence = min(current.group_confidence or 0.62, candidate.group_confidence or 0.62)
            current.children = list(current.children or []) + list(candidate.children or [])
        for index, aoi in enumerate(merged, 1):
            aoi.aoi_id = f"pdf_semantic_block_{index}"
        return merged

    @staticmethod
    def _pdf_lines_are_continuous(first: AOI, second: AOI) -> bool:
        if first.type != "text" or second.type != "text":
            return False
        if not first.text.strip() or not second.text.strip():
            return False
        if second.text.strip().startswith(("•", "o ", "*")) or first.text.strip().endswith((".", "!", "?", "]")):
            return False
        return abs(first.bbox[0] - second.bbox[0]) <= 0.025 and max(0.0, second.bbox[1] - first.bbox[3]) <= 0.025

    def build_llm_guided_slide(
        self,
        image_path: str,
        slide_text: str,
        rule_aois: list[AOI],
        text_aois: list[AOI],
    ) -> tuple[list[AOI], LLMAOIResult]:
        generation = self.llm_aoi_generator.generate(
            image_path,
            slide_text,
            [self._llm_prompt_aoi(aoi, grounding=False) for aoi in rule_aois],
            [self._llm_prompt_aoi(aoi) for aoi in text_aois],
        )
        aois: list[AOI] = []
        for item in generation.aois:
            bbox = [float(value) for value in item.get("bbox", [])]
            aoi_type = str(item.get("type", "mixed"))
            anchor_ids = list(dict.fromkeys(
                str(value).strip()
                for value in (item.get("anchor_ids") or [])
                if str(value).strip()
            ))
            anchored_text = aoi_type in {"title", "text", "caption", "footer", "axis_label"} and bool(anchor_ids)
            if not anchored_text:
                self._validate_bbox(bbox)
            aois.append(AOI(
                str(item.get("aoi_id", "")),
                bbox,
                aoi_type,
                str(item.get("text", "")),
                source="llm_guided",
                group_confidence=float(item.get("group_confidence", 0.7)),
                include_in_learning=bool(item.get("include_in_learning", True)),
                anchor_ids=anchor_ids or None,
            ))
        return aois, generation

    @staticmethod
    def _llm_prompt_aoi(aoi: AOI, *, grounding: bool = True) -> dict[str, Any]:
        if grounding:
            return {
                "anchor_id": aoi.aoi_id,
                "role": aoi.role or aoi.type,
                "text": aoi.text,
                "bbox": [float(value) for value in aoi.bbox],
                "line_count": len(aoi.children or []),
            }
        return {
            "aoi_id": aoi.aoi_id,
            "bbox": [float(value) for value in aoi.bbox],
            "type": aoi.type,
            "text": aoi.text,
            "source": aoi.source,
        }

    def reconcile_llm_aois(
        self,
        llm_aois: list[AOI],
        grounding_aois: list[AOI],
        minimum_text_coverage: float = 0.45,
    ) -> list[AOI]:
        grounding_by_id = {aoi.aoi_id: aoi for aoi in grounding_aois}
        candidates: list[AOI] = []
        for aoi in llm_aois:
            if aoi.type in TEXT_AOI_TYPES:
                resolved = self._resolve_text_aoi_anchors(aoi, grounding_by_id)
                if resolved is not None and self._bbox_area(resolved.bbox) < 0.90:
                    candidates.append(resolved)
            elif aoi.type in VISUAL_AOI_TYPES:
                try:
                    self._validate_bbox(aoi.bbox)
                except ValueError:
                    continue
                width = aoi.bbox[2] - aoi.bbox[0]
                height = aoi.bbox[3] - aoi.bbox[1]
                if (
                    width >= 0.04
                    and height >= 0.025
                    and self._bbox_area(aoi.bbox) >= 0.002
                    and self._bbox_area(aoi.bbox) < 0.90
                ):
                    candidates.append(aoi)

        candidates = self._collapse_same_anchor_outputs(candidates, grounding_aois)
        candidates = self._merge_llm_text_fragments(candidates, grounding_aois)
        candidates.sort(key=lambda aoi: aoi.group_confidence or 0.0, reverse=True)
        resolved: list[AOI] = []
        visual_count = 0
        for candidate in candidates:
            if any(
                self._same_aoi_category(candidate, other)
                and self._bbox_iou(candidate.bbox, other.bbox) >= 0.85
                for other in resolved
            ):
                continue
            if candidate.type in VISUAL_AOI_TYPES:
                if visual_count >= 8:
                    continue
                visual_count += 1
            resolved.append(candidate)
        resolved.sort(key=lambda aoi: (aoi.bbox[1], aoi.bbox[0]))
        grounding_tokens = self._learning_tokens([
            aoi for aoi in grounding_aois if aoi.role not in EXCLUDED_ROLES
        ])
        if len(grounding_tokens) >= 8:
            coverage = len(grounding_tokens & self._learning_tokens(resolved)) / len(grounding_tokens)
            if coverage < minimum_text_coverage:
                raise ValueError(f"LLM AOI text coverage too low: {coverage:.1%}; required {minimum_text_coverage:.0%}")
        if not resolved:
            raise ValueError("LLM AOI reconciliation produced no usable AOIs")
        for index, aoi in enumerate(resolved, 1):
            aoi.aoi_id = f"llm_aoi_{index}"
        return resolved

    def _resolve_text_aoi_anchors(
        self,
        aoi: AOI,
        grounding_by_id: dict[str, AOI],
    ) -> AOI | None:
        anchor_ids = list(dict.fromkeys(aoi.anchor_ids or []))
        requested = set(anchor_ids)
        anchors = [anchor for anchor_id, anchor in grounding_by_id.items() if anchor_id in requested]
        if len(anchors) != len(anchor_ids) or not anchors:
            return None
        if any(not self._is_content_grounding_aoi(anchor) for anchor in anchors):
            return None
        aoi.anchor_ids = [anchor.aoi_id for anchor in anchors]
        aoi.text = " ".join(anchor.text.strip() for anchor in anchors if anchor.text.strip())
        aoi.bbox = self._merged_aoi_bbox(anchors)
        aoi.type = "text"
        aoi.include_in_learning = True
        roles = {anchor.role for anchor in anchors if anchor.role}
        aoi.role = "list_item" if anchors[0].role == "list_item" else (
            next(iter(roles)) if len(roles) == 1 else "paragraph"
        )
        return aoi

    @staticmethod
    def _merged_aoi_bbox(aois: list[AOI]) -> list[float]:
        return [
            min(aoi.bbox[0] for aoi in aois),
            min(aoi.bbox[1] for aoi in aois),
            max(aoi.bbox[2] for aoi in aois),
            max(aoi.bbox[3] for aoi in aois),
        ]

    def _collapse_same_anchor_outputs(
        self,
        aois: list[AOI],
        grounding_aois: list[AOI],
    ) -> list[AOI]:
        grounding_by_id = {aoi.aoi_id: aoi for aoi in grounding_aois}
        collapsed: list[AOI] = []
        by_anchor_set: dict[tuple[str, ...], AOI] = {}
        for aoi in aois:
            if aoi.type not in TEXT_AOI_TYPES:
                collapsed.append(aoi)
                continue
            key = tuple(aoi.anchor_ids or [])
            previous = by_anchor_set.get(key)
            if previous is None:
                by_anchor_set[key] = aoi
                collapsed.append(aoi)
                continue
            previous.group_confidence = min(
                previous.group_confidence or 0.7,
                aoi.group_confidence or 0.7,
            )
            anchors = [grounding_by_id[value] for value in key]
            previous.text = " ".join(anchor.text.strip() for anchor in anchors if anchor.text.strip())
            previous.bbox = self._merged_aoi_bbox(anchors)
        return collapsed

    def _merge_llm_text_fragments(
        self,
        aois: list[AOI],
        grounding_aois: list[AOI],
    ) -> list[AOI]:
        grounding_order = {
            aoi.aoi_id: index for index, aoi in enumerate(grounding_aois)
        }
        text_candidates = sorted(
            (aoi for aoi in aois if aoi.type in TEXT_AOI_TYPES),
            key=lambda aoi: min(grounding_order[value] for value in aoi.anchor_ids or []),
        )
        visual_candidates = [aoi for aoi in aois if aoi.type not in TEXT_AOI_TYPES]
        return self._merge_ordered_text_candidates(
            text_candidates,
            grounding_aois,
            grounding_order,
        ) + visual_candidates

    def _merge_ordered_text_candidates(
        self,
        aois: list[AOI],
        grounding_aois: list[AOI],
        grounding_order: dict[str, int],
    ) -> list[AOI]:
        grounding_by_id = {aoi.aoi_id: aoi for aoi in grounding_aois}
        merged: list[AOI] = []
        for candidate in aois:
            if not merged or not self._llm_text_candidates_are_continuous(
                merged[-1],
                candidate,
                grounding_by_id,
                grounding_order,
            ):
                merged.append(candidate)
                continue
            previous = merged[-1]
            combined_ids = sorted(
                set(previous.anchor_ids or []) | set(candidate.anchor_ids or []),
                key=grounding_order.__getitem__,
            )
            anchors = [grounding_by_id[value] for value in combined_ids]
            previous.anchor_ids = combined_ids
            previous.text = " ".join(anchor.text.strip() for anchor in anchors if anchor.text.strip())
            previous.bbox = self._merged_aoi_bbox(anchors)
            previous.group_confidence = min(
                previous.group_confidence or 0.7,
                candidate.group_confidence or 0.7,
            )
            roles = {anchor.role for anchor in anchors if anchor.role}
            previous.role = "list_item" if anchors[0].role == "list_item" else (
                next(iter(roles)) if len(roles) == 1 else "paragraph"
            )
        return merged

    def _llm_text_candidates_are_continuous(
        self,
        first: AOI,
        second: AOI,
        grounding_by_id: dict[str, AOI],
        grounding_order: dict[str, int],
    ) -> bool:
        first_ids = first.anchor_ids or []
        second_ids = second.anchor_ids or []
        if not first_ids or not second_ids or set(first_ids) & set(second_ids):
            return False
        first_indices = sorted(grounding_order[value] for value in first_ids)
        second_indices = sorted(grounding_order[value] for value in second_ids)
        if first_indices != list(range(first_indices[0], first_indices[-1] + 1)):
            return False
        if second_indices != list(range(second_indices[0], second_indices[-1] + 1)):
            return False
        if first_indices[-1] + 1 != second_indices[0]:
            return False
        first_group = self._text_group_from_anchors(
            [grounding_by_id[value] for value in first_ids]
        )
        second_group = self._text_group_from_anchors(
            [grounding_by_id[value] for value in second_ids]
        )
        if first_group is None or second_group is None:
            return False
        profile = build_page_layout_profile(
            first_group.lines + second_group.lines,
            frozenset(),
            frozenset(),
        )
        return text_groups_are_continuous(first_group, second_group, profile)

    @staticmethod
    def _text_group_from_anchors(anchors: list[AOI]) -> TextGroup | None:
        lines: list[TextBox] = []
        for anchor in anchors:
            if anchor.role in EXCLUDED_ROLES or not anchor.children:
                return None
            for child in anchor.children:
                bbox = child.get("bbox")
                if not isinstance(bbox, list) or len(bbox) != 4:
                    return None
                direction = child.get("direction")
                lines.append(TextBox(
                    text=str(child.get("text", "")),
                    bbox=[float(value) for value in bbox],
                    confidence=float(child.get("confidence", 1.0)),
                    source=str(child.get("source", anchor.source)),
                    block_id=child.get("block_id"),
                    line_id=child.get("line_id"),
                    block_bbox=child.get("block_bbox"),
                    font_size=child.get("font_size"),
                    font_family=child.get("font_family"),
                    font_flags=child.get("font_flags"),
                    direction=tuple(float(value) for value in direction) if direction is not None else None,
                    starts_bullet=bool(child.get("starts_bullet", False)),
                ))
        role = anchors[0].role or "paragraph"
        return TextGroup(role=role, lines=lines) if lines else None

    @classmethod
    def _learning_tokens(cls, aois: list[AOI]) -> set[str]:
        return {
            token
            for aoi in aois
            if aoi.type != "footer"
            for token in cls._normalize_text(aoi.text).split()
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join("".join(character.casefold() if character.isalnum() else " " for character in text).split())

    @staticmethod
    def _same_aoi_category(first: AOI, second: AOI) -> bool:
        return (first.type in VISUAL_AOI_TYPES) == (second.type in VISUAL_AOI_TYPES)

    @staticmethod
    def _bbox_iou(first: list[float], second: list[float]) -> float:
        width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
        height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
        intersection = width * height
        first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
        second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
        union = first_area + second_area - intersection
        return intersection / union if union else 0.0

    @classmethod
    def _link_visual_context(
        cls,
        visual_context: tuple[VisualContextItem, ...],
        aois: list[AOI],
    ) -> tuple[VisualContextItem, ...]:
        compatible_types = {
            "formula": {"formula"},
            "chart": {"figure", "diagram"},
            "diagram": {"diagram", "figure"},
            "table": {"table"},
            "image": {"figure"},
            "code": {"code"},
            "other": {"mixed", "figure"},
        }
        linked: list[VisualContextItem] = []
        for item in visual_context:
            matches = [
                (cls._bbox_iou(item.bbox, aoi.bbox), aoi)
                for aoi in aois
                if aoi.type in compatible_types.get(item.type, set())
            ]
            best_iou, best_aoi = max(
                matches,
                key=lambda match: match[0],
                default=(0.0, None),
            )
            linked.append(replace(
                item,
                linked_aoi_id=(
                    best_aoi.aoi_id
                    if best_aoi is not None and best_iou >= 0.65
                    else None
                ),
            ))
        return tuple(linked)

    def build_pdf_semantic_aois(
        self,
        text_boxes: list[TextBox],
        repeated_top_text: frozenset[str] = frozenset(),
        repeated_bottom_text: frozenset[str] = frozenset(),
    ) -> list[AOI]:
        grouping = group_pdf_text(
            [box for box in text_boxes if box.source == "pdf_text"],
            repeated_top_text,
            repeated_bottom_text,
        )
        return self._aois_from_text_groups(grouping.content_groups)

    def _aois_from_text_groups(self, groups: list[TextGroup]) -> list[AOI]:
        return [
            AOI(
                aoi_id=f"pdf_paragraph_{index}",
                bbox=list(group.bbox),
                type="text",
                text=group.text,
                source="pdf_text_semantic",
                group_confidence=0.95 if len({line.block_id for line in group.lines}) == 1 else 0.85,
                children=[self._text_box_child(line) for line in group.lines],
                role=group.role,
            )
            for index, group in enumerate(groups, 1)
        ]

    def _excluded_text_group(self, group: TextGroup) -> dict[str, Any]:
        return {
            "role": group.role,
            "text": group.text,
            "bbox": list(group.bbox),
            "children": [self._text_box_child(line) for line in group.lines],
        }

    def save_slide_data(self, deck_id: str, slide_data: SlideAOIData) -> dict[str, Any]:
        for aoi in slide_data.aois:
            self._validate_bbox(aoi.bbox)
        data = slide_data.to_dict()
        with self._lock:
            key = self._slide_key(deck_id, slide_data.slide_id)
            previous = self.manifest.get(key, {})
            digest = self._anchor_digest(data)
            expected = self.llm_aoi_generator.profile(digest)
            if previous.get("llm_aoi_status") == "used" and previous.get("llm_aoi_profile") == expected:
                preserved_defaults = {
                    "llm_aois": [],
                    "llm_aoi_status": "used",
                    "llm_aoi_model": None,
                    "llm_aoi_profile": expected,
                    "llm_aoi_anchor_digest": digest,
                    "llm_aoi_error": None,
                    "llm_visual_context": [],
                    "llm_visual_context_status": "empty",
                }
                for field, default in preserved_defaults.items():
                    value = previous.get(field)
                    data[field] = default if value is None else value
            else:
                data.update({
                    "llm_aois": [],
                    "llm_visual_context": [],
                    "llm_visual_context_status": "empty",
                    "llm_aoi_status": "not_requested",
                    "llm_aoi_model": None,
                    "llm_aoi_profile": None,
                    "llm_aoi_anchor_digest": digest,
                    "llm_aoi_error": None,
                })
            self.manifest[key] = data
            self._save_manifest()
        return data

    def _anchor_digest(self, slide_data: dict[str, Any]) -> str:
        anchors = [
            {
                "aoi_id": str(aoi.get("aoi_id", "")),
                "bbox": [round(float(value), 6) for value in aoi.get("bbox", [])],
                "type": str(aoi.get("type", "")),
                "role": str(aoi.get("role", "")),
                "text": " ".join(str(aoi.get("text", "")).split()),
                "line_count": len(aoi.get("children") or []),
            }
            for aoi in slide_data.get("aois", [])
            if aoi.get("source") in {"pdf_text_semantic", "ocr", "ocr_image"}
            and self._is_content_grounding_aoi(self._aoi_from_dict(aoi))
        ]
        raw = json.dumps(anchors, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def process_llm_aoi(
        self,
        deck_id: str,
        slide_id: int,
        *,
        dpi: int = 250,
        allow_ocr: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        key = self._slide_key(deck_id, slide_id)
        slide_data = self.manifest.get(key)
        expected_suffix = f"_{dpi}dpi.png"
        if (
            slide_data is None
            or slide_data.get("auto_aoi_version") != AUTO_AOI_SCHEMA_VERSION
            or not str(slide_data.get("slide_image_path", "")).endswith(expected_suffix)
        ):
            slide_data = self.process_slide(deck_id, slide_id, dpi=dpi, allow_ocr=allow_ocr)
        anchor_digest = self._anchor_digest(slide_data)
        expected_profile = self.llm_aoi_generator.profile(anchor_digest)
        if not force and slide_data.get("llm_aoi_status") == "used" and slide_data.get("llm_aoi_profile") == expected_profile:
            return slide_data

        rule_aois = [self._aoi_from_dict(item) for item in slide_data.get("aois", []) if item.get("source") == "rule"]
        anchor_aois = []
        for item in slide_data.get("aois", []):
            if item.get("source") not in {"pdf_text_semantic", "ocr", "ocr_image"}:
                continue
            candidate = self._aoi_from_dict(item)
            if self._is_content_grounding_aoi(candidate):
                anchor_aois.append(candidate)
        try:
            generated_aois, generation = self.build_llm_guided_slide(
                str(slide_data.get("slide_image_path", "")),
                str(slide_data.get("ocr_text", "")),
                rule_aois,
                anchor_aois,
            )
            llm_aois = self.reconcile_llm_aois(
                generated_aois,
                anchor_aois,
            )
            visual_context = self._link_visual_context(
                generation.visual_context,
                llm_aois,
            )
            with self._lock:
                current = self.manifest[key]
                if self._anchor_digest(current) != anchor_digest:
                    raise RuntimeError("Deterministic AOIs changed during LLM generation")
                current.update({
                    "llm_aois": [aoi.to_dict() for aoi in llm_aois],
                    "llm_visual_context": [
                        item.to_dict() for item in visual_context
                    ],
                    "llm_visual_context_status": generation.visual_context_status,
                    "llm_aoi_status": "used",
                    "llm_aoi_model": str(self.llm_aoi_generator.config.model),
                    "llm_aoi_profile": expected_profile,
                    "llm_aoi_anchor_digest": anchor_digest,
                    "llm_aoi_error": None,
                })
                self._save_manifest()
                return current

        except Exception as exc:
            with self._lock:
                current = self.manifest[key]
                if self._anchor_digest(current) == anchor_digest:
                    current.update({
                        "llm_aois": [],
                        "llm_visual_context": [],
                        "llm_visual_context_status": "empty",
                        "llm_aoi_status": "fallback_used",
                        "llm_aoi_model": str(self.llm_aoi_generator.config.model),
                        "llm_aoi_profile": None,
                        "llm_aoi_anchor_digest": anchor_digest,
                        "llm_aoi_error": sanitized_llm_error(exc),
                    })
                    self._save_manifest()
                return current

    @staticmethod
    def _is_content_grounding_aoi(aoi: AOI) -> bool:
        if aoi.role in EXCLUDED_ROLES or aoi.type in {"title", "footer", "whole_slide"}:
            return False
        if aoi.source == "pdf_text_semantic":
            return aoi.role in CONTENT_ROLES
        return aoi.source in {"ocr", "ocr_image"}

    def get_llm_aoi_state(self, deck_id: str, slide_id: int) -> dict[str, Any]:
        configured = bool(self.llm_aoi_generator.is_configured())
        slide_data = self.manifest.get(self._slide_key(deck_id, slide_id))
        if slide_data is None:
            return {
                "configured": configured,
                "status": "not_requested",
                "model": None,
                "profile": None,
                "expected_profile": None,
                "eligible": False,
                "aoi_count": 0,
                "visual_count": 0,
                "visual_context_status": "empty",
                "error": None,
            }
        digest = self._anchor_digest(slide_data)
        expected_profile = self.llm_aoi_generator.profile(digest) if configured else None
        stored_profile = slide_data.get("llm_aoi_profile")
        status = str(slide_data.get("llm_aoi_status", "not_requested"))
        raw_llm_aois = slide_data.get("llm_aois")
        llm_aois = list(raw_llm_aois) if isinstance(raw_llm_aois, list) else []
        raw_visual_context = slide_data.get("llm_visual_context")
        visual_context = (
            raw_visual_context
            if isinstance(raw_visual_context, list)
            else []
        )
        raw_visual_status = slide_data.get("llm_visual_context_status", "empty")
        visual_status = (
            raw_visual_status
            if raw_visual_status in {"used", "empty", "invalid"}
            else "empty"
        )
        eligible = configured and status == "used" and bool(llm_aois) and stored_profile == expected_profile
        return {
            "configured": configured,
            "status": status if status in {"not_requested", "used", "fallback_used"} else "not_requested",
            "model": slide_data.get("llm_aoi_model"),
            "profile": stored_profile,
            "expected_profile": expected_profile,
            "eligible": eligible,
            "aoi_count": len(llm_aois),
            "visual_count": len(visual_context),
            "visual_context_status": visual_status,
            "error": slide_data.get("llm_aoi_error"),
        }

    def get_effective_aois(
        self,
        deck_id: str,
        slide_id: int,
        *,
        use_llm_aoi: bool,
    ) -> tuple[list[dict[str, Any]], str]:
        slide_data = self._ensure_slide_data(deck_id, slide_id)
        state = self.get_llm_aoi_state(deck_id, slide_id)
        if use_llm_aoi and state["eligible"]:
            selected = [dict(aoi) for aoi in slide_data.get("llm_aois", [])]
            profile = str(slide_data["llm_aoi_profile"])
        else:
            deterministic = [dict(aoi) for aoi in slide_data.get("aois", [])]
            semantic = [
                aoi
                for aoi in deterministic
                if (
                    (aoi.get("source") == "pdf_text_semantic" and aoi.get("role") in CONTENT_ROLES)
                    or aoi.get("source") in {"ocr", "ocr_image", "manual"}
                )
                and aoi.get("role") not in EXCLUDED_ROLES
                and aoi.get("type") not in {"title", "footer"}
            ]
            if semantic:
                selected = semantic
            else:
                selected = [
                    aoi
                    for aoi in deterministic
                    if aoi.get("source") == "rule"
                    and aoi.get("aoi_id") not in {"title", "bottom_region", "whole_slide"}
                    and aoi.get("type") not in {"title", "footer"}
                ]
            profile = "deterministic"
        if not any(aoi.get("aoi_id") == "whole_slide" for aoi in selected):
            selected.append(self.generate_rule_aois(str(slide_data.get("ocr_text", "")))[-1].to_dict())
        return selected, profile

    @staticmethod
    def _aoi_from_dict(item: dict[str, Any]) -> AOI:
        return AOI(
            aoi_id=str(item.get("aoi_id", "")),
            bbox=[float(value) for value in item.get("bbox", [])],
            type=str(item.get("type", "mixed")),
            text=str(item.get("text", "")),
            source=str(item.get("source", "rule")),
            group_confidence=item.get("group_confidence"),
            children=item.get("children"),
            include_in_learning=bool(item.get("include_in_learning", True)),
            role=item.get("role"),
            anchor_ids=list(item.get("anchor_ids") or []) or None,
        )

    def get_slide_aois(self, deck_id: str, slide_id: int) -> list[dict[str, Any]]:
        slide_data = self._ensure_slide_data(deck_id, slide_id)
        return list(slide_data["aois"])

    def get_slide_text(self, deck_id: str, slide_id: int) -> str:
        return str(self._ensure_slide_data(deck_id, slide_id).get("ocr_text", ""))

    def update_aoi(
        self,
        deck_id: str,
        slide_id: int,
        aoi_id: str,
        bbox: list[float],
        aoi_type: str,
        text: str,
    ) -> dict[str, Any]:
        self._validate_bbox(bbox)
        with self._lock:
            slide_data = self._ensure_slide_data(deck_id, slide_id)
            for aoi in slide_data["aois"]:
                if aoi["aoi_id"] == aoi_id:
                    aoi["bbox"] = [float(value) for value in bbox]
                    aoi["type"] = aoi_type
                    aoi["text"] = text
                    aoi["source"] = "manual"
                    self.manifest[self._slide_key(deck_id, slide_id)] = slide_data
                    self._save_manifest()
                    return aoi
        raise ValueError(f"AOI does not exist: {aoi_id}")

    def add_aoi(
        self,
        deck_id: str,
        slide_id: int,
        aoi_id: str,
        bbox: list[float],
        aoi_type: str,
        text: str = "",
    ) -> dict[str, Any]:
        self._validate_bbox(bbox)
        with self._lock:
            slide_data = self._ensure_slide_data(deck_id, slide_id)
            if any(aoi["aoi_id"] == aoi_id for aoi in slide_data["aois"]):
                raise ValueError(f"AOI already exists: {aoi_id}")
            new_aoi = AOI(aoi_id, [float(value) for value in bbox], aoi_type, text, source="manual").to_dict()
            slide_data["aois"].append(new_aoi)
            self.manifest[self._slide_key(deck_id, slide_id)] = slide_data
            self._save_manifest()
            return new_aoi

    def delete_aoi(self, deck_id: str, slide_id: int, aoi_id: str) -> None:
        with self._lock:
            slide_data = self._ensure_slide_data(deck_id, slide_id)
            original_count = len(slide_data["aois"])
            slide_data["aois"] = [aoi for aoi in slide_data["aois"] if aoi["aoi_id"] != aoi_id]
            if len(slide_data["aois"]) == original_count:
                raise ValueError(f"AOI does not exist: {aoi_id}")
            self.manifest[self._slide_key(deck_id, slide_id)] = slide_data
            self._save_manifest()

    def get_gaze_payload(self, deck_id: str, slide_id: int) -> dict[str, Any]:
        aois = [
            {"aoi_id": aoi["aoi_id"], "bbox": aoi["bbox"], "type": aoi["type"]}
            for aoi in self.get_slide_aois(deck_id, slide_id)
            if aoi.get("type") != "footer"
        ]
        return {"slide_id": slide_id, "aois": aois}

    def get_tutor_payload(self, deck_id: str, slide_id: int) -> dict[str, Any]:
        slide_data = self._ensure_slide_data(deck_id, slide_id)
        aois = [
            {"aoi_id": aoi["aoi_id"], "type": aoi["type"], "text": aoi.get("text", "")}
            for aoi in slide_data["aois"]
            if aoi.get("text") and aoi.get("type") != "footer"
        ]
        return {"slide_id": slide_id, "ocr_text": slide_data.get("ocr_text", ""), "aois": aois}

    def _ensure_slide_data(self, deck_id: str, slide_id: int) -> dict[str, Any]:
        key = self._slide_key(deck_id, slide_id)
        if (
            key not in self.manifest
            or self.manifest[key].get("auto_aoi_version") != AUTO_AOI_SCHEMA_VERSION
        ):
            self.process_slide(deck_id, slide_id)
        return self.manifest[key]

    def _semantic_pair_confidence(self, left: TextBox, right: TextBox) -> float:
        dy = abs(left.y_center - right.y_center)
        gap = right.x_min - left.x_max
        height_ratio = min(left.height, right.height) / max(left.height, right.height, 1e-6)
        if dy > 0.035 or gap < 0.0 or gap > 0.30 or height_ratio < 0.55:
            return 0.0

        row_score = 1.0 - min(dy / 0.035, 1.0)
        gap_score = 1.0 - min(gap / 0.30, 1.0)
        height_score = height_ratio
        left_short = left.word_count <= 3
        right_not_shorter = right.word_count >= left.word_count
        right_phrase_like = right.word_count >= 2 or len(right.text) >= 10
        both_very_short = left.word_count <= 2 and right.word_count <= 2

        if left_short and right_not_shorter and right_phrase_like:
            role_score = 1.0
        elif both_very_short:
            role_score = 0.35
        elif left_short:
            role_score = 0.70
        else:
            role_score = 0.45

        return round(0.35 * row_score + 0.25 * gap_score + 0.20 * height_score + 0.20 * role_score, 3)

    def _make_semantic_aoi(self, aoi_id: str, boxes: list[TextBox], aoi_type: str, confidence: float) -> AOI:
        bbox = self._merged_bbox(boxes, padding=0.006)
        return AOI(
            aoi_id=aoi_id,
            bbox=bbox,
            type=aoi_type,
            text="\n".join(box.text for box in boxes),
            source="pdf_text_semantic",
            group_confidence=round(float(confidence), 3),
            children=[self._text_box_child(box) for box in boxes],
            include_in_learning=aoi_type != "footer",
        )

    @staticmethod
    def _text_box_child(box: TextBox) -> dict[str, Any]:
        child: dict[str, Any] = {
            "text": box.text,
            "bbox": box.bbox,
            "source": box.source,
            "confidence": box.confidence,
        }
        optional = {
            "block_id": box.block_id,
            "line_id": box.line_id,
            "block_bbox": box.block_bbox,
            "font_size": box.font_size,
            "font_family": box.font_family,
            "font_flags": box.font_flags,
            "direction": list(box.direction) if box.direction is not None else None,
        }
        child.update({key: value for key, value in optional.items() if value is not None})
        if box.source == "pdf_text" or box.starts_bullet:
            child["starts_bullet"] = box.starts_bullet
        return child

    @staticmethod
    def _special_pdf_box_type(box: TextBox) -> str | None:
        if box.y_min > 0.82:
            return "footer"
        if box.y_min < 0.20:
            return "title"
        if box.width < 0.055 and box.height > 0.12:
            return "axis_label"
        return None

    def _find_best_block(self, box: TextBox, blocks: list[list[TextBox]]) -> list[TextBox] | None:
        best_block = None
        best_score = float("inf")
        for block in blocks:
            block_bbox = self._merged_bbox(block, padding=0.0)
            vertical_gap = box.y_min - block_bbox[3]
            if vertical_gap < -0.012:
                continue
            same_column = self._horizontal_overlap(box.bbox, block_bbox) >= 0.25
            left_aligned = abs(box.x_min - block_bbox[0]) <= 0.07
            close_y = 0.0 <= vertical_gap <= max(0.04, 1.8 * self._median_height(block))
            if close_y and (same_column or left_aligned):
                score = vertical_gap + abs(box.x_min - block_bbox[0]) * 0.4
                if score < best_score:
                    best_score = score
                    best_block = block
        return best_block

    def _merged_bbox(self, boxes: list[TextBox], padding: float = 0.0) -> list[float]:
        return [
            clamp(min(box.x_min for box in boxes) - padding),
            clamp(min(box.y_min for box in boxes) - padding),
            clamp(max(box.x_max for box in boxes) + padding),
            clamp(max(box.y_max for box in boxes) + padding),
        ]

    @staticmethod
    def _bbox_center_inside(inner: list[float], outer: list[float]) -> bool:
        x_center = (inner[0] + inner[2]) / 2
        y_center = (inner[1] + inner[3]) / 2
        return outer[0] <= x_center <= outer[2] and outer[1] <= y_center <= outer[3]

    @staticmethod
    def _horizontal_overlap(a: list[float], b: list[float]) -> float:
        overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
        min_width = max(1e-6, min(a[2] - a[0], b[2] - b[0]))
        return overlap / min_width

    @staticmethod
    def _median_height(block: list[TextBox]) -> float:
        heights = sorted(box.height for box in block)
        return heights[len(heights) // 2]

    @staticmethod
    def _bbox_area(bbox: list[float]) -> float:
        return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])

    @staticmethod
    def _validate_bbox(bbox: list[float]) -> None:
        if len(bbox) != 4:
            raise ValueError("bbox must have four values: [x_min, y_min, x_max, y_max]")
        x_min, y_min, x_max, y_max = [float(value) for value in bbox]
        if not all(0.0 <= value <= 1.0 for value in [x_min, y_min, x_max, y_max]):
            raise ValueError("bbox values must be between 0.0 and 1.0")
        if x_min >= x_max or y_min >= y_max:
            raise ValueError("bbox must satisfy x_min < x_max and y_min < y_max")


def get_slide_aois(deck_id: str, slide_id: int) -> list[dict[str, Any]]:
    return AOIManager().get_slide_aois(deck_id, slide_id)


def get_slide_text(deck_id: str, slide_id: int) -> str:
    return AOIManager().get_slide_text(deck_id, slide_id)


def update_aoi(deck_id: str, slide_id: int, aoi_id: str, bbox: list[float], aoi_type: str, text: str) -> dict[str, Any]:
    return AOIManager().update_aoi(deck_id, slide_id, aoi_id, bbox, aoi_type, text)


def add_aoi(deck_id: str, slide_id: int, aoi_id: str, bbox: list[float], aoi_type: str, text: str = "") -> dict[str, Any]:
    return AOIManager().add_aoi(deck_id, slide_id, aoi_id, bbox, aoi_type, text)


def delete_aoi(deck_id: str, slide_id: int, aoi_id: str) -> None:
    AOIManager().delete_aoi(deck_id, slide_id, aoi_id)
