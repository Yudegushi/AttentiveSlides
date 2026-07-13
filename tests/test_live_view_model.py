from __future__ import annotations

import unittest

from modules.common.schemas import GazePrediction, LearningState
from modules.media import BrowserMediaSource
from modules.system.adapters import MockManifestSlideProvider, SensingFrame
from modules.system.live_turn_runner import LiveTurnOutcome
from modules.system.pipeline import run_interaction
from modules.system.runtime_state import RuntimeState
from modules.system.sensing_snapshot_store import SensingSnapshot, SensingSnapshotStore
from modules.system.live_view_model import LiveViewModel


class FakeClock:
    def __init__(self, value: float = 10.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeTutorAdapter:
    def __init__(self) -> None:
        self.enabled = False
        self.calls: list[bool] = []

    def enable_grounded(self) -> bool:
        self.enabled = True
        self.calls.append(True)
        return True

    def disable_grounded(self) -> None:
        self.enabled = False
        self.calls.append(False)

    def status(self):
        return {
            "selection": "grounded" if self.enabled else "deterministic",
            "configuration_error": None,
            "provider_error": None,
            "last_status": "success" if self.enabled else "deterministic",
            "provider": "test_provider" if self.enabled else "deterministic_mock",
            "model": "test_model" if self.enabled else "mock",
            "fallback_used": False,
        }

    def latest_xai_view(self):
        return {"status": "success"} if self.enabled else None


class FakeController:
    def __init__(self) -> None:
        self.state = RuntimeState.STOPPED
        self.busy_turn_count = 0
        self.slides: list[int] = []
        self.start_count = 0
        self.stop_count = 0
        self.disconnect_count = 0
        self.outcomes: list[LiveTurnOutcome] = []
        self.confirmations: list[tuple[str, str]] = []

    def set_slide(self, slide_id: int) -> None:
        self.slides.append(slide_id)

    def start(self) -> None:
        self.start_count += 1
        self.state = RuntimeState.MONITORING

    def stop(self, *, reason: str = "requested") -> None:
        del reason
        self.stop_count += 1
        self.state = RuntimeState.STOPPED

    def handle_disconnect(self) -> None:
        self.disconnect_count += 1
        self.state = RuntimeState.STOPPED

    def poll(self) -> list[LiveTurnOutcome]:
        outcomes = list(self.outcomes)
        self.outcomes.clear()
        return outcomes

    def confirm(self, query_id: str, confirmed_aoi_id: str) -> LiveTurnOutcome:
        self.confirmations.append((query_id, confirmed_aoi_id))
        self.state = RuntimeState.MONITORING
        return LiveTurnOutcome(
            interaction_result=run_interaction(
                transcript="解释这个",
                gaze_prediction=GazePrediction(5, "middle_right", "right_figure", 0.9),
                learning_state=LearningState(),
                confirmed_aoi_id=confirmed_aoi_id,
            ),
            pending_confirmation=False,
            transcript="解释这个",
            turn_started_at=10.0,
            turn_ended_at=10.5,
        )


class LiveViewModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.provider = MockManifestSlideProvider()
        self.source = BrowserMediaSource(clock=self.clock)
        self.store = SensingSnapshotStore(clock=self.clock)
        self.controller = FakeController()
        self.view = LiveViewModel(
            controller=self.controller,
            media_source=self.source,
            slide_provider=self.provider,
            snapshot_store=self.store,
            clock=self.clock,
        )
        self.view.set_slide(5)

    def test_start_stop_and_rerun_ownership_are_idempotent(self) -> None:
        self.view.start()
        self.view.start()
        self.view.stop()
        self.view.stop()

        self.assertEqual(self.controller.start_count, 1)
        self.assertEqual(self.controller.stop_count, 1)
        self.assertEqual(self.controller.slides, [5])
        self.assertEqual(self.view.snapshot()["runtime"]["state"], "stopped")

    def test_snapshot_exposes_gaze_turn_and_pending_confirmation(self) -> None:
        self.source.start()
        self.store.put(
            SensingSnapshot(
                slide_id=5,
                source_timestamp=1.0,
                source_timestamp_clock="browser_performance_seconds",
                processed_at=9.8,
                frame=SensingFrame(
                    gaze_prediction=GazePrediction(5, "middle_right", "right_figure", 0.8),
                    learning_state=LearningState(),
                ),
                is_valid=True,
                invalid_reason=None,
            )
        )
        pending_result = run_interaction(
            transcript="解释这个",
            gaze_prediction=GazePrediction(5, "middle_right", "right_figure", 0.76),
            learning_state=LearningState(),
        )
        self.controller.outcomes.append(
            LiveTurnOutcome(
                interaction_result=pending_result,
                pending_confirmation=True,
                transcript="解释这个",
                turn_started_at=10.0,
                turn_ended_at=10.5,
            )
        )

        self.view.poll()
        snapshot = self.view.snapshot()

        self.assertEqual(snapshot["gaze"]["predicted_aoi_id"], "right_figure")
        self.assertEqual(snapshot["turn"]["duration_seconds"], 0.5)
        self.assertTrue(snapshot["confirmation"]["pending"])
        self.assertEqual(snapshot["confirmation"]["query_id"], pending_result.resolved_query.query_id)
        self.assertTrue(snapshot["interaction"]["pending_confirmation"])

    def test_grounded_selection_is_routed_without_recreating_workers(self) -> None:
        adapter = FakeTutorAdapter()
        view = LiveViewModel(
            controller=self.controller,
            media_source=self.source,
            slide_provider=self.provider,
            snapshot_store=self.store,
            tutor_adapter=adapter,
            clock=self.clock,
        )
        view.set_slide(5)

        self.assertTrue(view.configure_grounded_tutor(True))
        grounded = view.snapshot()
        view.configure_grounded_tutor(False)

        self.assertEqual(adapter.calls, [True, False])
        self.assertEqual(grounded["tutor"]["selection"], "grounded")
        self.assertEqual(grounded["grounded_xai"], {"status": "success"})
        self.assertEqual(view.snapshot()["tutor"]["selection"], "deterministic")

    def test_correction_routes_to_controller_and_disconnect_copy_is_explicit(self) -> None:
        self.controller.outcomes.append(
            LiveTurnOutcome(
                interaction_result=run_interaction(
                    transcript="解释这个",
                    gaze_prediction=GazePrediction(5, "middle_right", "right_figure", 0.76),
                    learning_state=LearningState(),
                ),
                pending_confirmation=True,
                transcript="解释这个",
                turn_started_at=10.0,
                turn_ended_at=10.5,
            )
        )
        self.view.poll()
        query_id = self.view.snapshot()["confirmation"]["query_id"]

        self.view.confirm(query_id, "bottom_caption")

        self.assertEqual(self.controller.confirmations, [(query_id, "bottom_caption")])
        self.assertTrue(self.view.snapshot()["interaction"]["actual"]["user_corrected"])

        self.view.handle_disconnect()

        self.assertEqual(self.controller.disconnect_count, 1)
        self.assertEqual(
            self.view.snapshot()["runtime"]["status_copy"],
            "Browser disconnected; live workers were stopped.",
        )


if __name__ == "__main__":
    unittest.main()
