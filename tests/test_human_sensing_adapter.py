import unittest

from modules.human_sensing.contracts import (
    AOIPrediction as MemberAOIPrediction,
    LearningState as MemberLearningState,
)

try:
    from modules.system.human_sensing_adapter import HumanSensingAdapter
except ImportError:
    HumanSensingAdapter = None


def member_learning_state(*, face_detected: bool = True) -> MemberLearningState:
    return MemberLearningState(
        timestamp=12.0,
        face_detected=face_detected,
        screen_facing_score=0.8 if face_detected else 0.0,
        yawn_detected=False,
        yawn_count_last_3min=0,
        eyes_closed=False,
        eye_closure_duration_sec=0.0,
        head_down=False,
        fatigue_signal_score=0.2,
        possible_review_needed=False,
    )


class HumanSensingAdapterTest(unittest.TestCase):
    def test_maps_member_outputs_to_canonical_frames_with_stable_candidate_ranking(self):
        self.assertIsNotNone(HumanSensingAdapter)
        member_gaze = MemberAOIPrediction(
            timestamp=12.0,
            slide_id=3,
            gaze_grid="middle_center",
            predicted_aoi_id="target",
            confidence=0.76,
            stable_duration_sec=2.4,
            candidate_scores={"beta": 0.3, "alpha": 0.3, "target": 0.8},
        )

        adapted = HumanSensingAdapter().adapt(member_gaze, member_learning_state())

        self.assertTrue(adapted.is_valid)
        self.assertIsNone(adapted.invalid_reason)
        self.assertEqual(adapted.frame.gaze_prediction.predicted_aoi_id, "target")
        self.assertEqual(adapted.frame.gaze_prediction.confidence, 0.76)
        self.assertEqual(adapted.frame.gaze_prediction.stable_duration_sec, 2.4)
        self.assertEqual(
            adapted.frame.gaze_prediction.alternative_targets,
            [
                {"aoi_id": "target", "score": 0.8},
                {"aoi_id": "alpha", "score": 0.3},
                {"aoi_id": "beta", "score": 0.3},
            ],
        )
        self.assertTrue(adapted.frame.learning_state.face_detected)

    def test_downgrades_no_face_unknown_grid_and_low_confidence_without_target(self):
        self.assertIsNotNone(HumanSensingAdapter)
        adapter = HumanSensingAdapter(min_confidence=0.5)
        cases = [
            (
                MemberAOIPrediction(12.0, 3, "unknown", "target", 0.9, 1.0),
                member_learning_state(),
                "unknown_grid",
            ),
            (
                MemberAOIPrediction(12.0, 3, "middle_center", "target", 0.9, 1.0),
                member_learning_state(face_detected=False),
                "no_face",
            ),
            (
                MemberAOIPrediction(12.0, 3, "middle_center", "target", 0.2, 1.0),
                member_learning_state(),
                "low_confidence",
            ),
        ]

        for gaze, learning, reason in cases:
            with self.subTest(reason=reason):
                adapted = adapter.adapt(gaze, learning)

                self.assertFalse(adapted.is_valid)
                self.assertEqual(adapted.invalid_reason, reason)
                self.assertIsNone(adapted.frame.gaze_prediction.predicted_aoi_id)
                self.assertEqual(adapted.frame.gaze_prediction.alternative_targets, [])


if __name__ == "__main__":
    unittest.main()
