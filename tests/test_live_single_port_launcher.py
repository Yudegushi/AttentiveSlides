import sys
import gzip
import io
import socket
import unittest
from unittest.mock import patch

from aiohttp import ClientSession, WSMsgType, web
from aiohttp.test_utils import TestServer


class LiveSinglePortLauncherSpikeTest(unittest.TestCase):
    def test_official_main_ui_is_the_default(self):
        from scripts.run_live_single_port import parse_args

        self.assertEqual(
            parse_args([]).streamlit_app,
            "apps/streamlit_attentive_slides.py",
        )

    def test_diagnostic_app_remains_selectable(self):
        from scripts.run_live_single_port import parse_args

        self.assertEqual(
            parse_args(
                ["--streamlit-app", "apps/streamlit_live.py"]
            ).streamlit_app,
            "apps/streamlit_live.py",
        )

    def test_streamlit_child_uses_current_interpreter(self):
        from scripts.run_live_single_port import build_streamlit_command

        command = build_streamlit_command("tests/fixtures/live_media_path_spike.py", "127.0.0.1", 8502)

        self.assertEqual(command[:3], [sys.executable, "-m", "streamlit"])
        self.assertIn("tests/fixtures/live_media_path_spike.py", command)

    def test_capture_routes_use_private_namespace_and_streamlit_media_stays_streamlit(self):
        from scripts.run_live_single_port import select_origin

        streamlit = "http://127.0.0.1:8502"
        ingress = "http://127.0.0.1:8503"
        self.assertEqual(select_origin("/capture", streamlit, ingress), ingress)
        self.assertEqual(
            select_origin("/attentive-media/video", streamlit, ingress),
            ingress,
        )
        self.assertEqual(select_origin("/media/thumbnail.jpg", streamlit, ingress), streamlit)
        self.assertEqual(select_origin("/_stcore/stream", streamlit, ingress), streamlit)
        self.assertEqual(select_origin("/", streamlit, ingress), streamlit)

    def test_overlapping_ports_are_rejected(self):
        from scripts.run_live_single_port import validate_distinct_bindings

        with self.assertRaisesRegex(ValueError, "distinct"):
            validate_distinct_bindings(
                ("127.0.0.1", 8501),
                ("127.0.0.1", 8501),
                ("127.0.0.1", 8503),
            )

    def test_streamlit_websocket_protocols_are_forwarded(self):
        from scripts.run_live_single_port import websocket_protocols

        self.assertEqual(
            websocket_protocols("streamlit, 2|session-token"),
            ("streamlit", "2|session-token"),
        )

    @patch("scripts.run_live_single_port.socket.socket")
    def test_preflight_uses_server_reuse_semantics(self, socket_factory):
        from scripts.run_live_single_port import preflight_bindings

        candidate = socket_factory.return_value
        preflight_bindings([("127.0.0.1", 8501)])

        candidate.setsockopt.assert_called_once_with(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
        )

    @patch("scripts.run_live_single_port.subprocess.Popen")
    def test_child_stdout_and_stderr_are_inherited(self, popen):
        from scripts.run_live_single_port import spawn_streamlit

        command = [sys.executable, "-m", "streamlit"]
        environment = {"ATTENTIVE_LIVE_INGRESS_PORT": "8503"}
        spawn_streamlit(command, environment)

        popen.assert_called_once_with(
            command,
            env=environment,
            stdout=None,
            stderr=None,
        )

    def test_occupied_requested_port_fails(self):
        from scripts.run_live_single_port import preflight_bindings

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        try:
            with self.assertRaises(OSError):
                preflight_bindings([listener.getsockname()])
        finally:
            listener.close()


class FakeChild:
    def __init__(self, return_code=None):
        self.return_code = return_code

    def poll(self):
        return self.return_code


class LiveSinglePortProxyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from scripts.run_live_single_port import build_proxy_app

        self.seen = []

        async def streamlit_handler(request):
            self.seen.append(("streamlit", request.path))
            if request.path == "/_stcore/stream":
                socket_response = web.WebSocketResponse(
                    protocols=("streamlit", "2|session-token")
                )
                await socket_response.prepare(request)
                async for message in socket_response:
                    if message.type == WSMsgType.BINARY:
                        await socket_response.send_bytes(message.data)
                    elif message.type == WSMsgType.TEXT:
                        await socket_response.send_str(message.data)
                return socket_response
            if request.path == "/redirect":
                raise web.HTTPFound(location=f"{self.streamlit_origin}/target")
            if request.path == "/component-gzip":
                payload = gzip.compress(b"<script>componentReady</script>")
                return web.Response(
                    body=payload,
                    content_type="text/html",
                    headers={"Content-Encoding": "gzip"},
                )
            body = await request.read()
            response = web.Response(
                body=body or f"streamlit:{request.path}".encode(),
                content_type=request.content_type or "text/plain",
                headers={"X-Upstream": "streamlit"},
            )
            response.set_cookie("live", "ok")
            return response

        async def ingress_handler(request):
            self.seen.append(("ingress", request.path))
            return web.Response(text=f"ingress:{request.path}")

        streamlit_app = web.Application(client_max_size=8 * 1024**2)
        streamlit_app.router.add_route("*", "/{path:.*}", streamlit_handler)
        self.streamlit_server = TestServer(streamlit_app)
        await self.streamlit_server.start_server()
        self.streamlit_origin = str(self.streamlit_server.make_url("/")).rstrip("/")

        ingress_app = web.Application()
        ingress_app.router.add_route("*", "/{path:.*}", ingress_handler)
        self.ingress_server = TestServer(ingress_app)
        await self.ingress_server.start_server()
        self.ingress_origin = str(self.ingress_server.make_url("/")).rstrip("/")

        self.proxy_server = TestServer(
            build_proxy_app(self.streamlit_origin, self.ingress_origin)
        )
        await self.proxy_server.start_server()
        self.client = ClientSession()

    async def asyncTearDown(self):
        await self.client.close()
        await self.proxy_server.close()
        await self.ingress_server.close()
        await self.streamlit_server.close()

    def proxy_url(self, path):
        return str(self.proxy_server.make_url(path))

    async def test_http_routes_headers_cookie_and_pdf_streaming(self):
        async with self.client.get(self.proxy_url("/capture")) as response:
            self.assertEqual(await response.text(), "ingress:/capture")
        async with self.client.post(
            self.proxy_url("/attentive-media/heartbeat")
        ) as response:
            self.assertEqual(
                await response.text(),
                "ingress:/attentive-media/heartbeat",
            )
        async with self.client.get(self.proxy_url("/media/thumbnail.jpg")) as response:
            self.assertEqual(await response.text(), "streamlit:/media/thumbnail.jpg")
        async with self.client.get(self.proxy_url("/static/app.js")) as response:
            self.assertEqual(await response.text(), "streamlit:/static/app.js")
        async with self.client.get(self.proxy_url("/")) as response:
            self.assertEqual(response.headers["X-Upstream"], "streamlit")
            self.assertEqual(response.cookies["live"].value, "ok")

        payload = b"%PDF-1.7\n" + b"x" * (2 * 1024 * 1024)
        async with self.client.post(
            self.proxy_url("/_stcore/upload_file/test"),
            data=io.BytesIO(payload),
            headers={"Content-Type": "application/pdf"},
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.read(), payload)
            self.assertEqual(response.content_type, "application/pdf")

        self.assertIn(("ingress", "/capture"), self.seen)
        self.assertIn(("ingress", "/attentive-media/heartbeat"), self.seen)
        self.assertIn(("streamlit", "/media/thumbnail.jpg"), self.seen)
        self.assertIn(("streamlit", "/_stcore/upload_file/test"), self.seen)

    async def test_streamlit_binary_websocket_round_trips(self):
        async with self.client.ws_connect(
            self.proxy_url("/_stcore/stream"),
            protocols=("streamlit", "2|session-token"),
        ) as websocket:
            await websocket.send_bytes(b"streamlit-frame")
            message = await websocket.receive(timeout=2)
            self.assertEqual(message.type, WSMsgType.BINARY)
            self.assertEqual(message.data, b"streamlit-frame")

    async def test_compressed_component_body_stays_compressed_through_proxy(self):
        async with self.client.get(
            self.proxy_url("/component-gzip")
        ) as response:
            self.assertEqual(response.headers["Content-Encoding"], "gzip")
            self.assertEqual(
                await response.text(),
                "<script>componentReady</script>",
            )

    async def test_internal_origin_is_removed_from_redirect(self):
        async with self.client.get(
            self.proxy_url("/redirect"), allow_redirects=False
        ) as response:
            location = response.headers["Location"]
            self.assertNotIn(self.streamlit_origin, location)
            self.assertEqual(location, "/target")

    async def test_premature_capture_returns_explicit_503(self):
        from scripts.run_live_single_port import build_proxy_app

        unavailable = TestServer(
            build_proxy_app(self.streamlit_origin, "http://127.0.0.1:1")
        )
        await unavailable.start_server()
        try:
            async with self.client.get(str(unavailable.make_url("/capture"))) as response:
                self.assertEqual(response.status, 503)
                self.assertIn("media ingress not ready", await response.text())
        finally:
            await unavailable.close()

    async def test_health_timeout_and_premature_child_exit_are_explicit(self):
        from scripts.run_live_single_port import wait_for_streamlit

        with self.assertRaisesRegex(RuntimeError, "code 7"):
            await wait_for_streamlit("http://127.0.0.1:1", FakeChild(7), timeout=0.01)
        with self.assertRaisesRegex(TimeoutError, "ready"):
            await wait_for_streamlit("http://127.0.0.1:1", FakeChild(), timeout=0.01)

    async def test_ingress_loss_after_first_health_stops_monitor(self):
        from scripts.run_live_single_port import monitor_services

        calls = 0

        async def health(_request):
            nonlocal calls
            calls += 1
            return web.Response(status=200 if calls == 1 else 503)

        app = web.Application()
        app.router.add_get("/health", health)
        server = TestServer(app)
        await server.start_server()
        try:
            with self.assertRaisesRegex(RuntimeError, "ingress health lost"):
                await monitor_services(
                    FakeChild(),
                    str(server.make_url("/")).rstrip("/"),
                    poll_interval_seconds=0.001,
                )
        finally:
            await server.close()


if __name__ == "__main__":
    unittest.main()
