import builtins
import tempfile
import unittest
from unittest import mock

from modules.common.schemas import Transcript
from modules.audio.faster_whisper_transcriber import FasterWhisperTranscriber
from modules.audio.mock_transcriber import MockTranscriber
from modules.audio.transcriber import TranscriptionConfig
from modules.interaction.speech_to_text import transcribe_audio


class AudioTranscriberTest(unittest.TestCase):
    def test_mock_transcriber_returns_known_transcript(self):
        transcriber = MockTranscriber()

        transcript = transcriber.transcribe("data/audio_samples/explain_this.wav")

        self.assertEqual(transcript, Transcript(text="解释一下这个", language="zh", confidence=None))

    def test_mock_transcriber_reports_unknown_sample(self):
        transcriber = MockTranscriber()

        with self.assertRaisesRegex(ValueError, "No mock transcript configured"):
            transcriber.transcribe("data/audio_samples/not_configured.wav")

    def test_public_transcribe_audio_uses_mock_engine(self):
        transcript = transcribe_audio(
            "data/audio_samples/summarize_slide.wav",
            TranscriptionConfig(engine="mock"),
        )

        self.assertEqual(transcript.text, "总结一下这一页")
        self.assertEqual(transcript.language, "zh")
        self.assertIsNone(transcript.confidence)

    def test_unknown_transcription_engine_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported STT engine"):
            transcribe_audio("data/audio_samples/explain_this.wav", TranscriptionConfig(engine="other"))

    def test_faster_whisper_missing_dependency_fails_at_runtime(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ModuleNotFoundError("No module named 'faster_whisper'")
            return original_import(name, *args, **kwargs)

        with tempfile.NamedTemporaryFile(suffix=".wav") as audio_file:
            with mock.patch("builtins.__import__", side_effect=fake_import):
                transcriber = FasterWhisperTranscriber(TranscriptionConfig(engine="faster_whisper"))
                with self.assertRaisesRegex(RuntimeError, "Install optional audio dependencies"):
                    transcriber.transcribe(audio_file.name)

    def test_faster_whisper_checks_missing_audio_file_before_loading_model(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ModuleNotFoundError("No module named 'faster_whisper'")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            transcriber = FasterWhisperTranscriber(TranscriptionConfig(engine="faster_whisper"))
            with self.assertRaisesRegex(FileNotFoundError, "Audio file not found"):
                transcriber.transcribe("data/audio_samples/missing.wav")

    def test_faster_whisper_missing_audio_file_has_clear_error(self):
        class LoadedModelTranscriber(FasterWhisperTranscriber):
            def _load_model(self):
                class FakeModel:
                    def transcribe(self, *args, **kwargs):
                        return [], object()

                return FakeModel()

        transcriber = LoadedModelTranscriber(TranscriptionConfig(engine="faster_whisper"))

        with self.assertRaisesRegex(FileNotFoundError, "Audio file not found"):
            transcriber.transcribe("data/audio_samples/missing.wav")


if __name__ == "__main__":
    unittest.main()
