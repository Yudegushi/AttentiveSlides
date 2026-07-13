"""Audio-only browser microphone HTTP ingress."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import asdict, dataclass
import math
import os
from pathlib import Path
from threading import (
    Event,
    RLock,
    Thread,
    current_thread,
)
import time
from typing import Callable

from aiohttp import web
import numpy as np

from modules.media.browser_audio_source import (
    BrowserAudioSource,
)


SESSION_HEADER = (
    "X-Attentive-Audio-Session"
)

TIMESTAMP_HEADER = (
    "X-Audio-Timestamp"
)

SAMPLE_RATE_HEADER = (
    "X-Audio-Sample-Rate"
)

CHANNELS_HEADER = (
    "X-Audio-Channels"
)


class MicrophoneIngressError(
    ValueError
):
    """Invalid browser microphone request."""


class InactiveMicrophoneSession(
    MicrophoneIngressError
):
    """Request belongs to an inactive session."""


@dataclass(frozen=True)
class MicrophoneIngressSnapshot:
    enabled: bool
    active: bool
    heartbeat_fresh: bool
    audio_fresh: bool
    last_heartbeat_at: float | None
    last_audio_at: float | None
    cleanup_reason: str | None


class MicrophoneIngress:
    """Validate browser PCM and feed BrowserAudioSource."""

    def __init__(
        self,
        source: BrowserAudioSource,
        *,
        inactive_after_seconds: float = 3.0,
        audio_stale_after_seconds: float = 3.0,
        max_audio_bytes: int = (
            128 * 1024
        ),
        clock: Callable[
            [],
            float,
        ] = time.monotonic,
    ) -> None:
        self.source = source
        self.inactive_after_seconds = float(
            inactive_after_seconds
        )
        self.audio_stale_after_seconds = float(
            audio_stale_after_seconds
        )
        self.max_audio_bytes = int(
            max_audio_bytes
        )
        self._clock = clock
        self._lock = RLock()

        self._enabled = False
        self._session_id: str | None = None
        self._last_heartbeat_at: (
            float | None
        ) = None
        self._last_audio_at: (
            float | None
        ) = None
        self._cleanup_reason: (
            str | None
        ) = None

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        with self._lock:
            self._enabled = bool(
                enabled
            )

            if not self._enabled:
                self._clear(
                    reason=(
                        "microphone disabled"
                    )
                )

    def start(
        self,
        session_id: str,
    ) -> None:
        session_id = (
            self._validate_session_id(
                session_id
            )
        )

        with self._lock:
            if not self._enabled:
                raise (
                    InactiveMicrophoneSession(
                        "microphone ingress "
                        "is disabled"
                    )
                )

            if (
                self._session_id
                == session_id
            ):
                return

            if (
                self._session_id
                is not None
            ):
                self.source.stop(
                    reason=(
                        "browser session "
                        "replaced"
                    )
                )

            self._session_id = (
                session_id
            )
            self._last_heartbeat_at = (
                self._clock()
            )
            self._last_audio_at = None
            self._cleanup_reason = None

            self.source.start()

    def stop(
        self,
        session_id: str,
        *,
        reason: str = "browser stopped",
    ) -> None:
        with self._lock:
            self._require_session(
                session_id
            )

            self._clear(
                reason=reason
            )

    def heartbeat(
        self,
        session_id: str,
    ) -> None:
        with self._lock:
            self._require_session(
                session_id
            )

            self._last_heartbeat_at = (
                self._clock()
            )

    def accept_pcm(
        self,
        session_id: str,
        payload: bytes,
        *,
        timestamp: float,
        sample_rate: int,
        channels: int,
    ) -> bool:
        if (
            not payload
            or len(payload)
            > self.max_audio_bytes
        ):
            raise MicrophoneIngressError(
                "audio payload is empty "
                "or too large"
            )

        if sample_rate != 16_000:
            raise MicrophoneIngressError(
                "audio sample rate must "
                "be 16000 Hz"
            )

        if channels != 1:
            raise MicrophoneIngressError(
                "audio channel count "
                "must be 1"
            )

        if len(payload) % 2:
            raise MicrophoneIngressError(
                "audio payload is not "
                "aligned signed-16 PCM"
            )

        timestamp = float(
            timestamp
        )

        if not math.isfinite(
            timestamp
        ):
            raise MicrophoneIngressError(
                "audio timestamp must "
                "be finite"
            )

        samples = np.frombuffer(
            payload,
            dtype="<i2",
        ).reshape(
            -1,
            1,
        )

        with self._lock:
            self._require_session(
                session_id
            )

            accepted = (
                self.source
                .accept_audio_samples(
                    samples,
                    timestamp=timestamp,
                    sample_rate=sample_rate,
                    channels=channels,
                )
            )

            self._last_audio_at = (
                self._clock()
            )

            return accepted

    def stop_if_inactive(
        self,
    ) -> bool:
        with self._lock:
            if (
                self._session_id is None
                or self._last_heartbeat_at
                is None
            ):
                return False

            if (
                self._clock()
                - self._last_heartbeat_at
                < self.inactive_after_seconds
            ):
                return False

            self._clear(
                reason="browser inactive"
            )

            return True

    def snapshot(
        self,
    ) -> MicrophoneIngressSnapshot:
        with self._lock:
            now = self._clock()
            active = (
                self._session_id
                is not None
            )

            return (
                MicrophoneIngressSnapshot(
                    enabled=self._enabled,
                    active=active,
                    heartbeat_fresh=(
                        active
                        and self._fresh(
                            self
                            ._last_heartbeat_at,
                            now,
                            self
                            .inactive_after_seconds,
                        )
                    ),
                    audio_fresh=(
                        active
                        and self._fresh(
                            self
                            ._last_audio_at,
                            now,
                            self
                            .audio_stale_after_seconds,
                        )
                    ),
                    last_heartbeat_at=(
                        self
                        ._last_heartbeat_at
                    ),
                    last_audio_at=(
                        self._last_audio_at
                    ),
                    cleanup_reason=(
                        self._cleanup_reason
                    ),
                )
            )

    def stats_payload(
        self,
    ) -> dict[str, object]:
        payload = asdict(
            self.snapshot()
        )

        stats = self.source.stats()

        payload.update(
            {
                "source_running": (
                    stats.is_running
                ),
                "queue_depth": (
                    stats.queue_depth
                ),
                "accepted_chunks": (
                    stats.accepted_chunks
                ),
                "dropped_chunks": (
                    stats.dropped_chunks
                ),
                "overruns": (
                    stats.overruns
                ),
            }
        )

        return payload

    def _require_session(
        self,
        session_id: str,
    ) -> None:
        if (
            not session_id
            or session_id
            != self._session_id
        ):
            raise (
                InactiveMicrophoneSession(
                    "microphone session "
                    "is not active"
                )
            )

    def _clear(
        self,
        *,
        reason: str,
    ) -> None:
        self.source.stop(
            reason=reason
        )

        self._session_id = None
        self._last_heartbeat_at = None
        self._last_audio_at = None
        self._cleanup_reason = reason

    @staticmethod
    def _validate_session_id(
        session_id: str,
    ) -> str:
        if (
            not isinstance(
                session_id,
                str,
            )
            or not session_id.strip()
            or len(session_id) > 128
        ):
            raise MicrophoneIngressError(
                "invalid microphone "
                "session id"
            )

        return session_id

    @staticmethod
    def _fresh(
        received_at: float | None,
        now: float,
        deadline: float,
    ) -> bool:
        return bool(
            received_at is not None
            and now - received_at
            <= deadline
        )


class MicrophoneIngressService:
    """Own the loopback aiohttp microphone server."""

    def __init__(
        self,
        ingress: MicrophoneIngress,
        *,
        host: str | None = None,
        port: int | None = None,
        capture_html_path: (
            str | Path | None
        ) = None,
    ) -> None:
        self.ingress = ingress

        self.host = (
            host
            or os.environ.get(
                "ATTENTIVE_MICROPHONE_HOST",
                "127.0.0.1",
            )
        )

        self.port = int(
            port
            if port is not None
            else os.environ.get(
                "ATTENTIVE_MICROPHONE_PORT",
                "8503",
            )
        )

        self.capture_html_path = Path(
            capture_html_path
            or (
                Path(__file__)
                .parent
                / "microphone_component"
                / "index.html"
            )
        )

        self.bound_port: int | None = None

        self._lock = RLock()
        self._thread: Thread | None = None
        self._loop: (
            asyncio.AbstractEventLoop
            | None
        ) = None
        self._runner: (
            web.AppRunner | None
        ) = None
        self._startup_error: (
            BaseException | None
        ) = None

    @property
    def capture_url(
        self,
    ) -> str:
        configured = os.environ.get(
            "ATTENTIVE_MICROPHONE_PUBLIC_URL"
        )

        if configured:
            return configured.rstrip(
                "/"
            )

        port = (
            self.bound_port
            or self.port
        )

        return (
            f"http://127.0.0.1:"
            f"{port}/capture"
        )

    def ensure_started(
        self,
    ) -> None:
        with self._lock:
            if (
                self._thread is not None
                and self._thread.is_alive()
            ):
                return

            ready = Event()
            self._startup_error = None

            self._thread = Thread(
                target=self._serve,
                args=(ready,),
                name=(
                    "attentive-microphone-"
                    "ingress"
                ),
                daemon=True,
            )

            self._thread.start()

        if not ready.wait(
            timeout=20
        ):
            raise TimeoutError(
                "microphone ingress did "
                "not start"
            )

        if (
            self._startup_error
            is not None
        ):
            raise RuntimeError(
                "microphone ingress failed"
            ) from self._startup_error

    def shutdown(
        self,
    ) -> None:
        self.ingress.set_enabled(
            False
        )

        with self._lock:
            loop = self._loop
            thread = self._thread

        if (
            loop is not None
            and loop.is_running()
        ):
            loop.call_soon_threadsafe(
                loop.stop
            )

        if (
            thread is not None
            and thread
            is not current_thread()
        ):
            thread.join(
                timeout=5
            )

    def _serve(
        self,
        ready: Event,
    ) -> None:
        loop = (
            asyncio.new_event_loop()
        )

        asyncio.set_event_loop(
            loop
        )

        with self._lock:
            self._loop = loop

        runner = web.AppRunner(
            self._build_app()
        )

        async def start() -> None:
            try:
                await runner.setup()

                site = web.TCPSite(
                    runner,
                    self.host,
                    self.port,
                )

                await site.start()

                sockets = (
                    site._server.sockets
                    if site._server
                    is not None
                    else []
                )

                if not sockets:
                    raise RuntimeError(
                        "microphone ingress "
                        "has no socket"
                    )

                self.bound_port = int(
                    sockets[0]
                    .getsockname()[1]
                )

                self._runner = runner

            except BaseException as error:
                self._startup_error = (
                    error
                )

            finally:
                ready.set()

        loop.run_until_complete(
            start()
        )

        if self._startup_error is None:
            loop.run_forever()

        loop.run_until_complete(
            runner.cleanup()
        )

        loop.close()

    def _build_app(
        self,
    ) -> web.Application:
        app = web.Application(
            client_max_size=(
                self.ingress
                .max_audio_bytes
            )
        )

        async def capture(
            _request: web.Request,
        ) -> web.Response:
            return web.Response(
                text=(
                    self.capture_html_path
                    .read_text(
                        encoding="utf-8"
                    )
                ),
                content_type="text/html",
            )

        async def health(
            _request: web.Request,
        ) -> web.Response:
            return web.json_response(
                {
                    "status": "ok"
                }
            )

        async def start(
            request: web.Request,
        ) -> web.Response:
            try:
                self.ingress.start(
                    _session_id(
                        request
                    )
                )

            except MicrophoneIngressError as error:
                raise web.HTTPBadRequest(
                    text=str(error)
                ) from error

            return web.json_response(
                self.ingress
                .stats_payload()
            )

        async def chunk(
            request: web.Request,
        ) -> web.Response:
            try:
                self.ingress.accept_pcm(
                    _session_id(
                        request
                    ),
                    await request.read(),
                    timestamp=_float_header(
                        request,
                        TIMESTAMP_HEADER,
                    ),
                    sample_rate=_int_header(
                        request,
                        SAMPLE_RATE_HEADER,
                    ),
                    channels=_int_header(
                        request,
                        CHANNELS_HEADER,
                    ),
                )

            except MicrophoneIngressError as error:
                raise web.HTTPBadRequest(
                    text=str(error)
                ) from error

            return web.json_response(
                self.ingress
                .stats_payload()
            )

        async def heartbeat(
            request: web.Request,
        ) -> web.Response:
            try:
                self.ingress.heartbeat(
                    _session_id(
                        request
                    )
                )

            except MicrophoneIngressError as error:
                raise web.HTTPBadRequest(
                    text=str(error)
                ) from error

            return web.json_response(
                self.ingress
                .stats_payload()
            )

        async def stop(
            request: web.Request,
        ) -> web.Response:
            try:
                self.ingress.stop(
                    _session_id(
                        request
                    )
                )

            except MicrophoneIngressError:
                pass

            return web.json_response(
                self.ingress
                .stats_payload()
            )

        async def stats(
            _request: web.Request,
        ) -> web.Response:
            return web.json_response(
                self.ingress
                .stats_payload()
            )

        async def watchdog(
            app: web.Application,
        ) -> None:
            while True:
                await asyncio.sleep(
                    0.25
                )

                self.ingress.stop_if_inactive()

        async def on_startup(
            app: web.Application,
        ) -> None:
            app["watchdog"] = (
                asyncio.create_task(
                    watchdog(app)
                )
            )

        async def on_cleanup(
            app: web.Application,
        ) -> None:
            task = app.get(
                "watchdog"
            )

            if task is not None:
                task.cancel()

                with suppress(
                    asyncio.CancelledError
                ):
                    await task

        app.router.add_get(
            "/capture",
            capture,
        )

        app.router.add_get(
            "/health",
            health,
        )

        app.router.add_post(
            "/audio/start",
            start,
        )

        app.router.add_post(
            "/audio/chunk",
            chunk,
        )

        app.router.add_post(
            "/audio/heartbeat",
            heartbeat,
        )

        app.router.add_post(
            "/audio/stop",
            stop,
        )

        app.router.add_get(
            "/audio/stats",
            stats,
        )

        app.on_startup.append(
            on_startup
        )

        app.on_cleanup.append(
            on_cleanup
        )

        return app


def _session_id(
    request: web.Request,
) -> str:
    return (
        request.headers.get(
            SESSION_HEADER
        )
        or request.query.get(
            "session"
        )
        or ""
    )


def _float_header(
    request: web.Request,
    name: str,
) -> float:
    value = request.headers.get(
        name
    )

    if value is None:
        raise MicrophoneIngressError(
            f"{name} is required"
        )

    try:
        return float(value)

    except ValueError as error:
        raise MicrophoneIngressError(
            f"{name} must be numeric"
        ) from error


def _int_header(
    request: web.Request,
    name: str,
) -> int:
    value = request.headers.get(
        name
    )

    if value is None:
        raise MicrophoneIngressError(
            f"{name} is required"
        )

    try:
        return int(value)

    except ValueError as error:
        raise MicrophoneIngressError(
            f"{name} must be integer"
        ) from error
