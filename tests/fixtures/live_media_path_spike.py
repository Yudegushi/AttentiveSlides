"""Minimal formal-path browser gate for the single-port media transport."""

from __future__ import annotations

import asyncio
import atexit
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sys
from threading import Event, Thread
import urllib.request

from aiohttp import web

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import streamlit as st

from modules.media import BrowserMediaSource
from modules.media.single_port_transport import FallbackMediaIngress, build_fallback_app


@dataclass
class SpikeResources:
    source: BrowserMediaSource
    ingress: FallbackMediaIngress
    loop: asyncio.AbstractEventLoop
    thread: Thread

    def close(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)


@st.cache_resource
def spike_resources() -> SpikeResources:
    source = BrowserMediaSource()
    ingress = FallbackMediaIngress(source)
    host = os.environ.get("ATTENTIVE_LIVE_INGRESS_HOST", "127.0.0.1")
    port = int(os.environ.get("ATTENTIVE_LIVE_INGRESS_PORT", "8503"))
    loop = asyncio.new_event_loop()
    ready = Event()
    failure: list[BaseException] = []

    def serve() -> None:
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(build_fallback_app(ingress))

        async def start() -> None:
            try:
                await runner.setup()
                await web.TCPSite(runner, host, port).start()
            except BaseException as exc:
                failure.append(exc)
            finally:
                ready.set()

        loop.run_until_complete(start())
        if not failure:
            loop.run_forever()
        loop.run_until_complete(runner.cleanup())
        loop.close()

    thread = Thread(target=serve, name="live-media-path-spike", daemon=True)
    thread.start()
    if not ready.wait(timeout=30):
        raise TimeoutError("media ingress did not bind within 30 seconds")
    if failure:
        raise RuntimeError("media ingress failed to start") from failure[0]
    with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"media ingress health returned {response.status}")
    resources = SpikeResources(source, ingress, loop, thread)
    atexit.register(resources.close)
    return resources


@st.fragment(run_every=1.0)
def render_stats(resources: SpikeResources) -> None:
    payload = resources.ingress.stats_payload()
    payload["source_identity"] = id(resources.source)
    payload["ingress_source_identity"] = id(resources.ingress.source)
    payload["shared_source"] = resources.ingress.source is resources.source
    st.json(payload)


st.set_page_config(page_title="AttentiveSlides media path spike")
st.title("AttentiveSlides formal-path media spike")
resources = spike_resources()
st.iframe("/capture", height=620)
uploaded = st.file_uploader("PDF integrity check", type=["pdf"])
if uploaded is not None:
    payload = uploaded.getvalue()
    st.json({"pdf_bytes": len(payload), "pdf_sha256": hashlib.sha256(payload).hexdigest()})
render_stats(resources)
