# AttentiveSlides 02 UI Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Do not dispatch subagents unless the user explicitly asks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the user's ten follow-up refinements to the implemented 02-aligned Study workspace, remove every user-visible mock-deck artifact, restore symmetric collapsible side rails, refine typography and spacing, keep the slide centered at reduced scale, move learner alerts into the top bar, and preserve the low-salience live gaze indicator.

**Architecture:** Keep the existing Streamlit application and custom-component boundaries. Use keyed Streamlit containers plus `body:has(...)` CSS for the left and right drawer states, replace the production mock fallback with a neutral one-slide `AttentiveSlides Deck` empty-state manifest, and keep all slide/AOI/gaze coordinate logic inside the existing slide viewport and capture components. This is a focused presentation and shell-behavior pass; it must not alter voice-mode semantics, AOI aggregation, Review data, or backend architecture.

**Tech Stack:** Python 3.11, Streamlit, keyed Streamlit containers, local HTML/CSS/JavaScript custom components, existing Literata and IBM Plex Sans assets.

## Authority and starting point

- Target host: `LenovoLinux_Dorm`.
- Repository: `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration`.
- Branch: `codex/gaze-heatmap-review`.
- Expected starting `HEAD`: `fe65cf1 fix: address AttentiveSlides 02 alignment review` plus this plan commit.
- Existing visual specification: `docs/superpowers/specs/2026-07-17-attentiveslides-02-aligned-ui-design.md`.
- Canonical visual reference: `docs/superpowers/specs/references/02-cool-instrument-panel.html` and `docs/superpowers/specs/references/attentiveslides-concepts.css`.
- This follow-up plan overrides the earlier specification only where the user's July 18 feedback is explicit:
  - the left settings rail must now collapse and reopen;
  - a reduced slide is centered within its own stage rather than left-aligned;
  - the right rail is named `SLIDES INDEX`, not `DECK INDEX`;
  - learner-state alerts move from the slide toolbar to the top bar;
  - the Control header no longer carries a right-side status badge.
- Work directly on the current branch. Do not merge, rebase, push, or modify `main`.

## Global constraints

- Light mode only; primary target is the Lenovo 4060 demo at an effective viewport near `1600×1000`.
- Preserve the four existing palettes and the default `Ivory Study Desk` preference.
- Preserve Literata for editorial/serif roles and IBM Plex Sans for operational/sans-serif roles.
- Do not introduce glassmorphism, backdrop blur, gradients, a UI framework, remote font assets, or a mobile layout.
- Do not change One-turn, Dialogue, or Realtime behavior in this pass.
- Do not change PTT, Hands-free, `V`, Pause/Resume, AOI selection, gaze aggregation, coordinate mapping, Tutor generation, Review data, or learner-state calculations.
- “Remove mock” means the production Study UI no longer loads or exposes `data/mock_deck`, `Mock AttentiveSlides Deck`, `mock_deck`, fake SHAP lesson content, or mock thumbnails. Keep the old `data/mock_deck` directory only as a legacy backend/test fixture because deleting every unrelated fixture consumer is outside this UI pass; the main app must no longer reference it.
- No test files are modified. Per the user's explicit instruction, do not run unit tests, full suites, lint, type checks, browser automation, or visual acceptance after implementation.
- After the edit and commit, restart the existing single-port demo service directly. A process/port check is allowed only to confirm the requested restart completed; it is not an application test.

## Current behavior that explains the requested changes

- `main()` always resolves `data/mock_deck/mock_aoi_manifest.json` when no PDF is uploaded. `_render_live_controls()` currently exposes both its title (`Mock AttentiveSlides Deck`) and ID (`mock_deck`), and `_render_header()` repeats the title.
- `_render_upload_controls()` is called after normal runtime and system controls, so the `DECK` expander appears at the bottom of the left rail.
- The fixed right rail already collapses, but its labels are `DECK INDEX` / `DECK / nn` and its reopen button reads `DECK`.
- The slide viewport uses `margin-inline: 0 auto`, and the built-in placeholder uses a left-only width wrapper, so reduced slides remain attached to the left edge.
- `_render_learner_state_alert_periodic()` is rendered inside the toolbar's Learner State column, so an alert adds height and moves the entire slide region.
- `.as-status-badge` appears at the right of both Control and Tutor Output headings. The user wants to retain `WAITING`/`READY` for Tutor Output, but remove the Control badge.
- The gaze dot still exists in `modules/ui/slide_viewport_component/index.html`. It is hidden until `modules/media/live_capture_component/index.html` publishes a valid `kind: "gaze"` message. The capture component connects to `ws://127.0.0.1:8001/ws/predict_gaze`; therefore a Mac SSH tunnel that forwards only 8501 cannot display remote EyeTheia gaze predictions.

## File map

**Modify**

- `apps/streamlit_attentive_slides.py`
  - reorder the `DECK` expander;
  - suppress mock title/ID in learner-facing contexts;
  - add left-rail drawer state and controls;
  - rename and refine the right rail;
  - relocate the learner alert;
  - remove the Control badge and empty Tutor instruction;
  - keep the branded empty slide but separate its title/tagline.
- `modules/system/main_ui_state.py`
  - add the default `main_left_rail_expanded = True` UI state.
- `modules/ui/workspace.css`
  - style symmetric rail close/reopen controls and shell offsets;
  - remove the dark study-shell underlay;
  - align toolbar popovers and top-bar alert;
  - enforce the requested button typography and compact Reset Turn geometry;
  - separate the branded empty-state title/tagline.
- `modules/ui/palette_control_component/index.html`
  - use smaller Literata labels and slightly rounder palette buttons.
- `modules/ui/slide_viewport_component/index.html`
  - center the slide at all widths below 100% without changing its coordinate system.

**Create**

- `data/attentiveslides_deck/manifest.json`
  - neutral one-slide production empty-state deck with ID `attentiveslides_deck`, title `AttentiveSlides Deck`, no image, no lesson/SHAP text, and only the canonical `whole_slide` AOI.

**Do not modify**

- files under `tests/`;
- `modules/system/point_gaze.py`, `modules/system/turn_context.py`, or any gaze/AOI calculation code;
- Review contracts/store/data rendering;
- voice orchestrator, speech detector, or provider clients;
- palette semantic color values;
- the existing `.gaze-dot` size, opacity, blur, stale timer, or coordinate mapping.

---

### Task 1: Remove the production mock fallback and move `DECK` to the top

**Files:**

- Modify: `apps/streamlit_attentive_slides.py` (`main`, `_render_live_controls`, `_render_header`, `_render_sidebar_status`, `_render_upload_controls`)
- Create: `data/attentiveslides_deck/manifest.json`

**Interfaces:**

- Consumes: `st.session_state["main_uploaded_deck_id"]` as the authoritative distinction between the neutral empty-state deck and a user-uploaded PDF.
- Produces: `BUILT_IN_MANIFEST_PATH = REPOSITORY_ROOT / "data" / "attentiveslides_deck" / "manifest.json"` and one `_has_uploaded_deck() -> bool` presentation helper.

- [ ] **Step 1: Replace the main app's production fallback manifest**

  Create `data/attentiveslides_deck/manifest.json` with exactly one neutral slide:

  - `deck_id`: `attentiveslides_deck`;
  - `title`: `AttentiveSlides Deck`;
  - `slide_id`: `1`;
  - no `slide_image_path`;
  - empty `ocr_text` and `neighbor_slide_text`;
  - one `whole_slide` AOI covering `[0.0, 0.0, 1.0, 1.0]`, with neutral name/text and no fake lesson content.

  Use this exact payload:

  ```json
  {
    "deck_id": "attentiveslides_deck",
    "title": "AttentiveSlides Deck",
    "slides": [
      {
        "slide_id": 1,
        "ocr_text": "",
        "neighbor_slide_text": "",
        "aois": [
          {
            "aoi_id": "whole_slide",
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "type": "slide",
            "name": "Whole slide",
            "text": ""
          }
        ]
      }
    ]
  }
  ```

  Point `BUILT_IN_MANIFEST_PATH` in `apps/streamlit_attentive_slides.py` to this new manifest. Change the built-in-placeholder condition from `view.deck_id == "mock_deck"` to `view.deck_id == "attentiveslides_deck"`.

  Do not edit `modules/tutor/context_retriever.py`, `modules/system/adapters.py`, or the legacy `data/mock_deck` fixture in this UI-only pass. The production Streamlit app must have no remaining path reference to `data/mock_deck`.

- [ ] **Step 2: Define the display contract for an unloaded workspace**

  Implement a small pure presentation decision in `apps/streamlit_attentive_slides.py`:

  ```python
  def _has_uploaded_deck() -> bool:
      return bool(st.session_state.get("main_uploaded_deck_id"))
  ```

  - uploaded PDF: show the real `view.deck_title`, current/total slide position, and real deck details where appropriate;
  - no uploaded PDF: left lesson area shows only `AttentiveSlides Deck`; it shows neither `LESSON / 05` nor `mock_deck`;
  - no uploaded PDF: the top bar keeps `STUDY / WORKSPACE` and its numeric slide context, but omits `Mock AttentiveSlides Deck` entirely;
  - no uploaded PDF: `SYSTEM & PRIVACY > Active deck` renders exactly `No PDF loaded` and no ID;
  - no uploaded PDF: `START STUDY` remains disabled because a branded empty-state deck is not a study deck.

  Do not replace the mock wording with fake lesson metadata. Do not display the internal SHAP text or AOI names.

- [ ] **Step 3: Render the upload expander before runtime controls**

  In `main()`, move `_render_upload_controls(workspace, disabled=...)` so it is the first normal control after `_render_sidebar_brand()` and before `_render_live_controls(...)` and `_render_sidebar_status(...)`.

  Preserve the existing study mutation gating. Set the `DECK` expander to:

  - expanded when no PDF has been uploaded, so the empty workspace exposes its only setup action;
  - collapsed after a PDF is loaded, so the working study rail remains compact.

  The visible order must begin:

  1. fixed AttentiveSlides brand cell;
  2. `DECK` upload expander;
  3. `AttentiveSlides Deck` or the real uploaded deck title;
  4. runtime configuration.

- [ ] **Step 4: Keep the empty slide branded without presenting it as a mock lesson**

  Retain `_render_builtin_slide_placeholder()` as the empty workspace canvas because the user explicitly wants the two branded lines adjusted. Ensure this placeholder is the only slide content when no PDF is loaded. Do not surface the internal manifest title, deck ID, SHAP copy, thumbnail content, or AOI labels.

- [ ] **Step 5: Inspect only the resulting diff for scope**

  Confirm by code inspection that the normal UI has no direct rendering of `Mock AttentiveSlides Deck` or `mock_deck`. Do not run tests.

---

### Task 2: Restore the left settings drawer and make both rails symmetric

**Files:**

- Modify: `modules/system/main_ui_state.py`
- Modify: `apps/streamlit_attentive_slides.py` (`_render_sidebar_brand`, new left-rail state callbacks/reopen renderer, `main`)
- Modify: `modules/ui/workspace.css`

**Interfaces:**

- Produces: `st.session_state["main_left_rail_expanded"]: bool`, defaulting to `True`.
- Produces: `_set_left_rail_expanded(expanded: bool) -> None`.
- Mirrors: the existing `main_slide_rail_expanded` / `_set_slide_rail_expanded` right-rail pattern.

- [ ] **Step 1: Add stable left-rail UI state**

  Add `"main_left_rail_expanded": True` to the main UI defaults in `modules/system/main_ui_state.py`. This is a presentation preference only and must not reset deck, conversation, media, or study lifecycle state.

  Add the callback beside `_set_slide_rail_expanded`:

  ```python
  def _set_left_rail_expanded(expanded: bool) -> None:
      st.session_state["main_left_rail_expanded"] = bool(expanded)
  ```

- [ ] **Step 2: Put the collapse button in the brand cell's upper-right**

  Refactor `_render_sidebar_brand()` to render the A mark/title on the left and a compact icon-only `×` collapse control at the far right of the fixed 52 px brand cell. Use accessible help `Collapse settings`.

- [ ] **Step 3: Add the collapsed reopen control**

  When `main_left_rail_expanded` is false, render one fixed left-edge reopen tab below the top bar. It shows only `»`, with accessible help `Open settings`. Do not render a floating `DECK` text button.

- [ ] **Step 4: Collapse the native Streamlit sidebar as an app drawer**

  In `workspace.css`, use the presence of the keyed reopen container to:

  - move/hide the 226 px native sidebar without destroying its widget state;
  - change the central `.st-key-main_topbar` left edge from `226px` to `0`;
  - let `.block-container` use the reclaimed width;
  - keep the reopen tab above the workspace and below the fixed top bar;
  - use a 180 ms transform/opacity transition that does not reflow or jitter;
  - preserve a visible focus ring and an adequate click target even though the chevron glyph is small.

  The open state remains the default on every fresh session.

- [ ] **Step 5: Rename and refine the right rail**

  In `_render_slide_selector()`:

  - replace `DECK INDEX` with `SLIDES INDEX`;
  - keep the header counter in the form `{active:02d} / {total:02d}`;
  - replace `DECK / {total:02d}` with `SLIDES / {total:02d}`;
  - retain the compact `×` close button at the upper-right;
  - replace the collapsed `DECK` button with an icon-only `«` reopen button and help `Open slides index`.

  Preserve the fixed right edge, independent thumbnail scroll, selected-slide outline, and existing slide navigation callbacks.

- [ ] **Step 6: Make the two rails visually related**

  Give both close/reopen controls the same font family, border weight, background token, focus treatment, and 2–4 px geometry. The left rail opens toward the right; the right rail opens toward the left. Do not use large text labels on either collapsed tab.

---

### Task 3: Center reduced slides, repair the empty canvas, and remove the dark shell ring

**Files:**

- Modify: `modules/ui/slide_viewport_component/index.html`
- Modify: `apps/streamlit_attentive_slides.py` (`_left_aligned_slide_width` or its replacement, `_render_builtin_slide_placeholder`, static fallback path only as needed)
- Modify: `modules/ui/workspace.css`

**Interfaces:**

- Preserves: `display_width_percent`, `layout_revision`, viewport geometry reporting, AOI boxes, manual selection, gaze mapping, and slide image aspect ratio.
- Produces: centered presentation for 50–100% slide widths.

- [ ] **Step 1: Center the custom slide viewport**

  Change `#slide` in `modules/ui/slide_viewport_component/index.html` from left attachment (`margin-inline: 0 auto`) to horizontal centering (`margin-inline: auto`). Do not change `slide.style.width`, the overlay's `inset: 0`, image dimensions, reported frame geometry, or pointer-coordinate calculations.

- [ ] **Step 2: Center non-component and empty-state fallbacks**

  Rename `_left_aligned_slide_width()` to `_centered_slide_width()`. For widths below 100, render three no-gap columns with ratios `[(100 - width) / 2, width, (100 - width) / 2]` and yield the middle column; for 100, yield directly. Use it for the built-in placeholder and static fallback so both occupy the same centered horizontal position as the custom component.

- [ ] **Step 3: Separate the two branded empty-state lines**

  Keep:

  - `AttentiveSlides` as the large serif title;
  - `Select a slide region, state your learning goal, and receive a grounded tutor response.` as the supporting serif line.

  Set a 32 px flex/grid gap between the two rows so they cannot overlap. This moves the title slightly upward and the supporting line slightly downward without absolute positioning. Preserve centering and the 16:9 stage.

- [ ] **Step 4: Remove the dark underlay/ring around the three study modules**

  The visible outer plane beneath Slide, Control, and Tutor Output must match the page canvas without a darker band around the bottom or perimeter. In `workspace.css`:

  - set `.st-key-main_study_shell { background: transparent; }`;
  - remove any redundant shell padding/margin that exposes a darker workspace strip;
  - preserve the individual white/ivory Slide surface, Control border, and Tutor Output border;
  - do not flatten the distinct right/left rails or remove the slide-only shadow.

---

### Task 4: Refine Palette and operational button typography

**Files:**

- Modify: `modules/ui/palette_control_component/index.html`
- Modify: `modules/ui/workspace.css`

**Interfaces:**

- Preserves: palette IDs, colors, localStorage key, active/paused lock, selection callbacks, and accessible `aria-pressed` state.

- [ ] **Step 1: Make Palette labels small and serif**

  In the Palette iframe:

  - use `Literata`, then the existing serif fallbacks, for palette button copy;
  - reduce label size from the current 12 px to 11 px with a 15 px line height;
  - use a 6 px radius on each palette button;
  - keep swatches, selection border, disabled state, focus ring, and full-width click area;
  - do not make the buttons pill-shaped.

- [ ] **Step 2: Normalize lifecycle and Tutor action buttons**

  Apply IBM Plex Sans, uppercase transformation, 700 weight, and `0.05em` letter spacing to:

  - `PAUSE` / `RESUME`;
  - `START STUDY` / `END & REVIEW` / `BACK TO STUDY` / `RETRY REVIEW`;
  - `RESET TURN` and any actions in the same Tutor Output action group.

  These labels must remain all-caps sans-serif even though panel headings and Tutor prose remain Literata.

- [ ] **Step 3: Match `RESET TURN` to the `WAITING` badge height**

  Introduce `--as-compact-status-height: 22px` and apply it to `.as-status-badge` and `.st-key-main_reset_turn_button button`. Reduce Reset Turn padding and width so it reads as a small instrument action rather than a normal CTA. Keep the hit area usable on the desktop target and preserve the disabled/focus states.

- [ ] **Step 4: Remove the empty Tutor instruction**

  In `_render_tutor_result()`, when there is no Tutor result, return without rendering `Ask a question to receive a grounded explanation.` Do not replace it with another instructional sentence. Preserve the Tutor Output header and its `WAITING` state.

---

### Task 5: Stabilize the slide toolbar and move learner alerts into the top bar

**Files:**

- Modify: `apps/streamlit_attentive_slides.py` (`_render_header`, `_render_slide_workspace`, `_render_learner_state_alert_periodic` placement)
- Modify: `modules/ui/workspace.css`

**Interfaces:**

- Preserves: `_learner_state_view()`, one-second fragment refresh, popover contents, dismiss action, alert strings, and lifecycle controls.
- Produces: a no-wrap top-bar alert slot that does not affect slide-toolbar height.

- [ ] **Step 1: Remove the alert from the slide toolbar**

  In `_render_slide_workspace()`, remove `main_learner_state_reminder_slot` and the `_render_learner_state_alert_periodic(...)` call from the Learner State column. Keep the Learner State popover in the toolbar.

- [ ] **Step 2: Align Learner State with Slide tools**

  Adjust the toolbar column alignment and keyed popover button CSS so `Learner State` and `Slide tools` share the same top edge, minimum height, padding, and baseline. Neither popover may create a second toolbar row.

- [ ] **Step 3: Add a dedicated top-bar alert slot**

  Refactor `_render_header()` into five stable columns in Study mode:

  1. workspace/deck/slide context;
  2. learner alert slot;
  3. lifecycle status/timer;
  4. Pause/Resume slot;
  5. Start Study or End & Review action.

  Use `[0.34, 0.28, 0.14, 0.09, 0.15]` at the effective 1600 px viewport. Review mode leaves the alert slot empty while retaining stable lifecycle/action alignment.

- [ ] **Step 4: Guarantee that the alert never wraps or reflows the shell**

  Style `.attentive-learner-alert` in the top bar as one compact inline strip:

  - `white-space: nowrap`;
  - `overflow: hidden`;
  - `text-overflow: ellipsis` if the available width becomes too small;
  - 10 px IBM Plex Sans type;
  - a single border/background treatment using palette tokens;
  - fixed 28 px height aligned with the lifecycle controls;
  - no change to top-bar height when the alert appears or disappears.

  `Attention appears distracted — return to the slide when ready.` must remain on one line at the target viewport.

---

### Task 6: Simplify the Control header without changing voice behavior

**Files:**

- Modify: `apps/streamlit_attentive_slides.py` (`_render_unified_interaction`)
- Modify: `modules/ui/workspace.css` only if header alignment needs a selector adjustment after badge removal

**Interfaces:**

- Preserves: `VoicePanelView`, state block, media controls, typed input, target source, listening behavior, PTT/Hands-free actions, and error handling.

- [ ] **Step 1: Remove only the Control header's right-side status badge**

  Remove the `<span class="as-status-badge">...</span>` from the `1 CONTROL` header. This eliminates user-visible header badges such as `STUDY PAUSED` or `OFF`. Keep the circled `1`, `CONTROL`, and accessible heading label.

- [ ] **Step 2: Keep meaningful state in the primary state block**

  Do not remove the existing primary state block below the header. It may still communicate `Study paused`, readiness, target state, listening, transcribing, or an actionable error because those are part of the panel's main hierarchy rather than a redundant upper-right badge.

- [ ] **Step 3: Leave the Tutor Output badge intact**

  `WAITING` / `READY` remains visible in the Tutor Output header and is the height reference for `RESET TURN`.

---

### Task 7: Preserve and restore the live gaze position indicator in the Mac demo path

**Files:**

- No production code change is required unless implementation inspection reveals that a preceding UI edit accidentally suppresses the viewport or capture component.
- Preserve: `modules/ui/slide_viewport_component/index.html` `.gaze-dot` and `handleGazeMessage()`.
- Preserve: `modules/media/live_capture_component/index.html` EyeTheia gaze publication.

**Interfaces:**

- Consumes: EyeTheia WebSocket at `ws://127.0.0.1:8001/ws/predict_gaze` from the browser's point of view.
- Produces: a low-salience 10 px blurred gaze dot on the slide for fresh valid predictions; the dot clears after 1000 ms without a valid sample.

- [ ] **Step 1: Do not restyle or remove the existing gaze dot**

  Preserve these approved low-distraction properties:

  - 10×10 px size;
  - muted gray-green transparent border/fill;
  - soft 8 px blur shadow;
  - no animation, pulse, scale, or transition;
  - pointer-events disabled;
  - 1000 ms stale timeout.

- [ ] **Step 2: Record the actual visibility conditions**

  The dot is visible only when all of the following are true:

  - `Enable camera and microphone` is on and browser permission is granted;
  - the live capture component is running;
  - EyeTheia on Lenovo is listening on 8001 and returns valid predictions;
  - the predicted point falls inside the currently rendered slide;
  - the Mac browser can reach the remote 8001 service.

  `Show attention regions` controls AOI regions/server-match overlays; it is not a substitute for a live EyeTheia gaze sample.

- [ ] **Step 3: Use the correct Mac tunnel after restart**

  Forward both the public app port and the browser-facing EyeTheia port:

  ```bash
  ssh -N \
    -L 8501:127.0.0.1:8501 \
    -L 8001:127.0.0.1:8001 \
    LenovoLinux_Dorm
  ```

  Then open `http://127.0.0.1:8501`. Forwarding only 8501 is sufficient for the normal Streamlit/ingress UI but not for the current hard-coded local EyeTheia WebSocket.

---

### Task 8: Commit the UI refinement and restart the demo without tests

**Files:**

- Modify: this plan's production files only.
- Do not modify: `tests/**`.

- [ ] **Step 1: Review the scoped diff without executing validation suites**

  Inspect `git status --short` and `git diff --` for the six planned production files. Confirm no unrelated files, no test edits, no voice/gaze calculation changes, and no raw mock copy in learner-facing render functions. Do not run `unittest`, `pytest`, lint, type checks, or browser automation.

- [ ] **Step 2: Commit once**

  Stage only the planned files and commit:

  ```bash
  git add \
    apps/streamlit_attentive_slides.py \
    modules/system/main_ui_state.py \
    modules/ui/workspace.css \
    modules/ui/palette_control_component/index.html \
    modules/ui/slide_viewport_component/index.html \
    data/attentiveslides_deck/manifest.json
  git commit -m "style: refine AttentiveSlides study workspace controls"
  ```

  If Task 7 required no code change, do not stage either gaze calculation file.

- [ ] **Step 3: Restart only the single-port AttentiveSlides demo**

  Stop the existing process whose command line is exactly the AttentiveSlides single-port runner, then start:

  ```bash
  /home/charles/miniconda3/envs/pyboe/bin/python \
    scripts/run_live_single_port.py \
    --host 127.0.0.1 \
    --port 8501 \
    --streamlit-port 8502 \
    --ingress-port 8503
  ```

  Run it detached with the existing project log convention. Do not stop or restart the separate EyeTheia service on 8001.

- [ ] **Step 4: Confirm only that the requested processes are listening**

  Check that 8501, 8502, and 8503 are listening after restart and that the existing EyeTheia 8001 process remains listening. This is a restart confirmation, not a UI or test-suite acceptance run.

## Conversation-flow explanation (no implementation change)

- `1 turn`: each question is independent and sends no previous dialogue history to the Tutor.
- `Dialogue`: keeps a bounded local history (currently the latest four sanitized turns) so follow-up questions can refer to the preceding exchange.
- `Realtime`: uses the provider-owned persistent streaming conversation with continuous audio/barge-in semantics.

`Dialogue` was already part of the approved pre-existing conversation-flow contract; the 02 redesign made all three values visible in the left segmented control. Per the user's instruction, this pass explains it but does not add, remove, rename, or change any mode.

## Final code-inspection acceptance checklist

Do not execute this checklist as automated or browser testing; use it only to keep the implementation scoped before restart.

- [ ] No user-visible `Mock AttentiveSlides Deck` or `mock_deck` remains.
- [ ] With no PDF, the left lesson identity is only `AttentiveSlides Deck`; the branded empty slide contains separated title/tagline text.
- [ ] `DECK` upload is the first left-rail control and opens by default only when no PDF is loaded.
- [ ] Left rail closes from its upper-right and reopens with a small `»` edge tab.
- [ ] Right rail reads `SLIDES INDEX`, `{active} / {total}`, and `SLIDES / {total}`; it reopens with `«`, never `DECK`.
- [ ] Reduced custom, static, and empty slides are horizontally centered inside the slide stage.
- [ ] No dark shell band/ring surrounds the Slide, Control, and Tutor Output group.
- [ ] Palette button labels are smaller Literata text with modest rounded corners.
- [ ] Lifecycle and Tutor action buttons are all-caps IBM Plex Sans.
- [ ] `RESET TURN` matches the `WAITING` badge height.
- [ ] The empty Tutor instruction sentence is absent.
- [ ] Learner State aligns with Slide tools.
- [ ] Learner alert is in the top bar, stays on one line, and cannot change shell height.
- [ ] Control has no right-side status badge; Tutor Output still has `WAITING`/`READY`.
- [ ] Gaze cursor code and approved low-salience styling are untouched.
- [ ] No tests were run; the single-port service was restarted directly as requested.

## Explicitly deferred

- Changing or removing Dialogue mode.
- Deleting or renaming the legacy `data/mock_deck` backend/test fixture outside the production Streamlit path.
- Rewriting EyeTheia routing into the 8501 same-origin proxy; the immediate Mac demo path uses the dual-port SSH tunnel.
- Architecture refactoring, analytics expansion, dark mode, mobile layout, and new browser tests.
- Formal closure of the earlier plan's Checkpoint 7 full-suite verification; this follow-up obeys the user's newer instruction not to run tests.
