#!/usr/bin/env python3
"""Expose Streamlit and browser media through one public aiohttp port."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
from typing import Iterable

from aiohttp import ClientConnectorError, ClientError, ClientSession, WSMsgType, web


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def build_streamlit_command(app: str, host: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        app,
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--server.headless",
        "true",
    ]


def select_origin(path: str, streamlit_origin: str, ingress_origin: str) -> str:
    is_capture_path = path == "/capture" or path.startswith("/attentive-media/")
    return ingress_origin if is_capture_path else streamlit_origin


def validate_distinct_bindings(*bindings: tuple[str, int]) -> None:
    if len(set(bindings)) != len(bindings):
        raise ValueError("public, Streamlit, and ingress bindings must be distinct")


def websocket_protocols(header: str | None) -> tuple[str, ...]:
    return tuple(value.strip() for value in (header or "").split(",") if value.strip())


def preflight_bindings(bindings: Iterable[tuple[str, int]]) -> None:
    sockets: list[socket.socket] = []
    try:
        for host, port in bindings:
            candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(candidate)
            candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            candidate.bind((host, port))
    finally:
        for candidate in sockets:
            candidate.close()


def _filtered_headers(headers, *, websocket: bool = False):
    skipped = HOP_BY_HOP_HEADERS | ({"host", "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol"} if websocket else set())
    filtered = headers.copy()
    for name in list(filtered.keys()):
        if name.lower() in skipped:
            del filtered[name]
    return filtered


def _public_response_headers(headers, *internal_origins: str):
    filtered = _filtered_headers(headers)
    location = filtered.get("Location")
    if location:
        for origin in internal_origins:
            if location.startswith(origin):
                filtered["Location"] = location[len(origin):] or "/"
                break
    return filtered


async def _proxy_websocket(request: web.Request, target: str) -> web.WebSocketResponse:
    protocols = websocket_protocols(request.headers.get("Sec-WebSocket-Protocol"))
    async with ClientSession() as client:
        upstream = await client.ws_connect(
            target,
            headers=_filtered_headers(request.headers, websocket=True),
            protocols=protocols,
            autoping=False,
        )
        downstream = web.WebSocketResponse(protocols=protocols, autoping=False)
        await downstream.prepare(request)

        async def relay(source, destination) -> None:
            async for message in source:
                if message.type == WSMsgType.TEXT:
                    await destination.send_str(message.data)
                elif message.type == WSMsgType.BINARY:
                    await destination.send_bytes(message.data)
                elif message.type == WSMsgType.PING:
                    await destination.ping(message.data)
                elif message.type == WSMsgType.PONG:
                    await destination.pong(message.data)
                elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                    break

        tasks = {
            asyncio.create_task(relay(downstream, upstream)),
            asyncio.create_task(relay(upstream, downstream)),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done | pending:
            with suppress(asyncio.CancelledError):
                await task
        await upstream.close()
        await downstream.close()
        return downstream


def build_proxy_app(streamlit_origin: str, ingress_origin: str) -> web.Application:
    async def proxy(request: web.Request) -> web.StreamResponse:
        origin = select_origin(request.path, streamlit_origin, ingress_origin)
        target = f"{origin}{request.rel_url}"
        try:
            if request.headers.get("Upgrade", "").lower() == "websocket":
                return await _proxy_websocket(request, target)
            async with ClientSession(auto_decompress=False) as client:
                async with client.request(
                    request.method,
                    target,
                    headers=_filtered_headers(request.headers),
                    data=request.content.iter_chunked(64 * 1024),
                    allow_redirects=False,
                ) as upstream:
                    response = web.StreamResponse(
                        status=upstream.status,
                        reason=upstream.reason,
                        headers=_public_response_headers(
                            upstream.headers, streamlit_origin, ingress_origin
                        ),
                    )
                    await response.prepare(request)
                    async for chunk in upstream.content.iter_chunked(64 * 1024):
                        await response.write(chunk)
                    await response.write_eof()
                    return response
        except ClientConnectorError as exc:
            if origin == ingress_origin:
                raise web.HTTPServiceUnavailable(text=f"media ingress not ready: {exc}") from exc
            raise

    app = web.Application(client_max_size=1024**3)
    app.router.add_route("*", "/{path:.*}", proxy)
    return app


async def wait_for_streamlit(origin: str, child: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    async with ClientSession() as client:
        while asyncio.get_running_loop().time() < deadline:
            return_code = child.poll()
            if return_code is not None:
                raise RuntimeError(f"Streamlit exited before readiness with code {return_code}")
            try:
                async with client.get(f"{origin}/_stcore/health") as response:
                    if response.status == 200:
                        return
            except ClientConnectorError:
                pass
            await asyncio.sleep(0.1)
    raise TimeoutError("Streamlit did not become ready within 30 seconds")


async def monitor_services(
    child: subprocess.Popen,
    ingress_origin: str,
    *,
    poll_interval_seconds: float = 0.5,
) -> None:
    ingress_was_ready = False
    async with ClientSession() as client:
        while True:
            return_code = child.poll()
            if return_code is not None:
                raise RuntimeError(f"Streamlit exited with code {return_code}")
            healthy = False
            try:
                async with client.get(f"{ingress_origin}/health") as response:
                    healthy = response.status == 200
            except ClientError:
                pass
            if healthy:
                ingress_was_ready = True
            elif ingress_was_ready:
                raise RuntimeError("media ingress health lost after readiness")
            await asyncio.sleep(poll_interval_seconds)


async def run(args: argparse.Namespace, child: subprocess.Popen) -> None:
    streamlit_origin = f"http://{args.streamlit_host}:{args.streamlit_port}"
    ingress_origin = f"http://{args.ingress_host}:{args.ingress_port}"
    await wait_for_streamlit(streamlit_origin, child)
    runner = web.AppRunner(build_proxy_app(streamlit_origin, ingress_origin))
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()
    print(f"AttentiveSlides live proxy ready at http://{args.host}:{args.port}", flush=True)
    try:
        await monitor_services(child, ingress_origin)
    finally:
        await runner.cleanup()


def spawn_streamlit(command: list[str], environment: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        env=environment,
        stdout=None,
        stderr=None,
    )


def _handle_termination(_signum, _frame) -> None:
    raise KeyboardInterrupt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--streamlit-app",
        default="apps/streamlit_attentive_slides.py",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--streamlit-host", default="127.0.0.1")
    parser.add_argument("--streamlit-port", type=int, default=8502)
    parser.add_argument("--ingress-host", default="127.0.0.1")
    parser.add_argument("--ingress-port", type=int, default=8503)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    bindings = (
        (args.host, args.port),
        (args.streamlit_host, args.streamlit_port),
        (args.ingress_host, args.ingress_port),
    )
    validate_distinct_bindings(*bindings)
    preflight_bindings(bindings)
    app = str(Path(args.streamlit_app))
    environment = os.environ.copy()
    environment["ATTENTIVE_LIVE_INGRESS_HOST"] = args.ingress_host
    environment["ATTENTIVE_LIVE_INGRESS_PORT"] = str(args.ingress_port)
    child = spawn_streamlit(
        build_streamlit_command(app, args.streamlit_host, args.streamlit_port),
        environment,
    )
    previous_sigterm = signal.signal(signal.SIGTERM, _handle_termination)
    try:
        asyncio.run(run(args, child))
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
