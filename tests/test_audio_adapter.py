import unittest

from modules.audio.mock_transcriber import MockTranscriber
from modules.common.schemas import GazePrediction, LearningState
from modules.system.adapters import MockManifestSlideProvider, SensingFrame, build_pipeline_input_bundle, run_interaction_from_bundle
from modules.system.audio_adapters import AudioFileTranscriptProvider


class PresetSensingProvider:
    def get_sensing_frame(self, slide_id: int) -> SensingFrame:
        return SensingFrame(
            gaze_prediction=GazePrediction(slide_id, "middle_right", "right_figure", 0.76, stable_duration_sec=2.3),
            learning_state=LearningState(),
        )


class AudioAdapterTest(unittest.TestCase):
    def test_audio_file_transcript_provider_returns_transcriber_result(self):
        provider = AudioFileTranscriptProvider(
            audio_path="data/audio_samples/right_figure.wav",
            transcriber=MockTranscriber(),
        )

        transcript = provider.get_transcript()

        self.assertEqual(transcript.text, "讲讲右边这个图")
        self.assertEqual(transcript.language, "zh")

    def test_audio_transcript_enters_existing_pipeline_through_adapters(self):
        bundle = build_pipeline_input_bundle(
            slide_provider=MockManifestSlideProvider(),
            transcript_provider=AudioFileTranscriptProvider("data/audio_samples/right_figure.wav", MockTranscriber()),
            sensing_provider=PresetSensingProvider(),
            slide_id=5,
        )

        result = run_interaction_from_bundle(bundle)

        self.assertEqual(bundle.transcript, "讲讲右边这个图")
        self.assertEqual(result.resolved_query.intent, "explain")
        self.assertEqual(result.resolved_query.resolved_aoi_id, "right_figure")
        self.assertEqual(result.tutor_response.response_mode, "explain")


if __name__ == "__main__":
    unittest.main()
