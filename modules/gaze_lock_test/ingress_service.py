"""Minimal HTTP ingress owned by the standalone gaze-lock test."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import os
from pathlib import Path
from threading import current_thread, Event, RLock, Thread
import urllib.request

from aiohttp import web

from modules.media.browser_gaze_source import BrowserGazeSource
from modules.media.browser_media_source import BrowserMediaSource
from modules.media.single_port_transport import (
    FallbackMediaIngress,
    build_fallback_app,
)


CAPTURE_HTML_PATH = Path(__file__).parent / "capture" / "index.html"


class GazeOnlyIngressService:
    """Serve camera-local gaze transport without production live workers."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        reconcile_interval_seconds: float = 0.1,
        capture_html: str | None = None,
    ) -> None:
        self.host = host or os.environ.get(
            "ATTENTIVE_LIVE_INGRESS_HOST",
            "127.0.0.1",
        )
        self.port = int(
            port
            if port is not None
            else os.environ.get("ATTENTIVE_LIVE_INGRESS_PORT", "8503")
        )
        if reconcile_interval_seconds <= 0:
            raise ValueError("reconcile_interval_seconds must be positive")
        self.bound_port: int | None = None
        self.source = BrowserMediaSource()
        self.observations = BrowserGazeSource()
        self.ingress = FallbackMediaIngress(
            self.source,
            observations=self.observations,
            start_armed=True,
            coordinated_activation=False,
            inactive_after_seconds=4.0,
        )
        self._interval = float(reconcile_interval_seconds)
        self._capture_html = (
            capture_html
            if capture_html is not None
            else CAPTURE_HTML_PATH.read_text(encoding="utf-8")
        )
        self._lock = RLock()
        self._server_thread: Thread | None = None
        self._server_loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._watchdog_error: str | None = None
        self._startup_failure: BaseException | None = None

    @property
    def server_thread(self) -> Thread | None:
        with self._lock:
            return self._server_thread

    def build_app(self) -> web.Application:
        """Build the service app without binding a port."""
        return build_fallback_app(
            self.ingress,
            capture_html=self._capture_html,
            health_check=self.health_status,
        )

    def ensure_started(self) -> None:
        with self._lock:
            if self._server_thread is not None and self._server_thread.is_alive():
                return
            ready = Event()
            self._startup_failure = None
            thread = Thread(
                target=self._serve,
                args=(ready,),
                name="gaze-lock-http-ingress",
                daemon=True,
            )
            self._server_thread = thread
            thread.start()
        if not ready.wait(timeout=30):
            self.shutdown()
            raise TimeoutError("gaze-only ingress did not bind within 30 seconds")
        if self._startup_failure is not None:
            failure = self._startup_failure
            self.shutdown()
            raise RuntimeError("gaze-only ingress failed to start") from failure
        assert self.bound_port is not None
        with urllib.request.urlopen(
            f"http://{self.host}:{self.bound_port}/health",
            timeout=30,
        ) as response:
            if response.status != 200:
                self.shutdown()
                raise RuntimeError(
                    f"gaze-only ingress health returned {response.status}"
                )

    def shutdown(self) -> None:
        self.ingress.stop_active(reason="gaze-lock service shutdown")
        with self._lock:
            loop = self._server_loop
            thread = self._server_thread
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread is not current_thread():
            thread.join(timeout=5)
        with self._lock:
            if (
                self._server_thread is thread
                and (thread is None or not thread.is_alive())
            ):
                self._server_thread = None
                self._server_loop = None
                self._runner = None
                self._watchdog_task = None

    def health_status(self) -> tuple[bool, dict[str, object]]:
        with self._lock:
            task = self._watchdog_task
            error = self._watchdog_error
        running = task is not None and not task.done()
        healthy = running and error is None
        return healthy, {
            "status": "ok" if healthy else "error",
            "gaze_only": True,
            "watchdog_running": running,
            "watchdog_error": error,
        }

    def capture_generation(self) -> int | None:
        """Return the active browser-session generation for lock scoping."""
        snapshot = self.ingress.session_snapshot()
        return snapshot.generation if snapshot.active else None

    def _serve(self, ready: Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._server_loop = loop
        runner = web.AppRunner(self.build_app())

        async def start() -> None:
            try:
                await runner.setup()
                site = web.TCPSite(runner, self.host, self.port)
                await site.start()
                sockets = site._server.sockets if site._server is not None else []
                if not sockets:
                    raise RuntimeError("gaze-only ingress has no listening socket")
                self.bound_port = int(sockets[0].getsockname()[1])
                self._runner = runner
                self._watchdog_error = None
                self._watchdog_task = asyncio.create_task(self._watchdog())
            except BaseException as exc:
                self._startup_failure = exc
            finally:
                ready.set()

        loop.run_until_complete(start())
        if self._startup_failure is None:
            loop.run_forever()
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                loop.run_until_complete(self._watchdog_task)
        loop.run_until_complete(runner.cleanup())
        loop.close()

    async def _watchdog(self) -> None:
        try:
            while True:
                self.ingress.stop_if_inactive()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            with self._lock:
                self._watchdog_error = f"{type(exc).__name__}: {exc}"
            raise
