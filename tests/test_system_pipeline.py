import json
import tempfile
import unittest
from pathlib import Path

from evaluation.eval_reference_resolution import evaluate_scenarios
from evaluation.eval_scenario_outputs import evaluate_outputs
from modules.common.schemas import GazePrediction, InteractionResult, LearningState
from modules.interaction.interaction_history import InteractionHistory
from modules.logging.interaction_logger import InteractionLogger
from modules.system.pipeline import run_interaction
from modules.system.scenarios import load_scenarios


class SystemPipelineTest(unittest.TestCase):
    def test_pipeline_returns_full_interaction_result(self):
        result = run_interaction(
            transcript="总结这一页",
            gaze_prediction=GazePrediction(5, "middle_center", None, 0.0),
            learning_state=LearningState(),
        )

        self.assertIsInstance(result, InteractionResult)
        self.assertEqual(result.resolved_query.resolved_aoi_id, "whole_slide")
        self.assertEqual(result.tutor_response.response_mode, "summarize")
        self.assertEqual(result.ui_state.highlighted_aoi_id, "whole_slide")

    def test_pending_confirmation_gates_final_answer(self):
        result = run_interaction(
            transcript="解释这个",
            gaze_prediction=GazePrediction(5, "middle_right", "right_figure", 0.76, stable_duration_sec=2.3),
            learning_state=LearningState(),
        )

        self.assertEqual(result.resolved_query.confirmation_mode, "confirm_one")
        self.assertEqual(result.tutor_response.response_mode, "pending_confirmation")
        self.assertIsNone(result.ui_state.response["answer"])
        self.assertIsNone(result.ui_state.highlighted_aoi_id)
        self.assertIsNotNone(result.ui_state.confirmation_message)
        self.assertIsNone(result.log_event.confirmed_aoi_id)
        self.assertIsNone(result.log_event.user_corrected)

    def test_confirmed_correction_overrides_predicted_aoi(self):
        result = run_interaction(
            transcript="解释这个",
            gaze_prediction=GazePrediction(5, "middle_right", "right_figure", 0.76, stable_duration_sec=2.3),
            learning_state=LearningState(),
            confirmed_aoi_id="bottom_caption",
        )

        self.assertEqual(result.resolved_query.resolved_aoi_id, "bottom_caption")
        self.assertEqual(result.tutor_response.response_mode, "explain")
        self.assertEqual(result.tutor_response.used_context["aoi_id"], "bottom_caption")
        self.assertEqual(result.log_event.predicted_aoi_id, "right_figure")
        self.assertEqual(result.log_event.confirmed_aoi_id, "bottom_caption")
        self.assertTrue(result.log_event.user_corrected)

    def test_click_required_does_not_fallback_to_whole_slide(self):
        result = run_interaction(
            transcript="解释这个",
            gaze_prediction=GazePrediction(5, "bottom_left", "bottom_formula", 0.2, stable_duration_sec=0.4),
            learning_state=LearningState(),
        )

        self.assertEqual(result.resolved_query.confirmation_mode, "click_required")
        self.assertIsNone(result.resolved_query.resolved_aoi_id)
        self.assertEqual(result.tutor_response.response_mode, "pending_confirmation")
        self.assertIsNone(result.ui_state.response["answer"])

    def test_click_required_selection_can_confirm_same_prediction(self):
        result = run_interaction(
            transcript="解释这个",
            gaze_prediction=GazePrediction(5, "bottom_left", "bottom_formula", 0.2, stable_duration_sec=0.4),
            learning_state=LearningState(),
            confirmed_aoi_id="bottom_formula",
        )

        self.assertEqual(result.resolved_query.resolved_aoi_id, "bottom_formula")
        self.assertEqual(result.log_event.confirmed_aoi_id, "bottom_formula")
        self.assertFalse(result.log_event.user_corrected)
        self.assertEqual(result.tutor_response.used_context["aoi_id"], "bottom_formula")

    def test_jsonl_logging_records_confirmation_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "interactions.jsonl"
            run_interaction(
                transcript="解释这个",
                gaze_prediction=GazePrediction(5, "middle_right", "right_figure", 0.76),
                learning_state=LearningState(),
                confirmed_aoi_id="bottom_caption",
                logger=InteractionLogger(log_path),
            )

            payload = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["predicted_aoi_id"], "right_figure")
            self.assertEqual(payload["confirmed_aoi_id"], "bottom_caption")
            self.assertTrue(payload["user_corrected"])
            self.assertEqual(payload["response_mode"], "explain")

    def test_pipeline_updates_provided_empty_history(self):
        history = InteractionHistory()
        run_interaction(
            transcript="总结这一页",
            gaze_prediction=GazePrediction(5, "middle_center", None, 0.0),
            learning_state=LearningState(),
            history=history,
        )

        self.assertEqual(len(history), 1)
        self.assertEqual(history.recent()[0]["resolved_aoi_id"], "whole_slide")

    def test_scenarios_match_expected_fields(self):
        scenarios = load_scenarios()
        self.assertGreaterEqual(len(scenarios), 5)

        for scenario in scenarios:
            with self.subTest(scenario=scenario.name):
                result = run_interaction(
                    transcript=scenario.transcript,
                    gaze_prediction=scenario.gaze_prediction,
                    learning_state=scenario.learning_state,
                    confirmed_aoi_id=scenario.confirmed_aoi_id,
                )
                expected = scenario.expected
                self.assertEqual(result.resolved_query.intent, expected["intent"])
                self.assertEqual(result.resolved_query.resolved_aoi_id, expected["resolved_aoi_id"])
                self.assertEqual(result.resolved_query.confirmation_mode, expected["confirmation_mode"])
                self.assertEqual(result.resolved_query.adaptive_strategy, expected["adaptive_strategy"])
                self.assertEqual(result.tutor_response.response_mode, expected["response_mode"])
                if "confirmed_aoi_id" in expected:
                    self.assertEqual(result.log_event.confirmed_aoi_id, expected["confirmed_aoi_id"])
                if "user_corrected" in expected:
                    self.assertEqual(result.log_event.user_corrected, expected["user_corrected"])

    def test_evaluation_scripts_report_full_accuracy(self):
        reference_eval = evaluate_scenarios()
        output_eval = evaluate_outputs()

        self.assertEqual(reference_eval["metrics"]["intent_accuracy"], 1.0)
        self.assertEqual(reference_eval["metrics"]["resolved_aoi_accuracy"], 1.0)
        self.assertEqual(reference_eval["metrics"]["confirmation_mode_accuracy"], 1.0)
        self.assertEqual(reference_eval["metrics"]["adaptive_strategy_accuracy"], 1.0)
        self.assertEqual(output_eval["output_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
