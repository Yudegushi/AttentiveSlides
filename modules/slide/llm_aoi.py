"""Optional, OpenAI-compatible vision AOI generation."""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from modules.common.schemas import VisualContextItem


PROMPT_SCHEMA_VERSION = "attentive-llm-aoi-v4-visual-aoi-promotion"
ALLOWED_AOI_TYPES = {
    "title", "text", "figure", "diagram", "table", "formula", "code",
    "caption", "footer", "axis_label", "mixed", "whole_slide",
}
TEXT_AOI_TYPES = frozenset({"title", "text", "caption", "footer", "axis_label"})
ALLOWED_VISUAL_CONTEXT_TYPES = {
    "formula", "chart", "diagram", "table", "image", "code", "other",
}
MAX_VISUAL_CONTEXT_ITEMS = 6
MIN_VISUAL_CONFIDENCE = 0.55
MIN_VISUAL_WIDTH = 0.04
MIN_VISUAL_HEIGHT = 0.025
MIN_VISUAL_AREA = 0.002
VISUAL_CONTEXT_DEDUPE_IOU = 0.80

VisualContextStatus = Literal["used", "empty", "invalid"]


@dataclass(frozen=True)
class LLMAOIResult:
    aois: tuple[dict[str, Any], ...]
    visual_context: tuple[VisualContextItem, ...]
    visual_context_status: VisualContextStatus


def sanitized_llm_error(error: Exception) -> str:
    # Exception messages from URL/request libraries may contain the configured
    # endpoint, query parameters, response bodies, or other credentials.
    # Persist and display only fixed copy at this trust boundary.
    return "LLM AOI processing failed"


@dataclass
class LLMAOIConfig:
    endpoint: str | None = None
    api_key: str | None = None
    model: str = "gpt-4o-mini"
    timeout_sec: int = 90
    max_image_side: int = 1280

    @classmethod
    def from_env(cls) -> "LLMAOIConfig":
        endpoint = os.getenv("SLIDE_AOI_LLM_ENDPOINT")
        qwen_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if not endpoint and base_url:
            endpoint = base_url.rstrip("/") + "/chat/completions"
        api_key = os.getenv("SLIDE_AOI_LLM_API_KEY") or qwen_key or os.getenv("OPENAI_API_KEY")
        if not endpoint and qwen_key:
            endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        elif not endpoint and api_key:
            endpoint = "https://api.openai.com/v1/chat/completions"
        return cls(
            endpoint=endpoint,
            api_key=api_key,
            model=(os.getenv("SLIDE_AOI_LLM_MODEL") or os.getenv("QWEN_MODEL") or os.getenv("OPENAI_MODEL") or ("qwen-vl-plus" if qwen_key else "gpt-4o-mini")),
            timeout_sec=int(os.getenv("SLIDE_AOI_LLM_TIMEOUT_SEC", "90")),
            max_image_side=int(os.getenv("SLIDE_AOI_LLM_MAX_IMAGE_SIDE", "1280")),
        )


class LLMAOIGenerator:
    def __init__(self, config: LLMAOIConfig | None = None) -> None:
        self.config = config or LLMAOIConfig.from_env()

    def is_configured(self) -> bool:
        return bool(self.config.endpoint and self.config.api_key)

    def profile(self, anchor_digest: str) -> str:
        payload = {
            "model": self.config.model,
            "prompt_schema": PROMPT_SCHEMA_VERSION,
            "max_image_side": self.config.max_image_side,
            "anchor_digest": anchor_digest,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def generate(
        self,
        image_path: str,
        slide_text: str,
        rule_aois: list[dict[str, Any]],
        text_aois: list[dict[str, Any]],
    ) -> LLMAOIResult:
        if not self.is_configured():
            raise RuntimeError("LLM AOI API is not configured")
        try:
            payload = self._build_payload(image_path, slide_text, rule_aois, text_aois)
            request = urllib.request.Request(
                str(self.config.endpoint),
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.config.timeout_sec) as response:
                raw = response.read().decode("utf-8")
            data = self._extract_json_object(self._extract_message_content(raw))
            aois = data.get("aois")
            if not isinstance(aois, list):
                raise ValueError("LLM AOI response must contain an 'aois' list")
            validated_aois = tuple(self._validate_aois(aois))
            visual_context, visual_status = self._validate_visual_context(
                data.get("visual_context"),
                field_present="visual_context" in data,
            )
            return LLMAOIResult(
                aois=validated_aois,
                visual_context=visual_context,
                visual_context_status=visual_status,
            )
        except Exception as exc:
            raise RuntimeError("LLM AOI request failed") from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _build_payload(self, image_path: str, slide_text: str, rule_aois: list[dict[str, Any]], text_aois: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "temperature": 0.1,
            "max_tokens": 4000,
            "messages": [
                {"role": "system", "content": "Return only valid JSON with normalized AOI bounding boxes."},
                {"role": "user", "content": [
                    {"type": "text", "text": self._prompt(slide_text, rule_aois, text_aois)},
                    {"type": "image_url", "image_url": {"url": self._image_data_url(image_path)}},
                ]},
            ],
        }

    @staticmethod
    def _prompt(slide_text: str, rule_aois: list[dict[str, Any]], text_aois: list[dict[str, Any]]) -> str:
        return (
            "Generate one flat semantic AOI list. The image is visual truth; paragraph anchors are text provenance; "
            "rule AOIs are coarse visual hints. Never return parents, children, containers, duplicates, or invented text. "
            "One visual paragraph or one list item equals one text AOI. "
            "Rendered line wrapping is never an AOI boundary. "
            "Keep multiple complete sentences together when they share one visual paragraph. "
            "Do not return titles, headings, headers, footers, or page numbers. "
            "Every text-like AOI must return anchor_ids. "
            "Visual AOIs without text anchors may return bbox. "
            "Allowed types: text,figure,diagram,table,formula,code,caption,axis_label,mixed. "
            "Positive example: three rendered lines belonging to one paragraph return one text AOI with all relevant anchor_ids. "
            "Forbidden example: do not return three line-level AOIs for those same three wrapped lines. "
            "In the same JSON object, optionally return visual_context.items. "
            "Describe only meaningful visible formulas, charts, diagrams, tables, code, and instructional images. "
            "Exclude logos, headers, footers, backgrounds, decorative icons, and tiny fragments. "
            "For each item return type,bbox,description,transcription,confidence. "
            "For formulas and readable code, preserve the visible content in transcription and explain its visible role separately in description. "
            "For each self-contained targetable visual item, also return one matching visual AOI with the same region. "
            "Every formula visual_context item must also appear as one type=formula AOI with the same bbox. "
            "Every targetable chart, diagram, table, or code visual_context item must likewise have one matching visual AOI. "
            "Do not duplicate overlapping visual items or AOIs. "
            "Return {\"aois\":[{\"aoi_id\":\"llm_aoi_1\",\"type\":\"text\","
            "\"anchor_ids\":[\"pdf_paragraph_1\"],\"text\":\"...\",\"confidence\":0.85},"
            "{\"aoi_id\":\"llm_aoi_2\",\"type\":\"diagram\",\"bbox\":[0.1,0.1,0.5,0.3],"
            "\"text\":\"\",\"confidence\":0.85}],\"visual_context\":{\"items\":[{"
            "\"type\":\"diagram\",\"bbox\":[0.1,0.1,0.5,0.3],"
            "\"description\":\"A visible flow diagram.\",\"transcription\":\"\","
            "\"confidence\":0.85}]}}.\n"
            f"Slide text:\n{slide_text[:5000]}\nRule AOIs:\n{json.dumps(rule_aois, ensure_ascii=False)}\n"
            f"Grounding AOIs:\n{json.dumps(text_aois, ensure_ascii=False)}"
        )

    def _image_data_url(self, image_path: str) -> str:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError("Slide image does not exist")
        return "data:image/png;base64," + base64.b64encode(self._compressed_image_bytes(path)).decode("ascii")

    def _compressed_image_bytes(self, path: Path) -> bytes:
        try:
            from PIL import Image
        except ImportError:
            return path.read_bytes()
        with Image.open(path) as opened:
            image = opened.convert("RGB")
            if max(image.size) > self.config.max_image_side:
                scale = self.config.max_image_side / max(image.size)
                image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()

    @staticmethod
    def _extract_message_content(raw: str) -> str:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            content = choices[0].get("message", {}).get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("text"))
        return raw

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        recovered = LLMAOIGenerator._recover_complete_aois(cleaned)
        if recovered:
            return {"aois": recovered}
        raise ValueError("LLM AOI response did not contain recoverable JSON")

    @staticmethod
    def _recover_complete_aois(text: str) -> list[dict[str, Any]]:
        match = re.search(r'["\']aois["\']\s*:\s*\[', text)
        if not match:
            return []
        decoder, cursor, recovered = json.JSONDecoder(), match.end(), []
        while cursor < len(text):
            start = text.find("{", cursor)
            if start < 0:
                break
            try:
                value, cursor = decoder.raw_decode(text, start)
            except json.JSONDecodeError:
                cursor = start + 1
                continue
            if isinstance(value, dict):
                recovered.append(value)
        return recovered

    def _validate_aois(self, aois: list[Any]) -> list[dict[str, Any]]:
        validated = []
        for item in aois:
            if not isinstance(item, dict):
                continue
            aoi_type = str(item.get("type", "mixed")).strip().lower()
            if aoi_type not in ALLOWED_AOI_TYPES:
                aoi_type = "mixed"
            anchor_ids = list(dict.fromkeys(
                str(value).strip()
                for value in (item.get("anchor_ids") or [])
                if str(value).strip()
            ))
            bbox_is_valid = self._valid_bbox(item.get("bbox"))
            if not bbox_is_valid and not (aoi_type in TEXT_AOI_TYPES and anchor_ids):
                continue
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", item.get("group_confidence", 0.7)))))
            except (TypeError, ValueError):
                confidence = 0.7
            validated_item = {
                "aoi_id": str(item.get("aoi_id", "")),
                "type": aoi_type,
                "text": str(item.get("text", "")).strip(),
                "source": "llm_guided",
                "group_confidence": round(confidence, 3),
                "include_in_learning": aoi_type != "footer",
            }
            if bbox_is_valid:
                validated_item["bbox"] = [float(value) for value in item["bbox"]]
            if anchor_ids:
                validated_item["anchor_ids"] = anchor_ids
            validated.append(validated_item)
        if not validated:
            raise ValueError("LLM AOI response contained no valid AOIs")
        return self._dedupe_and_renumber(validated)

    def _validate_visual_context(
        self,
        value: Any,
        *,
        field_present: bool,
    ) -> tuple[tuple[VisualContextItem, ...], VisualContextStatus]:
        if not field_present:
            return (), "empty"
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            return (), "invalid"
        raw_items = value["items"]
        if not raw_items:
            return (), "empty"

        candidates: list[VisualContextItem] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item_type = str(raw_item.get("type", "")).strip().lower()
            raw_description = raw_item.get("description", "")
            if not isinstance(raw_description, str):
                continue
            description = raw_description.strip()
            bbox = raw_item.get("bbox")
            if (
                item_type not in ALLOWED_VISUAL_CONTEXT_TYPES
                or not description
                or not self._valid_bbox(bbox)
            ):
                continue
            normalized_bbox = [float(item) for item in bbox]
            width = normalized_bbox[2] - normalized_bbox[0]
            height = normalized_bbox[3] - normalized_bbox[1]
            if (
                width < MIN_VISUAL_WIDTH
                or height < MIN_VISUAL_HEIGHT
                or width * height < MIN_VISUAL_AREA
            ):
                continue
            try:
                confidence = max(0.0, min(1.0, float(raw_item.get("confidence", 0.7))))
            except (TypeError, ValueError):
                confidence = 0.7
            if confidence < MIN_VISUAL_CONFIDENCE:
                continue
            raw_transcription = raw_item.get("transcription", "")
            transcription = (
                raw_transcription.strip()
                if isinstance(raw_transcription, str)
                else ""
            )
            candidates.append(VisualContextItem(
                visual_id="",
                type=item_type,
                bbox=normalized_bbox,
                description=description[:600],
                transcription=transcription[:1200],
                confidence=round(confidence, 3),
            ))

        retained: list[VisualContextItem] = []
        for candidate in sorted(
            candidates,
            key=lambda item: item.confidence,
            reverse=True,
        ):
            if any(
                self._compatible_visual_types(candidate.type, item.type)
                and self._bbox_iou(candidate.bbox, item.bbox)
                >= VISUAL_CONTEXT_DEDUPE_IOU
                for item in retained
            ):
                continue
            retained.append(candidate)
            if len(retained) == MAX_VISUAL_CONTEXT_ITEMS:
                break
        if not retained:
            return (), "invalid"
        return tuple(
            VisualContextItem(
                visual_id=f"visual_{index}",
                type=item.type,
                bbox=item.bbox,
                description=item.description,
                transcription=item.transcription,
                confidence=item.confidence,
            )
            for index, item in enumerate(retained, 1)
        ), "used"

    @staticmethod
    def _compatible_visual_types(first: str, second: str) -> bool:
        return first == second

    @staticmethod
    def _bbox_iou(first: list[float], second: list[float]) -> float:
        width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
        height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
        intersection = width * height
        first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
        second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
        union = first_area + second_area - intersection
        return intersection / union if union else 0.0

    @staticmethod
    def _dedupe_and_renumber(aois: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique, seen = [], set()
        for aoi in aois:
            normalized = " ".join(re.sub(r"[^\w]+", " ", str(aoi.get("text", "")).casefold()).split())
            identity = (normalized, tuple(aoi.get("anchor_ids", [])))
            if normalized and identity in seen:
                continue
            if normalized:
                seen.add(identity)
            unique.append(aoi)
        for index, aoi in enumerate(unique, 1):
            aoi["aoi_id"] = f"llm_aoi_{index}"
        return unique

    @staticmethod
    def _valid_bbox(value: Any) -> bool:
        if not isinstance(value, list) or len(value) != 4:
            return False
        try:
            x1, y1, x2, y2 = (float(item) for item in value)
        except (TypeError, ValueError):
            return False
        return 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1
