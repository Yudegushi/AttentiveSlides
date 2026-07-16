# AttentiveSlides Study and Review UI Redesign

**Status:** Approved on 2026-07-17

## Goal

Redesign the light-mode AttentiveSlides interface into a calm, coherent desktop study tool while preserving the existing gaze, speech, tutoring, learner-state, and Study Review capabilities.

The redesign must make the slide the primary object, keep attention and voice controls stable across interaction modes, place the tutor explanation below the working area, replace the Slides popover with a persistent right rail, and give the separate Review workspace a clear hierarchy for gaze and learner-state evidence.

## Scope

This design includes:

- the shared light-mode visual system;
- the Study Workspace information architecture;
- a persistent left settings rail and right slide rail;
- unified One-turn, Dialogue, and Realtime interaction presentation;
- Push-to-talk and Hands-free speaking controls;
- the `V` hold-to-speak keyboard shortcut;
- dwell-weighted AOI resolution at speech-turn boundaries;
- a low-salience live gaze cursor;
- palette selection and local preference persistence;
- the Review Workspace visual hierarchy;
- presentation-layer extraction required to keep the Streamlit application maintainable.

## Non-goals

- Dark mode.
- Mobile or narrow-screen layouts.
- Glassmorphism, gradients, decorative blur panels, or animated backgrounds.
- A backend architecture rewrite.
- New learner-state models, analytics, or second-by-second derived metrics.
- Changes to gaze aggregation mathematics, VAD thresholds, Tutor grounding, provider fallback, or Study Review storage contracts.
- Persisting question-and-answer transcripts inside completed Study Review files.
- A new Study pause lifecycle.
- New browser automation, end-to-end test frameworks, or screenshot-diff infrastructure.

## Target Environment

- Host: `LenovoLinux_Dorm`.
- Physical display: `2560x1600`.
- X11 fractional scaling: approximately `160%`.
- Effective design viewport: approximately `1600x1000`.
- Browser presentation: desktop Chromium in light mode.
- Primary language: English.
- Streamlit: `1.59.1` in `/home/charles/miniconda3/envs/pyboe`.

The layout may compress modestly below the target viewport, but it does not need a mobile reflow.

## Chosen Design Direction

The chosen direction is **Structured Reading Desk**:

- B / Cool Instrument Panel supplies the strict grid, compact controls, persistent operational rails, and information density.
- C / Autumn Reading Room supplies the restrained roundness, editorial reading rhythm, serif headings, and palette selector.
- A / Ivory Study Desk supplies the default color palette.

The UI is operational, not marketing-oriented. Borders and background planes establish hierarchy. Shadows are reserved for the slide canvas and overlays that must visibly float. Components are not wrapped in cards unless they have an independent boundary or state.

## Shared Shell

### Top bar

The top bar contains, from left to right:

- `AttentiveSlides` identity;
- workspace name (`Study Workspace` or `Review Workspace`);
- deck title and slide position;
- Study lifecycle status and elapsed time;
- the primary lifecycle action (`Start study` or `End study & review`).

Technical provider names and the removed `Manual / Live` split do not appear in the top bar.

### Left rail

The Study left rail contains:

1. lesson identity;
2. conversation flow;
3. speaking control;
4. attention source and answer preferences;
5. palette selector;
6. participant/calibration status;
7. collapsed `Advanced voice settings` for engine/provider details.

The Review left rail contains:

1. `Back to Study Workspace`;
2. completed-session selector;
3. selected-session metadata;
4. JSON export;
5. destructive session deletion inside a collapsed confirmation section.

### Right slide rail

The current top-right Slides popover becomes a persistent right rail:

- open by default;
- fixed-width and independently scrollable;
- current slide outlined using the selected palette accent;
- compact slide number plus thumbnail;
- small `×` collapse control;
- a narrow `Slides` reopen control when collapsed;
- auto-scrolls the current slide into view.

The rail is shared by Study and Review.

## Study Workspace Layout

The main Study Workspace uses two rows:

1. slide canvas on the left and the unified Attention & Voice panel on the right;
2. Tutor explanation spanning the width below the first row.

The slide is left-aligned inside the central workspace and defaults to `70%` scale. The existing 50–100%, five-point step control remains available, but the default presentation must no longer center an oversized slide with unused space on both sides.

The Attention & Voice panel does not move when the selected conversation flow or speaking control changes. Only its state text and controls change.

The Tutor explanation is never rendered inside the voice transport component. It uses the same lower region for One-turn, Dialogue, and Realtime.

## Interaction Model

Two orthogonal controls replace the current top-level `Manual / Live`, dialogue-engine, and speaking-style presentation.

### Conversation flow

User-facing values:

- `One-turn`: one grounded request and response; prior turns are not supplied as context.
- `Dialogue`: grounded requests use the existing bounded conversation history.
- `Realtime`: the existing persistent Omni runtime and interruption behavior.

Internal engine/provider details remain in `Advanced voice settings` and do not change the layout.

The former `main_interaction_mode == "Live"` condition is not retained as a hidden compatibility mode. `main_live_master_enabled`—the visible camera/microphone master control—is the sole gate for starting or polling media services, updating learner-state sensing, and enabling answer audio. Conversation flow selects only the turn engine and history behavior. Typed input remains usable when the media master is off.

### Speaking control

User-facing values:

- `Hold to speak`: pointer PTT or the `V` key.
- `Hands-free`: automatic speech-turn detection.

The default is `Hold to speak` because it is deterministic for the recorded demo and minimizes false activation. A session may switch to Hands-free without changing the panel layout.

Typed input remains an optional secondary path inside the unified panel. It is not a top-level interaction mode.

## Hold-to-speak State Machine

Visible states:

1. `Ready · Hold V or the button to speak`.
2. `Recording · Sampling attention`.
3. `Transcribing`.
4. `Resolving target` or `Target needs confirmation`.
5. `Target locked`.
6. `Answering`.
7. `Ready` after completion.

Behavior:

- pointer down or `V` keydown begins the PTT turn;
- pointer up or `V` keyup ends the turn;
- release automatically transcribes, resolves the target, and generates the answer;
- the current `Generate grounded answer` button is removed;
- a target-confirmation action immediately continues into answer generation;
- `Retry` is offered for too-short input, empty transcription, or transcription failure;
- `Cancel` stops an active PTT turn;
- the existing 0.3-second minimum and 20-second maximum remain unchanged.

### Global `V` shortcut safety

The shortcut is active only when:

- the Study Workspace is visible;
- speaking control is `Hold to speak`;
- no text input, text area, select, content-editable element, menu, dialog, or palette control owns focus;
- no Ctrl, Alt, Meta, or Shift modifier is held.

Repeated keydown events do not start duplicate turns. Window blur, page hide, component teardown, or lost keyup forces the same safe PTT stop used by pointer cancellation. The shortcut installs at the workspace document boundary, not only on the focused PTT button.

## Hands-free State Machine

Visible states:

1. `Listening for speech`.
2. `Speech detected · Sampling attention`.
3. `Transcribing` or provider transcription.
4. `Resolving target` or `Target needs confirmation`.
5. `Target locked`.
6. `Answering`.
7. `Listening for speech` after completion.

The existing turn detector remains authoritative:

- 150 ms speech-start window;
- 300 ms audio pre-roll;
- 800 ms end-of-speech silence;
- 300 ms minimum utterance;
- 20-second maximum utterance.

One-turn and Dialogue ignore additional automatic turns while the current turn is being processed. Realtime keeps the existing barge-in behavior: new speech interrupts a responding or playing Tutor and begins the next turn.

The panel provides `Pause listening` / `Resume listening`. This pauses continuous capture only; it does not introduce a new Study pause lifecycle.

## AOI Turn Boundary and Locking

The current `TurnContextCollector` behavior is preserved.

### Window definition

- PTT begins the window on button/key press and ends it on release.
- Hands-free begins the window at detected speech start and ends it at the last detected speech frame.
- The sensing window includes the existing 0.5-second pre-speech lookback.
- The slide identity and AOI manifest identity are frozen at speech start.
- Slide changes during a speech turn do not silently rebind evidence.

### Resolution

Gaze is not reduced to a simple coordinate mean. Valid evidence is ranked using dwell contribution weighted by confidence, with the existing 0.15-second minimum dwell and 0.5-second per-sample dwell cap. Local point-gaze aggregation remains authoritative when fresh local gaze exists.

The UI therefore says `Sampling attention` during speech. It says `Target locked` only after the window closes and aggregation resolves a target.

### Low-confidence behavior

When no valid target or insufficient evidence exists:

- do not generate against an arbitrary AOI;
- show `Target needs confirmation` in the same right panel;
- offer ranked AOI candidates when present;
- always offer `Whole slide`;
- offer manual region selection;
- continue directly into answer generation after confirmation.

The default confirmation policy is `Confidence-based auto` with threshold `0.80`. A valid resolved target at or above the threshold proceeds automatically; a missing, invalid, or lower-confidence target requires confirmation. `Always confirm` remains available only in `Advanced voice settings`.

## Low-salience Live Gaze Cursor

The current live gaze point is a 12 px solid blue dot with a white border and strong dark/blue shadow. That treatment can become an exogenous attention cue and bias the study experience.

The redesigned gaze cursor is intentionally peripheral:

- size: `10px × 10px`;
- fill: low-chroma gray-green `rgba(72, 84, 78, 0.16)`;
- edge: `1px solid rgba(72, 84, 78, 0.18)`;
- diffusion: `0 0 8px 5px rgba(72, 84, 78, 0.08)`;
- no white outline;
- no blue;
- no dark drop shadow;
- no pulse, scale, spring, trail, or other animation;
- preserve the existing 1000 ms stale clear behavior.

This component does not use the palette primary accent. It stays neutral across palettes so palette switching cannot turn the gaze point into a stronger stimulus. The cursor is non-essential feedback and is not required to meet text/control contrast ratios.

AOI candidate, confirmed target, manual region, and Review heatmap styling remain distinct from the live gaze cursor.

## Design Tokens and Palettes

The implementation uses three layers:

1. primitive values;
2. semantic roles;
3. component tokens.

Components never hardcode palette colors. Palette switching replaces semantic roles, and component tokens inherit the change.

CSS custom properties in the Streamlit parent document do not cross custom-component iframe boundaries. Every themeable iframe therefore receives the selected palette ID and a complete, whitelisted semantic-token map as component arguments and applies those tokens to its own root. The palette control and voice transport always use this bridge; slide-viewport chrome uses it where applicable. Live gaze, AOI status, alerts, and heatmap colors remain invariant and are never derived from palette accent colors.

### Themeable groups

- app canvas;
- workspace plane;
- left/right rails;
- raised surface;
- primary and muted text;
- borders;
- primary interaction accent;
- selected segment and active thumbnail;
- target context surface;
- slide-canvas rule/accent used by the AttentiveSlides shell.

### Invariant groups

- slide image/content pixels;
- live gaze cursor;
- proposed/confirmed AOI semantics;
- success, warning, error, destructive, fatigue-alert, and distraction-alert semantics;
- gaze heatmap scale.

### Complete semantic palette registry

Every palette defines exactly the same semantic keys. `Ivory Study Desk` is the default.

| Semantic role | Ivory Study Desk | Autumn Reading Room | Cool Archive | Dusty Blue |
|---|---:|---:|---:|---:|
| `canvas` | `#F6F1E7` | `#F7EFE1` | `#EDF0EC` | `#EEF0EF` |
| `workspace` | `#F0EBE0` | `#EEE4D4` | `#E4E9E6` | `#E3E8E8` |
| `topbar` | `#FAF7EF` | `#FBF6EC` | `#F6F7F3` | `#F6F7F5` |
| `rail` | `#F7F3E9` | `#F5ECDD` | `#F0F3EF` | `#EDF1F0` |
| `surface` | `#FFFDF8` | `#FFFBF3` | `#FBFCF8` | `#FAFBF8` |
| `ink` | `#292A24` | `#332B26` | `#202A29` | `#263033` |
| `muted` | `#747168` | `#7D7064` | `#687371` | `#697377` |
| `muted-2` | `#AAA59A` | `#AFA195` | `#9BA4A1` | `#9BA4A6` |
| `border` | `#DDD6C7` | `#DFD0BC` | `#CDD5D1` | `#CBD3D4` |
| `border-strong` | `#C9C0AE` | `#C6B49D` | `#AFBBB6` | `#ADB9BB` |
| `primary` | `#485F55` | `#774837` | `#3E6264` | `#4B6169` |
| `primary-on` | `#FFFDF8` | `#FFFAF1` | `#FBFCF8` | `#FAFBF8` |
| `primary-soft` | `#E2E9E1` | `#EAD8C9` | `#D8E6E4` | `#DBE5E7` |
| `segment` | `#E9E3D7` | `#E9DECE` | `#DFE5E2` | `#DFE5E4` |
| `slide-accent` | `#A55D42` | `#B97843` | `#8D5A48` | `#9A6653` |
| `slide-accent-soft` | `#EDD3C6` | `#F0D7B8` | `#E8D4CB` | `#EAD6CC` |

The local-storage key is `attentiveslides-ui-palette-v1`. A missing, unknown, or corrupt value resolves to `ivory-study-desk`.

Palette selection is disabled whenever the Study lifecycle is active. The active palette remains visible with the explanation `Palette is locked during an active study.` Review and inactive Study states may change it. The selection persists across Study and Review and across browser restarts on the same device.

## Typography and Geometry

No runtime web-font request is introduced.

- Heading and editorial answer text: `Noto Serif`, then `DejaVu Serif`, then generic serif.
- Controls, labels, captions, tables, and status text: `Noto Sans`, then `DejaVu Sans`, then generic sans-serif.

Both Noto families are available on the Lenovo environment.

Geometry:

- base spacing: 4 px with 8 px dominant rhythm;
- control radius: 6 px;
- independent panel radius: 8 px;
- slide radius: 3 px;
- outer shell radius: 12 px;
- pill radius only for badges, status dots, and segmented-selection indicators;
- no shadow on ordinary controls or rails;
- one restrained shadow on the slide canvas.

## Review Workspace

The Review Workspace uses existing stored data only.

### Session Summary

The first band shows:

- Study duration;
- interaction count;
- mean engagement;
- mean fatigue;
- top emotion and probability;
- learner-state observation coverage.

These values are compact summary facts, not a wall of cards.

### Learner State Overview

The next section shows:

- the existing eight-class session emotion distribution;
- distraction-alert duration and count;
- fatigue-alert duration and count;
- one slide-order overview row per reviewed slide containing study time, interaction count, mean engagement, mean fatigue, and top emotion.

The current Review contract stores slide-level aggregates, not raw second-by-second learner-state history. The UI uses a slide-order overview and does not imply a continuous temporal curve.

### Selected Slide Detail

The selected slide area contains:

- slide image with optional gaze heatmap;
- valid gaze duration and gaze coverage;
- AOI dwell-time list;
- slide study time;
- slide interaction count;
- mean engagement;
- mean fatigue;
- top emotion and probability;
- distraction and fatigue alert duration/count;
- heatmap PNG export.

The slide selector stays in the shared right rail. Session selection and JSON export stay in the left rail.

Every learner-state section includes `Model estimates, not a diagnosis.` Missing values render as unavailable and never as zero. Coverage is shown next to summaries so low-observation sessions are not presented as equally reliable.

## Error and Empty States

- No loaded deck: retain the built-in empty presentation and upload path inside the new shell.
- No valid gaze: show the slide and `No valid gaze captured`; hide misleading heatmap intensity.
- No learner-state observation: show `Unavailable` and coverage, not `0%`.
- Voice transport unavailable: keep target and prior answer visible; show one inline retry/status message.
- STT empty/too short: remain in the same voice panel and offer Retry.
- Tutor failure: retain transcript and target, show a bounded inline error, and allow retry without repeating gaze collection.
- Saved Review warning: keep valid sessions selectable and show the warning in the left rail.
- Palette preference failure: fall back to Ivory Study Desk without blocking Study or Review.

## Presentation Boundaries

This work may extract pure presentation helpers and static assets from `apps/streamlit_attentive_slides.py`, but it does not replace the application controller or backend contracts.

Expected boundaries:

- palette definitions and CSS-variable rendering;
- a palette-control component that owns local-storage persistence;
- base workspace CSS;
- a pure voice-panel view mapper;
- a pure Review view mapper;
- existing slide viewport and voice transport components;
- the Streamlit app remains the orchestration/composition layer.

The existing voice orchestrator, VAD, turn collector, target switching, Study Review store, learner-state trackers, gaze review renderer, Tutor agent, and provider clients remain the sources of truth.

## Privacy and Research Integrity

- No new network endpoint or external UI asset is added.
- No raw gaze, camera, or microphone payload is persisted by the UI redesign.
- Palette preference is the only new browser-local value.
- Live gaze cursor styling must not alter gaze coordinates or AOI inference.
- Learner-state values remain model estimates and are not diagnoses.
- Study Review values are displayed from existing stored aggregates; no invented interpolation or derived temporal analysis is added.

## Verification Budget

Follow the repository Lean Execution Profile:

- no baseline suite;
- no RED or expected-failing runs;
- one focused GREEN group after each checkpoint;
- if a group fails, rerun only the affected module after the fix;
- no automated browser smoke test, screenshot test, lint, type check, security scan, or performance suite;
- one independent whole-change review after all implementation checkpoints;
- one complete unit suite after review and bounded fixes;
- no repeated passing full suite;
- final visual acceptance is performed manually on Lenovo at the target resolution.

## Acceptance Criteria

- Light mode is the only designed mode; no dark/glass styling remains visible.
- Ivory Study Desk is the default palette.
- Four named palettes switch semantic component groups together and persist locally.
- Themeable custom-component iframes receive and apply the same complete semantic-token map as the parent shell.
- Palette controls are disabled during an active Study.
- Noto Serif is used for headings/editorial answer text and Noto Sans for controls.
- The top-level `Manual / Live` split is removed.
- No runtime condition depends on `main_interaction_mode`; the camera/microphone master is the sole media-service and learner-sensing gate.
- One-turn, Dialogue, and Realtime use the same Attention & Voice and Tutor explanation regions.
- Hold-to-speak supports pointer and global `V` press/release with focus and teardown safety.
- Hands-free uses the existing automatic speech detector and exposes pause/resume listening.
- Voice release/end-of-speech automatically proceeds to target resolution and answer generation.
- Confidence-based auto-confirm is the default at `0.80`; only insufficient or lower-confidence targets require confirmation.
- The `Generate grounded answer` button is absent.
- AOI says `Sampling attention` during speech and locks only after dwell-weighted turn aggregation.
- Insufficient gaze evidence requests target confirmation before generation.
- The live gaze cursor is low-chroma, highly transparent, softly diffused, non-animated, and not blue.
- The slide defaults to 70%, aligns with the main grid, and does not dominate the viewport.
- Slides use a persistent right rail with a smaller collapse control.
- Review shows session summary, learner-state overview, slide heatmap, AOI dwell, and slide learner-state detail.
- Review includes duration, interaction count, engagement, fatigue, emotion, alert duration/count, and coverage from existing data.
- No backend architecture rewrite or new learner-state analytics are introduced.
- Focused checkpoint groups and the final full unit suite pass.

## Open Questions

None.
