import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from modules.attention.gaze_heatmap import GazeHeatmapAccumulator
from modules.fatigue import FatigueSnapshot
from modules.learner_state import (
    EmotionSnapshot,
    EngagementSnapshot,
    LearnerStateSnapshot,
)
from modules.review import StudyReviewSession, StudyReviewStore
from tests.test_gaze_heatmap import AOIS, make_sample


class MutableClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def state_snapshot(
    now,
    *,
    emotion=True,
    engagement=True,
    fatigue=True,
    distracted=0.25,
    fatigued=0.2,
    distraction_alert=False,
    fatigue_alert=False,
):
    probabilities = (0.05, 0.05, 0.05, 0.05, 0.1, 0.6, 0.05, 0.05)
    emotion_state = (
        EmotionSnapshot(
            status="ready",
            probabilities=probabilities,
            top_label="Neutral",
            top_probability=0.6,
            updated_at=now,
        )
        if emotion
        else EmotionSnapshot(status="unavailable", updated_at=now, error="missing")
    )
    engagement_state = (
        EngagementSnapshot(
            status="ready",
            distracted_probability=distracted,
            engaged_probability=1.0 - distracted,
            alert_active=distraction_alert,
            buffered_frames=128,
            updated_at=now,
        )
        if engagement
        else EngagementSnapshot(status="warming", buffered_frames=4, updated_at=now)
    )
    fatigue_state = (
        FatigueSnapshot(
            status="ready",
            raw_probability=fatigued,
            smoothed_probability=fatigued,
            alert_active=fatigue_alert,
            updated_at=now,
        )
        if fatigue
        else FatigueSnapshot(status="unavailable", updated_at=now, error="missing")
    )
    return LearnerStateSnapshot(
        emotion=emotion_state,
        engagement=engagement_state,
        fatigue=fatigue_state,
        updated_at=now,
    )


class StudyReviewStoreTest(unittest.TestCase):
    def make_store(self, root, ids=("review-1", "review-2", "review-3"), legacy=None):
        self.monotonic = MutableClock(0.0)
        self.wall = MutableClock(100.0)
        id_values = iter(ids)
        return StudyReviewStore(
            Path(root) / "study_reviews",
            legacy_gaze_path=legacy,
            monotonic_clock=self.monotonic,
            wall_clock=self.wall,
            id_factory=lambda: next(id_values),
        )

    def activate_with_state(self, store, now=0.0, slide_id=1):
        self.monotonic.value = now
        store.set_context("deck-a", slide_id, received_at=now)
        return store.accept_learner_state(
            "deck-a", slide_id, state_snapshot(now), now
        )

    def test_each_meaningful_start_path_activates_one_shared_session(self):
        with TemporaryDirectory() as root:
            state_store = self.make_store(Path(root) / "state")
            self.assertTrue(self.activate_with_state(state_store))
            self.assertEqual(state_store.active_deck_id(), "deck-a")

            gaze_store = self.make_store(Path(root) / "gaze")
            gaze_store.register_slide("deck-a", 1, AOIS)
            self.assertTrue(gaze_store.accept_gaze(make_sample(received_at=0.0)))
            self.assertEqual(gaze_store.active_deck_id(), "deck-a")

            interaction_store = self.make_store(Path(root) / "interaction")
            interaction_store.set_context("deck-a", 1, received_at=0.0)
            self.assertTrue(
                interaction_store.record_completed_interaction("turn-1", "deck-a", 1)
            )
            self.assertEqual(interaction_store.active_deck_id(), "deck-a")

    def test_gaze_and_learner_state_finish_under_one_identity(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.register_slide("deck-a", 1, AOIS)
            store.set_context("deck-a", 1, received_at=0.0)
            store.accept_gaze(make_sample(received_at=0.0))
            store.accept_learner_state("deck-a", 1, state_snapshot(0.0), 0.0)
            store.accept_gaze(make_sample(received_at=0.2))
            self.monotonic.value = 1.0
            self.wall.value = 101.0

            session = store.finish(deck_id="deck-a")

            self.assertEqual(session.session_id, session.gaze_review.session_id)
            self.assertEqual(session.deck_id, session.gaze_review.deck_id)
            self.assertEqual(session.started_at_epoch, session.gaze_review.started_at_epoch)
            self.assertEqual(session.ended_at_epoch, session.gaze_review.ended_at_epoch)

    def test_study_time_follows_context_even_when_models_are_unavailable(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            self.activate_with_state(store, now=0.0, slide_id=1)
            store.set_context("deck-a", 2, received_at=2.0)
            store.accept_learner_state(
                "deck-a",
                2,
                state_snapshot(2.0, emotion=False, engagement=False, fatigue=False),
                2.0,
            )
            self.monotonic.value = 5.0
            self.wall.value = 105.0

            session = store.finish(deck_id="deck-a")
            slides = {slide.slide_id: slide for slide in session.learner_state_summary.slides}

            self.assertEqual(slides[1].study_seconds, 2.0)
            self.assertEqual(slides[2].study_seconds, 3.0)
            self.assertEqual(slides[2].observed_seconds, 0.0)

    def test_state_intervals_are_capped_and_modalities_have_independent_denominators(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.set_context("deck-a", 1, received_at=0.0)
            store.accept_learner_state(
                "deck-a", 1, state_snapshot(0.0, engagement=False, fatigue=False), 0.0
            )
            store.accept_learner_state(
                "deck-a", 1, state_snapshot(10.0, emotion=False, fatigue=False), 10.0
            )
            store.accept_learner_state(
                "deck-a", 1, state_snapshot(11.0, emotion=False, engagement=False), 11.0
            )
            self.monotonic.value = 12.0
            self.wall.value = 112.0

            slide = store.finish(deck_id="deck-a").learner_state_summary.slides[0]

            self.assertEqual(slide.observed_seconds, 3.0)
            self.assertEqual(slide.emotion_observed_seconds, 1.0)
            self.assertEqual(slide.engagement_observed_seconds, 1.0)
            self.assertEqual(slide.fatigue_observed_seconds, 1.0)
            self.assertAlmostEqual(slide.mean_engaged_probability, 0.75)
            self.assertAlmostEqual(slide.mean_fatigue_probability, 0.2)
            self.assertEqual(slide.top_emotion, "Neutral")

    def test_late_worker_callback_for_old_context_is_rejected(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            self.activate_with_state(store, now=0.0, slide_id=1)
            store.set_context("deck-a", 2, received_at=0.5)

            accepted = store.accept_learner_state(
                "deck-a", 1, state_snapshot(0.75), 0.75
            )

            self.assertFalse(accepted)
            self.assertEqual(store.active_slide_summary("deck-a", 2, now=1.0).observed_seconds, 0.0)

    def test_alert_entry_counts_are_distinct_from_weighted_duration(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.set_context("deck-a", 1, received_at=0.0)
            active = state_snapshot(
                0.0, distraction_alert=True, fatigue_alert=True, distracted=0.8, fatigued=0.9
            )
            inactive = state_snapshot(1.0)
            store.accept_learner_state("deck-a", 1, active, 0.0)
            store.accept_learner_state("deck-a", 1, active, 0.5)
            store.accept_learner_state("deck-a", 1, inactive, 1.0)
            self.monotonic.value = 1.5
            self.wall.value = 101.5

            slide = store.finish(deck_id="deck-a").learner_state_summary.slides[0]

            self.assertEqual(slide.distraction_alert_count, 1)
            self.assertEqual(slide.fatigue_alert_count, 1)
            self.assertEqual(slide.distraction_alert_seconds, 1.0)
            self.assertEqual(slide.fatigue_alert_seconds, 1.0)

    def test_completed_interactions_deduplicate_by_existing_id(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.set_context("deck-a", 1, received_at=0.0)

            self.assertTrue(store.record_completed_interaction("turn-1", "deck-a", 1))
            self.assertFalse(store.record_completed_interaction("turn-1", "deck-a", 1))
            self.assertTrue(store.record_completed_interaction("turn-2", "deck-a", 1))
            self.monotonic.value = 1.0
            self.wall.value = 101.0
            slide = store.finish(deck_id="deck-a").learner_state_summary.slides[0]

            self.assertEqual(slide.interaction_count, 2)

    def test_two_finishes_are_immutable_newest_first_and_start_new_preserves_history(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            first = store.finish(deck_id="deck-a")
            with self.assertRaisesRegex(RuntimeError, "Start a new study"):
                store.finish(deck_id="deck-a")
            store.start_new()
            self.wall.value = 102.0
            second = store.finish(deck_id="deck-a")

            self.assertEqual([item.session_id for item in store.list_sessions()], [second.session_id, first.session_id])
            self.assertTrue((Path(root) / "study_reviews" / "sessions" / f"{first.session_id}.json").is_file())
            self.assertTrue((Path(root) / "study_reviews" / "sessions" / f"{second.session_id}.json").is_file())

    def test_delete_removes_only_selected_canonical_session(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            first = store.finish(deck_id="deck-a")
            store.start_new()
            self.wall.value = 102.0
            second = store.finish(deck_id="deck-a")

            store.delete(second.session_id)

            self.assertIsNone(store.get(second.session_id))
            self.assertEqual(store.latest().session_id, first.session_id)
            self.assertFalse(store.is_armed())

    def test_corrupt_and_filename_mismatched_sessions_are_skipped(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            valid = store.finish(deck_id="deck-a")
            sessions = Path(root) / "study_reviews" / "sessions"
            (sessions / "broken.json").write_text("not-json", encoding="utf-8")
            (sessions / "wrong-name.json").write_text(valid.to_json(), encoding="utf-8")

            reloaded = self.make_store(root, ids=("unused",))

            self.assertEqual([item.session_id for item in reloaded.list_sessions()], [valid.session_id])
            self.assertEqual(len(reloaded.load_warnings()), 2)

    def test_ui_ids_never_become_paths(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            session = store.finish(deck_id="deck-a")

            self.assertIsNone(store.get("../../outside"))
            with self.assertRaises(KeyError):
                store.delete("../../outside")
            self.assertIsNotNone(store.get(session.session_id))

    def test_canonical_finish_failure_retries_same_frozen_record(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            self.activate_with_state(store)
            original_write = store._write_canonical
            with patch.object(store, "_write_canonical", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    store.finish(deck_id="deck-a")
            pending = store._pending_finish
            with self.assertRaisesRegex(RuntimeError, "frozen Study Review"):
                store.start_new()
            self.assertIs(store._pending_finish, pending)
            self.monotonic.value = 99.0
            self.wall.value = 999.0
            with patch.object(store, "_write_canonical", wraps=original_write):
                completed = store.finish(deck_id="deck-a")

            self.assertEqual(completed.session_id, pending.session_id)
            self.assertEqual(completed.started_at_epoch, pending.started_at_epoch)
            self.assertEqual(completed.ended_at_epoch, pending.ended_at_epoch)
            self.assertEqual(len(store.list_sessions()), 1)

    def test_latest_cache_failure_cannot_undo_finish_or_resurrect_delete(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            with patch.object(store, "_refresh_latest_cache", side_effect=OSError("cache")):
                session = store.finish(deck_id="deck-a")
            canonical = Path(root) / "study_reviews" / "sessions" / f"{session.session_id}.json"
            self.assertTrue(canonical.is_file())
            self.assertEqual(store.latest().session_id, session.session_id)
            self.assertTrue(any("cache refresh failed" in item for item in store.load_warnings()))

            with patch.object(store, "_refresh_latest_cache", side_effect=OSError("cache")):
                store.delete(session.session_id)
            reloaded = self.make_store(root, ids=("unused",))
            self.assertEqual(reloaded.list_sessions(), ())

    def test_canonical_delete_failure_leaves_history_intact(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            session = store.finish(deck_id="deck-a")
            with patch.object(store, "_unlink_and_fsync", side_effect=OSError("read only")):
                with self.assertRaisesRegex(OSError, "read only"):
                    store.delete(session.session_id)

            self.assertIsNotNone(store.get(session.session_id))

    def test_legacy_gaze_review_migrates_before_new_finish(self):
        with TemporaryDirectory() as root:
            legacy_path = Path(root) / "gaze_reviews" / "latest.json"
            legacy_path.parent.mkdir(parents=True)
            accumulator = GazeHeatmapAccumulator(
                session_id="legacy-1", deck_id="deck-a", started_at_epoch=90.0
            )
            legacy = accumulator.finish(ended_received_at=0.0, ended_at_epoch=91.0)
            legacy_path.write_text(legacy.to_json(), encoding="utf-8")
            store = self.make_store(root, legacy=legacy_path)
            self.assertEqual(store.latest().session_id, "legacy-1")
            self.assertEqual(store.latest().learner_state_summary.slides, ())

            store.start_new()
            self.wall.value = 101.0
            current = store.finish(deck_id="deck-a")

            sessions = Path(root) / "study_reviews" / "sessions"
            self.assertTrue((sessions / "legacy-1.json").is_file())
            self.assertTrue((sessions / f"{current.session_id}.json").is_file())
            self.assertTrue(legacy_path.is_file())

    def test_explicit_delete_of_legacy_source_prevents_restart_reappearance(self):
        with TemporaryDirectory() as root:
            legacy_path = Path(root) / "gaze_reviews" / "latest.json"
            legacy_path.parent.mkdir(parents=True)
            accumulator = GazeHeatmapAccumulator(
                session_id="legacy-1", deck_id="deck-a", started_at_epoch=90.0
            )
            legacy = accumulator.finish(ended_received_at=0.0, ended_at_epoch=91.0)
            legacy_path.write_text(legacy.to_json(), encoding="utf-8")
            store = self.make_store(root, legacy=legacy_path)

            store.delete("legacy-1")
            reloaded = self.make_store(root, legacy=legacy_path)

            self.assertFalse(legacy_path.exists())
            self.assertEqual(reloaded.list_sessions(), ())

    def test_round_trip_contains_aggregates_but_no_raw_biometric_fields(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            self.activate_with_state(store)
            self.monotonic.value = 1.0
            self.wall.value = 101.0
            session = store.finish(deck_id="deck-a")
            payload = session.to_dict()
            restored = StudyReviewSession.from_dict(payload)
            serialized = json.dumps(payload).lower()

            self.assertEqual(restored.to_dict(), payload)
            for forbidden in (
                "face_crop",
                "image",
                "feature_vector",
                "frame_history",
                "audio",
                "transcript",
                "raw_gaze",
            ):
                self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
