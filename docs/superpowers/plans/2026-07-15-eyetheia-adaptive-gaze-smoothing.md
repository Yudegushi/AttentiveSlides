# EyeTheia Adaptive Gaze Smoothing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not dispatch subagents for this plan.

**Goal:** Make local EyeTheia gaze output strongly suppress small fixation jitter while following genuine long-distance gaze shifts within about one 200 ms sample, so the visible gaze point and AOI dwell matching use the same steadier coordinates.

**Architecture:** Add a dependency-free, stateful two-dimensional adaptive exponential filter to the EyeTheia repository. It measures raw movement speed as viewport diagonals per second, maps slow movement to a long smoothing time constant and fast movement to a short time constant, and caps the first-frame response to reduce isolated large outliers. The EyeTheia WebSocket inference path passes viewport dimensions into this filter; the existing One Euro filters and tuner remain available to the legacy desktop tracking path. AttentiveSlides keeps consuming the returned `x_px`/`y_px` unchanged, so its debug point and server AOI observations stay coordinate-identical without a second filter.

**Tech Stack:** Python 3.11, standard-library `math`, PyTorch-backed EyeTheia tracker, FastAPI WebSocket endpoint, pytest.

## Global Constraints

- Work in the existing Lenovo repositories and branches; do not create another branch or worktree.
- EyeTheia implementation repository: `/home/charles/repos/EyeTheia`, current branch `codex/browser-calibration-setup`.
- Plan and integration repository: `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration`, current branch `codex/eyetheia-local-gaze-integration`.
- Do not change the EyeTheia WebSocket response contract: predictions remain `{"type":"pred","seq":...,"x_px":...,"y_px":...}` in top-level viewport CSS pixels.
- Reuse the existing `gaze_filtered` switch. When it is false, return raw coordinates; when true on the WebSocket path, use the adaptive filter.
- Use the same adaptive output for AttentiveSlides' gaze marker and `/attentive-media/gaze` upload; do not add client-side smoothing or a second AOI-only coordinate stream.
- Preserve the existing One Euro filters and `OneEuroTuner` behavior for `GazeTracker.start_tracking()`; only the WebSocket path selects the new filter by supplying viewport dimensions.
- Reset adaptive state on the existing `screen`, `reset_filter`, and configuration-toggle reset paths.
- Initial constants are fixed internal defaults: slow time constant `0.45 s`, fast time constant `0.04 s`, slow threshold `0.03 viewport diagonals/s`, fast threshold `0.20 viewport diagonals/s`, velocity time constant `0.12 s`, and maximum update alpha `0.90`.
- Do not add packages, environment variables, UI controls, persistence, browser automation, lint, type checks, performance tests, or unrelated refactors.
- Verification budget: no baseline run, no RED/expected-failing run, one focused GREEN group after each implementation checkpoint, one independent final diff review, and the EyeTheia full pytest suite exactly once after final-review fixes.
- If a focused test fails, rerun only the affected module after fixing it. If final review finds an Important or Critical issue, make one bounded fix wave, run only affected focused tests, then rerun the full suite at most once.
- Do not push or merge. Commit only the intended files in their respective current repositories.

---

### Task 1: Add the resolution-independent adaptive filter

**Files:**
- Create: `/home/charles/repos/EyeTheia/src/utils/AdaptiveGazeFilter.py`
- Create: `/home/charles/repos/EyeTheia/tests/test_AdaptiveGazeFilter.py`

**Interfaces:**
- Consumes: raw `(x_px, y_px)`, a monotonically increasing timestamp in seconds, and positive viewport width/height.
- Produces: `AdaptiveGazeFilter.filter(x_px, y_px, timestamp, viewport_width, viewport_height) -> tuple[float, float]` and `AdaptiveGazeFilter.reset() -> None`.
- State: previous raw point, previous filtered point, previous timestamp, and low-pass-filtered normalized speed.

- [ ] **Step 1: Add focused behavior tests without running a RED phase**

Create `tests/test_AdaptiveGazeFilter.py` with deterministic tests for seeding, fixation smoothing, fast following, resolution invariance, and reset:

```python
from __future__ import annotations

import pytest

from utils.AdaptiveGazeFilter import AdaptiveGazeFilter


def test_first_sample_seeds_filter_without_offset() -> None:
    gaze_filter = AdaptiveGazeFilter()

    assert gaze_filter.filter(320.0, 240.0, 1.0, 1920, 1080) == (320.0, 240.0)


def test_small_fixation_jitter_is_strongly_smoothed() -> None:
    gaze_filter = AdaptiveGazeFilter()
    gaze_filter.filter(500.0, 500.0, 0.0, 1000, 1000)

    filtered_x, filtered_y = gaze_filter.filter(505.0, 497.0, 0.2, 1000, 1000)

    assert 500.0 < filtered_x < 503.0
    assert 498.0 < filtered_y < 500.0


def test_large_gaze_shift_follows_most_of_the_distance_in_one_sample() -> None:
    gaze_filter = AdaptiveGazeFilter()
    gaze_filter.filter(100.0, 100.0, 0.0, 1000, 1000)

    filtered_x, filtered_y = gaze_filter.filter(800.0, 700.0, 0.2, 1000, 1000)

    assert filtered_x == pytest.approx(730.0)
    assert filtered_y == pytest.approx(640.0)


def test_equivalent_normalized_motion_is_resolution_independent() -> None:
    small = AdaptiveGazeFilter()
    large = AdaptiveGazeFilter()
    small.filter(100.0, 100.0, 0.0, 1000, 1000)
    large.filter(200.0, 200.0, 0.0, 2000, 2000)

    small_point = small.filter(120.0, 110.0, 0.2, 1000, 1000)
    large_point = large.filter(240.0, 220.0, 0.2, 2000, 2000)

    assert large_point[0] / 2.0 == pytest.approx(small_point[0])
    assert large_point[1] / 2.0 == pytest.approx(small_point[1])


def test_reset_makes_the_next_sample_a_fresh_seed() -> None:
    gaze_filter = AdaptiveGazeFilter()
    gaze_filter.filter(100.0, 100.0, 0.0, 1000, 1000)
    gaze_filter.filter(800.0, 700.0, 0.2, 1000, 1000)

    gaze_filter.reset()

    assert gaze_filter.filter(300.0, 400.0, 0.4, 1000, 1000) == (300.0, 400.0)
```

- [ ] **Step 2: Implement the pure adaptive filter**

Create `src/utils/AdaptiveGazeFilter.py`:

```python
from __future__ import annotations

import math


class AdaptiveGazeFilter:
    """Smooth fixation jitter while following fast gaze shifts promptly."""

    def __init__(
        self,
        *,
        slow_time_constant_sec: float = 0.45,
        fast_time_constant_sec: float = 0.04,
        slow_speed_diagonals_per_sec: float = 0.03,
        fast_speed_diagonals_per_sec: float = 0.20,
        velocity_time_constant_sec: float = 0.12,
        max_alpha: float = 0.90,
    ) -> None:
        if not 0.0 < fast_time_constant_sec <= slow_time_constant_sec:
            raise ValueError("time constants must satisfy 0 < fast <= slow")
        if not 0.0 <= slow_speed_diagonals_per_sec < fast_speed_diagonals_per_sec:
            raise ValueError("speed thresholds must satisfy 0 <= slow < fast")
        if velocity_time_constant_sec <= 0.0:
            raise ValueError("velocity_time_constant_sec must be positive")
        if not 0.0 < max_alpha <= 1.0:
            raise ValueError("max_alpha must be in (0, 1]")

        self.slow_time_constant_sec = float(slow_time_constant_sec)
        self.fast_time_constant_sec = float(fast_time_constant_sec)
        self.slow_speed_diagonals_per_sec = float(slow_speed_diagonals_per_sec)
        self.fast_speed_diagonals_per_sec = float(fast_speed_diagonals_per_sec)
        self.velocity_time_constant_sec = float(velocity_time_constant_sec)
        self.max_alpha = float(max_alpha)
        self.reset()

    def reset(self) -> None:
        self._last_raw: tuple[float, float] | None = None
        self._last_filtered: tuple[float, float] | None = None
        self._last_timestamp: float | None = None
        self._filtered_speed = 0.0

    @staticmethod
    def _alpha(delta_sec: float, time_constant_sec: float) -> float:
        return 1.0 - math.exp(-delta_sec / time_constant_sec)

    @staticmethod
    def _smoothstep(value: float) -> float:
        bounded = max(0.0, min(1.0, value))
        return bounded * bounded * (3.0 - 2.0 * bounded)

    def _seed(self, x_px: float, y_px: float, timestamp: float) -> tuple[float, float]:
        point = (float(x_px), float(y_px))
        self._last_raw = point
        self._last_filtered = point
        self._last_timestamp = float(timestamp)
        self._filtered_speed = 0.0
        return point

    def filter(
        self,
        x_px: float,
        y_px: float,
        timestamp: float,
        viewport_width: int,
        viewport_height: int,
    ) -> tuple[float, float]:
        values = (x_px, y_px, timestamp, viewport_width, viewport_height)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("gaze samples and viewport dimensions must be finite")
        if viewport_width <= 0 or viewport_height <= 0:
            raise ValueError("viewport dimensions must be positive")
        if self._last_timestamp is None or timestamp <= self._last_timestamp:
            return self._seed(x_px, y_px, timestamp)

        assert self._last_raw is not None
        assert self._last_filtered is not None
        delta_sec = float(timestamp) - self._last_timestamp
        diagonal = math.hypot(float(viewport_width), float(viewport_height))
        raw_distance = math.hypot(
            float(x_px) - self._last_raw[0],
            float(y_px) - self._last_raw[1],
        )
        raw_speed = raw_distance / diagonal / delta_sec
        velocity_alpha = self._alpha(delta_sec, self.velocity_time_constant_sec)
        self._filtered_speed += velocity_alpha * (raw_speed - self._filtered_speed)

        speed_range = (
            self.fast_speed_diagonals_per_sec
            - self.slow_speed_diagonals_per_sec
        )
        speed_fraction = (
            self._filtered_speed - self.slow_speed_diagonals_per_sec
        ) / speed_range
        blend = self._smoothstep(speed_fraction)
        time_constant = self.slow_time_constant_sec + blend * (
            self.fast_time_constant_sec - self.slow_time_constant_sec
        )
        position_alpha = min(
            self.max_alpha,
            self._alpha(delta_sec, time_constant),
        )
        filtered = (
            self._last_filtered[0]
            + position_alpha * (float(x_px) - self._last_filtered[0]),
            self._last_filtered[1]
            + position_alpha * (float(y_px) - self._last_filtered[1]),
        )

        self._last_raw = (float(x_px), float(y_px))
        self._last_filtered = filtered
        self._last_timestamp = float(timestamp)
        return filtered
```

The `smoothstep` transition avoids a hard fixation/saccade boundary. At the deployed 200 ms sample interval, the slow constant yields an alpha near `0.36`; a fast movement reaches the `0.90` cap and therefore follows 90% of the jump on its first sample.

- [ ] **Step 3: Run the first focused GREEN group once**

Run:

```bash
cd /home/charles/repos/EyeTheia
/home/charles/miniforge3/envs/eyetheia/bin/python -m pytest tests/test_AdaptiveGazeFilter.py -q
```

Expected: `5 passed`. Do not run these tests before both the test file and implementation exist.

- [ ] **Step 4: Commit the isolated filter checkpoint**

```bash
cd /home/charles/repos/EyeTheia
git add src/utils/AdaptiveGazeFilter.py tests/test_AdaptiveGazeFilter.py
git commit -m "feat: add adaptive gaze smoothing filter"
```

Record in the execution ledger: Task 1 complete, focused test result, commit hash, no blocker, Task 2 next.

---

### Task 2: Route WebSocket gaze through the adaptive filter

**Files:**
- Modify: `/home/charles/repos/EyeTheia/src/tracker/GazeTracker.py:27-35,70-82,254-283`
- Modify: `/home/charles/repos/EyeTheia/src/routes/ws_model.py:55-89`
- Modify: `/home/charles/repos/EyeTheia/src/routes/config.py:8-11,49-85`
- Modify: `/home/charles/repos/EyeTheia/tests/test_GazeTracker.py`
- Create: `/home/charles/repos/EyeTheia/tests/test_ws_model_filtering.py`

**Interfaces:**
- Consumes: `AdaptiveGazeFilter` from Task 1 and WebSocket `screen_width`/`screen_height` already maintained by `ws_predict_gaze`.
- Produces: extended `GazeTracker.filter_gaze_pixels(gaze_x_px, gaze_y_px, timestamp, screen_width=None, screen_height=None) -> tuple[float, float]`.
- Compatibility: if both dimensions are present, use adaptive smoothing; if neither is present, retain the legacy One Euro path used by the desktop tuner.

- [ ] **Step 1: Add tracker and frame-routing tests without running a RED phase**

Append these tests to `tests/test_GazeTracker.py`:

```python
def test_gaze_tracker_uses_adaptive_filter_when_viewport_is_supplied():
    tracker = GazeTracker.__new__(GazeTracker)
    tracker.adaptive_gaze_filter = MagicMock()
    tracker.adaptive_gaze_filter.filter.return_value = (123.0, 456.0)

    result = tracker.filter_gaze_pixels(100.0, 200.0, 1.25, 1920, 1080)

    assert result == (123.0, 456.0)
    tracker.adaptive_gaze_filter.filter.assert_called_once_with(
        100.0, 200.0, 1.25, 1920, 1080
    )


def test_gaze_tracker_keeps_one_euro_path_without_viewport():
    tracker = GazeTracker.__new__(GazeTracker)
    tracker.gaze_filter_x = MagicMock()
    tracker.gaze_filter_y = MagicMock()
    tracker.gaze_filter_x.filter.return_value = 101.0
    tracker.gaze_filter_y.filter.return_value = 202.0

    assert tracker.filter_gaze_pixels(100.0, 200.0, 1.25) == (101.0, 202.0)
```

Create `tests/test_ws_model_filtering.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from routes.ws_model import _process_frame_sync


def test_process_frame_passes_viewport_to_adaptive_filter() -> None:
    tracker = MagicMock()
    tracker.mp = "itracker_baseline.tar"
    tracker.gaze_filtered = True
    tracker.extract_features.return_value = ("face", "left", "right", "grid")
    tracker.predict_gaze.return_value = (0.0, 0.0)
    tracker.filter_gaze_pixels.return_value = (321.0, 654.0)

    with (
        patch("routes.ws_model.decode_image_bytes", return_value="image"),
        patch("routes.ws_model.FaceLandmarks", return_value="landmarks"),
        patch("routes.ws_model.gaze_cm_to_pixels", return_value=(300.0, 600.0)),
        patch("routes.ws_model.time.perf_counter", return_value=10.0),
    ):
        result = _process_frame_sync(
            {"landmarks": []},
            b"jpeg",
            tracker,
            1920,
            1080,
            7.5,
        )

    assert result == (321.0, 654.0)
    tracker.filter_gaze_pixels.assert_called_once_with(
        300.0,
        600.0,
        2.5,
        1920,
        1080,
    )
```

- [ ] **Step 2: Integrate the adaptive filter without removing the desktop filter**

In `src/tracker/GazeTracker.py`, import the new class:

```python
from utils.AdaptiveGazeFilter import AdaptiveGazeFilter
from utils.OneEuroTuner import OneEuroTuner
```

After the existing X/Y One Euro filter construction in `__init__`, add:

```python
self.adaptive_gaze_filter = AdaptiveGazeFilter()
```

Replace `filter_gaze_pixels` with:

```python
def filter_gaze_pixels(
    self,
    gaze_x_px: float,
    gaze_y_px: float,
    timestamp: float,
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> tuple[float, float]:
    """Filter WebSocket gaze adaptively, preserving legacy desktop filtering."""
    if (screen_width is None) != (screen_height is None):
        raise ValueError("screen_width and screen_height must be provided together")
    if screen_width is not None and screen_height is not None:
        return self.adaptive_gaze_filter.filter(
            float(gaze_x_px),
            float(gaze_y_px),
            float(timestamp),
            screen_width,
            screen_height,
        )

    filtered_x = float(self.gaze_filter_x.filter(float(gaze_x_px), timestamp))
    filtered_y = float(self.gaze_filter_y.filter(float(gaze_y_px), timestamp))
    return filtered_x, filtered_y
```

At the end of `reset_gaze_filters`, reset the new state while retaining the existing recreation of `gaze_filter_x` and `gaze_filter_y`:

```python
if hasattr(self, "adaptive_gaze_filter"):
    self.adaptive_gaze_filter.reset()
else:
    self.adaptive_gaze_filter = AdaptiveGazeFilter()
```

This `hasattr` branch supports hot-reloaded tracker instances that predate the new attribute.

In `src/routes/ws_model.py`, pass the screen dimensions already associated with the current WebSocket connection:

```python
if getattr(gaze_tracker, "gaze_filtered", True):
    timestamp = time.perf_counter() - start_time
    x_px, y_px = gaze_tracker.filter_gaze_pixels(
        x_px,
        y_px,
        timestamp,
        screen_width,
        screen_height,
    )
```

Do not change the returned tuple or the WebSocket `pred` JSON. The existing AttentiveSlides `handleEyeTheiaMessage` function will continue assigning the same returned values to both `publishDebug({kind: "gaze", ...})` and `latestGaze` for `/attentive-media/gaze`.

- [ ] **Step 3: Update stale API descriptions**

In the `src/routes/config.py` module docstring, replace the final description with:

```python
It exposes endpoints to update the screen resolution used for
coordinate normalization and gaze prediction, and to toggle adaptive
gaze filtering for real-time WebSocket output.
```

Replace the `set_gaze_filtered` docstring with:

```python
"""
Enable or disable adaptive filtering for real-time WebSocket gaze output.

:param enabled: True to enable filtering, False to disable it.
:type enabled: bool

:return: Confirmation message with current filtering state.
:rtype: dict
"""
```

Replace the `get_gaze_filtered` summary sentence with:

```python
"""Return whether adaptive real-time gaze filtering is enabled."""
```

Do not rename `/config/set_gaze_filtered`, `/config/gaze_filtered`, the `enabled` form field, or the response keys.

- [ ] **Step 4: Run the second focused GREEN group once**

Run:

```bash
cd /home/charles/repos/EyeTheia
/home/charles/miniforge3/envs/eyetheia/bin/python -m pytest \
  tests/test_AdaptiveGazeFilter.py \
  tests/test_GazeTracker.py \
  tests/test_ws_model_filtering.py -q
```

Expected: all selected tests pass. If a failure occurs, fix it and rerun only its affected test module.

- [ ] **Step 5: Commit the WebSocket integration checkpoint**

```bash
cd /home/charles/repos/EyeTheia
git add \
  src/tracker/GazeTracker.py \
  src/routes/ws_model.py \
  src/routes/config.py \
  tests/test_GazeTracker.py \
  tests/test_ws_model_filtering.py
git commit -m "feat: adapt gaze smoothing to movement speed"
```

Record in the execution ledger: Task 2 complete, focused test result, commit hash, no blocker, final review next.

---

### Task 3: Final review, bounded verification, and deployment

**Files:**
- Review only: `/home/charles/repos/EyeTheia/src/utils/AdaptiveGazeFilter.py`
- Review only: `/home/charles/repos/EyeTheia/src/tracker/GazeTracker.py`
- Review only: `/home/charles/repos/EyeTheia/src/routes/ws_model.py`
- Review only: `/home/charles/repos/EyeTheia/src/routes/config.py`
- Review only: `/home/charles/repos/EyeTheia/tests/test_AdaptiveGazeFilter.py`
- Review only: `/home/charles/repos/EyeTheia/tests/test_GazeTracker.py`
- Review only: `/home/charles/repos/EyeTheia/tests/test_ws_model_filtering.py`

**Interfaces:**
- Consumes: the two committed checkpoints.
- Produces: a reviewed EyeTheia branch, one full-suite result, and a healthy restarted personalized model service.

- [ ] **Step 1: Perform one independent whole-change review**

Run only read-only review commands:

```bash
cd /home/charles/repos/EyeTheia
git diff e96a656..HEAD --check
git diff --stat e96a656..HEAD
git diff e96a656..HEAD -- \
  src/utils/AdaptiveGazeFilter.py \
  src/tracker/GazeTracker.py \
  src/routes/ws_model.py \
  src/routes/config.py \
  tests/test_AdaptiveGazeFilter.py \
  tests/test_GazeTracker.py \
  tests/test_ws_model_filtering.py
```

Review exactly these risks:

- Small normalized motion keeps `position_alpha` low; large motion reaches but never exceeds `0.90`.
- Timestamp regression reseeds instead of producing a negative or unbounded update.
- Screen-size and explicit filter-reset messages clear adaptive history.
- `gaze_filtered=false` still bypasses all filtering in `_process_frame_sync`.
- The legacy no-viewport call in `start_tracking()` still uses tunable One Euro filters.
- `pred.x_px/y_px` remain the only coordinates consumed by both the visible debug marker and AOI upload.
- No AttentiveSlides, calibration, model-loading, or checkpoint-selection behavior changed.

If the review finds an Important or Critical issue, make one bounded fix wave and run only directly affected focused test modules before continuing.

- [ ] **Step 2: Run the full EyeTheia suite exactly once**

```bash
cd /home/charles/repos/EyeTheia
/home/charles/miniforge3/envs/eyetheia/bin/python -m pytest -q
```

Expected: the full suite passes once. Do not run an AttentiveSlides suite because that repository has no implementation changes, and do not run browser tests.

- [ ] **Step 3: Confirm repository state before deployment**

```bash
cd /home/charles/repos/EyeTheia
git status --short --branch
git log -3 --oneline
```

Expected: no uncommitted implementation changes and two new local commits on `codex/browser-calibration-setup`. Do not push or merge.

- [ ] **Step 4: Restart only the personalized EyeTheia service**

```bash
systemctl --user restart eyetheia-personalized.service
systemctl --user is-active eyetheia-personalized.service
```

Expected: `active`. AttentiveSlides need not restart because its WebSocket client reconnects automatically and its code is unchanged.

- [ ] **Step 5: Verify service identity and filter state without browser automation**

```bash
curl --fail --silent --show-error http://127.0.0.1:8001/api/health
curl --fail --silent --show-error http://127.0.0.1:8001/config/gaze_filtered
```

Expected health fields: `status=ok`, `personalized=true`, `cuda_available=true`, checkpoint `itracker_personalized_63.tar`, and 13 calibration points. Expected filter state: `{"gaze_filtered":true}`.

- [ ] **Step 6: Hand off manual acceptance to the user**

Ask the user to reload the existing AttentiveSlides page if it has not reconnected after two seconds, re-enable camera/microphone if necessary, and validate:

1. While staring within one small region, the gaze dot has visibly less jitter than before.
2. When looking at a distant AOI, the gaze dot moves most of the way on the first sample and settles by the next sample (target approximately 200 ms, not a multi-frame trailing average).
3. The amber live AOI candidate follows the visible filtered point.
4. After speech confirmation, the matching AOI can still become red and the Live target no longer diverges from the displayed point.

Do not tune constants during this deployment. Record the user's observations first; any parameter adjustment is a separate bounded follow-up using the same focused test modules and no additional architecture change.
