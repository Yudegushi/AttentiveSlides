from types import SimpleNamespace
import unittest

from modules.common.schemas import AOI, GazePrediction, LearningState, Transcript
from modules.human_sensing.contracts import GazePrediction as MemberGazePrediction
from modules.system.adapters import SensingFrame
from modules.system.runtime_state import RuntimeState
from modules.system.slide_geometry import SlideViewportGeometry, ViewportBBox
from modules.system.turn_context import AggregatedSensing


def make_proposal(**changes):
    from modules.system.live_ui_bridge import LiveInteractionProposal

    values = {
        "interaction_id": "interaction-1",
        "deck_id": "deck-a",
        "slide_id": 2,
        "layout_revision": -1,
        "transcript": "Explain this",
        "gaze_grid": "middle_right",
        "gaze_confidence": 0.9,
        "stable_duration_sec": 0.4,
        "original_speech_transcript": "Explain this",
    }
    values.update(changes)
    return LiveInteractionProposal(**values)


def make_geometry(**changes):
    values = {
        "deck_id": "deck-a",
        "slide_id": 2,
        "layout_revision": 7,
        "received_at": 10.0,
        "viewport_width": 900.0,
        "viewport_height": 900.0,
        "device_pixel_ratio": 2.0,
        "slide_rect": ViewportBBox(100, 100, 800, 800),
        "aoi_rects": {
            "right": ViewportBBox(650, 350, 850, 550),
            "left": ViewportBBox(50, 350, 250, 550),
        },
    }
    values.update(changes)
    return SlideViewportGeometry(**values)


class LatestProposalInboxTest(unittest.TestCase):
    def test_latest_unconsumed_proposal_wins(self):
        from modules.system.live_ui_bridge import LatestProposalInbox

        inbox = LatestProposalInbox()
        inbox.publish(make_proposal(interaction_id="old"))
        inbox.publish(make_proposal(interaction_id="new"))

        self.assertEqual(inbox.pop().interaction_id, "new")
        self.assertIsNone(inbox.pop())

    def test_clear_discards_pending_proposal(self):
        from modules.system.live_ui_bridge import LatestProposalInbox

        inbox = LatestProposalInbox()
        inbox.publish(make_proposal())
        inbox.clear()

        self.assertIsNone(inbox.pop())


class GridTargetResolverTest(unittest.TestCase):
    def aois(self):
        return [
            AOI("right", [0.6, 0.3, 0.9, 0.7], "figure"),
            AOI("left", [0.1, 0.3, 0.4, 0.7], "text"),
            AOI("whole_slide", [0, 0, 1, 1], "whole_slide"),
        ]

    def test_resolves_grid_with_deterministic_viewport_score(self):
        from modules.system.live_ui_bridge import resolve_grid_target

        resolved = resolve_grid_target(
            make_proposal(), make_geometry(), self.aois()
        )

        self.assertEqual(resolved.predicted_aoi_id, "right")
        self.assertEqual(resolved.layout_revision, 7)
        self.assertGreater(resolved.target_confidence, 0.8)
        self.assertEqual(resolved.alternatives[0].aoi_id, "right")

    def test_ties_sort_by_aoi_id(self):
        from modules.system.live_ui_bridge import resolve_grid_target

        geometry = make_geometry(
            aoi_rects={
                "zeta": ViewportBBox(650, 350, 850, 550),
                "alpha": ViewportBBox(650, 350, 850, 550),
            }
        )
        aois = [
            AOI("zeta", [0, 0, 0.2, 0.2], "text"),
            AOI("alpha", [0, 0, 0.2, 0.2], "text"),
        ]

        resolved = resolve_grid_target(make_proposal(), geometry, aois)

        self.assertEqual(resolved.predicted_aoi_id, "alpha")

    def test_mismatch_or_low_confidence_has_no_predicted_aoi(self):
        from modules.system.live_ui_bridge import resolve_grid_target

        mismatched = resolve_grid_target(
            make_proposal(deck_id="other"), make_geometry(), self.aois()
        )
        low = resolve_grid_target(
            make_proposal(gaze_confidence=0.2), make_geometry(), self.aois()
        )

        self.assertIsNone(mismatched.predicted_aoi_id)
        self.assertIsNone(low.predicted_aoi_id)
        self.assertIn(
            "deck or slide mismatch",
            mismatched.sensing_evidence[-1],
        )

    def test_layout_revision_mismatch_retains_discard_reason(self):
        from modules.system.live_ui_bridge import resolve_grid_target

        mismatched = resolve_grid_target(
            make_proposal(
                layout_revision=6,
                sensing_evidence=("prior public note",),
            ),
            make_geometry(layout_revision=7),
            self.aois(),
        )

        self.assertIsNone(mismatched.predicted_aoi_id)
        self.assertEqual(
            mismatched.sensing_evidence[-1],
            "gaze-grid evidence discarded: layout revision mismatch",
        )


class LiveConfirmationContractTest(unittest.TestCase):
    def resolved(self, **changes):
        values = {
            "layout_revision": 7,
            "predicted_aoi_id": "right",
            "target_confidence": 0.88,
        }
        values.update(changes)
        return make_proposal(**values)

    def test_always_confirm_never_auto_confirms(self):
        from modules.system.live_ui_bridge import should_auto_confirm

        self.assertFalse(
            should_auto_confirm(
                self.resolved(),
                make_geometry(),
                policy="Always confirm",
                threshold=0.80,
                interaction_pending=False,
            )
        )

    def test_high_confidence_can_auto_confirm(self):
        from modules.system.live_ui_bridge import should_auto_confirm

        self.assertTrue(
            should_auto_confirm(
                self.resolved(),
                make_geometry(),
                policy="Confidence-based auto",
                threshold=0.80,
                interaction_pending=False,
            )
        )

    def test_low_or_missing_gaze_cannot_auto_confirm(self):
        from modules.system.live_ui_bridge import should_auto_confirm

        for proposal in (
            self.resolved(target_confidence=0.79),
            self.resolved(predicted_aoi_id=None),
        ):
            self.assertFalse(
                should_auto_confirm(
                    proposal,
                    make_geometry(),
                    policy="Confidence-based auto",
                    threshold=0.80,
                    interaction_pending=False,
                )
            )

    def test_stale_geometry_pending_turn_and_bad_threshold_block_auto(self):
        from modules.system.live_ui_bridge import should_auto_confirm

        cases = (
            (self.resolved(), make_geometry(layout_revision=8), 0.80, False),
            (self.resolved(), make_geometry(), 0.80, True),
            (self.resolved(), make_geometry(), 0.69, False),
            (self.resolved(transcript=" "), make_geometry(), 0.80, False),
        )
        for proposal, geometry, threshold, pending in cases:
            self.assertFalse(
                should_auto_confirm(
                    proposal,
                    geometry,
                    policy="Confidence-based auto",
                    threshold=threshold,
                    interaction_pending=pending,
                )
            )

    def test_prediction_builds_sensor_assisted_interaction(self):
        from modules.system.live_ui_bridge import build_live_interaction_input

        interaction = build_live_interaction_input(
            self.resolved(),
            command="Explain this",
            selected_aoi_id="right",
            automatic=True,
        )

        self.assertEqual(interaction.mode, "sensor_assisted")
        self.assertEqual(interaction.target.source, "gaze_prediction")
        self.assertEqual(interaction.intent.source, "speech_transcript")
        self.assertIsNone(interaction.intent.source_confidence)
        self.assertEqual(
            interaction.confirmation.source,
            "automatic_high_confidence",
        )

    def test_user_correction_preserves_prediction(self):
        from modules.system.live_ui_bridge import build_live_interaction_input

        interaction = build_live_interaction_input(
            self.resolved(),
            command="Explain this",
            selected_aoi_id="left",
        )

        self.assertEqual(
            interaction.confirmation.source,
            "manual_correction",
        )
        self.assertEqual(
            interaction.confirmation.confirmed_aoi_id,
            "left",
        )
        self.assertEqual(
            interaction.confirmation.corrected_from_aoi_id,
            "right",
        )
        self.assertEqual(
            interaction.metadata["predicted_aoi_id"],
            "right",
        )

    def test_public_gaze_provenance_is_retained_and_bounded(self):
        from modules.system.live_ui_bridge import build_live_interaction_input

        interaction = build_live_interaction_input(
            self.resolved(
                gaze_source="eyetheia_local",
                sensing_evidence=(
                    "local point-gaze matched dwell=0.400s",
                    "older layout revision evidence discarded; "
                    "newest layout retained",
                    42,
                    "x" * 300,
                ),
            ),
            command="Explain this",
            selected_aoi_id="right",
        )

        self.assertEqual(
            interaction.metadata["gaze_source"],
            "eyetheia_local",
        )
        self.assertEqual(
            interaction.metadata["sensing_evidence"][:2],
            [
                "local point-gaze matched dwell=0.400s",
                "older layout revision evidence discarded; "
                "newest layout retained",
            ],
        )
        self.assertEqual(
            len(interaction.metadata["sensing_evidence"][2]),
            240,
        )

    def test_unknown_gaze_provenance_fails_safe(self):
        from modules.system.live_ui_bridge import build_live_interaction_input

        interaction = build_live_interaction_input(
            self.resolved(
                gaze_source="raw-private-provider",
                sensing_evidence="not-a-list",
            ),
            command="Explain this",
            selected_aoi_id="right",
        )

        self.assertEqual(interaction.metadata["gaze_source"], "unknown")
        self.assertEqual(interaction.metadata["sensing_evidence"], [])

    def test_transcript_edit_enters_hybrid_mode(self):
        from modules.system.live_ui_bridge import build_live_interaction_input

        interaction = build_live_interaction_input(
            self.resolved(),
            command="Please compare both concepts",
            selected_aoi_id="right",
        )

        self.assertEqual(interaction.mode, "hybrid")
        self.assertEqual(interaction.intent.source, "typed_text")

    def test_whole_slide_and_manual_rectangle_remain_explicit(self):
        from modules.system.live_ui_bridge import build_live_interaction_input

        whole = build_live_interaction_input(
            self.resolved(predicted_aoi_id=None),
            command="Explain this",
            selected_aoi_id="whole_slide",
        )
        region = build_live_interaction_input(
            self.resolved(),
            command="Explain this",
            selected_aoi_id="left",
            manual_bbox=(0.1, 0.2, 0.4, 0.6),
        )

        self.assertEqual(whole.target.source, "whole_slide")
        self.assertEqual(
            whole.confirmation.source,
            "explicit_user_confirmation",
        )
        self.assertEqual(region.target.source, "manual_rectangle")
        self.assertEqual(region.mode, "hybrid")


class ProposalTurnRunnerTest(unittest.TestCase):
    def test_publishes_transcript_and_grid_without_pending_confirmation(self):
        from modules.system.live_ui_bridge import (
            LatestProposalInbox,
            ProposalTurnRunner,
        )

        gaze = GazePrediction(
            slide_id=2,
            gaze_grid="middle_left",
            predicted_aoi_id=None,
            confidence=0.75,
            stable_duration_sec=0.3,
        )
        collector = SimpleNamespace(
            aggregate=lambda _context: AggregatedSensing(
                frame=SensingFrame(gaze, LearningState()),
                evidence=[],
            )
        )
        inbox = LatestProposalInbox()
        runner = ProposalTurnRunner(
            context_collector=collector,
            inbox=inbox,
            id_factory=lambda: "interaction-live",
        )
        audio = SimpleNamespace(
            status="completed",
            transcript=Transcript("What is this?"),
            turn=SimpleNamespace(started_at=1.0, ended_at=2.0),
            error=None,
        )

        outcome = runner.run(
            audio, SimpleNamespace(deck_id="deck-a", slide_id=2)
        )
        proposal = inbox.pop()

        self.assertFalse(outcome.pending_confirmation)
        self.assertEqual(proposal.interaction_id, "interaction-live")
        self.assertEqual(proposal.transcript, "What is this?")
        self.assertEqual(proposal.gaze_grid, "middle_left")
        self.assertEqual(proposal.layout_revision, -1)
        self.assertEqual(proposal.gaze_source, "cloud_grid")

    def test_local_point_provenance_and_resolved_target_are_preserved(self):
        from modules.system.live_ui_bridge import (
            LatestProposalInbox,
            ProposalTurnRunner,
        )

        gaze = GazePrediction(
            slide_id=2,
            gaze_grid="point",
            predicted_aoi_id="right",
            confidence=0.82,
            stable_duration_sec=0.4,
            alternative_targets=[
                {"aoi_id": "right", "score": 0.75},
                {"aoi_id": "left", "score": 0.25},
            ],
        )
        collector = SimpleNamespace(
            aggregate=lambda _context: AggregatedSensing(
                frame=SensingFrame(gaze, LearningState()),
                evidence=["local dwell"],
                gaze_source="eyetheia_local",
                layout_revision=7,
            )
        )
        inbox = LatestProposalInbox()
        runner = ProposalTurnRunner(
            context_collector=collector,
            inbox=inbox,
            id_factory=lambda: "interaction-local",
        )
        audio = SimpleNamespace(
            status="completed",
            transcript=Transcript("Explain this"),
            turn=SimpleNamespace(started_at=1.0, ended_at=2.0),
            error=None,
        )

        runner.run(audio, SimpleNamespace(deck_id="deck-a", slide_id=2))
        proposal = inbox.pop()

        self.assertEqual(proposal.gaze_source, "eyetheia_local")
        self.assertEqual(proposal.sensing_evidence, ("local dwell",))
        self.assertEqual(proposal.layout_revision, 7)
        self.assertEqual(proposal.predicted_aoi_id, "right")
        self.assertEqual(proposal.target_confidence, 0.82)
        self.assertEqual(
            [candidate.aoi_id for candidate in proposal.alternatives],
            ["right", "left"],
        )
        self.assertEqual(
            proposal.alternatives[0].evidence,
            ("local EyeTheia dwell",),
        )

    def test_grid_passthrough_uses_grid_as_temporary_member_key(self):
        from modules.system.live_ui_bridge import map_gaze_grid_only

        member = MemberGazePrediction(
            timestamp=1.5,
            slide_id=2,
            gaze_grid="bottom_center",
            confidence=0.8,
            stable_duration_sec=0.25,
        )

        prediction = map_gaze_grid_only(member, [])

        self.assertEqual(prediction.predicted_aoi_id, "bottom_center")
        self.assertEqual(prediction.gaze_grid, "bottom_center")
        self.assertEqual(prediction.confidence, 0.8)


class FakeController:
    def __init__(self):
        self.state = RuntimeState.STOPPED
        self.calls = []

    def start(self):
        self.calls.append(("start",))
        self.state = RuntimeState.MONITORING

    def stop(self, *, reason):
        self.calls.append(("stop", reason))
        self.state = RuntimeState.STOPPED

    def handle_disconnect(self):
        self.calls.append(("disconnect",))
        self.state = RuntimeState.ERROR

    def set_slide(self, slide_id):
        self.calls.append(("slide", slide_id))

    def poll(self):
        self.calls.append(("poll",))
        return ["outcome"]


class Clearable:
    def __init__(self):
        self.clear_count = 0

    def clear(self):
        self.clear_count += 1


class MainUILiveRuntimeTest(unittest.TestCase):
    def test_delegates_lifecycle_and_clears_transient_state_on_slide_binding(self):
        from modules.system.live_ui_bridge import MainUILiveRuntime

        controller = FakeController()
        inbox = Clearable()
        snapshots = Clearable()
        runtime = MainUILiveRuntime(
            controller=controller,
            inbox=inbox,
            snapshot_store=snapshots,
        )

        self.assertFalse(runtime.is_running)
        runtime.set_slide(3)
        runtime.start()
        self.assertTrue(runtime.is_running)
        self.assertEqual(runtime.poll(), ["outcome"])
        runtime.stop(reason="test")
        runtime.handle_disconnect()

        self.assertEqual(inbox.clear_count, 1)
        self.assertEqual(snapshots.clear_count, 1)
        self.assertIn(("slide", 3), controller.calls)
        self.assertIn(("stop", "test"), controller.calls)


if __name__ == "__main__":
    unittest.main()
