from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from modules.attention.gaze_review_store import GazeReviewStore
from tests.test_gaze_heatmap import AOIS, make_sample


def make_deck_sample(deck_id, **kwargs):
    sample = make_sample(**kwargs)
    geometry_snapshot = sample.geometry
    assert geometry_snapshot is not None
    geometry = replace(geometry_snapshot.geometry, deck_id=deck_id)
    return replace(
        sample,
        geometry=replace(geometry_snapshot, geometry=geometry),
    )


class SequenceClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class GazeReviewStoreTest(unittest.TestCase):
    def make_store(self, root):
        self.monotonic = SequenceClock(1.0)
        self.wall = SequenceClock(100.0)
        return GazeReviewStore(
            Path(root) / "gaze_reviews" / "latest.json",
            monotonic_clock=self.monotonic,
            wall_clock=self.wall,
            id_factory=lambda: "review-1",
        )

    def test_first_valid_point_starts_session_and_finish_persists(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.register_slide("deck-a", 1, AOIS)
            self.assertFalse(store.accept(make_sample(received_at=1.0, valid=False)))
            self.assertFalse(store.has_active())
            self.assertTrue(store.accept(make_sample(received_at=1.2)))
            self.assertTrue(store.has_active())
            store.accept(make_sample(received_at=1.4))
            self.monotonic.value = 1.4
            self.wall.value = 101.0

            review = store.finish(deck_id="deck-a")
            reloaded = self.make_store(root)

            self.assertEqual(review.session_id, "review-1")
            self.assertEqual(reloaded.latest().to_dict(), review.to_dict())
            self.assertFalse(reloaded.is_armed())

    def test_pause_prevents_transport_gap_from_becoming_dwell(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.register_slide("deck-a", 1, AOIS)
            store.accept(make_sample(received_at=1.0))
            store.pause()
            store.accept(make_sample(received_at=9.0))
            store.accept(make_sample(received_at=9.2))
            self.monotonic.value = 9.2

            review = store.finish(deck_id="deck-a")

            self.assertAlmostEqual(review.slides[0].valid_gaze_seconds, 0.2)

    def test_finish_without_valid_gaze_creates_empty_review(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)

            review = store.finish(deck_id="deck-a")

            self.assertEqual(review.deck_id, "deck-a")
            self.assertEqual(review.slides, ())

    def test_start_new_clears_latest_and_arms_collection(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.finish(deck_id="deck-a")

            store.start_new()

            self.assertIsNone(store.latest())
            self.assertTrue(store.is_armed())
            self.assertFalse((Path(root) / "gaze_reviews" / "latest.json").exists())

    def test_malformed_latest_is_reported_without_crashing(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "gaze_reviews" / "latest.json"
            path.parent.mkdir(parents=True)
            path.write_text("not-json", encoding="utf-8")

            store = self.make_store(root)

            self.assertIsNone(store.latest())
            self.assertIn("JSON", store.load_error())
            self.assertFalse(store.is_armed())

    def test_parseable_malformed_latest_is_reported_without_crashing(self):
        for content, error_name in (
            ("null", "AttributeError"),
            ('{"schema_version": 1}', "KeyError"),
        ):
            with self.subTest(content=content), TemporaryDirectory() as root:
                path = Path(root) / "gaze_reviews" / "latest.json"
                path.parent.mkdir(parents=True)
                path.write_text(content, encoding="utf-8")

                store = self.make_store(root)

                self.assertIsNone(store.latest())
                self.assertIn(error_name, store.load_error())
                self.assertFalse(store.is_armed())

    def test_persist_failure_keeps_active_session_for_retry(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.register_slide("deck-a", 1, AOIS)
            store.accept(make_sample(received_at=1.0))
            store.accept(make_sample(received_at=1.2))
            self.monotonic.value = 1.2

            with patch.object(store, "_write", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    store.finish(deck_id="deck-a")

            self.assertTrue(store.has_active())
            self.assertTrue(store.is_armed())
            self.assertIsNone(store.latest())

    def test_completed_review_cannot_be_overwritten_until_start_new(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            original = store.finish(deck_id="deck-a")

            with self.assertRaisesRegex(RuntimeError, "Start a new study"):
                store.finish(deck_id="deck-a")

            self.assertEqual(store.latest().to_dict(), original.to_dict())
            self.assertFalse(store.is_armed())

    def test_active_study_rejects_another_deck_until_start_new(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            store.register_slide("deck-a", 1, AOIS)
            store.register_slide("deck-b", 1, AOIS)
            self.assertTrue(
                store.accept(make_deck_sample("deck-a", received_at=1.0))
            )

            self.assertFalse(
                store.accept(make_deck_sample("deck-b", received_at=1.2))
            )
            self.assertEqual(store.active_deck_id(), "deck-a")
            with self.assertRaisesRegex(RuntimeError, "another deck"):
                store.finish(deck_id="deck-b")

            store.start_new()
            self.assertTrue(
                store.accept(make_deck_sample("deck-b", received_at=2.0))
            )
            self.assertEqual(store.active_deck_id(), "deck-b")

    def test_delete_failure_preserves_latest_and_disarmed_state(self):
        with TemporaryDirectory() as root:
            store = self.make_store(root)
            original = store.finish(deck_id="deck-a")

            with patch.object(store, "_delete_latest", side_effect=OSError("read only")):
                with self.assertRaisesRegex(OSError, "read only"):
                    store.start_new()

            self.assertEqual(store.latest().to_dict(), original.to_dict())
            self.assertFalse(store.is_armed())


if __name__ == "__main__":
    unittest.main()
