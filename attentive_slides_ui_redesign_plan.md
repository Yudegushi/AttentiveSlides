# AttentiveSlides Streamlit UI Redesign Plan

## Context

AttentiveSlides is currently a deterministic, mock-driven human-centered AI slide tutoring prototype. The implemented milestone combines:

- text transcript as explicit learner intent,
- coarse mock gaze/head-pose signals as visual reference hints,
- observable learning-state signals,
- AOI reference resolution,
- confirmation-gated tutor response,
- JSONL logging and evaluation tables.

The current UI lives mainly in `apps/streamlit_demo.py`. It works functionally, but its first-screen feel is closer to a generic debugging dashboard than a careful learning assistant. `PROJECT_PROGRESS.md` records that the core mock pipeline, adapter boundary, Streamlit demo, tests, and evaluation scripts are already working and should not be broken.

The requested visual inspiration comes from `https://www.aununo.xyz/public/contact.html`: a restrained personal site with a small navigation/header, a letter-like title, date/body rhythm, and quiet editorial tone. The redesign should translate that feeling into a warm research-notebook / learning-desk interface. It should not copy the page layout, text, colors, or assets.

## Request

Redesign the current Streamlit demo UI using the `ui-ux-pro-max` skill direction:

- Make the app feel like a quiet, careful, human-centered slide learning assistant.
- Keep uncertainty, confirmation, and correction visible.
- Make the slide AOI grounding area the primary visual anchor.
- Make confirmation emotionally central and calm.
- Keep system evidence available but visually secondary.
- Move evaluation and logs into a lower developer trace section.
- Preserve all existing mock pipeline behavior, state handling, logging, tests, and scenario controls.

The work should focus on UI design and layout inside `apps/streamlit_demo.py`. Do not perform a broad frontend rewrite or project-structure refactor.

## Output

Expected deliverables after implementation:

- `apps/streamlit_demo.py` has a clearer design-token CSS layer inside `_inject_css()`.
- The first screen uses a warm paper-like canvas instead of a dark/debug dashboard feel.
- The header uses precise, non-marketing copy:
  - small label: `AttentiveSlides · mock tutor loop`
  - title: `A slide tutor that asks before it assumes.`
  - subtitle: `Gaze gives a hint, voice gives intent, confirmation keeps the answer grounded.`
- The left sidebar is renamed and visually reframed as a quiet input desk:
  - `Mock input desk`
  - Scenario
  - Learner utterance
  - Gaze hint
  - Observable signals
- The main area is arranged as a study table with three zones:
  - Slide / Learning Surface
  - Tutor Note / Confirmation
  - Evidence Drawer / Grounding Trace
- The slide AOI area looks like paper on a desk:
  - warm off-white slide surface,
  - subtle border,
  - AOI outlines that read as annotations,
  - candidate state in muted amber,
  - confirmed state in muted sage,
  - quiet available-region state.
- The slide includes a small metadata row:
  - `slide_05 · SHAP explanation · AOI manifest`
- The slide includes a tiny legend:
  - `candidate`
  - `confirmed`
  - `available region`
- The confirmation UI is rewritten from warning-like messaging to gentle, explicit confirmation:
  - pending example: `I think you mean the right figure. Please confirm before I answer.`
  - primary action: `Confirm right figure`
  - secondary action: `Choose another region`
  - confirmed example: `Target confirmed · right_figure`
- The tutor response is presented as `Tutor note`.
- Pending response copy says:
  - `Waiting for target confirmation before giving an AOI-specific answer.`
- Evidence is renamed to `Grounding trace`.
- Evidence summary uses compact chips, not large dashboard metrics:
  - `intent: explain`
  - `gaze hint: right_figure`
  - `confidence: 0.76`
  - `strategy: normal`
- Evaluation and JSONL log are grouped under `Developer trace` below the main flow.
- Existing commands still pass:

```bash
python -m py_compile apps/streamlit_demo.py
python -m unittest discover -s tests -v
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
```

If doing final UI verification, also run:

```bash
python -m streamlit run apps/streamlit_demo.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
curl -I http://localhost:8501
```

## Constraints

- Keep this as a Streamlit app.
- Do not rewrite the UI into React, Next.js, or another frontend stack.
- Do not reorganize the whole project.
- Keep changes narrowly focused on `apps/streamlit_demo.py`, unless a small test update is needed.
- Preserve existing functions and pipeline behavior:
  - scenario loading,
  - sidebar controls,
  - AOI rendering,
  - confirmation state,
  - evidence rendering,
  - evaluation table,
  - JSONL logging.
- Do not change underlying data keys, dataclasses, schema fields, fixture names, or evaluation expectations.
- Do not hide uncertainty or make unsupported claims about accurate gaze, attention, emotion, fatigue, or cognition.
- Treat gaze as coarse AOI grounding only, not pixel-level eye tracking.
- Treat learning-state as observable signals only, not true internal state.
- Candidate and confirmed states must be distinguishable by label/text as well as color.
- Maintain accessible contrast and visible focus states where Streamlit allows.
- Do not use:
  - SaaS landing-page composition,
  - purple AI gradients,
  - glassmorphism cards,
  - cyberpunk terminal styling,
  - oversized hero metrics,
  - heavy shadows,
  - large decorative motion.
- Motion should be limited to subtle hover/state transitions using opacity/transform/background/border changes and should respect `prefers-reduced-motion`.
- Avoid a large decomposition of `apps/streamlit_demo.py` during this pass. Small helper functions are acceptable if they make the UI clearer without changing behavior.

## Recommended UI Approach

Use a restrained editorial interface: warm paper background, thin dividers, compact metadata, readable note cards, and low-emphasis controls. This best matches the prototype's human-centered claim because it makes the tutor loop understandable without pretending to be a polished production learning platform.

Alternative approaches considered:

- Full dashboard polish: rejected because it would overemphasize metrics and make evidence feel primary.
- App-like product shell: possible, but too close to SaaS demo language for this milestone.
- Minimal notebook style: recommended because it supports transparency, confirmation, and careful language.

## Design Tokens

Implement a local CSS token layer in `_inject_css()`:

```css
:root {
  --as-bg: #F6F0E6;
  --as-surface: #FFFCF5;
  --as-slide: #FBFAF7;
  --as-text: #241F1A;
  --as-muted: #6F675D;
  --as-border: #DDD2C1;
  --as-border-strong: #CBBDA8;
  --as-candidate: #B86B3C;
  --as-candidate-fill: rgba(184, 107, 60, 0.12);
  --as-confirmed: #6F8A6A;
  --as-confirmed-fill: rgba(111, 138, 106, 0.14);
  --as-info: #6E7F91;
  --as-danger: #A84A3F;
}
```

Use system fonts. Use monospace only for IDs, metadata, confidence values, and logs.

## Implementation Plan

### Phase 1: Baseline and Guardrails

- Read `apps/streamlit_demo.py`, `tests/test_demo_view_model.py`, and `PROJECT_PROGRESS.md`.
- Run the existing verification commands before implementation.
- If a command fails because of missing local dependencies or a port conflict, record the exact failure before making UI edits.
- Keep behavior changes out of this phase.

### Phase 2: CSS Token and Global Surface

- Refactor `_inject_css()` into organized sections:
  - design tokens,
  - Streamlit app shell overrides,
  - header,
  - cards and metadata,
  - slide/AOI,
  - chips,
  - confirmation states,
  - developer trace,
  - responsive rules.
- Set the main app background to warm off-white.
- Make sidebar controls quieter using Streamlit-safe selectors.
- Keep CSS scoped with `as-` class names where possible.

### Phase 3: Header and Sidebar Copy

- Replace `st.title()` and `st.caption()` with a custom header block rendered through `st.html()`, matching the existing app's HTML rendering pattern.
- Rename sidebar header from `Mock Inputs` to `Mock input desk`.
- Rename visible labels only where clarity improves:
  - `Transcript` -> `Learner utterance`
  - `Gaze prediction` -> `Gaze hint`
  - `Predicted AOI` -> `Gaze-indicated region`
  - `Stable duration` -> `Stable for`
  - `Reset confirmation` -> `Clear confirmation`
- Do not change variable names, fixture keys, or schema fields.

### Phase 4: Main Layout

- Keep the current two-column Streamlit layout but adjust semantics:
  - left column: slide surface and metadata,
  - right column: tutor note, confirmation, grounding trace.
- Use ratios close to `[1.35, 0.9]` so the slide remains primary.
- Avoid nested card-heavy layouts.
- Place `Developer trace` below the main columns with a subtle divider.

### Phase 5: Slide AOI Grounding

- Update `_slide_html()` to include:
  - a metadata row,
  - a subtle legend,
  - the existing slide title/subtitle,
  - AOI boxes.
- Update `_aoi_box_html()` so state is explicit:
  - candidate labels include `candidate`,
  - confirmed labels include `confirmed`,
  - available labels remain readable but quiet.
- Keep normalized manifest coordinates unchanged.
- Preserve responsive behavior:
  - on narrow screens, reduce AOI padding and hide long AOI text if necessary,
  - never introduce horizontal scroll.

### Phase 6: Confirmation and Tutor Note

- Update `_render_confirmation()`:
  - Replace `st.warning()` with a custom calm confirmation card.
  - Pending state should explain why confirmation is needed before answering.
  - The primary button should mention the selected region when possible, for example `Confirm right figure`.
  - Keep correction flow through the existing selectbox.
  - Keep fixture correction action available but secondary.
  - Confirmed state should be calm and explicit.
- Update `_render_response()`:
  - Rename section to `Tutor note`.
  - Use note-like layout.
  - Keep answer, active recall, and adaptive suggestion.
  - Pending state must continue hiding AOI-specific answer.

### Phase 7: Grounding Trace and Developer Trace

- Update `_render_evidence()`:
- Rename from `System Evidence` to `Grounding trace`.
- Replace `st.metric()` columns with chip-like compact HTML rendered through `st.html()`.
  - Keep evidence details in an expander.
  - Keep learning-state summary and scenario fixture hidden by default.
  - Keep `Append current turn to JSONL log`.
- Update `_render_evaluation()` and `_render_log_viewer()`:
  - Nest under a visible `Developer trace` section.
  - Keep dataframes compact and secondary.

### Phase 8: Verification and Visual QA

- Run Python compile and tests.
- Run evaluation scripts.
- Start Streamlit and verify HTTP 200.
- Open the app and inspect:
  - pending confirmation scenario,
  - confirmed AOI scenario,
  - click-required low-confidence scenario,
  - narrow viewport if browser tooling is available.
- Check that:
  - no final AOI-specific answer appears before confirmation,
  - candidate and confirmed AOIs are both labeled and colored,
  - evidence is present but not visually dominant,
  - developer trace is below the first-screen learning flow,
  - sidebar remains usable.

## Checkpoints

Stop and ask the user before continuing if any of these occur:

- Implementing the desired layout would require moving the app out of Streamlit.
- The UI work starts requiring a broad split of `apps/streamlit_demo.py` into many component files.
- A requested visual detail conflicts with the human-centered constraint against implying accurate emotion/cognition/pixel gaze.
- Existing tests or evaluation scripts fail for reasons unrelated to the UI edits.
- Streamlit CSS limitations prevent a major visual requirement from being implemented cleanly.
- The redesign would need new dependencies, web fonts, icon libraries, or external assets.
- The visual direction starts drifting toward a SaaS landing page, dark dashboard, glassmorphism, or AI-gradient style.

If no checkpoint is triggered, continue through verification and report the changed files, commands run, and any residual UI risks.

## Acceptance Criteria

- The first screen no longer feels like a dark debug dashboard.
- The slide grounding area is the visual anchor.
- Confirmation is clear, calm, and central to the interaction.
- Evidence remains available but secondary.
- Developer logs and evaluation tables remain present but below the main learner-facing flow.
- The UI copy is precise and does not overclaim sensing ability.
- Existing mock behavior remains unchanged.
- Existing tests and evaluation commands pass.
