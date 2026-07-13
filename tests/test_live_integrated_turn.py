from pathlib import Path
import tempfile
import unittest

import fitz
import numpy as np

from modules.audio.voice_turn_detector import VoiceTurnDetector, VoiceTurnDetectorConfig
from modules.common.schemas import GazePrediction, LearningState, Transcript
from modules.logging.interaction_logger import InteractionLogger
from modules.media import BrowserMediaSource
from modules.system.adapters import SensingFrame
from modules.system.audio_worker import AudioWorker
from modules.system.controller import SystemController
from modules.system.live_turn_runner import LiveTurnRunner
from modules.system.real_slide_provider import RealSlideProvider
from modules.system.sensing_snapshot_store import SensingSnapshot, SensingSnapshotStore
from modules.system.turn_context import TurnContextCollector, manifest_identity_for_frame


class AmplitudeVad:
    def is_speech(self, pcm_frame, sample_rate):
        return bool(np.max(np.abs(pcm_frame)) >= 100)


class NoopSensingWorker:
    def set_slide(self, slide_id):
        self.slide_id = slide_id

    def start(self):
        pass

    def stop(self):
        pass


def make_pdf(path):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Live concept", fontsize=24)
    page.insert_text((72, 160), "Explained evidence", fontsize=16)
    document.save(path)
    document.close()


class LiveIntegratedTurnTest(unittest.TestCase):
    def test_real_pdf_synthetic_sensing_pcm_turn_confirmation_log_and_monitoring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "deck.pdf"
            make_pdf(pdf)
            provider = RealSlideProvider(data_dir=root / "data")
            provider.load_deck(pdf)
            frame = provider.get_slide_frame(1)
            target = next(aoi.aoi_id for aoi in frame.aois if aoi.aoi_id != "whole_slide")
            store = SensingSnapshotStore(stale_after_seconds=5.0)
            collector = TurnContextCollector(
                slide_provider=provider,
                snapshot_store=store,
                minimum_dwell_seconds=0.05,
            )
            identity = manifest_identity_for_frame(frame)
            store.put(
                SensingSnapshot(
                    slide_id=1,
                    source_timestamp=1.0,
                    source_timestamp_clock="browser_performance_seconds",
                    processed_at=9.9,
                    frame=SensingFrame(
                        gaze_prediction=GazePrediction(1, "middle_center", target, 0.9),
                        learning_state=LearningState(),
                    ),
                    is_valid=True,
                    invalid_reason=None,
                    manifest_identity=identity,
                )
            )
            source = BrowserMediaSource()
            detector = VoiceTurnDetector(
                AmplitudeVad(),
                config=VoiceTurnDetectorConfig(
                    pre_roll_ms=30,
                    speech_start_window_ms=30,
                    speech_end_silence_ms=30,
                    minimum_utterance_ms=30,
                ),
            )
            audio = AudioWorker(
                media_source=source,
                detector=detector,
                transcribe=lambda path: Transcript("解释这个"),
                clock=lambda: 10.0,
            )
            log_path = root / "live.jsonl"
            runner = LiveTurnRunner(
                slide_provider=provider,
                context_collector=collector,
                logger=InteractionLogger(log_path),
            )
            controller = SystemController(
                media_source=source,
                sensing_worker=NoopSensingWorker(),
                audio_worker=audio,
                context_collector=collector,
                turn_runner=runner,
            )
            controller.set_slide(1)
            controller.start()
            pcm = np.concatenate(
                [np.full(480, 1_000, dtype=np.int16), np.zeros(480, dtype=np.int16)]
            ).reshape(-1, 1)
            source.accept_audio_samples(
                pcm,
                timestamp=1.0,
                sample_rate=16_000,
                channels=1,
                timestamp_clock="browser_performance_seconds",
            )

            audio.process_available_audio()
            pending = controller.poll()[0]
            final = controller.confirm(
                pending.interaction_result.resolved_query.query_id,
                target,
            )

            self.assertFalse(final.pending_confirmation)
            self.assertEqual(final.interaction_result.tutor_response.response_mode, "explain")
            self.assertEqual(controller.state.value, "monitoring")
            self.assertEqual(len(log_path.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
