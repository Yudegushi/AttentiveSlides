"""Latest-frame live sensing worker built on the BrowserMediaSource contract."""

from __future__ import annotations

from dataclasses import dataclass
import queue
from threading import Event, RLock, Thread, current_thread
import time
from typing import Callable

from modules.human_sensing.contracts import AOI as MemberAOI
from modules.human_sensing.contracts import HumanSensingHistory
from modules.human_sensing.face_state_detector import FaceStateDetector
from modules.human_sensing.gaze_estimator import (
    FaceLandmarkExtractor,
    GazeEstimator,
    estimate_head_pose,
    map_gaze_to_aoi,
)
from modules.human_sensing.learning_state_aggregator import LearningStateAggregator
from modules.media.browser_media_source import BrowserMediaSource
from modules.system.adapters import SlideProvider
from modules.system.human_sensing_adapter import HumanSensingAdapter
from modules.system.sensing_snapshot_store import SensingSnapshotStore


@dataclass(frozen=True)
class SensingWorkerConfig:
    inference_interval_seconds: float = 0.1
    poll_interval_seconds: float = 0.02

    def __post_init__(self) -> None:
        if self.inference_interval_seconds < 0:
            raise ValueError("inference_interval_seconds must be non-negative")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")


class SensingWorker:
    """Read only the newest queued browser frame and publish canonical snapshots."""

    def __init__(
        self,
        *,
        media_source: BrowserMediaSource,
        slide_provider: SlideProvider,
        snapshot_store: SensingSnapshotStore,
        adapter: HumanSensingAdapter | None = None,
        face_landmark_extractor_factory: Callable[[], object] = FaceLandmarkExtractor,
        gaze_estimator_factory: Callable[[], object] = GazeEstimator,
        face_state_detector_factory: Callable[[], object] = FaceStateDetector,
        learning_state_aggregator_factory: Callable[[], object] = LearningStateAggregator,
        head_pose_estimator: Callable[[object], object] = estimate_head_pose,
        gaze_to_aoi: Callable[[object, list[MemberAOI]], object] = map_gaze_to_aoi,
        clock: Callable[[], float] = time.monotonic,
        config: SensingWorkerConfig | None = None,
    ) -> None:
        self.media_source = media_source
        self.slide_provider = slide_provider
        self.snapshot_store = snapshot_store
        self.adapter = adapter or HumanSensingAdapter()
        self._extractor_factory = face_landmark_extractor_factory
        self._gaze_estimator_factory = gaze_estimator_factory
        self._face_state_detector_factory = face_state_detector_factory
        self._learning_state_aggregator_factory = learning_state_aggregator_factory
        self._head_pose_estimator = head_pose_estimator
        self._gaze_to_aoi = gaze_to_aoi
        self._clock = clock
        self.config = config or SensingWorkerConfig()
        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._slide_id: int | None = None
        self._last_processed_at: float | None = None
        self._history = HumanSensingHistory()
        self._extractor: object | None = None
        self._gaze_estimator: object | None = None
        self._face_state_detector: object | None = None
        self._learning_state_aggregator: object | None = None
        self.last_error: Exception | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def set_slide(self, slide_id: int) -> None:
        if not isinstance(slide_id, int) or slide_id < 1:
            raise ValueError("slide_id must be a positive integer")
        with self._lock:
            if slide_id != self._slide_id:
                self._slide_id = slide_id
                self._history = HumanSensingHistory()
                self._last_processed_at = None
                self.snapshot_store.clear()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self.last_error = None
            self._thread = Thread(target=self._run, name="attentive-sensing", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=2.0)
        self._release_resources()

    def process_available_frame(self) -> bool:
        packet = self._latest_video_packet()
        if packet is None:
            return False
        with self._lock:
            slide_id = self._slide_id
        if slide_id is None:
            return False

        processed_at = self._clock()
        if (
            self._last_processed_at is not None
            and processed_at - self._last_processed_at < self.config.inference_interval_seconds
        ):
            return False

        self._initialize_resources()
        slide_frame = self.slide_provider.get_slide_frame(slide_id)
        member_aois = [
            MemberAOI.from_dict(
                {
                    "aoi_id": aoi.aoi_id,
                    "bbox": list(aoi.bbox),
                    "type": aoi.type,
                    "text": aoi.text,
                }
            )
            for aoi in slide_frame.aois
            if aoi.aoi_id != "whole_slide"
        ]
        landmarks = self._extractor.extract(packet.frame)
        head_pose = self._head_pose_estimator(landmarks)
        member_gaze = self._gaze_estimator.predict(
            packet.frame,
            slide_id=slide_id,
            face_landmarks=landmarks,
            head_pose=head_pose,
        )
        member_aoi_prediction = self._gaze_to_aoi(member_gaze, member_aois)
        face_state = self._face_state_detector.detect_face_state_signals(
            face_landmarks=landmarks,
            history=self._history,
            head_pose=head_pose,
            timestamp=packet.timestamp,
        )
        member_learning = self._learning_state_aggregator.aggregate(
            face_state=face_state,
            history=self._history,
            gaze_prediction=member_aoi_prediction,
        )
        adapted = self.adapter.adapt(member_aoi_prediction, member_learning)

        with self._lock:
            if slide_id != self._slide_id:
                return False
        self.snapshot_store.put(
            self.snapshot_store.snapshot(
                slide_id=slide_id,
                source_timestamp=packet.timestamp,
                source_timestamp_clock=packet.timestamp_clock,
                frame=adapted.frame,
                is_valid=adapted.is_valid,
                invalid_reason=adapted.invalid_reason,
            )
        )
        self._last_processed_at = processed_at
        return True

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self.process_available_frame()
                self._stop_event.wait(self.config.poll_interval_seconds)
        except Exception as exc:
            with self._lock:
                self.last_error = exc
            self._stop_event.set()
        finally:
            self._release_resources()

    def _latest_video_packet(self):
        latest = None
        while True:
            try:
                latest = self.media_source.video_queue.get_nowait()
            except queue.Empty:
                return latest

    def _initialize_resources(self) -> None:
        with self._lock:
            if self._extractor is None:
                self._extractor = self._extractor_factory()
                self._gaze_estimator = self._gaze_estimator_factory()
                self._face_state_detector = self._face_state_detector_factory()
                self._learning_state_aggregator = self._learning_state_aggregator_factory()

    def _release_resources(self) -> None:
        with self._lock:
            extractor = self._extractor
            self._extractor = None
            self._gaze_estimator = None
            self._face_state_detector = None
            self._learning_state_aggregator = None
            if self._thread is not None and not self._thread.is_alive():
                self._thread = None
        if extractor is not None:
            close = getattr(extractor, "close", None)
            if callable(close):
                close()
