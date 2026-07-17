# AttentiveSlides 02-Aligned Study and Review UI Design

**Status:** Approved direction, implementation-ready

**Date:** 2026-07-17

**Target branch at authoring:** `codex/gaze-heatmap-review`

**Target host:** `LenovoLinux_Dorm`

**Primary demo environment:** desktop Chromium, physical `2560x1600`, approximately 160% X11 scaling (effective viewport near `1600x1000`), light mode only

## 1. Decision and Authority

This document defines the next UI refinement of AttentiveSlides. It deliberately moves the implemented Study Workspace toward the approved **02 / Cool Instrument Panel** reference while retaining the approved multi-palette behavior and all working voice, gaze, Tutor, and Review capabilities.

This document supersedes the following parts of `docs/superpowers/specs/2026-07-17-attentiveslides-study-review-ui-redesign-design.md`:

- the Noto-only typography decision;
- the 6/8/12 px rounded-card geometry;
- the loose Streamlit two-column composition that allowed the slide toolbar, interaction panel, and right rail trigger to drift;
- the statement that a Study pause lifecycle is out of scope;
- any visual direction that conflicts with the 02 reference's strict grid, compact type scale, square controls, or editorial Tutor output.

The earlier specification remains authoritative for the following behavior unless this document explicitly changes it:

- four light palettes and local preference persistence;
- palette lock during an active or paused study;
- Conversation flow values (`One-turn`, `Dialogue`, `Realtime`);
- Speaking control values (`Hold to speak`, `Hands-free`);
- `V` hold-to-speak safety rules;
- gaze/AOI aggregation and confidence behavior;
- automatic answer generation after target resolution or confirmation;
- low-salience gaze cursor intent;
- learner-state and gaze evidence included in Review;
- no backend architecture rewrite or analytics expansion.

If an implementation detail remains ambiguous, use this priority order:

1. Preserve verified application behavior and data integrity.
2. Match the hierarchy, proportions, typography, density, and control treatment of 02.
3. Preserve the approved palette system and voice/gaze interaction rules.
4. Prefer a small, explicit implementation over another abstraction layer.

## 2. Durable Visual References

The implementation must not rely on the original `.superpowers/brainstorm` directory or a chat screenshot surviving. The following files are committed with this specification:

- `docs/superpowers/specs/references/02-cool-instrument-panel.html` — canonical 02 markup.
- `docs/superpowers/specs/references/attentiveslides-concepts.css` — canonical 02 styling used by that HTML.
- `docs/superpowers/specs/assets/attentiveslides-02-reference.png` — approved reference at 2204×1392.
- `docs/superpowers/specs/assets/attentiveslides-4060-before.png` — 4060 implementation before this refinement at 2848×1464.

During implementation, inspect both the rendered HTML and screenshot. From the repository root on the 4060, the reference can be served without modifying application code:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m http.server 8765 \
  --directory docs/superpowers/specs/references
```

Then open `http://127.0.0.1:8765/02-cool-instrument-panel.html`. This is a design reference, not production code to copy wholesale. Production remains Streamlit plus the existing local custom components.

## 3. What Is Wrong in the Current 4060 UI

The current result contains much of the right functionality, but its composition does not reproduce the approved design language.

| Area | Current 4060 result | Required 02-aligned result |
|---|---|---|
| Product identity | `AttentiveSlides` is absent from the visible app top bar; Streamlit/Deploy chrome dominates | A persistent product cell with the `A` mark and serif `AttentiveSlides` title anchors the upper-left |
| Study context | `Study Workspace`, slide count, and Start action float as separate Streamlit rows | One compact top bar contains workspace, lesson/deck context, slide position, lifecycle status, Pause/Resume, and End & Review |
| Slides navigation | The expanded rail is on the right, but the collapsed trigger can appear in normal left-side flow and its proportions are inconsistent | A fixed right `DECK INDEX` rail mirrors the left rail; a small `×` collapses it and a fixed right-edge tab reopens it |
| Slide scale | A full-width red Streamlit slider consumes a row; the slide is shrunk inside an already narrow column | A compact `− 70% + FIT` toolbar sits directly above a left-aligned slide; the slide column itself remains dominant |
| Interaction panel | Large `Attention & Voice`, nested state cards, repeated Target headings, and many diagnostic captions create a long card | A narrow numbered `① CONTROL` instrument panel uses one highlighted state block, one primary voice action, and only actionable secondary controls |
| Diagnostic copy | Camera/microphone off, attention-source location, whole-slide selection, target-ready count, and raw matched IDs are always visible | Remove routine diagnostic prose; expose detail only inside Advanced/System Status when needed |
| Tutor response | The answer is visually detached and card-like | `② TUTOR OUTPUT` is an editorial panel directly below the slide, with compact actions and serif answer text |
| Typography | Noto typography, large headings, and default Streamlit widget text produce a generic app/dashboard feel | Literata for identity, panel headings, and Tutor prose; IBM Plex Sans for controls, metadata, and labels; compact scale from 10–16 px |
| Geometry | Repeated 6–12 px rounding makes nearly every area a card | Square shell and rails; 2–4 px controls/panels; round only status dots, tiny badges, and truly pill-shaped indicators |
| Information density | Wide padding and repeated helper text make key actions fall below the fold | 02-like tight rhythm, stable alignment, and progressive disclosure keep the complete working loop visible |

The redesign is therefore an information-architecture and composition correction, not a palette-only reskin.

## 4. Design Character

The product should feel like a calm academic instrument: precise enough for research, warm enough for extended reading, and quiet enough not to compete with the slide.

Use:

- thin borders and flat background planes for hierarchy;
- a strict four-zone shell: left settings rail, slide/output workspace, control panel, right deck rail;
- editorial serif only where reading hierarchy benefits;
- compact uppercase sans-serif labels for operational metadata;
- tabular numerals for time, slide counters, confidence, and calibration;
- a restrained slide-only shadow;
- small status color accents that retain a text label.

Do not use:

- glassmorphism, backdrop blur, gradients, translucent cards, decorative animation, or floating dashboard tiles;
- large hero headings inside operational panels;
- rounded containers around every section;
- raw internal identifiers or provider terminology in the normal learner path;
- multiple simultaneous status banners that say the same thing.

## 5. Typography

### 5.1 Families

- **Display/editorial:** `Literata`, fallback `Noto Serif`, `DejaVu Serif`, serif.
- **Interface/metadata:** `IBM Plex Sans`, fallback `Noto Sans`, `DejaVu Sans`, sans-serif.

Font files must be vendored and installed locally for the Lenovo demo; the app must make no runtime request to Google Fonts, jsDelivr, a CDN, or any third-party host. Preserve license files and source provenance. The implementation plan names exact assets and installation checks.

### 5.2 Type scale at the effective 1600×1000 viewport

| Role | Family | Size / line height | Weight / treatment |
|---|---|---:|---|
| Product identity | Literata | 16 px / 20 px | 650–700 |
| Main panel heading (`CONTROL`, `TUTOR OUTPUT`) | Literata | 16 px / 20 px | 650–700 |
| Sidebar lesson title | Literata | 18 px / 21 px | 650–700 |
| Section heading | Literata | 14 px / 18 px | 650 |
| Tutor answer | Literata | 15 px / 22 px | 450–600, emphasis may use primary color |
| Primary button | IBM Plex Sans | 11 px / 15 px | 650, uppercase only for short instrument actions |
| Normal control text | IBM Plex Sans | 12 px / 17 px | 450–550 |
| Top-bar context | IBM Plex Sans | 11 px / 16 px | 500 |
| Eyebrow / field label | IBM Plex Sans | 10 px / 13 px | 650, uppercase, 0.06–0.09 em tracking |
| Caption / metadata | IBM Plex Sans | 10 px / 14 px | 450, muted |

Do not reduce interactive text below 11 px. Streamlit labels that cannot be safely restyled retain 12 px rather than becoming illegible.

## 6. Geometry and Shell

### 6.1 Root geometry

At the effective target viewport:

- top bar: 52 px high;
- left rail: 226 px wide;
- right deck rail: 190 px wide;
- control column: 292 px wide;
- central gutter: 12 px;
- canvas padding: 16 px horizontal and 14 px vertical;
- Tutor output row: approximately 176–196 px minimum height, growing with content;
- shell radius: 0–2 px;
- panel radius: 2 px;
- control radius: 2–4 px;
- slide/thumbnail radius: 0 px.

The normal open state follows this conceptual grid:

```text
┌──────────────────┬───────────────────────────────────────────────┬──────────────┐
│ A AttentiveSlides│ STUDY / WORKSPACE · lesson · 06—18 · ACTIVE  │ DECK INDEX   │ 52
├──────────────────┼───────────────────────────────┬───────────────┼──────────────┤
│ Lesson + settings│ slide toolbar + slide canvas  │ ① CONTROL     │ thumbnails   │
│                  ├───────────────────────────────┤               │              │
│                  │ ② TUTOR OUTPUT                │               │              │
└──────────────────┴───────────────────────────────┴───────────────┴──────────────┘
       226 px                  fluid                     292 px          190 px
```

The implementation keeps the native Streamlit sidebar as the left rail; it does not fake a second sidebar inside the main column. The shell is assembled from three fixed 52 px header cells sharing the same viewport baseline:

- `main_sidebar_brand` is the first keyed sidebar container, fixed at viewport `left: 0; top: 0; width: 226px; height: 52px`;
- `main_topbar` is fixed/sticky over the main document from `left: 226px` to the open right-rail edge;
- the `main_slide_rail` begins at `top: 0`, and its first 52 px is the `DECK INDEX` header cell; thumbnails begin below it.

Native sidebar content begins below the brand cell. Main content begins below the central top bar. The native sidebar stays expanded in the desktop demo. When the deck rail collapses, only the central top bar expands to the right edge and the fixed reopen tab remains below it. Default Streamlit top padding, header spacing, column gaps, and widget margins must not create extra rows between these zones.

### 6.2 Responsive boundary

Desktop only. Between roughly 1280 and 1600 effective pixels:

- keep both rails and the control column visible;
- allow the slide column to contract first;
- never move the control panel below the slide;
- never transform the right rail into a left-side button;
- allow the right rail to be intentionally collapsed by the user.

Below that boundary, graceful compression is sufficient; a mobile reflow is not required.

## 7. Top Bar

The top bar is part of the application, not the default Streamlit header.

### 7.1 Left product cell

- 32×32 muted primary square with a white/ivory `A` serif mark;
- `AttentiveSlides` in Literata 16 px;
- a vertical border aligns with the left-rail boundary.

### 7.2 Context cell

One line in this order:

`STUDY / WORKSPACE  ·  {deck or lesson title}  ·  {current slide:02d}—{total:02d}`

Use the real loaded deck title. If no deck is loaded, use `Study Workspace` and `00—00`; do not invent `Selective Attention` in production. Long titles truncate with an accessible title/tooltip.

### 7.3 Lifecycle actions

The top bar is the correct place for study lifecycle state because it is global and must stay visible while the learner works.

| Lifecycle | Status | Primary control | Secondary control |
|---|---|---|---|
| Idle | `READY 00:00` | `START STUDY` | none |
| Active | green dot + `ACTIVE 18:42` | `PAUSE` | outlined warm `END & REVIEW` |
| Paused | amber dot + `PAUSED 18:42` | `RESUME` | outlined warm `END & REVIEW` |
| Review | `REVIEW · 18:42 STUDIED` | `BACK TO STUDY` | session actions remain in Review rail |

`End & Review` is available while paused. Status never relies on color alone. Buttons use compact instrument proportions: approximately 34–38 px high, 10–14 px horizontal padding, square 2 px radius.

### 7.4 Streamlit chrome

Keep essential Streamlit functionality accessible, but hide or de-emphasize `Deploy` and the default header so it cannot visually replace the product bar in the recorded demo. Do not use brittle CSS that removes the application menu if it is required for development; demo chrome may be controlled with Streamlit configuration when available.

## 8. Left Settings Rail

The left rail remains the configuration surface, but it adopts 02's hierarchy and progressive disclosure.

### 8.1 Always visible

1. `LESSON / {number}` eyebrow, real deck title, optional subject.
2. `RUNTIME CONFIGURATION` eyebrow.
3. Conversation flow segmented control: `1 turn`, `Dialogue`, `Realtime`.
4. Speaking control segmented control: `Hold`, `Hands-free`.
5. Attention source select.
6. Answer profile / answer audio only when meaningful.
7. Camera and microphone master control.
8. Palette control, visible but disabled during Active and Paused.

### 8.2 Collapsed by default

- upload/deck replacement after a deck is already loaded;
- participant/calibration details;
- privacy and cloud-permission details;
- conversation context/history controls;
- provider/engine selection;
- system status and raw diagnostics;
- active deck manifest details.

These belong under compact expanders such as `DECK`, `PARTICIPANT`, and `ADVANCED`. The normal study view should not read like a setup form.

### 8.3 Behavior

- Study flow and speaking selections remain locked while a turn is actively recording/resolving/answering.
- The full Study Pause also makes runtime interaction controls read-only until Resume.
- Typed input remains available when media is simply off, but not while the whole Study is paused.
- Palette preference remains locally remembered and defaults to `Ivory Study Desk`.

## 9. Slide Workspace

### 9.1 Compact toolbar

Directly above the slide:

- left: `CANVAS / SLIDE {current:02d}`;
- right: `−`, current scale (`70%`), `+`, `FIT`;
- a compact Learner State status/popover may sit immediately before the scale controls, never as a full-width button or separate row.

Replace the red full-width Streamlit slider. The default remains 70%; controls step through the existing allowed scale range. `FIT` computes the largest scale that fits the current slide stage without horizontal overflow. The displayed percent reports the actual stage scale.

### 9.2 Slide canvas

- left-aligned, not centered in an oversized blank area;
- consumes most of the fluid column;
- white/ivory slide surface with one restrained shadow;
- previous/next navigation is small and peripheral;
- no additional rounded container around the slide;
- preserve the existing slide viewport component, AOI overlay, selection coordinates, and gaze mapping.

The desired result is not “make the rendered slide tiny.” The 70% label is a presentation scale inside a correctly sized dominant slide column. Avoid double-shrinking through both a small column ratio and CSS width percentage.

## 10. `① CONTROL`: Unified Attention and Voice Panel

Rename the visible panel from `Attention & Voice` to the numbered 02-style heading `① CONTROL`. Keep an accessible label such as `Attention and voice controls`.

### 10.1 Fixed hierarchy

The panel always uses this order:

1. header row: circled `1`, `CONTROL`, compact status badge (`READY`, `LOCKED`, `PAUSED`, `ERROR`);
2. one primary state block with the active target or state;
3. compact input readiness row and waveform/level affordance when media is active;
4. primary voice action (`HOLD TO SPEAK`, `STOP`, `PAUSE LISTENING`, or `RESUME LISTENING`);
5. typed input, visually secondary;
6. target source and listening behavior controls only when actionable;
7. small actions (`EDIT TARGET`, `CLEAR`, `RETRY`) when relevant.

The panel spans the slide row and Tutor output row so its vertical edge remains stable, as in 02. It does not grow and shrink because routine diagnostics appear.

### 10.2 Copy policy

Remove these normal-path messages entirely:

- `Camera and microphone are off. Typed input remains available.`
- `Attention regions are controlled from the left settings rail.`
- `The complete slide is selected.`
- `Target ready · Slide 5 · 1 AOI match(es)`
- `Matched: whole_slide`

The UI already communicates those facts through control state. Raw AOI IDs, match counts, transport status, and device diagnostics remain available in Advanced/System Status or genuine error details.

Use only short, actionable state copy:

- `Ready · Hold V or the button to speak`
- `Listening for speech`
- `Sampling attention`
- `Transcribing`
- `Target needs confirmation`
- `Answering`
- `Study paused`
- concise, actionable retry errors.

Do not show a success banner for a normal whole-slide target. The state block may simply show:

```text
WHOLE SLIDE
SLIDE 05 · CURRENT TARGET
```

or, for an AOI:

```text
Stimulus salience
REGION 04 · 2.8 SECONDS
```

### 10.3 Mode consistency

Conversation flow changes behavior, not layout:

- `1 turn`: one grounded turn without supplied history.
- `Dialogue`: bounded local conversation history; show a compact `HISTORY {n}` indicator and clear action only when needed.
- `Realtime`: provider-owned persistent conversation and barge-in behavior; provider details stay Advanced.

Speaking control also changes behavior, not panel structure:

- `Hold`: pointer or global safe `V` PTT; release submits automatically; no Generate Answer button.
- `Hands-free`: automatic speech detection; primary action toggles listening.

Existing turn-boundary AOI rules remain unchanged. PTT freezes the resolved evidence window at release; Hands-free freezes it at the detected last speech frame. Full Study Pause is separate and stops both paths.

## 11. `② TUTOR OUTPUT`

The Tutor output occupies the lower cell under the slide only; the Control panel continues beside it.

Header row:

- circled `2` and `TUTOR OUTPUT` at left;
- compact actions at right: `REPLAY`, `FOLLOW-UP`, `SAVE NOTE` when supported;
- omit actions that are not wired rather than render decorative buttons.

Body:

- Literata 15/22;
- first grounded clause may use the primary muted green emphasis;
- no nested answer card inside the panel;
- metadata (`SLIDE 06 + NOTES`, latency, confidence) sits on one muted 10 px line;
- Dialogue history is collapsed beneath the current output and does not push the primary answer out of view.

Empty state is one restrained line: `Ask about the slide to begin.` Errors replace the answer body and include only an actionable retry when safe.

## 12. Fixed Right `DECK INDEX` Rail

The right rail is always on the right and open by default.

- top bar cell: `DECK INDEX` plus `{current:02d} / {total:02d}`;
- rail header: `DECK / {total:02d}` plus a small 32×32 maximum `×` button;
- independent vertical scrolling;
- 16:9 thumbnail surface, slide number to the left or above;
- selected thumbnail receives a 2 px primary outline;
- current thumbnail scrolls into view on navigation;
- collapse stores only session state, not palette preference.

When collapsed:

- the central workspace expands into the released 190 px;
- a narrow fixed `SLIDES` or icon tab remains at the extreme right below the top bar;
- the trigger must never participate in the Streamlit document flow or appear beside the left rail.

Review uses the same rail to select the slide detail being inspected.

## 13. Full Study Pause Lifecycle

The user approved a complete Pause, not merely `Pause listening`.

### 13.1 Paused behavior

Pressing `PAUSE` must atomically:

- freeze active-study elapsed time;
- stop gaze and learner-state accumulation;
- stop/cancel an active PTT turn safely;
- stop Hands-free and Realtime voice capture/session behavior;
- stop new answer generation and prevent new typed requests;
- disable interaction, target editing, navigation that would mutate study context, and runtime preference changes;
- preserve the current slide, resolved target, current Tutor output, dialogue history, palette, and Review accumulator identity;
- set the top bar to `PAUSED {active elapsed}` and the primary action to `RESUME`;
- present one quiet `Study paused` state in Control, not multiple warnings.

The Pause guarantee is enforced server-side as well as in disabled UI. Before stopping voice, the service closes a command gate so new PTT/Hands-free/target-confirm start commands are rejected; stop/cancel commands remain allowed. Runtime/media stop runs in a `finally` path even if provider voice stop fails. A stop error leaves the Study paused and the command gate closed, with a recoverable error shown outside the normal Control copy.

Pausing must not discard a completed answer or delete the media master preference. Runtime capture may be stopped while paused, then reconciled from the preserved preference on Resume.

### 13.2 Resume behavior

Pressing `RESUME` must:

- continue the same Study Review session ID;
- resume active elapsed time without counting the paused interval;
- restart gaze/learner accumulation for the latest valid slide/AOI context;
- restore the prior media/voice mode only if the visible camera/microphone master preference is enabled;
- return Control to the appropriate ready/listening state;
- avoid replaying or double-recording the prior interaction.

### 13.3 Finish while paused

`END & REVIEW` uses the same quiesce path from both Active and Paused. It closes the Study lifecycle to new records, closes the server-side voice command gate, stops runtime/media, and only then saves/routes to Review. Finishing while paused includes the currently open interval in `paused_seconds`. A save failure leaves `finish_pending` with media/voice closed and exposes a safe retry of the same frozen session. The Review's Study duration is active time, not wall-clock time.

### 13.4 Timing contract

Use a monotonic clock for interval math and epoch timestamps for persistence. Add `paused_seconds` as a backward-compatible persisted field with default `0.0`; old Review JSON remains readable. Compute:

```text
active_seconds = max(0, ended_at_epoch - started_at_epoch - paused_seconds)
```

The lifecycle snapshot exposes `idle`, `active`, `paused`, or `finish_pending`, a stable `active_seconds`, and a monotonic lifecycle revision. Gaze, learner observations, and interactions received while paused or finish-pending are ignored/rejected consistently. Proposal, generation, interaction-log, and answer-playback commits carry the current `(session_id, lifecycle revision)` token; Pause/Resume/Finish changes the revision, so a late pre-transition result cannot be committed after Resume.

### 13.5 User Pause versus technical media gaps

The existing media ingress closes gaze/learner observation intervals when a browser session is replaced, stale, or disconnected. Those technical gaps must not become a user-visible full Study Pause. The implementation therefore uses separate APIs:

- user lifecycle: `pause()` / `resume()`, which changes `active` ↔ `paused` and the top bar;
- technical gap: `mark_observation_gap(now)`, which closes the current gaze/learner observation interval but leaves the Study lifecycle active.

Every current ingress call that uses `study_review.pause()` for replacement/readiness/cleanup is migrated to `mark_observation_gap()` before `pause()` gains full lifecycle meaning.

## 14. Low-Salience Gaze Cursor

Retain the approved neutral cursor treatment:

- 10×10 px;
- fill `rgba(72, 84, 78, 0.16)`;
- edge `1px solid rgba(72, 84, 78, 0.18)`;
- diffusion `0 0 8px 5px rgba(72, 84, 78, 0.08)`;
- no white outline, blue center, dark shadow, pulse, trail, or palette-primary color;
- preserve the existing 1000 ms stale clear and all coordinate mapping.

This cursor should be noticeable only when the learner intentionally looks for it. AOI confirmation and Review heatmaps remain more legible and visually distinct.

## 15. Palette System

Preserve the implemented semantic palette registry and local storage key `attentiveslides-ui-palette-v1`:

- `Ivory Study Desk` — default;
- `Autumn Reading Room`;
- `Cool Archive`;
- `Dusty Blue`.

Palette changes update the grouped semantic surfaces together: canvas, workspace, top bar, rails, surface, ink, muted text, borders, primary actions, segments, and slide selection accents. Status colors, gaze cursor, AOI geometry, and heatmap colors remain invariant.

The palette selector stays visible in the left rail and locally remembers the last user selection. It is disabled from Start through Active and Paused, and becomes editable again only in Idle or Review. No dark-mode branch is introduced.

## 16. Review Workspace

Review receives the same visual system, typography, rails, and compact top bar. It is not redesigned into a separate dashboard style.

Review is a non-capture workspace. Entering it—whether from End & Review or by opening a saved session—quiesces media and voice while preserving the user's media preference. `BACK TO STUDY` restores the service from that preference before returning to the Study Workspace.

### 16.1 Top-level hierarchy

1. compact session identity and active Study duration;
2. one metric band with Study time, slides viewed, interactions, AOI coverage, learner-state coverage;
3. slide timeline/list in deck order;
4. selected slide detail with screenshot/heatmap and AOI dwell;
5. learner-state evidence for emotion, fatigue, and engagement.

### 16.2 Learner-state content

The Review must include the data already present in the learner-state store:

- top emotion and probability when available;
- fatigue level/score and fatigue-alert entries;
- engagement availability and state distribution;
- observed duration and coverage per modality;
- Study duration and interaction count;
- clear `Unavailable` / `Not observed` presentation without fabricating zero.

These metrics belong in Session Summary and the selected-slide detail. Do not introduce second-by-second charts or raw biometric persistence.

### 16.3 Visual form

- summary is a horizontal instrument band, not a row of floating rounded KPI cards;
- labels are 10 px uppercase; values use tabular numerals;
- section titles use Literata 16 px;
- selected slide and AOI list use thin rules and one accent edge;
- heatmap legend remains legible but visually secondary;
- deletion stays under a collapsed destructive section;
- JSON export and session selection remain functional.

Review durations and coverage denominators use active Study time after the Pause implementation. Older sessions with no `paused_seconds` behave exactly as before.

## 17. Accessibility and Interaction Quality

- Maintain visible 2 px focus indicators using the palette primary.
- All icon-only controls have `aria-label` or Streamlit help text.
- Status includes words, not color alone.
- Buttons remain at least 32 px high in compact desktop mode.
- Truncated deck/lesson titles expose the full text.
- `V` PTT continues to ignore editable/control focus, modifiers, repeats, hidden pages, and unsafe teardown.
- Full Pause disables controls semantically, not only through opacity or pointer-events.
- Native controls and local component DOM remain keyboard reachable.
- Avoid continuous animation; wave/level feedback may update only while actually listening.

## 18. Performance and Dependency Boundaries

This design does not require glass effects or expensive filters. The only blur-like visual is the tiny, static CSS diffusion around the gaze cursor. It is negligible compared with camera, gaze, and model processing.

Do not add a UI framework, icon package, chart package, animation library, or remote font loader. Reuse Streamlit, existing custom components, CSS variables, and small inline SVG/CSS where necessary. Do not rewrite voice, gaze, or Review architecture merely to obtain the layout.

## 19. Explicit Non-goals

- Dark mode or automatic OS theme following.
- Mobile/tablet layout.
- Provider, gaze-model, VAD, AOI-ranking, grounding, or learner-model changes.
- A new analytics pipeline or raw biometric storage.
- Full application architecture refactor.
- Decorative glass, gradients, large shadows, or animated backgrounds.
- Pixel-perfect duplication of placeholder slide content from the 02 concept.
- Showing raw system diagnostics in the normal learner path.

## 20. Visual Acceptance Checklist

At the target 4060 viewport, the implementation is visually acceptable only if all are true:

- `AttentiveSlides` is clearly visible in the upper-left product cell.
- `STUDY / WORKSPACE`, real lesson/deck context, slide index, active timer, Pause/Resume, and End & Review share one compact top bar.
- The left settings rail, central slide, `① CONTROL`, and right `DECK INDEX` read as one aligned shell.
- The deck rail is on the right in both open and collapsed states; its close button is visibly smaller than before.
- The slide is dominant and left-aligned; it is not double-shrunk or separated from its toolbar by a full-width slider.
- `① CONTROL` resembles the 02 reference in heading size, borders, spacing, state block, and primary action.
- Routine diagnostics and raw AOI identifiers listed in section 10.2 are absent.
- `② TUTOR OUTPUT` sits beneath the slide with editorial serif text.
- Literata and IBM Plex Sans are actually resolved on the Lenovo host, with fallbacks retained.
- Corners are predominantly square/2–4 px, not soft 8–12 px cards.
- Ivory Study Desk remains the default and palette switching still updates grouped components.
- Pause freezes Study time, gaze, learner state, and every voice path, while Resume preserves session context.
- Review shows active duration, interaction count, gaze, emotion, fatigue, engagement, and modality coverage with the same visual language.
- The gaze cursor remains neutral, translucent, and non-animated.

Functional completeness without this hierarchy is not sufficient, and visual similarity that breaks existing voice/gaze/Review contracts is also not sufficient.
