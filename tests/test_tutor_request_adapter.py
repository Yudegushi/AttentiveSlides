"""Tests for TutorContext to TutorLLMRequest adaptation."""

from __future__ import annotations

import unittest

from modules.common.schemas import (
    AOI,
    ResolvedQuery,
    TutorContext,
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
