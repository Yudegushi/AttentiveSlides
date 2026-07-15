"""Coordinate one HTTP media ingress with the existing live runtime."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import os
from threading import current_thread, Event, RLock, Thread
import time
from typing import Any, Callable
import urllib.request

from aiohttp import web

from .browser_media_source import BrowserMediaSource
from .single_port_transport import (
    FallbackMediaIngress,
    VoiceTransport,
    build_fallback_app,
)


class LiveIngressService:
    """Own one shared source, ingress server, and controller readiness gate."""

    def __init__(
        self,
        *,
        runtime: Any,
        source: BrowserMediaSource,
        ingress: FallbackMediaIngress,
        host: str | None = None,
        port: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        reconcile_interval_seconds: float = 0.05,
        capture_html: str | None = None,
        voice_transport: VoiceTransport | None = None,
    ) -> None:
        if ingress.source is not source:
            raise ValueError("live ingress and runtime must share BrowserMediaSource")
        self.runtime = runtime
        self.source = source
        self.ingress = ingress
        self.host = host or os.environ.get("ATTENTIVE_LIVE_INGRESS_HOST", "127.0.0.1")
        self.port = int(port if port is not None else os.environ.get("ATTENTIVE_LIVE_INGRESS_PORT", "8503"))
        self.bound_port: int | None = None
        self._clock = clock
        self._interval = float(reconcile_interval_seconds)
        self._capture_html = capture_html
        self.voice_transport = voice_transport
        self._lock = RLock()
        self._master_enabled = False
        self._runtime_generation: int | None = None
        self._server_thread: Thread | None = None
        self._server_loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._coordinator_task: asyncio.Task[None] | None = None
        self._coordinator_last_error: str | None = None
        self._startup_failure: BaseException | None = None

    @property
    def server_thread(self) -> Thread | None:
        with self._lock:
            return self._server_thread

    @property
    def master_enabled(self) -> bool:
        with self._lock:
            return self._master_enabled

    def set_master_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        with self._lock:
            if enabled == self._master_enabled:
                return
            self._master_enabled = enabled
            if enabled:
                self.ingress.arm()
            else:
                self.ingress.disarm(reason="master switch off")

    def reconcile_once(self) -> None:
        reason = self._voice_stop_reason()
        if reason is not None:
            self._stop_voice_from_sync(reason)
        self._reconcile_core()

    def _reconcile_core(self) -> None:
        with self._lock:
            if not self._master_enabled:
                if self.runtime.is_running:
                    self.runtime.stop(reason="master switch off")
                self._runtime_generation = None
                return

            snapshot = self.ingress.session_snapshot()
            if snapshot.session_pending:
                if self.runtime.is_running:
                    self.runtime.stop(reason="browser session replaced")
                self._runtime_generation = None
                self.ingress.activate_pending()
                return

            if self.runtime.is_running:
                if not snapshot.active:
                    self.runtime.handle_disconnect()
                    self._runtime_generation = None
                    return
                if snapshot.generation != self._runtime_generation:
                    self.runtime.stop(reason="browser session generation changed")
                    self._runtime_generation = None
                    return
                if not self.source.is_running:
                    self.runtime.stop(reason="shared media source stopped")
                    self._runtime_generation = None
                    self.ingress.reset_active_readiness(
                        reason="shared media source stopped"
                    )
                    return
                if not snapshot.heartbeat_fresh:
                    self.ingress.stop_active(reason="browser inactive")
                    self.runtime.handle_disconnect()
                    self._runtime_generation = None
                    return
                if not snapshot.video_fresh or not snapshot.audio_fresh:
                    self.ingress.stop_active(reason="browser media stale")
                    self.runtime.handle_disconnect()
                    self._runtime_generation = None
                    return
                return

            if (
                snapshot.active
                and snapshot.video_fresh
                and snapshot.audio_fresh
                and snapshot.heartbeat_fresh
            ):
                self.runtime.start()
                if self.runtime.is_running:
                    self._runtime_generation = snapshot.generation

    def ensure_started(self) -> None:
        with self._lock:
            if self._server_thread is not None and self._server_thread.is_alive():
                return
            ready = Event()
            self._startup_failure = None
            thread = Thread(
                target=self._serve,
                args=(ready,),
                name="live-http-media-ingress",
                daemon=True,
            )
            self._server_thread = thread
            thread.start()
        if not ready.wait(timeout=30):
            self.shutdown()
            raise TimeoutError("live media ingress did not bind within 30 seconds")
        if self._startup_failure is not None:
            failure = self._startup_failure
            self.shutdown()
            raise RuntimeError("live media ingress failed to start") from failure
        assert self.bound_port is not None
        with urllib.request.urlopen(
            f"http://{self.host}:{self.bound_port}/health", timeout=30
        ) as response:
            if response.status != 200:
                self.shutdown()
                raise RuntimeError(f"live media ingress health returned {response.status}")

    def shutdown(self) -> None:
        self.set_master_enabled(False)
        self.reconcile_once()
        self._stop_voice_from_sync("service shutdown")
        with self._lock:
            loop = self._server_loop
            thread = self._server_thread
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread is not current_thread():
            thread.join(timeout=5)
        with self._lock:
            if self._server_thread is thread and (thread is None or not thread.is_alive()):
                self._server_thread = None
                self._server_loop = None
                self._runner = None
                self._coordinator_task = None

    def stats_payload(self) -> dict[str, object]:
        return self.ingress.stats_payload()

    def health_status(self) -> tuple[bool, dict[str, object]]:
        with self._lock:
            task = self._coordinator_task
            error = self._coordinator_last_error
        running = task is not None and not task.done()
        healthy = running and error is None
        return healthy, {
            "status": "ok" if healthy else "error",
            "coordinator_running": running,
            "coordinator_last_error": error,
        }

    def _serve(self, ready: Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._server_loop = loop
        if self.voice_transport is not None:
            attach_loop = getattr(self.voice_transport, "attach_loop", None)
            if callable(attach_loop):
                attach_loop(loop)
        runner = web.AppRunner(
            build_fallback_app(
                self.ingress,
                capture_html=self._capture_html,
                health_check=self.health_status,
                voice_transport=self.voice_transport,
            )
        )

        async def start() -> None:
            try:
                await runner.setup()
                site = web.TCPSite(runner, self.host, self.port)
                await site.start()
                sockets = site._server.sockets if site._server is not None else []
                if not sockets:
                    raise RuntimeError("live media ingress has no listening socket")
                self.bound_port = int(sockets[0].getsockname()[1])
                self._runner = runner
                self._coordinator_last_error = None
                self._coordinator_task = asyncio.create_task(self._coordinate())
            except BaseException as exc:
                self._startup_failure = exc
            finally:
                ready.set()

        loop.run_until_complete(start())
        if self._startup_failure is None:
            loop.run_forever()
        if self._coordinator_task is not None:
            self._coordinator_task.cancel()
            with suppress(asyncio.CancelledError):
                loop.run_until_complete(self._coordinator_task)
        if self.voice_transport is not None and self._voice_is_active():
            with suppress(Exception):
                loop.run_until_complete(self.voice_transport.stop("service shutdown"))
        loop.run_until_complete(runner.cleanup())
        loop.close()

    async def _coordinate(self) -> None:
        try:
            while True:
                reason = self._voice_stop_reason()
                if reason is not None and self.voice_transport is not None:
                    await self.voice_transport.stop(reason)
                self._reconcile_core()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            with self._lock:
                self._coordinator_last_error = f"{type(exc).__name__}: {exc}"
            with suppress(Exception):
                if self.runtime.is_running:
                    self.runtime.stop(reason="coordinator failed")
            raise

    def _voice_stop_reason(self) -> str | None:
        if self.voice_transport is None or not self._voice_is_active():
            return None
        with self._lock:
            master_enabled = self._master_enabled
            runtime_generation = self._runtime_generation
        if not master_enabled:
            return "master switch off"
        snapshot = self.ingress.session_snapshot()
        if snapshot.session_pending:
            return "browser session replaced"
        if not snapshot.active:
            return "browser disconnected"
        if runtime_generation is not None and snapshot.generation != runtime_generation:
            return "browser session generation changed"
        if not self.source.is_running:
            return "shared media source stopped"
        if not snapshot.heartbeat_fresh:
            return "browser inactive"
        if not snapshot.video_fresh or not snapshot.audio_fresh:
            return "browser media stale"
        return None

    def _voice_is_active(self) -> bool:
        if self.voice_transport is None:
            return False
        try:
            snapshot = self.voice_transport.snapshot()
        except Exception:
            return True
        state = snapshot.get("state")
        return bool(snapshot.get("ptt_active")) or state not in {None, "off"}

    def _stop_voice_from_sync(self, reason: str) -> None:
        if self.voice_transport is None:
            return
        if not self._voice_is_active():
            return
        with self._lock:
            loop = self._server_loop
            server_thread = self._server_thread
        if loop is None or not loop.is_running():
            return
        if current_thread() is server_thread:
            raise RuntimeError("voice stop must be awaited on the ingress event loop")
        future = asyncio.run_coroutine_threadsafe(
            self.voice_transport.stop(reason), loop
        )
        future.result(timeout=5)
