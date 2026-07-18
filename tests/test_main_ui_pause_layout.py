from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from apps import streamlit_attentive_slides as app


class FakeStreamlit:
    def __init__(self, state):
        self.session_state = state

    def spinner(self, _message):
        return nullcontext()

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class FakeStudyReview:
    def __init__(self, events, status="active"):
        self.events = events
        self.status = status
        self.revision = 1
        self.session_id = "review-1" if status != "idle" else None
        self.finish_error = None
        self.latest_review = SimpleNamespace(
            session_id="saved-1",
            gaze_review=SimpleNamespace(slides=()),
        )

    def lifecycle(self):
        return SimpleNamespace(
            status=self.status,
            session_id=self.session_id,
            revision=self.revision,
            active_seconds=12.0,
            deck_id="deck-a" if self.session_id else None,
        )

    def pause(self):
        if self.status == "active":
            self.events.append("store.pause")
            self.status = "paused"
            self.revision += 1

    def resume(self):
        if self.status == "paused":
            self.events.append("store.resume")
            self.status = "active"
            self.revision += 1

    def finish(self, *, deck_id):
        self.events.append(("store.finish", deck_id))
        if self.finish_error is not None:
            self.status = "finish_pending"
            self.revision += 1
            raise self.finish_error
        self.status = "idle"
        self.session_id = None
        self.revision += 1
        return self.latest_review

    def latest(self):
        return self.latest_review

    def load_warnings(self):
        return ()

    def set_context(self, deck_id, slide_id):
        self.events.append(("store.context", deck_id, slide_id))

    def register_slide(self, deck_id, slide_id, aois):
        self.events.append(("store.register", deck_id, slide_id, tuple(aois)))


class FakeService:
    def __init__(self, events):
        self.events = events
        self.quiesce_error = None
        self.resume_error = None

    def quiesce(self, reason):
        self.events.append(("service.quiesce", reason))
        if self.quiesce_error is not None:
            raise self.quiesce_error

    def resume_from_quiesce(self, *, master_enabled):
        self.events.append(("service.resume", master_enabled))
        if self.resume_error is not None:
            raise self.resume_error


class FakeQueue:
    def __init__(self):
        self.clear_count = 0
        self.pop_count = 0

    def clear(self):
        self.clear_count += 1

    def pop(self):
        self.pop_count += 1
        return None


def make_state():
    return {
        **app.build_main_turn_defaults(),
        **app.build_main_live_defaults(),
        **app.build_main_review_defaults(),
        "main_live_master_enabled": True,
        "main_review_session": None,
        "main_review_error": None,
        "main_live_full_rerun_requested": True,
        "main_tutor_result": {"answer": "completed"},
        "main_tutor_context": {"source": "slide"},
        "main_xai_result": {"status": "ok"},
        "main_last_generated_interaction_id": "done-1",
        "main_tutor_result_token": ("review-1", 1),
    }


def make_resources(status="active"):
    events = []
    study = FakeStudyReview(events, status=status)
    resources = SimpleNamespace(
        study_review=study,
        service=FakeService(events),
        inbox=FakeQueue(),
        snapshots=FakeQueue(),
        voice=SimpleNamespace(snapshot=lambda: {"suspended": False}),
        ingress=SimpleNamespace(
            session_snapshot=lambda: SimpleNamespace(active=True)
        ),
        runtime=SimpleNamespace(poll=lambda: None),
        single_turn_tts=None,
    )
    return resources, events


class MainUIPauseBehaviorTests(unittest.TestCase):
    def test_pause_closes_store_before_service_and_preserves_preference_and_answer(self):
        state = make_state()
        resources, events = make_resources("active")
        with patch.object(app, "st", FakeStreamlit(state)):
            app._pause_study_review(resources)

        self.assertEqual(events[:2], [
            "store.pause",
            ("service.quiesce", "study paused"),
        ])
        self.assertEqual(resources.study_review.status, "paused")
        self.assertTrue(state["main_live_master_enabled"])
        self.assertEqual(state["main_tutor_result"], {"answer": "completed"})
        self.assertIsNone(state["main_confirmed_interaction"])
        self.assertEqual(resources.inbox.clear_count, 1)

    def test_resume_restores_service_before_store_and_failure_stays_paused(self):
        state = make_state()
        resources, events = make_resources("paused")
        view = SimpleNamespace(
            deck_id="deck-a",
            active_slide_id=2,
            active_slide=SimpleNamespace(aois=()),
        )
        resources.service.resume_error = RuntimeError("device busy")
        with patch.object(app, "st", FakeStreamlit(state)):
            app._resume_study_review(resources, view)
        self.assertEqual(resources.study_review.status, "paused")
        self.assertNotIn("store.resume", events)

        resources.service.resume_error = None
        with patch.object(app, "st", FakeStreamlit(state)), patch.object(
            app, "_sync_main_live_voice_resources"
        ):
            app._resume_study_review(resources, view)
        self.assertLess(
            events.index(("service.resume", True), 1),
            events.index("store.resume"),
        )
        self.assertEqual(resources.study_review.status, "active")

    def test_active_and_paused_finish_quiesce_before_save_and_save_failure_is_retryable(self):
        for initial in ("active", "paused"):
            with self.subTest(initial=initial):
                state = make_state()
                resources, events = make_resources(initial)
                with patch.object(app, "st", FakeStreamlit(state)):
                    app._finish_study_review(resources, "deck-a")
                quiesce = events.index(("service.quiesce", "study finished"))
                finish = events.index(("store.finish", "deck-a"))
                self.assertLess(quiesce, finish)
                self.assertEqual(state["main_workspace_mode"], "review")

        state = make_state()
        resources, events = make_resources("paused")
        resources.study_review.finish_error = OSError("disk full")
        with patch.object(app, "st", FakeStreamlit(state)):
            app._finish_study_review(resources, "deck-a")
        self.assertEqual(resources.study_review.status, "finish_pending")
        self.assertEqual(state["main_workspace_mode"], "study")
        self.assertIn("disk full", state["main_review_error"])

    def test_saved_review_and_back_to_study_use_safe_service_gate(self):
        state = make_state()
        resources, events = make_resources("idle")
        with patch.object(app, "st", FakeStreamlit(state)):
            app._open_latest_review(resources)
        self.assertEqual(events[0], ("service.quiesce", "saved review opened"))
        self.assertEqual(state["main_workspace_mode"], "review")

        with patch.object(app, "st", FakeStreamlit(state)):
            app._back_to_study_workspace(resources)
        self.assertEqual(events[-1], ("service.resume", True))
        self.assertEqual(state["main_workspace_mode"], "study")

        paused, paused_events = make_resources("paused")
        with patch.object(app, "st", FakeStreamlit(make_state())):
            app._open_latest_review(paused)
        self.assertEqual(paused_events, [])

    def test_mutation_gate_and_tokens_reject_paused_or_stale_work(self):
        paused, _events = make_resources("paused")
        active, _events = make_resources("active")
        token = app._lifecycle_token(active)
        self.assertFalse(app._study_mutations_enabled(paused))
        self.assertTrue(app._study_mutations_enabled(active))
        self.assertTrue(app._lifecycle_token_matches(active, token))
        active.study_review.revision += 1
        self.assertFalse(app._lifecycle_token_matches(active, token))

        with patch.object(app, "st", FakeStreamlit(make_state())):
            app._consume_live_proposal(paused, SimpleNamespace())
        self.assertEqual(paused.inbox.pop_count, 0)

    def test_tutor_late_result_and_playback_are_discarded_after_token_change(self):
        state = make_state()
        state.update({
            "main_confirmed_interaction": {
                "interaction": {"interaction_id": "turn-1"},
                "lifecycle_token": ("review-1", 1),
            },
            "main_cloud_text_allowed": True,
            "main_conversation_error": None,
            "main_conversation_turns": [],
            "main_history_max_items": 4,
            "main_interaction_flow": "one_turn",
            "main_logged_interaction_ids": [],
        })
        resources, _events = make_resources("active")
        generation = SimpleNamespace(
            to_session_payload=lambda: {
                "context": {},
                "tutor": {"answer": "late"},
                "xai": {},
            }
        )

        def late_generation(*args, **kwargs):
            del args, kwargs
            resources.study_review.revision += 1
            return generation

        with patch.object(app, "st", FakeStreamlit(state)), patch.object(
            app, "assess_tutor_generation", return_value=SimpleNamespace(ready=True)
        ), patch.object(
            app.OpenAICompatibleLLMClient, "from_env", return_value=object()
        ), patch.object(
            app, "GroundedTutorAgent", return_value=object()
        ), patch.object(
            app, "generate_main_tutor_response", side_effect=late_generation
        ):
            committed = app._generate_confirmed_turn(SimpleNamespace(active_slide=object()), resources)

        self.assertFalse(committed)
        self.assertEqual(state["main_tutor_result"], {"answer": "completed"})
        self.assertEqual(state["main_logged_interaction_ids"], [])

        calls = []
        state["main_tutor_result"] = {
            "answer": "completed",
            "validation_is_valid": True,
            "status": "grounded",
        }
        state["main_tutor_result_token"] = ("review-1", 1)
        resources.single_turn_tts = SimpleNamespace(
            synthesize_once=lambda **kwargs: (
                calls.append(kwargs)
                or SimpleNamespace(audio_path=None, error_message=None)
            )
        )
        with patch.object(app, "st", FakeStreamlit(state)):
            app._render_tutor_result(resources)
        self.assertFalse(calls[0]["enabled"])

    def test_header_uses_store_timer_and_exposes_all_lifecycle_actions(self):
        source = Path("apps/streamlit_attentive_slides.py").read_text(encoding="utf-8")
        self.assertNotIn("main_study_started_monotonic", source)
        for token in (
            "lifecycle.active_seconds",
            "selected_review.active_seconds",
            '"READY"',
            '"REVIEW · {elapsed} STUDIED"',
            '"PAUSE"',
            '"RESUME"',
            '"END & REVIEW"',
            '"BACK TO STUDY"',
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
