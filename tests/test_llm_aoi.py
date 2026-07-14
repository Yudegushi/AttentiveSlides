from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from modules.slide.aoi_manager import AOI, AOIManager, SlideAOIData
from modules.slide.llm_aoi import LLMAOIGenerator


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01"
    b"\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeLLMGenerator:
    def __init__(self, *, result=None, error=None, profile="profile-a"):
        self.result = result or []
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
        return list(self.result)


def llm_item(text="alpha beta gamma delta", *, aoi_type="text", bbox=None):
    return {
        "aoi_id": "anything",
        "bbox": bbox or [0.1, 0.2, 0.8, 0.4],
        "type": aoi_type,
        "text": text,
        "source": "llm_guided",
        "group_confidence": 0.9,
        "include_in_learning": True,
    }


class LLMAOIGeneratorValidationTest(unittest.TestCase):
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
                "pdf_semantic_block_1",
                [0.1, 0.2, 0.8, 0.4],
                "text",
                "alpha beta gamma delta epsilon zeta eta theta",
                source="pdf_text_semantic",
                children=[{"text": "alpha", "bbox": [0.1, 0.2, 0.2, 0.3]}],
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
        grounding = [AOI("a", [0.1, 0.1, 0.4, 0.2], "text", "one two three four five six seven eight", source="pdf_text_semantic")]
        with self.assertRaisesRegex(ValueError, "coverage"):
            manager.reconcile_llm_aois([AOI("x", [0.2, 0.2, 0.5, 0.5], "text", "unrelated", source="llm_guided")], grounding)
        visual = manager.reconcile_llm_aois(
            [AOI("x", [0.2, 0.2, 0.5, 0.5], "diagram", "flow", source="llm_guided")],
            [AOI("a", [0.1, 0.1, 0.4, 0.2], "text", "few anchors", source="pdf_text_semantic")],
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

    def test_generator_receives_only_flat_stable_anchor_fields(self):
        generator = FakeLLMGenerator(result=[llm_item("alpha beta gamma delta epsilon zeta eta theta")])
        manager = self.seeded_manager(generator)
        manager.process_llm_aoi("deck", 1, allow_ocr=False)
        self.assertIsNotNone(generator.last_text_aois)
        self.assertEqual(
            set(generator.last_text_aois[0]),
            {"aoi_id", "bbox", "type", "text", "source"},
        )
        self.assertNotIn("children", generator.last_text_aois[0])

    def test_timeout_and_malformed_output_fall_back_without_touching_aois(self):
        for generator in (
            FakeLLMGenerator(error=TimeoutError("  temporary   timeout  ")),
            FakeLLMGenerator(result=[llm_item(bbox=[0.8, 0.2, 0.1, 0.4])]),
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


if __name__ == "__main__":
    unittest.main()
