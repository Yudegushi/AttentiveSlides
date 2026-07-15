from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from modules.common.schemas import VisualContextItem
from modules.slide.aoi_manager import AOI, AOIManager, SlideAOIData
from modules.slide.llm_aoi import (
    PROMPT_SCHEMA_VERSION,
    LLMAOIConfig,
    LLMAOIGenerator,
    LLMAOIResult,
    sanitized_llm_error,
)


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01"
    b"\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeLLMGenerator:
    def __init__(self, *, result=None, error=None, profile="profile-a"):
        self.result = result if isinstance(result, LLMAOIResult) else LLMAOIResult(
            aois=tuple(result or []),
            visual_context=(),
            visual_context_status="empty",
        )
        self.error = error
        self.calls = 0
        self.config = SimpleNamespace(model="fake-vlm")
        self._profile = profile
        self.last_rule_aois = None
        self.last_text_aois = None

    def is_configured(self):
        return True

    def profile(self, anchor_digest):
        return f"{self._profile}:{anchor_digest}"

    def generate(self, image_path, slide_text, rule_aois, text_aois):
        self.calls += 1
        self.last_rule_aois = list(rule_aois)
        self.last_text_aois = list(text_aois)
        if self.error is not None:
            raise self.error
        return self.result


def llm_item(text="alpha beta gamma delta", *, aoi_type="text", bbox=None, anchor_ids=None):
    item = {
        "aoi_id": "anything",
        "bbox": bbox or [0.1, 0.2, 0.8, 0.4],
        "type": aoi_type,
        "text": text,
        "source": "llm_guided",
        "group_confidence": 0.9,
        "include_in_learning": True,
    }
    if anchor_ids is not None:
        item["anchor_ids"] = anchor_ids
    elif aoi_type in {"title", "text", "caption", "footer", "axis_label"}:
        item["anchor_ids"] = ["pdf_paragraph_1"]
    return item


def visual_item(
    *,
    item_type="formula",
    bbox=None,
    description="Conditional probability formula.",
    transcription="p(y | x)",
    confidence=0.9,
):
    return {
        "type": item_type,
        "bbox": bbox or [0.2, 0.3, 0.7, 0.45],
        "description": description,
        "transcription": transcription,
        "confidence": confidence,
    }


class FakeHTTPResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def grounding_anchor(
    anchor_id,
    text,
    bbox,
    *,
    role="paragraph",
    block_id=1,
    starts_bullet=False,
):
    return AOI(
        anchor_id,
        list(bbox),
        "text",
        text,
        source="pdf_text_semantic",
        group_confidence=0.9,
        role=role,
        children=[{
            "text": text,
            "bbox": list(bbox),
            "source": "pdf_text",
            "confidence": 1.0,
            "block_id": block_id,
            "line_id": 0,
            "font_size": 10.0,
            "font_family": "Body",
            "font_flags": 0,
            "direction": [1.0, 0.0],
            "starts_bullet": starts_bullet,
        }],
    )


class LLMAOIGeneratorValidationTest(unittest.TestCase):
    def test_generator_returns_aois_and_formula_visual_context(self):
        provider_payload = {
            "choices": [{"message": {"content": json.dumps({
                "aois": [{
                    "type": "formula",
                    "bbox": [0.2, 0.3, 0.7, 0.45],
                    "text": "",
                    "confidence": 0.91,
                }],
                "visual_context": {"items": [visual_item(
                    description="A conditional-probability formula.",
                    transcription="p(y | x)",
                    confidence=0.91,
                )]},
            })}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "slide.png"
            image_path.write_bytes(PNG)
            generator = LLMAOIGenerator(LLMAOIConfig(
                endpoint="https://example.invalid/chat/completions",
                api_key="secret",
                model="fake-vlm",
            ))
            with patch(
                "modules.slide.llm_aoi.urllib.request.urlopen",
                return_value=FakeHTTPResponse(json.dumps(provider_payload).encode()),
            ) as urlopen:
                result = generator.generate(str(image_path), "", [], [])

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(len(result.aois), 1)
        self.assertEqual(result.visual_context_status, "used")
        self.assertEqual(result.visual_context[0].description, "A conditional-probability formula.")
        self.assertEqual(result.visual_context[0].transcription, "p(y | x)")

    def test_malformed_visual_context_does_not_reject_valid_aois(self):
        generator = LLMAOIGenerator()
        aois = tuple(generator._validate_aois([{
            "type": "diagram",
            "bbox": [0.1, 0.1, 0.5, 0.5],
            "text": "",
        }]))
        visual_context, status = generator._validate_visual_context(
            {"items": "not-a-list"},
            field_present=True,
        )

        self.assertEqual(len(aois), 1)
        self.assertEqual(visual_context, ())
        self.assertEqual(status, "invalid")

    def test_visual_context_filters_tiny_low_confidence_and_duplicate_items(self):
        generator = LLMAOIGenerator()
        items, status = generator._validate_visual_context({"items": [
            visual_item(confidence=0.91),
            visual_item(bbox=[0.205, 0.302, 0.695, 0.448], confidence=0.8),
            visual_item(bbox=[0.1, 0.1, 0.12, 0.12], confidence=0.99),
            visual_item(bbox=[0.1, 0.6, 0.4, 0.8], confidence=0.54),
        ]}, field_present=True)

        self.assertEqual(status, "used")
        self.assertEqual(len(items), 1)
        self.assertGreaterEqual(items[0].bbox[2] - items[0].bbox[0], 0.04)
        self.assertGreaterEqual(items[0].bbox[3] - items[0].bbox[1], 0.025)
        self.assertGreaterEqual(
            (items[0].bbox[2] - items[0].bbox[0])
            * (items[0].bbox[3] - items[0].bbox[1]),
            0.002,
        )

    def test_visual_context_is_capped_at_six_items(self):
        generator = LLMAOIGenerator()
        raw_items = [
            visual_item(
                item_type="chart",
                bbox=[0.05 + index * 0.1, 0.2, 0.12 + index * 0.1, 0.3],
                description=f"Chart {index}",
                transcription="",
                confidence=0.99 - index * 0.01,
            )
            for index in range(8)
        ]

        items, status = generator._validate_visual_context(
            {"items": raw_items},
            field_present=True,
        )

        self.assertEqual(status, "used")
        self.assertEqual(len(items), 6)
        self.assertEqual([item.visual_id for item in items], [f"visual_{i}" for i in range(1, 7)])

    def test_visual_context_rejects_non_string_description_and_normalizes_null_transcription(self):
        generator = LLMAOIGenerator()
        items, status = generator._validate_visual_context({"items": [
            visual_item(description=None),
            visual_item(
                description="A visible formula.",
                transcription=None,
            ),
        ]}, field_present=True)

        self.assertEqual(status, "used")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "A visible formula.")
        self.assertEqual(items[0].transcription, "")

    def test_sanitized_error_never_echoes_arbitrary_exception_text(self):
        sentinel = "SENTINEL_ENDPOINT_TOKEN"

        error = sanitized_llm_error(ValueError(f"bad endpoint https://host/?key={sentinel}"))

        self.assertEqual(error, "LLM AOI processing failed")
        self.assertNotIn(sentinel, error)

    def test_rejects_empty_and_invalid_bbox_results(self):
        generator = LLMAOIGenerator()
        for payload in ([], [{"bbox": []}], [{"bbox": [0.8, 0.1, 0.2, 0.4]}]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                generator._validate_aois(payload)

    def test_deduplicates_text_and_stably_renumbers(self):
        generator = LLMAOIGenerator()
        result = generator._validate_aois(
            [
                {"bbox": [0.1, 0.1, 0.4, 0.2], "type": "text", "text": "Same text", "confidence": 0.8},
                {"bbox": [0.1, 0.2, 0.4, 0.3], "type": "text", "text": "same, text!", "confidence": 0.7},
                {"bbox": [0.1, 0.3, 0.4, 0.4], "type": "diagram", "text": "Visual", "confidence": 0.6},
            ]
        )
        self.assertEqual([item["aoi_id"] for item in result], ["llm_aoi_1", "llm_aoi_2"])
        self.assertEqual(result[0]["group_confidence"], 0.8)


class LLMAOIPromptV3Test(unittest.TestCase):
    def prompt(self) -> str:
        return LLMAOIGenerator._prompt("slide text", [], [])

    def test_prompt_defines_visual_paragraph_not_sentence_or_line(self) -> None:
        prompt = self.prompt()
        self.assertIn("One visual paragraph or one list item equals one text AOI.", prompt)
        self.assertIn("Rendered line wrapping is never an AOI boundary.", prompt)
        self.assertIn("Keep multiple complete sentences together when they share one visual paragraph.", prompt)
        self.assertIn("three rendered lines", prompt)
        self.assertIn("do not return three line-level AOIs", prompt)

    def test_prompt_excludes_non_content_roles(self) -> None:
        self.assertIn("Do not return titles, headings, headers, footers, or page numbers.", self.prompt())

    def test_prompt_requires_anchor_ids_for_text_aois(self) -> None:
        prompt = self.prompt()
        self.assertIn("Every text-like AOI must return anchor_ids.", prompt)
        self.assertIn("Visual AOIs without text anchors may return bbox.", prompt)

    def test_validation_preserves_clean_anchor_ids(self) -> None:
        result = LLMAOIGenerator()._validate_aois([
            {
                "type": "text",
                "text": "Paragraph",
                "anchor_ids": [" pdf_paragraph_1 ", "", "pdf_paragraph_1", "pdf_paragraph_2"],
            }
        ])
        self.assertEqual(result[0]["anchor_ids"], ["pdf_paragraph_1", "pdf_paragraph_2"])

    def test_prompt_schema_version_invalidates_v1_profile(self) -> None:
        generator = LLMAOIGenerator(LLMAOIConfig(model="fake", max_image_side=1280))
        anchor_digest = "anchor-digest"
        v1_payload = {
            "model": "fake",
            "prompt_schema": "attentive-llm-aoi-v1",
            "max_image_side": 1280,
            "anchor_digest": anchor_digest,
        }
        v1_profile = hashlib.sha256(
            json.dumps(v1_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(PROMPT_SCHEMA_VERSION, "attentive-llm-aoi-v4-visual-aoi-promotion")
        self.assertNotEqual(generator.profile(anchor_digest), v1_profile)

    def test_prompt_requests_visual_context_in_same_response(self) -> None:
        prompt = self.prompt()
        self.assertIn("In the same JSON object, optionally return visual_context.items.", prompt)
        self.assertIn("transcription", prompt)
        self.assertIn("description", prompt)
        self.assertIn("Every formula visual_context item must also appear", prompt)
        self.assertIn("Do not duplicate overlapping visual items or AOIs.", prompt)

    def test_anchored_text_without_bbox_is_valid(self) -> None:
        result = LLMAOIGenerator()._validate_aois([
            {"type": "text", "text": "Paragraph", "anchor_ids": ["pdf_paragraph_1"]}
        ])
        self.assertNotIn("bbox", result[0])
        self.assertEqual(result[0]["anchor_ids"], ["pdf_paragraph_1"])

    def test_visual_item_without_bbox_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no valid AOIs"):
            LLMAOIGenerator()._validate_aois([{"type": "diagram", "text": "Flow"}])


class LLMAOIManagerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image_path = self.root / "slide_images" / "deck_slide_001_250dpi.png"
        self.image_path.parent.mkdir(parents=True)
        self.image_path.write_bytes(PNG)

    def tearDown(self):
        self.temporary.cleanup()

    def seeded_manager(self, generator, *, anchors=None):
        manager = AOIManager(str(self.root), llm_aoi_generator=generator)
        anchor_aois = anchors or [
            AOI(
                "pdf_paragraph_1",
                [0.1, 0.2, 0.8, 0.4],
                "text",
                "alpha beta gamma delta epsilon zeta eta theta",
                source="pdf_text_semantic",
                children=[{"text": "alpha", "bbox": [0.1, 0.2, 0.2, 0.3]}],
                role="paragraph",
            )
        ]
        manager.save_slide_data(
            "deck",
            SlideAOIData(
                slide_id=1,
                slide_image_path=str(self.image_path),
                ocr_text=" ".join(aoi.text for aoi in anchor_aois),
                aois=manager.generate_rule_aois() + anchor_aois,
                text_source="pdf_text",
                auto_aoi_method="pdf_text_semantic",
            ),
        )
        return manager

    def test_reconciliation_rejects_low_text_coverage_but_accepts_visual_heavy(self):
        manager = self.seeded_manager(FakeLLMGenerator())
        grounding = [
            grounding_anchor("a", "one two three four", [0.1, 0.1, 0.4, 0.2]),
            grounding_anchor("b", "five six seven eight nine ten", [0.1, 0.3, 0.4, 0.4], block_id=2),
        ]
        with self.assertRaisesRegex(ValueError, "coverage"):
            manager.reconcile_llm_aois([
                AOI("x", [], "text", "model text", source="llm_guided", anchor_ids=["a"])
            ], grounding, minimum_text_coverage=0.75)
        visual = manager.reconcile_llm_aois(
            [AOI("x", [0.2, 0.2, 0.5, 0.5], "diagram", "flow", source="llm_guided")],
            [grounding_anchor("a", "few anchors", [0.1, 0.1, 0.4, 0.2])],
        )
        self.assertEqual(visual[0].type, "diagram")

    def test_success_is_separate_preserves_deterministic_and_caches_by_profile(self):
        generator = FakeLLMGenerator(result=[llm_item("alpha beta gamma delta epsilon zeta eta theta")])
        manager = self.seeded_manager(generator)
        before = json.dumps(manager.manifest["deck:1"]["aois"], ensure_ascii=False)
        first = manager.process_llm_aoi("deck", 1, allow_ocr=False)
        second = manager.process_llm_aoi("deck", 1, allow_ocr=False)
        self.assertEqual(generator.calls, 1)
        self.assertEqual(first["llm_aoi_status"], "used")
        self.assertEqual(second["llm_aoi_status"], "used")
        self.assertEqual(first["llm_aoi_model"], "fake-vlm")
        self.assertTrue(first["llm_aoi_profile"].startswith("profile-a:"))
        self.assertNotIn("api_key", first)
        self.assertEqual(json.dumps(first["aois"], ensure_ascii=False), before)
        manager.process_llm_aoi("deck", 1, allow_ocr=False, force=True)
        self.assertEqual(generator.calls, 2)

    def test_successful_cache_persists_visual_context_and_status(self):
        generator = FakeLLMGenerator(result=LLMAOIResult(
            aois=(
                llm_item("alpha beta gamma delta epsilon zeta eta theta"),
                llm_item("visual", aoi_type="formula", bbox=[0.2, 0.3, 0.7, 0.45]),
            ),
            visual_context=(VisualContextItem(
                visual_id="visual_1",
                type="formula",
                bbox=[0.2, 0.3, 0.7, 0.45],
                description="A conditional-probability formula.",
                transcription="p(y | x)",
                confidence=0.91,
            ),),
            visual_context_status="used",
        ))
        manager = self.seeded_manager(generator)

        result = manager.process_llm_aoi("deck", 1, allow_ocr=False)

        self.assertEqual(result["llm_visual_context_status"], "used")
        self.assertEqual(result["llm_visual_context"][0]["description"], "A conditional-probability formula.")
        self.assertEqual(result["llm_visual_context"][0]["transcription"], "p(y | x)")
        self.assertEqual(result["llm_visual_context"][0]["linked_aoi_id"], "llm_aoi_2")

    def test_visual_context_formula_is_promoted_when_model_omits_visual_aoi(self):
        generator = FakeLLMGenerator(result=LLMAOIResult(
            aois=(
                llm_item("alpha beta gamma delta epsilon zeta eta theta"),
            ),
            visual_context=(VisualContextItem(
                visual_id="visual_1",
                type="formula",
                bbox=[0.2, 0.3, 0.7, 0.45],
                description="A conditional-probability formula.",
                transcription="p(y | x)",
                confidence=0.91,
            ),),
            visual_context_status="used",
        ))
        manager = self.seeded_manager(generator)

        result = manager.process_llm_aoi("deck", 1, allow_ocr=False)

        promoted = [
            item for item in result["llm_aois"]
            if item["type"] == "formula"
        ]
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0]["bbox"], [0.2, 0.3, 0.7, 0.45])
        self.assertEqual(promoted[0]["source"], "llm_visual_context")
        self.assertEqual(
            result["llm_visual_context"][0]["linked_aoi_id"],
            promoted[0]["aoi_id"],
        )

    def test_aoi_fallback_clears_visual_context_without_leaking_error_details(self):
        sentinel = "SENTINEL_PROVIDER_SECRET"
        manager = self.seeded_manager(FakeLLMGenerator(error=RuntimeError(sentinel)))

        result = manager.process_llm_aoi("deck", 1, allow_ocr=False)

        self.assertEqual(result["llm_aoi_status"], "fallback_used")
        self.assertEqual(result["llm_visual_context"], [])
        self.assertEqual(result["llm_visual_context_status"], "empty")
        self.assertNotIn(sentinel, json.dumps(result))

    def test_cached_profile_returns_visual_count_without_second_generation(self):
        generator = FakeLLMGenerator(result=LLMAOIResult(
            aois=(
                llm_item("alpha beta gamma delta epsilon zeta eta theta"),
                llm_item("visual", aoi_type="diagram", bbox=[0.2, 0.3, 0.7, 0.6]),
            ),
            visual_context=(VisualContextItem(
                visual_id="visual_1",
                type="diagram",
                bbox=[0.2, 0.3, 0.7, 0.6],
                description="A flow diagram.",
            ),),
            visual_context_status="used",
        ))
        manager = self.seeded_manager(generator)

        manager.process_llm_aoi("deck", 1, allow_ocr=False)
        manager.process_llm_aoi("deck", 1, allow_ocr=False)
        state = manager.get_llm_aoi_state("deck", 1)

        self.assertEqual(generator.calls, 1)
        self.assertTrue(state["eligible"])
        self.assertEqual(state["visual_count"], 1)
        self.assertEqual(state["visual_context_status"], "used")

    def test_generator_receives_only_flat_stable_anchor_fields(self):
        generator = FakeLLMGenerator(result=[llm_item("alpha beta gamma delta epsilon zeta eta theta")])
        manager = self.seeded_manager(generator)
        manager.process_llm_aoi("deck", 1, allow_ocr=False)
        self.assertIsNotNone(generator.last_text_aois)
        self.assertEqual(
            set(generator.last_text_aois[0]),
            {"anchor_id", "role", "text", "bbox", "line_count"},
        )
        self.assertNotIn("children", generator.last_text_aois[0])
        self.assertEqual(generator.last_text_aois[0]["anchor_id"], "pdf_paragraph_1")
        self.assertEqual(generator.last_text_aois[0]["role"], "paragraph")
        self.assertEqual(generator.last_text_aois[0]["line_count"], 1)

    def test_generator_excludes_ocr_title_from_grounding(self):
        generator = FakeLLMGenerator(result=[llm_item("Body paragraph")])
        anchors = [
            grounding_anchor("pdf_paragraph_1", "Body paragraph", [0.1, 0.3, 0.8, 0.4]),
            AOI(
                "ocr_title",
                [0.1, 0.1, 0.8, 0.2],
                "title",
                "Slide title",
                source="ocr",
                children=[{"text": "Slide title", "bbox": [0.1, 0.1, 0.8, 0.2]}],
            ),
        ]
        manager = self.seeded_manager(generator, anchors=anchors)

        manager.process_llm_aoi("deck", 1, allow_ocr=False)

        self.assertEqual([item["anchor_id"] for item in generator.last_text_aois], ["pdf_paragraph_1"])

    def test_timeout_and_malformed_output_fall_back_without_touching_aois(self):
        for generator in (
            FakeLLMGenerator(error=TimeoutError("  temporary   timeout  ")),
            FakeLLMGenerator(result=[llm_item("visual", aoi_type="diagram", bbox=[0.8, 0.2, 0.1, 0.4])]),
        ):
            with self.subTest(generator=generator):
                manager = self.seeded_manager(generator)
                before = json.dumps(manager.manifest["deck:1"]["aois"], ensure_ascii=False)
                result = manager.process_llm_aoi("deck", 1, allow_ocr=False)
                self.assertEqual(result["llm_aoi_status"], "fallback_used")
                self.assertEqual(result["llm_aois"], [])
                self.assertLessEqual(len(result["llm_aoi_error"]), 280)
                self.assertNotIn("  ", result["llm_aoi_error"])
                self.assertEqual(json.dumps(result["aois"], ensure_ascii=False), before)

    def test_malformed_endpoint_and_key_never_reach_manifest_or_exposed_state(self):
        endpoint_sentinel = "SENTINEL_ENDPOINT_TOKEN"
        key_sentinel = "SENTINEL_API_KEY"
        generator = LLMAOIGenerator(
            LLMAOIConfig(
                endpoint=f"not a url {endpoint_sentinel}",
                api_key=key_sentinel,
                model="fake-vlm",
            )
        )
        manager = self.seeded_manager(generator)

        result = manager.process_llm_aoi("deck", 1, allow_ocr=False)
        state = manager.get_llm_aoi_state("deck", 1)
        exposed = json.dumps({"result": result, "state": state}, ensure_ascii=False)

        self.assertEqual(result["llm_aoi_status"], "fallback_used")
        self.assertEqual(result["llm_aoi_error"], "LLM AOI processing failed")
        self.assertNotIn(endpoint_sentinel, exposed)
        self.assertNotIn(key_sentinel, exposed)

    def test_anchor_change_invalidates_old_variant_and_effective_selection(self):
        generator = FakeLLMGenerator(result=[llm_item("alpha beta gamma delta epsilon zeta eta theta")])
        manager = self.seeded_manager(generator)
        manager.process_llm_aoi("deck", 1, allow_ocr=False)
        manager.manifest["deck:1"]["aois"][-1]["text"] = "changed anchor"
        state = manager.get_llm_aoi_state("deck", 1)
        effective, profile = manager.get_effective_aois("deck", 1, use_llm_aoi=True)
        self.assertFalse(state["eligible"])
        self.assertEqual(profile, "deterministic")
        self.assertTrue(any(aoi["aoi_id"] == "whole_slide" for aoi in effective))

    def test_anchor_line_count_changes_digest(self):
        manager = self.seeded_manager(FakeLLMGenerator())
        slide_data = manager.manifest["deck:1"]
        original = manager._anchor_digest(slide_data)

        slide_data["aois"][-1]["children"].append({
            "text": "continuation",
            "bbox": [0.2, 0.3, 0.4, 0.4],
        })

        self.assertNotEqual(manager._anchor_digest(slide_data), original)

    def test_effective_llm_always_contains_whole_slide(self):
        generator = FakeLLMGenerator(result=[llm_item("alpha beta gamma delta epsilon zeta eta theta")])
        manager = self.seeded_manager(generator)
        manager.process_llm_aoi("deck", 1, allow_ocr=False)
        selected, profile = manager.get_effective_aois("deck", 1, use_llm_aoi=True)
        self.assertNotEqual(profile, "deterministic")
        self.assertTrue(any(aoi["aoi_id"] == "whole_slide" for aoi in selected))

    def test_allow_ocr_false_never_calls_region_ocr(self):
        generator = FakeLLMGenerator(result=[llm_item("visual", aoi_type="diagram")])
        manager = AOIManager(str(self.root), llm_aoi_generator=generator)
        with patch("modules.slide.aoi_manager.SlideParser.render_slide", return_value=str(self.image_path)), \
             patch("modules.slide.aoi_manager.SlideParser.extract_pdf_text_boxes", return_value=[]), \
             patch("modules.slide.aoi_manager.SlideParser.extract_pdf_image_boxes", return_value=[[0.1, 0.1, 0.7, 0.7]]), \
             patch("modules.slide.aoi_manager.OCREngine.extract_region_boxes") as region_ocr:
            manager.process_llm_aoi("deck", 1, allow_ocr=False)
        region_ocr.assert_not_called()

    def test_deterministic_save_keeps_matching_variant_and_clears_mismatch(self):
        generator = FakeLLMGenerator(result=[llm_item("alpha beta gamma delta epsilon zeta eta theta")])
        manager = self.seeded_manager(generator)
        manager.process_llm_aoi("deck", 1, allow_ocr=False)
        current = manager.manifest["deck:1"]
        same = SlideAOIData(1, str(self.image_path), current["ocr_text"], [AOI(**aoi) for aoi in current["aois"]], current["text_source"], current["auto_aoi_method"])
        preserved = manager.save_slide_data("deck", same)
        self.assertEqual(preserved["llm_aoi_status"], "used")
        changed_aois = [AOI(**aoi) for aoi in current["aois"]]
        changed_aois[-1].text = "different deterministic anchors"
        stale = manager.save_slide_data("deck", SlideAOIData(1, str(self.image_path), "different", changed_aois, "pdf_text", "pdf_text_semantic"))
        self.assertEqual(stale["llm_aoi_status"], "not_requested")
        self.assertEqual(stale["llm_aois"], [])

    def test_matching_cache_defaults_missing_visual_fields(self):
        generator = FakeLLMGenerator()
        manager = self.seeded_manager(generator)
        current = manager.manifest["deck:1"]
        digest = manager._anchor_digest(current)
        current.update({
            "llm_aois": [llm_item("alpha beta gamma delta epsilon zeta eta theta")],
            "llm_aoi_status": "used",
            "llm_aoi_profile": generator.profile(digest),
        })
        current.pop("llm_visual_context", None)
        current.pop("llm_visual_context_status", None)
        deterministic = SlideAOIData(
            1,
            str(self.image_path),
            current["ocr_text"],
            [AOI(**aoi) for aoi in current["aois"]],
            current["text_source"],
            current["auto_aoi_method"],
        )

        preserved = manager.save_slide_data("deck", deterministic)
        state = manager.get_llm_aoi_state("deck", 1)

        self.assertEqual(preserved["llm_visual_context"], [])
        self.assertEqual(preserved["llm_visual_context_status"], "empty")
        self.assertEqual(state["visual_count"], 0)
        self.assertEqual(state["visual_context_status"], "empty")


class LLMAOIProvenanceReconciliationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.manager = AOIManager(self.temporary.name, llm_aoi_generator=FakeLLMGenerator())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_text_bbox_is_union_of_referenced_anchors(self) -> None:
        grounding = [
            grounding_anchor("a", "First paragraph", [0.10, 0.20, 0.60, 0.28]),
            grounding_anchor("b", "Second paragraph", [0.12, 0.30, 0.75, 0.38], block_id=2),
        ]
        llm = AOI(
            "model",
            [0.0, 0.0, 0.1, 0.1],
            "text",
            "invented model formatting",
            source="llm_guided",
            anchor_ids=["b", "a", "b"],
        )

        result = self.manager.reconcile_llm_aois([llm], grounding, minimum_text_coverage=0.0)

        self.assertEqual(result[0].anchor_ids, ["a", "b"])
        self.assertEqual(result[0].text, "First paragraph Second paragraph")
        self.assertEqual(result[0].bbox, [0.10, 0.20, 0.75, 0.38])

    def test_unknown_or_excluded_anchor_is_rejected(self) -> None:
        grounding = [
            grounding_anchor("content", "Body", [0.10, 0.20, 0.60, 0.28]),
            grounding_anchor("heading", "Heading", [0.10, 0.10, 0.60, 0.16], role="heading"),
            AOI("ocr_title", [0.10, 0.05, 0.70, 0.12], "title", "OCR title", source="ocr"),
        ]
        llm = [
            AOI("unknown", [], "text", "Unknown", source="llm_guided", anchor_ids=["missing"]),
            AOI("excluded", [], "text", "Heading", source="llm_guided", anchor_ids=["heading"]),
            AOI("ocr-excluded", [], "text", "OCR title", source="llm_guided", anchor_ids=["ocr_title"]),
            AOI("visual", [0.70, 0.20, 0.90, 0.50], "diagram", "Flow", source="llm_guided"),
        ]

        result = self.manager.reconcile_llm_aois(llm, grounding, minimum_text_coverage=0.0)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, "diagram")
        self.assertIsNone(result[0].anchor_ids)

    def test_same_anchor_split_outputs_collapse_to_one_aoi(self) -> None:
        grounding = [grounding_anchor("a", "Canonical paragraph", [0.10, 0.20, 0.70, 0.30])]
        llm = [
            AOI("one", [], "text", "First fragment", source="llm_guided", group_confidence=0.9, anchor_ids=["a"]),
            AOI("two", [], "text", "Second fragment", source="llm_guided", group_confidence=0.7, anchor_ids=["a"]),
        ]

        result = self.manager.reconcile_llm_aois(llm, grounding)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].anchor_ids, ["a"])
        self.assertEqual(result[0].text, "Canonical paragraph")
        self.assertEqual(result[0].bbox, [0.10, 0.20, 0.70, 0.30])
        self.assertEqual(result[0].group_confidence, 0.7)

    def test_continuous_anchor_outputs_merge(self) -> None:
        grounding = [
            grounding_anchor("a", "Paragraph starts", [0.10, 0.20, 0.72, 0.25], block_id=10),
            grounding_anchor("b", "and continues", [0.12, 0.255, 0.74, 0.305], block_id=11),
        ]
        llm = [
            AOI("one", [], "text", "First", source="llm_guided", group_confidence=0.9, anchor_ids=["a"]),
            AOI("two", [], "text", "Second", source="llm_guided", group_confidence=0.8, anchor_ids=["b"]),
        ]

        result = self.manager.reconcile_llm_aois(llm, grounding)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].anchor_ids, ["a", "b"])
        self.assertEqual(result[0].text, "Paragraph starts and continues")
        self.assertEqual(result[0].bbox, [0.10, 0.20, 0.74, 0.305])
        self.assertEqual(result[0].group_confidence, 0.8)

    def test_new_bullet_anchor_outputs_remain_separate(self) -> None:
        grounding = [
            grounding_anchor("a", "• First item", [0.10, 0.20, 0.72, 0.25], role="list_item", block_id=10, starts_bullet=True),
            grounding_anchor("b", "• Second item", [0.10, 0.255, 0.74, 0.305], role="list_item", block_id=11, starts_bullet=True),
        ]
        llm = [
            AOI("one", [], "text", "First", source="llm_guided", anchor_ids=["a"]),
            AOI("two", [], "text", "Second", source="llm_guided", anchor_ids=["b"]),
        ]

        result = self.manager.reconcile_llm_aois(llm, grounding)

        self.assertEqual(len(result), 2)
        self.assertEqual([aoi.anchor_ids for aoi in result], [["a"], ["b"]])
        self.assertEqual([aoi.role for aoi in result], ["list_item", "list_item"])

    def test_visual_aoi_keeps_valid_model_bbox(self) -> None:
        visual = AOI("visual", [0.55, 0.25, 0.90, 0.70], "figure", "Illustration", source="llm_guided")

        result = self.manager.reconcile_llm_aois([visual], [])

        self.assertEqual(result[0].bbox, [0.55, 0.25, 0.90, 0.70])
        self.assertEqual(result[0].type, "figure")

    def test_reconciliation_links_visual_item_to_final_visual_aoi(self) -> None:
        aois = self.manager.reconcile_llm_aois([
            AOI("model", [0.2, 0.3, 0.7, 0.45], "formula", "", source="llm_guided"),
        ], [])
        items = self.manager._link_visual_context((VisualContextItem(
            visual_id="visual_1",
            type="formula",
            bbox=[0.2, 0.3, 0.7, 0.45],
            description="A formula.",
        ),), aois)

        self.assertEqual(aois[0].aoi_id, "llm_aoi_1")
        self.assertEqual(items[0].linked_aoi_id, "llm_aoi_1")

    def test_unmatched_visual_item_remains_without_linked_aoi(self) -> None:
        aois = self.manager.reconcile_llm_aois([
            AOI("model", [0.7, 0.7, 0.9, 0.9], "figure", "", source="llm_guided"),
        ], [])
        items = self.manager._link_visual_context((VisualContextItem(
            visual_id="visual_1",
            type="formula",
            bbox=[0.1, 0.1, 0.4, 0.2],
            description="A formula.",
        ),), aois)

        self.assertIsNone(items[0].linked_aoi_id)

    def test_visual_aoi_candidates_are_deduplicated_and_capped_at_eight(self) -> None:
        candidates = [
            AOI(
                f"visual_{index}",
                [0.03 + (index % 5) * 0.19, 0.05 + (index // 5) * 0.3,
                 0.15 + (index % 5) * 0.19, 0.18 + (index // 5) * 0.3],
                "figure",
                "",
                source="llm_guided",
                group_confidence=0.99 - index * 0.01,
            )
            for index in range(10)
        ]
        candidates.append(AOI(
            "duplicate",
            list(candidates[0].bbox),
            "diagram",
            "",
            source="llm_guided",
            group_confidence=0.5,
        ))

        result = self.manager.reconcile_llm_aois(candidates, [])

        self.assertEqual(len(result), 8)
        for index, first in enumerate(result):
            for second in result[index + 1:]:
                self.assertLess(self.manager._bbox_iou(first.bbox, second.bbox), 0.85)

    def test_anchored_title_type_is_canonicalized_to_text(self) -> None:
        grounding = [grounding_anchor("a", "Body paragraph", [0.10, 0.20, 0.70, 0.30])]
        model = AOI("model", [], "title", "Misclassified", source="llm_guided", anchor_ids=["a"])

        result = self.manager.reconcile_llm_aois([model], grounding)

        self.assertEqual(result[0].type, "text")
        self.assertEqual(result[0].role, "paragraph")
        self.assertEqual(result[0].text, "Body paragraph")

    def test_mixed_visual_is_not_deduplicated_as_text(self) -> None:
        grounding = [grounding_anchor("a", "Body paragraph", [0.10, 0.20, 0.70, 0.30])]
        candidates = [
            AOI("text", [], "text", "Body", source="llm_guided", anchor_ids=["a"]),
            AOI("mixed", [0.10, 0.20, 0.70, 0.30], "mixed", "Panel", source="llm_guided"),
        ]

        result = self.manager.reconcile_llm_aois(candidates, grounding)

        self.assertEqual(len(result), 2)
        self.assertEqual({aoi.type for aoi in result}, {"text", "mixed"})

    def test_low_grounding_coverage_still_falls_back(self) -> None:
        grounding = [
            grounding_anchor("a", "one two three four", [0.10, 0.10, 0.70, 0.20]),
            grounding_anchor("b", "five six seven eight nine ten", [0.10, 0.40, 0.70, 0.50], block_id=2),
        ]
        llm = AOI("partial", [], "text", "Partial", source="llm_guided", anchor_ids=["a"])

        with self.assertRaisesRegex(ValueError, "coverage too low"):
            self.manager.reconcile_llm_aois([llm], grounding, minimum_text_coverage=0.75)


if __name__ == "__main__":
    unittest.main()
