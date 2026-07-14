"""Optional, OpenAI-compatible vision AOI generation."""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROMPT_SCHEMA_VERSION = "attentive-llm-aoi-v1"
ALLOWED_AOI_TYPES = {
    "title", "text", "figure", "diagram", "table", "formula", "code",
    "caption", "footer", "axis_label", "mixed", "whole_slide",
}


def sanitized_llm_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message[:240]}"


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

    def generate(self, image_path: str, slide_text: str, rule_aois: list[dict[str, Any]], text_aois: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.is_configured():
            raise RuntimeError("LLM AOI API is not configured")
        payload = self._build_payload(image_path, slide_text, rule_aois, text_aois)
        request = urllib.request.Request(
            str(self.config.endpoint),
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError("LLM AOI request failed") from exc
        data = self._extract_json_object(self._extract_message_content(raw))
        aois = data.get("aois")
        if not isinstance(aois, list):
            raise ValueError("LLM AOI response must contain an 'aois' list")
        return self._validate_aois(aois)

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
            "Generate one flat semantic AOI list. The image is visual truth; PDF/OCR AOIs are anchors; "
            "rule AOIs are coarse hints. Never return parents, children, containers, duplicates, or invented text. "
            "Keep each complete sentence/list item and each code/table/diagram/formula/image panel together. "
            "Allowed types: title,text,figure,diagram,table,formula,code,caption,footer,axis_label,mixed. "
            "Return {\"aois\":[{\"aoi_id\":\"llm_aoi_1\",\"bbox\":[0.1,0.1,0.5,0.3],"
            "\"type\":\"text\",\"text\":\"...\",\"confidence\":0.85}]}.\n"
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
            if not isinstance(item, dict) or not self._valid_bbox(item.get("bbox")):
                continue
            aoi_type = str(item.get("type", "mixed")).strip().lower()
            if aoi_type not in ALLOWED_AOI_TYPES:
                aoi_type = "mixed"
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", item.get("group_confidence", 0.7)))))
            except (TypeError, ValueError):
                confidence = 0.7
            validated.append({
                "aoi_id": str(item.get("aoi_id", "")),
                "bbox": [float(value) for value in item["bbox"]],
                "type": aoi_type,
                "text": str(item.get("text", "")).strip(),
                "source": "llm_guided",
                "group_confidence": round(confidence, 3),
                "include_in_learning": aoi_type != "footer",
            })
        if not validated:
            raise ValueError("LLM AOI response contained no valid AOIs")
        return self._dedupe_and_renumber(validated)

    @staticmethod
    def _dedupe_and_renumber(aois: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique, seen = [], set()
        for aoi in aois:
            normalized = " ".join(re.sub(r"[^\w]+", " ", str(aoi.get("text", "")).casefold()).split())
            if normalized and normalized in seen:
                continue
            if normalized:
                seen.add(normalized)
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
