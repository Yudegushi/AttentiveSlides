import unittest

from modules.common.schemas import AOI, GazePrediction, LearningState, VisualContextItem
from modules.system.adapters import (
    MockManifestSlideProvider,
    PipelineInputBundle,
    ProviderBackedDeckStore,
    ScenarioSensingProvider,
    ScenarioTranscriptProvider,
    build_pipeline_input_bundle,
    run_interaction_from_bundle,
    SlideFrame,
)
from modules.system.pipeline import run_interaction
from modules.system.scenarios import load_scenarios


class SystemAdaptersTest(unittest.TestCase):
    def test_manifest_slide_provider_returns_internal_slide_frame(self):
        provider = MockManifestSlideProvider()

        frame = provider.get_slide_frame(5)

        self.assertEqual(frame.deck_id, "mock_deck")
        self.assertEqual(frame.slide_id, 5)
        self.assertTrue(frame.slide_text)
        self.assertTrue(frame.slide_image_path.endswith("slide_005.png"))
        self.assertIn("right_figure", {aoi.aoi_id for aoi in frame.aois})
        self.assertTrue(all(isinstance(aoi, AOI) for aoi in frame.aois))

    def test_scenario_providers_return_transcript_and_sensing_frame(self):
        scenario = load_scenarios()[0]

        transcript = ScenarioTranscriptProvider(scenario).get_transcript()
        sensing = ScenarioSensingProvider(scenario).get_sensing_frame(slide_id=5)

        self.assertEqual(transcript.text, scenario.transcript)
        self.assertIsInstance(sensing.gaze_prediction, GazePrediction)
        self.assertIsInstance(sensing.learning_state, LearningState)
        self.assertEqual(sensing.gaze_prediction.slide_id, 5)

    def test_provider_backed_deck_store_matches_manifest_contract(self):
        store = ProviderBackedDeckStore(MockManifestSlideProvider())

        slide = store.get_slide(5)
        aois = store.get_aois(5)

        self.assertEqual(store.deck_id, "mock_deck")
        self.assertEqual(slide["slide_id"], 5)
        self.assertEqual(slide["ocr_text"], store.get_slide(5)["ocr_text"])
        self.assertIn("neighbor_slide_text", slide)
        self.assertIn("aois", slide)
        self.assertTrue(all(isinstance(aoi, AOI) for aoi in aois))

    def test_provider_backed_store_preserves_visual_context(self):
        visual = VisualContextItem(
            visual_id="visual_1",
            type="diagram",
            bbox=[0.2, 0.3, 0.7, 0.6],
            description="A flow diagram.",
        )

        class Provider:
            deck_id = "deck"

            def get_slide_frame(self, slide_id):
                return SlideFrame(
                    deck_id="deck",
                    slide_id=slide_id,
                    aois=[],
                    slide_text="text",
                    visual_context=(visual,),
                )

        slide = ProviderBackedDeckStore(Provider()).get_slide(1)

        self.assertEqual(slide["visual_context"], [visual.to_dict()])

    def test_build_pipeline_input_bundle_can_run_existing_pipeline(self):
        scenario = load_scenarios()[0]
        bundle = build_pipeline_input_bundle(
            slide_provider=MockManifestSlideProvider(),
            transcript_provider=ScenarioTranscriptProvider(scenario),
            sensing_provider=ScenarioSensingProvider(scenario),
            slide_id=5,
        )

        self.assertIsInstance(bundle, PipelineInputBundle)
        self.assertEqual(bundle.transcript, scenario.transcript)
        self.assertEqual(bundle.deck_id, "mock_deck")
        self.assertEqual(bundle.slide_id, 5)

        result = run_interaction_from_bundle(bundle)

        self.assertEqual(result.tutor_response.response_mode, "pending_confirmation")
        self.assertIsNone(result.ui_state.response["answer"])

    def test_adapter_driven_scenarios_match_direct_pipeline_results(self):
        slide_provider = MockManifestSlideProvider()

        for scenario in load_scenarios():
            with self.subTest(scenario=scenario.name):
                bundle = build_pipeline_input_bundle(
                    slide_provider=slide_provider,
                    transcript_provider=ScenarioTranscriptProvider(scenario),
                    sensing_provider=ScenarioSensingProvider(scenario),
                    slide_id=5,
                )
                adapter_result = run_interaction_from_bundle(
                    bundle,
                    confirmed_aoi_id=scenario.confirmed_aoi_id,
                )
                direct_result = run_interaction(
                    transcript=scenario.transcript,
                    gaze_prediction=scenario.gaze_prediction,
                    learning_state=scenario.learning_state,
                    confirmed_aoi_id=scenario.confirmed_aoi_id,
                )

                self.assertEqual(adapter_result.resolved_query.intent, direct_result.resolved_query.intent)
                self.assertEqual(
                    adapter_result.resolved_query.resolved_aoi_id,
                    direct_result.resolved_query.resolved_aoi_id,
                )
                self.assertEqual(
                    adapter_result.resolved_query.confirmation_mode,
                    direct_result.resolved_query.confirmation_mode,
                )
                self.assertEqual(
                    adapter_result.resolved_query.adaptive_strategy,
                    direct_result.resolved_query.adaptive_strategy,
                )
                self.assertEqual(
                    adapter_result.tutor_response.response_mode,
                    direct_result.tutor_response.response_mode,
                )


if __name__ == "__main__":
    unittest.main()
