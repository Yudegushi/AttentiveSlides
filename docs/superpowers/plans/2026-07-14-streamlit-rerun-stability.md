# Streamlit Rerun Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unnecessary full-page and idle-fragment reruns while preserving browser-coordinate AOI geometry and active Live proposal latency.

**Architecture:** The viewport component becomes change-driven: it debounces layout events, compares a stable geometry signature, and increments revision only for a new value. The Main UI creates the 0.5-second Live fragment only while media is enabled and otherwise renders the interaction panel once.

**Tech Stack:** Plain JavaScript Streamlit component protocol, Python 3.10, Streamlit fragments, `unittest`.

## Global Constraints

- Keep browser viewport CSS coordinates and manual rectangle behavior.
- Keep active Live polling at 0.5 seconds.
- Do not change proxy, media, STT, gaze, LLM, or logging contracts.
- Add no dependency.
- Use TDD and commit the focused fix on `codex/ui-live-runtime-integration-v1`.

---

### Task 1: Make viewport geometry reports change-driven

**Files:**
- Modify: `modules/ui/slide_viewport_component/index.html`
- Modify: `tests/test_slide_viewport_component.py`

**Interfaces:**
- Consumes: existing `streamlit:render` arguments and browser viewport geometry.
- Produces: the unchanged component payload schema with revisions that advance only for distinct geometry.

- [ ] **Step 1: Write failing component contract tests**

Add tests requiring `lastReportedSignature`, a stable signature comparison before `setValue`, a trailing debounce timer, and revision increment only on a distinct report. Assert the parent scroll and resize listeners schedule the debounced report rather than an immediate animation-frame report.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_slide_viewport_component -v
```

Expected: the new assertions fail against the unconditional current reporter.

- [ ] **Step 3: Implement minimal signature deduplication and debounce**

In `index.html`, keep one `reportTimer` and `lastReportedSignature`. Build the payload without changing revision, serialize a rounded geometry-only signature, return without sending when it matches, otherwise increment revision, attach it to the payload, send, and store the signature. Debounce scroll/resize/observer callbacks by 180 ms; keep manual completion and initial load immediate.

- [ ] **Step 4: Run component and geometry regressions**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_slide_viewport_component tests.test_slide_geometry \
  tests.test_manual_targeting tests.test_live_single_port_launcher -v
```

Expected: all pass and `git diff --check` exits 0.

---

### Task 2: Stop polling an inactive Live runtime

**Files:**
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `tests/test_streamlit_attentive_slides.py`

**Interfaces:**
- Consumes: `main_live_master_enabled` and the existing `_render_live_periodic` / `_render_live_interaction` functions.
- Produces: active-media polling at 0.5 seconds and one-shot inactive rendering.

- [ ] **Step 1: Write a failing Main UI source test**

Require `_render_manual_interaction` to branch on `main_live_master_enabled`: enabled calls `_render_live_periodic`; disabled calls `_render_live_interaction` directly. Keep the capture iframe outside the fragment.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_streamlit_attentive_slides -v
```

Expected: the new inactive-polling assertion fails.

- [ ] **Step 3: Implement the one conditional**

Inside the existing Live branch of `_render_manual_interaction`, call `_render_live_periodic(...)` only when `main_live_master_enabled` is true; otherwise call `_render_live_interaction(view)`. Return after either path.

- [ ] **Step 4: Run affected UI/runtime regressions**

Run:

```bash
ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST=1 \
/root/miniconda3/bin/conda run -n attentive-app python -m unittest \
  tests.test_streamlit_attentive_slides tests.test_main_ui_widget_inventory \
  tests.test_compact_main_layout tests.test_slide_preview_canvas \
  tests.test_live_ui_bridge tests.test_main_ui_state -v
```

Expected: all pass and `git diff --check` exits 0.

---

### Task 3: Browser acceptance, record, commit, and push

**Files:**
- Modify: `docs/plans/UI-integration/handoffs/ui-live-runtime-integration-log.md`
- Modify: this plan's checkboxes.

**Interfaces:**
- Produces: verified rerun fix on the existing remote delivery branch.

- [ ] **Step 1: Run full focused validation**

Run compileall plus every test module from Tasks 1 and 2. Run `git diff --check`.

- [ ] **Step 2: Restart the launcher with the absolute cached Whisper model**

Use ports 18601/18602/18603 and `ATTENTIVE_WHISPER_MODEL=/root/.cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots/536b0662742c02347bc0e980a01041f333bce120`.

- [ ] **Step 3: Verify browser behavior**

Observe Manual and Live-media-off for at least five seconds without persistent full-page Running/fade. Enable media and verify ingress audio/video freshness, `Media: ready`, and active Live polling. Scroll and resize; require at most one settled geometry rerun per action, not a feedback loop.

- [ ] **Step 4: Record evidence, commit, and push**

Update the integration log, commit code/tests/docs with `fix: stabilize Streamlit reruns`, push the existing branch, and verify local and remote HEAD match with a clean worktree.
