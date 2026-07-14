"""Local browser-to-realtime-model voice gateway."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import math
import os
from pathlib import Path
from threading import (
    Event,
    RLock,
    Thread,
    current_thread,
)
from typing import Any

from aiohttp import web

from modules.system.realtime_voice_runtime import (
    RealtimeVoiceRuntime,
)


SESSION_HEADER = (
    "X-Attentive-Voice-Session"
)


class RealtimeVoiceGateway:
    """Serve browser controls, audio ingress and output playback."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        html_path: (
            str | Path | None
        ) = None,
    ) -> None:
        self.host = (
            host
            or os.environ.get(
                (
                    "ATTENTIVE_REALTIME_"
                    "VOICE_HOST"
                ),
                "127.0.0.1",
            )
        )

        self.port = int(
            port
            if port is not None
            else os.environ.get(
                (
                    "ATTENTIVE_REALTIME_"
                    "VOICE_PORT"
                ),
                "8504",
            )
        )

        self.html_path = Path(
            html_path
            or (
                Path(__file__)
                .parent
                / "microphone_component"
                / "index.html"
            )
        )

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

        self._subscribers: set[
            web.WebSocketResponse
        ] = set()

        self.runtime = (
            RealtimeVoiceRuntime(
                emit_json=(
                    self.broadcast_json
                ),
                emit_audio=(
                    self.broadcast_audio
                ),
            )
        )

        self.bound_port: int | None = (
            None
        )

    @property
    def public_base_url(
        self,
    ) -> str:
        configured = os.environ.get(
            (
                "ATTENTIVE_REALTIME_"
                "VOICE_PUBLIC_URL"
            )
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
            "http://127.0.0.1:"
            + str(port)
        )

    def capture_url(
        self,
        *,
        view: str,
    ) -> str:
        return (
            self.public_base_url
            + "/capture?view="
            + view
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
                daemon=True,
                name=(
                    "attentive-realtime-"
                    "voice-gateway"
                ),
            )

            self._thread.start()

        if not ready.wait(
            timeout=20
        ):
            raise TimeoutError(
                "Realtime voice gateway "
                "did not start."
            )

        if (
            self._startup_error
            is not None
        ):
            raise RuntimeError(
                "Realtime voice gateway "
                "failed to start."
            ) from self._startup_error

    def shutdown(
        self,
    ) -> None:
        with self._lock:
            loop = self._loop
            thread = self._thread

        if (
            loop is not None
            and loop.is_running()
        ):
            future = (
                asyncio
                .run_coroutine_threadsafe(
                    self.runtime.stop_all(),
                    loop,
                )
            )

            with suppress(
                Exception
            ):
                future.result(
                    timeout=5
                )

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

    async def broadcast_json(
        self,
        payload: dict[str, Any],
    ) -> None:
        text = json.dumps(
            payload,
            ensure_ascii=False,
        )

        stale = []

        for socket in tuple(
            self._subscribers
        ):
            try:
                await socket.send_str(
                    text
                )

            except Exception:
                stale.append(
                    socket
                )

        for socket in stale:
            self._subscribers.discard(
                socket
            )

    async def broadcast_audio(
        self,
        pcm: bytes,
    ) -> None:
        stale = []

        for socket in tuple(
            self._subscribers
        ):
            try:
                await socket.send_bytes(
                    pcm
                )

            except Exception:
                stale.append(
                    socket
                )

        for socket in stale:
            self._subscribers.discard(
                socket
            )

    def snapshot(
        self,
    ) -> dict[str, Any]:
        return self.runtime.snapshot()

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
                        "Gateway did not "
                        "bind a socket."
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
                256 * 1024
            )
        )

        async def capture(
            _request: web.Request,
        ) -> web.Response:
            return web.Response(
                text=self.html_path.read_text(
                    encoding="utf-8"
                ),
                content_type="text/html",
            )

        async def health(
            _request: web.Request,
        ) -> web.Response:
            return web.json_response(
                {
                    "status": "ok",
                    "service": (
                        "realtime_voice"
                    ),
                }
            )

        async def state(
            _request: web.Request,
        ) -> web.Response:
            return web.json_response(
                self.runtime.snapshot()
            )

        async def camera_toggle(
            _request: web.Request,
        ) -> web.Response:
            await self.runtime.toggle_camera()

            return web.json_response(
                self.runtime.snapshot()
            )

        async def microphone(
            request: web.Request,
        ) -> web.Response:
            payload = await request.json()

            await self.runtime.set_microphone(
                enabled=bool(
                    payload.get(
                        "enabled",
                        False,
                    )
                ),
                permission=str(
                    payload.get(
                        "permission",
                        "unknown",
                    )
                ),
                session_id=(
                    _session_id(
                        request
                    )
                ),
            )

            return web.json_response(
                self.runtime.snapshot()
            )

        async def speaker(
            request: web.Request,
        ) -> web.Response:
            payload = await request.json()

            await (
                self.runtime
                .set_speaker_enabled(
                    enabled=bool(
                        payload.get(
                            "enabled",
                            False,
                        )
                    )
                )
            )

            return web.json_response(
                self.runtime.snapshot()
            )

        async def heartbeat(
            request: web.Request,
        ) -> web.Response:
            await self.runtime.heartbeat(
                session_id=(
                    _session_id(
                        request
                    )
                )
            )

            return web.json_response(
                self.runtime.snapshot()
            )

        async def audio(
            request: web.Request,
        ) -> web.Response:
            sample_rate = int(
                request.headers.get(
                    (
                        "X-Audio-"
                        "Sample-Rate"
                    ),
                    "0",
                )
            )

            channels = int(
                request.headers.get(
                    "X-Audio-Channels",
                    "0",
                )
            )

            timestamp = float(
                request.headers.get(
                    "X-Audio-Timestamp",
                    "nan",
                )
            )

            if sample_rate != 16_000:
                raise web.HTTPBadRequest(
                    text=(
                        "Sample rate must "
                        "be 16000."
                    )
                )

            if channels != 1:
                raise web.HTTPBadRequest(
                    text=(
                        "Audio must be mono."
                    )
                )

            if not math.isfinite(
                timestamp
            ):
                raise web.HTTPBadRequest(
                    text=(
                        "Timestamp must "
                        "be finite."
                    )
                )

            pcm = await request.read()

            if (
                not pcm
                or len(pcm) % 2
            ):
                raise web.HTTPBadRequest(
                    text=(
                        "Invalid signed-16 "
                        "PCM payload."
                    )
                )

            await self.runtime.accept_pcm(
                session_id=(
                    _session_id(
                        request
                    )
                ),
                pcm=pcm,
            )

            return web.json_response(
                {
                    "accepted": True
                }
            )

        async def ptt_start(
            _request: web.Request,
        ) -> web.Response:
            await self.runtime.start_push_to_talk()

            return web.json_response(
                self.runtime.snapshot()
            )

        async def ptt_stop(
            _request: web.Request,
        ) -> web.Response:
            await self.runtime.stop_push_to_talk()

            return web.json_response(
                self.runtime.snapshot()
            )

        async def continuous_start(
            _request: web.Request,
        ) -> web.Response:
            await self.runtime.start_continuous()

            return web.json_response(
                self.runtime.snapshot()
            )

        async def continuous_stop(
            _request: web.Request,
        ) -> web.Response:
            await self.runtime.stop_continuous()

            return web.json_response(
                self.runtime.snapshot()
            )

        async def events(
            request: web.Request,
        ) -> web.WebSocketResponse:
            socket = (
                web.WebSocketResponse(
                    heartbeat=20,
                )
            )

            await socket.prepare(
                request
            )

            self._subscribers.add(
                socket
            )

            try:
                async for message in socket:
                    if (
                        message.type
                        == web.WSMsgType.ERROR
                    ):
                        break

            finally:
                self._subscribers.discard(
                    socket
                )

            return socket

        async def watchdog(
            _app: web.Application,
        ) -> None:
            while True:
                await asyncio.sleep(
                    0.5
                )

                await (
                    self.runtime
                    .expire_inactive_microphone()
                )

        async def on_startup(
            app: web.Application,
        ) -> None:
            app["voice_watchdog"] = (
                asyncio.create_task(
                    watchdog(app)
                )
            )

        async def on_cleanup(
            app: web.Application,
        ) -> None:
            task = app.get(
                "voice_watchdog"
            )

            if task is not None:
                task.cancel()

                with suppress(
                    asyncio.CancelledError
                ):
                    await task

            await self.runtime.stop_all()

        app.router.add_get(
            "/capture",
            capture,
        )

        app.router.add_get(
            "/health",
            health,
        )

        app.router.add_get(
            "/voice/state",
            state,
        )

        app.router.add_post(
            (
                "/voice/device/"
                "camera/toggle"
            ),
            camera_toggle,
        )

        app.router.add_post(
            (
                "/voice/device/"
                "microphone"
            ),
            microphone,
        )

        app.router.add_post(
            (
                "/voice/device/"
                "speaker"
            ),
            speaker,
        )

        app.router.add_post(
            "/voice/heartbeat",
            heartbeat,
        )

        app.router.add_post(
            "/voice/audio",
            audio,
        )

        app.router.add_post(
            "/voice/ptt/start",
            ptt_start,
        )

        app.router.add_post(
            "/voice/ptt/stop",
            ptt_stop,
        )

        app.router.add_post(
            (
                "/voice/"
                "continuous/start"
            ),
            continuous_start,
        )

        app.router.add_post(
            (
                "/voice/"
                "continuous/stop"
            ),
            continuous_stop,
        )

        app.router.add_get(
            "/voice/events",
            events,
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
    value = (
        request.headers.get(
            SESSION_HEADER
        )
        or request.query.get(
            "session"
        )
        or ""
    ).strip()

    if (
        not value
        or len(value) > 128
    ):
        raise web.HTTPBadRequest(
            text=(
                "Invalid voice "
                "session ID."
            )
        )

    return value
