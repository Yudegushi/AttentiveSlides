from __future__ import annotations

import unittest

from modules.attention.gaze_heatmap import (
    AOIDwellSnapshot,
    GazeReviewSession,
    SlideHeatmapSnapshot,
)
from modules.learner_state import EMOTION_LABELS
from modules.review import (
    LearnerStateReviewSummary,
    SlideLearnerStateSummary,
    StudyReviewSession,
)
from modules.ui.review_view import UNAVAILABLE, build_review_view


def learner_slide(
    slide_id: int,
    *,
    study: float,
    observed: float,
    engagement_observed: float,
    fatigue_observed: float,
    emotion_observed: float,
    engagement: float | None,
    fatigue: float | None,
    emotions: tuple[float, ...] = (),
    top: str | None = None,
    interactions: int = 0,
    distraction_seconds: float = 0.0,
    distraction_count: int = 0,
    fatigue_alert_seconds: float = 0.0,
    fatigue_alert_count: int = 0,
) -> SlideLearnerStateSummary:
    top_probability = (
        emotions[EMOTION_LABELS.index(top)]
        if top is not None else None
    )
    return SlideLearnerStateSummary(
        slide_id=slide_id,
        study_seconds=study,
        observed_seconds=observed,
        emotion_observed_seconds=emotion_observed,
        engagement_observed_seconds=engagement_observed,
        fatigue_observed_seconds=fatigue_observed,
        interaction_count=interactions,
        mean_engaged_probability=engagement,
        mean_fatigue_probability=fatigue,
        emotion_probabilities=emotions,
        top_emotion=top,
        top_emotion_probability=top_probability,
        distraction_alert_seconds=distraction_seconds,
        distraction_alert_count=distraction_count,
        fatigue_alert_seconds=fatigue_alert_seconds,
        fatigue_alert_count=fatigue_alert_count,
    )


def gaze_slide(
    slide_id: int,
    *,
    observed: float,
    valid: float,
    dwell: float = 0.0,
) -> SlideHeatmapSnapshot:
    return SlideHeatmapSnapshot(
        deck_id="deck-a",
        slide_id=slide_id,
        grid_width=1,
        grid_height=1,
        grid=(valid,),
        observed_seconds=observed,
        valid_gaze_seconds=valid,
        aoi_dwell=(
            AOIDwellSnapshot("aoi-1", "Definition", (0.1, 0.1, 0.5, 0.5), dwell),
        ) if dwell else (),
    )


def review_session(
    learner_slides: tuple[SlideLearnerStateSummary, ...],
    gaze_slides: tuple[SlideHeatmapSnapshot, ...],
    *,
    paused: float = 0.0,
) -> StudyReviewSession:
    gaze = GazeReviewSession(
        schema_version=1,
        session_id="review-1",
        deck_id="deck-a",
        started_at_epoch=100.0,
        ended_at_epoch=130.0,
        slides=gaze_slides,
    )
    return StudyReviewSession(
        schema_version=1,
        session_id="review-1",
        deck_id="deck-a",
        started_at_epoch=100.0,
        ended_at_epoch=130.0,
        gaze_review=gaze,
        learner_state_summary=LearnerStateReviewSummary(learner_slides),
        paused_seconds=paused,
    )


class ReviewViewTests(unittest.TestCase):
    def setUp(self) -> None:
        neutral = (0.05, 0.05, 0.05, 0.05, 0.10, 0.60, 0.05, 0.05)
        happy = (0.05, 0.05, 0.05, 0.05, 0.50, 0.20, 0.05, 0.05)
        self.review = review_session(
            (
                learner_slide(
                    2, study=20.0, observed=10.0,
                    engagement_observed=5.0, fatigue_observed=5.0,
                    emotion_observed=5.0, engagement=0.50, fatigue=0.40,
                    emotions=happy, top="Happiness", interactions=1,
                    distraction_seconds=2.0, distraction_count=2,
                    fatigue_alert_seconds=1.0, fatigue_alert_count=1,
                ),
                learner_slide(
                    1, study=10.0, observed=5.0,
                    engagement_observed=4.0, fatigue_observed=2.0,
                    emotion_observed=5.0, engagement=0.75, fatigue=0.20,
                    emotions=neutral, top="Neutral", interactions=2,
                    distraction_seconds=1.0, distraction_count=1,
                    fatigue_alert_seconds=0.5, fatigue_alert_count=1,
                ),
            ),
            (
                gaze_slide(3, observed=2.0, valid=1.0),
                gaze_slide(1, observed=8.0, valid=4.0, dwell=2.5),
            ),
        )

    def test_session_summary_uses_weighted_stored_values(self) -> None:
        view = build_review_view(self.review)
        summary = {metric.label: metric.value for metric in view.summary}
        self.assertEqual(summary["Study duration"], "00:30")
        self.assertEqual(summary["Interactions"], "3")
        self.assertEqual(summary["Mean engagement"], "61%")
        self.assertEqual(summary["Mean fatigue"], "34%")
        self.assertEqual(summary["Learner coverage"], "50%")
        self.assertIn("·", summary["Top emotion"])

    def test_session_summary_and_coverage_exclude_paused_time(self) -> None:
        paused_review = review_session(
            self.review.learner_state_summary.slides,
            self.review.gaze_review.slides,
            paused=10.0,
        )
        summary = {
            metric.label: metric.value
            for metric in build_review_view(paused_review).summary
        }

        self.assertEqual(paused_review.active_seconds, 20.0)
        self.assertEqual(summary["Study duration"], "00:20")
        self.assertEqual(summary["Learner coverage"], "75%")

    def test_all_eight_emotions_keep_official_order_and_values(self) -> None:
        view = build_review_view(self.review)
        self.assertEqual(
            tuple(metric.label for metric in view.emotion_distribution),
            EMOTION_LABELS,
        )
        self.assertEqual(len(view.emotion_distribution), 8)
        self.assertEqual(
            tuple(metric.value for metric in view.emotion_distribution),
            ("5%", "5%", "5%", "5%", "30%", "40%", "5%", "5%"),
        )

    def test_alert_duration_and_count_are_exposed(self) -> None:
        view = build_review_view(self.review)
        alerts = {metric.label: metric.value for metric in view.alert_summary}
        self.assertEqual(alerts["Distraction alert duration"], "3.0 s")
        self.assertEqual(alerts["Distraction alert count"], "3")
        self.assertEqual(alerts["Fatigue alert duration"], "1.5 s")
        self.assertEqual(alerts["Fatigue alert count"], "2")

    def test_slide_details_join_learner_and_gaze_by_id_and_sort(self) -> None:
        view = build_review_view(self.review)
        self.assertEqual([row.slide_id for row in view.slide_rows], [1, 2, 3])
        first = view.slide_details[1]
        self.assertEqual(first.study_time, "00:10")
        self.assertEqual(first.interaction_count, 2)
        self.assertEqual(first.engagement, "75%")
        self.assertEqual(first.fatigue, "20%")
        self.assertEqual(first.top_emotion_label, "Neutral")
        self.assertEqual(first.top_emotion_probability, "60%")
        self.assertEqual(first.distraction_alert_duration, "1.0 s")
        self.assertEqual(first.distraction_alert_count, 1)
        self.assertEqual(first.fatigue_alert_duration, "0.5 s")
        self.assertEqual(first.fatigue_alert_count, 1)
        self.assertEqual(first.learner_coverage, "50%")
        self.assertEqual(first.valid_gaze_duration, "4.0 s")
        self.assertEqual(first.gaze_coverage, "50%")
        self.assertEqual(first.aoi_dwell[0].dwell_seconds, "2.5 s")
        self.assertEqual(first.aoi_dwell[1].label, "Other slide area")
        self.assertEqual(view.slide_details[2].gaze_coverage, UNAVAILABLE)
        self.assertEqual(view.slide_details[3].engagement, UNAVAILABLE)

    def test_zero_modality_coverage_never_invents_probability_values(self) -> None:
        empty = learner_slide(
            1, study=10.0, observed=0.0,
            engagement_observed=0.0, fatigue_observed=0.0,
            emotion_observed=0.0, engagement=None, fatigue=None,
        )
        view = build_review_view(review_session(
            (empty,),
            (gaze_slide(1, observed=0.0, valid=0.0),),
        ))
        summary = {metric.label: metric.value for metric in view.summary}
        self.assertEqual(summary["Mean engagement"], UNAVAILABLE)
        self.assertEqual(summary["Mean fatigue"], UNAVAILABLE)
        self.assertEqual(summary["Top emotion"], UNAVAILABLE)
        self.assertEqual(summary["Learner coverage"], UNAVAILABLE)
        self.assertTrue(all(
            metric.value == UNAVAILABLE
            for metric in view.emotion_distribution
        ))
        detail = view.slide_details[1]
        self.assertEqual(detail.valid_gaze_duration, UNAVAILABLE)
        self.assertEqual(detail.gaze_coverage, UNAVAILABLE)
        self.assertIsNone(detail.distraction_alert_count)
        self.assertIsNone(detail.fatigue_alert_count)
        self.assertEqual(detail.learner_coverage, UNAVAILABLE)

    def test_legacy_gaze_only_review_keeps_session_time_and_marks_learner_data_missing(self) -> None:
        view = build_review_view(review_session(
            (),
            (gaze_slide(3, observed=10.0, valid=5.0),),
        ))
        summary = {metric.label: metric.value for metric in view.summary}

        self.assertEqual(summary["Study duration"], "00:30")
        self.assertEqual(summary["Interactions"], UNAVAILABLE)
        self.assertEqual(summary["Learner coverage"], UNAVAILABLE)
        self.assertIsNone(view.slide_rows[0].interaction_count)
        self.assertIsNone(view.slide_details[3].interaction_count)


if __name__ == "__main__":
    unittest.main()
