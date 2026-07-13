# AttentiveSlides HTTP Media Live Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Do not dispatch subagents unless the user explicitly requests delegation. Steps use checkbox syntax for tracking.

**Goal:** Remove streamlit-webrtc from the formal live runtime and connect the proven same-origin HTTP media transport to the existing continuous SystemController pipeline through one SSH-forwarded TCP port.

**Architecture:** First prove the risky browser path with a minimal formal-path spike: one public aiohttp port, a minimal Streamlit page, an embedded /capture page, and /media/* backed by an explicitly injected BrowserMediaSource. Only after that gate passes, build the full lifecycle. The final public aiohttp reverse proxy owns the only externally reachable port; it routes /capture and /media/* to an internal aiohttp ingress running inside the Streamlit Python process, while routing Streamlit HTTP, upload, static, and WebSocket traffic to the internal Streamlit server. The internal ingress and LiveViewModel are constructed by one cached resource factory and share exactly one BrowserMediaSource instance.

**Tech Stack:** Python 3.10, Streamlit 1.59.1, aiohttp 3.14.1, OpenCV, NumPy, existing unittest suite, existing SystemController/LiveTurnRunner pipeline.

## Global Constraints

- SSH host: AutoDL.
- Worktree: /root/autodl-tmp/workspace/AttentiveSlides-live-system.
- Branch: codex/live-system-integration-v1.
- Required start HEAD: aaadb51bb5a1d01149a965bd340de7b4c1fa7d4f.
- Do not modify, merge, or switch main. Do not create a pull request.
- Do not debug or repair ICE, STUN, or TURN.
- apps/streamlit_live.py must not import or call webrtc_streamer.
- The diagnostic WebRTC probe may remain, but it is not a formal runtime transport.
- FallbackMediaIngress and the live runtime must share the same BrowserMediaSource object; do not create parallel sources, queues, controllers, or IPC bridges.
- Browser media remains bounded JPEG video and 16 kHz mono signed-16 PCM audio over same-origin HTTP.
- Freshness uses server-side monotonic receive times, not browser timestamps or lifetime queue counters. Initial live thresholds are 2.0 seconds for either media track and 3.0 seconds for heartbeat inactivity.
- Retain heartbeat, pagehide cleanup, bounded client in-flight requests, bounded server queues, observable drops, and no raw ingress media persistence.
- One public TCP port only. Internal Streamlit and aiohttp ports bind to 127.0.0.1.
- Media handlers only validate, decode, timestamp, enqueue, and update lifecycle state. They never run sensing, VAD, STT, LLM, or Streamlit commands.
- Preserve SystemController single-active-turn, frozen turn context, LiveTurnRunner canonical pipeline, confirmation resume, correction-over-prediction, SensingSnapshotStore, and bounded queue contracts.
- Automated tests use fakes and synthetic JPEG/PCM only; they do not access real camera, microphone, STT API, or LLM API.
- Preserve the existing untracked data/live_decks/ directory and do not stage it.
- Keep the implementation minimal: reuse FallbackMediaIngress, build_fallback_app, aiohttp, Streamlit fragments, and existing runtime objects; add no proxy framework, Nginx, Redis, multiprocessing transport, or new dependency.
- The launcher starts Streamlit with sys.executable, inherits child stdout/stderr, uses fixed requested ports, and never silently selects replacement ports.

---

## Fixed Context

### Current state

- apps/streamlit_live.py caches one LiveViewModel but still imports and calls streamlit-webrtc.
- modules/media/single_port_transport.py already validates and enqueues bounded JPEG and 16 kHz mono PCM into an injected BrowserMediaSource.
- build_fallback_app currently defaults to a new BrowserMediaSource when no ingress is passed. The formal live path must always pass the explicitly shared ingress.
- The standalone fallback has been manually verified through one SSH-forwarded port at approximately 4.68 video FPS and 10.92 audio chunks per second, including OFF queue cleanup.
- WebRTC obtained browser permissions and SDP/ICE data but repeatedly failed before playing over the SSH TCP-only route.
- SystemController, LiveTurnRunner, AudioWorker, SensingWorker, SensingSnapshotStore, and correction/confirmation tests are currently separate from the fallback ingress and must remain canonical.
- LiveViewModel.stop returns immediately when the controller is STOPPED. Therefore ingress cleanup cannot rely only on LiveViewModel.stop when media arrived before both streams were ready.
- HTTP ingress activity does not trigger a Streamlit rerun. The formal UI needs a periodic fragment to call runtime.poll and render completed results.
- Streamlit 1.59.1 exposes st.iframe(src, *, width, height, tab_index). Its installed frontend uses an iframe allow policy containing camera and microphone and a sandbox containing allow-same-origin and allow-scripts. This makes the native API a valid candidate, but only the Task 0 browser gate can prove permission behavior in the deployed path.
- Streamlit executes the app script after a browser session/WebSocket is created. Because the shared ingress is constructed inside that script, waiting for ingress health before exposing any public Streamlit route would deadlock. Launcher readiness is therefore deliberately two-phase: wait for internal Streamlit health before exposing the UI, then require the app-side ensure_started() call to wait for internal ingress health before it renders /capture.

### Confirmed browser-permission behavior

- Master ON is the only server/runtime lifecycle switch.
- ON renders and arms the capture component, which automatically attempts getUserMedia.
- If browser autoplay or permission policy blocks automatic start, the component shows one Grant camera/mic recovery button.
- The recovery button only resumes browser permission/capture. It is not a second master switch and cannot arm or start the controller while Master is OFF.

## Fixed Request

1. Before full implementation, prove the formal embedded browser path, Streamlit WebSocket, nonzero media packets, and uncorrupted PDF upload through the one-port proxy; stop immediately if this spike fails.
2. Replace the formal live WebRTC path with the existing HTTP fallback contract.
3. Route the capture component and /media/* through the same public origin and forwarded port as Streamlit.
4. Start SystemController only after currently fresh video and currently fresh audio from the same active browser session.
5. Apply identical cleanup to Master OFF, /media/stop, pagehide/disconnect, heartbeat timeout, persistent media-track staleness, session replacement, and launcher shutdown.
6. Keep lifecycle operations idempotent across Streamlit reruns.
7. Preserve the existing canonical speech, sensing, confirmation, correction, tutor, and JSONL path.
8. Prove behavior with RED-to-GREEN automated tests, full regression, and one-port manual acceptance with at least five live turns.
9. Update handoff and live transport/UI documentation, create one independent commit, and push the existing branch.

## Fixed Outputs

- Create modules/media/live_ingress_service.py.
- Create modules/media/live_capture_component/index.html.
- Create scripts/run_live_single_port.py.
- Create tests/test_live_ingress_service.py.
- Create tests/test_live_single_port_launcher.py.
- Create tests/fixtures/live_media_path_spike.py as the minimal reproducible Streamlit page used by the Task 0 browser gate.
- Modify modules/media/single_port_transport.py only with additive /health and /capture aliases plus session arming/readiness APIs needed by the formal runtime.
- Modify apps/streamlit_live.py to use one cached runtime/ingress resource bundle, render the HTTP capture component, and periodically poll.
- Modify modules/system/live_view_model.py only to expose safe worker/ingress cleanup diagnostics required by manual acceptance.
- Modify tests/test_single_port_transport.py, tests/test_streamlit_live.py, tests/test_live_view_model.py, and existing integrated/controller tests where explicit regression assertions are needed.
- Update docs/live_ui_usage.md, docs/browser_media_runtime.md, and docs/plans/live-system/handoffs/04_live_release/handoff.md.
- Include this plan in the final scoped commit.
- Push codex/live-system-integration-v1 without merging or opening a PR.

## Explicit Non-Outputs

- No WebRTC retry path in the formal UI.
- No new media source, queue abstraction, controller, tutor client, prompt, or confirmation pipeline.
- No authentication system, multi-user session manager, distributed state, TLS terminator, or production process supervisor.
- No real camera/microphone or external API in automated tests.
- No claim that the standalone media probe satisfies formal live tutor acceptance.

## File Responsibility Map

- modules/media/single_port_transport.py: bounded HTTP media validation plus additive arm/disarm, pending-to-active session coordination, server receive timestamps, and session-generation snapshot.
- modules/media/live_ingress_service.py: shared-source ownership, internal aiohttp lifecycle, readiness gate, and controller start/stop coordination.
- modules/media/live_capture_component/index.html: browser capture, preview, bounded upload pumps, heartbeat, permission recovery, and track cleanup.
- apps/streamlit_live.py: cached resource construction, Master command, stable capture iframe, periodic UI polling, and rendering only.
- scripts/run_live_single_port.py: internal Streamlit subprocess plus the one-port aiohttp reverse proxy and signal cleanup.
- tests/test_live_ingress_service.py: deterministic lifecycle contract with fake runtime and synthetic packets.
- tests/test_live_single_port_launcher.py: HTTP route, upload streaming, and WebSocket proxy tests using local fake upstreams.
- tests/fixtures/live_media_path_spike.py: minimal Streamlit iframe/upload page with a process-local injected fallback ingress, used only to prove the formal browser/proxy path before lifecycle work.

---

### Task 0: Formal-Path Technical Spike — Stop Unless It Passes

**Files:**
- Create: scripts/run_live_single_port.py
- Create: tests/fixtures/live_media_path_spike.py
- Modify: modules/media/single_port_transport.py
- Modify: tests/test_single_port_transport.py
- Read: modules/media/single_port_transport.py
- Read: modules/media/browser_media_source.py
- Read: apps/streamlit_live.py

**Interfaces:**
- Consumes: build_fallback_app(FallbackMediaIngress(injected_source)), Streamlit 1.59.1 embedding API, aiohttp ClientSession/WebSocketResponse, and one fixed public port.
- Produces: the minimum reusable proxy/launcher path plus recorded browser evidence for WebSocket stability, iframe camera/microphone permission, nonzero video/audio packets, and byte-identical PDF upload.

- [ ] **Step 1: Reconfirm the execution baseline and installed embedding API**

Run on AutoDL:

~~~bash
cd /root/autodl-tmp/workspace/AttentiveSlides-live-system
git branch --show-current
git rev-parse HEAD
git status --short --branch
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_single_port_transport \
  tests.test_streamlit_live \
  tests.test_system_controller \
  tests.test_live_integrated_turn -v
/root/miniconda3/envs/attentive-app/bin/python -c 'import inspect, streamlit as st; import streamlit.components.v1 as components; print(st.__version__); print(inspect.signature(st.iframe)); print(inspect.signature(components.iframe))'
grep -R -n 'camera.*microphone' /root/miniconda3/envs/attentive-app/lib/python3.10/site-packages/streamlit/static/static/js/IFrameUtil.*.js
~~~

Expected: branch codex/live-system-integration-v1 at aaadb51bb5a1d01149a965bd340de7b4c1fa7d4f, only the requested plan plus existing data/live_decks/ untracked, baseline tests passing, Streamlit 1.59.1, a callable relative-URL embedding API, and the installed iframe allow policy includes camera and microphone. Select the native API that is actually present; do not make later tests depend on the literal text st.iframe("/capture").

- [ ] **Step 2: Add only the route aliases required by the formal path**

Add RED assertions that build_fallback_app(explicit_ingress) exposes GET /health and GET /capture in addition to the existing routes. Implement /health as a constant readiness response and /capture as an alias of the existing fallback HTML. Do not alter packet validation, source construction, or watchdog behavior. Run tests.test_single_port_transport and require GREEN before launching a browser.

- [ ] **Step 3: Create the smallest reproducible Streamlit spike page**

tests/fixtures/live_media_path_spike.py must construct exactly one BrowserMediaSource and inject it into FallbackMediaIngress. A cached process-local helper starts build_fallback_app(ingress) on the requested loopback ingress port and waits up to 30 seconds until GET /health succeeds. The page then:

- embeds the existing fallback /capture page through relative URL /capture;
- exposes one st.file_uploader accepting PDF;
- displays uploaded byte length and SHA-256 so it can be compared with sha256sum on the original file;
- keeps the iframe outside a one-second Streamlit fragment that displays source/ingress identity and media stats from that same source;
- contains no SystemController, sensing, VAD, STT, tutor, or external API.

The fallback page's own ON button is allowed only in this spike gate. It does not define the final Master-switch UX.

- [ ] **Step 4: Implement only the minimum one-port launcher needed by the spike**

scripts/run_live_single_port.py must start the selected Streamlit app with:

~~~python
[
    sys.executable,
    "-m", "streamlit", "run", streamlit_app,
    "--server.address", streamlit_host,
    "--server.port", str(streamlit_port),
    "--server.headless", "true",
]
~~~

Do not set stdout=PIPE or stderr=PIPE; inherit them. Preflight all three fixed bind addresses and fail on collision. Wait up to 30 seconds for internal Streamlit /_stcore/health, then bind the public listener. Route /capture and /media/* to the internal ingress and all other HTTP/WebSocket traffic to Streamlit. Do not add retries, configuration layers, or production supervision beyond what the spike needs.

The launcher must not wait for ingress before the public Streamlit route is reachable: that would deadlock because the Streamlit script creates the shared ingress only after the browser WebSocket session starts. Instead, the spike page waits for ingress /health before rendering /capture; a direct premature /capture request returns an explicit 503, never an opaque proxy 502.

- [ ] **Step 5: Run the one-port browser gate before any lifecycle coordinator work**

Launch the spike with the same interpreter and one public port:

~~~bash
cd /root/autodl-tmp/workspace/AttentiveSlides-live-system
/root/miniconda3/envs/attentive-app/bin/python scripts/run_live_single_port.py \
  --streamlit-app tests/fixtures/live_media_path_spike.py \
  --host 127.0.0.1 --port 8501 \
  --streamlit-port 8502 --ingress-port 8503
~~~

Forward exactly that port from the browser machine:

~~~bash
ssh -N -L 8501:127.0.0.1:8501 AutoDL
~~~

Before upload, record the known PDF's byte count and SHA-256 locally; compare both with the values rendered by Streamlit. Then verify and record:

1. the Streamlit page and WebSocket remain connected for at least 60 seconds;
2. /capture is an iframe inside Streamlit and getUserMedia obtains both camera and microphone after browser permission is granted;
3. the injected BrowserMediaSource reports video_fps > 0 and audio_chunks_per_second > 0;
4. a known PDF uploaded through the public proxy has the same byte length and SHA-256 shown by Streamlit as the local original.

Use browser console/network evidence and launcher logs. Do not use the standalone top-level fallback page as evidence.

- [ ] **Step 6: Apply the early stop rule**

If iframe permission, WebSocket relay, media packets, or PDF integrity fails after one minimal root-cause attempt, stop execution and report exact browser/proxy/server evidence. Do not implement Tasks 1-7, do not fall back to WebRTC, and do not claim the standalone probe satisfies this gate.

- [ ] **Step 7: Proceed only after all four checks pass**

Keep the minimal launcher code for Task 4 hardening and keep the spike fixture as a reproducible regression aid. Stop its processes and confirm the public/internal ports are released before starting lifecycle work.

### Task 1: Reconfirm Baseline and Write RED Lifecycle Tests

**Files:**
- Create: tests/test_live_ingress_service.py
- Read: modules/media/single_port_transport.py
- Read: modules/media/browser_media_source.py
- Read: modules/system/live_view_model.py

**Interfaces:**
- Consumes: FallbackMediaIngress(source, coordinated_activation=True), BrowserMediaSource, runtime.start(), runtime.stop(reason=...), runtime.handle_disconnect(), runtime.is_running, and an injected monotonic clock.
- Produces: failing tests defining MediaIngressSessionSnapshot, pending-to-active generation ordering, time-based track freshness, and LiveIngressService behavior.

- [ ] **Step 1: Verify the execution baseline without altering existing files**

Run:

~~~bash
cd /root/autodl-tmp/workspace/AttentiveSlides-live-system
git branch --show-current
git rev-parse HEAD
git status --short --branch
~~~

Expected: branch codex/live-system-integration-v1 and HEAD still aaadb51bb5a1d01149a965bd340de7b4c1fa7d4f. The working tree now contains only the known Task 0 spike/route changes, the requested plan, and existing data/live_decks/; no unrelated file or generated artifact appeared.

- [ ] **Step 2: Re-run the targeted regression after the spike**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_single_port_transport \
  tests.test_streamlit_live \
  tests.test_system_controller \
  tests.test_live_integrated_turn -v
~~~

Expected: existing tests still pass before new lifecycle RED tests are added.

- [ ] **Step 3: Add deterministic RED tests**

Define a FakeRuntime with start_count, stop_count, disconnect_count, is_running, start(), stop(reason), and handle_disconnect(). Build one BrowserMediaSource, one FallbackMediaIngress using that source, and one LiveIngressService using the same source and runtime.

The test class must include these exact behaviors:

~~~python
def test_ingress_and_runtime_share_exactly_one_source(self):
    self.assertIs(self.service.source, self.source)
    self.assertIs(self.service.ingress.source, self.source)

def test_controller_starts_only_after_fresh_video_and_audio(self):
    self.service.set_master_enabled(True)
    self.ingress.start("session-a")
    self.service.reconcile_once()  # coordinator activates pending generation
    self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 0)
    self.ingress.accept_audio_pcm(
        "session-a", pcm_payload(), timestamp=1.1,
        sample_rate=16_000, channels=1,
    )
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 1)

def test_audio_only_does_not_start_controller(self):
    self.service.set_master_enabled(True)
    self.ingress.start("session-a")
    self.service.reconcile_once()
    self.ingress.accept_audio_pcm(
        "session-a", pcm_payload(), timestamp=1.0,
        sample_rate=16_000, channels=1,
    )
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 0)

def test_master_off_before_controller_start_clears_queues(self):
    self.service.set_master_enabled(True)
    self.ingress.start("session-a")
    self.service.reconcile_once()
    self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
    self.service.set_master_enabled(False)
    self.service.reconcile_once()
    self.assertFalse(self.source.is_running)
    self.assertTrue(self.source.video_queue.empty())
    self.assertTrue(self.source.audio_queue.empty())

def test_timeout_and_disconnect_stop_controller_and_source(self):
    self.start_ready_session()
    self.clock.value += 3.01
    self.assertTrue(self.ingress.stop_if_inactive())
    self.service.reconcile_once()
    self.assertEqual(self.runtime.disconnect_count, 1)
    self.assertFalse(self.source.is_running)

def test_explicit_page_stop_uses_disconnect_cleanup(self):
    self.start_ready_session("session-a")
    self.ingress.stop("session-a", reason="pagehide")
    self.service.reconcile_once()
    self.assertEqual(self.runtime.disconnect_count, 1)
    self.assertFalse(self.source.is_running)

def test_new_session_generation_restarts_readiness_gate(self):
    self.start_ready_session("session-a")
    self.assertEqual(self.runtime.start_count, 1)
    self.ingress.start("session-b")
    self.assertFalse(self.source.is_running)
    self.service.reconcile_once()
    self.assertEqual(self.runtime.stop_count, 1)
    self.assertTrue(self.source.is_running)
    self.ingress.accept_video_jpeg("session-b", jpeg_payload(), timestamp=2.0)
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 1)
    self.ingress.accept_audio_pcm(
        "session-b", pcm_payload(), timestamp=2.1,
        sample_rate=16_000, channels=1,
    )
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 2)
    self.assertEqual(self.runtime.stop_count, 1)
    self.assertTrue(self.source.is_running)

def test_lifetime_packet_history_does_not_count_as_current_freshness(self):
    self.service.set_master_enabled(True)
    self.ingress.start("session-a")
    self.service.reconcile_once()
    self.ingress.accept_video_jpeg("session-a", jpeg_payload(), timestamp=1.0)
    self.clock.value += 2.01
    self.ingress.accept_audio_pcm(
        "session-a", pcm_payload(), timestamp=1.1,
        sample_rate=16_000, channels=1,
    )
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 0)

def test_stale_track_while_running_uses_disconnect_cleanup(self):
    self.start_ready_session("session-a")
    self.clock.value += 2.01
    self.ingress.accept_audio_pcm(
        "session-a", pcm_payload(), timestamp=2.0,
        sample_rate=16_000, channels=1,
    )
    self.ingress.heartbeat("session-a")
    self.service.reconcile_once()
    self.assertEqual(self.runtime.disconnect_count, 1)
    self.assertFalse(self.source.is_running)
~~~

Also add the symmetric video-only test. Assert video_fresh and audio_fresh are computed from server monotonic last_video_received_at and last_audio_received_at, never browser timestamps or queue lifetime counters. Assert repeated set_master_enabled, reconcile_once, ensure_started, and shutdown calls do not duplicate server threads, runtime starts, or cleanup.

- [ ] **Step 4: Run RED tests**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest tests.test_live_ingress_service -v
~~~

Expected: FAIL because LiveIngressService and the additive ingress lifecycle APIs do not exist.

### Task 2: Implement the Minimal Shared-Source Ingress Lifecycle

**Files:**
- Modify: modules/media/single_port_transport.py
- Create: modules/media/live_ingress_service.py
- Modify: modules/media/__init__.py only if public imports materially simplify callers
- Test: tests/test_live_ingress_service.py
- Test: tests/test_single_port_transport.py

**Interfaces:**
- Produces: MediaIngressSessionSnapshot(armed, active, generation, pending_generation, session_pending, video_fresh, audio_fresh, heartbeat_fresh, last_video_received_at, last_audio_received_at, last_heartbeat_at, cleanup_reason), FallbackMediaIngress.arm(), disarm(reason), activate_pending(), stop_active(reason), session_snapshot(), LiveIngressService.set_master_enabled(), reconcile_once(), ensure_started(), shutdown(), and stats_payload().

- [ ] **Step 1: Add the smallest additive FallbackMediaIngress lifecycle surface**

Implement a frozen MediaIngressSessionSnapshot dataclass. FallbackMediaIngress accepts start_armed=True and coordinated_activation=False so the standalone probe remains compatible. The formal runtime passes coordinated_activation=True.

arm() only permits a session request. disarm() idempotently clears pending/active session state, stops the source, and clears both queues. In coordinated mode, start(session_id) validates and records a pending generation but never activates the new source. On replacement it immediately stops/closes the old source so old workers cannot consume packets from the new generation; it then leaves the new generation pending. Only the coordinator may call activate_pending(), which resets receive timestamps, promotes the pending generation to active, and calls source.start(). Same-session start is idempotent.

Keep the existing inactive_after_seconds constructor argument for backward compatibility and use it as the heartbeat deadline; the formal runtime passes 3.0. Add media_stale_after_seconds with a 2.0-second default. Record last_video_received_at, last_audio_received_at, and last_heartbeat_at from the injected server monotonic clock after a valid request for the active generation. Browser-provided media timestamps remain packet metadata only. session_snapshot() reads that injected clock and computes video_fresh/audio_fresh from media_stale_after_seconds and heartbeat_fresh from inactive_after_seconds. Do not derive readiness from queue counters or "ever received" flags.

Extend stats_payload() only with browser-safe lifecycle fields needed by the component: armed, session_state (inactive, pending, or active), generation, video_fresh, audio_fresh, and heartbeat_fresh. Do not expose session IDs.

Do not change JPEG decoding, PCM validation, request limits, queue sizes, timestamps, or handler responsibilities.

- [ ] **Step 2: Implement LiveIngressService by composition**

The constructor must reject mismatched object identity:

~~~python
if ingress.source is not source:
    raise ValueError("live ingress and runtime must share BrowserMediaSource")
~~~

set_master_enabled(True) arms ingress. set_master_enabled(False) disarms ingress immediately and records Master OFF cleanup. reconcile_once() performs controller transitions outside HTTP handlers:

- pending generation appears: prevent readiness for it, stop the old runtime first, then call ingress.activate_pending(), reset the ready generation, and wait for new packets;
- active generation has both video_fresh and audio_fresh: call runtime.start once;
- while runtime is running, either media track stale for more than 2.0 seconds: use the same disconnect cleanup as heartbeat loss even if heartbeat remains fresh;
- active session disappears while runtime is running: call runtime.handle_disconnect once;
- Master OFF: ensure runtime.stop(reason="master switch off") and ingress queues are stopped;
- repeated calls in the same state: no-op.

The replacement order is invariant and must be asserted in tests:

~~~text
HTTP start(session-b)
  -> stop/close old shared source
  -> record session-b as pending; do not start it
coordinator reconcile
  -> stop old runtime/controller (source stop is now idempotent)
  -> activate/reset shared source for session-b
  -> clear readiness timestamps
  -> require fresh session-b video + audio
  -> start runtime for the second time
~~~

ensure_started() starts one loopback aiohttp server thread and one coordinator/watchdog lifecycle. It builds on build_fallback_app(service.ingress), uses the GET /health and GET /capture aliases proven in Task 0, never invokes build_fallback_app without the explicit ingress, and synchronously waits for its loopback /health before returning. A bind failure or readiness timeout raises visibly before the UI renders /capture. shutdown() is idempotent and cleans the controller, active/pending ingress, aiohttp runner, event loop, and thread.

- [ ] **Step 3: Keep HTTP handlers lightweight**

The existing /media handlers may call FallbackMediaIngress methods only. Controller start/stop and pending-session activation are executed by the service coordinator calling reconcile_once(), never by start/video/audio/heartbeat/stop handlers. A start request for a coordinated session may return pending state; the component tolerates temporary conflict/pending responses and begins counting readiness only after the generation is active.

- [ ] **Step 4: Run focused GREEN tests**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_live_ingress_service \
  tests.test_single_port_transport -v
~~~

Expected: PASS, including old standalone probe behavior.

### Task 3: Add the Formal Capture Component and Replace WebRTC in the Live UI

**Files:**
- Create: modules/media/live_capture_component/index.html
- Modify: apps/streamlit_live.py
- Modify: modules/system/live_view_model.py
- Modify: tests/test_streamlit_live.py
- Modify: tests/test_live_view_model.py

**Interfaces:**
- Consumes: LiveIngressService and relative /capture route.
- Produces: one cached runtime/service bundle, Master-controlled capture iframe, periodic runtime polling, and worker cleanup diagnostics.

- [ ] **Step 1: Replace the existing WebRTC assertion with behavioral RED assertions**

Update tests/test_streamlit_live.py to assert that the formal module contains no streamlit_webrtc import/call, then exercise the capture renderer with a fake embedding callable:

~~~python
self.assertNotIn("webrtc_streamer(", source)
self.assertNotIn("streamlit_webrtc", source)

embed = Mock()
render_capture_component(embed=embed)
embed.assert_called_once()
self.assertEqual(embed.call_args.args[0], "/capture")
~~~

Inspect the periodic fragment function separately and assert it calls runtime.poll but not render_capture_component. The test must not pass merely because source text happens to contain st.iframe("/capture"). A one-time installed-version assertion may confirm the selected embedding API exists, but real camera/microphone permission evidence comes from Task 0.

Add a construction test asserting:

~~~python
self.assertIs(resources.runtime.media_source, resources.ingress.source)
self.assertIs(resources.runtime.controller.media_source, resources.ingress.source)
~~~

Add LiveViewModel snapshot assertions for audio_worker_running and sensing_worker_running under developer diagnostics.

- [ ] **Step 2: Run the UI RED tests**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_streamlit_live tests.test_live_view_model -v
~~~

Expected: FAIL because the formal UI still contains WebRTC and lacks the shared resource bundle/fragment.

- [ ] **Step 3: Build the capture HTML by extracting only proven fallback mechanics**

The component must:

- generate one document session ID;
- automatically call getUserMedia with video and audio after Master ON renders it;
- show one Grant camera/mic button only when automatic permission or AudioContext resume fails;
- call /media/start only while the server reports armed; if it returns pending, poll /media/stats for that request to become active before starting media pumps or heartbeat, without creating another session;
- send at most one 320-pixel-wide JPEG request every 200 ms;
- send at most one 16 kHz mono signed-16 PCM request at a time;
- send one heartbeat per second;
- stop tracks, timers, AudioContext nodes, and preview on server disarm/inactivity;
- register ended, mute, and unmute listeners on every browser track; ended immediately stops capture and notifies the server, mute starts a 2.0-second grace timer, unmute cancels it, and a still-muted track stops capture after the grace period;
- send a /media/stop beacon on pagehide;
- use only relative same-origin URLs;
- contain no independent ON/OFF master control and no raw-media persistence.

- [ ] **Step 4: Build one cached resource bundle**

Replace _live_runtime() with one cached builder that creates, in order:

1. one BrowserMediaSource;
2. the existing provider, snapshot store, workers, collector, tutor adapter, runner, and controller using that source;
3. one LiveViewModel;
4. one FallbackMediaIngress(source, start_armed=False, coordinated_activation=True, media_stale_after_seconds=2.0, inactive_after_seconds=3.0);
5. one LiveIngressService(runtime=view_model, source=source, ingress=ingress);
6. one ensure_started() call.

Return the view model and service together. Never construct a source inside the ingress app.

- [ ] **Step 5: Replace _render_media**

Master ON with a loaded deck calls service.set_master_enabled(True) and renders relative /capture through the Streamlit embedding API verified on installed 1.59.1. Master OFF or no deck calls service.set_master_enabled(False) and renders no capture iframe. The UI does not call runtime.start based on component state; the service freshness gate owns startup.

- [ ] **Step 6: Add periodic polling without reloading capture**

Keep the capture iframe outside the fragment. Put runtime.poll(), transport/runtime state, turn transcript, confirmation, tutor response, and developer diagnostics in a fragment with a 0.5-second run interval. Confirmation remains routed through runtime.confirm(query_id, selected_id).

- [ ] **Step 7: Run focused UI GREEN tests**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_streamlit_live \
  tests.test_live_view_model \
  tests.test_live_ingress_service -v
~~~

Expected: PASS with no formal WebRTC import/call.

### Task 4: Harden and Test the One-Port Launcher

**Files:**
- Modify: scripts/run_live_single_port.py created by Task 0
- Create: tests/test_live_single_port_launcher.py

**Interfaces:**
- Produces: build_proxy_app(streamlit_origin, ingress_origin), run_proxy(), and main() CLI.

- [ ] **Step 1: Write RED proxy tests with local fake upstreams**

Use unittest.IsolatedAsyncioTestCase and aiohttp test servers. Assert:

- GET /capture and POST /media/heartbeat reach the ingress upstream;
- GET /, /_stcore/health, static paths, and upload paths reach Streamlit;
- a binary WebSocket message through /_stcore/stream reaches a fake Streamlit echo socket and returns unchanged;
- a multi-megabyte synthetic PDF body is streamed through without truncation;
- response status, content type, cookies, and non-hop-by-hop headers survive;
- internal origins never appear in browser-facing redirects;
- CLI rejects overlapping public, Streamlit, and ingress ports.
- the child command begins with sys.executable, child stdout/stderr are inherited, and an occupied requested port fails without choosing another port;
- Streamlit health timeout, premature child exit, and ingress-not-ready /capture produce explicit failures rather than transient 502 responses.
- after ingress has first reported healthy, loss of ingress health terminates the public proxy and child instead of leaving a half-alive UI.

- [ ] **Step 2: Run proxy RED tests**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest tests.test_live_single_port_launcher -v
~~~

Expected: FAIL because the Task 0 launcher has not yet implemented all relay, readiness, and failure contracts.

- [ ] **Step 3: Implement the launcher with existing aiohttp only**

Defaults:

~~~text
public host/port: 127.0.0.1:8501
internal Streamlit: 127.0.0.1:8502
internal ingress: 127.0.0.1:8503
~~~

The launcher sets ATTENTIVE_LIVE_INGRESS_HOST and ATTENTIVE_LIVE_INGRESS_PORT for the Streamlit subprocess and starts it with the launcher's active interpreter:

~~~python
subprocess.Popen(
    [
        sys.executable,
        "-m", "streamlit", "run", "apps/streamlit_live.py",
        "--server.address", "127.0.0.1",
        "--server.port", "8502",
        "--server.headless", "true",
    ],
    stdout=None,
    stderr=None,
)
~~~

Before spawn, fail if any requested public/internal port is already bound; never auto-increment or silently replace a port. Wait at most 30 seconds for internal Streamlit /_stcore/health, checking child.poll() during the wait, before accepting the public UI. Then run one public aiohttp listener. /capture and /media/* select the ingress origin; every other path selects Streamlit. HTTP requests and responses stream bodies rather than buffering uploads. The WebSocket branch relays text, binary, close, ping, and pong frames in both directions. Remove hop-by-hop headers. Preserve the public Host/Origin semantics required by Streamlit.

Do not wait for ingress health before the public Streamlit route becomes reachable: the app session must run to construct the shared ingress. Instead, LiveIngressService.ensure_started() waits for /health before apps/streamlit_live.py renders /capture. If /capture is requested early, the proxy returns explicit HTTP 503 with ingress-not-ready detail. This two-phase readiness preserves exact source identity and avoids both startup deadlock and transient 502.

SIGINT, SIGTERM, child exit, or proxy failure terminates the Streamlit child and closes aiohttp sessions/runners. Monitor the child continuously; if it exits early, the public proxy exits and reports its return code. Before ingress has ever become ready, keep the public Streamlit route available so the app session can initialize it. After ingress has reported healthy once, poll its /health and treat later loss as an internal-service failure that shuts down the proxy and child. It must not kill unrelated processes or ports.

- [ ] **Step 4: Run launcher GREEN tests**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest tests.test_live_single_port_launcher -v
~~~

Expected: PASS without starting a real Streamlit server, camera, microphone, or API.

### Task 5: Protect Canonical Turn and Cleanup Contracts

**Files:**
- Modify: tests/test_system_controller.py only if an explicit restart assertion is absent
- Modify: tests/test_live_integrated_turn.py
- Test: tests/test_live_turn_runner.py
- Test: tests/test_turn_context.py

**Interfaces:**
- Consumes: unchanged SystemController and LiveTurnRunner public methods.
- Produces: regression evidence that transport integration did not alter canonical behavior.

- [ ] **Step 1: Extend integrated coverage through the shared ingress**

Add one deterministic integration test with these exact dependency boundaries:

- real RealSlideProvider loading a temporary real PDF;
- one shared BrowserMediaSource;
- real FallbackMediaIngress, LiveIngressService, SystemController, AudioWorker, SensingWorker, SensingSnapshotStore, and LiveTurnRunner;
- SensingWorker configured only with the deterministic fake extractor, gaze estimator, face-state detector, learning-state aggregator, head-pose function, and gaze-to-AOI function already patterned in tests/test_sensing_worker.py;
- fake transcriber and deterministic tutor;
- no default FaceLandmarkExtractor/MediaPipe/model factory and no real STT/LLM API.

Arm the live ingress, send synthetic JPEG and PCM, let the real SensingWorker publish the fake-backend snapshot, reach MONITORING only after both currently fresh media types, complete speech-end/STT with the fake transcriber, select an AOI different from the prediction, and assert:

~~~python
self.assertTrue(final.interaction_result.actual.user_corrected)
self.assertEqual(
    final.interaction_result.resolved_query.resolved_aoi_id,
    confirmed_aoi_id,
)
self.assertNotEqual(confirmed_aoi_id, predicted_aoi_id)
self.assertEqual(controller.state.value, "monitoring")
self.assertGreaterEqual(len(log_path.read_text().splitlines()), 2)
~~~

Also assert Master OFF leaves controller STOPPED, audio/sensing workers false, ingress inactive, source stopped, and both queues empty.

Assert the fake sensing factories were used and no default model/device backend was constructed. This test proves the transport-to-runtime contract, not MediaPipe accuracy.

- [ ] **Step 2: Add OFF-to-ON restart coverage**

Start a second browser session after OFF. Require fresh video and audio again, assert only one controller is active, and verify AudioWorker overrun/VAD state does not leak across sessions.

- [ ] **Step 3: Run the complete targeted suite**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_single_port_transport \
  tests.test_live_ingress_service \
  tests.test_live_single_port_launcher \
  tests.test_streamlit_live \
  tests.test_live_view_model \
  tests.test_system_controller \
  tests.test_live_turn_runner \
  tests.test_turn_context \
  tests.test_live_integrated_turn -v
~~~

Expected: PASS with synthetic media and fake STT/tutor only.

### Task 6: Run the Formal Single-Port Manual Gate

**Files:**
- Runtime log: data/logs/live_interactions.jsonl
- Do not persist raw video or audio.

- [ ] **Step 1: Start the formal launcher on AutoDL**

Default reproducible command:

~~~bash
cd /root/autodl-tmp/workspace/AttentiveSlides-live-system
/root/miniconda3/envs/attentive-app/bin/python \
  scripts/run_live_single_port.py \
  --host 127.0.0.1 \
  --port 8501 \
  --streamlit-port 8502 \
  --ingress-port 8503
~~~

- [ ] **Step 2: Forward exactly one port from the browser machine**

Run:

~~~bash
ssh -N -L 8501:127.0.0.1:8501 AutoDL
~~~

Open http://localhost:8501. If 8501 is occupied, choose one different public remote port and one local port, while still using exactly one ssh -L mapping. Internal ports remain unforwarded.

- [ ] **Step 3: Complete the required browser acceptance**

Record evidence for:

1. formal live UI opens and Streamlit WebSocket remains connected;
2. a real PDF uploads through the proxy;
3. Master ON renders capture and browser permission is granted;
4. video/audio counters become non-zero;
5. runtime reaches MONITORING only after both streams;
6. “解释一下这里” reaches automatic speech end and transcript;
7. when confirmation appears, choose an AOI different from the prediction;
8. correction overrides prediction and a tutor response is generated;
9. data/logs/live_interactions.jsonl gains the canonical records;
10. complete at least five turns without restarting the app;
11. Master OFF reports controller STOPPED, inactive ingress, stopped audio/sensing workers, zero queues, and browser tracks released;
12. close/reload, heartbeat-loss, browser track ended, and persistent single-track mute/staleness paths produce the same cleanup.

Mandatory acceptance uses the deterministic tutor so transport/runtime verification does not depend on an external provider. A grounded provider turn is optional only when the existing environment is already configured; never expose or record its key.

- [ ] **Step 4: Apply the technical stop rule**

Stop and report exact browser console, proxy, and server evidence if either condition remains after a minimal formal-path attempt:

- the same-origin /capture component cannot obtain or retain camera/microphone permission;
- the aiohttp proxy cannot reliably forward Streamlit upload or WebSocket traffic.

Do not fall back to WebRTC and do not substitute the standalone transport probe for this acceptance.

### Task 7: Regression, Documentation, Commit, and Push

**Files:**
- Modify: docs/live_ui_usage.md
- Modify: docs/browser_media_runtime.md
- Modify: docs/plans/live-system/handoffs/04_live_release/handoff.md
- Modify: modules/slide/aoi_manager.py (manual-gate concurrency regression)
- Add: tests/test_aoi_manager_concurrency.py
- Include: docs/superpowers/plans/2026-07-13-attentiveslides-http-media-live-integration.md

- [ ] **Step 1: Update documentation with measured evidence**

Document the launcher command, the single ssh -L command, route split, shared-source ownership, Master/readiness lifecycle, permission recovery behavior, five-turn evidence, measured media rates/latencies, JSONL result, OFF/disconnect cleanup, and any known limitation. Remove text that presents the standalone fallback as the selected but disconnected live path.

- [ ] **Step 2: Run complete automated regression**

Run:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m compileall -q modules apps scripts tests
/root/miniconda3/envs/attentive-app/bin/python -m unittest discover -s tests -v
/root/miniconda3/envs/attentive-app/bin/python scripts/demo_tutor_loop.py
/root/miniconda3/envs/attentive-app/bin/python evaluation/eval_reference_resolution.py
/root/miniconda3/envs/attentive-app/bin/python evaluation/eval_scenario_outputs.py
git diff --check
~~~

Expected: all automated checks pass; evaluations retain their existing accepted metrics; git diff --check has no output.

- [ ] **Step 3: Inspect the final diff and workspace**

Run:

~~~bash
git diff --stat
git diff -- apps/streamlit_live.py modules/media modules/system/live_view_model.py scripts tests docs
git status --short --branch
~~~

Confirm data/live_decks/ remains untracked and no raw-media artifact, secret, unrelated file, or generated cache is staged.

- [ ] **Step 4: Create one scoped commit**

Stage only the implementation, tests, plan, and updated documentation:

~~~bash
git add \
  apps/streamlit_live.py \
  modules/media \
  modules/slide/aoi_manager.py \
  modules/system/live_view_model.py \
  scripts/run_live_single_port.py \
  tests/test_single_port_transport.py \
  tests/test_live_ingress_service.py \
  tests/test_live_single_port_launcher.py \
  tests/test_streamlit_live.py \
  tests/test_live_view_model.py \
  tests/test_system_controller.py \
  tests/test_live_integrated_turn.py \
  tests/test_aoi_manager_concurrency.py \
  tests/fixtures/live_media_path_spike.py \
  docs/live_ui_usage.md \
  docs/browser_media_runtime.md \
  docs/plans/live-system/handoffs/04_live_release/handoff.md \
  docs/superpowers/plans/2026-07-13-attentiveslides-http-media-live-integration.md
git commit -m "fix: integrate HTTP media into live runtime"
~~~

Do not stage data/live_decks/. If a listed test file did not need a change, omit it from git add.

- [ ] **Step 5: Push only the requested branch**

Run:

~~~bash
git push origin codex/live-system-integration-v1
git status --short --branch
git log -1 --oneline --decorate
~~~

Expected: the branch push succeeds, no PR is created, main is unchanged, and only preserved data/live_decks/ remains untracked.

## Execution Notes for a Compacted Follow-up

- Re-read this entire plan and the files named in the original request before editing.
- Task 0 is a hard gate. Do not begin lifecycle coordinator or integrated runtime work until its four formal-path checks pass.
- Use systematic-debugging if any baseline test unexpectedly fails.
- Use test-driven-development for every behavior change: run the focused RED test, implement the minimum, then run GREEN.
- Use ponytail at full intensity: prefer existing aiohttp and Streamlit APIs; do not add an external proxy or component framework unless the formal-path technical gate proves the native path impossible.
- Use verification-before-completion before claiming success, committing, or pushing.
- The user has approved automatic capture with one permission-recovery button and has not authorized a second master switch.
- Browser camera/microphone approval is the only expected user interaction during Task 0; it is not a CAPTCHA and not a second Master switch.
