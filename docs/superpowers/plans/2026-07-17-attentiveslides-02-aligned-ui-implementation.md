# AttentiveSlides 02-Aligned UI Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan checkpoint by checkpoint. Work directly in the existing 4060 branch. Do not dispatch implementation subagents unless the user explicitly asks for them in the execution turn.

**Goal:** Refine the implemented AttentiveSlides Study and Review UI toward the approved 02 / Cool Instrument Panel reference, restore a clear product shell and compact instrument hierarchy, and add a complete Pause/Resume lifecycle without changing gaze/AOI mathematics, voice semantics, Tutor grounding, or learner-state models.

**Architecture:** Keep Streamlit as the page composition layer and retain the existing local custom components. Make the Study Review store the single source of lifecycle timing truth, use the existing live ingress master gate to stop media/voice during Pause, and reshape the current CSS/keyed-container composition into a strict left rail + slide/output + Control + right rail shell. Add only small presentation helpers and backward-compatible Review fields.

**Tech Stack:** Python 3.10, Streamlit 1.59.1, local Streamlit custom components, HTML/CSS/JavaScript, existing aiohttp media/voice service, unittest, self-hosted Literata and IBM Plex Sans fonts.

**Approved design:** `docs/superpowers/specs/2026-07-17-attentiveslides-02-aligned-ui-design.md`

## Global Constraints

- Work on host `LenovoLinux_Dorm` in `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration`.
- Continue on existing branch `codex/gaze-heatmap-review`; do not create a branch or worktree.
- At authoring, the implementation baseline is commit `2e43986` plus the documentation commit containing this plan. Record the actual starting commit in the ledger; do not reset to an older hash.
- Preserve any user changes. If the worktree is dirty and an overlapping file is modified, stop and report it instead of overwriting it.
- Do not push, merge, rebase, or replace `main` under this plan.
- Light mode and desktop only. Optimize for physical `2560x1600` at approximately 160% X11 scaling.
- English learner-facing copy.
- No glassmorphism, gradients, backdrop blur, large decorative shadows, animation library, UI framework, icon dependency, or remote runtime asset.
- Do not change gaze aggregation, AOI confidence thresholds/meaning, VAD thresholds, voice provider behavior, Tutor grounding, model inference, privacy policy, or raw biometric retention.
- Do not perform an architecture rewrite or add new analytics.
- Keep all four palettes and local preference persistence; Ivory Study Desk remains the default.
- No initial/baseline suite and no expected-failing RED run.
- After each checkpoint, run exactly its named focused GREEN group. If it fails, fix and rerun only the smallest affected module/group.
- Do not add browser automation, screenshot-diff tests, lint, type, security, performance, or extra acceptance suites.
- Perform one whole-change review after all checkpoints. The current authorization covers one review subagent for the documentation phase, not an automatic implementation subagent; use a review subagent later only if the user explicitly asks again.
- Run the complete unittest suite once after implementation, review, and any bounded final fixes. Do not repeat a passing full suite for commits or handoff.
- Keep the implementation ledger concise: checkpoint, focused result, commit, blocker, next step.

## Start Protocol — Inspect, Do Not Baseline-Test

Connect and confirm context:

```bash
ssh LenovoLinux_Dorm
cd /home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration
git branch --show-current
git status --short
git log -1 --oneline
```

Expected branch: `codex/gaze-heatmap-review`. Expected status: clean before implementation. Do **not** run tests here.

Read these files before editing:

```text
docs/superpowers/specs/2026-07-17-attentiveslides-02-aligned-ui-design.md
docs/superpowers/specs/references/02-cool-instrument-panel.html
docs/superpowers/specs/references/attentiveslides-concepts.css
docs/superpowers/specs/assets/attentiveslides-02-reference.png
docs/superpowers/specs/assets/attentiveslides-4060-before.png
apps/streamlit_attentive_slides.py
modules/ui/workspace.css
modules/ui/design_tokens.py
modules/ui/voice_panel.py
modules/ui/voice_control_component/index.html
modules/ui/slide_viewport_component/index.html
modules/review/contracts.py
modules/review/study_review_store.py
modules/media/single_port_transport.py
modules/media/live_ingress_service.py
modules/system/controller.py
modules/system/voice_orchestrator.py
```

The reference can be rendered locally on the 4060 with:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m http.server 8765 \
  --directory docs/superpowers/specs/references
```

Open `http://127.0.0.1:8765/02-cool-instrument-panel.html`. Do not copy its placeholder lesson content or fake data into production; copy its visual hierarchy and proportions.

## Execution Ledger

**Implementation start:** `06c4aac` on `codex/gaze-heatmap-review`.

Update this table in the plan while executing. One row per checkpoint is enough. Before each checkpoint commit, update only that row and include this plan file in the same commit; do not create ledger-only commits or rerun tests for the Markdown change.

| Checkpoint | Status | Focused GREEN result | Commit | Blocker / next |
|---|---|---|---|---|
| 1. Typography and 02 tokens | completed | 15 passed in 0.003s; both font families resolved | this checkpoint commit | Checkpoint 2 |
| 2. Shell, top bar, rails, slide stage | completed | 38 passed in 0.041s | this checkpoint commit | Checkpoint 3 |
| 3. Control and Tutor output | pending | — | — | — |
| 4. Pause persistence and timing | pending | — | — | — |
| 5. Pause runtime integration | pending | — | — | — |
| 6. Review visual alignment | pending | — | — | — |
| 7. Whole-change review and final verification | pending | — | — | — |

## Planned File Map

### New production/support files

- `assets/fonts/literata/Literata-Variable.ttf`
- `assets/fonts/literata/OFL.txt`
- `assets/fonts/ibm-plex-sans/IBMPlexSans-Regular.woff2`
- `assets/fonts/ibm-plex-sans/IBMPlexSans-SemiBold.woff2`
- `assets/fonts/ibm-plex-sans/IBMPlexSans-Bold.woff2`
- `assets/fonts/ibm-plex-sans/OFL.txt`
- `assets/fonts/README.md`
- `scripts/install_attentiveslides_demo_fonts.sh`

### New tests

- `tests/test_font_assets.py`
- `tests/test_main_ui_pause_layout.py`

### Main modified files

- `apps/streamlit_attentive_slides.py`
- `modules/system/main_ui_state.py`
- `modules/ui/design_tokens.py`
- `modules/ui/workspace.css`
- `modules/ui/voice_panel.py`
- `modules/ui/voice_control_component/__init__.py`
- `modules/ui/voice_control_component/index.html`
- `modules/ui/palette_control_component/index.html` only if font/geometry tokens must enter its iframe
- `modules/ui/slide_viewport_component/index.html` only for stage/gaze visual alignment; do not change coordinates
- `modules/review/contracts.py`
- `modules/review/study_review_store.py`
- `modules/ui/review_view.py`
- `modules/media/single_port_transport.py`
- `modules/media/live_ingress_service.py`
- `modules/system/voice_orchestrator.py`

### Existing tests expected to change

- `tests/test_ui_design_tokens.py`
- `tests/test_main_ui_state.py`
- `tests/test_main_ui_workspace_layout.py`
- `tests/test_main_ui_widget_inventory.py`
- `tests/test_main_ui_voice_layout.py`
- `tests/test_voice_control_component.py`
- `tests/test_slide_preview_canvas.py`
- `tests/test_study_review_store.py`
- `tests/test_review_view.py`
- `tests/test_main_ui_review_layout.py`
- `tests/test_single_port_transport.py`
- `tests/test_live_ingress_service.py`
- `tests/test_voice_orchestrator.py`

Do not create new modules merely to avoid editing the composition functions above.

---

## Checkpoint 1: Typography, Font Assets, and 02-Aligned Tokens

**Purpose:** Establish the exact type families, compact scale, square geometry, and offline installation path before rearranging layout.

**Files:**

- Add the font assets, licenses, provenance README, and install script named in the file map.
- Modify `modules/ui/workspace.css`.
- Modify `modules/ui/design_tokens.py` only if a shared non-palette typography/geometry constant is genuinely needed.
- Modify iframe component CSS to use the same font-family fallbacks; do not duplicate palette values.
- Add `tests/test_font_assets.py`.
- Modify `tests/test_ui_design_tokens.py`.

### Implementation

1. Vendor the pinned roman files from the official projects and keep their OFL license text:

   - Literata official project: `https://github.com/googlefonts/literata`, pinned release/version 3.103.
   - IBM Plex official project: `https://github.com/IBM/plex`, pinned official `@ibm/plex-sans` release 1.1.0.

   Use these acquisition commands in a temporary directory:

```bash
font_tmp="$(mktemp -d)"
git clone --depth 1 --branch 3.103 \
  https://github.com/googlefonts/literata.git "$font_tmp/literata"
npm pack @ibm/plex-sans@1.1.0 --pack-destination "$font_tmp"
tar -xzf "$font_tmp/ibm-plex-sans-1.1.0.tgz" -C "$font_tmp"
```

   From Literata 3.103, copy `fonts/variable/Literata[opsz,wght].ttf` to `Literata-Variable.ttf`. The pinned `@ibm/plex-sans@1.1.0` package contains WOFF/WOFF2 but no TTF files, so copy `fonts/complete/woff2/IBMPlexSans-{Regular,SemiBold,Bold}.woff2` and `LICENSE.txt` to the stable paths in the file map without conversion. If the tag, package, or these exact files are unavailable, stop and report it; do not silently select a later release or unofficial mirror.

   In `assets/fonts/README.md`, record the official URL, exact tag/package, original filename, committed filename, SHA-256, license, and acquisition date. Generate the hashes after copying with `sha256sum assets/fonts/literata/*.ttf assets/fonts/ibm-plex-sans/*.woff2`; `tests/test_font_assets.py` recomputes the committed hashes and requires an exact README match.

2. Implement `scripts/install_attentiveslides_demo_fonts.sh` without root:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
font_root="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/attentiveslides"
install -d "$font_root"
install -m 0644 "$repo_root/assets/fonts/literata/Literata-Variable.ttf" "$font_root/"
install -m 0644 "$repo_root/assets/fonts/ibm-plex-sans/IBMPlexSans-Regular.woff2" "$font_root/"
install -m 0644 "$repo_root/assets/fonts/ibm-plex-sans/IBMPlexSans-SemiBold.woff2" "$font_root/"
install -m 0644 "$repo_root/assets/fonts/ibm-plex-sans/IBMPlexSans-Bold.woff2" "$font_root/"
fc-cache -f "$font_root"
```

3. Change the CSS root variables to:

```css
:root {
  --as-font-heading: "Literata", "Noto Serif", "DejaVu Serif", serif;
  --as-font-ui: "IBM Plex Sans", "Noto Sans", "DejaVu Sans", sans-serif;
  --as-radius-control: 3px;
  --as-radius-panel: 2px;
  --as-radius-shell: 0px;
  --as-left-rail-width: 226px;
  --as-right-rail-width: 190px;
  --as-control-width: 292px;
  --as-topbar-height: 52px;
}
```

4. Apply the design-spec scale rather than broad `h1/h2` overrides. Use explicit keyed-container/classes for identity, panel titles, labels, captions, controls, and Tutor body. Normal body/control text is 12 px; operational labels 10 px; main panel titles 16 px; Tutor body 15/22.

5. Remove the current 6/8/12 px card geometry and large generic padding. Preserve only the restrained slide shadow. Do not alter the 16 semantic palette values or the default palette.

6. Update each local component iframe to use the same family strings. Because the fonts are installed on the demo host, no `@import`, remote URL, base64 duplication, or parent-document CSS inheritance is required.

### Focused test contract

`tests/test_font_assets.py` must verify:

- all four stable font files and both OFL files exist and are non-empty;
- README provenance names the official projects and SHA-256 strings;
- install script copies only repository font assets into a user font directory and calls `fc-cache`;
- no CSS/HTML file contains a Google Fonts/CDN font URL.

`tests/test_ui_design_tokens.py` must keep all palette assertions and add the exact family/geometry root tokens.

Run one GREEN group:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest \
  tests.test_ui_design_tokens \
  tests.test_font_assets \
  tests.test_palette_control_component -v
```

Expected: all tests in these three modules pass and the command ends with `OK`.

Install and verify on the Lenovo host after the unit group:

```bash
bash scripts/install_attentiveslides_demo_fonts.sh
fc-match -f '%{family}\n' Literata | head -1
fc-match -f '%{family}\n' 'IBM Plex Sans' | head -1
```

Expected first lines include `Literata` and `IBM Plex Sans`. Restart Chromium before the later visual check so it observes the font cache.

Commit:

```bash
git add assets/fonts scripts/install_attentiveslides_demo_fonts.sh \
  modules/ui/workspace.css modules/ui/design_tokens.py \
  modules/ui/voice_control_component/index.html \
  modules/ui/palette_control_component/index.html \
  modules/ui/slide_viewport_component/index.html tests/test_font_assets.py \
  tests/test_ui_design_tokens.py tests/test_palette_control_component.py \
  docs/superpowers/plans/2026-07-17-attentiveslides-02-aligned-ui-implementation.md
git commit -m "style: align AttentiveSlides typography with concept 02"
```

Before committing, narrow the `git add` list if unrelated files appear; never include caches.

---

## Checkpoint 2: Product Shell, Top Bar, Rails, and Slide Stage

**Purpose:** Make the visible page structure match 02 before polishing inner controls.

**Files:**

- Modify `apps/streamlit_attentive_slides.py`.
- Modify `modules/system/main_ui_state.py` only for new shell defaults/normalization.
- Modify `modules/ui/workspace.css`.
- Modify `tests/test_main_ui_state.py`.
- Modify `tests/test_main_ui_workspace_layout.py`.
- Modify `tests/test_slide_preview_canvas.py`.

### 2.1 Replace loose page rows with a stable shell

Keep the existing functions but give each zone one keyed boundary:

```text
main_sidebar_brand
main_topbar
main_study_shell
main_slide_toolbar
main_slide_stage
main_interaction_workspace
main_tutor_answer
main_slide_rail
main_slide_rail_reopen
```

Keep native `st.sidebar` as the real 226 px left rail. Do not build another left column inside main. Use the following concrete viewport contract:

```css
.st-key-main_sidebar_brand {
  position: fixed; inset: 0 auto auto 0;
  width: var(--as-left-rail-width); height: var(--as-topbar-height);
  z-index: 46;
}
.st-key-main_topbar {
  position: fixed; top: 0; left: var(--as-left-rail-width);
  right: var(--as-right-rail-width); height: var(--as-topbar-height);
  z-index: 45;
}
.st-key-main_slide_rail {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: var(--as-right-rail-width); z-index: 46;
}
```

The keyed sidebar brand contains the `A` mark and `AttentiveSlides`. Add 52 px top padding to native sidebar content after that cell. The central top bar contains context/status/actions but not a duplicate product name. The right rail's first 52 px is its `DECK INDEX` header; its thumbnail scroller begins below that header. Keep the native sidebar expanded for this desktop interface.

When `main_slide_rail_expanded` is false, set the central top bar/right padding to `right: 0`, hide only the right rail, and fix `main_slide_rail_reopen` at the extreme right below 52 px. Keyed-container positioning is the correctness mechanism; `:has(...)` may optimize the open/closed CSS but must not be the only mechanism that prevents normal document flow.

The normal Study route must render:

```python
_render_header(...)
_render_slide_selector(...)
slide_column, control_column = st.columns([1.0, fixed_control_ratio], gap="small")
# slide toolbar/stage and Tutor output stay in slide_column
# Control stays in control_column for both vertical rows
```

Streamlit cannot literally create a CSS grid across iframe boundaries, so use the simplest stable column composition plus CSS alignment. Do not add a new layout framework or duplicate the answer route.

### 2.2 Rebuild `_render_header`

Render the fixed sidebar brand cell plus one compact central top bar with:

- product mark `A` and serif `AttentiveSlides` in `main_sidebar_brand`;
- `STUDY / WORKSPACE` or `REVIEW / WORKSPACE`;
- real deck/lesson label;
- `{current:02d}—{total:02d}`;
- lifecycle status and tabular elapsed time;
- Start / Pause or Resume / End & Review actions according to the design spec.

At this checkpoint, wire Start and End exactly as today and render Pause/Resume only when the store exposes those states after Checkpoints 4–5. It is acceptable to introduce the button slots/classes now and finalize callbacks later. Do not show a nonfunctional enabled Pause button.

Remove the standalone wide `Start study` row and ensure the default Streamlit `Deploy` header does not become the visual product header in the demo.

### 2.3 Compact the left settings rail

Refactor `_render_live_controls` into the approved visible order:

1. lesson identity;
2. conversation flow;
3. speaking control;
4. attention/answer controls;
5. media master;
6. palette;
7. participant/calibration status.

Move upload replacement, privacy, provider/engine, context/history, system status, preview, and active deck details into compact collapsed expanders. Preserve every functional widget/key that is still used. Remove redundant explanatory paragraphs from the always-visible path.

Palette `locked` must eventually include `paused` as well as `active` and `finish_pending`; add the state check once Checkpoint 4 lands.

### 2.4 Fix `_render_slide_selector`

Retain the fixed right rail but enforce:

- open by default;
- 190 px width beginning at viewport top, with a 52 px rail header and scrolling thumbnails below it;
- title `DECK INDEX` and counter;
- 32×32 maximum close control;
- independent scroll;
- selected outline;
- current item scroll-into-view;
- collapsed reopen control fixed to the extreme right.

Do not use a DOM selector whose failure causes the reopen button to enter document flow. The keyed reopen container itself must be fixed. Verify both `main_slide_rail_expanded=True` and `False` in static contracts.

### 2.5 Replace the slide slider with a toolbar

In `_render_slide_workspace`:

- remove the full-width `st.slider` from the normal page;
- render `CANVAS / SLIDE NN` at left;
- render small minus, percentage, plus, and Fit controls at right;
- keep session key `main_slide_scale` (or migrate once in `main_ui_state`) with default 70;
- clamp to the existing allowed range;
- keep Learner State as a compact status/popover in the toolbar;
- remove the double-shrink: the slide viewport uses the full slide-column width and applies scale only once;
- keep previous/next navigation, AOI overlay, selection, and slide coordinate mapping unchanged.

`FIT` may set a stable fit sentinel or computed percentage; it must report an actual displayed percentage and must not introduce client/server resize polling.

### Focused GREEN group

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest \
  tests.test_main_ui_state \
  tests.test_main_ui_workspace_layout \
  tests.test_slide_preview_canvas -v
```

Expected: all tests pass and the command ends with `OK`.

Commit:

```bash
git add apps/streamlit_attentive_slides.py modules/system/main_ui_state.py \
  modules/ui/workspace.css tests/test_main_ui_state.py \
  tests/test_main_ui_workspace_layout.py tests/test_slide_preview_canvas.py \
  docs/superpowers/plans/2026-07-17-attentiveslides-02-aligned-ui-implementation.md
git commit -m "style: rebuild AttentiveSlides study shell"
```

---

## Checkpoint 3: `① CONTROL` and `② TUTOR OUTPUT`

**Purpose:** Remove the current long diagnostic card and make all voice modes share the compact 02 control/output hierarchy.

**Files:**

- Modify `apps/streamlit_attentive_slides.py`.
- Modify `modules/ui/voice_panel.py`.
- Modify `modules/ui/voice_control_component/__init__.py` and `index.html` only where compact presentation needs it.
- Modify `modules/ui/workspace.css`.
- Modify `tests/test_main_ui_voice_layout.py`.
- Modify `tests/test_voice_control_component.py`.
- Modify `tests/test_main_ui_widget_inventory.py`.

### 3.1 Refactor `_render_unified_interaction`

Render one header row:

```html
<div class="as-panel-heading">
  <span class="as-panel-index">1</span>
  <h2>CONTROL</h2>
  <span class="as-status-badge">READY</span>
</div>
```

The accessible name remains `Attention and voice controls`. Under it, keep exactly one `as-voice-state` block. Map `VoicePanelView` to short learner-facing copy and never stack a caption, warning, and success for the same state.

Delete normal-path rendering of these exact concepts:

- media-off typed-input explanation;
- attention-regions location explanation;
- complete-slide selected explanation;
- `Target ready · Slide ... · ... AOI match(es)`;
- `Matched: ...` raw IDs;
- live transport/runtime/media/local-gaze caption.

Preserve genuine errors, but phrase them as one actionable message. Move raw transport details into the existing Advanced/System Status expander.

### 3.2 Flatten target and intent controls

Adjust `_render_target_column`, `_render_compact_target_summary`, `_render_intent_column`, and `_render_live_target_column` so the Control hierarchy is:

1. current state/target block;
2. voice transport;
3. typed question/intent;
4. target source/listening behavior only when actionable;
5. small Edit/Clear/Retry actions.

Remove repeated `Target`, `Ask tutor`, and `Quick actions` large headings. Use 10 px field labels instead. Keep all widget keys and confirmation behavior needed by the backend.

Do not restore a Generate Answer button. Release/turn end auto-generates; confirmation continues immediately.

### 3.3 Preserve one component across voice modes

`One-turn`, `Dialogue`, and `Realtime` continue to use `_render_manual_interaction` → `_render_unified_interaction`. `Hold` and `Hands-free` use the same component boundary. Verify:

- global safe `V` PTT remains;
- pointer and `V` take the same start/stop path;
- Hands-free can pause/resume listening;
- no second media capture is opened;
- only state text/action changes, not panel placement;
- iframe height is compact and does not leave a provider/debug block.

### 3.4 Refactor `_render_lower_workspace`

Rename the visible heading to `② TUTOR OUTPUT`, with a circled index and compact action row. The output stays below the slide only. Use Literata 15/22 for the answer and one 10 px metadata line. Keep Conversation history collapsed and keep One-turn/Dialogue/Realtime on this same route.

Do not render decorative Replay/Follow-up/Save Note buttons unless their callbacks are real. Existing answer audio/retry actions remain if wired.

### Focused GREEN group

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest \
  tests.test_main_ui_voice_layout \
  tests.test_voice_control_component \
  tests.test_main_ui_widget_inventory -v
```

Expected: all tests pass and the command ends with `OK`.

### Single interim visual check

Use the existing `scripts/run_live_single_port.py` launcher on port 8502 and inspect one Study screenshot at the target 4060 scale. Compare side by side with `docs/superpowers/specs/assets/attentiveslides-02-reference.png`. This is manual visual inspection, not a new browser test suite.

Correct immediately if any of these structural failures appear:

- product title missing;
- right-rail reopen control on the left/in flow;
- full-width red scale slider remains;
- slide is double-shrunk;
- Control is a large rounded card or routine captions remain;
- Tutor output spans under Control instead of only under the slide;
- Literata/IBM Plex Sans are not visibly resolved.

Do not spend this checkpoint on one-pixel tuning; correct hierarchy and proportions.

Commit:

```bash
git add apps/streamlit_attentive_slides.py modules/ui/voice_panel.py \
  modules/ui/voice_control_component modules/ui/workspace.css \
  tests/test_main_ui_voice_layout.py tests/test_voice_control_component.py \
  tests/test_main_ui_widget_inventory.py \
  docs/superpowers/plans/2026-07-17-attentiveslides-02-aligned-ui-implementation.md
git commit -m "style: align voice controls and tutor output with concept 02"
```

---

## Checkpoint 4: Backward-Compatible Pause Persistence and Timing

**Purpose:** Make Pause a real lifecycle state and make Review duration exclude paused time before wiring UI/runtime controls.

**Files:**

- Modify `modules/review/contracts.py`.
- Modify `modules/review/study_review_store.py`.
- Modify `modules/media/single_port_transport.py` to separate technical media gaps from user Pause.
- Modify `modules/ui/review_view.py` only for active-duration mapping.
- Modify `tests/test_study_review_store.py`.
- Modify `tests/test_single_port_transport.py` for the renamed technical-gap call.
- Modify `tests/test_review_view.py`.

### 4.1 Extend `StudyReviewSession` additively

Keep `STUDY_REVIEW_SCHEMA_VERSION` unchanged because the change is backward-compatible. Add at the end of the dataclass:

```python
paused_seconds: float = 0.0
```

Validate it as finite, nonnegative, and not greater than wall duration beyond numeric tolerance. Add:

```python
@property
def active_seconds(self) -> float:
    return max(
        0.0,
        self.ended_at_epoch - self.started_at_epoch - self.paused_seconds,
    )
```

`to_dict()` writes rounded `paused_seconds`; `from_dict()` uses `float(payload.get("paused_seconds", 0.0))`. Old schema-v1 JSON therefore remains valid. Do not mutate nested gaze session timestamps; they still preserve the Study's wall-clock identity.

### 4.2 Make the in-memory lifecycle explicit

Extend `_ActiveStudy` with monotonic timing:

```python
started_received_at: float
paused_at_received: float | None = None
paused_seconds: float = 0.0
```

Extend `StudyLifecycleSnapshot`:

```python
status: Literal["idle", "active", "paused", "finish_pending"]
active_seconds: float = 0.0
paused_seconds: float = 0.0
revision: int = 0
```

Keep one store-owned `_lifecycle_revision` counter. Increment it on Start, user Pause, Resume, and transition to frozen Finish. Compute lifecycle timing with the injected monotonic clock. While paused, repeated snapshots return the same `active_seconds` and `revision`. The pair `(session_id, revision)` is the only late-result token used later; do not create a parallel session-state generation counter.

### 4.3 Correct learner accumulation

Change `LearnerStateReviewAccumulator.pause(now)` to:

- close the prior observation;
- close the current study-time interval;
- set `_context_started_at = None` so `active_slide_summary` cannot continue counting.

Add `resume(now)` that reactivates the latest valid current context at `now` without restoring the previous learner observation. A new observation must arrive after Resume before learner-state duration accumulates again.

Add a separate `mark_observation_gap(now)` on the learner accumulator that calls only `_close_observation(now)` and leaves `_context_started_at` untouched. The store's technical-gap API calls `gaze.pause()` plus this observation-only method; it must not call the full learner `pause(now)`.

`set_context()` while paused may update the store's latest context but must not start learner time until Resume.

### 4.4 Implement idempotent store Pause/Resume

First preserve the meaning of existing media cleanup. Add:

```python
def mark_observation_gap(self, received_at: float | None = None) -> None: ...
```

It closes the current gaze/learner observation interval without changing lifecycle status, active Study time, session ID, or revision. In `modules/media/single_port_transport.py`, change the three current technical calls in `FallbackMediaIngress.start`, `reset_active_readiness`, and `_clear_sessions` from `study_review.pause()` to `study_review.mark_observation_gap()`. A browser reconnect must never display `PAUSED` or require the learner to press Resume.

`StudyReviewStore.pause()`:

- acts only when active and not already paused;
- captures one monotonic `paused_at_received`;
- pauses gaze and learner accumulators;
- leaves session ID, deck, registered slides, and current context intact.

`StudyReviewStore.resume()`:

- acts only when paused;
- adds `now - paused_at_received` to accumulated paused seconds;
- clears `paused_at_received`;
- resumes learner study time at `now` for the latest valid context;
- allows gaze to continue naturally on the next accepted sample.

While paused, `accept_gaze`, `accept_learner_state`, and `record_completed_interaction` return `False`. They must not alter summaries. `set_context` and `register_slide` may keep structural knowledge current but do not accumulate evidence.

`finish()` while paused closes the open pause interval, persists total `paused_seconds`, and finishes gaze/learner accumulators exactly once. Retry of a failed canonical write reuses the same frozen record.

### 4.5 Map Review duration

In `build_review_view`, replace wall duration with `review.active_seconds` for:

- `Study duration`;
- learner coverage denominator;
- any session-level study-time comparison.

Per-slide study time already comes from learner accumulation and must agree within normal sampling tolerance.

### Focused test cases

Add deterministic clock tests for:

- active elapsed advances before Pause and freezes during Pause;
- repeated Pause/Resume is idempotent;
- gaze, learner state, and interactions are rejected during Pause;
- Resume continues the same session/context and adds only post-resume time;
- context changed while paused activates only on Resume;
- Finish while paused includes the open paused interval;
- failed finish retry preserves paused duration and identity;
- browser replacement, readiness reset, and disconnect close observation gaps without changing active lifecycle or stopping per-slide Study time;
- lifecycle revision changes only on Start/Pause/Resume/frozen Finish and remains stable across snapshots;
- old JSON without `paused_seconds` loads as zero;
- invalid negative/nonfinite/excess paused duration is rejected;
- Review summary/coverage use active rather than wall time.

Run one GREEN group:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest \
  tests.test_study_review_store \
  tests.test_single_port_transport \
  tests.test_review_view -v
```

Expected: all tests pass and the command ends with `OK`.

Commit:

```bash
git add modules/review/contracts.py modules/review/study_review_store.py \
  modules/media/single_port_transport.py modules/ui/review_view.py \
  tests/test_study_review_store.py tests/test_single_port_transport.py \
  tests/test_review_view.py \
  docs/superpowers/plans/2026-07-17-attentiveslides-02-aligned-ui-implementation.md
git commit -m "feat: add complete study pause timing"
```

---

## Checkpoint 5: Pause/Resume UI and Runtime Integration

**Purpose:** Connect the new lifecycle to media, voice, interaction, palette lock, and the top bar without inventing a second state machine.

**Files:**

- Modify `apps/streamlit_attentive_slides.py`.
- Modify `modules/ui/voice_panel.py`.
- Modify `modules/ui/voice_control_component/__init__.py` and `index.html`.
- Modify `modules/ui/workspace.css`.
- Modify `modules/media/single_port_transport.py` (`VoiceTransport` protocol and command-path contract).
- Modify `modules/media/live_ingress_service.py` (one idempotent quiesce/resume API).
- Modify `modules/system/voice_orchestrator.py` (server-side suspended command gate).
- Add `tests/test_main_ui_pause_layout.py`.
- Modify `tests/test_single_port_transport.py`.
- Modify `tests/test_live_ingress_service.py`.
- Modify `tests/test_voice_orchestrator.py`.

### 5.1 Use the store as lifecycle truth

Remove `main_study_started_monotonic` as an independent timer. `_render_header` obtains `resources.study_review.lifecycle()` and formats `active_seconds`. A one-second fragment/rerun may refresh the display while active; it must not run media or interaction work merely to update the clock.

Add callbacks with one responsibility each:

```python
def _pause_study_review(resources: MainLiveResources) -> None: ...
def _resume_study_review(resources: MainLiveResources) -> None: ...
def _finish_study_review(resources: MainLiveResources, deck_id: str) -> None: ...
```

Do not store a separate `main_study_paused` boolean.

### 5.2 Add the server-side suspended command gate

Extend `VoiceTransport` with a synchronous, thread-safe gate method:

```python
def set_suspended(self, suspended: bool, reason: str) -> None: ...
```

`VoiceOrchestrator` owns `_suspended` under its existing lock. Its contract is:

- `set_suspended(True, reason)` flips the gate immediately before any awaited provider stop;
- `should_consume_audio()` returns `False` and `accept_pcm()` discards input while suspended;
- `handle_http_command()` rejects `ptt/start`, `continuous/start`, and `target/confirm` while suspended;
- cleanup commands `ptt/stop`, `continuous/stop`, and `target/reject` remain accepted and idempotent;
- `snapshot()` includes `suspended` and a short reason for diagnostics;
- `set_suspended(False, ...)` reopens the command path but does not itself start capture.

This is the authoritative server-side Pause guard. Disabled iframe controls are defense in depth, not the guarantee.

### 5.3 Add one safe `LiveIngressService` quiesce path

Add public idempotent methods:

```python
def quiesce(self, reason: str) -> None: ...
def resume_from_quiesce(self, *, master_enabled: bool) -> None: ...
```

`quiesce()` must execute in this order:

1. synchronously set the voice transport suspended gate;
2. set master false/disarm ingress so new media sessions are rejected;
3. try the existing loop-owned voice stop;
4. in `finally`, call `_reconcile_core()` so runtime/media stop occurs even if voice stop times out or raises;
5. re-raise a concise `RuntimeError` only after the command gate is closed and runtime stop was attempted.

Do not call private `_stop_voice_from_sync` from the Streamlit app. `shutdown()` may reuse `quiesce("service shutdown")`. `resume_from_quiesce()` clears the voice gate first, then restores master state from its explicit argument and reconciles; it never reads Streamlit state itself.

### 5.4 Pause, Resume, and End sequences

`_pause_study_review` for Active:

1. call `resources.study_review.pause()` first so evidence/interaction records are rejected immediately and lifecycle revision advances;
2. clear incomplete turn state: `main_live_proposal`, incomplete `main_confirmed_interaction`, confirmation error, rerun request, inbox/snapshot proposal queues, and pending automatic playback; preserve `main_tutor_result`, the last completed interaction ID, and conversation history;
3. call `resources.service.quiesce("study paused")`;
4. leave `main_live_master_enabled` unchanged as the user's preference;
5. if quiesce reports an error, remain Paused with the gate closed and show one recoverable runtime error in Advanced/System Status;
6. rerun to the read-only Paused presentation.

`_resume_study_review` for Paused:

1. call `resources.service.resume_from_quiesce(master_enabled=bool(main_live_master_enabled))` first;
2. if service resume fails, keep the store Paused and show the error;
3. on success, call `resources.study_review.resume()` so a new lifecycle revision begins;
4. synchronize current slide/AOI/voice target through `_bind_main_live_resources` and `_sync_main_live_voice_resources`;
5. do not automatically replay the preserved answer or record an interaction;
6. rerun to Ready/Listening.

`_finish_study_review` from **both Active and Paused**:

1. if Active, call `study_review.pause()` to close evidence immediately; if already Paused, leave it idempotent;
2. clear incomplete turn/proposal/playback state as above;
3. call `service.quiesce("study finished")` and do not save until it succeeds;
4. call `study_review.finish(deck_id=...)` and route to Review;
5. if quiesce fails, remain Paused and allow retry;
6. if canonical save fails, retain the existing frozen `finish_pending`, keep service/voice quiesced, and expose the existing safe finish retry.

The Review route must not be the first place media is stopped. Opening a previously saved Review is allowed only while lifecycle is `idle` and calls `service.quiesce("saved review opened")` before switching workspace mode. The Review top-bar `BACK TO STUDY` calls `resume_from_quiesce(master_enabled=the preserved preference)` before returning; on failure it remains in Review and shows the error. Thus Review never captures even when the user left the media preference enabled.

### 5.5 Guard every mutating path and late result

Use explicit lifecycle sets:

```python
def _study_mutations_enabled(resources: MainLiveResources) -> bool:
    return resources.study_review.lifecycle().status in {"idle", "active"}

def _media_runtime_requested(resources: MainLiveResources) -> bool:
    return (
        _study_mutations_enabled(resources)
        and bool(st.session_state.get("main_live_master_enabled", False))
    )
```

`paused` and `finish_pending` both disable media, proposal consumption, auto-generation, typed/quick intents, target editing/confirmation, navigation/context mutation, conversation clearing, answer playback, and runtime preference changes. Palette remains locked for `active`, `paused`, and `finish_pending`. `RESUME` exists only for Paused; `END & REVIEW` exists for Active and Paused; finish retry exists for finish-pending. Non-mutating diagnostics stay accessible. Audit every current status set, including `_open_latest_review`, rather than patching only header and palette checks.

Use the store-owned token `(lifecycle.session_id, lifecycle.revision)`:

- `_consume_live_proposal` accepts a proposal only when mutations are enabled, the voice snapshot is not suspended, and the event belongs to the current browser-media session; save the current token beside the proposal;
- `_store_live_confirmation` copies that proposal token into `main_confirmed_interaction`;
- `_generate_confirmed_turn` captures the token before the Tutor call and rechecks it before assigning `main_tutor_context`, `main_tutor_result`, conversation history, interaction log, or automatic TTS;
- `_log_completed_interaction_once` and initial answer playback also recheck the token;
- Pause/Resume/Frozen Finish increments the store revision, so pre-transition work becomes invalid;
- displaying the last completed `main_tutor_result` does not require the old token; it remains visible. Automatic playback is suppressed after a token change, while a later explicit Replay is a new action under the current lifecycle.

Do not introduce a `main_generation_epoch` or another independent lifecycle counter. On Pause/Finish, drain application proposal queues after closing the service gate so a pre-Pause event cannot be relabeled with the post-Resume token.

In the voice component, transition to `study_paused` uses the existing lost-keyup/teardown stop path, stops Hands-free continuous requests, and disables the global `V` handler. The component still sends safe stop/cancel when necessary; server rejection covers any late start race.

### 5.6 Paused presentation

- top bar: amber dot, `PAUSED mm:ss`, `RESUME`, `END & REVIEW`;
- Control: badge `PAUSED`, one line `Study paused`, no waveform/recording action;
- working content remains visible but read-only;
- no page-wide warning banner and no repeated pause captions;
- Finish while paused routes to Review and persists the open pause interval.

### Focused tests

`tests/test_main_ui_pause_layout.py` must use fake resources/clocks/session state to exercise callback behavior; static inventory assertions may supplement but not replace behavior tests. Cover:

- Pause advances the store lifecycle before service quiesce and preserves the media preference;
- Resume calls service restore before store Resume and stays Paused on restore failure;
- Active and Paused End both quiesce; save failure stays finish-pending and quiesced;
- opening saved Review from Idle quiesces, paused/finish-pending cannot open it, and Back to Study safely restores the preserved preference;
- paused/finish-pending reject every mutating path and opening saved Review;
- token mismatch discards proposal, Tutor commit, interaction log, and automatic playback while preserving the last completed displayed answer;
- the header maps all lifecycle states without a duplicate timer.

The service/orchestrator/transport tests must cover:

- suspended start/confirm commands are rejected server-side and stop/reject commands remain safe;
- audio is not consumed while suspended;
- voice stop failure still stops runtime/media in `finally` and leaves the gate closed;
- Resume clears the gate before optional master enable;
- repeated quiesce/resume is idempotent;
- technical ingress cleanup still calls `mark_observation_gap`, not user Pause.

Run one GREEN group:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest \
  tests.test_main_ui_pause_layout \
  tests.test_single_port_transport \
  tests.test_live_ingress_service \
  tests.test_voice_orchestrator -v
```

Expected: all selected tests pass and the command ends with `OK`.

Commit:

```bash
git add apps/streamlit_attentive_slides.py modules/ui/voice_panel.py \
  modules/ui/voice_control_component modules/ui/workspace.css \
  modules/media/single_port_transport.py modules/media/live_ingress_service.py \
  modules/system/voice_orchestrator.py tests/test_main_ui_pause_layout.py \
  tests/test_single_port_transport.py tests/test_live_ingress_service.py \
  tests/test_voice_orchestrator.py \
  docs/superpowers/plans/2026-07-17-attentiveslides-02-aligned-ui-implementation.md
git commit -m "feat: wire full study pause and resume"
```

---

## Checkpoint 6: Review Workspace Visual Alignment

**Purpose:** Apply the same 02 system to Review while preserving the already implemented gaze, emotion, fatigue, engagement, duration, and interaction evidence.

**Files:**

- Modify `apps/streamlit_attentive_slides.py` Review render functions.
- Modify `modules/ui/review_view.py` only for presentation fields not completed in Checkpoint 4.
- Modify `modules/ui/workspace.css`.
- Modify `tests/test_main_ui_review_layout.py`.

### 6.1 Shared shell

Review uses the same:

- product identity cell;
- `REVIEW / WORKSPACE` context top bar;
- Literata/IBM Plex typography;
- left rail widths and square geometry;
- fixed right deck rail for selected slide;
- palette semantic variables.

`BACK TO STUDY` appears only once, as the Review top-bar primary action. The Review left rail retains the completed-session selector, JSON export, metadata, and collapsed deletion confirmation; it does not duplicate Back to Study and does not display live voice controls.

### 6.2 Summary hierarchy

Render one horizontal metric band, not floating KPI cards. Include:

- active Study duration (`review.active_seconds`);
- slides viewed;
- completed interactions;
- gaze/valid gaze coverage as already available;
- learner-state coverage;
- top emotion, mean engagement, and mean fatigue in the next evidence band or detail region if the first band would overcrowd.

Use `Unavailable` for absent modality evidence, not `0%` unless zero is measured. Preserve emotion probability, fatigue and distraction alert duration/count, modality-specific observation duration, and interaction count.

### 6.3 Slide and evidence detail

- show slides in deck order with compact study time, interaction count, engagement, fatigue, and emotion;
- selecting a slide updates the right rail and central detail;
- keep screenshot/heatmap and AOI dwell list legible;
- use thin rules and one accent edge rather than nested rounded cards;
- show the learner-state evidence already stored at session and slide levels;
- do not add second-by-second charts or raw frame histories.

### Focused GREEN group

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest \
  tests.test_main_ui_review_layout -v
```

Expected: all tests pass and the command ends with `OK`.

### Final manual visual acceptance

Inspect Study and Review once at the target 4060 display. Exercise these states manually without creating a browser automation suite:

1. right rail open and collapsed;
2. One-turn + Hold PTT ready state;
3. Hands-free ready state;
4. active Study then Pause then Resume;
5. End & Review from Paused;
6. Review summary and one selected-slide detail;
7. one non-default palette in Idle/Review, then confirm palette is locked in Active/Paused;
8. gaze cursor when available.

Use the design specification's section 20 checklist. Compare to `attentiveslides-02-reference.png`, with special attention to type sizes, 52 px top bar, 226/292/190 widths, 2–4 px corners, slide dominance, Control density, and deleted diagnostic copy.

Only fix visual defects that violate the approved hierarchy or acceptance checklist. Do not start an unrelated architecture cleanup.

Commit:

```bash
git add apps/streamlit_attentive_slides.py modules/ui/review_view.py \
  modules/ui/workspace.css tests/test_main_ui_review_layout.py \
  docs/superpowers/plans/2026-07-17-attentiveslides-02-aligned-ui-implementation.md
git commit -m "style: align AttentiveSlides review workspace"
```

---

## Checkpoint 7: One Whole-Change Review, Bounded Fix Wave, Full Suite Once

### 7.1 Review the complete diff

Review from the documentation implementation baseline to `HEAD`:

Resolve the documentation commit from the design-spec history; the design spec is not edited by execution-ledger updates:

```bash
BASELINE="$(git log -1 --format=%H -- \
  docs/superpowers/specs/2026-07-17-attentiveslides-02-aligned-ui-design.md)"
git log --oneline --decorate -12
git diff --stat "$BASELINE"..HEAD
git diff --check "$BASELINE"..HEAD
git diff "$BASELINE"..HEAD -- apps modules scripts assets/fonts tests
```

The review must check:

- every section-20 visual acceptance item from the design spec;
- no second shell/voice/answer path was introduced;
- Pause store lifecycle, runtime gate, UI disabled state, and persisted duration agree;
- Pause never mutates the user's media preference and Resume restores only that preference;
- paused events cannot accumulate gaze, learner state, interactions, or answer playback;
- old Review JSON remains readable;
- Review uses active duration;
- `V` safety and Hands-free stop paths remain intact;
- slide/AOI coordinate behavior is untouched;
- no remote asset, dark mode, raw diagnostic copy, UI framework, or unrelated architecture work appeared;
- no font license/provenance omission;
- no user-facing fake lesson data from the reference was copied.

Classify findings as Critical, Important, or Minor. Fix Critical/Important findings in one bounded wave. Run only the directly affected focused test module(s) after that wave. Do not rerun already-passing unaffected groups.

If the user explicitly requests an implementation review subagent in the execution turn, use exactly one for this whole-change review. Otherwise perform the review as a distinct final pass in the executing task; do not silently add a subagent.

### 7.2 Run the full suite once

After review fixes:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest discover \
  -s tests -p 'test_*.py' -v
```

Expected: the complete discovered suite passes and ends with `OK`. Record the test count and duration from the actual output. If the suite fails, diagnose and run only the smallest affected group after the fix, then rerun the full suite at most once.

### 7.3 Final commit only if needed

If review fixes or ledger updates remain, inspect `git status --short`, stage each file from the bounded fix wave by its explicit path, and commit with message `fix: address AttentiveSlides 02 alignment review`. Do not use `git add .` or stage unrelated files.

Do not create an empty commit. Documentation-only ledger updates do not justify repeating the full suite.

### 7.4 Handoff evidence

Report:

- branch and final commit;
- checkpoint commits;
- focused GREEN results from the ledger;
- one full-suite result;
- visual acceptance states inspected;
- any intentional minor deviation from 02 and its reason;
- that no push/merge was performed;
- exact launch command/URL for the user to inspect.

## Definition of Done

The plan is complete only when:

- the visible UI has the 02 product title, top bar, grid, typography, density, square geometry, Control hierarchy, Tutor output, and right deck rail;
- the listed routine diagnostics are absent from the learner path;
- all voice modes retain one stable Control/output layout and existing behavior;
- Pause/Resume freezes and restores active time, gaze, learner state, PTT, Hands-free, Realtime, and interaction actions without losing context;
- Review active duration excludes pause and old JSON remains compatible;
- Review includes current gaze, emotion, fatigue, engagement, duration, coverage, and interaction evidence;
- the font files are self-hosted, licensed, installed on the Lenovo demo host, and actually resolve;
- the single final whole-change review has no unresolved Critical/Important findings;
- every checkpoint's focused GREEN group and the one final full suite pass;
- work is committed locally on `codex/gaze-heatmap-review`, with no push or merge.
