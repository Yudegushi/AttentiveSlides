from io import BytesIO
from pathlib import Path
import tempfile
import time
import unittest

import fitz
import numpy as np
from PIL import Image

from modules.audio.voice_turn_detector import VoiceTurnDetector, VoiceTurnDetectorConfig
from modules.common.schemas import GazePrediction, LearningState, Transcript
from modules.human_sensing.contracts import (
    AOIPrediction as MemberAOIPrediction,
    FaceStateSignals,
    GazePrediction as MemberGazePrediction,
    LearningState as MemberLearningState,
)
from modules.logging.interaction_logger import InteractionLogger
from modules.media import BrowserMediaSource
from modules.media.live_ingress_service import LiveIngressService
from modules.media.single_port_transport import FallbackMediaIngress
from modules.system.adapters import SensingFrame
from modules.system.audio_worker import AudioWorker
from modules.system.controller import SystemController
from modules.system.live_turn_runner import LiveTurnRunner
from modules.system.real_slide_provider import RealSlideProvider
from modules.system.sensing_snapshot_store import SensingSnapshot, SensingSnapshotStore
from modules.system.sensing_worker import SensingWorker, SensingWorkerConfig
from modules.system.turn_context import TurnContextCollector, manifest_identity_for_frame
from modules.system.live_view_model import LiveViewModel
from modules.tutor.tutor_agent import TutorAgent


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


class FakeExtractor:
    def __init__(self):
        self.values = []
        self.closed = 0

    def extract(self, frame):
        self.values.append(int(frame[0, 0, 0]))
        return object()

    def close(self):
        self.closed += 1


class FakeGazeEstimator:
    def predict(self, _frame, **_kwargs):
        return MemberGazePrediction(
            timestamp=2.0,
            slide_id=1,
            gaze_grid="middle_center",
            confidence=0.8,
            stable_duration_sec=2.0,
        )


class FakeFaceStateDetector:
    def detect_face_state_signals(self, **kwargs):
        return FaceStateSignals(
            timestamp=kwargs["timestamp"],
            face_detected=True,
            screen_facing_score=0.9,
            yawn_detected=False,
            yawn_count_last_3min=0,
            eyes_closed=False,
            eye_closure_duration_sec=0.0,
            head_down=False,
            mouth_aspect_ratio=0.1,
            eye_aspect_ratio=0.3,
        )


class FakeLearningAggregator:
    def aggregate(self, face_state, **_kwargs):
        return MemberLearningState(
            timestamp=face_state.timestamp,
            face_detected=True,
            screen_facing_score=face_state.screen_facing_score,
            yawn_detected=False,
            yawn_count_last_3min=0,
            eyes_closed=False,
            eye_closure_duration_sec=0.0,
            head_down=False,
            fatigue_signal_score=0.1,
            possible_review_needed=False,
        )


def make_pdf(path):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Live concept", fontsize=24)
    page.insert_text((72, 160), "Explained evidence", fontsize=16)
    document.save(path)
    document.close()


def jpeg_payload() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(output, format="JPEG")
    return output.getvalue()


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return None


class LiveIntegratedTurnTest(unittest.TestCase):
    def test_shared_http_ingress_runs_real_workers_correction_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "deck.pdf"
            make_pdf(pdf)
            provider = RealSlideProvider(data_dir=root / "data")
            provider.load_deck(pdf)
            frame = provider.get_slide_frame(1)
            region_ids = [aoi.aoi_id for aoi in frame.aois if aoi.aoi_id != "whole_slide"]
            self.assertTrue(region_ids)
            predicted_aoi_id = region_ids[0]
            confirmed_aoi_id = region_ids[1] if len(region_ids) > 1 else "whole_slide"
            self.assertNotEqual(confirmed_aoi_id, predicted_aoi_id)

            source = BrowserMediaSource()
            store = SensingSnapshotStore(stale_after_seconds=5.0)
            collector = TurnContextCollector(
                slide_provider=provider,
                snapshot_store=store,
                minimum_dwell_seconds=0.01,
            )
            factories = {"extractor": 0, "gaze": 0, "face": 0, "learning": 0}
            extractors = []

            def extractor_factory():
                factories["extractor"] += 1
                extractor = FakeExtractor()
                extractors.append(extractor)
                return extractor

            def gaze_factory():
                factories["gaze"] += 1
                return FakeGazeEstimator()

            def face_factory():
                factories["face"] += 1
                return FakeFaceStateDetector()

            def learning_factory():
                factories["learning"] += 1
                return FakeLearningAggregator()

            def map_to_predicted(gaze, aois):
                self.assertIn(predicted_aoi_id, [aoi.aoi_id for aoi in aois])
                return MemberAOIPrediction(
                    timestamp=gaze.timestamp,
                    slide_id=gaze.slide_id,
                    gaze_grid=gaze.gaze_grid,
                    predicted_aoi_id=predicted_aoi_id,
                    confidence=0.8,
                    stable_duration_sec=gaze.stable_duration_sec,
                    candidate_scores={predicted_aoi_id: 0.8},
                )

            sensing = SensingWorker(
                media_source=source,
                slide_provider=provider,
                snapshot_store=store,
                face_landmark_extractor_factory=extractor_factory,
                gaze_estimator_factory=gaze_factory,
                face_state_detector_factory=face_factory,
                learning_state_aggregator_factory=learning_factory,
                head_pose_estimator=lambda _landmarks: None,
                gaze_to_aoi=map_to_predicted,
                config=SensingWorkerConfig(
                    inference_interval_seconds=0.0,
                    poll_interval_seconds=0.01,
                ),
            )
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
                transcribe=lambda _path: Transcript("解释一下这里"),
            )
            log_path = root / "live.jsonl"
            runner = LiveTurnRunner(
                slide_provider=provider,
                context_collector=collector,
                tutor=TutorAgent(),
                logger=InteractionLogger(log_path),
            )
            controller = SystemController(
                media_source=source,
                sensing_worker=sensing,
                audio_worker=audio,
                context_collector=collector,
                turn_runner=runner,
            )
            view = LiveViewModel(
                controller=controller,
                media_source=source,
                slide_provider=provider,
                snapshot_store=store,
            )
            view.set_slide(1)
            ingress = FallbackMediaIngress(
                source,
                start_armed=False,
                coordinated_activation=True,
                media_stale_after_seconds=2.0,
                inactive_after_seconds=3.0,
            )
            service = LiveIngressService(
                runtime=view,
                source=source,
                ingress=ingress,
            )

            service.set_master_enabled(True)
            ingress.start("session-a")
            service.reconcile_once()
            ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
            ingress.accept_audio_pcm(
                "session-a",
                np.zeros(480, dtype="<i2").tobytes(),
                timestamp=1.0,
                sample_rate=16_000,
                channels=1,
            )
            service.reconcile_once()
            self.assertEqual(controller.state.value, "monitoring")
            self.assertIsNotNone(
                wait_until(lambda: store.latest_valid_for_slide(1))
            )
            self.assertEqual(factories, {"extractor": 1, "gaze": 1, "face": 1, "learning": 1})

            speech = np.concatenate(
                [np.full(480, 1_000, dtype=np.int16), np.zeros(480, dtype=np.int16)]
            )
            ingress.accept_audio_pcm(
                "session-a",
                speech.astype("<i2").tobytes(),
                timestamp=1.03,
                sample_rate=16_000,
                channels=1,
            )
            ingress.heartbeat("session-a")

            pending = wait_until(
                lambda: (outcomes[0] if (outcomes := controller.poll()) else None)
            )
            self.assertIsNotNone(pending)
            self.assertTrue(pending.pending_confirmation)
            self.assertEqual(
                pending.interaction_result.resolved_query.resolved_aoi_id,
                predicted_aoi_id,
            )
            final = controller.confirm(
                pending.interaction_result.resolved_query.query_id,
                confirmed_aoi_id,
            )

            self.assertTrue(final.interaction_result.log_event.user_corrected)
            self.assertEqual(
                final.interaction_result.resolved_query.resolved_aoi_id,
                confirmed_aoi_id,
            )
            self.assertNotEqual(confirmed_aoi_id, predicted_aoi_id)
            self.assertEqual(controller.state.value, "monitoring")
            self.assertGreaterEqual(len(log_path.read_text().splitlines()), 2)

            service.set_master_enabled(False)
            service.reconcile_once()
            self.assertEqual(controller.state.value, "stopped")
            self.assertFalse(audio.is_running)
            self.assertFalse(sensing.is_running)
            self.assertFalse(ingress.session_snapshot().active)
            self.assertFalse(source.is_running)
            self.assertTrue(source.video_queue.empty())
            self.assertTrue(source.audio_queue.empty())
            self.assertEqual(extractors[0].closed, 1)

            service.set_master_enabled(True)
            ingress.start("session-b")
            service.reconcile_once()
            ingress.accept_video_jpeg("session-b", jpeg_payload(), timestamp=2.0)
            ingress.accept_audio_pcm(
                "session-b",
                np.zeros(480, dtype="<i2").tobytes(),
                timestamp=2.0,
                sample_rate=16_000,
                channels=1,
            )
            service.reconcile_once()
            self.assertEqual(controller.state.value, "monitoring")
            self.assertEqual(audio.start_count, 2)
            self.assertFalse(detector.has_active_turn)
            service.set_master_enabled(False)
            service.reconcile_once()

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
