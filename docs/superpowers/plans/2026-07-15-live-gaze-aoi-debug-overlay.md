# Live Gaze and AOI Debug Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not dispatch subagents.

**Goal:** Show an auxiliary live EyeTheia gaze point and browser AOI preview on the slide, then mark the most recent authoritative server-matched or manually confirmed AOI in red without adding automatic full-page Streamlit reruns.

**Architecture:** The existing capture page broadcasts gaze-only messages through one fixed same-origin `BroadcastChannel`; the slide viewport consumes them locally for a transient dot and amber preview. A zero-height component rendered by the existing 0.5-second live fragment publishes the authoritative AOI derived from existing proposal and confirmation state through the same channel, so the viewport can update red CSS without returning component values or rerunning the full app.

**Tech Stack:** Python 3.10, Streamlit 1.59.1 custom components, vanilla JavaScript, CSS, `BroadcastChannel`, `unittest`.

## Global Constraints

- Implement directly in `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration` on `LenovoLinux_Dorm`.
- Stay on the existing `codex/eyetheia-local-gaze-integration` branch; do not create another branch.
- Do not push or merge.
- Do not use subagents.
- Do not run an initial or baseline test suite.
- Do not perform RED or expected-failing test runs.
- Run exactly one focused GREEN group after each implementation checkpoint.
- Perform one whole-change self-review after both implementation checkpoints.
- Run the full unit suite once after the self-review and any bounded review fix.
- Do not run browser tests, browser smoke tests, lint, type checks, security scans, or performance suites.
- Reuse the existing `Show AOI overlay` control; do not add a second debug toggle.
- Use the fixed channel name `attentiveslides-gaze-debug-v1`; the user will not run multiple AttentiveSlides tabs.
- The gaze dot and amber AOI are auxiliary browser-only indicators. They must not affect gaze upload, dwell aggregation, proposal generation, confirmation, or tutoring.
- Default AOIs retain their existing green/teal style.
- Red means the most recent authoritative non-empty-STT server proposal AOI, overridden by a later manual confirmation or correction.
- Starting a new speech turn must not clear the previous red AOI.
- A failed turn, empty transcript, or turn without an AOI match must not clear the previous red AOI.
- A new successful proposal atomically replaces the previous red AOI.
- Reset and slide/deck changes clear the red AOI through the existing turn state lifecycle.
- Turning off `Show AOI overlay` hides green AOIs, gaze, amber preview, and red match without deleting proposal or confirmation state.
- Do not add a dedicated debug-match session-state key. Resolve display state from `main_live_proposal` and `main_confirmed_interaction`.
- Do not broadcast transcript, audio, landmarks, images, API data, or raw confirmation payloads.
- Do not add an automatic `st.rerun(scope="app")`; the existing user-triggered overlay rerun remains unchanged.

---

## File Responsibility Map

| File | Responsibility after this work |
|---|---|
| `modules/media/live_capture_component/index.html` | Broadcast current valid EyeTheia point gaze and explicit auxiliary-clear messages. |
| `modules/ui/slide_viewport_component/index.html` | Render the transient gaze point, local amber preview, and authoritative red AOI with red-over-amber precedence. |
| `modules/system/live_debug_overlay.py` | Resolve the authoritative AOI id from existing proposal and confirmed interaction state. |
| `modules/ui/live_debug_bridge_component/index.html` | Publish server match/clear messages from the live fragment without setting a component value. |
| `modules/ui/live_debug_bridge_component/__init__.py` | Dependency-free Streamlit wrapper for the zero-height bridge. |
| `apps/streamlit_attentive_slides.py` | Resolve the current authoritative AOI after live controls render and invoke the bridge inside the existing fragment. |
| `tests/test_live_gaze_debug_components.py` | Static contracts for fixed channel messages, stale cleanup, visual precedence, and no gaze-driven component values. |
| `tests/test_live_debug_overlay.py` | Unit contracts for proposal/confirmation resolution and bridge source behavior. |
| `tests/test_streamlit_attentive_slides.py` | Static wiring contract proving the bridge remains inside the fragment and after live interaction handling. |

---

### Task 1: Add Browser-Only Gaze and Amber AOI Preview

**Files:**
- Modify: `modules/media/live_capture_component/index.html`
- Modify: `modules/ui/slide_viewport_component/index.html`
- Create: `tests/test_live_gaze_debug_components.py`

**Interfaces:**
- Produces capture messages on `attentiveslides-gaze-debug-v1`:

```javascript
{
  version: 1,
  kind: "gaze",
  sequence: Number,
  browser_timestamp_ms: Number,
  x_css: Number,
  y_css: Number,
  viewport_width: Number,
  viewport_height: Number,
  valid: true,
  face_detected: true,
  source: "eyetheia_local"
}
```

- Produces an auxiliary reset message:

```javascript
{ version: 1, kind: "gaze_clear" }
```

- Consumes those messages only inside the slide viewport. No message calls `streamlit:setComponentValue`.

- [ ] **Step 1: Add GREEN-only component source contracts without running them separately**

Create `tests/test_live_gaze_debug_components.py` with these exact contracts:

```python
from __future__ import annotations

import unittest
from pathlib import Path


CAPTURE_PATH = Path("modules/media/live_capture_component/index.html")
VIEWPORT_PATH = Path("modules/ui/slide_viewport_component/index.html")


class LiveGazeDebugComponentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = CAPTURE_PATH.read_text(encoding="utf-8")
        cls.viewport = VIEWPORT_PATH.read_text(encoding="utf-8")

    def test_capture_broadcasts_only_gaze_debug_contract(self) -> None:
        self.assertIn('"attentiveslides-gaze-debug-v1"', self.capture)
        self.assertIn('kind: "gaze"', self.capture)
        self.assertIn('kind: "gaze_clear"', self.capture)
        self.assertIn('source: "eyetheia_local"', self.capture)
        self.assertNotIn("landmarks: latestLandmarks", self.capture)

    def test_viewport_has_transient_gaze_and_aoi_states(self) -> None:
        self.assertIn('"attentiveslides-gaze-debug-v1"', self.viewport)
        self.assertIn('className = "gaze-dot"', self.viewport)
        self.assertIn("aoi-live-candidate", self.viewport)
        self.assertIn("aoi-server-match", self.viewport)
        self.assertIn("GAZE_STALE_AFTER_MS = 1000", self.viewport)

    def test_server_match_style_has_priority_over_live_candidate(self) -> None:
        self.assertIn("serverMatchedAoiId === aoiId", self.viewport)
        self.assertIn("else if (liveCandidateAoiId === aoiId)", self.viewport)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Broadcast the existing valid EyeTheia point without changing upload behavior**

Near the capture component constants, add:

```javascript
const DEBUG_CHANNEL_NAME = "attentiveslides-gaze-debug-v1";
const debugChannel = typeof BroadcastChannel === "function"
  ? new BroadcastChannel(DEBUG_CHANNEL_NAME)
  : null;

function publishDebug(message) {
  if (!debugChannel) return;
  debugChannel.postMessage({ version: 1, ...message });
}

function clearDebugGaze() {
  publishDebug({ kind: "gaze_clear" });
}
```

Immediately after assigning the existing `latestGaze` object in `handleEyeTheiaMessage`, publish a copy containing only its public fields:

```javascript
publishDebug({ kind: "gaze", ...latestGaze });
```

Call `clearDebugGaze()` from `handleLocalGazeFailure()` and `stopLocalGaze()`. In the existing `pagehide` listener, publish one final clear message and close the channel:

```javascript
clearDebugGaze();
if (debugChannel) debugChannel.close();
```

Do not change `latestGaze`, `scheduleGazeUpload()`, HTTP timing, EyeTheia frame timing, or the uploaded payload.

- [ ] **Step 3: Add the viewport visual layer and fixed channel state**

Add these styles after the existing `.aoi` rule:

```css
.aoi-live-candidate {
  border-color: rgba(217, 119, 6, .95);
  background: rgba(251, 191, 36, .14);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, .20), 0 0 18px rgba(245, 158, 11, .32);
}
.aoi-server-match {
  border-color: rgba(220, 38, 38, 1);
  border-width: 3px;
  background: rgba(239, 68, 68, .12);
  box-shadow: 0 0 0 4px rgba(239, 68, 68, .22), 0 0 24px rgba(220, 38, 38, .48);
}
.gaze-dot {
  position: absolute;
  width: 12px;
  height: 12px;
  margin: -6px 0 0 -6px;
  border: 2px solid #ffffff;
  border-radius: 999px;
  background: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, .30), 0 2px 8px rgba(15, 23, 42, .42);
  display: none;
  z-index: 20;
}
```

Add component state beside the existing viewport state:

```javascript
const DEBUG_CHANNEL_NAME = "attentiveslides-gaze-debug-v1";
const GAZE_STALE_AFTER_MS = 1000;
const debugChannel = typeof BroadcastChannel === "function"
  ? new BroadcastChannel(DEBUG_CHANNEL_NAME)
  : null;
let gazeDot = null;
let gazeStaleTimer = null;
let liveCandidateAoiId = null;
let serverMatchedAoiId = null;
let aoiElements = new Map();
```

- [ ] **Step 4: Implement local gaze validation, coordinate conversion, preview selection, and visual precedence**

Add these functions inside the viewport component closure:

```javascript
function clearAuxiliaryGaze() {
  window.clearTimeout(gazeStaleTimer);
  gazeStaleTimer = null;
  liveCandidateAoiId = null;
  if (gazeDot) gazeDot.style.display = "none";
  refreshDebugClasses();
}

function refreshDebugClasses() {
  for (const [aoiId, element] of aoiElements.entries()) {
    element.classList.remove("aoi-live-candidate", "aoi-server-match");
    if (serverMatchedAoiId === aoiId) {
      element.classList.add("aoi-server-match");
    } else if (liveCandidateAoiId === aoiId) {
      element.classList.add("aoi-live-candidate");
    }
  }
}

function finiteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function eligibleAoi(aoi) {
  const excluded = new Set(["whole_slide", "footer", "page_number", "decoration", "background"]);
  const type = String(aoi && aoi.type || "").trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
  return Boolean(aoi && aoi.aoi_id && Array.isArray(aoi.bbox) && aoi.bbox.length === 4)
    && !excluded.has(type)
    && String(aoi.aoi_id) !== "whole_slide";
}

function previewCandidate(normalizedX, normalizedY) {
  const candidates = (args.aois || []).filter(eligibleAoi).filter((aoi) => {
    const [x1, y1, x2, y2] = aoi.bbox.map(Number);
    return x1 <= normalizedX && normalizedX <= x2 && y1 <= normalizedY && normalizedY <= y2;
  });
  candidates.sort((left, right) => {
    const leftCenter = Math.hypot(normalizedX - (Number(left.bbox[0]) + Number(left.bbox[2])) / 2,
      normalizedY - (Number(left.bbox[1]) + Number(left.bbox[3])) / 2);
    const rightCenter = Math.hypot(normalizedX - (Number(right.bbox[0]) + Number(right.bbox[2])) / 2,
      normalizedY - (Number(right.bbox[1]) + Number(right.bbox[3])) / 2);
    return leftCenter - rightCenter || String(left.aoi_id).localeCompare(String(right.aoi_id));
  });
  return candidates.length ? String(candidates[0].aoi_id) : null;
}

function handleGazeMessage(message) {
  if (!args || !args.show_aoi_overlay || !image || !image.complete) return clearAuxiliaryGaze();
  if (!message.valid || !message.face_detected || message.source !== "eyetheia_local") return clearAuxiliaryGaze();
  const x = finiteNumber(message.x_css);
  const y = finiteNumber(message.y_css);
  const width = finiteNumber(message.viewport_width);
  const height = finiteNumber(message.viewport_height);
  if (x === null || y === null || width === null || height === null) return clearAuxiliaryGaze();
  const context = coordinateContext();
  if (!context || Math.abs(width - context.viewportWidth) > 1 || Math.abs(height - context.viewportHeight) > 1) {
    return clearAuxiliaryGaze();
  }
  const localRect = image.getBoundingClientRect();
  const slideRect = viewportRect(localRect, context.frameRect);
  if (x < slideRect.x1 || x > slideRect.x2 || y < slideRect.y1 || y > slideRect.y2) return clearAuxiliaryGaze();
  const normalizedX = (x - slideRect.x1) / (slideRect.x2 - slideRect.x1);
  const normalizedY = (y - slideRect.y1) / (slideRect.y2 - slideRect.y1);
  gazeDot.style.left = `${normalizedX * 100}%`;
  gazeDot.style.top = `${normalizedY * 100}%`;
  gazeDot.style.display = "block";
  liveCandidateAoiId = previewCandidate(normalizedX, normalizedY);
  refreshDebugClasses();
  window.clearTimeout(gazeStaleTimer);
  gazeStaleTimer = window.setTimeout(clearAuxiliaryGaze, GAZE_STALE_AFTER_MS);
}
```

Register the channel listener once:

```javascript
if (debugChannel) {
  debugChannel.addEventListener("message", (event) => {
    const message = event.data || {};
    if (message.version !== 1) return;
    if (message.kind === "gaze") handleGazeMessage(message);
    if (message.kind === "gaze_clear") clearAuxiliaryGaze();
  });
}
window.addEventListener("pagehide", () => {
  clearAuxiliaryGaze();
  if (debugChannel) debugChannel.close();
});
```

During `render(nextArgs)`, clear debug state when deck or slide identity changes, rebuild `aoiElements`, append one `gazeDot` inside `overlay`, and call `refreshDebugClasses()` after AOI elements exist:

```javascript
const sameDebugSlide = Boolean(args)
  && String(args.deck_id) === String(nextArgs.deck_id)
  && Number(args.slide_id) === Number(nextArgs.slide_id);
if (!sameDebugSlide) {
  serverMatchedAoiId = null;
  clearAuxiliaryGaze();
}
```

```javascript
aoiElements = new Map();
// For each created AOI box:
aoiElements.set(String(aoi.aoi_id || ""), box);
```

```javascript
gazeDot = document.createElement("div");
gazeDot.className = "gaze-dot";
overlay.appendChild(gazeDot);
refreshDebugClasses();
```

Keep the existing manual rectangle above or alongside this layer and preserve all existing geometry uploads and manual-selection component values.

- [ ] **Step 5: Run the Task 1 focused GREEN group once**

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
/home/charles/miniconda3/bin/conda run -n pyboe \
  python -m unittest tests.test_live_gaze_debug_components -v
```

Expected: all tests in the module pass. Do not run browser tests.

- [ ] **Step 6: Commit Task 1**

```bash
git add modules/media/live_capture_component/index.html \
  modules/ui/slide_viewport_component/index.html \
  tests/test_live_gaze_debug_components.py
git commit -m "feat: show live gaze debug overlay"
```

---

### Task 2: Broadcast the Authoritative Server AOI Without an App Rerun

**Files:**
- Create: `modules/system/live_debug_overlay.py`
- Create: `modules/ui/live_debug_bridge_component/__init__.py`
- Create: `modules/ui/live_debug_bridge_component/index.html`
- Modify: `modules/ui/slide_viewport_component/index.html`
- Modify: `apps/streamlit_attentive_slides.py`
- Create: `tests/test_live_debug_overlay.py`
- Modify: `tests/test_streamlit_attentive_slides.py`

**Interfaces:**
- Produces:

```python
def resolve_live_debug_aoi_id(
    *,
    deck_id: str,
    slide_id: int,
    valid_aoi_ids: Collection[str],
    proposal: LiveInteractionProposal | None,
    confirmed_interaction: Mapping[str, object] | None,
) -> str | None:
    ...
```

- Produces bridge messages:

```javascript
{
  version: 1,
  kind: "server_match",
  deck_id: String,
  slide_id: Number,
  aoi_id: String | null
}
```

- [ ] **Step 1: Add GREEN-only resolver tests without running them separately**

Create `tests/test_live_debug_overlay.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path

from modules.system.live_debug_overlay import resolve_live_debug_aoi_id
from modules.system.live_ui_bridge import LiveInteractionProposal


def proposal(**overrides) -> LiveInteractionProposal:
    values = {
        "interaction_id": "turn-1",
        "deck_id": "deck-1",
        "slide_id": 2,
        "layout_revision": 7,
        "transcript": "explain this",
        "gaze_grid": "middle_center",
        "gaze_confidence": 0.9,
        "stable_duration_sec": 0.8,
        "predicted_aoi_id": "aoi-1",
        "target_confidence": 0.86,
        "original_speech_transcript": "explain this",
        "gaze_source": "eyetheia_local",
    }
    values.update(overrides)
    return LiveInteractionProposal(**values)


class LiveDebugOverlayTest(unittest.TestCase):
    def test_valid_completed_proposal_is_displayed(self) -> None:
        self.assertEqual(
            resolve_live_debug_aoi_id(
                deck_id="deck-1",
                slide_id=2,
                valid_aoi_ids={"aoi-1", "aoi-2"},
                proposal=proposal(),
                confirmed_interaction=None,
            ),
            "aoi-1",
        )

    def test_empty_failed_or_other_slide_proposal_does_not_replace_display(self) -> None:
        for item in (
            proposal(transcript=""),
            proposal(predicted_aoi_id=None),
            proposal(slide_id=3),
        ):
            self.assertIsNone(
                resolve_live_debug_aoi_id(
                    deck_id="deck-1",
                    slide_id=2,
                    valid_aoi_ids={"aoi-1"},
                    proposal=item,
                    confirmed_interaction=None,
                )
            )

    def test_current_manual_confirmation_overrides_proposal(self) -> None:
        confirmed = {
            "interaction": {"deck_id": "deck-1", "slide_id": 2},
            "selected_target": {"aoi_id": "aoi-2"},
        }
        self.assertEqual(
            resolve_live_debug_aoi_id(
                deck_id="deck-1",
                slide_id=2,
                valid_aoi_ids={"aoi-1", "aoi-2"},
                proposal=proposal(),
                confirmed_interaction=confirmed,
            ),
            "aoi-2",
        )

    def test_bridge_never_sets_a_streamlit_component_value(self) -> None:
        source = Path("modules/ui/live_debug_bridge_component/index.html").read_text(encoding="utf-8")
        self.assertIn('kind: "server_match"', source)
        self.assertIn('"attentiveslides-gaze-debug-v1"', source)
        self.assertNotIn("streamlit:setComponentValue", source)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement the pure resolver without adding session state**

Create `modules/system/live_debug_overlay.py`:

```python
"""Resolve the current authoritative AOI used only by the debug overlay."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from modules.system.live_ui_bridge import LiveInteractionProposal


def resolve_live_debug_aoi_id(
    *,
    deck_id: str,
    slide_id: int,
    valid_aoi_ids: Collection[str],
    proposal: LiveInteractionProposal | None,
    confirmed_interaction: Mapping[str, object] | None,
) -> str | None:
    valid = {str(aoi_id) for aoi_id in valid_aoi_ids}
    confirmed = confirmed_interaction or {}
    interaction = confirmed.get("interaction")
    target = confirmed.get("selected_target")
    if isinstance(interaction, Mapping) and isinstance(target, Mapping):
        confirmed_id = str(target.get("aoi_id") or "")
        try:
            confirmed_slide_id = int(interaction.get("slide_id", -1))
        except (TypeError, ValueError):
            confirmed_slide_id = -1
        if (
            str(interaction.get("deck_id") or "") == deck_id
            and confirmed_slide_id == slide_id
            and confirmed_id in valid
        ):
            return confirmed_id

    if (
        isinstance(proposal, LiveInteractionProposal)
        and proposal.deck_id == deck_id
        and proposal.slide_id == slide_id
        and proposal.transcript.strip()
        and proposal.predicted_aoi_id in valid
    ):
        return proposal.predicted_aoi_id
    return None
```

Do not add a `main_live_debug_*` session-state key. Existing `reset_main_live_turn_state()` already clears the proposal and confirmed interaction; slide/deck binding already invokes the turn reset lifecycle.

- [ ] **Step 3: Create the zero-height bridge wrapper and component**

Create `modules/ui/live_debug_bridge_component/__init__.py`:

```python
"""Publish authoritative debug overlay state without returning component values."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_COMPONENT: Any = None


def render_live_debug_bridge(
    *,
    deck_id: str,
    slide_id: int,
    matched_aoi_id: str | None,
    enabled: bool,
    key: str,
) -> None:
    if os.environ.get("ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST") == "1":
        return
    _component()(
        deck_id=str(deck_id),
        slide_id=int(slide_id),
        matched_aoi_id=(str(matched_aoi_id) if matched_aoi_id else None),
        enabled=bool(enabled),
        default=None,
        key=key,
    )


def _component() -> Any:
    global _COMPONENT
    if _COMPONENT is None:
        _COMPONENT = components.declare_component(
            "attentive_live_debug_bridge",
            path=str(Path(__file__).parent),
        )
    return _COMPONENT
```

Create `modules/ui/live_debug_bridge_component/index.html`:

```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body>
<script>
(() => {
  const CHANNEL_NAME = "attentiveslides-gaze-debug-v1";
  const channel = typeof BroadcastChannel === "function"
    ? new BroadcastChannel(CHANNEL_NAME)
    : null;
  window.parent.postMessage({
    isStreamlitMessage: true,
    type: "streamlit:componentReady",
    apiVersion: 1,
  }, "*");
  window.parent.postMessage({
    isStreamlitMessage: true,
    type: "streamlit:setFrameHeight",
    height: 0,
  }, "*");
  window.addEventListener("message", (event) => {
    if (!channel || !event.data || event.data.type !== "streamlit:render") return;
    const args = event.data.args || {};
    channel.postMessage({
      version: 1,
      kind: "server_match",
      deck_id: String(args.deck_id || ""),
      slide_id: Number(args.slide_id),
      aoi_id: args.enabled && args.matched_aoi_id
        ? String(args.matched_aoi_id)
        : null,
    });
  });
  window.addEventListener("pagehide", () => {
    if (channel) channel.close();
  });
})();
</script>
</body>
</html>
```

- [ ] **Step 4: Consume authoritative match messages in the viewport**

Extend the existing debug-channel handler from Task 1:

```javascript
function handleServerMatch(message) {
  if (!args) return;
  if (
    String(message.deck_id) !== String(args.deck_id)
    || Number(message.slide_id) !== Number(args.slide_id)
  ) return;
  const requested = message.aoi_id ? String(message.aoi_id) : null;
  serverMatchedAoiId = requested && aoiElements.has(requested) ? requested : null;
  refreshDebugClasses();
}
```

```javascript
if (message.kind === "server_match") handleServerMatch(message);
```

The bridge repeats current state on every fragment render. Do not deduplicate bridge messages; this lets a newly mounted viewport recover the latest red state.

- [ ] **Step 5: Wire the resolver and bridge after live interaction rendering**

Import:

```python
from modules.system.live_debug_overlay import resolve_live_debug_aoi_id
from modules.ui.live_debug_bridge_component import render_live_debug_bridge
```

At the end of `_render_live_periodic`, immediately after `_render_live_interaction(view)`, resolve existing state and render the bridge:

```python
    valid_aoi_ids = {
        aoi.aoi_id
        for aoi in view.active_slide.aois
        if aoi.aoi_id != "whole_slide"
    }
    matched_aoi_id = resolve_live_debug_aoi_id(
        deck_id=view.deck_id,
        slide_id=view.active_slide_id,
        valid_aoi_ids=valid_aoi_ids,
        proposal=(
            st.session_state.get("main_live_proposal")
            if isinstance(
                st.session_state.get("main_live_proposal"),
                LiveInteractionProposal,
            )
            else None
        ),
        confirmed_interaction=(
            st.session_state.get("main_confirmed_interaction")
            if isinstance(
                st.session_state.get("main_confirmed_interaction"),
                dict,
            )
            else None
        ),
    )
    render_live_debug_bridge(
        deck_id=view.deck_id,
        slide_id=view.active_slide_id,
        matched_aoi_id=matched_aoi_id,
        enabled=bool(st.session_state["main_show_aoi_overlay"]),
        key=(
            "main_live_debug_bridge_"
            f"{view.deck_id}_{view.active_slide_id}"
        ),
    )
```

Do not set `main_live_full_rerun_requested` from proposal consumption, confirmation, or bridge rendering. Do not change the existing overlay-toggle callback.

- [ ] **Step 6: Add the Main UI static wiring contract**

Add to `TestStreamlitAttentiveSlides`:

```python
def test_live_debug_bridge_uses_existing_state_inside_fragment(
    self,
) -> None:
    periodic = self.function_source("_render_live_periodic")
    self.assertIn("resolve_live_debug_aoi_id", periodic)
    self.assertIn("render_live_debug_bridge", periodic)
    self.assertIn('main_live_proposal', periodic)
    self.assertIn('main_confirmed_interaction', periodic)
    self.assertLess(
        periodic.index("_render_live_interaction"),
        periodic.index("render_live_debug_bridge"),
    )
    self.assertNotIn("main_live_debug_match", self.source)
```

- [ ] **Step 7: Run the Task 2 focused GREEN group once**

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
/home/charles/miniconda3/bin/conda run -n pyboe python -m unittest \
  tests.test_live_debug_overlay \
  tests.test_streamlit_attentive_slides -v
```

Expected: all tests in both modules pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add modules/system/live_debug_overlay.py \
  modules/ui/live_debug_bridge_component/__init__.py \
  modules/ui/live_debug_bridge_component/index.html \
  modules/ui/slide_viewport_component/index.html \
  apps/streamlit_attentive_slides.py \
  tests/test_live_debug_overlay.py \
  tests/test_streamlit_attentive_slides.py
git commit -m "feat: publish authoritative AOI debug matches"
```

---

### Task 3: Final Review, Bounded Verification, and Local Restart

**Files:** No planned repository changes. If the review finds a Critical or Important issue, make one bounded fix wave only in the directly affected files.

**Interfaces:**
- Consumes: both implementation commits.
- Produces: one reviewed local deployment ready for user browser acceptance.

- [ ] **Step 1: Perform one whole-change self-review**

Inspect exactly:

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
git diff 10adfc5..HEAD -- \
  modules/media/live_capture_component/index.html \
  modules/ui/slide_viewport_component/index.html \
  modules/system/live_debug_overlay.py \
  modules/ui/live_debug_bridge_component \
  apps/streamlit_attentive_slides.py \
  tests/test_live_gaze_debug_components.py \
  tests/test_live_debug_overlay.py \
  tests/test_streamlit_attentive_slides.py
git diff --check 10adfc5..HEAD
```

Review for these exact risks:

- gaze upload and EyeTheia frame pumps are unchanged;
- no image, landmark, transcript, or audio enters the debug channel;
- server red has CSS precedence over amber;
- stale gaze clears only auxiliary state;
- failed/new speech does not clear the previous server match;
- reset and slide identity changes clear through existing proposal/confirmation state;
- the bridge never sets a component value and adds no automatic app rerun;
- manual rectangle component values and geometry uploads remain unchanged.

If a Critical or Important issue exists, fix it once and run only the directly affected Task 1 or Task 2 focused group before continuing.

- [ ] **Step 2: Run the full unit suite once**

```bash
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
ATTENTIVE_RUNTIME_DATA_DIR=/home/charles/.local/share/attentiveslides/project_data/runtime/attentive_slides \
  /home/charles/miniconda3/bin/conda run -n pyboe \
  python -m unittest discover -s tests -v
```

Record the exact pass/fail count. The known unrelated `test_required_static_keys_exist` failure for removed `main_thumbnail_window_previous/next` may remain; do not restore those UI keys and do not rerun the full suite solely for that assertion.

- [ ] **Step 3: Restart only the Lenovo local app service**

```bash
systemctl --user restart attentiveslides-local.service
systemctl --user is-active attentiveslides-local.service
curl --fail --silent http://127.0.0.1:8501/_stcore/health
curl --fail --silent http://127.0.0.1:8001/api/health
```

Require both services healthy. Do not restart or retrain EyeTheia.

- [ ] **Step 4: Hand off for manual acceptance without browser automation**

Ask the user to open `http://127.0.0.1:8501`, keep `Show AOI overlay` enabled, and manually verify:

1. a blue/white gaze dot follows current gaze only while it is over the visible slide;
2. the exact browser preview AOI becomes amber and fades after one second without gaze;
3. default AOIs remain green;
4. a completed non-empty speech turn with server AOI match makes that AOI red;
5. starting or failing another speech turn leaves the previous red AOI in place;
6. the next successful match replaces red atomically;
7. manual correction moves red to the confirmed AOI;
8. Reset or slide change clears red;
9. disabling `Show AOI overlay` hides every debug visual;
10. the page does not visibly refresh from gaze or red-match updates.

Do not run automated browser tests. Do not push or merge after acceptance.
