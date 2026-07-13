# AttentiveSlides UI + Live Runtime Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not delegate to subagents unless the user explicitly requests delegation. Keep the checkboxes and execution ledger current.

**Goal:** Deliver and push one maintainable branch, `codex/ui-live-runtime-integration-v1`, whose only production UI is the teammate's latest `apps/streamlit_attentive_slides.py` and whose Live mode uses the existing browser media, VAD/STT, gaze-grid sensing, and continuous runtime.

**Architecture:** Start from frontend commit `3af3c52`, merge backend commit `e3f1939`, then add a thin bridge instead of a second pipeline. The uploaded deck remains canonical; the live backend publishes one bounded proposal to the Streamlit interaction panel; confirmation and the final LLM call remain owned by the existing Main UI. A minimal slide component reports manual rectangles and viewport CSS geometry while the current coarse 3×3 gaze remains in use.

**Tech Stack:** Python 3.11, Streamlit, aiohttp, standard-library `queue`, Pillow, existing OpenCV/MediaPipe/faster-whisper/VAD modules, plain HTML/CSS/JavaScript Streamlit component protocol, `unittest`.

## Global Constraints

- Source frontend: `feature/api-llm-pipeline@3af3c527b1de4b7cf3abe9d72c32eac6f0a39745`.
- Source backend: `codex/live-system-integration-v1@e3f193928a2601422d5face51572eeca6ee08cb1`.
- Delivery branch: `codex/ui-live-runtime-integration-v1`.
- Do not modify or merge `main`; do not create a PR unless separately authorized.
- Production entrypoint: `apps/streamlit_attentive_slides.py`; keep `apps/streamlit_live.py` as diagnostics.
- Default confirmation policy: `Always confirm`; user-selected `Confidence-based auto` threshold defaults to `0.80` and never goes below contract minimum `0.70`.
- Heuristic gaze may auto-confirm only after the user actively selects `Confidence-based auto`.
- Provider, response-parse, or grounding-validation exhaustion is a retryable UI error; no deterministic answer is displayed.
- Current scope is 3×3 gaze only. Do not implement point gaze, calibration, a generic event bus, a geometry framework, authentication, or multi-user state.
- Background workers never mutate `st.session_state` and never call the LLM.
- Automated tests use fakes; camera, microphone, and real API calls are manual acceptance only.
- No new Python or JavaScript dependency unless an existing required import cannot satisfy the component spike.
- Use `/root/miniconda3/bin/conda run -n attentive-app python` for backend/integration tests. Record any environment-specific exception in the execution ledger.

---

## File Map

**Create**

- `modules/system/active_deck_slide_provider.py` — adapt `UploadedDeckBrowser` to the existing `SlideProvider` protocol.
- `modules/system/slide_geometry.py` — small CSS-pixel geometry dataclasses and component-value parser.
- `modules/system/live_ui_bridge.py` — latest-only inbox, grid passthrough/aggregation, proposal runner, resolver, and runtime facade.
- `modules/ui/slide_viewport_component/__init__.py` — Streamlit component wrapper.
- `modules/ui/slide_viewport_component/index.html` — slide image, AOI overlay, manual rectangle, viewport reporting.
- `tests/test_active_deck_slide_provider.py`
- `tests/test_slide_geometry.py`
- `tests/test_live_ui_bridge.py`
- `docs/plans/UI-integration/handoffs/ui-live-runtime-integration-log.md`

**Modify**

- `modules/slide/aoi_manager.py` — merge `allow_ocr` behavior with `RLock` and atomic manifest writes.
- `modules/media/single_port_transport.py` — reset active-session media readiness and expose injectable health.
- `modules/media/live_ingress_service.py` — use the reset and report coordinator task failure.
- `modules/system/turn_context.py` — opt-in grid aggregation while preserving AOI aggregation as default.
- `modules/system/main_tutor_integration.py` — convert exhausted fallback results into retryable errors.
- `modules/system/main_ui_state.py` — minimal Live-mode session defaults.
- `apps/streamlit_attentive_slides.py` — official UI wiring, component, Live controls, proposal consumption, confirmation, logging.
- `scripts/run_live_single_port.py` — make the attentive-slides app the documented launch target without changing diagnostic support.
- Existing focused tests listed in the tasks below.

**Do not create**

- `GazeObservation`, `SlideGeometryStore`, `PointGazeResolver`, a second interaction schema, a second LLM adapter, or a second uploaded-deck store.

---

### Task 0: Create the Delivery Worktree and Merge Both Sources

**Files:**
- Modify through merge: `modules/slide/aoi_manager.py`
- Review after merge: `modules/slide/slide_parser.py`, `requirements-*.txt`, `README.md`, `PROJECT_PROGRESS.md`
- Preserve: all files and tests from both source branches

**Interfaces:**
- Consumes: the two immutable source SHAs from Global Constraints.
- Produces: isolated worktree `/root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration` on `codex/ui-live-runtime-integration-v1` with one merge commit.

- [x] **Step 1: Verify immutable inputs and existing branch/worktree names**

Run:

```bash
cd /root/autodl-tmp/workspace/AttentiveSlides-live-system
git fetch origin feature/api-llm-pipeline codex/live-system-integration-v1
git rev-parse origin/feature/api-llm-pipeline
git rev-parse origin/codex/live-system-integration-v1
git branch --list codex/ui-live-runtime-integration-v1
git worktree list
```

Expected: the first two outputs equal the Global Constraints SHAs; the delivery branch and target worktree path do not already exist. If either SHA differs, stop and report instead of silently changing the baseline.

- [x] **Step 2: Create the isolated delivery worktree**

Run:

```bash
git worktree add \
  -b codex/ui-live-runtime-integration-v1 \
  /root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration \
  3af3c527b1de4b7cf3abe9d72c32eac6f0a39745
cd /root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration
git status --short --branch
```

Expected: clean worktree on `codex/ui-live-runtime-integration-v1`.

- [x] **Step 3: Merge the live backend**

Run:

```bash
git merge --no-ff e3f193928a2601422d5face51572eeca6ee08cb1
```

Expected: merge pauses with a conflict only in `modules/slide/aoi_manager.py`. If additional conflicts appear, record them before editing.

- [x] **Step 4: Resolve the AOI manager conflict with both behaviors**

The resolved file must keep the frontend signature:

```python
def process_slide(
    self,
    deck_id: str,
    slide_id: int,
    image_path: str,
    *,
    allow_ocr: bool = True,
) -> list[AOI]:
```

It must also keep one `RLock` created in `AOIManager.__init__`, guard manifest mutation/read-modify-write operations with that lock, and retain atomic save via temporary file plus `os.replace`. Do not duplicate manifest writes or OCR calls.

Run:

```bash
git add modules/slide/aoi_manager.py
git diff --check
git diff --cached -- modules/slide/aoi_manager.py
git commit --no-edit
```

Expected: one merge commit with two parents.

- [x] **Step 5: Verify combined dependencies without adding another requirements file**

Run:

```bash
git grep -n "streamlit-drawable-canvas\|aiohttp\|faster-whisper\|webrtcvad" -- requirements*.txt
```

Expected: existing requirements files cover frontend canvas, HTTP media, Whisper, and VAD. Keep the files split by existing purpose.

- [x] **Step 6: Run the two source regression groups**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_interaction_contracts \
  tests.test_manual_targeting \
  tests.test_manual_confirmation \
  tests.test_main_tutor_integration \
  tests.test_uploaded_deck_service -v
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_live_ingress_service \
  tests.test_live_single_port_launcher \
  tests.test_sensing_worker \
  tests.test_turn_context \
  tests.test_system_controller -v
```

Expected: PASS. Environment/import failures are recorded separately from behavior failures and resolved before Task 1.

- [x] **Step 7: Record Checkpoint 0**

Append branch SHA, test commands, pass counts, and any semantic merge notes to `docs/plans/UI-integration/handoffs/ui-live-runtime-integration-log.md`, then commit:

```bash
git add docs/plans/UI-integration/handoffs/ui-live-runtime-integration-log.md
git commit -m "docs: record UI live merge baseline"
```

---

### Task 1: Fix the Two Live Ingress Lifecycle Defects

**Files:**
- Modify: `modules/media/single_port_transport.py`
- Modify: `modules/media/live_ingress_service.py`
- Modify: `tests/test_live_ingress_service.py`
- Modify: `tests/test_single_port_transport.py`

**Interfaces:**
- Produces: `FallbackMediaIngress.reset_active_readiness(reason: str) -> bool`.
- Produces: `build_fallback_app(ingress=None, *, capture_html=None, health_check=None) -> web.Application`.
- Produces: `LiveIngressService.health_status() -> tuple[bool, dict[str, object]]`.

- [x] **Step 1: Replace the incorrect deck-reload regression expectation**

Replace `test_external_shared_source_stop_restarts_runtime_through_fresh_gate` with a test that asserts no restart until both new tracks arrive:

```python
def test_external_source_stop_requires_new_video_and_audio(self):
    original_start = self.runtime.start

    def start_runtime_and_source():
        self.source.start()
        original_start()

    self.runtime.start = start_runtime_and_source
    self.start_ready_session()
    self.source.stop(reason="deck reload")

    self.service.reconcile_once()
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 1)

    self.ingress.accept_video_jpeg(
        "session-a", jpeg_payload(), timestamp=2.0
    )
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 1)

    self.ingress.accept_audio_pcm(
        "session-a",
        pcm_payload(),
        timestamp=2.1,
        sample_rate=16_000,
        channels=1,
    )
    self.service.reconcile_once()
    self.assertEqual(self.runtime.start_count, 2)
```

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_live_ingress_service.LiveIngressServiceTest.test_external_source_stop_requires_new_video_and_audio -v
```

Expected: FAIL because the second reconcile still reuses old freshness.

- [x] **Step 2: Add the smallest readiness reset**

Add to `FallbackMediaIngress`:

```python
def reset_active_readiness(
    self,
    *,
    reason: str,
) -> bool:
    with self._lock:
        if self._active_session_id is None:
            return False
        self._last_video_received_at = None
        self._last_audio_received_at = None
        self._cleanup_reason = reason
        self.source.start()
        return True
```

In the `not self.source.is_running` branch of `LiveIngressService.reconcile_once()`, stop the runtime, clear `_runtime_generation`, then call:

```python
self.ingress.reset_active_readiness(
    reason="shared media source stopped"
)
```

Run the failing test again. Expected: PASS.

- [x] **Step 3: Write coordinator health tests**

Add tests covering a healthy pending task and a task that ended with an exception:

```python
class LiveIngressCoordinatorHealthTest(
    unittest.IsolatedAsyncioTestCase
):
    async def test_health_is_unavailable_after_coordinator_failure(self):
        clock = FakeClock()
        source = BrowserMediaSource(clock=clock)
        ingress = FallbackMediaIngress(
            source,
            clock=clock,
            start_armed=False,
            coordinated_activation=True,
        )
        service = LiveIngressService(
            runtime=FakeRuntime(),
            source=source,
            ingress=ingress,
            clock=clock,
            port=0,
        )

        async def fail():
            raise RuntimeError("reconcile exploded")

        task = asyncio.create_task(fail())
        with self.assertRaisesRegex(RuntimeError, "reconcile exploded"):
            await task
        service._coordinator_task = task
        service._coordinator_last_error = "RuntimeError: reconcile exploded"

        healthy, payload = service.health_status()
        self.assertFalse(healthy)
        self.assertEqual(payload["status"], "error")
        self.assertIn("reconcile exploded", payload["coordinator_last_error"])
```

Also add an aiohttp route test asserting `/health` returns 503 when an injected `health_check` returns `(False, payload)`.

Run both new tests. Expected: FAIL because the health callback and state do not exist.

- [x] **Step 4: Make health reflect the coordinator task**

Add `_coordinator_last_error: str | None = None` in `LiveIngressService.__init__` and reset it before creating the coordinator task.

Implement:

```python
def health_status(
    self,
) -> tuple[bool, dict[str, object]]:
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
```

Change `build_fallback_app` to accept the optional callback and implement the route as:

```python
async def health(_request: web.Request) -> web.Response:
    if health_check is None:
        return web.json_response({"status": "ok"})
    healthy, payload = health_check()
    return web.json_response(
        payload,
        status=200 if healthy else 503,
    )
```

Pass `health_check=self.health_status` when `LiveIngressService` builds the app.

Wrap `_coordinate` without swallowing cancellation:

```python
async def _coordinate(self) -> None:
    try:
        while True:
            self.reconcile_once()
            await asyncio.sleep(self._interval)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        with self._lock:
            self._coordinator_last_error = (
                f"{type(exc).__name__}: {exc}"
            )
        with suppress(Exception):
            if self.runtime.is_running:
                self.runtime.stop(reason="coordinator failed")
        raise
```

- [x] **Step 5: Run lifecycle and launcher regressions**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_live_ingress_service \
  tests.test_single_port_transport \
  tests.test_live_single_port_launcher -v
git diff --check
```

Expected: PASS, including the new 503 behavior.

- [x] **Step 6: Commit**

```bash
git add modules/media/single_port_transport.py \
  modules/media/live_ingress_service.py \
  tests/test_live_ingress_service.py \
  tests/test_single_port_transport.py
git commit -m "fix: harden live ingress lifecycle readiness"
```

---

### Task 2: Use the Uploaded Frontend Deck as the Only Production Deck

**Files:**
- Create: `modules/system/active_deck_slide_provider.py`
- Create: `tests/test_active_deck_slide_provider.py`
- Modify: `modules/slide/aoi_manager.py` only if Task 0 tests expose a merged behavior defect

**Interfaces:**
- Consumes: `UploadedDeckBrowser.get_slide(slide_id) -> MainUISlide`.
- Produces: `ActiveDeckSlideProvider.set_browser(browser)`, `clear()`, and `get_slide_frame(slide_id) -> SlideFrame`.

- [x] **Step 1: Write provider tests**

Use a fake browser whose `get_slide` returns a `MainUISlide`; assert deck ID, slide ID, AOI IDs, text, neighbor text, and image path are copied exactly. Add tests that `get_slide_frame` before `set_browser` raises `RuntimeError`, and replacing the browser changes the deck atomically.

Core assertion:

```python
provider.set_browser(browser)
frame = provider.get_slide_frame(2)
self.assertEqual(frame.deck_id, browser.deck_id)
self.assertEqual(
    [aoi.aoi_id for aoi in frame.aois],
    [aoi.aoi_id for aoi in browser.get_slide(2).aois],
)
```

Run the new test. Expected: FAIL because the module does not exist.

- [x] **Step 2: Implement the adapter**

Implement exactly one lock and no caching:

```python
class ActiveDeckSlideProvider:
    def __init__(self) -> None:
        self._lock = RLock()
        self._browser: UploadedDeckBrowser | None = None

    def set_browser(self, browser: UploadedDeckBrowser) -> None:
        with self._lock:
            self._browser = browser

    def clear(self) -> None:
        with self._lock:
            self._browser = None

    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        with self._lock:
            browser = self._browser
        if browser is None:
            raise RuntimeError("No uploaded deck is active.")
        slide = browser.get_slide(slide_id)
        return SlideFrame(
            deck_id=browser.deck_id,
            slide_id=slide.slide_id,
            aois=list(slide.aois),
            slide_text=slide.slide_text,
            neighbor_slide_text=slide.neighbor_slide_text,
            slide_image_path=slide.image_path,
        )
```

- [x] **Step 3: Verify provider and AOI concurrency behavior**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_active_deck_slide_provider \
  tests.test_uploaded_deck_service \
  tests.test_aoi_manager_concurrency -v
```

Expected: PASS.

- [x] **Step 4: Commit**

```bash
git add modules/system/active_deck_slide_provider.py \
  tests/test_active_deck_slide_provider.py
git commit -m "feat: adapt uploaded deck for live sensing"
```

---

### Task 3: Build the Minimal Slide Viewport Component and Pass the Coordinate Gate

**Files:**
- Create: `modules/system/slide_geometry.py`
- Create: `modules/ui/slide_viewport_component/__init__.py`
- Create: `modules/ui/slide_viewport_component/index.html`
- Create: `tests/test_slide_geometry.py`
- Modify: `tests/test_main_ui_widget_inventory.py`

**Interfaces:**
- Produces: `ViewportBBox`, `SlideViewportGeometry`, `parse_component_geometry(payload, received_at)`.
- Produces: `render_slide_viewport(*, deck_id, slide, layout_revision, drawing_enabled, show_aoi_overlay, key) -> dict[str, object] | None`.
- Component returns: `deck_id`, `slide_id`, `layout_revision`, viewport/slide/AOI rects, DPR, and optional normalized manual bbox.

- [ ] **Step 1: Write pure geometry parser tests**

Test valid CSS-pixel payload parsing, negative viewport coordinates after scroll, invalid rectangle ordering, missing AOI IDs, and deck/slide identity preservation. The parser receives `received_at` from Python and must ignore any browser timestamp for freshness.

Run the new tests. Expected: FAIL because `slide_geometry.py` does not exist.

- [ ] **Step 2: Implement the geometry dataclasses and parser**

Use plain dataclasses:

```python
@dataclass(frozen=True)
class ViewportBBox:
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if self.x1 >= self.x2 or self.y1 >= self.y2:
            raise ValueError("ViewportBBox requires x1 < x2 and y1 < y2.")

@dataclass(frozen=True)
class SlideViewportGeometry:
    deck_id: str
    slide_id: int
    layout_revision: int
    received_at: float
    viewport_width: float
    viewport_height: float
    device_pixel_ratio: float
    slide_rect: ViewportBBox
    aoi_rects: dict[str, ViewportBBox]
```

Do not import the normalized AOI `BBox` or Member 2's `BBox`.

- [ ] **Step 3: Implement the dependency-free component wrapper**

Declare the component from the checked-in static directory. Convert the slide image to a data URL in Python and pass normalized AOIs. Preserve the AppTest escape hatch by returning `None` when `ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST=1`.

Required Python signature:

```python
def render_slide_viewport(
    *,
    deck_id: str,
    slide: MainUISlide,
    layout_revision: int,
    drawing_enabled: bool,
    show_aoi_overlay: bool,
    key: str,
) -> dict[str, object] | None:
```

The plain JavaScript component must:

1. listen for `streamlit:render`;
2. render one responsive image and absolutely positioned AOI rectangles;
3. use pointer down/move/up for one manual rectangle;
4. use `ResizeObserver`, parent scroll, and resize listeners;
5. add `window.frameElement.getBoundingClientRect()` offsets to the image's iframe-local rect;
6. call `streamlit:setComponentValue` with geometry plus normalized manual bbox;
7. call `streamlit:setFrameHeight` after image load and resize.

Do not add React, npm, a build pipeline, or a second visible slide.

- [ ] **Step 4: Run the technical spike before integrating the app**

Create a temporary diagnostic call in `apps/streamlit_attentive_slides.py`, launch:

```bash
/root/miniconda3/bin/conda run -n attentive-app python \
  scripts/run_live_single_port.py \
  --streamlit-app apps/streamlit_attentive_slides.py \
  --host 127.0.0.1 --port 8501
```

Through the forwarded port, verify and record:

- component returns parent viewport CSS coordinates;
- iframe offset is included;
- sidebar toggle, browser resize, and scroll update layout revision/rects;
- manual rectangle returns normalized slide coordinates;
- slide occupies approximately the same width and height as before.

Expected gate: all five pass. If `window.frameElement` is inaccessible or coordinates remain component-local, stop this task and report; do not continue with guessed offsets.

- [ ] **Step 5: Remove the temporary diagnostics and run tests**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_slide_geometry \
  tests.test_manual_targeting \
  tests.test_main_ui_widget_inventory -v
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/system/slide_geometry.py \
  modules/ui/slide_viewport_component \
  tests/test_slide_geometry.py \
  tests/test_main_ui_widget_inventory.py
git commit -m "feat: report slide viewport geometry"
```

---

### Task 4: Publish One Grid-Gaze Proposal Without Calling the Tutor

**Files:**
- Create: `modules/system/live_ui_bridge.py`
- Create: `tests/test_live_ui_bridge.py`
- Modify: `modules/system/turn_context.py`
- Modify: `tests/test_turn_context.py`

**Interfaces:**
- Produces: `LiveInteractionProposal`, `LatestProposalInbox`, `resolve_grid_target`, `ProposalTurnRunner`, `MainUILiveRuntime`.
- Consumes: existing `SensingWorker` dependency injection, `SystemController`, `AudioTurnResult`, and `TurnContextCollector`.

- [ ] **Step 1: Add an opt-in grid aggregation test**

Construct snapshots for `middle_left` and `middle_right`, instantiate `TurnContextCollector(..., aggregation_key="gaze_grid")`, and assert the dwell winner is returned in `gaze_grid`, with `predicted_aoi_id=None`. Existing default AOI aggregation tests must remain unchanged.

Run the focused test. Expected: FAIL because `aggregation_key` does not exist.

- [ ] **Step 2: Add the smallest aggregation switch**

Add constructor validation for `aggregation_key in {"aoi_id", "gaze_grid"}`. In `aggregate`, choose the weight key from either `predicted_aoi_id` or `gaze_grid`. For grid mode, construct:

```python
gaze = GazePrediction(
    slide_id=context.slide_id,
    gaze_grid=top_key,
    predicted_aoi_id=None,
    confidence=round(top_weight / total_weight, 3),
    stable_duration_sec=round(total_weight, 3),
    alternative_targets=[],
)
```

Run all `tests.test_turn_context`. Expected: PASS for old and new modes.

- [ ] **Step 3: Write bridge unit tests**

Cover:

- latest-only inbox overwrites one unconsumed proposal;
- `resolve_grid_target` uses viewport AOI rects and deterministic `(-score, aoi_id)` sorting;
- missing/mismatched geometry returns no predicted AOI;
- `target_confidence < 0.35` returns no predicted AOI;
- proposal runner publishes transcript/grid and returns `pending_confirmation=False`;
- runtime facade delegates lifecycle and clears inbox/snapshots on deck replacement.

Run the new test module. Expected: FAIL because the bridge does not exist.

- [ ] **Step 4: Implement the proposal and latest-only inbox**

Use:

```python
@dataclass(frozen=True)
class LiveInteractionProposal:
    interaction_id: str
    deck_id: str
    slide_id: int
    layout_revision: int
    transcript: str
    gaze_grid: str
    gaze_confidence: float
    stable_duration_sec: float
    predicted_aoi_id: str | None = None
    target_confidence: float = 0.0
    alternatives: tuple[TargetCandidate, ...] = ()
    original_speech_transcript: str = ""

class LatestProposalInbox:
    def __init__(self) -> None:
        self._queue: queue.Queue[LiveInteractionProposal] = queue.Queue(maxsize=1)

    def publish(self, proposal: LiveInteractionProposal) -> None:
        with suppress(queue.Empty):
            self._queue.get_nowait()
        self._queue.put_nowait(proposal)

    def pop(self) -> LiveInteractionProposal | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def clear(self) -> None:
        while self.pop() is not None:
            pass
```

- [ ] **Step 5: Reuse the existing sensing injection point for raw grid confidence**

Implement `map_gaze_grid_only(gaze, _aois) -> MemberAOIPrediction` by copying timestamp, slide ID, `gaze_grid`, confidence, and dwell, and using the grid name as the temporary non-null prediction key. This preserves the existing learning-state call but avoids the old normalized-AOI score. Configure production `SensingWorker(gaze_to_aoi=map_gaze_grid_only)` and `TurnContextCollector(aggregation_key="gaze_grid")`; diagnostic apps keep defaults.

- [ ] **Step 6: Implement proposal resolution and runner**

`resolve_grid_target` divides `(0, 0, viewport_width, viewport_height)` into 3×3 CSS-pixel cells, scores eligible AOI rects using the approved formula, and returns `dataclasses.replace` with the current geometry revision. Eligibility excludes `whole_slide` and AOIs whose normalized type is one of `footer`, `page_number`, `decoration`, or `background`.

The background proposal uses `layout_revision=-1` because it must not read Streamlit state. Resolution in the UI assigns the current component revision. Deck/slide mismatch still invalidates the proposal; no separate background geometry store is introduced.

`ProposalTurnRunner.run(audio_result, context)` must:

```python
aggregated = self.context_collector.aggregate(context)
gaze = aggregated.frame.gaze_prediction
proposal = LiveInteractionProposal(
    interaction_id=self.id_factory(),
    deck_id=context.deck_id,
    slide_id=context.slide_id,
    layout_revision=-1,
    transcript=audio_result.transcript.text,
    gaze_grid=gaze.gaze_grid,
    gaze_confidence=gaze.confidence,
    stable_duration_sec=gaze.stable_duration_sec,
    original_speech_transcript=audio_result.transcript.text,
)
self.inbox.publish(proposal)
return ProposalTurnOutcome(pending_confirmation=False)
```

It must not import `GroundedTutorAgent`, `LiveTutorAdapter`, or `InteractionLogger`.

- [ ] **Step 7: Implement the runtime facade in the same module**

`MainUILiveRuntime` wraps the existing controller and exposes only:

```python
@property
def is_running(self) -> bool:
    return self.controller.state not in {
        RuntimeState.STOPPED,
        RuntimeState.ERROR,
    }

def start(self) -> None:
    self.controller.start()

def stop(self, *, reason: str = "requested") -> None:
    self.controller.stop(reason=reason)

def handle_disconnect(self) -> None:
    self.controller.handle_disconnect()

def set_slide(self, slide_id: int) -> None:
    self.controller.set_slide(slide_id)

def poll(self) -> None:
    self.controller.poll()
```

`poll()` delegates to `controller.poll()`; the runner already published the proposal. Do not reproduce `LiveViewModel` snapshots or tutor state.

- [ ] **Step 8: Run bridge/runtime regressions and commit**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_live_ui_bridge \
  tests.test_turn_context \
  tests.test_sensing_worker \
  tests.test_system_controller \
  tests.test_live_turn_runner -v
git diff --check
```

Expected: PASS, including untouched diagnostic behavior.

Commit:

```bash
git add modules/system/live_ui_bridge.py modules/system/turn_context.py \
  tests/test_live_ui_bridge.py tests/test_turn_context.py
git commit -m "feat: bridge live turns into UI proposals"
```

---

### Task 5: Wire Live Mode into the Official Frontend and Keep One LLM Path

**Files:**
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `modules/system/main_ui_state.py`
- Modify: `modules/system/main_tutor_integration.py`
- Modify: `scripts/run_live_single_port.py`
- Modify: `tests/test_streamlit_attentive_slides.py`
- Modify: `tests/test_main_ui_state.py`
- Modify: `tests/test_main_tutor_integration.py`
- Modify: `tests/test_live_single_port_launcher.py`

**Interfaces:**
- Consumes: Tasks 2–4 adapters, component, bridge, inbox, and runtime facade.
- Produces: Manual/Live mode UI, Always-confirm/auto policy, exactly-once Main Tutor call and JSONL entry.

- [ ] **Step 1: Add minimal Live session defaults and tests**

Add only these session keys:

```python
{
    "main_interaction_mode": "Manual",
    "main_live_master_enabled": False,
    "main_confirmation_policy": "Always confirm",
    "main_auto_confirm_threshold": 0.80,
    "main_live_proposal": None,
    "main_live_original_transcript": None,
    "main_live_predicted_aoi_id": None,
    "main_live_layout_revision": None,
    "main_logged_interaction_ids": [],
}
```

Deck/slide change resets proposal fields and the current turn, but preserves mode and policy preferences. Run `tests.test_main_ui_state`; expected FAIL before implementation and PASS after.

- [ ] **Step 2: Make exhausted grounded generation retryable without changing the agent hierarchy**

Add a helper in `main_tutor_integration.py` that extracts the last provider/parse/validation error from `GroundedTutorResult.attempts`. Immediately after `agent.answer_context(...)`, reject fallback:

```python
if result.status == "fallback":
    raise RuntimeError(
        retryable_generation_error_message(result)
    )
```

Add tests for provider exception, malformed response, and validation exhaustion. Each must assert an exception message containing the real final failure and must assert no generation payload is returned. Existing successful fake-agent tests remain unchanged.

- [ ] **Step 3: Build cached live resources around the canonical deck provider**

In `apps/streamlit_attentive_slides.py`, add a cached `build_main_live_resources()` that constructs one:

- `BrowserMediaSource`;
- `ActiveDeckSlideProvider`;
- `SensingSnapshotStore`;
- `SensingWorker(..., gaze_to_aoi=map_gaze_grid_only)`;
- existing `AudioWorker` with faster-whisper;
- `TurnContextCollector(..., aggregation_key="gaze_grid")`;
- `LatestProposalInbox` and `ProposalTurnRunner`;
- `SystemController` and `MainUILiveRuntime`;
- `FallbackMediaIngress` and fixed `LiveIngressService`.

Do not construct `RealSlideProvider`, `LiveTurnRunner`, `LiveTutorAdapter`, or a live JSONL logger in this production resource graph.

- [ ] **Step 4: Replace both static/manual slide renderers with the component**

`_render_slide_workspace(view)` always calls `render_slide_viewport`. Set `drawing_enabled` only when target scope is `Manual region`. Parse geometry with Python `time.monotonic()` and store the latest geometry in `main_live_geometry`. For a returned normalized manual bbox, call `map_bbox_to_aois`, construct `ManualSelectionResult` with the component's slide pixel width/height, and pass it to the existing `_store_manual_selection` function.

When the component is disabled for AppTest, retain `_render_static_slide` as the test fallback. Remove production use of `st_canvas` after equivalent manual-selection tests pass; then remove `streamlit-drawable-canvas-fix` from `requirements-ui.txt` only if no remaining import exists.

- [ ] **Step 5: Add Live controls without redesigning the sidebar**

Add:

- `Mode`: Manual / Live;
- Live-only master switch;
- `Confirmation policy`: Always confirm / Confidence-based auto;
- threshold slider bounded `[0.70, 0.95]`, default `0.80`;
- compact transport/runtime status;
- camera preview in one collapsed expander.

Mount `st.iframe("/capture", height=340)` outside every periodic fragment. Manual mode disarms ingress and stops runtime. Binding a new uploaded browser calls provider `set_browser`, clears snapshots/inbox, and sets the active slide before enabling the master switch.

- [ ] **Step 6: Consume proposals before rendering Live interaction widgets**

Create a Live-only fragment with `run_every=0.5`. Within the fragment, in this order:

1. `runtime.poll()`;
2. `inbox.pop()`;
3. resolve against the current `SlideViewportGeometry` and AOIs;
4. discard deck/slide/revision mismatch;
5. replace the raw proposal's `layout_revision=-1` with the current geometry revision and write transcript/proposal state;
6. render command, target candidates, confirmation, tutor result, history, and XAI.

Because the fragment owns the command widget, it may set `main_typed_command` before creating that widget. The capture iframe remains outside and is not remounted by periodic fragment reruns.

- [ ] **Step 7: Build the canonical live `InteractionInput`**

Before user edits:

```python
mode="sensor_assisted"
target.source="gaze_prediction"
intent.source="speech_transcript"
intent.source_confidence=None
```

If transcript differs from `original_speech_transcript`, set `mode="hybrid"` and `intent.source="typed_text"`. If selected AOI differs from `predicted_aoi_id`, set confirmation source `manual_correction` and preserve both IDs in metadata.

Auto-confirm only when all conditions in the design spec pass. Otherwise show the same candidate selector, whole-slide option, and manual-region entry used by explicit confirmation. Unit-test the ten acceptance cases from Checkpoint 3 of the design spec.

- [ ] **Step 8: Keep tutor call and logging exactly once**

Continue calling only the existing `generate_main_tutor_response` function with the confirmed interaction, active slide, grounded agent, privacy/API gates, and conversation history already used by the Main UI.

Use `main_last_generated_interaction_id` as the API idempotency gate. On error, leave `main_confirmed_interaction` intact, show the retryable message, and do not set the last-generated ID. On success, upsert history/XAI and call the existing `InteractionLogger` only if the interaction ID is absent from `main_logged_interaction_ids`; append the ID after the write succeeds.

- [ ] **Step 9: Update launcher default and automated tests**

Change only the CLI default:

```python
parser.add_argument(
    "--streamlit-app",
    default="apps/streamlit_attentive_slides.py",
)
```

Keep `--streamlit-app apps/streamlit_live.py` working for diagnostics. Update launcher tests accordingly.

Run:

```bash
ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST=1 \
  /root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_streamlit_attentive_slides \
  tests.test_main_ui_widget_inventory \
  tests.test_main_ui_state \
  tests.test_main_tutor_integration \
  tests.test_interaction_contracts \
  tests.test_conversation_history \
  tests.test_live_single_port_launcher -v
git diff --check
```

Expected: PASS; tests use fake agents and no device/API.

- [ ] **Step 10: Commit**

```bash
git add apps/streamlit_attentive_slides.py \
  modules/system/main_ui_state.py \
  modules/system/main_tutor_integration.py \
  scripts/run_live_single_port.py \
  requirements-ui.txt \
  tests/test_streamlit_attentive_slides.py \
  tests/test_main_ui_state.py \
  tests/test_main_tutor_integration.py \
  tests/test_live_single_port_launcher.py
git commit -m "feat: integrate live runtime into main UI"
```

---

### Task 6: Full Regression, One-Port Acceptance, Documentation, and Push

**Files:**
- Modify: `docs/plans/UI-integration/handoffs/ui-live-runtime-integration-log.md`
- Modify: `docs/live_ui_usage.md`
- Modify: `README.md` only for the official launch command and capability wording

**Interfaces:**
- Produces: verified and pushed `codex/ui-live-runtime-integration-v1`.

- [ ] **Step 1: Run static and full automated validation**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m compileall -q \
  modules apps scripts tests
/root/miniconda3/bin/conda run -n attentive-app python -m unittest discover \
  -s tests -v
/root/miniconda3/bin/conda run -n attentive-app python scripts/demo_tutor_loop.py
/root/miniconda3/bin/conda run -n attentive-app python evaluation/eval_reference_resolution.py
/root/miniconda3/bin/conda run -n attentive-app python evaluation/eval_scenario_outputs.py
git diff --check
git status --short
```

Expected: all commands exit 0; status contains only intentional documentation updates.

- [ ] **Step 2: Run diagnostic smoke tests**

Launch the old diagnostic app explicitly and verify it still starts:

```bash
/root/miniconda3/bin/conda run -n attentive-app python \
  scripts/run_live_single_port.py \
  --streamlit-app apps/streamlit_live.py \
  --host 127.0.0.1 --port 8501
```

Stop it cleanly, then launch the official app using the launcher default.

- [ ] **Step 3: Complete manual one-port acceptance**

Record exact evidence for:

1. Manual upload/navigation/rectangle/confirmation/real LLM/history/XAI.
2. Live Always-confirm with camera, mic, STT autofill, predicted AOI, correction, real LLM.
3. Live user-selected auto with a high-confidence proposal.
4. Low confidence falling back to explicit choice.
5. No valid gaze falling back to whole slide/manual rectangle.
6. API/provider failure showing real retryable error, then successful retry with the same interaction ID.
7. Deck reload not restarting runtime until one new video and one new audio packet arrive.
8. Forced coordinator exception making internal `/health` return 503 and launcher report lost ingress health.

Do not claim continuous gaze or calibrated accuracy.

- [ ] **Step 4: Update concise user documentation**

Document only:

- official launch command;
- Manual/Live mode and confirmation policy;
- current capability wording: “coarse 3×3 viewport gaze targeting”;
- camera/mic and cloud-text privacy behavior;
- diagnostic app invocation;
- known limitation that point gaze/calibration is future work.

- [ ] **Step 5: Commit final evidence**

```bash
git add docs/plans/UI-integration/handoffs/ui-live-runtime-integration-log.md \
  docs/live_ui_usage.md README.md
git commit -m "docs: record UI live runtime acceptance"
```

- [ ] **Step 6: Verify branch ancestry and push**

Run:

```bash
git merge-base --is-ancestor \
  3af3c527b1de4b7cf3abe9d72c32eac6f0a39745 HEAD
git merge-base --is-ancestor \
  e3f193928a2601422d5face51572eeca6ee08cb1 HEAD
git log --oneline --decorate --graph -12
git status --short --branch
git push -u origin codex/ui-live-runtime-integration-v1
```

Expected: both ancestry checks exit 0, worktree is clean, and the remote delivery branch is created. Do not create a PR or merge `main`.

---

## Execution Ledger Template

Keep this table current in `docs/plans/UI-integration/handoffs/ui-live-runtime-integration-log.md`:

| Task | Status | Evidence | Commit | Notes |
|---|---|---|---|---|
| 0 Merge baseline | pending | — | — | — |
| 1 Ingress fixes | pending | — | — | — |
| 2 Canonical deck | pending | — | — | — |
| 3 Slide component | pending | — | — | coordinate gate blocks later tasks |
| 4 Live proposal bridge | pending | — | — | — |
| 5 Official UI integration | pending | — | — | — |
| 6 Acceptance and push | pending | — | — | — |

## Stop Conditions

Stop and report instead of expanding scope when:

- either source branch SHA no longer matches the approved baseline;
- merge reveals an ownership conflict beyond the documented files;
- the component cannot report parent viewport CSS coordinates through the official one-port launcher;
- Manual mode regresses and the fix would require rewriting teammate UI;
- live integration would require a second LLM path or background access to `st.session_state`;
- a requested fix requires point gaze, calibration, authentication, or multi-user architecture.
