# Local MobileViT Fatigue Reminder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Do not use subagents unless the user explicitly requests them. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the pinned member2 MobileViT-v2 checkpoint on the Lenovo RTX 4060 and show a gray real-time fatigue probability plus a sustained-fatigue amber reminder in AttentiveSlides.

**Architecture:** Reuse the existing single browser camera and FaceMesh. The browser posts a `224x224` face crop at 2 Hz through the current single-port ingress to a bounded latest-only queue; a non-critical CUDA fatigue worker publishes an isolated in-memory snapshot that a 0.5-second Streamlit fragment renders. Fatigue data never enters Tutor, AOI, confirmation, or adaptive-policy contracts.

**Tech Stack:** Python 3.10, PyTorch 2.5.1+cu121, timm 1.0.27, OpenCV, NumPy, aiohttp, Streamlit, browser Canvas/FaceMesh, systemd user service.

## Global Constraints

- Work in `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration` on its existing branch; create no branch or worktree.
- Do not modify the EyeTheia repository.
- Inference/deployment only; do not train or fine-tune.
- Do not push or merge.
- Do not run a baseline suite or any RED/expected-failing test.
- After each checkpoint, run only its named focused GREEN group.
- Do not run browser automation. Static source-contract unit tests are permitted.
- Perform one whole-change diff review after all implementation checkpoints.
- Run the complete unit suite once after review and any bounded fixes.
- Keep weights outside Git and never download them during application startup.
- Fatigue is informational only and must not mutate `LearningState`, `possible_review_needed`, adaptive strategy, AOI selection, confirmation, or Tutor behavior.
- Do not persist face crops or probability history.

## Pinned Model Artifact

- Hugging Face repository: `mosesb/drowsiness-detection-mobileViT-v2`
- Revision: `1aa87742178ae3a57b259d797b318bec696b02e1`
- Filename: `best_model.pt`
- Size: `69935051` bytes
- SHA-256: `fcbe35c8e0c8149bed84189ab3cf0a06429107a968667a9f681ff113bed35867`
- Architecture: `mobilevitv2_200`
- Labels: `0=Drowsy`, `1=Non Drowsy`
- Runtime path: `/home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2/best_model.pt`

## Planned File Map

- Create `modules/fatigue/__init__.py`: public fatigue contracts.
- Create `modules/fatigue/state.py`: probability validation, time-based EMA, hysteresis, thread-safe latest snapshot.
- Create `modules/fatigue/mobilevit_estimator.py`: pinned artifact constants, strict model loading, preprocessing, FP16 CUDA inference.
- Create `modules/system/fatigue_worker.py`: latest-only queue consumer and non-critical lifecycle.
- Create `modules/ui/fatigue_status.py`: pure UI text/banner view mapping.
- Create `scripts/prepare_mobilevit_fatigue.py`: explicit pinned download, checksum verification, and optional dummy inference.
- Create `requirements-fatigue.txt`: `timm==1.0.27`.
- Modify `modules/media/media_packets.py`: immutable `FaceCropPacket`.
- Modify `modules/media/browser_media_source.py`: one-item fatigue queue, accept/clear/stats.
- Modify `modules/media/__init__.py`: export `FaceCropPacket`.
- Modify `modules/media/single_port_transport.py`: bounded fatigue JPEG ingestion, route, freshness/stats.
- Modify `modules/media/live_capture_component/index.html`: FaceMesh-derived crop and 2 Hz latest-only upload.
- Modify `modules/system/controller.py`: optional best-effort fatigue worker start/stop.
- Modify `apps/streamlit_attentive_slides.py`: construct fatigue resources and render top status fragment.
- Modify `tests/test_browser_media_source.py`, `tests/test_single_port_transport.py`, and `tests/test_system_controller.py`.
- Create `tests/test_fatigue_state.py`, `tests/test_mobilevit_fatigue_estimator.py`, `tests/test_fatigue_worker.py`, and `tests/test_main_ui_fatigue_status.py`.

---

### Task 1: Fatigue State, EMA, and Hysteresis

**Files:**
- Create: `modules/fatigue/__init__.py`
- Create: `modules/fatigue/state.py`
- Create: `tests/test_fatigue_state.py`

**Interfaces:**
- Produces: `FatigueSnapshot`, `FatigueTemporalConfig`, `FatigueTemporalTracker.update(probability, now)`, `FatigueTemporalTracker.reset()`, `FatigueStateStore.publish(snapshot)`, `FatigueStateStore.snapshot(now=None)`, and `FatigueStateStore.clear()`.
- Consumed later by: the worker and Streamlit UI.

- [ ] **Step 1: Implement immutable state contracts and validation**

Add:

    FatigueStatus = Literal["waiting", "ready", "unavailable"]

    @dataclass(frozen=True)
    class FatigueSnapshot:
        status: FatigueStatus = "waiting"
        raw_probability: float | None = None
        smoothed_probability: float | None = None
        alert_active: bool = False
        updated_at: float | None = None
        error: str | None = None

        def __post_init__(self) -> None:
            for value in (self.raw_probability, self.smoothed_probability):
                if value is not None and not 0.0 <= float(value) <= 1.0:
                    raise ValueError("fatigue probabilities must be normalized")
            if self.alert_active and self.status != "ready":
                raise ValueError("only a ready fatigue snapshot may alert")

Use this configuration:

    @dataclass(frozen=True)
    class FatigueTemporalConfig:
        ema_time_constant_seconds: float = 1.5
        enter_threshold: float = 0.75
        enter_duration_seconds: float = 3.0
        exit_threshold: float = 0.45
        exit_duration_seconds: float = 5.0
        stale_after_seconds: float = 2.0

Validate positive durations and `0 <= exit_threshold < enter_threshold <= 1`.

- [ ] **Step 2: Implement time-based smoothing and gates**

`update` must:

1. Reset before processing when `now - last_update_at > stale_after_seconds`.
2. Initialize EMA to the first probability.
3. Otherwise use `alpha = 1 - exp(-dt / ema_time_constant_seconds)`.
4. Start/clear `high_since` around the enter threshold.
5. Activate only after a continuous 3 seconds above 0.75.
6. While active, start/clear `low_since` around the exit threshold.
7. Clear only after a continuous 5 seconds below 0.45.
8. Preserve alert state between thresholds.
9. Return a ready `FatigueSnapshot` using the server monotonic `now`.

`FatigueStateStore.snapshot(now=None)` must use the injected/current monotonic clock when omitted and return a waiting snapshot with no alert when the stored ready snapshot is older than 2 seconds. `publish` and `clear` must use an `RLock`.

- [ ] **Step 3: Add focused GREEN tests**

Cover in `tests/test_fatigue_state.py`:

- first sample initializes raw/smoothed values;
- high probability cannot alert before 3 seconds and does alert at 3 seconds;
- values in the hysteresis band preserve alert state;
- low probability clears only after 5 seconds;
- a gap over 2 seconds resets EMA/gates;
- the store suppresses stale alerts;
- invalid probabilities/configurations raise `ValueError`.

- [ ] **Step 4: Run the checkpoint GREEN group**

Run:

    /home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_fatigue_state -v

Expected: all tests in `tests.test_fatigue_state` pass.

- [ ] **Step 5: Commit**

    git add modules/fatigue/__init__.py modules/fatigue/state.py tests/test_fatigue_state.py
    git commit -m "feat: add temporal fatigue reminder state"

---

### Task 2: Strict MobileViT Estimator and Explicit Artifact Preparation

**Files:**
- Create: `modules/fatigue/mobilevit_estimator.py`
- Create: `scripts/prepare_mobilevit_fatigue.py`
- Create: `requirements-fatigue.txt`
- Create: `tests/test_mobilevit_fatigue_estimator.py`

**Interfaces:**
- Consumes: BGR uint8 face crops shaped `(224, 224, 3)`.
- Produces: `MobileViTFatigueEstimator.predict(face_bgr) -> float` where the value is `p_drowsy`.
- Produces for deployment: `verify_artifact(path) -> None` and `prepare_artifact(target) -> Path`.

- [ ] **Step 1: Add the pinned dependency and artifact constants**

`requirements-fatigue.txt` contains exactly:

    timm==1.0.27

Define the pinned repo, revision, filename, byte size, SHA-256, architecture, label indices, ImageNet mean/std, and default external path in `mobilevit_estimator.py`.

- [ ] **Step 2: Implement checksum and strict state-dict loading**

`verify_artifact(path)` must reject a missing file, wrong byte size, or wrong SHA-256.

`MobileViTFatigueEstimator.__init__` must:

- import `timm` lazily so the base UI can start without the optional dependency;
- select the requested device, defaulting to environment `ATTENTIVE_FATIGUE_DEVICE=cuda`;
- reject CUDA configuration when CUDA is unavailable;
- call `timm.create_model("mobilevitv2_200", pretrained=False, num_classes=2)`;
- call `torch.load(path, map_location="cpu", weights_only=True)`;
- unwrap only `state_dict`, `model_state_dict`, or `model`;
- remove only leading `module.` or `model.`;
- use `model.load_state_dict(normalized, strict=True)`;
- move to device and `eval()`;
- retain `use_fp16 = device.type == "cuda"`.

Do not call Hugging Face from this constructor.

- [ ] **Step 3: Implement preprocessing and inference**

Use OpenCV/NumPy:

    rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_AREA)
    normalized = resized.astype(np.float32) / 255.0
    normalized = (normalized - IMAGENET_MEAN) / IMAGENET_STD
    tensor = torch.from_numpy(
        np.ascontiguousarray(np.transpose(normalized, (2, 0, 1)))
    ).unsqueeze(0)

Run under `torch.inference_mode()` and CUDA FP16 autocast. Softmax the two logits in FP32 and return index 0. Reject invalid image shapes and non-finite output.

- [ ] **Step 4: Implement the explicit preparation script**

`scripts/prepare_mobilevit_fatigue.py` accepts:

    --target /home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2/best_model.pt
    --check

It must call `huggingface_hub.hf_hub_download` with the exact repo, revision, and filename, copy atomically through a sibling temporary file, verify before replacement, and print the final path/SHA. With `--check`, initialize the estimator and run one black `224x224` dummy image, printing `p_drowsy` and CUDA device.

- [ ] **Step 5: Add focused GREEN tests with injected fakes**

Tests must not download the weight. Patch lazy `timm.create_model`, `torch.load`, and artifact verification to cover:

- correct architecture and strict state load;
- known prefix normalization;
- BGR-to-RGB/ImageNet preprocessing shape and dtype;
- softmax returns class-zero probability;
- runtime loader never calls `hf_hub_download`;
- missing/corrupt artifact is rejected before model initialization.

- [ ] **Step 6: Run the checkpoint GREEN group**

Run:

    /home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_mobilevit_fatigue_estimator -v

Expected: all estimator tests pass without network or a real checkpoint.

- [ ] **Step 7: Commit**

    git add requirements-fatigue.txt modules/fatigue/mobilevit_estimator.py scripts/prepare_mobilevit_fatigue.py tests/test_mobilevit_fatigue_estimator.py
    git commit -m "feat: add pinned MobileViT fatigue estimator"

---

### Task 3: Same-Camera Face-Crop Transport

**Files:**
- Modify: `modules/media/media_packets.py`
- Modify: `modules/media/browser_media_source.py`
- Modify: `modules/media/__init__.py`
- Modify: `modules/media/single_port_transport.py`
- Modify: `modules/media/live_capture_component/index.html`
- Modify: `tests/test_browser_media_source.py`
- Modify: `tests/test_single_port_transport.py`

**Interfaces:**
- Produces: `FaceCropPacket(image, timestamp, timestamp_clock)`.
- Produces: `BrowserMediaSource.face_crop_queue` with size one and `accept_face_crop(image: np.ndarray, *, timestamp: float, timestamp_clock: str) -> bool`.
- Produces: `POST /attentive-media/fatigue`.
- Consumed later by: `FatigueWorker`.

- [ ] **Step 1: Add the immutable packet and one-item queue**

`FaceCropPacket` mirrors `VideoPacket` but requires exactly `(224, 224, 3)`. Export it from `modules.media`.

`BrowserMediaSource` must:

- create `face_crop_queue = BoundedMediaQueue(1, item_size=lambda packet: packet.image.nbytes)`;
- activate/close/clear it alongside video/audio;
- expose `accept_face_crop(image, timestamp, timestamp_clock)`;
- add `face_crop_fps`, queue depth, and drops to `BrowserMediaStats`.

- [ ] **Step 2: Add bounded ingress**

Extend `FallbackMediaIngress.__init__` with `max_fatigue_bytes=256 * 1024` and `_last_fatigue_received_at`.

Add:

    def accept_fatigue_jpeg(
        self, session_id: str, payload: bytes, *, timestamp: float
    ) -> bool

It validates the active session and timestamp, decodes BGR, requires exactly `224x224`, queues it, and records server receive time. Add fatigue freshness/depth/drop fields to stats and reset them with the media session.

Add the same-origin route:

    POST /attentive-media/fatigue

The fatigue route is optional for runtime readiness: video + audio + heartbeat remain the only controller start gate.

- [ ] **Step 3: Add browser crop and upload**

In the existing component:

- create a separate `fatigueCanvas`/context;
- add `fatigueInFlight`, `lastFatigueUploadAt`, and `FATIGUE_INTERVAL_MS = 500`;
- compute min/max x/y from the 478 normalized landmarks;
- make a centered square at 1.25 times the larger face dimension and clamp it to the native canvas;
- draw into `224x224`;
- JPEG encode at quality 0.80;
- post with the existing session/timestamp headers;
- drop the attempt when one upload is already in flight;
- call it from the existing successful FaceMesh callback;
- clear flags in `stopLocalGaze`.

Do not add another `getUserMedia`, MediaStream, webcam, FaceMesh instance, port, or remote URL. A fatigue upload error must update only a gray diagnostic message or console warning and must not call `stopCapture`.

- [ ] **Step 4: Extend focused static/transport contracts**

Add assertions for:

- immutable exact-size `FaceCropPacket`;
- one-item latest-only fatigue queue and cleanup;
- active-session enforcement and 256 KiB/dimension rejection;
- route presence and fatigue stats;
- exactly one `getUserMedia`;
- `224x224`, 500 ms, JPEG 0.80, and relative fatigue endpoint;
- no second FaceMesh or absolute fatigue URL.

These are Python/static source tests only; do not launch a browser.

- [ ] **Step 5: Run the checkpoint GREEN group**

Run:

    /home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_browser_media_source tests.test_single_port_transport -v

Expected: both modules pass.

- [ ] **Step 6: Commit**

    git add modules/media/media_packets.py modules/media/browser_media_source.py modules/media/__init__.py modules/media/single_port_transport.py modules/media/live_capture_component/index.html tests/test_browser_media_source.py tests/test_single_port_transport.py
    git commit -m "feat: stream bounded face crops for fatigue inference"

---

### Task 4: Non-Critical Fatigue Worker and Runtime Lifecycle

**Files:**
- Create: `modules/system/fatigue_worker.py`
- Modify: `modules/system/controller.py`
- Create: `tests/test_fatigue_worker.py`
- Modify: `tests/test_system_controller.py`

**Interfaces:**
- Consumes: `BrowserMediaSource.face_crop_queue`, estimator factory, tracker, and store.
- Produces: `FatigueWorker.start()`, `stop()`, `is_running`, and `last_error`.
- Controller consumes an optional `fatigue_worker`.

- [ ] **Step 1: Implement latest-only processing**

`FatigueWorker` uses a daemon thread and:

- drains the queue to the newest packet;
- initializes the estimator lazily inside the thread;
- retains the estimator object across `stop`/`start` cycles;
- calls `predict(packet.image)`;
- updates the temporal tracker with server monotonic time;
- publishes the snapshot;
- resets tracker before processing when the prior successful update is more than 2 seconds old;
- on model/inference error, publishes `status="unavailable"` with a concise error, stores `last_error`, and stops only its own thread;
- on normal stop, clears the store and tracker but does not unload the model.

Use a 50 ms empty-queue wait; never busy-spin.

Add `record_external_error(exc)` to set `last_error` and publish an unavailable snapshot using the worker clock. This is the controller boundary for an unexpected synchronous start failure.

- [ ] **Step 2: Add optional best-effort controller lifecycle**

Add `fatigue_worker: Any | None = None` to `SystemController`.

Start it after `media_source.start()` and before the required sensing/audio workers. Unexpected fatigue start exceptions must be recorded through `record_external_error(exc)` and must not change the controller from `MONITORING`.

Stop it idempotently before `media_source.stop()`. Fatigue has no `set_slide` call.

- [ ] **Step 3: Add focused GREEN tests**

Cover:

- only the newest queued crop is classified;
- probability reaches the tracker/store;
- repeated start/stop is idempotent and retains the estimator;
- a model initialization or inference error publishes unavailable and leaves other workers untouched;
- controller starts/stops fatigue with other workers;
- an exploding fatigue worker does not prevent controller monitoring;
- disconnect/master-off clears fatigue state.

- [ ] **Step 4: Run the checkpoint GREEN group**

Run:

    /home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_fatigue_worker tests.test_system_controller -v

Expected: both modules pass.

- [ ] **Step 5: Commit**

    git add modules/system/fatigue_worker.py modules/system/controller.py tests/test_fatigue_worker.py tests/test_system_controller.py
    git commit -m "feat: run fatigue inference as an optional live worker"

---

### Task 5: Gray Probability and Amber Top Reminder

**Files:**
- Create: `modules/ui/fatigue_status.py`
- Modify: `apps/streamlit_attentive_slides.py`
- Create: `tests/test_main_ui_fatigue_status.py`

**Interfaces:**
- Consumes: `FatigueSnapshot`, master-switch state, and current monotonic time.
- Produces: `FatigueStatusView(probability_text, alert_text, show_alert)`.
- Main resources expose `fatigue_store`.

- [ ] **Step 1: Add a pure UI mapping**

Implement:

    @dataclass(frozen=True)
    class FatigueStatusView:
        probability_text: str
        show_alert: bool
        alert_text: str = "检测到持续疲劳迹象，建议短暂休息。"

    def build_fatigue_status_view(
        snapshot: FatigueSnapshot, *, live_enabled: bool
    ) -> FatigueStatusView:
        if not live_enabled:
            return FatigueStatusView(
                "疲劳概率（模型估计）：--（Live 未开启）",
                False,
            )
        if snapshot.status == "unavailable":
            return FatigueStatusView(
                "疲劳概率（模型估计）：--（模型不可用）",
                False,
            )
        if (
            snapshot.status != "ready"
            or snapshot.smoothed_probability is None
        ):
            return FatigueStatusView(
                "疲劳概率（模型估计）：--（等待有效人脸）",
                False,
            )
        percent = round(snapshot.smoothed_probability * 100)
        return FatigueStatusView(
            f"疲劳概率（模型估计）：{percent}%",
            snapshot.alert_active,
        )

Exact text:

- Live off: `疲劳概率（模型估计）：--（Live 未开启）`
- waiting/stale: `疲劳概率（模型估计）：--（等待有效人脸）`
- unavailable: `疲劳概率（模型估计）：--（模型不可用）`
- ready: `疲劳概率（模型估计）：{rounded_percent}%`

`show_alert` is true only for a fresh ready snapshot with `alert_active=True`.

- [ ] **Step 2: Wire the resources without touching Tutor contracts**

In `build_main_live_resources`:

- instantiate `FatigueStateStore`, `FatigueTemporalTracker`, and `FatigueWorker`;
- create the estimator through a lazy factory reading:
  - `ATTENTIVE_FATIGUE_MODEL_PATH`;
  - `ATTENTIVE_FATIGUE_DEVICE` default `cuda`;
- pass the worker to `SystemController`;
- add `fatigue_store` to `MainLiveResources`.

Do not modify `modules/common/schemas.py`, `modules/system/human_sensing_adapter.py`, `modules/interaction/adaptive_policy.py`, Tutor modules, AOI modules, or confirmation modules.

- [ ] **Step 3: Render a 0.5-second top fragment**

Add:

    @st.fragment(run_every=0.5)
    def _render_fatigue_periodic(resources: MainLiveResources) -> None:
        snapshot = resources.fatigue_store.snapshot()
        view = build_fatigue_status_view(
            snapshot,
            live_enabled=bool(
                st.session_state.get("main_interaction_mode") == "Live"
                and st.session_state.get("main_live_master_enabled")
            ),
        )
        st.caption(view.probability_text)
        if view.show_alert:
            st.warning(view.alert_text)

Call it immediately after `_render_header(view)` and before slide selection/workspace. It must not request a full app rerun.

- [ ] **Step 4: Add focused GREEN tests**

Cover exact gray text, percent rounding, stale/unavailable/off states, banner visibility, and a static main-app contract proving:

- the fragment interval is 0.5;
- it is called after `_render_header` and before `_render_slide_selector`;
- only `st.caption` and conditional `st.warning` are used;
- no reference to `possible_review_needed`, adaptive policy, or Tutor was added in the fatigue UI module.

- [ ] **Step 5: Run the checkpoint GREEN group**

Run:

    /home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_main_ui_fatigue_status -v

Expected: all fatigue UI tests pass.

- [ ] **Step 6: Commit**

    git add modules/ui/fatigue_status.py apps/streamlit_attentive_slides.py tests/test_main_ui_fatigue_status.py
    git commit -m "feat: show live fatigue probability and reminder"

---

### Task 6: Whole-Change Review and Single Full Suite

**Files:**
- Review all files changed in Tasks 1-5.
- Modify only files required to address Critical or Important findings.

- [ ] **Step 1: Perform one independent whole-change diff review**

Run:

    git diff HEAD~5 --stat
    git diff HEAD~5

Review specifically:

- no second camera/FaceMesh/port;
- no unbounded queue or upload backlog;
- no application-start download;
- strict pinned weight verification and `weights_only=True`;
- fatigue errors cannot stop required runtime workers;
- stale state cannot revive an old banner;
- no fatigue-to-Tutor/AOI/confirmation data path;
- no face/probability persistence;
- no unrelated user changes overwritten.

Record the result in the execution ledger. Do not dispatch a review subagent.

- [ ] **Step 2: Apply one bounded fix wave if required**

Only if Critical or Important issues exist, fix them and run only the directly affected focused test modules once.

- [ ] **Step 3: Run the full suite once**

Run:

    /home/charles/miniconda3/envs/pyboe/bin/python -m unittest discover -s tests -v

Expected: the entire unit suite passes. Do not rerun a passing full suite because of later commits or documentation/deployment-only changes.

- [ ] **Step 4: Commit review fixes if any**

If code changed:

    git add modules/fatigue modules/media/media_packets.py modules/media/browser_media_source.py modules/media/__init__.py modules/media/single_port_transport.py modules/media/live_capture_component/index.html modules/system/fatigue_worker.py modules/system/controller.py modules/ui/fatigue_status.py apps/streamlit_attentive_slides.py scripts/prepare_mobilevit_fatigue.py requirements-fatigue.txt tests/test_fatigue_state.py tests/test_mobilevit_fatigue_estimator.py tests/test_browser_media_source.py tests/test_single_port_transport.py tests/test_fatigue_worker.py tests/test_system_controller.py tests/test_main_ui_fatigue_status.py
    git commit -m "fix: harden local fatigue reminder integration"

If no code changed, do not create an empty commit.

---

### Task 7: Lenovo Deployment, Service Restart, and Manual Handoff

**Files outside Git:**
- Create model directory under `/home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2`.
- Modify `/home/charles/.config/systemd/user/attentiveslides-local.service`.

**Interfaces:**
- Produces: installed pinned weight, CUDA model initialization, active local launcher, and visible UI diagnostics.

- [ ] **Step 1: Install only the fatigue dependency into pyboe**

Run:

    /home/charles/miniconda3/envs/pyboe/bin/python -m pip install -r requirements-fatigue.txt

Expected: `timm==1.0.27` installs without replacing the existing CUDA PyTorch/Torchvision.

Verify:

    /home/charles/miniconda3/envs/pyboe/bin/python -c "import timm, torch; print(timm.__version__, torch.__version__, torch.cuda.is_available())"

Expected: `1.0.27 2.5.1+cu121 True`.

- [ ] **Step 2: Download, verify, and initialize the pinned model**

Run once:

    /home/charles/miniconda3/envs/pyboe/bin/python scripts/prepare_mobilevit_fatigue.py --target /home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2/best_model.pt --check

Expected:

- final SHA equals `fcbe35c8e0c8149bed84189ab3cf0a06429107a968667a9f681ff113bed35867`;
- byte size equals `69935051`;
- device is CUDA;
- dummy `p_drowsy` is finite and between 0 and 1.

- [ ] **Step 3: Add explicit service environment**

Preserve the existing unit and add before `exec`:

    export ATTENTIVE_FATIGUE_MODEL_PATH=/home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2/best_model.pt
    export ATTENTIVE_FATIGUE_DEVICE=cuda

Do not print or alter DashScope secrets. Keep Whisper and runtime-data variables unchanged.

- [ ] **Step 4: Restart the existing launcher**

Run:

    systemctl --user daemon-reload
    systemctl --user restart attentiveslides-local.service
    systemctl --user --no-pager --full status attentiveslides-local.service

Expected: the existing service is active; no new service or port is created.

- [ ] **Step 5: Perform the bounded non-browser deployment checks**

Run:

    curl -fsS http://127.0.0.1:8501/health
    systemctl --user --no-pager --full status eyetheia-personalized.service attentiveslides-local.service
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv,noheader
    journalctl --user -u attentiveslides-local.service -n 120 --no-pager

Expected:

- AttentiveSlides and EyeTheia active;
- no OOM/CUDA allocation error;
- fatigue model has no checksum/state-dict/dependency error;
- gaze and speech services remain available.

Do not run Playwright, Selenium, or any automated browser acceptance.

- [ ] **Step 6: Hand off manual acceptance**

Ask the user to:

1. open the existing AttentiveSlides URL;
2. select Live mode and enable the master switch;
3. confirm the gray line updates with a percentage when one face is visible;
4. confirm no-face changes it to waiting and no amber banner remains;
5. simulate sustained fatigue to confirm the amber banner appears;
6. return to an awake pose to confirm it clears after the recovery interval;
7. confirm AOI/gaze, transcript, and Tutor behavior are unchanged.

Do not push or merge after acceptance.

## Concise Execution Ledger

Maintain only:

| Checkpoint | Focused GREEN | Commit | Blocker | Next |
|---|---|---|---|---|
| Temporal state | pending | pending | none | estimator |
| Estimator | pending | pending | none | transport |
| Transport | pending | pending | none | worker |
| Worker lifecycle | pending | pending | none | UI |
| UI reminder | pending | pending | none | whole review |
| Whole review/full suite | pending | optional fix | none | deploy |
| Deployment | pending | n/a | none | manual acceptance |
