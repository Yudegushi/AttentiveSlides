"""Same-origin HTTP fallback for browser media on a single SSH-forwarded port."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
import math
from threading import RLock
import time
from typing import Callable

import cv2
import numpy as np
from aiohttp import web

from .browser_gaze_source import (
    BrowserGazeSource,
    BrowserGeometrySnapshot,
    BrowserPointGazeSample,
)
from .browser_media_source import BrowserMediaSource


SESSION_HEADER = "X-Attentive-Media-Session"
TIMESTAMP_HEADER = "X-Media-Timestamp"
SAMPLE_RATE_HEADER = "X-Media-Sample-Rate"
CHANNELS_HEADER = "X-Media-Channels"


class MediaIngressError(ValueError):
    """A browser media request does not satisfy the fallback contract."""


class InactiveMediaSession(MediaIngressError):
    """A request belongs to a superseded, stopped, or missing browser session."""


class MediaPayloadTooLarge(MediaIngressError):
    """A browser media body exceeds the documented bounded request size."""


@dataclass(frozen=True)
class MediaIngressSessionSnapshot:
    armed: bool
    active: bool
    generation: int | None
    pending_generation: int | None
    session_pending: bool
    video_fresh: bool
    audio_fresh: bool
    fatigue_fresh: bool
    heartbeat_fresh: bool
    last_video_received_at: float | None
    last_audio_received_at: float | None
    last_fatigue_received_at: float | None
    last_heartbeat_at: float | None
    cleanup_reason: str | None


class FallbackMediaIngress:
    """Accept bounded browser chunks and feed the existing source queues."""

    def __init__(
        self,
        source: BrowserMediaSource,
        *,
        observations: BrowserGazeSource | None = None,
        clock: Callable[[], float] = time.monotonic,
        inactive_after_seconds: float = 2.0,
        media_stale_after_seconds: float = 2.0,
        start_armed: bool = True,
        coordinated_activation: bool = False,
        max_video_bytes: int = 512 * 1024,
        max_audio_bytes: int = 128 * 1024,
        max_fatigue_bytes: int = 256 * 1024,
        max_input_pixels: int = 640 * 480,
    ) -> None:
        if inactive_after_seconds <= 0:
            raise ValueError("inactive_after_seconds must be positive")
        if media_stale_after_seconds <= 0:
            raise ValueError("media_stale_after_seconds must be positive")
        if max_video_bytes <= 0 or max_audio_bytes <= 0 or max_fatigue_bytes <= 0:
            raise ValueError("media byte limits must be positive")
        self.source = source
        self.observations = observations or BrowserGazeSource(clock=clock)
        self._clock = clock
        self.inactive_after_seconds = float(inactive_after_seconds)
        self.media_stale_after_seconds = float(media_stale_after_seconds)
        self.max_video_bytes = int(max_video_bytes)
        self.max_audio_bytes = int(max_audio_bytes)
        self.max_fatigue_bytes = int(max_fatigue_bytes)
        self.max_input_pixels = int(max_input_pixels)
        self._lock = RLock()
        self._armed = bool(start_armed)
        self._coordinated_activation = bool(coordinated_activation)
        self._generation_counter = 0
        self._active_session_id: str | None = None
        self._active_generation: int | None = None
        self._pending_session_id: str | None = None
        self._pending_generation: int | None = None
        self._last_video_received_at: float | None = None
        self._last_audio_received_at: float | None = None
        self._last_fatigue_received_at: float | None = None
        self._last_heartbeat_at: float | None = None
        self._cleanup_reason: str | None = None

    def arm(self) -> None:
        with self._lock:
            self._armed = True

    def disarm(self, *, reason: str = "master switch off") -> None:
        with self._lock:
            self._armed = False
            self._clear_sessions(reason=reason)

    def start(self, session_id: str) -> None:
        """Activate one browser session, replacing any previous session safely."""

        session_id = self._validated_session_id(session_id)
        with self._lock:
            if not self._armed:
                raise InactiveMediaSession("browser media ingress is not armed")
            if session_id in {self._active_session_id, self._pending_session_id}:
                return
            self.observations.clear_gaze()
            replacing_session = self._active_session_id is not None or self._pending_session_id is not None
            if replacing_session:
                self.source.stop(reason="browser session replaced")
            self._generation_counter += 1
            generation = self._generation_counter
            self._active_session_id = None
            self._active_generation = None
            self._reset_receive_times()
            self._cleanup_reason = "browser session replaced" if replacing_session else None
            if self._coordinated_activation:
                self._pending_session_id = session_id
                self._pending_generation = generation
                return
            self._pending_session_id = None
            self._pending_generation = None
            self._active_session_id = session_id
            self._active_generation = generation
            self._last_heartbeat_at = self._clock()
            self.source.start()

    def activate_pending(self) -> bool:
        with self._lock:
            if not self._armed or self._pending_session_id is None:
                return False
            self._active_session_id = self._pending_session_id
            self._active_generation = self._pending_generation
            self._pending_session_id = None
            self._pending_generation = None
            self._reset_receive_times()
            self._last_heartbeat_at = self._clock()
            self._cleanup_reason = None
            self.source.start()
            return True

    def stop(self, session_id: str, *, reason: str = "browser stopped") -> None:
        """Stop the active session. A stale page is never allowed to stop a newer one."""

        with self._lock:
            if session_id == self._pending_session_id:
                self._clear_sessions(reason=reason)
                return
            self._require_active_session(session_id)
            self._clear_sessions(reason=reason)

    def stop_active(self, *, reason: str) -> bool:
        with self._lock:
            if self._active_session_id is None and self._pending_session_id is None:
                return False
            self._clear_sessions(reason=reason)
            return True

    def reset_active_readiness(self, *, reason: str) -> bool:
        """Require new media packets without replacing the browser session."""

        with self._lock:
            if self._active_session_id is None:
                return False
            self._last_video_received_at = None
            self._last_audio_received_at = None
            self._last_fatigue_received_at = None
            self._cleanup_reason = reason
            self.source.start()
            return True

    def heartbeat(self, session_id: str) -> None:
        with self._lock:
            self._require_active_session(session_id)
            self._last_heartbeat_at = self._clock()

    def stop_if_inactive(self) -> bool:
        """Apply disconnect cleanup when no browser activity arrives for the deadline."""

        with self._lock:
            if self._active_session_id is None or self._last_heartbeat_at is None:
                return False
            if self._clock() - self._last_heartbeat_at < self.inactive_after_seconds:
                return False
            self._clear_sessions(reason="browser inactive")
            return True

    def accept_video_jpeg(
        self,
        session_id: str,
        payload: bytes,
        *,
        timestamp: float,
    ) -> bool:
        """Decode one limited JPEG payload into the canonical BGR frame packet."""

        if len(payload) > self.max_video_bytes:
            raise MediaPayloadTooLarge("video payload exceeds byte limit")
        timestamp = self._validated_timestamp(timestamp)
        frame = self._decode_video(payload)
        with self._lock:
            self._require_active_session(session_id)
            accepted = self.source.accept_video_frame(
                frame,
                timestamp=timestamp,
                timestamp_clock="browser_performance_seconds",
            )
            self._last_video_received_at = self._clock()
            return accepted

    def accept_audio_pcm(
        self,
        session_id: str,
        payload: bytes,
        *,
        timestamp: float,
        sample_rate: int,
        channels: int,
    ) -> bool:
        """Accept one bounded 16 kHz mono little-endian signed-16 PCM chunk."""

        if len(payload) > self.max_audio_bytes:
            raise MediaPayloadTooLarge("audio payload exceeds byte limit")
        if sample_rate != 16_000:
            raise MediaIngressError("audio sample rate must be 16000 Hz")
        if channels != 1:
            raise MediaIngressError("audio channel count must be 1")
        sample_width = np.dtype("<i2").itemsize * channels
        if not payload or len(payload) % sample_width:
            raise MediaIngressError("audio payload is not aligned signed-16 PCM")
        timestamp = self._validated_timestamp(timestamp)
        samples = np.frombuffer(payload, dtype="<i2").reshape(-1, channels)
        with self._lock:
            self._require_active_session(session_id)
            accepted = self.source.accept_audio_samples(
                samples,
                timestamp=timestamp,
                sample_rate=sample_rate,
                channels=channels,
                timestamp_clock="browser_performance_seconds",
            )
            self._last_audio_received_at = self._clock()
            return accepted

    def accept_fatigue_jpeg(
        self,
        session_id: str,
        payload: bytes,
        *,
        timestamp: float,
    ) -> bool:
        """Decode one bounded exact-size face crop for fatigue inference."""

        if len(payload) > self.max_fatigue_bytes:
            raise MediaPayloadTooLarge("fatigue payload exceeds byte limit")
        timestamp = self._validated_timestamp(timestamp)
        image = self._decode_fatigue(payload)
        with self._lock:
            self._require_active_session(session_id)
            accepted = self.source.accept_face_crop(
                image,
                timestamp=timestamp,
                timestamp_clock="browser_performance_seconds",
            )
            self._last_fatigue_received_at = self._clock()
            return accepted

    def accept_geometry_json(
        self,
        payload: Mapping[str, object],
    ) -> BrowserGeometrySnapshot:
        return self.observations.accept_geometry(payload)

    def accept_gaze_json(
        self,
        session_id: str,
        payload: Mapping[str, object],
    ) -> BrowserPointGazeSample:
        with self._lock:
            self._require_active_session(session_id)
        return self.observations.accept_gaze(payload)

    def session_snapshot(self) -> MediaIngressSessionSnapshot:
        with self._lock:
            now = self._clock()
            active = self._active_session_id is not None
            return MediaIngressSessionSnapshot(
                armed=self._armed,
                active=active,
                generation=self._active_generation,
                pending_generation=self._pending_generation,
                session_pending=self._pending_session_id is not None,
                video_fresh=active and self._is_fresh(self._last_video_received_at, now, self.media_stale_after_seconds),
                audio_fresh=active and self._is_fresh(self._last_audio_received_at, now, self.media_stale_after_seconds),
                fatigue_fresh=active and self._is_fresh(self._last_fatigue_received_at, now, self.media_stale_after_seconds),
                heartbeat_fresh=active and self._is_fresh(self._last_heartbeat_at, now, self.inactive_after_seconds),
                last_video_received_at=self._last_video_received_at,
                last_audio_received_at=self._last_audio_received_at,
                last_fatigue_received_at=self._last_fatigue_received_at,
                last_heartbeat_at=self._last_heartbeat_at,
                cleanup_reason=self._cleanup_reason,
            )

    def stats_payload(self) -> dict[str, object]:
        stats = self.source.stats()
        session = self.session_snapshot()
        observation_stats = self.observations.stats()
        return {
            "transport": "single-port-http",
            "active_session": session.active,
            "armed": session.armed,
            "session_state": "pending" if session.session_pending else ("active" if session.active else "inactive"),
            "generation": session.generation if session.generation is not None else session.pending_generation,
            "video_fresh": session.video_fresh,
            "audio_fresh": session.audio_fresh,
            "fatigue_fresh": session.fatigue_fresh,
            "heartbeat_fresh": session.heartbeat_fresh,
            "video_fps": stats.video_fps,
            "audio_chunks_per_second": stats.audio_chunks_per_second,
            "face_crop_fps": stats.face_crop_fps,
            "last_video_timestamp": stats.last_video_timestamp,
            "last_audio_timestamp": stats.last_audio_timestamp,
            "last_face_crop_timestamp": stats.last_face_crop_timestamp,
            "video_queue_depth": stats.video_queue_depth,
            "audio_queue_depth": stats.audio_queue_depth,
            "face_crop_queue_depth": stats.face_crop_queue_depth,
            "video_drops": stats.video_drops,
            "audio_drops": stats.audio_drops,
            "face_crop_drops": stats.face_crop_drops,
            "audio_overruns": stats.audio_overruns,
            "is_running": stats.is_running,
            "cleanup_state": stats.cleanup_state,
            "gaze_fresh": self.observations.gaze_is_fresh(),
            "gaze_samples": observation_stats.gaze_samples,
            "gaze_rejections": observation_stats.gaze_rejections,
            "last_gaze_received_at": observation_stats.last_gaze_received_at,
            "geometry_slide_id": observation_stats.geometry_slide_id,
            "geometry_layout_revision": (
                observation_stats.geometry_layout_revision
            ),
        }

    def _decode_video(self, payload: bytes) -> np.ndarray:
        encoded = np.frombuffer(payload, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
            raise MediaIngressError("video payload is not a decodable color JPEG")
        height, width = frame.shape[:2]
        if height * width > self.max_input_pixels:
            raise MediaIngressError("video dimensions exceed input pixel limit")
        if width > 320 or height > 240:
            scale = min(320 / width, 240 / height)
            frame = cv2.resize(
                frame,
                (max(1, round(width * scale)), max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        return np.ascontiguousarray(frame)

    @staticmethod
    def _decode_fatigue(payload: bytes) -> np.ndarray:
        encoded = np.frombuffer(payload, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None or image.shape != (224, 224, 3):
            raise MediaIngressError(
                "fatigue payload must be a decodable 224x224 color JPEG"
            )
        return np.ascontiguousarray(image)

    def _require_active_session(self, session_id: str) -> None:
        if session_id != self._active_session_id:
            raise InactiveMediaSession("browser media session is not active")

    def _clear_sessions(self, *, reason: str) -> None:
        self.source.stop(reason=reason)
        self.observations.clear_gaze()
        self._active_session_id = None
        self._active_generation = None
        self._pending_session_id = None
        self._pending_generation = None
        self._reset_receive_times()
        self._cleanup_reason = reason

    def _reset_receive_times(self) -> None:
        self._last_video_received_at = None
        self._last_audio_received_at = None
        self._last_fatigue_received_at = None
        self._last_heartbeat_at = None

    @staticmethod
    def _is_fresh(received_at: float | None, now: float, deadline: float) -> bool:
        return received_at is not None and now - received_at <= deadline

    @staticmethod
    def _validated_session_id(session_id: str) -> str:
        if not isinstance(session_id, str) or not session_id.strip():
            raise MediaIngressError("browser media session header is required")
        if len(session_id) > 128:
            raise MediaIngressError("browser media session header is too long")
        return session_id

    @staticmethod
    def _validated_timestamp(timestamp: float) -> float:
        value = float(timestamp)
        if not math.isfinite(value):
            raise MediaIngressError("media timestamp must be finite")
        return value


def fallback_page_html() -> str:
    """Return the self-contained browser capture page served at the same origin."""

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AttentiveSlides single-port media probe</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 68rem; }
    button { font-size: 1rem; margin-right: .5rem; padding: .55rem .9rem; }
    #status { font-weight: 600; }
    video { background: #111; display: block; margin: 1rem 0; max-width: 320px; width: 100%; }
    pre { background: #f4f4f4; overflow-wrap: anywhere; padding: 1rem; }
  </style>
</head>
<body>
  <h1>Browser video/audio transport probe</h1>
  <p id="status">Off. No camera or microphone is active.</p>
  <button id="start">ON: camera + microphone</button>
  <button id="stop" disabled>OFF</button>
  <video id="preview" autoplay muted playsinline></video>
  <pre id="stats">Loading transport status…</pre>
  <p>Fallback transport uses same-origin HTTP only. Frames and PCM chunks are bounded in memory and are not written to disk.</p>
<script>
(() => {
  const sessionId = (globalThis.crypto && crypto.randomUUID) ? crypto.randomUUID() :
    String(Date.now()) + "-" + Math.random().toString(16).slice(2);
  const status = document.getElementById("status");
  const startButton = document.getElementById("start");
  const stopButton = document.getElementById("stop");
  const preview = document.getElementById("preview");
  const stats = document.getElementById("stats");
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: false });
  let stream = null;
  let audioContext = null;
  let mediaNode = null;
  let processor = null;
  let silentGain = null;
  let videoTimer = null;
  let heartbeatTimer = null;
  let running = false;
  let videoInFlight = false;
  let audioInFlight = false;
  let clientVideoDrops = 0;
  let clientAudioDrops = 0;

  function headers(extra = {}) {
    return { "X-Attentive-Media-Session": sessionId, ...extra };
  }

  function setStatus(message) {
    status.textContent = message;
  }

  async function requireOk(response) {
    if (!response.ok) {
      throw new Error(await response.text() || ("HTTP " + response.status));
    }
    return response;
  }

  function downsampleToS16(input, sourceRate) {
    const count = Math.max(1, Math.floor(input.length * 16000 / sourceRate));
    const output = new Int16Array(count);
    for (let index = 0; index < count; index += 1) {
      const sample = input[Math.min(input.length - 1, Math.floor(index * sourceRate / 16000))];
      output[index] = Math.max(-1, Math.min(1, sample)) * 32767;
    }
    return output;
  }

  function startVideoPump() {
    videoTimer = window.setInterval(() => {
      if (!running || videoInFlight || preview.videoWidth === 0) {
        if (running && videoInFlight) clientVideoDrops += 1;
        return;
      }
      canvas.width = 320;
      canvas.height = Math.max(1, Math.round(preview.videoHeight * 320 / preview.videoWidth));
      context.drawImage(preview, 0, 0, canvas.width, canvas.height);
      videoInFlight = true;
      canvas.toBlob(async (blob) => {
        if (!blob || !running) {
          videoInFlight = false;
          return;
        }
        try {
          await requireOk(await fetch("/attentive-media/video", {
            method: "POST",
            headers: headers({
              "Content-Type": "image/jpeg",
              "X-Media-Timestamp": String(performance.now() / 1000),
            }),
            body: await blob.arrayBuffer(),
          }));
        } catch (error) {
          setStatus("Video transport error: " + error.message);
        } finally {
          videoInFlight = false;
        }
      }, "image/jpeg", 0.65);
    }, 200);
  }

  function startAudioPump() {
    audioContext = new AudioContext();
    mediaNode = audioContext.createMediaStreamSource(stream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    processor.onaudioprocess = (event) => {
      if (!running) return;
      if (audioInFlight) {
        clientAudioDrops += 1;
        return;
      }
      const pcm = downsampleToS16(
        event.inputBuffer.getChannelData(0), audioContext.sampleRate
      );
      audioInFlight = true;
      fetch("/attentive-media/audio", {
        method: "POST",
        headers: headers({
          "Content-Type": "audio/L16",
          "X-Media-Timestamp": String(performance.now() / 1000),
          "X-Media-Sample-Rate": "16000",
          "X-Media-Channels": "1",
        }),
        body: pcm.buffer,
      }).then(requireOk).catch((error) => {
        setStatus("Audio transport error: " + error.message);
      }).finally(() => {
        audioInFlight = false;
      });
    };
    mediaNode.connect(processor);
    processor.connect(silentGain);
    silentGain.connect(audioContext.destination);
  }

  function startHeartbeat() {
    heartbeatTimer = window.setInterval(() => {
      if (!running) return;
      fetch("/attentive-media/heartbeat", { method: "POST", headers: headers() })
        .then(requireOk)
        .catch(() => stopCapture(false));
    }, 1000);
  }

  async function startCapture() {
    if (running) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      if (!stream.getVideoTracks().length || !stream.getAudioTracks().length) {
        throw new Error("Both camera and microphone tracks are required.");
      }
      await requireOk(await fetch("/attentive-media/start", { method: "POST", headers: headers() }));
      preview.srcObject = stream;
      await preview.play();
      await (audioContext ? audioContext.resume() : Promise.resolve());
      running = true;
      startAudioPump();
      await audioContext.resume();
      startVideoPump();
      startHeartbeat();
      startButton.disabled = true;
      stopButton.disabled = false;
      setStatus("Capturing camera + microphone through single-port fallback.");
    } catch (error) {
      setStatus("Capture did not start: " + error.message);
      await stopCapture(true);
    }
  }

  async function stopCapture(notifyServer) {
    const wasRunning = running || stream;
    running = false;
    window.clearInterval(videoTimer);
    window.clearInterval(heartbeatTimer);
    videoTimer = null;
    heartbeatTimer = null;
    if (processor) processor.disconnect();
    if (mediaNode) mediaNode.disconnect();
    if (silentGain) silentGain.disconnect();
    processor = null;
    mediaNode = null;
    silentGain = null;
    if (audioContext) await audioContext.close().catch(() => {});
    audioContext = null;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    preview.srcObject = null;
    startButton.disabled = false;
    stopButton.disabled = true;
    if (notifyServer && wasRunning) {
      await fetch("/attentive-media/stop", { method: "POST", headers: headers() }).catch(() => {});
    }
    if (!status.textContent.startsWith("Capture did not start")) {
      setStatus("Off. Browser tracks and server queues have been stopped.");
    }
  }

  async function refreshStats() {
    try {
      const payload = await (await fetch("/attentive-media/stats")).json();
      payload.client_video_drops = clientVideoDrops;
      payload.client_audio_drops = clientAudioDrops;
      stats.textContent = JSON.stringify(payload, null, 2);
      if (running && !payload.is_running) {
        await stopCapture(false);
        setStatus("Server stopped inactive capture; camera and microphone were released.");
      }
    } catch (error) {
      stats.textContent = "Stats unavailable: " + error.message;
    }
  }

  startButton.addEventListener("click", startCapture);
  stopButton.addEventListener("click", () => stopCapture(true));
  window.addEventListener("pagehide", () => {
    running = false;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    navigator.sendBeacon("/attentive-media/stop?session=" + encodeURIComponent(sessionId), "");
  });
  window.setInterval(refreshStats, 1000);
  refreshStats();
})();
</script>
</body>
</html>"""


MEDIA_INGRESS_KEY: web.AppKey[FallbackMediaIngress] = web.AppKey(
    "media_ingress", FallbackMediaIngress
)
WATCHDOG_TASK_KEY: web.AppKey[asyncio.Task[None]] = web.AppKey(
    "media_watchdog_task", asyncio.Task
)


def build_fallback_app(
    ingress: FallbackMediaIngress | None = None,
    *,
    capture_html: str | None = None,
    health_check: Callable[[], tuple[bool, dict[str, object]]] | None = None,
) -> web.Application:
    """Build the one-origin fallback application without starting a device."""

    ingress = ingress or FallbackMediaIngress(BrowserMediaSource())
    app = web.Application(
        client_max_size=max(
            ingress.max_video_bytes,
            ingress.max_audio_bytes,
            ingress.max_fatigue_bytes,
        )
    )
    app[MEDIA_INGRESS_KEY] = ingress

    async def page(_request: web.Request) -> web.Response:
        return web.Response(text=fallback_page_html(), content_type="text/html")

    async def health(_request: web.Request) -> web.Response:
        if health_check is None:
            return web.json_response({"status": "ok"})
        healthy, payload = health_check()
        return web.json_response(payload, status=200 if healthy else 503)

    async def capture(_request: web.Request) -> web.Response:
        return web.Response(
            text=capture_html or fallback_page_html(), content_type="text/html"
        )

    async def start(request: web.Request) -> web.Response:
        try:
            ingress.start(_session_id(request))
        except MediaIngressError as exc:
            _raise_http_error(exc)
        return web.json_response(ingress.stats_payload())

    async def video(request: web.Request) -> web.Response:
        try:
            ingress.accept_video_jpeg(
                _session_id(request),
                await request.read(),
                timestamp=_header_float(request, TIMESTAMP_HEADER),
            )
        except MediaIngressError as exc:
            _raise_http_error(exc)
        return web.json_response(ingress.stats_payload())

    async def audio(request: web.Request) -> web.Response:
        try:
            ingress.accept_audio_pcm(
                _session_id(request),
                await request.read(),
                timestamp=_header_float(request, TIMESTAMP_HEADER),
                sample_rate=_header_int(request, SAMPLE_RATE_HEADER),
                channels=_header_int(request, CHANNELS_HEADER),
            )
        except MediaIngressError as exc:
            _raise_http_error(exc)
        return web.json_response(ingress.stats_payload())

    async def fatigue(request: web.Request) -> web.Response:
        try:
            ingress.accept_fatigue_jpeg(
                _session_id(request),
                await request.read(),
                timestamp=_header_float(request, TIMESTAMP_HEADER),
            )
        except MediaIngressError as exc:
            _raise_http_error(exc)
        return web.json_response(ingress.stats_payload())

    async def geometry(request: web.Request) -> web.Response:
        try:
            ingress.accept_geometry_json(await _json_object(request))
        except ValueError as exc:
            _raise_http_error(exc)
        return web.json_response(ingress.stats_payload())

    async def gaze(request: web.Request) -> web.Response:
        try:
            ingress.accept_gaze_json(
                _session_id(request),
                await _json_object(request),
            )
        except ValueError as exc:
            _raise_http_error(exc)
        return web.json_response(ingress.stats_payload())

    async def heartbeat(request: web.Request) -> web.Response:
        try:
            ingress.heartbeat(_session_id(request))
        except MediaIngressError as exc:
            _raise_http_error(exc)
        return web.json_response(ingress.stats_payload())

    async def stop(request: web.Request) -> web.Response:
        try:
            ingress.stop(_session_id(request))
        except MediaIngressError as exc:
            _raise_http_error(exc)
        return web.json_response(ingress.stats_payload())

    async def stats(_request: web.Request) -> web.Response:
        return web.json_response(ingress.stats_payload())

    app.router.add_get("/", page)
    app.router.add_get("/health", health)
    app.router.add_get("/capture", capture)
    app.router.add_post("/attentive-media/start", start)
    app.router.add_post("/attentive-media/video", video)
    app.router.add_post("/attentive-media/audio", audio)
    app.router.add_post("/attentive-media/fatigue", fatigue)
    app.router.add_post("/attentive-media/geometry", geometry)
    app.router.add_post("/attentive-media/gaze", gaze)
    app.router.add_post("/attentive-media/heartbeat", heartbeat)
    app.router.add_post("/attentive-media/stop", stop)
    app.router.add_get("/attentive-media/stats", stats)
    app.on_startup.append(_start_watchdog)
    app.on_cleanup.append(_stop_watchdog)
    return app


async def _start_watchdog(app: web.Application) -> None:
    app[WATCHDOG_TASK_KEY] = asyncio.create_task(_watchdog(app))


async def _stop_watchdog(app: web.Application) -> None:
    task = app.get(WATCHDOG_TASK_KEY)
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _watchdog(app: web.Application) -> None:
    ingress = app[MEDIA_INGRESS_KEY]
    while True:
        await asyncio.sleep(0.25)
        ingress.stop_if_inactive()


def _session_id(request: web.Request) -> str:
    return request.headers.get(SESSION_HEADER) or request.query.get("session") or ""


async def _json_object(request: web.Request) -> Mapping[str, object]:
    try:
        payload = await request.json()
    except (TypeError, ValueError) as exc:
        raise MediaIngressError("request body must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise MediaIngressError("request JSON must be an object")
    return payload


def _header_float(request: web.Request, name: str) -> float:
    value = request.headers.get(name)
    if value is None:
        raise MediaIngressError(f"{name} header is required")
    try:
        return float(value)
    except ValueError as exc:
        raise MediaIngressError(f"{name} must be numeric") from exc


def _header_int(request: web.Request, name: str) -> int:
    value = request.headers.get(name)
    if value is None:
        raise MediaIngressError(f"{name} header is required")
    try:
        return int(value)
    except ValueError as exc:
        raise MediaIngressError(f"{name} must be an integer") from exc


def _raise_http_error(error: ValueError) -> None:
    if isinstance(error, InactiveMediaSession):
        raise web.HTTPConflict(text=str(error))
    if isinstance(error, MediaPayloadTooLarge):
        raise web.HTTPRequestEntityTooLarge(max_size=0, actual_size=0, text=str(error))
    raise web.HTTPBadRequest(text=str(error))


def run_single_port_server(*, host: str, port: int) -> None:
    """Run the fallback probe bound to loopback unless a caller chooses otherwise."""

    web.run_app(
        build_fallback_app(),
        host=host,
        port=port,
        access_log=None,
        print=None,
    )
