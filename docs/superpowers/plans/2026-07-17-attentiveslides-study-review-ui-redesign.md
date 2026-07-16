# AttentiveSlides Study and Review UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Do not use implementation subagents unless the user explicitly requests them. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Structured Reading Desk interface for Study and Review, including semantic palette switching, a unified voice interaction panel, automatic answer generation, low-salience gaze feedback, and learner-state Review presentation.

**Architecture:** Keep the existing Streamlit app as the composition layer and preserve all backend contracts. Extract palette tokens, base CSS, voice-state presentation, Review presentation, and local palette persistence into focused UI modules; then route the existing single-turn, conversation-history, Omni, gaze, and Study Review data through one stable Study/Review shell.

**Tech Stack:** Python 3.10, Streamlit 1.59.1, Streamlit custom components, HTML/CSS/JavaScript, existing aiohttp voice/media transport, unittest static/pure contract tests.

## Global Constraints

- Work in `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration` on existing branch `codex/gaze-heatmap-review`; create no branch or worktree.
- Continue from commit `9fafb76` or its direct documentation-only descendant.
- Do not push, merge, or replace `main` during this plan.
- Light mode only; do not add dark-mode tokens or behavior.
- Target the Lenovo `2560x1600` display at approximately 160% scaling; mobile is out of scope.
- Use English learner-facing copy.
- Use `Noto Serif` for headings/editorial answers and `Noto Sans` for controls; make no runtime font request.
- Do not add glassmorphism, background blur panels, gradients, animated decoration, or a UI framework dependency.
- Do not change VAD thresholds, gaze aggregation mathematics, Tutor grounding, provider fallback, Study Review storage contracts, or learner-state models.
- Do not add second-by-second learner-state analytics or Q&A transcript persistence to completed reviews.
- Do not add a Study pause lifecycle.
- Do not run a baseline suite or any RED/expected-failing test.
- After each checkpoint, run only its named focused GREEN group.
- If a focused group fails, rerun only the affected test module or smallest relevant group after the fix.
- Do not add browser automation, screenshot tests, lint, type, security, or performance suites.
- Perform one independent whole-change review after all implementation checkpoints.
- Run the complete unit suite once after review and any bounded fixes.
- Do not repeat a passing full suite because of commits, handoff, or documentation-only changes.

## Planned File Map

### New files

- `modules/ui/design_tokens.py`: palette registry, normalization, semantic CSS-variable rendering.
- `modules/ui/workspace.css`: shared Study/Review shell, typography, rails, controls, panels, and responsive desktop CSS.
- `modules/ui/palette_control_component/__init__.py`: Streamlit wrapper for the palette control.
- `modules/ui/palette_control_component/index.html`: swatches, local-storage persistence, active-study lock state.
- `modules/ui/voice_panel.py`: pure mapping from runtime/speech state to learner-facing panel state.
- `modules/ui/review_view.py`: pure mapping from stored Review contracts to session, slide-order, and selected-slide presentation values.
- `tests/test_ui_design_tokens.py`: palette normalization and CSS-token contracts.
- `tests/test_palette_control_component.py`: static local-storage, locking, and safe-rendering contracts.
- `tests/test_main_ui_workspace_layout.py`: static shell/right-rail/top-level-mode inventory.
- `tests/test_main_ui_voice_layout.py`: unified voice/answer layout and automatic-generation contracts.
- `tests/test_review_view.py`: Review metric/coverage mapping.
- `tests/test_main_ui_review_layout.py`: static Review hierarchy contract.

### Modified files

- `apps/streamlit_attentive_slides.py`: compose the new shell, controls, unified interaction, automatic generation, and Review hierarchy.
- `modules/system/main_ui_state.py`: new interaction-flow, palette, and right-rail defaults; remove the top-level Manual/Live default.
- `modules/ui/voice_control_component/__init__.py`: pass the stable flow/speaking-control arguments and iframe palette tokens required by the compact transport UI.
- `modules/ui/voice_control_component/index.html`: compact PTT/Hands-free transport, `V` shortcut, pause listening, and teardown safety.
- `modules/ui/slide_viewport_component/__init__.py`: pass palette tokens for iframe chrome without changing invariant gaze/AOI colors.
- `modules/ui/slide_viewport_component/index.html`: apply palette tokens to themeable chrome and use the low-salience gaze cursor; preserve coordinate and AOI behavior.
- `tests/test_main_ui_state.py`: new defaults and flow migration.
- `tests/test_main_ui_widget_inventory.py`: replace removed/added widget keys.
- `tests/test_slide_preview_canvas.py`: right-rail and gaze-cursor static contracts.
- `tests/test_voice_control_component.py`: `V`, Hands-free, teardown, and compact component contracts.

---

### Task 1: Semantic Design Tokens and Persistent Palette Control

**Files:**
- Create: `modules/ui/design_tokens.py`
- Create: `modules/ui/workspace.css`
- Create: `modules/ui/palette_control_component/__init__.py`
- Create: `modules/ui/palette_control_component/index.html`
- Create: `tests/test_ui_design_tokens.py`
- Create: `tests/test_palette_control_component.py`

**Interfaces:**
- Produces: `DEFAULT_PALETTE_ID`, `PALETTE_STORAGE_KEY`, `PALETTES`, `normalize_palette_id(value)`, `palette_semantic(value)`, and `render_palette_css(value)`.
- Produces: `render_palette_control(*, selected: str, palette_tokens: Mapping[str, str], locked: bool, key: str) -> str | None`.
- Consumed by: the Streamlit shell in Task 2 and Review shell in Task 5.

- [ ] **Step 1: Implement the three-layer palette registry**

Create this public shape in `modules/ui/design_tokens.py`:

```python
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

DEFAULT_PALETTE_ID = "ivory-study-desk"
PALETTE_STORAGE_KEY = "attentiveslides-ui-palette-v1"

@dataclass(frozen=True)
class PaletteDefinition:
    palette_id: str
    label: str
    semantic: Mapping[str, str]

def normalize_palette_id(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in PALETTES else DEFAULT_PALETTE_ID

def palette_semantic(value: object) -> dict[str, str]:
    palette = PALETTES[normalize_palette_id(value)]
    return dict(palette.semantic)

def render_palette_css(value: object) -> str:
    declarations = "\n".join(
        f"--as-{name}: {css_value};"
        for name, css_value in palette_semantic(value).items()
    )
    return f":root {{\n{declarations}\n}}"
```

Define exactly four palettes: `ivory-study-desk`, `autumn-reading-room`, `cool-archive`, and `dusty-blue`. Copy the complete 16-key semantic table from the design spec verbatim for every palette. Require the same semantic keys in all palettes and validate this at import time. Keep status, AOI, heatmap, and gaze-cursor colors out of the palette registry.

- [ ] **Step 2: Move base visual rules into `workspace.css`**

The stylesheet must consume semantic variables only:

```css
:root {
  --as-font-heading: "Noto Serif", "DejaVu Serif", serif;
  --as-font-ui: "Noto Sans", "DejaVu Sans", sans-serif;
  --as-radius-control: 6px;
  --as-radius-panel: 8px;
  --as-radius-shell: 12px;
  --as-left-rail-width: 232px;
  --as-right-rail-width: 194px;
  --as-topbar-height: 56px;
}
```

Add rules for the top bar, built-in sidebar, fixed right rail, main two-row workspace, slide stage, unified interaction panel, Tutor answer, Review summary, learner-state rows, buttons, selects, tabs/segments, focus rings, empty/error states, and the collapsed-right-rail reopen control. Use borders/background planes for hierarchy. Only the slide surface may use the approved restrained shadow.

- [ ] **Step 3: Implement the palette component**

`palette_control_component/index.html` must:

- render four named buttons with three color swatches each;
- use `textContent`, `dataset`, and explicit DOM creation; never inject preference content through `innerHTML`;
- read `attentiveslides-ui-palette-v1` on first render;
- normalize unknown storage values to `ivory-study-desk`;
- call `Streamlit.setComponentValue(paletteId)` when the stored or clicked value differs from the Python-selected value;
- write local storage only after an enabled user click;
- set `disabled`, `aria-disabled`, and the explanation `Palette is locked during an active study.` when `locked` is true;
- mark the selected button with `aria-pressed="true"`;
- use no remote font, image, script, or stylesheet.

The Python wrapper declares the component from its local directory, passes the normalized `selected` ID and `palette_semantic(selected)` as `palette_tokens`, and returns `None` until the component has a value. The iframe accepts only the 16 whitelisted semantic keys and applies them as `--as-*` variables on `document.documentElement`; it must not depend on parent-document CSS-variable inheritance.

- [ ] **Step 4: Add focused palette and component tests**

`tests/test_ui_design_tokens.py` must cover:

- default/unknown normalization;
- all four labels and IDs;
- equal semantic-key sets;
- all 64 exact palette values from the design-spec table;
- rendered CSS contains semantic variables and no component-specific hardcoded selector;
- no dark-mode token.

`tests/test_palette_control_component.py` must statically assert:

- the storage key;
- four palette IDs;
- `localStorage.getItem` and `localStorage.setItem`;
- locked/disabled and `aria-pressed` handling;
- `Streamlit.setComponentValue`;
- complete `palette_tokens` input and whitelisted iframe-root CSS-variable application;
- no `innerHTML` and no `http://` or `https://` asset.

- [ ] **Step 5: Run the checkpoint GREEN group**

Run:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_ui_design_tokens tests.test_palette_control_component -v
```

Expected: both modules pass.

- [ ] **Step 6: Commit**

```bash
git add modules/ui/design_tokens.py modules/ui/workspace.css modules/ui/palette_control_component tests/test_ui_design_tokens.py tests/test_palette_control_component.py
git commit -m "feat: add AttentiveSlides UI design tokens"
```

---

### Task 2: Shared Study Shell, Stable Grid, and Persistent Slide Rail

**Files:**
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `modules/system/main_ui_state.py`
- Modify: `tests/test_main_ui_state.py`
- Modify: `tests/test_main_ui_widget_inventory.py`
- Modify: `tests/test_slide_preview_canvas.py`
- Create: `tests/test_main_ui_workspace_layout.py`

**Interfaces:**
- Consumes: `normalize_palette_id`, `render_palette_css`, `render_palette_control`, and `workspace.css`.
- Produces session keys: `main_interaction_flow`, `main_ui_palette`, `main_slide_rail_expanded`, and existing `main_speech_mode`.
- Preserves internal keys: `main_voice_engine`, `main_live_master_enabled`, and `main_history_enabled` because backend orchestration still consumes them.

- [ ] **Step 1: Replace top-level Manual/Live state with user-facing flow state**

Update `build_main_live_defaults()` and normalization to use:

```python
"main_interaction_flow": "one_turn",
"main_speech_mode": "push_to_talk",
"main_voice_engine": "single_turn",
"main_live_master_enabled": False,
"main_confirmation_policy": "Confidence-based auto",
"main_auto_confirm_threshold": 0.80,
"main_ui_palette": "ivory-study-desk",
"main_slide_rail_expanded": True,
```

Remove `main_interaction_mode`. Add one flow callback with the exact mapping:

```python
FLOW_ENGINE = {
    "one_turn": "single_turn",
    "dialogue": "single_turn",
    "realtime": "omni",
}
```

Set `main_history_enabled` only for `dialogue`; Realtime history remains provider-owned. Reuse the existing voice-engine hot-update callback after deriving the internal engine.

- [ ] **Step 2: Migrate every media-runtime gate to the visible master control**

Add one helper such as:

```python
def _media_runtime_requested() -> bool:
    return bool(st.session_state.get("main_live_master_enabled", False))
```

Replace every `main_interaction_mode == "Live"` condition that currently gates media-service startup/shutdown, periodic event polling, learner-state sensing/rendering, or answer-audio enablement with this sole master-control predicate. Conversation flow may choose engine and history semantics, but must never enable or disable capture, polling, sensing, or TTS by itself. Typed input and text answers remain available with the media master off. Remove all runtime reads and writes of `main_interaction_mode` after migration.

Set the learner-facing confirmation default to `Confidence-based auto` at `0.80`: valid resolved AOIs at or above the threshold auto-confirm; missing, invalid, or lower-confidence AOIs enter the existing confirmation UI. Keep `Always confirm` only under Advanced voice settings.

- [ ] **Step 3: Inject palette variables and the shared stylesheet once per run**

Load `modules/ui/workspace.css` from a repository-relative `Path`, cache the file text, and inject:

```python
st.html(
    "<style>"
    + render_palette_css(st.session_state["main_ui_palette"])
    + workspace_css
    + "</style>"
)
```

Render the palette component in the left rail. When it returns a valid new value, update `main_ui_palette` and rerun. Determine `locked` only from the existing Study Review lifecycle active state. An active study must keep the palette visible but disabled.

- [ ] **Step 4: Build the top bar and left rail hierarchy**

Replace the fixed brand header and top-level Manual/Live radio with:

- identity + `Study Workspace`;
- deck title and `Slide NN of NN`;
- lifecycle state, elapsed time, and Start/End action;
- lesson identity;
- segmented `One-turn / Dialogue / Realtime` flow control;
- segmented `Hold to speak / Hands-free` speaking control;
- camera/microphone enable control;
- attention source and answer-audio controls;
- palette control;
- participant/calibration summary;
- collapsed `Advanced voice settings` containing provider/engine diagnostics and confirmation policy.

Keep technical labels out of the always-visible shell.

- [ ] **Step 5: Replace the Slides popover with a right rail**

Refactor `_render_slide_selector` so it renders directly inside `st.container(key="main_slide_rail")` instead of `st.popover`. Preserve the existing thumbnail buttons, slide-number navigation, and active-slide scroll helper.

Add:

- `main_slide_rail_collapse_button` with visible label `×` and accessible help `Collapse slide deck`;
- `main_slide_rail_expand_button` with visible label `Slides` when collapsed;
- CSS fixed positioning below the top bar;
- an independently scrolling thumbnail list;
- a main-content right margin only while the rail is open.

Do not create a second slide selector.

- [ ] **Step 6: Compose the two-row Study Workspace**

Make `_render_slide_workspace` and the new unified interaction container siblings in the first row using `st.columns([1.0, 0.42], gap="medium")`. Render the Tutor answer in a separate full-width container below them.

Keep `main_slide_width_percent`, but default it to 70 and apply it inside the slide cell rather than centering the entire page. Preserve previous/next navigation, manual-region drawing, AOI overlay, geometry reporting, and slide loading.

- [ ] **Step 7: Update static/state tests**

Tests must assert:

- no `main_interaction_mode` default;
- no `main_interaction_mode` reference in `apps/streamlit_attentive_slides.py` or `modules/system/main_ui_state.py`;
- the media master is the sole gate for media service, polling, learner sensing, and TTS, independent of conversation flow;
- `main_interaction_flow == "one_turn"` and PTT default;
- default confirmation is Confidence-based auto at 0.80, with below-threshold evidence requiring confirmation;
- Ivory Study Desk and `main_slide_rail_expanded is True` defaults;
- no `options=["Manual", "Live"]` widget;
- visible flow labels and hidden advanced engine section;
- `_render_slide_selector` no longer uses `st.popover`;
- right-rail close/open keys exist;
- workspace creates slide/interaction columns and a lower answer container;
- slide width still clamps to 50–100 and defaults to 70.

- [ ] **Step 8: Run the checkpoint GREEN group**

Run:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_main_ui_state tests.test_main_ui_widget_inventory tests.test_slide_preview_canvas tests.test_main_ui_workspace_layout -v
```

Expected: all four modules pass.

- [ ] **Step 9: Commit**

```bash
git add apps/streamlit_attentive_slides.py modules/system/main_ui_state.py tests/test_main_ui_state.py tests/test_main_ui_widget_inventory.py tests/test_slide_preview_canvas.py tests/test_main_ui_workspace_layout.py
git commit -m "feat: redesign the AttentiveSlides workspace shell"
```

---

### Task 3: Unified Voice Panel, PTT `V`, Hands-free, and Automatic Answers

**Files:**
- Create: `modules/ui/voice_panel.py`
- Modify: `modules/ui/voice_control_component/__init__.py`
- Modify: `modules/ui/voice_control_component/index.html`
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `tests/test_voice_control_component.py`
- Modify: `tests/test_main_ui_widget_inventory.py`
- Create: `tests/test_main_ui_voice_layout.py`

**Interfaces:**
- Produces: `VoicePanelView` and `build_voice_panel_view`.
- Uses existing routes: `/attentive-voice/ptt/start`, `/attentive-voice/ptt/stop`, `/attentive-voice/continuous/start`, `/attentive-voice/continuous/stop`, and `/attentive-voice/events`.
- Passes `palette_tokens: Mapping[str, str]` into the voice custom-component iframe on every render.
- Produces app helpers: `_generate_confirmed_turn(view, resources)`, `_maybe_generate_confirmed_turn(view, resources)`, `_render_unified_interaction(view, resources)`, and `_render_unified_answer(view, resources)`.

- [ ] **Step 1: Add a pure voice presentation mapper**

Define:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class VoicePanelView:
    state: str
    title: str
    detail: str
    transcript: str
    target_label: str | None
    target_state: str
    busy: bool
    retryable: bool

def build_voice_panel_view(
    *,
    speech_mode: str,
    turn_phase: str,
    transcript: str,
    target_label: str | None,
    target_needs_confirmation: bool,
    error_code: str | None = None,
) -> VoicePanelView:
    phase = str(turn_phase or "").strip().lower()
    copy = {
        "ready": ("Ready", "Hold V or the button to speak"),
        "listening": ("Listening for speech", "Hands-free input is active"),
        "paused": ("Listening paused", "Resume when you are ready"),
        "sampling": ("Recording", "Sampling attention"),
        "transcribing": ("Transcribing", "Preparing your question"),
        "resolving": ("Resolving target", "Matching gaze evidence to this slide"),
        "confirmation": ("Target needs confirmation", "Choose the intended region"),
        "answering": ("Answering", "Generating a grounded explanation"),
        "playing": ("Tutor speaking", "You can interrupt in Realtime"),
    }
    if error_code:
        title, detail = "Voice input needs attention", str(error_code)
        phase = "error"
    else:
        title, detail = copy.get(phase, ("Preparing voice", "Connecting the current input mode"))
    target_state = (
        "needs_confirmation"
        if target_needs_confirmation
        else "locked"
        if target_label
        else "sampling"
        if phase == "sampling"
        else "waiting"
    )
    return VoicePanelView(
        state=phase or "preparing",
        title=title,
        detail=detail,
        transcript=" ".join(str(transcript or "").split()),
        target_label=target_label,
        target_state=target_state,
        busy=phase in {"sampling", "transcribing", "resolving", "answering", "playing"},
        retryable=error_code in {"too_short", "empty_transcript", "stt_failed"},
    )
```

Implement exact learner-facing mappings for Ready, Listening, Recording/Sampling attention, Transcribing, Resolving target, Target needs confirmation, Target locked, Answering, Playing, retryable STT errors, and transport errors. Unknown runtime values map to a calm `Preparing voice` state rather than exposing raw provider text.

- [ ] **Step 2: Redesign the voice transport component**

Keep the existing single media source, WebSocket, PCM forwarding, playback queue, target-switch commands, and same-origin routes. Replace the component's visual hierarchy with:

- status title/detail;
- compact audio meter;
- PTT button with visible `V` keycap;
- Hands-free `Pause listening` / `Resume listening` button;
- a small retry/status message;
- no Tutor-answer block;
- no engine/provider labels.

The component height must fit the right interaction panel without becoming a second card stack.

Extend the Python wrapper to require the current `palette_semantic(...)` mapping. In JavaScript, `applyPalette(paletteTokens)` must accept only the 16 registered semantic keys and set the corresponding `--as-*` properties on the iframe root before rendering. Do not assume parent CSS custom properties cross the iframe boundary, and do not introduce fixed palette colors in the transport markup.

- [ ] **Step 3: Implement the global `V` hold shortcut**

Install key listeners on `window.parent.document` when same-origin access succeeds, otherwise on `document`. Use:

```javascript
function shouldIgnoreShortcut(event) {
  const target = event.target;
  const editing = target && (
    target.matches?.("input, textarea, select, [contenteditable='true']") ||
    target.closest?.("[role='dialog'], [role='menu'], .palette-control")
  );
  return editing || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey;
}
```

For `event.code === "KeyV"` in PTT mode:

- ignore `event.repeat`;
- keydown calls the same `startPtt` path as pointerdown;
- keyup calls the same `stopPtt` path as pointerup;
- maintain one `keyboardPttActive` boolean;
- call safe stop on `blur`, `visibilitychange` when hidden, `pagehide`, and component teardown;
- remove every parent-document listener during teardown;
- never trigger while Hands-free is selected.

- [ ] **Step 4: Add Hands-free pause/resume**

Preserve automatic `/continuous/start` on a new active session. A local pause button calls `/continuous/stop`, displays `Listening paused`, and prevents automatic restart until the same button calls `/continuous/start`. A mode/session signature change clears the local paused state. Page teardown still stops continuous capture with keepalive semantics.

- [ ] **Step 5: Extract answer generation from the removed button**

Move the body of the current `_render_tutor_generation_panel` click branch into `_generate_confirmed_turn(view, resources)`. It must preserve:

- `assess_tutor_generation` gates;
- cloud permission and API checks;
- existing GroundedTutorAgent configuration;
- bounded conversation history only when flow is Dialogue;
- session payload fields;
- exactly-once interaction logging;
- TTS behavior;
- error retention and retry behavior.

Implement `_maybe_generate_confirmed_turn` with the existing interaction-ID gate. Call it after automatic confirmation and after explicit target confirmation. Remove `main_generate_answer_button` and the `Generate grounded answer` widget.

Typed input receives a compact `Ask tutor` action because text has no speech-end event; this is the only explicit submit action.

- [ ] **Step 6: Render every flow through one panel and one answer region**

Replace the three-equal-column One-turn and Omni trees with `_render_unified_interaction` in the top-right panel and `_render_unified_answer` below the slide row.

- One-turn reads the current proposal/transcript and clears history context.
- Dialogue reads the same proposal/transcript and supplies existing bounded history.
- Realtime reads `resources.voice.snapshot()` for transcript, target, answer text, pending switch, and runtime state.
- Target correction appears inline in the same panel.
- Tutor output, replay/TTS, follow-up, uncertainty, and retry appear only in the lower answer region.

Delete obsolete learner-facing headings `1. Live target`, `2. Live command`, `3. Tutor answer`, `2. Realtime dialogue`, and `3. Realtime answer` after the unified route is active.

- [ ] **Step 7: Add focused voice/UI tests**

Tests must cover:

- state-to-copy mappings for both speaking controls;
- unknown/error states;
- `KeyV`, repeat/modifier/focus guards, parent-document listener, and teardown removal;
- pointer and keyboard paths call the same PTT commands;
- blur/hidden/pagehide safe stop;
- Hands-free pause/resume routes;
- no second `getUserMedia`;
- no Tutor answer or provider label in the transport component;
- voice iframe receives the complete palette token map and applies only whitelisted keys;
- no `main_generate_answer_button`;
- automatic generation is interaction-ID gated;
- the default 0.80 confidence policy auto-generates for valid high-confidence AOIs and pauses for missing/invalid/below-threshold AOIs;
- one unified interaction render and one lower answer render for all flows.

- [ ] **Step 8: Run the checkpoint GREEN group**

Run:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_voice_control_component tests.test_voice_orchestrator tests.test_main_ui_widget_inventory tests.test_main_ui_voice_layout -v
```

Expected: all four modules pass.

- [ ] **Step 9: Commit**

```bash
git add modules/ui/voice_panel.py modules/ui/voice_control_component apps/streamlit_attentive_slides.py tests/test_voice_control_component.py tests/test_main_ui_widget_inventory.py tests/test_main_ui_voice_layout.py
git commit -m "feat: unify AttentiveSlides voice interactions"
```

---

### Task 4: Turn-boundary AOI Copy and Low-salience Gaze Cursor

**Files:**
- Modify: `modules/ui/slide_viewport_component/__init__.py`
- Modify: `modules/ui/slide_viewport_component/index.html`
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `tests/test_slide_preview_canvas.py`

**Interfaces:**
- Preserves: `TurnContextCollector.freeze_start`, `freeze_end`, `aggregate`, point-gaze aggregation, gaze debug channel, and the 1000 ms stale timeout.
- Changes presentation only: gaze cursor CSS, iframe chrome tokens, and turn-state wording.

- [ ] **Step 1: Bridge palette tokens to viewport chrome**

Pass the current complete `palette_semantic(...)` mapping through the slide-viewport Python wrapper. Apply only the 16 whitelisted `--as-*` variables to the iframe root, and use them only for themeable viewport chrome. Do not derive the live gaze cursor, AOI candidate/confirmed states, alerts, or heatmap colors from these tokens.

- [ ] **Step 2: Replace the strong blue gaze-dot styling**

Use exactly:

```css
.gaze-dot {
  position: absolute;
  width: 10px;
  height: 10px;
  margin: -5px 0 0 -5px;
  border: 1px solid rgba(72, 84, 78, 0.18);
  border-radius: 999px;
  background: rgba(72, 84, 78, 0.16);
  box-shadow: 0 0 8px 5px rgba(72, 84, 78, 0.08);
  display: none;
  z-index: 20;
  pointer-events: none;
}
```

Remove `#2563eb`, the white border, the dark shadow, and every gaze-dot animation/transition. Do not change coordinate transforms, preview candidate selection, BroadcastChannel messages, or `GAZE_STALE_AFTER_MS = 1000`.

- [ ] **Step 3: Align visible AOI wording with actual turn boundaries**

During active PTT or detected speech, render `Sampling attention`; do not render `Target locked`. After the proposal/Omni gaze window resolves, render `Target locked` only for a valid resolved target. Render `Target needs confirmation` for insufficient evidence and reuse the existing candidate/whole-slide/manual correction paths.

Do not change the existing 0.5-second lookback, 0.15-second minimum dwell, 0.5-second sample dwell cap, local point-gaze preference, or confidence weighting.

- [ ] **Step 4: Extend static contracts**

Add assertions for:

- 10 px size;
- exact transparent neutral fill/border/shadow;
- no blue literal in `.gaze-dot`;
- no white border or dark drop shadow;
- no gaze-dot animation/transition;
- pointer-events none;
- 1000 ms stale clear retained;
- learner-facing Sampling/Locked/Needs confirmation copy.
- complete palette-token input is applied only to iframe chrome while gaze/AOI literals remain invariant.

- [ ] **Step 5: Run the checkpoint GREEN group**

Run:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_turn_context tests.test_point_gaze tests.test_slide_preview_canvas -v
```

Expected: all AOI aggregation tests remain green and the viewport contract passes.

- [ ] **Step 6: Commit**

```bash
git add modules/ui/slide_viewport_component/__init__.py modules/ui/slide_viewport_component/index.html apps/streamlit_attentive_slides.py tests/test_slide_preview_canvas.py
git commit -m "style: reduce live gaze cursor salience"
```

---

### Task 5: Review Summary, Learner-state Overview, and Slide Detail

**Files:**
- Create: `modules/ui/review_view.py`
- Modify: `apps/streamlit_attentive_slides.py`
- Create: `tests/test_review_view.py`
- Create: `tests/test_main_ui_review_layout.py`
- Modify: `tests/test_main_ui_widget_inventory.py`

**Interfaces:**
- Consumes: `StudyReviewSession`, `LearnerStateReviewSummary`, `SlideLearnerStateSummary`, and existing gaze-review slide contracts.
- Produces: `ReviewSessionView`, `ReviewSlideRowView`, `ReviewAoiDwellView`, `ReviewSlideDetailView`, and `build_review_view(review: StudyReviewSession)`.

- [ ] **Step 1: Add pure Review presentation contracts**

Define:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ReviewMetric:
    label: str
    value: str
    detail: str = ""

@dataclass(frozen=True)
class ReviewSlideRowView:
    slide_id: int
    study_time: str
    interaction_count: int
    engagement: str
    fatigue: str
    top_emotion: str

@dataclass(frozen=True)
class ReviewAoiDwellView:
    aoi_id: str
    label: str
    dwell_seconds: str

@dataclass(frozen=True)
class ReviewSlideDetailView:
    slide_id: int
    study_time: str
    interaction_count: int
    engagement: str
    fatigue: str
    top_emotion_label: str
    top_emotion_probability: str
    distraction_alert_duration: str
    distraction_alert_count: int | None
    fatigue_alert_duration: str
    fatigue_alert_count: int | None
    learner_coverage: str
    valid_gaze_duration: str
    gaze_coverage: str
    aoi_dwell: tuple[ReviewAoiDwellView, ...]

@dataclass(frozen=True)
class ReviewSessionView:
    summary: tuple[ReviewMetric, ...]
    emotion_distribution: tuple[ReviewMetric, ...]
    slide_rows: tuple[ReviewSlideRowView, ...]
    slide_details: dict[int, ReviewSlideDetailView]
```

`build_review_view(review: StudyReviewSession)` must join `review.learner_state_summary.slides` and `review.gaze_review.slides` by slide ID, rather than making the Streamlit renderer repeat metric ownership or calculations. It must format missing probabilities as `Unavailable`, calculate learner coverage as `sum(observed_seconds) / study_seconds` when study time is positive, preserve the official eight emotion labels/order, expose slide-level top-emotion probability, alert duration/count, valid gaze duration, gaze coverage, and AOI dwell from their owning stored contracts, and never replace missing observation with zero.

- [ ] **Step 2: Build the Review top hierarchy**

Render in this order:

1. Review top bar and session identity.
2. Session Summary inline metric band: Study duration, interactions, mean engagement, mean fatigue, top emotion, learner coverage.
3. Learner State Overview: eight emotion values, distraction alert duration/count, fatigue alert duration/count, and slide-order overview rows.
4. Selected-slide area: heatmap slide left and slide detail/AOI dwell right.
5. Heatmap and JSON export actions in their existing contextual rails.

Use one continuous Review page with border/rule hierarchy, not a grid of unrelated cards.

- [ ] **Step 3: Preserve current Review behavior**

Keep:

- prior-session selection;
- invalid saved-session warnings;
- JSON download;
- delete confirmation;
- deck mismatch handling;
- heatmap toggle;
- heatmap PNG export;
- valid gaze duration, gaze coverage, and AOI dwell;
- slide thumbnails and navigation in the right rail;
- `Model estimates, not a diagnosis.`

Do not add Q&A transcript persistence, a raw learner-state timeline, interpolated values, or a chart dependency. The slide-order overview is the only timeline-like learner-state presentation in this scope.

- [ ] **Step 4: Add focused Review tests**

`tests/test_review_view.py` must cover:

- session weighted engagement/fatigue values;
- top emotion and all eight emotion probabilities;
- study duration and interaction total;
- learner coverage;
- alert duration/count;
- slide-detail top-emotion probability, alert duration/count, valid gaze duration, gaze coverage, and AOI dwell;
- learner and gaze slide summaries are joined by slide ID through `StudyReviewSession`;
- slide ordering;
- unavailable values when modality coverage is zero.

`tests/test_main_ui_review_layout.py` must statically assert the rendering order and visible section names, plus the absence of a second-by-second learner-state chart and transcript-history section.

Update widget inventory only for keys that actually changed in the new Review shell.

- [ ] **Step 5: Run the checkpoint GREEN group**

Run:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_review_view tests.test_study_review_store tests.test_main_ui_review_layout tests.test_main_ui_widget_inventory -v
```

Expected: all four modules pass.

- [ ] **Step 6: Commit**

```bash
git add modules/ui/review_view.py apps/streamlit_attentive_slides.py tests/test_review_view.py tests/test_main_ui_review_layout.py tests/test_main_ui_widget_inventory.py
git commit -m "feat: redesign the AttentiveSlides review workspace"
```

---

### Task 6: Whole-change Review, Bounded Fixes, and Final Verification

**Files:**
- Review every file changed by Tasks 1–5.
- Modify only files required by Critical or Important findings.

**Interfaces:**
- Produces: one reviewed, fully verified UI change ready for the user's manual Lenovo acceptance.

- [ ] **Step 1: Inspect the complete diff and execution ledger**

Confirm each checkpoint has exactly one focused GREEN result and one intentional commit. Review the cumulative diff against every acceptance criterion in the design spec.

- [ ] **Step 2: Run one independent whole-change review**

Use one review subagent only. Ask it to inspect the complete diff for:

- design-spec gaps;
- stale Manual/Live or three-column mode-specific UI;
- palette leakage/hardcoded component colors;
- keyboard listener leaks or unsafe PTT stop behavior;
- accidental backend/VAD/gaze aggregation changes;
- automatic-generation duplicate calls;
- Review values that convert missing data to zero;
- Streamlit widget-key collisions;
- accessibility regressions;
- scope expansion into architecture or analytics.

Do not assign per-checkpoint reviewers.

- [ ] **Step 3: Apply one bounded fix wave if required**

Fix only Critical or Important findings. Run only the directly affected focused modules after fixes. If the independent review has no such finding, make no review-only code change.

- [ ] **Step 4: Run the complete unit suite once**

Run:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest discover -s tests -v
```

Expected: the complete suite passes.

If the bounded review fix wave occurred after an earlier full-suite run, rerun the full suite at most once. Do not repeat a passing full suite for commits or handoff.

- [ ] **Step 5: Commit review fixes if any**

The bounded fix wave must modify tracked files only. Commit them with:

```bash
git commit -am "fix: address AttentiveSlides UI review findings"
```

Skip this commit when the review produced no code changes.

- [ ] **Step 6: Hand off manual visual acceptance**

Report the focused GREEN evidence, independent-review result, full-suite result, branch, and commits. Ask the user to verify on Lenovo at the target display:

- Ivory Study Desk default and all four palette switches while Study is inactive;
- palette lock during an active Study;
- 70% slide scale and fixed right rail;
- One-turn, Dialogue, and Realtime stable layout;
- pointer PTT and hold/release `V`;
- Hands-free start, pause, resume, speech end, and Realtime interruption;
- Sampling attention → Target locked/confirmation transitions;
- low-salience gaze cursor;
- automatic answer without Generate button;
- Review summary, learner-state overview, heatmap, AOI dwell, and slide detail.

Do not push or merge until the user accepts the result and explicitly requests integration.
