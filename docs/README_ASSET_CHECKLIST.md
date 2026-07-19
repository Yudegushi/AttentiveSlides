# README Asset Checklist

This checklist defines the public screenshots and brand assets planned for the
AttentiveSlides README. Capture real application states from the current main
application; do not substitute mock interfaces or historical demos.

## Capture rules

- Use a synthetic or redistributable PDF with no student, course, institution,
  or account information.
- Remove browser chrome unless it explains an interaction.
- Hide local paths, hostnames, IP addresses, API configuration, terminal output,
  provider identifiers, and debug overlays.
- Do not show faces, camera frames, transcripts from real participants, or raw
  gaze points.
- Use the default cream, ochre, sage, and charcoal palette.
- Prefer PNG for static UI captures and an optimized GIF for short interaction
  sequences. Keep text legible at GitHub's rendered width.

## README screenshots

### `.github/assets/hero-workspace.png`

- **UI state:** Main AttentiveSlides workspace with a sample PDF open, one slide
  visible, the deck rail collapsed, Manual mode selected, and the tutor panel
  showing a short grounded answer with its source/reliability summary. Do not
  show settings or debug controls.
- **Recommended size:** 1600 × 900 px (16:9).
- **Caption:** "Study a slide, confirm the intended region, and ask a grounded
  tutor in one workspace."
- **Alt text:** "AttentiveSlides workspace with a presentation slide, confirmed
  target, and grounded tutor answer."
- **Hide:** PDF filename if private, local paths, API status details, account
  data, timestamps tied to a participant, and browser camera permission UI.

### `.github/assets/demo-grounding.gif`

- **UI state:** A 6–10 second loop: select or propose a slide region, show the
  confirmation/correction step, submit a concise question, then reveal the
  grounded answer and reliability state. Use Manual mode so the interaction is
  reproducible without exposing camera input.
- **Recommended size:** 1280 × 720 px, 12–18 fps, under 8 MB if practical.
- **Caption:** "From visual reference to learner confirmation to a source-backed
  answer."
- **Alt text:** "Animated AttentiveSlides flow from target proposal and learner
  confirmation to a grounded tutor answer."
- **Hide:** Cursor trails that resemble raw gaze, real user queries, provider
  payloads, latency/debug counters, filenames, and desktop notifications.

### `.github/assets/feature-confirmation.png`

- **UI state:** Target proposal card over a slide with the primary candidate,
  confidence/reason summary, visible alternatives, and confirm/correct controls.
  Use neutral synthetic content and a deliberately ambiguous target so the
  learner-control boundary is clear.
- **Recommended size:** 1400 × 900 px.
- **Caption:** "Gaze or manual evidence proposes; the learner confirms or
  corrects."
- **Alt text:** "AttentiveSlides target proposal showing confidence,
  alternatives, and learner confirmation controls."
- **Hide:** Raw coordinate values, calibration diagnostics, camera frames,
  model-internal output, and participant identifiers.

### `.github/assets/feature-grounded-tutor.png`

- **UI state:** A completed tutor turn with the confirmed AOI still visible,
  the answer, source references, reliability label, and a corrective action if
  evidence is incomplete. Keep the answer short enough to fit without scrolling.
- **Recommended size:** 1400 × 900 px.
- **Caption:** "Tutor responses remain tied to confirmed slide evidence."
- **Alt text:** "Grounded tutor answer beside the confirmed slide region with
  source and reliability information."
- **Hide:** Full prompts, hidden reasoning, provider request/response data, API
  keys, request IDs, and private document content.

### `.github/assets/feature-live-voice.png`

- **UI state:** Live mode with the compact voice panel ready or listening, a
  confirmed target locked for the turn, and clear microphone/session status.
  Prefer a staged state before transcription so no real speech appears.
- **Recommended size:** 1400 × 900 px.
- **Caption:** "Use push-to-talk or continuous speech without bypassing target
  confirmation."
- **Alt text:** "AttentiveSlides Live mode voice controls with a confirmed slide
  target and session status."
- **Hide:** Camera preview, faces, real transcripts, device names, network
  endpoints, API/provider identifiers, and operating-system permission dialogs.

### `.github/assets/feature-study-review.png`

- **UI state:** Study Review for a synthetic completed session, showing the
  slide heatmap, study-time summary, AOI dwell summary, and learner-state
  aggregates with uncertainty language visible. Use generated interaction data.
- **Recommended size:** 1600 × 1000 px.
- **Caption:** "Review derived study patterns without storing raw camera, audio,
  face crops, or gaze points."
- **Alt text:** "AttentiveSlides Study Review with a gaze heatmap and aggregated
  study signals for a synthetic session."
- **Hide:** Session IDs, filesystem paths, raw coordinates, real participant
  data, transcripts, face crops, and export destinations.

## Logo design brief

### Core idea

Create an original, vector-friendly mark that combines:

1. a rounded presentation slide as the primary silhouette;
2. a subtle focus marker identifying one part of the slide;
3. a dialogue/voice symbol whose resolved endpoint also communicates learner
   confirmation.

The mark should communicate slide learning, visual reference, voice, and
confirmation without implying surveillance or diagnostic certainty.

### Visual direction

- **Style:** restrained geometric flat design with soft corners, balanced
  negative space, and consistent medium-weight strokes.
- **Palette:** warm cream background, ochre focus accent, muted sage
  speech/confirmation accent, and charcoal structure. It must remain legible in
  monochrome.
- **Composition:** one strong silhouette with no more than three internal visual
  ideas; recognizable at 32 px.
- **Typography:** no generated text inside image assets. A future horizontal
  wordmark should pair the mark with editable repository-rendered text.

### Avoid

- realistic or stylized eyes;
- surveillance cameras or tracking reticles aimed at a person;
- robot heads, glowing brains, stars, sparkles, or generic AI circuitry;
- purple/blue AI gradients, neon glow, glassmorphism, or 3D rendering;
- tiny landmarks, dense waveforms, generated letters, watermarks, or mockups.

### Required variants

| Variant | Planned output | Notes |
|---|---|---|
| Approved source | `.github/assets/attentiveslides-logo-generation-master.png` | Original 1254 × 1254 AI generation selected as the authoritative current artwork |
| Square mark | `.github/assets/attentiveslides-logo.png` | Transparent-background derivative of the approved source under the stable README asset name |
| Editable vector source | Maintainer-supplied later | Create only from a faithful manual redraw that preserves the approved artwork |
| Horizontal wordmark | Maintainer-supplied later | Combine the mark with editable "AttentiveSlides" text; do not generate lettering |
| Favicon | Maintainer-supplied later | Simplify to slide + focus/confirmation at 32 px and 16 px |
| Light background | Derived from source | Charcoal outline on warm cream |
| Dark background | Maintainer-supplied later | Cream structure with restrained ochre/sage accents |

### Acceptance checks

- The image is original and has no text or watermark.
- The generation master is the authoritative approved artwork until a faithful
  editable vector source is created and reviewed.
- The square mark reads clearly at 32 × 32 px and on both white and cream.
- The mark does not resemble an eye, camera, robot, or medical symbol.
- Stroke widths and corner radii remain coherent after downscaling.
- The transparent PNG has clean edges and enough internal padding for GitHub.

### Current logo assets

- `attentiveslides-logo-generation-master.png`: authoritative 1254 × 1254 AI
  original selected by the maintainer.
- `attentiveslides-logo.png`: transparent-background derivative used by the
  README. Fully opaque artwork pixels retain the approved original's RGB data;
  only the extracted antialiased boundary uses a soft alpha matte.
- The rejected SVG redraw has been removed; no vector file is currently
  presented as canonical.
- Horizontal wordmark, favicon-specific exports, and a dedicated dark-background
  variant remain maintainer-supplied derivatives.

## README integration status

Until an asset is complete and reviewed, the README must use an HTML TODO
comment at its intended location instead of a broken Markdown image link.
