# AttentiveSlides Topbar, Rail, and Review Navigation Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan checkpoint by checkpoint. Do not use subagents unless the user explicitly asks for one. Track progress with the checkboxes below.

**Goal:** Remove the eager whole-deck PDF preparation path and refine the AttentiveSlides Study/Review shell so collapsed-rail controls live in the top bar, the left rail has the requested information hierarchy, Tutor Output typography matches the lifecycle controls, and Review navigation hugs the displayed slide.

**Architecture:** Keep the existing Streamlit session-state rail model, fixed 02-style shell, light palettes, and production interaction graph. Pass the already-prepared active `MainUISlide` into the slide-index renderer so the index never prepares inactive pages; render rail reopen actions as icon-only tertiary Streamlit buttons inside the fixed header; use one centered review slide frame as the positioning ancestor for both the rendered slide and its previous/next controls.

**Tech Stack:** Python 3.10, Streamlit, HTML/CSS injected through `st.html`, the existing Literata/IBM Plex Sans WOFF2 assets, PyMuPDF native worker, `unittest`/AST-based UI contract tests.

## Global Constraints

- Execute on `LenovoLinux_Dorm` in `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration`.
- Continue on branch `codex/gaze-heatmap-review`; the inspected implementation baseline is commit `aed01ac` (`style: refine AttentiveSlides study workspace controls`). The plan-document commit will be newer and is also an acceptable baseline.
- The inspected worktree was clean and the branch was 17 commits ahead of `origin/codex/gaze-heatmap-review` before this plan was added.
- Do not merge, rebase, push, or modify `main`.
- Target the Lenovo 4060 desktop viewport and light mode only. Do not add mobile, dark-mode, glass, blur-heavy, or responsive redesign work.
- Preserve the approved 02 visual direction, Ivory Study Desk default, user-selectable palette groups, Literata headings, IBM Plex Sans functional UI, square instrument-panel geometry, and existing semantic color tokens.
- Preserve Pause/Resume semantics, study lifecycle, One-turn/Dialogue/Realtime behavior, PTT/Hands-free behavior, AOI selection, low-salience gaze indicator, learner-state collection, review metrics, and all voice/media services.
- Do not reintroduce mock deck copy or assets into the production app.
- Do not change the existing left-rail collapse `×` or right-rail collapse `×`; this plan changes only the controls shown after a rail is collapsed.
- Use Material double-chevron icons, not literal `<<`, `>>`, `«`, or `»` text. The left reopen icon points right; the right reopen icon points left.
- Reopen controls have no filled background, border, or box shadow in default/hover/active states. Keep a keyboard-only focus outline.
- Keep the reopen hit target at the current 32 px and render the chevron itself at 20 px; do not enlarge the top bar.
- The left rail always displays `AttentiveSlides Deck` after PDF upload; it must not change to `LESSON / 01` or the uploaded filename.
- The top bar may continue to show the real uploaded deck title as contextual metadata. This is separate from the stable left-rail identity.
- `DECK` remains an expander: expanded before upload, collapsed after a PDF has been loaded.
- Do not add browser automation, visual-mock pages, lint, type checks, security scans, or performance suites. Follow the repository Lean Execution Profile: one focused GREEN group per implementation checkpoint, one final whole-change review, then one full suite.
- Restart the AttentiveSlides 8501/8502/8503 chain only after implementation, review, full-suite verification, and commit. Port 8503 remains lazy until browser media is enabled; port 8001 EyeTheia remains a separate unchanged service.

## Current-State Diagnosis Recorded on 2026-07-18

- The service was healthy: runner PID `2907443`, Streamlit PID `2907444`, 8501 and 8502 listening, and no PDF worker child remained.
- The reported Load PDF operation was slow but not deadlocked. The 13.8 MB, 62-page deck `574a1265a8f2` was registered at `18:37:14`; pages 1–62 were synchronously rasterized at 220 DPI until `18:39:36`, and `aoi_manifest.json` finished at `18:39:38`.
- Root cause: `_render_slide_selector()` loops over every `slide_id` and calls `browser.get_slide(slide_id)`. For an uploaded deck, `get_slide()` invokes `_get_or_process_slide()`, so merely rendering the right rail prepares the whole deck during one Streamlit rerun.
- All 62 pages of that specific deck are now prepared. Do not kill or restart the current service merely to recover this completed upload.
- The fix in Checkpoint 1 is intentionally lazy: main view-model construction prepares the current page; the rail uses that already-prepared `MainUISlide`; inactive entries retain lightweight placeholders until selected. Do not replace this with background batching or lower-DPI eager rendering.

## File Map

- Modify `apps/streamlit_attentive_slides.py`
  - render order for left-rail identity/upload/runtime controls;
  - topbar slot construction and collapsed-rail reopen controls;
  - slide-index preview policy;
  - Review slide/frame structure.
- Modify `modules/ui/workspace.css`
  - shared content top gap;
  - transparent icon-only reopen controls in the topbar;
  - exact RESET TURN typography;
  - Review slide-frame positioning.
- Modify `tests/test_slide_preview_canvas.py`
  - prevent inactive slide preparation in the index;
  - assert reopen controls are no longer owned by the selector.
- Modify `tests/test_compact_main_layout.py`
  - retain clickable index and navigation contracts while accepting lazy preview rendering.
- Modify `tests/test_main_ui_workspace_layout.py`
  - current `SLIDES INDEX`/`SLIDES /` copy;
  - topbar reopen placement and icon contract;
  - stable left-rail identity and order;
  - Tutor Output typography selector.
- Modify `tests/test_sidebar_layout.py`
  - left-rail identity/upload/runtime order and absence of `LESSON /`.
- Modify `tests/test_main_ui_review_layout.py`
  - centered Review frame owns navigation and slide rendering.
- Modify `tests/test_streamlit_attentive_slides.py`
  - update both selector call-shape contracts to pass `active_slide=view.active_slide`;
  - assert the Review detail uses the new centered slide frame.

---

### Checkpoint 1: Stop Slides Index from preparing the entire uploaded deck

**Files:**
- Modify: `apps/streamlit_attentive_slides.py:620-675`
- Modify: `apps/streamlit_attentive_slides.py:1815-1830`
- Modify: `apps/streamlit_attentive_slides.py:2575-2685`
- Modify: `tests/test_slide_preview_canvas.py`
- Modify: `tests/test_compact_main_layout.py`

**Interfaces:**
- Consumes: `view.active_slide: MainUISlide`, already prepared by `build_main_ui_view_model()` before either Study or Review renders.
- Produces: `_render_slide_selector(browser, *, active_slide: MainUISlide, slide_ids: Sequence[int] | None = None, disabled: bool = False) -> None`.
- Invariant: `_render_slide_selector()` must contain no call to `browser.get_slide(...)` and must never invoke PDF preparation for an inactive entry.

- [ ] **Step 1: Update the static selector contract before changing the renderer**

Add the following assertion in `tests/test_slide_preview_canvas.py`:

```python
def test_selector_reuses_only_the_already_prepared_active_slide(self) -> None:
    selector = ast.unparse(self.functions["_render_slide_selector"])
    self.assertIn("active_slide", selector)
    self.assertNotIn("browser.get_slide", selector)
    self.assertIn("slide_id == active_slide_id", selector)
```

Update stale assertions in `tests/test_slide_preview_canvas.py` and `tests/test_main_ui_workspace_layout.py` from `DECK INDEX`/`DECK /` to the accepted production copy `SLIDES INDEX`/`SLIDES /`.

- [ ] **Step 2: Pass the active slide to both selector call sites**

Use the following call shapes:

```python
_render_slide_selector(
    browser,
    active_slide=view.active_slide,
    disabled=not mutations_enabled,
)
```

```python
_render_slide_selector(
    browser,
    active_slide=view.active_slide,
    slide_ids=review_slide_ids,
)
```

- [ ] **Step 3: Make selector thumbnails lazy**

Change the selector signature to:

```python
def _render_slide_selector(
    browser: Any,
    *,
    active_slide: MainUISlide,
    slide_ids: Sequence[int] | None = None,
    disabled: bool = False,
) -> None:
    """Render the fixed, independently scrolling 02-style slides rail."""
```

The one-line docstring above replaces the old `DECK` wording. Retain the existing body, then replace only the `try: browser.get_slide(slide_id)` preview block inside the existing slide loop with:

```python
preview_slide = (
    active_slide
    if slide_id == active_slide_id
    else None
)
if (
    preview_slide is not None
    and preview_slide.image_available
    and preview_slide.image_path
):
    preview_path = Path(preview_slide.image_path)
    st.image(
        _thumbnail_png_bytes(
            str(preview_path),
            preview_path.stat().st_mtime_ns,
        ),
        width="stretch",
    )
else:
    st.markdown(
        '<div class="as-slide-preview-empty">Preview</div>',
        unsafe_allow_html=True,
    )
```

Keep every slide-number button, active selection styling, automatic scroll-to-active behavior, and placeholder height unchanged. Selecting an inactive placeholder prepares that page through normal view-model construction on the next rerun, then displays its thumbnail as the new active entry.

- [ ] **Step 4: Run the focused selector group**

Run:

```bash
python -m unittest tests.test_slide_preview_canvas tests.test_compact_main_layout -v
```

Expected: GREEN. If it fails, rerun only the failing test module after the fix.

- [ ] **Step 5: Commit Checkpoint 1**

```bash
git add apps/streamlit_attentive_slides.py tests/test_slide_preview_canvas.py tests/test_compact_main_layout.py tests/test_main_ui_workspace_layout.py
git commit -m "perf: lazily render slide index previews"
```

---

### Checkpoint 2: Move collapsed-rail reopen controls into the topbar

**Files:**
- Modify: `apps/streamlit_attentive_slides.py:515-565`
- Modify: `apps/streamlit_attentive_slides.py:580-595`
- Modify: `apps/streamlit_attentive_slides.py:2570-2610`
- Modify: `apps/streamlit_attentive_slides.py:2864-2960`
- Modify: `modules/ui/workspace.css:587-735`
- Modify: `modules/ui/workspace.css:987-1010`
- Modify: `tests/test_main_ui_workspace_layout.py`
- Modify: `tests/test_slide_preview_canvas.py`

**Interfaces:**
- Consumes: `main_left_rail_expanded` and `main_slide_rail_expanded` booleans.
- Produces: `_render_left_rail_reopen() -> None` and `_render_right_rail_reopen() -> None`, each rendered only inside `_render_header()`.
- Preserves: `_set_left_rail_expanded(bool)` and `_set_slide_rail_expanded(bool)` callbacks and all existing state keys.

- [ ] **Step 1: Convert reopen actions to Material icon buttons**

Keep the keyed containers because the CSS `body:has(...)` rules use their presence to expand the fixed topbar and collapse the rails. Render the following controls:

```python
def _render_left_rail_reopen() -> None:
    with st.container(key="main_sidebar_reopen"):
        st.button(
            "Open settings",
            key="main_sidebar_expand_button",
            help="Open settings",
            type="tertiary",
            icon=":material/keyboard_double_arrow_right:",
            on_click=_set_left_rail_expanded,
            args=(True,),
        )


def _render_right_rail_reopen() -> None:
    with st.container(key="main_slide_rail_reopen"):
        st.button(
            "Open slides index",
            key="main_slide_rail_expand_button",
            help="Open slides index",
            type="tertiary",
            icon=":material/keyboard_double_arrow_left:",
            on_click=_set_slide_rail_expanded,
            args=(True,),
        )
```

Delete literal `»` and `«` reopen labels. Do not change the `×` collapse labels.

- [ ] **Step 2: Remove edge-floating reopen rendering**

- Delete the top-level `_render_left_rail_reopen()` call from `main()`.
- When `_render_slide_selector()` sees `main_slide_rail_expanded == False`, it must simply `return`; it must not render a button.
- Do not add a replacement edge tab.

- [ ] **Step 3: Build dynamic topbar slots**

Within `_render_header()`, construct columns from named specs so no empty trigger-width column remains while a rail is open:

```python
left_collapsed = not st.session_state.get(
    "main_left_rail_expanded",
    True,
)
right_collapsed = not st.session_state.get(
    "main_slide_rail_expanded",
    True,
)

column_specs: list[tuple[str, float]] = []
if left_collapsed:
    column_specs.append(("left_reopen", 0.035))
column_specs.extend(
    (
        ("context", 0.34),
        ("alert", 0.28),
        ("status", 0.14),
        ("pause", 0.09),
        ("action", 0.15),
    )
)
if right_collapsed:
    column_specs.append(("right_reopen", 0.035))

columns = st.columns(
    [weight for _, weight in column_specs],
    gap="small",
    vertical_alignment="center",
)
slots = {
    name: column
    for (name, _), column in zip(column_specs, columns)
}
```

Render `_render_left_rail_reopen()` before the Study/Review context in `slots["left_reopen"]`, and render `_render_right_rail_reopen()` after START STUDY / END & REVIEW / BACK TO STUDY in `slots["right_reopen"]`. Leave alert, status, Pause/Resume, and lifecycle action behavior unchanged.

- [ ] **Step 4: Restyle keyed reopen containers as transparent topbar cells**

Delete the old fixed `left`, `right`, and `top: calc(var(--as-topbar-height) + 8px)` positioning. Apply a shared contract:

```css
.st-key-main_sidebar_reopen,
.st-key-main_slide_rail_reopen {
  align-items: center;
  display: flex;
  justify-content: center;
  margin: 0;
  min-width: 32px;
  width: 32px;
}

.st-key-main_sidebar_reopen button,
.st-key-main_slide_rail_reopen button,
.st-key-main_sidebar_reopen button:hover,
.st-key-main_slide_rail_reopen button:hover,
.st-key-main_sidebar_reopen button:active,
.st-key-main_slide_rail_reopen button:active {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  color: var(--as-ink) !important;
  height: 32px;
  min-height: 32px;
  padding: 0;
  width: 32px;
}

.st-key-main_sidebar_reopen button p,
.st-key-main_slide_rail_reopen button p {
  clip-path: inset(50%);
  height: 1px;
  overflow: hidden;
  position: absolute;
  white-space: nowrap;
  width: 1px;
}

.st-key-main_sidebar_reopen [data-testid="stIconMaterial"],
.st-key-main_slide_rail_reopen [data-testid="stIconMaterial"] {
  font-size: 20px;
  margin: 0;
}
```

Retain the global `button:focus-visible` outline; do not suppress it. Keep the existing `body:has(.st-key-main_sidebar_reopen)` and `body:has(.st-key-main_slide_rail_reopen)` rail/topbar width rules.

- [ ] **Step 5: Update and run the focused topbar/rail group**

In `tests/test_main_ui_workspace_layout.py`, assert:

- `_render_header` owns both reopen helpers;
- material icon names are exact;
- selector owns only the right-rail collapse button;
- CSS contains `background: transparent !important`, `border: 0 !important`, 32 px controls, and 20 px Material icons;
- the topbar `body:has(...)` width rules remain.

Add this ownership test to `tests/test_slide_preview_canvas.py` in this checkpoint:

```python
def test_reopen_actions_are_owned_by_the_topbar_not_the_selector(self) -> None:
    selector = ast.unparse(self.functions["_render_slide_selector"])
    header = ast.unparse(self.functions["_render_header"])
    self.assertNotIn("main_slide_rail_expand_button", selector)
    self.assertIn("_render_left_rail_reopen", header)
    self.assertIn("_render_right_rail_reopen", header)
```

Run:

```bash
python -m unittest tests.test_main_ui_workspace_layout tests.test_slide_preview_canvas -v
```

Expected: GREEN.

- [ ] **Step 6: Commit Checkpoint 2**

```bash
git add apps/streamlit_attentive_slides.py modules/ui/workspace.css tests/test_main_ui_workspace_layout.py tests/test_slide_preview_canvas.py
git commit -m "style: move rail reopen controls into topbar"
```

---

### Checkpoint 3: Reorder the left rail and unify compact typography/gaps

**Files:**
- Modify: `apps/streamlit_attentive_slides.py:620-670`
- Modify: `apps/streamlit_attentive_slides.py:1347-1380`
- Modify: `apps/streamlit_attentive_slides.py:2053-2140`
- Modify: `modules/ui/workspace.css:1-95`
- Modify: `modules/ui/workspace.css:580-595`
- Modify: `modules/ui/workspace.css:719-730`
- Modify: `modules/ui/workspace.css:918-942`
- Modify: `tests/test_main_ui_workspace_layout.py`
- Modify: `tests/test_sidebar_layout.py`
- Modify: `tests/test_ui_design_tokens.py`

**Interfaces:**
- Produces: `_render_sidebar_deck_identity() -> None` with stable `AttentiveSlides Deck` copy.
- Preserves: `_render_upload_controls(workspace, disabled=...)` and `_render_live_controls(resources, view=...)` behavior below the divider.
- CSS produces one `--as-content-top-gap: 10px` token shared by the sidebar user content and main block container.

- [ ] **Step 1: Extract a stable deck identity block**

Add:

```python
def _render_sidebar_deck_identity() -> None:
    st.sidebar.markdown(
        '<section class="as-rail-lesson">'
        '<h2 class="as-rail-title">AttentiveSlides Deck</h2>'
        "</section>",
        unsafe_allow_html=True,
    )
```

Delete the `_has_uploaded_deck()` conditional that currently emits `LESSON / NN` and `view.deck_title` at the start of `_render_live_controls()`. `_render_live_controls()` must begin with only:

```python
st.sidebar.markdown(
    '<div class="as-sidebar-rule"></div>'
    '<div class="as-eyebrow">RUNTIME CONFIGURATION</div>',
    unsafe_allow_html=True,
)
```

- [ ] **Step 2: Make sidebar render order explicit**

In the Study path of `main()`, use this order:

```python
_render_header(view, resources=live_resources)
_render_sidebar_deck_identity()
_render_upload_controls(
    workspace,
    disabled=not mutations_enabled,
)
_render_live_controls(
    live_resources,
    view=view,
)
```

`_render_sidebar_brand()` remains the first sidebar element and continues to show the product name `AttentiveSlides` plus the existing rail-collapse `×`. The resulting visible order is exactly:

1. `AttentiveSlides`
2. `AttentiveSlides Deck`
3. `DECK`
4. divider
5. `RUNTIME CONFIGURATION`

- [ ] **Step 3: Use one small top gap for the sidebar and workspace**

Add the token and replace the two independent offsets:

```css
:root {
  --as-content-top-gap: 10px;
}

[data-testid="stSidebarUserContent"] {
  padding: calc(var(--as-topbar-height) + var(--as-content-top-gap))
    12px 18px;
}

.block-container {
  max-width: none;
  padding: calc(var(--as-topbar-height) + var(--as-content-top-gap))
    calc(var(--as-right-rail-width) + 16px) 24px 16px;
}
```

Keep the product brand inside the 52 px sidebar header cell, but use a small internal vertical inset rather than attaching its content to the upper edge:

```css
.st-key-main_sidebar_brand {
  padding: 4px 10px 4px 20px;
}
```

- [ ] **Step 4: Make RESET TURN use the exact lifecycle-button typography**

Share the typography selector rather than approximating it in two places:

```css
.st-key-main_topbar button,
.st-key-main_reset_turn_button button {
  font-family: var(--as-font-ui);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  white-space: nowrap;
}
```

Keep the existing RESET TURN compact height, 22 px minimum height, and `0 7px` padding. Do not increase it to the 32 px topbar button height.

- [ ] **Step 5: Update and run the focused sidebar/typography group**

Add source-order assertions in `tests/test_sidebar_layout.py` or `tests/test_main_ui_workspace_layout.py`:

```python
main = self.functions["main"]
self.assertLess(
    main.index("_render_sidebar_deck_identity"),
    main.index("_render_upload_controls"),
)
self.assertLess(
    main.index("_render_upload_controls"),
    main.index("_render_live_controls"),
)
```

Also assert:

- `_render_sidebar_deck_identity` contains `AttentiveSlides Deck`;
- `_render_live_controls` contains neither `LESSON /` nor the deck-title identity branch;
- the shared top-gap token is exactly 10 px;
- the shared typography selector includes both topbar and RESET TURN;
- RESET TURN remains exactly 22 px high.

Run:

```bash
python -m unittest tests.test_sidebar_layout tests.test_main_ui_workspace_layout tests.test_ui_design_tokens -v
```

Expected: GREEN.

- [ ] **Step 6: Commit Checkpoint 3**

```bash
git add apps/streamlit_attentive_slides.py modules/ui/workspace.css tests/test_sidebar_layout.py tests/test_main_ui_workspace_layout.py tests/test_ui_design_tokens.py
git commit -m "style: refine sidebar hierarchy and control typography"
```

---

### Checkpoint 4: Anchor Review navigation to the scaled slide

**Files:**
- Modify: `apps/streamlit_attentive_slides.py:1840-1935`
- Modify: `modules/ui/workspace.css:395-510`
- Modify: `modules/ui/workspace.css:1040-1065`
- Modify: `tests/test_main_ui_review_layout.py`
- Modify: `tests/test_streamlit_attentive_slides.py`

**Interfaces:**
- Consumes: `_centered_slide_width()` and `main_slide_width_percent` (50–100%).
- Produces: keyed `main_review_slide_frame` containing both `_render_navigation(...)` and the Review slide/fallback.
- Preserves: heatmap rendering, heatmap toggle, FIT/+/− toolbar, download behavior, selected-slide detail, and all Review metrics.

- [ ] **Step 1: Put navigation and slide content in one centered frame**

Inside `main_review_slide_stage`, replace the full-stage navigation plus separately centered image with:

```python
with st.container(key="main_review_slide_stage"):
    with _centered_slide_width():
        with st.container(key="main_review_slide_frame"):
            _render_navigation(
                browser,
                view,
                slide_ids=review_slide_ids,
            )
            if image_path is None:
                _render_review_text_fallback(view.active_slide)
            else:
                try:
                    if (
                        slide_review is not None
                        and slide_review.valid_gaze_seconds > 0.0
                    ):
                        rendered = render_review_slide(
                            image_path,
                            slide_review,
                            show_heatmap=show_heatmap,
                        )
                    else:
                        rendered = _load_slide_image(image_path)
                    try:
                        st.image(rendered, width="stretch")
                    finally:
                        rendered.close()
                except (OSError, ValueError):
                    st.warning("The slide image or heatmap is unavailable.")
```

Do not nest a second `_centered_slide_width()` around `st.image`; the frame itself is already centered and scaled.

- [ ] **Step 2: Make the Review frame the absolute-positioning ancestor**

Add:

```css
.st-key-main_review_slide_frame {
  position: relative;
}
```

Keep the shared previous/next rules and their `left: 0.4rem`, `right: 0.4rem`, and `top: 50%`. Because the nearest positioned ancestor is now the scaled Review slide frame, the controls sit at the slide sides instead of the wider detail module edges. Do not change the Study slide navigation contract.

- [ ] **Step 3: Update and run the focused Review group**

In `tests/test_main_ui_review_layout.py`, assert:

- `main_review_slide_frame` exists;
- `_centered_slide_width()` appears before the frame;
- `_render_navigation` and both image/fallback branches are inside that frame;
- CSS gives the frame `position: relative`;
- the separate inner `_centered_slide_width()` around the image no longer exists.

Run:

```bash
python -m unittest tests.test_main_ui_review_layout tests.test_streamlit_attentive_slides -v
```

Expected: GREEN.

- [ ] **Step 4: Commit Checkpoint 4**

```bash
git add apps/streamlit_attentive_slides.py modules/ui/workspace.css tests/test_main_ui_review_layout.py tests/test_streamlit_attentive_slides.py
git commit -m "style: anchor review navigation to slide frame"
```

---

### Checkpoint 5: Whole-change review, full verification, commit state, and service restart

**Files:**
- Review: all files changed since the plan-document commit.
- Runtime log: `/tmp/attentiveslides-live.log`

**Interfaces:**
- Produces: one clean committed branch and a restarted local AttentiveSlides service chain.
- Does not produce: push, merge, PR, or main-branch changes.

- [ ] **Step 1: Perform one bounded whole-change review**

Inspect:

```bash
git diff --check
git diff HEAD~4 -- apps/streamlit_attentive_slides.py modules/ui/workspace.css tests
```

Review for the following specific regressions:

- literal `«`, `»`, `<<`, or `>>` reopen labels;
- reopen buttons outside `_render_header()`;
- background/border/box-shadow on reopen controls;
- `browser.get_slide(slide_id)` inside `_render_slide_selector()`;
- left identity changing with uploaded deck or slide number;
- DECK rendered before `AttentiveSlides Deck`;
- Review arrows positioned against `main_review_slide_stage` rather than `main_review_slide_frame`;
- changed Pause/Resume, voice, AOI, gaze, or palette behavior.

If the review finds a Critical or Important issue, fix it in one bounded wave and rerun only the directly affected focused module(s).

- [ ] **Step 2: Run the full suite once**

Run:

```bash
python -m unittest discover -s tests -v
```

Expected: GREEN. Do not repeat a passing full suite after commit or restart. If it fails because a stale static UI assertion still encodes the pre-`aed01ac` copy, update only that directly related assertion, run its module, then rerun the full suite at most once.

- [ ] **Step 3: Confirm the final branch is committed and clean**

If the bounded review required fixes, commit them:

```bash
git add apps/streamlit_attentive_slides.py modules/ui/workspace.css tests
git commit -m "fix: address AttentiveSlides rail refinement review"
```

Then record:

```bash
git status --short --branch
git log -6 --oneline --decorate
```

Expected: clean `codex/gaze-heatmap-review`; no push or merge.

- [ ] **Step 4: Restart only the AttentiveSlides runner process group**

Find the current runner PID and PGID from the exact command:

```bash
ps -eo pid,ppid,pgid,stat,etime,args | rg "scripts/run_live_single_port.py --host 127.0.0.1 --port 8501 --streamlit-port 8502 --ingress-port 8503"
```

Capture the exact runner and terminate only its process group:

```bash
runner_pid="$(pgrep -f '^/home/charles/miniconda3/envs/pyboe/bin/python scripts/run_live_single_port.py --host 127.0.0.1 --port 8501 --streamlit-port 8502 --ingress-port 8503$' | head -n 1)"
runner_pgid="$(ps -o pgid= -p "$runner_pid" | tr -d ' ')"
kill -TERM -- "-$runner_pgid"
```

Wait until 8501 and 8502 have closed. Then launch from the repository root with the exact detached command below. Do not kill port 8001 EyeTheia.

```bash
setsid /home/charles/miniconda3/envs/pyboe/bin/python scripts/run_live_single_port.py --host 127.0.0.1 --port 8501 --streamlit-port 8502 --ingress-port 8503 > /tmp/attentiveslides-live.log 2>&1 < /dev/null &
```

- [ ] **Step 5: Verify service state without browser automation**

Run:

```bash
ss -ltnp
tail -n 80 /tmp/attentiveslides-live.log
```

Expected:

- 8501 proxy listening;
- 8502 Streamlit listening;
- log contains `AttentiveSlides live proxy ready at http://127.0.0.1:8501`;
- 8503 may be absent until camera/microphone is enabled and is still configured by `--ingress-port 8503`;
- 8001 EyeTheia remains listening.

- [ ] **Step 6: Handoff**

Report:

- final commit hashes;
- focused and full-suite results;
- clean branch state;
- service PIDs/ports and the 8503 lazy-ingress note;
- no push/merge;
- primary URL `http://127.0.0.1:8501`;
- full Mac tunnel command:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 8501:127.0.0.1:8501 \
  -L 8502:127.0.0.1:8502 \
  -L 8503:127.0.0.1:8503 \
  -L 8001:127.0.0.1:8001 \
  LenovoLinux_Dorm
```

## Acceptance Checklist

- [ ] A newly uploaded multi-page PDF prepares only the current slide during the first Study render; Slides Index does not synchronously rasterize every page.
- [ ] Collapsed left rail shows a small right-pointing Material double-chevron immediately left of `STUDY / WORKSPACE` or `REVIEW / WORKSPACE`.
- [ ] Collapsed right rail shows a small left-pointing Material double-chevron immediately right of START STUDY / END & REVIEW / BACK TO STUDY.
- [ ] Neither reopen control displays literal angle characters, text, a border, fill, or shadow.
- [ ] Expanding either rail removes its reopen slot so the remaining topbar content does not retain a blank gutter.
- [ ] Main content begins 10 px below the 52 px topbar.
- [ ] Left rail order is `AttentiveSlides`, `AttentiveSlides Deck`, `DECK`, divider, `RUNTIME CONFIGURATION`.
- [ ] Uploading a PDF does not change the left identity to `LESSON / 01` or the uploaded filename.
- [ ] RESET TURN exactly matches START STUDY's IBM Plex Sans, 10 px, 700, 0.05em, uppercase typography while retaining its 22 px height.
- [ ] Review previous/next controls sit at the left/right sides of the currently scaled slide at 50%, 70%, and 100%, not at the edges of the full evidence column.
- [ ] Existing 02 palette, fonts, slide centering, gaze dot, AOIs, voice modes, Pause/Resume, Tutor Output, and Review data remain unchanged.
