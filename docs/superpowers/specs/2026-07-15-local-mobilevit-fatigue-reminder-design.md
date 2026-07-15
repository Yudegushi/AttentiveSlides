# Local MobileViT Fatigue Reminder Design

**Status:** Approved on 2026-07-15

## Goal

Deploy member2's MobileViT-v2 drowsiness classifier on the Lenovo RTX 4060 and integrate it into the existing local AttentiveSlides runtime as an informational reminder only.

The feature displays:

- a small gray line with the current smoothed “fatigue probability (model estimate)”;
- a non-blocking amber banner after sustained fatigue is detected.

It must not change Tutor responses, generate review questions, alter AOI selection, affect confirmation policy, or block speech and gaze processing.

## Evidence and Model Choice

Member2 added two inference demos in commit `da480fb74b2d49ab4633cb4b010c0044381a1798`:

- `model1`: MediaPipe + YOLO11x-cls + multiprocessing + calibration + temporal fusion;
- `model2`: MediaPipe + MobileViT-v2 with direct PyTorch inference.

Neither weight is stored in the Git repository. The selected MobileViT artifact is:

- repository: `mosesb/drowsiness-detection-mobileViT-v2`;
- revision: `1aa87742178ae3a57b259d797b318bec696b02e1`;
- file: `best_model.pt`;
- size: `69,935,051` bytes;
- SHA-256: `fcbe35c8e0c8149bed84189ab3cf0a06429107a968667a9f681ff113bed35867`;
- architecture: `mobilevitv2_200`;
- classes: `Drowsy=0`, `Non Drowsy=1`;
- input: RGB `224x224`, ImageNet mean/std normalization.

MobileViT is selected because its AttentiveSlides deployment surface is smaller: direct PyTorch + timm inference, no Ultralytics runtime, no YOLO worker process, and no YOLO-specific calibration/state-machine stack. The checkpoint itself is not smaller than the YOLO checkpoint; the advantage is operational simplicity and isolation.

## Alternatives Considered

### Selected: browser face crop through the existing ingress

The existing browser FaceMesh already receives the full native camera frame and produces 478 landmarks. It will crop one square face image every 500 ms and post it to the existing same-origin media ingress. A dedicated latest-only queue and fatigue worker will run MobileViT in the AttentiveSlides process.

Advantages:

- one camera permission and one browser media stream;
- full-resolution source for the face crop;
- no Python MediaPipe dependency;
- no new port or systemd service;
- fatigue failure remains isolated from EyeTheia.

### Rejected: re-detect the face from the 320px backend video

This would avoid a new HTTP route but duplicate FaceMesh work in Python, require installing MediaPipe into `pyboe`, and classify a lower-resolution crop.

### Rejected: run MobileViT inside EyeTheia

This would reuse EyeTheia's frame and landmarks, but it couples two independent models and requires coordinated changes and deployment across the EyeTheia and AttentiveSlides repositories. A gaze service failure would also remove fatigue information.

## Architecture and Data Flow

1. The existing `getUserMedia` stream remains the only camera source.
2. The existing browser FaceMesh callback obtains exactly one 478-landmark face.
3. At most once every 500 ms, the browser:
   - computes a clamped square face box with 1.25x margin;
   - draws the crop from the native EyeTheia canvas into a separate `224x224` canvas;
   - encodes JPEG at quality `0.80`;
   - posts it to `/attentive-media/fatigue` with the current media session and timestamp headers.
4. `FallbackMediaIngress` validates:
   - active session;
   - payload at most 256 KiB;
   - decodable three-channel JPEG;
   - dimensions exactly `224x224`.
5. `BrowserMediaSource` places an immutable `FaceCropPacket` in a one-item latest-only queue.
6. `FatigueWorker` drains to the newest packet, runs MobileViT on CUDA using FP16 autocast, and passes `p_drowsy` to `FatigueTemporalTracker`.
7. `FatigueStateStore` keeps only the latest in-memory snapshot.
8. A Streamlit fragment refreshes every 0.5 seconds and renders the gray probability plus the optional amber banner near the top of the main content.

The fatigue store has no connection to `LearningState`, `possible_review_needed`, `adaptive_policy`, Tutor generation, AOI matching, or confirmation.

## Runtime Contracts

`FaceCropPacket`

- `image: np.ndarray`, immutable BGR uint8 with shape `(224, 224, 3)`;
- `timestamp: float`, browser performance timestamp;
- `timestamp_clock: str = "browser_performance_seconds"`.

`FatigueSnapshot`

- `status: "waiting" | "ready" | "unavailable"`;
- `raw_probability: float | None`;
- `smoothed_probability: float | None`;
- `alert_active: bool`;
- `updated_at: float | None`, server monotonic time;
- `error: str | None`.

The store is thread-safe. `snapshot(now=None)` uses the injected/current monotonic clock when `now` is omitted. A snapshot older than 2 seconds is presented as waiting/no-face and never shows the amber banner.

## Temporal Rules

Defaults are configurable but initially fixed to:

- inference/upload cadence: 2 Hz;
- EMA time constant: 1.5 seconds;
- enter threshold: smoothed `p_drowsy >= 0.75`;
- enter duration: 3.0 continuous seconds;
- exit threshold: smoothed `p_drowsy <= 0.45`;
- exit duration: 5.0 continuous seconds;
- stale/no-face timeout: 2.0 seconds.

Values between 0.45 and 0.75 preserve the current alert state. A gap longer than the stale timeout resets EMA and duration gates before the next valid observation. This prevents an old high score from immediately restoring an alert after the learner leaves the frame.

## UI Behavior

When Live mode and the master switch are active:

- valid fresh result: gray caption `疲劳概率（模型估计）：37%`;
- no valid face or stale crop: gray caption `疲劳概率（模型估计）：--（等待有效人脸）`;
- model/dependency/weight failure: gray caption `疲劳概率（模型估计）：--（模型不可用）`;
- active alert: amber banner `检测到持续疲劳迹象，建议短暂休息。`.

The gray value uses the smoothed probability so it does not flicker. There is no red state, sound, modal, forced pause, or repeated toast. Turning off the master switch clears the runtime fatigue state and hides the banner.

## Model Loading and Deployment

- Reuse `/home/charles/miniconda3/envs/pyboe`.
- Keep the current CUDA PyTorch `2.5.1+cu121`.
- Add only `timm==1.0.27`; do not add Ultralytics or Python MediaPipe.
- Store the weight outside Git at:
  `/home/charles/.local/share/attentiveslides/models/fatigue/mobilevitv2/best_model.pt`.
- Download only through an explicit preparation script using the pinned revision.
- Verify byte size and SHA-256 before installation and model initialization.
- The application never downloads a model at runtime.
- Load with `torch.load(..., weights_only=True)`, normalize only known `module.`/`model.` prefixes, and require a strict state-dict match.
- Load lazily on the first Live start, retain the model in memory across master-switch cycles, and stop only frame processing when Live is off.

The existing `attentiveslides-local.service` remains the sole AttentiveSlides service. It receives explicit fatigue environment variables and is restarted after dependency and weight preparation.

## Failure and Privacy Behavior

- Missing `timm`, missing/corrupt weight, CUDA initialization failure, or inference failure marks fatigue as unavailable.
- Fatigue errors do not stop the media source, sensing worker, audio worker, EyeTheia, or Tutor runtime.
- The browser drops a fatigue upload when the previous one is still in flight; it never queues an unbounded backlog.
- Face crops and probabilities remain in memory only. They are not written to runtime data, interaction logs, or model caches beyond the external static weight.
- The endpoint is same-origin and covered by the existing active media session checks.

## Verification Budget

Use the repository Lean Execution Profile:

- no baseline run;
- no RED/expected-failing run;
- one focused GREEN group after each checkpoint;
- no Playwright, Selenium, browser automation, lint, type, security, or performance suite;
- static HTML contract assertions are allowed because they do not launch a browser;
- one independent whole-change diff review after implementation;
- one full unit suite after review and fixes;
- one deployment/model initialization check;
- user performs the final browser acceptance after launcher restart.

## Acceptance Criteria

- Only one `getUserMedia` call remains.
- A valid face crop reaches a bounded one-item fatigue queue at no more than 2 Hz.
- The pinned MobileViT weight loads on CUDA and returns normalized binary probabilities.
- Gray probability text refreshes every 0.5 seconds without highlighting.
- The amber banner follows the 0.75/3s enter and 0.45/5s exit rules.
- Stale/no-face data hides the banner within 2 seconds.
- No fatigue value enters Tutor, AOI, confirmation, or review-question logic.
- EyeTheia + faster-whisper-small + MobileViT run concurrently without OOM.
- Service restart succeeds and the user can perform manual UI acceptance.
