import unittest

from modules.system.demo_view_model import build_interaction_view_model, run_scenario_turn
from modules.system.scenarios import load_scenarios


class DemoViewModelTest(unittest.TestCase):
    def test_pending_confirmation_view_model_hides_final_answer(self):
        scenario = load_scenarios()[0]

        result = run_scenario_turn(scenario)
        view_model = build_interaction_view_model(result, scenario)

        self.assertTrue(view_model["pending_confirmation"])
        self.assertIsNone(view_model["response"]["answer"])
        self.assertEqual(view_model["confirmation_mode"], "confirm_one")
        self.assertEqual(view_model["confirmation_options"][0]["aoi_id"], "right_figure")
        self.assertEqual(view_model["expected_actual"]["response_mode"]["actual"], "pending_confirmation")
        self.assertTrue(view_model["expected_actual"]["response_mode"]["matches"])

    def test_confirmed_view_model_exposes_grounded_answer_and_correction(self):
        scenario = load_scenarios()[0]

        result = run_scenario_turn(scenario, confirmed_aoi_id="bottom_caption")
        view_model = build_interaction_view_model(result, scenario)

        self.assertFalse(view_model["pending_confirmation"])
        self.assertEqual(view_model["highlighted_aoi_id"], "bottom_caption")
        self.assertIn("Bottom caption", view_model["response"]["answer"])
        self.assertEqual(view_model["actual"]["confirmed_aoi_id"], "bottom_caption")
        self.assertTrue(view_model["actual"]["user_corrected"])

    def test_click_required_view_model_offers_all_slide_aois(self):
        scenario = next(item for item in load_scenarios() if item.name == "click-required low confidence waits for selection")

        result = run_scenario_turn(scenario)
        view_model = build_interaction_view_model(result, scenario)

        self.assertTrue(view_model["pending_confirmation"])
        self.assertEqual(view_model["confirmation_mode"], "click_required")
        self.assertGreaterEqual(len(view_model["confirmation_options"]), 5)
        self.assertIn("bottom_formula", {option["aoi_id"] for option in view_model["confirmation_options"]})

    def test_run_scenario_turn_uses_adapter_boundary_without_changing_output(self):
        scenario = load_scenarios()[0]

        result = run_scenario_turn(scenario)
        view_model = build_interaction_view_model(result, scenario)

        self.assertEqual(view_model["actual"]["response_mode"], "pending_confirmation")
        self.assertEqual(view_model["actual"]["resolved_aoi_id"], "right_figure")
        self.assertIsNone(view_model["response"]["answer"])


if __name__ == "__main__":
    unittest.main()
