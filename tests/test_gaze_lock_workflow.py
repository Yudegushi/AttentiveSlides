import unittest

from modules.common.schemas import AOI
from modules.gaze_lock_test.contracts import GazeLockScope
from modules.gaze_lock_test.workflow import (
    aggregate_preclick_gaze,
    build_typed_interaction,
    canonical_aoi_identity,
    consume_lock_event,
    lock_is_current,
)
from modules.media.browser_gaze_source import (
    BrowserGeometrySnapshot,
    BrowserPointGazeSample,
)
from modules.system.slide_geometry import SlideViewportGeometry, ViewportBBox


AOIS = (
    AOI(
        "alpha",
        [0.1, 0.1, 0.3, 0.3],
        "text",
        text="Alpha explanation",
        name="Alpha",
    ),
    AOI(
        "beta",
        [0.5, 0.1, 0.7, 0.3],
        "figure",
        name="Beta",
    ),
)


def make_scope(**changes):
    values = {
        "deck_id": "deck-a",
        "slide_id": 1,
        "layout_revision": 7,
        "capture_session_id": "capture-a",
        "aoi_identity": canonical_aoi_identity(
            AOIS,
            aoi_profile="llm_assisted",
        ),
    }
    values.update(changes)
    return GazeLockScope(**values)


def make_sample(
    *,
    browser_ms,
    x=150.0,
    deck_id="deck-a",
    slide_id=1,
    revision=7,
):
    geometry = SlideViewportGeometry(
        deck_id=deck_id,
        slide_id=slide_id,
        layout_revision=revision,
        received_at=browser_ms / 1000.0,
        viewport_width=1000.0,
        viewport_height=800.0,
        device_pixel_ratio=1.0,
        slide_rect=ViewportBBox(0.0, 0.0, 1000.0, 800.0),
        aoi_rects={
            "alpha": ViewportBBox(100.0, 100.0, 300.0, 300.0),
            "beta": ViewportBBox(500.0, 100.0, 700.0, 300.0),
        },
    )
    snapshot = BrowserGeometrySnapshot(
        browser_timestamp_ms=browser_ms - 1,
        received_at=browser_ms / 1000.0,
        geometry=geometry,
    )
    return BrowserPointGazeSample(
        sequence=int(browser_ms),
        browser_timestamp_ms=float(browser_ms),
        received_at=browser_ms / 1000.0,
        x_css=x,
        y_css=150.0,
        viewport_width=1000.0,
        viewport_height=800.0,
        valid=True,
        face_detected=True,
        source="eyetheia_local",
        geometry=snapshot,
    )


def lock_payload(event_id="event-1", clicked_at=10_000.0):
    return {
        "event": "gaze_lock",
        "event_id": event_id,
        "clicked_at_browser_ms": clicked_at,
    }


class GazeLockWorkflowTest(unittest.TestCase):
    def test_preclick_window_excludes_post_click_and_old_samples(self):
        result = aggregate_preclick_gaze(
            (
                make_sample(browser_ms=8_999, x=550),
                make_sample(browser_ms=9_700),
                make_sample(browser_ms=9_900),
                make_sample(browser_ms=10_001, x=550),
            ),
            AOIS,
            clicked_at_browser_ms=10_000,
            scope=make_scope(),
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.predicted_aoi_id, "alpha")
        self.assertEqual(result.stable_duration_sec, 0.3)

    def test_preclick_uses_browser_deltas_and_caps_each_interval(self):
        result = aggregate_preclick_gaze(
            (
                make_sample(browser_ms=9_000),
                make_sample(browser_ms=9_900),
            ),
            AOIS,
            clicked_at_browser_ms=10_000,
            scope=make_scope(),
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.stable_duration_sec, 0.6)

    def test_stale_slide_or_layout_is_not_lockable(self):
        for sample in (
            make_sample(browser_ms=9_700, slide_id=2),
            make_sample(browser_ms=9_700, revision=6),
        ):
            with self.subTest(sample=sample):
                result = aggregate_preclick_gaze(
                    (sample,),
                    AOIS,
                    clicked_at_browser_ms=10_000,
                    scope=make_scope(),
                )
                self.assertIsNone(result)

    def test_insufficient_dwell_remains_unlocked(self):
        attempt = consume_lock_event(
            lock_payload(),
            seen_event_ids=(),
            current_target=None,
            scope=make_scope(),
            samples=(make_sample(browser_ms=9_950),),
            aois=AOIS,
        )

        self.assertEqual(attempt.status, "insufficient_gaze")
        self.assertIsNone(attempt.target)

    def test_lock_event_is_idempotent(self):
        attempt = consume_lock_event(
            lock_payload(),
            seen_event_ids=("event-1",),
            current_target=None,
            scope=make_scope(),
            samples=(make_sample(browser_ms=9_700),),
            aois=AOIS,
        )

        self.assertEqual(attempt.status, "duplicate")
        self.assertIsNone(attempt.target)

    def test_existing_lock_cannot_be_replaced_by_new_gaze(self):
        first = consume_lock_event(
            lock_payload(),
            seen_event_ids=(),
            current_target=None,
            scope=make_scope(),
            samples=(make_sample(browser_ms=9_700),),
            aois=AOIS,
            server_clock=lambda: 123.0,
            lock_id_factory=lambda: "lock-a",
        )
        second = consume_lock_event(
            lock_payload("event-2", 11_000),
            seen_event_ids=("event-1",),
            current_target=first.target,
            scope=make_scope(),
            samples=(make_sample(browser_ms=10_700, x=550),),
            aois=AOIS,
        )

        self.assertEqual(first.status, "locked")
        self.assertEqual(second.status, "already_locked")
        self.assertIs(second.target, first.target)
        self.assertEqual(second.target.aoi_id, "alpha")

    def test_identity_boundaries_invalidate_the_lock(self):
        attempt = consume_lock_event(
            lock_payload(),
            seen_event_ids=(),
            current_target=None,
            scope=make_scope(),
            samples=(make_sample(browser_ms=9_700),),
            aois=AOIS,
            lock_id_factory=lambda: "lock-a",
        )

        self.assertTrue(lock_is_current(attempt.target, make_scope()))
        for changed_scope in (
            make_scope(deck_id="deck-b"),
            make_scope(slide_id=2),
            make_scope(layout_revision=8),
            make_scope(capture_session_id="capture-b"),
            make_scope(aoi_identity="different"),
        ):
            with self.subTest(scope=changed_scope):
                self.assertFalse(lock_is_current(attempt.target, changed_scope))

    def test_typed_interaction_is_confirmed_and_contains_no_raw_gaze(self):
        attempt = consume_lock_event(
            lock_payload(),
            seen_event_ids=(),
            current_target=None,
            scope=make_scope(),
            samples=(make_sample(browser_ms=9_700),),
            aois=AOIS,
            server_clock=lambda: 123.0,
            lock_id_factory=lambda: "lock-a",
        )

        interaction = build_typed_interaction(
            attempt.target,
            question_text=" Explain this ",
            interaction_id="request-a",
        )
        payload = interaction.to_dict()

        self.assertEqual(interaction.mode, "hybrid")
        self.assertEqual(interaction.target.source, "gaze_prediction")
        self.assertEqual(interaction.target.predicted_aoi_id, "alpha")
        self.assertEqual(interaction.intent.source, "typed_text")
        self.assertEqual(interaction.intent.text, "Explain this")
        self.assertTrue(interaction.confirmation.confirmed)
        self.assertEqual(
            interaction.confirmation.source,
            "explicit_user_confirmation",
        )
        self.assertEqual(interaction.confirmation.confirmed_aoi_id, "alpha")
        self.assertNotIn("samples", str(payload).lower())
        self.assertNotIn("x_css", str(payload).lower())


if __name__ == "__main__":
    unittest.main()
