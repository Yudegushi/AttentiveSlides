"""Tests for TutorContext to TutorLLMRequest adaptation."""

from __future__ import annotations

import unittest
from dataclasses import replace

from modules.common.schemas import (
    AOI,
    ResolvedQuery,
    TutorContext,
    VisualContextItem,
)
from modules.tutor.tutor_request_adapter import (
    TutorRequestAdapter,
)


def make_context(
    *,
    needs_confirmation: bool = False,
) -> TutorContext:
    aoi = AOI(
        aoi_id="aoi_fixation",
        bbox=[0.1, 0.1, 0.4, 0.3],
        type="text",
        text=(
            "Fixation is maintaining gaze "
            "on a single location."
        ),
        name="Fixation",
    )

    resolved = ResolvedQuery(
        query_id="query_adapter_001",
        deck_id="lecture_2",
        slide_id=2,
        transcript=(
            "fixation 和 saccade 有什么区别？"
        ),
        intent="compare",
        resolved_aoi_id="aoi_fixation",
        target_confidence=0.88,
        needs_confirmation=needs_confirmation,
        confirmation_mode=(
            "confirm_one"
            if needs_confirmation
            else "none"
        ),
        adaptive_strategy="normal",
    )

    return TutorContext(
        deck_id="lecture_2",
        slide_id=2,
        current_slide_text=(
            "Fixation maintains gaze on one location. "
            "Saccade is rapid movement between fixations."
        ),
        current_aoi=aoi,
        current_aoi_text=aoi.text,
        neighbor_slide_text=(
            "The next slide discusses gaze calibration."
        ),
        resolved_query=resolved,
        adaptive_strategy="normal",
    )


class TestTutorRequestAdapter(unittest.TestCase):
    def test_external_knowledge_is_allowed_by_default(self) -> None:
        request = TutorRequestAdapter().from_context(
            make_context()
        )

        self.assertTrue(
            request.allow_external_knowledge
        )

    def test_confirmed_aoi_is_preserved(self) -> None:
        request = TutorRequestAdapter().from_context(
            make_context()
        )

        self.assertEqual(
            request.confirmed_aoi_id,
            "aoi_fixation",
        )

        confirmed_sources = [
            source
            for source in request.sources
            if source.source_kind
            == "confirmed_aoi"
        ]

        self.assertEqual(
            len(confirmed_sources),
            1,
        )

        self.assertEqual(
            confirmed_sources[0].source_id,
            "slide_002_aoi_fixation",
        )

    def test_unconfirmed_aoi_is_not_marked_confirmed(
        self,
    ) -> None:
        request = TutorRequestAdapter().from_context(
            make_context(
                needs_confirmation=True
            )
        )

        self.assertIsNone(
            request.confirmed_aoi_id
        )

        self.assertFalse(
            any(
                source.source_kind
                == "confirmed_aoi"
                for source in request.sources
            )
        )

    def test_slide_and_neighbor_sources_are_created(
        self,
    ) -> None:
        request = TutorRequestAdapter().from_context(
            make_context()
        )

        self.assertIn(
            "slide_002_full_text",
            request.source_ids(),
        )

        self.assertIn(
            "slide_002_neighbor_context",
            request.source_ids(),
        )

    def test_visual_observation_source_contains_description_transcription_and_provenance(self) -> None:
        visual = VisualContextItem(
            visual_id="visual_1",
            type="formula",
            bbox=[0.2, 0.3, 0.7, 0.45],
            description="A conditional-probability formula.",
            transcription="p(y | x)",
            confidence=0.91,
            linked_aoi_id="aoi_fixation",
        )
        request = TutorRequestAdapter().from_context(replace(
            make_context(),
            slide_id=7,
            visual_context=[visual],
        ))
        source = next(
            item for item in request.sources
            if item.source_kind == "visual_observation"
        )

        self.assertEqual(source.source_id, "slide_007_visual_01")
        self.assertIn("Description: A conditional-probability formula.", source.text)
        self.assertIn("Visible transcription: p(y | x)", source.text)
        self.assertEqual(source.aoi_id, "aoi_fixation")
        self.assertEqual(source.metadata, {
            "visual_type": "formula",
            "bbox": [0.2, 0.3, 0.7, 0.45],
            "confidence": 0.91,
            "provenance": "llm_visual_analysis",
        })

    def test_unlinked_visual_observation_has_no_aoi_id(self) -> None:
        visual = VisualContextItem(
            visual_id="visual_1",
            type="chart",
            bbox=[0.2, 0.3, 0.7, 0.6],
            description="A bar chart.",
        )
        request = TutorRequestAdapter().from_context(replace(
            make_context(),
            visual_context=[visual],
        ))
        source = next(
            item for item in request.sources
            if item.source_kind == "visual_observation"
        )

        self.assertIsNone(source.aoi_id)

    def test_visual_observation_source_id_is_stable(self) -> None:
        visual = VisualContextItem(
            visual_id="visual_1",
            type="diagram",
            bbox=[0.2, 0.3, 0.7, 0.6],
            description="A flow diagram.",
        )
        context = replace(
            make_context(),
            slide_id=7,
            visual_context=[visual],
        )

        first = TutorRequestAdapter().from_context(context)
        second = TutorRequestAdapter().from_context(context)

        self.assertIn("slide_007_visual_01", first.source_ids())
        self.assertEqual(first.source_ids(), second.source_ids())

    def test_existing_text_only_context_still_builds_the_same_source_set(self) -> None:
        request = TutorRequestAdapter().from_context(make_context())

        self.assertEqual(
            {source.source_kind for source in request.sources},
            {"confirmed_aoi", "current_slide", "neighbor_slide"},
        )
        self.assertFalse(any(
            source.source_kind == "visual_observation"
            for source in request.sources
        ))

    def test_response_mode_uses_existing_policy(
        self,
    ) -> None:
        request = TutorRequestAdapter().from_context(
            make_context()
        )

        self.assertEqual(
            request.response_mode,
            "compare",
        )


if __name__ == "__main__":
    unittest.main()
