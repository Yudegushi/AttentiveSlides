# AttentiveSlides System Features

## Purpose of this document

This is the canonical, implementation-backed inventory of AttentiveSlides.
It is the source material for the project README, presentation slides, and
technical report. It describes durable system behavior rather than branch
history or checkpoint logs.

The production baseline is `apps/streamlit_attentive_slides.py`, launched
through `scripts/run_live_single_port.py`. Diagnostic and mock applications
are identified separately and must not be presented as the main product.

## 1. Project definition

AttentiveSlides is a human-centered AI learning assistant for slide-based
study. It combines an uploaded PDF, an explicit learning intent, and coarse
visual-reference evidence to help a learner ask questions such as
"explain this" without manually describing the region they are looking at.

The core interaction claim is:

> A low-cost gaze-and-voice loop can make slide tutoring more natural when
> uncertainty is visible and the learner can confirm or correct the target.

### Capability boundaries

The system deliberately does not claim:

- clinical, psychological, or educational diagnosis;
- accurate emotion, cognition, attention, or comprehension measurement;
- research-grade or pixel-perfect eye tracking;
- that a model prediction is ground truth about the learner;
- that an AI answer is supported when its slide evidence cannot be validated.

Gaze, facial state, engagement, and fatigue outputs are interface signals and
review aids. Target confirmation and source-grounded answers remain the
authoritative controls.

## 2. End-to-end product flow

```text
PDF or built-in deck
  -> slide rendering, text extraction, and AOI generation
  -> learner selects Manual or Live interaction
  -> explicit intent from text, quick action, PTT, or continuous speech
  -> target evidence from a manual region, whole slide, gaze grid, or point gaze
  -> target proposal with confidence and alternatives
  -> learner confirmation or correction
  -> slide-grounded tutor context and answer
  -> sanitized XAI, conversation history, and interaction log
  -> optional TTS or persistent realtime voice
  -> optional Study Review with heatmap and learner-state aggregates
```

The confirmation boundary is central: gaze may propose a target, but it does
not silently replace a learner-confirmed target. Target changes during a
conversation create a new proposal that must be accepted or rejected.

## 3. Operating modes

| Mode | Inputs | Target source | Tutor path | Privacy behavior |
|---|---|---|---|---|
| Manual | Uploaded PDF, typed text, quick actions | Drawn region, selected AOI, or whole slide | Confirmed Grounded Tutor | Camera and microphone are not required |
| Live — Grounded Tutor | Browser camera/microphone, STT, gaze evidence | Local point gaze with grid/manual fallback | Confirmation-gated single-turn tutor, optional TTS | Raw media stays in bounded memory queues |
| Live — Omni | Browser microphone and the same confirmed target | Locked confirmed target; explicit switch proposals | Persistent DashScope realtime session | Provider session resets at explicit context boundaries |
| Review | Completed Study session | Persisted derived grid and AOI dwell | No new tutoring target | No raw gaze, face crop, video, or audio is persisted |

## 4. User interface and study workspace

### User-facing capabilities

- Upload a PDF and retain its page count, slide images, extracted text, and AOIs.
- Navigate using previous/next controls or the lazily hydrated slide index.
- Resize or fit the current slide while keeping target geometry aligned.
- Show or hide canonical AOI overlays and the low-salience live gaze cursor.
- Open and collapse the settings rail and deck-index rail independently.
- Select Manual or Live interaction without changing the deck workflow.
- Start, pause, resume, finish, and review a Study session.
- Choose a visual palette while preserving accessible semantic status colors.
- Inspect learner-state status and non-blocking reminders.
- View answers, reliability information, conversation history, and XAI.

### Implementation notes

The Streamlit application keeps one cached production resource graph across
reruns. Workers do not call Streamlit directly; they publish bounded state for
the UI to consume. Slide rendering, voice components, palette controls, and
live debug overlays use dedicated HTML components so browser geometry and
media events can be returned to Python without treating the browser as a
trusted source of tutoring truth.

**Primary evidence:**

- `apps/streamlit_attentive_slides.py`
- `modules/ui/workspace.css`
- `modules/ui/design_tokens.py`
- `modules/ui/slide_viewport_component/`
- `modules/ui/voice_control_component/`
- `modules/ui/palette_control_component/`

## 5. PDF, slide, AOI, and visual-context processing

### Functions

- Validate and persist an uploaded PDF in the external runtime-data directory.
- Render individual pages without blocking the UI on the whole deck.
- Extract native PDF text and layout metadata with PyMuPDF.
- Fall back to OCR when usable native text is unavailable.
- Group text boxes into deterministic, normalized AOIs.
- Maintain a whole-slide AOI so every page has a safe target.
- Optionally request paragraph-level and visual AOIs from an LLM.
- Accept an LLM AOI only when it can be grounded back to PDF text or validated
  visual context; invalid output does not replace deterministic AOIs.
- Generate slide-index previews asynchronously and expose readiness through
  the single-port launcher.

AOI bounding boxes use normalized `[x1, y1, x2, y2]` coordinates. The browser
component reports CSS viewport geometry separately; server code validates the
geometry before mapping a gaze point or drawn rectangle to an AOI.

### Failure behavior

- PDF preparation errors are shown without crashing the Streamlit server.
- LLM AOI generation is optional; deterministic AOIs remain available.
- A page with no specific AOI still supports whole-slide questions.
- Runtime PDFs, rendered pages, previews, and AOI caches remain outside Git.

**Primary evidence:**

- `modules/slide/slide_parser.py`
- `modules/slide/ocr.py`
- `modules/slide/aoi_grouping.py`
- `modules/slide/aoi_manager.py`
- `modules/slide/llm_aoi.py`
- `modules/system/uploaded_deck_service.py`
- `scripts/pdf_native_worker.py`

## 6. Target acquisition and confirmation

### Supported target sources

| Source | Behavior | Typical fallback |
|---|---|---|
| Manual rectangle | Normalizes the selected region and ranks overlapping AOIs | Whole slide or explicit AOI choice |
| Manual AOI | Uses an explicit AOI selected by the learner | Whole slide |
| Gaze grid | Maps a coarse 3x3 viewport cell to visible AOIs | Manual correction |
| Local point gaze | Matches EyeTheia viewport points to AOIs with dwell and tolerance | Gaze grid, then manual correction |
| Explicit language | Phrases such as "the figure on the right" can override weak gaze | Confirmation when ambiguity remains |

The resolver combines target evidence with the explicit intent. High
confidence may enable automatic confirmation only when the learner has
explicitly selected that preference. Missing, stale, low-confidence, or
layout-mismatched gaze is not auto-confirmed.

After confirmation, the target is frozen for the turn. In persistent voice,
gaze movement does not silently replace the active target. A switch request
creates a candidate and the learner decides whether it becomes active.

**Primary evidence:**

- `modules/system/manual_targeting.py`
- `modules/system/manual_confirmation.py`
- `modules/system/point_gaze.py`
- `modules/system/live_ui_bridge.py`
- `modules/system/target_switching.py`
- `modules/interaction/reference_resolver.py`

## 7. Intent and interaction contracts

The hardware-independent interaction contract separates:

- target evidence;
- intent evidence;
- confirmation or correction;
- privacy and runtime metadata.

Intent can come from typed text, quick actions, or a speech transcript.
Supported teaching actions include explaining a target, summarizing a slide,
asking a quiz question, comparing content, and following up on an existing
conversation. Explicit target language is preserved as evidence instead of
being discarded after parsing.

The canonical pipeline produces a resolved query with candidates, confidence,
confirmation mode, adaptive strategy, and a public explanation of why the
target and intent were selected.

**Primary evidence:**

- `modules/common/interaction_contracts.py`
- `modules/interaction/intent_parser.py`
- `modules/interaction/interaction_contract_adapter.py`
- `modules/interaction/adaptive_policy.py`
- `modules/system/manual_intent.py`

## 8. Browser media and runtime lifecycle

The production launcher exposes Streamlit, media ingestion, voice WebSockets,
and slide previews through one public aiohttp port. Streamlit and ingress use
separate internal ports and are never exposed directly to the browser. Local
EyeTheia is a separate loopback WebSocket service on port 8001; a remote
browser needs an additional SSH tunnel for that port because it is not routed
through the AttentiveSlides proxy.

The browser capture component provides:

- bounded JPEG video frames;
- 16 kHz mono PCM audio;
- latest-only face crops for learner-state inference;
- local point-gaze messages and viewport geometry;
- heartbeat, generation, mute, disconnect, and page-hide lifecycle events.

`BrowserMediaSource` uses bounded queues: video favors freshness, audio has a
byte cap, and face crops are latest-only. HTTP handlers validate and enqueue;
they do not run sensing, STT, or tutor calls. Disconnect or generation changes
invalidate stale packets and release the active runtime safely.

**Primary evidence:**

- `scripts/run_live_single_port.py`
- `modules/media/live_capture_component/index.html`
- `modules/media/browser_media_source.py`
- `modules/media/live_ingress_service.py`
- `modules/media/single_port_transport.py`
- `modules/system/controller.py`

## 9. Gaze and human sensing

### Local EyeTheia point gaze

Face Mesh runs in browser JavaScript. Its landmarks are sent to
`ws://127.0.0.1:8001/ws/predict_gaze`; for a browser on another machine, an
SSH tunnel maps that browser-local port to the EyeTheia service on Lenovo.
Raw landmarks are not sent to the AttentiveSlides ingress or persisted there.
The returned point prediction is forwarded to AttentiveSlides with its page
and viewport geometry. The server keeps only recent points and rejects stale
or revision-mismatched samples.

Point-to-AOI matching considers containment, distance tolerance, AOI priority,
and short dwell aggregation. The live debug overlay displays the authoritative
server match but does not alter the confirmed tutor target.

### Coarse sensing fallback

The repository also contains camera, calibration, head-pose, face-state, and
coarse gaze-grid adapters. These provide observable signals and compatibility
with OpenCV/RealSense-style sources, but the canonical 4060 production path is
browser capture plus local EyeTheia. Failure of local gaze must not stop the
camera, microphone, manual targeting, or tutoring path.

**Primary evidence:**

- `modules/media/browser_gaze_source.py`
- `modules/system/slide_geometry.py`
- `modules/system/point_gaze.py`
- `modules/system/sensing_worker.py`
- `modules/human_sensing/`
- `configs/human_sensing/human_sensing.example.yaml`

## 10. Audio, speech-to-text, and turn detection

The single-turn voice path supports push-to-talk and continuous speaking.
Audio is buffered in memory, segmented by VAD, transcribed, and then routed
through the same intent, target-proposal, confirmation, and tutor path as text.

Key behaviors:

- WebRTC VAD is preferred; an energy-based backend is available as a fallback.
- faster-whisper provides local STT with configurable model, device, compute
  type, and language.
- Temporary WAV data is deleted after transcription.
- Queue overrun, empty speech, VAD timeout, or STT failure is recoverable.
- Slide and sensing context is frozen at the turn boundary so a page change
  during speech cannot mix two slides in one query.

**Primary evidence:**

- `modules/audio/audio_ring_buffer.py`
- `modules/audio/streaming_vad.py`
- `modules/audio/voice_turn_detector.py`
- `modules/audio/faster_whisper_transcriber.py`
- `modules/system/audio_worker.py`
- `modules/system/single_turn_ptt_runtime.py`
- `modules/system/turn_context.py`

## 11. Grounded Tutor and answer validation

Only a confirmed interaction can enter the production Main Tutor. The context
contains the confirmed AOI, slide text, linked visual context, bounded
neighbor-slide text, explicit intent, and bounded conversation history.

The tutor pipeline performs:

1. canonical request adaptation;
2. source-labelled prompt construction;
3. an OpenAI-compatible DashScope request;
4. structured response parsing;
5. grounding and source-ID validation;
6. one bounded retry for provider or schema deviation;
7. a sanitized public answer or a retryable error.

The production UI does not display a confident deterministic answer after the
cloud provider, parser, or grounding validator has exhausted its retry. Raw
prompts, API keys, provider payloads, hidden reasoning, and unvalidated claims
are not exposed in public state.

**Primary evidence:**

- `modules/system/main_tutor_integration.py`
- `modules/tutor/tutor_request_adapter.py`
- `modules/tutor/grounded_prompt.py`
- `modules/tutor/api_llm_client.py`
- `modules/tutor/response_parser.py`
- `modules/tutor/grounding_validator.py`
- `modules/tutor/grounded_tutor_agent.py`

## 12. Conversation, realtime voice, and TTS

### Conversation history

Completed turns can be stored as bounded, sanitized conversation records.
Follow-up requests receive only the permitted source-backed history. History
can be cleared or exported. Page, confirmed target, and voice-engine changes
form explicit context boundaries.

### Persistent Omni

The Omni runtime maintains one DashScope realtime session while page, engine,
and confirmed target remain unchanged. It supports push-to-talk and continuous
speech. A connection or protocol failure falls back to the single-turn engine.
If a final transcript is recoverable, it re-enters the normal proposal and
confirmation path rather than bypassing the tutor gate.

### Text-to-speech

A completed Grounded Tutor answer may be synthesized once and cached for the
interaction. TTS failure does not invalidate the successful text answer.

**Primary evidence:**

- `modules/system/conversation_history.py`
- `modules/system/voice_orchestrator.py`
- `modules/system/omni_voice_runtime.py`
- `modules/realtime/bailian_omni_realtime_client.py`
- `modules/audio/bailian_tts_client.py`
- `modules/system/single_turn_tts.py`

## 13. Explainability and corrective control

The public XAI model answers four questions:

- Why was this target proposed?
- Why was this intent selected?
- Which slide sources support the answer?
- What can the learner do when confidence or evidence is insufficient?

Target candidates, intent evidence, answer claims, source IDs, reliability
states, and corrective actions are normalized into a public view. Reliability
is shown as pending, supported, caution, or unsupported. Sanitizers reject
secret fields, raw provider data, and hidden reasoning before the payload can
reach the UI.

**Primary evidence:**

- `modules/system/integrated_pipeline_xai.py`
- `modules/system/xai_view_model.py`
- `modules/ui/learner_state_status.py`

## 14. Learner-state estimation

One latest-only worker consumes face crops and isolates three derived signals:

- EmotiEff top emotion;
- EmotiEff-derived engagement;
- MobileViT fatigue probability.

Emotion, engagement, and fatigue have independent temporal trackers and error
states. Failure in one modality does not erase healthy values from another and
does not block slide study, voice, or tutoring. The UI presents state as a
non-authoritative status and uses non-blocking fatigue/distraction reminders.

The operational EmotiEff window samples at 4 Hz over 128 frames, approximately
32 seconds. This is a deployment policy, not a claim that the original model's
training protocol or accuracy has been reproduced.

**Primary evidence:**

- `modules/learner_state/emotieff_estimator.py`
- `modules/learner_state/temporal.py`
- `modules/fatigue/mobilevit_estimator.py`
- `modules/fatigue/state.py`
- `modules/system/learner_state_worker.py`
- `scripts/prepare_emotieff_learner_state.py`
- `scripts/prepare_mobilevit_fatigue.py`

## 15. Study lifecycle and Review

A Study session has explicit Start, Pause, Resume, Finish, and Review states.
Pausing stops study-time accumulation and prevents late media or tutor results
from mutating the suspended session. Finishing produces an immutable review;
starting a new Study does not overwrite previous completed sessions.

### Gaze heatmap

Valid browser point gaze is converted server-side into a bounded dwell grid
and AOI dwell totals. Each observation has a maximum accepted duration to
avoid assigning long disconnect gaps to a slide. Review rendering combines
the original slide with a transparent heatmap overlay and supports PNG export.

### Learner-state review

Review stores time-weighted per-slide emotion, engagement, fatigue, reminder,
study-time, and completed-interaction summaries. The UI supports session
selection, JSON export, and explicit deletion.

### Persistence boundary

Canonical review files may contain derived heatmap cells and per-slide
aggregates. They do not contain raw gaze points, face crops, video, audio,
1280-dimensional embeddings, per-frame predictions, transcripts, or API
credentials. Writes use temporary files and atomic replacement; stale latest
caches can be repaired from canonical session history.

**Primary evidence:**

- `modules/attention/gaze_heatmap.py`
- `modules/attention/heatmap_renderer.py`
- `modules/review/contracts.py`
- `modules/review/study_review_store.py`
- `modules/ui/review_view.py`

## 16. Persistence, logs, and data ownership

Production runtime data defaults to:

```text
$XDG_DATA_HOME/attentive_slides
```

or `~/.local/share/attentive_slides` when `XDG_DATA_HOME` is unset. It can be
overridden with `ATTENTIVE_RUNTIME_DATA_DIR`.

The runtime directory owns uploaded PDFs, generated slides, previews, AOI
caches, interaction logs, model artifacts, and Study Review history. These are
machine/user data and do not belong in Git.

Git tracks only deterministic project inputs such as example manifests,
interaction-contract examples, mock scenarios, configuration examples, and
licensed UI assets. Interaction logs are JSONL and written once per completed
interaction ID; raw media and secrets are excluded.

## 17. Models, services, and configuration

| Capability | Runtime/model | Important configuration | Artifact policy |
|---|---|---|---|
| Grounded Tutor | DashScope OpenAI-compatible chat model | `DASHSCOPE_API_KEY`, base URL, model | No provider payload or key in Git/logs |
| Realtime voice | DashScope Omni realtime | realtime model, region, voice, VAD/silence settings | Session audio is not persisted by the app |
| TTS | DashScope/Bailian TTS | model, voice, endpoint | Generated audio is runtime cache |
| STT | faster-whisper | model, device, compute type, language | HF model cache stays outside Git |
| Point gaze | Local EyeTheia service | loopback WebSocket endpoint | No EyeTheia weights in this repository |
| Fatigue | MobileViT + PyTorch | model path and CUDA/CPU device | Prepared model stays in runtime data |
| Emotion/engagement | EmotiEff + PyTorch | TorchScript/state paths and device | Source and converted weights stay outside Git |
| Slide OCR | EasyOCR | language/device configuration | Downloaded OCR models stay in external cache |

The preparation scripts pin model sources and verify checksums where the
upstream model permits it. A missing optional model changes the corresponding
feature to unavailable; it must not silently fabricate a healthy prediction.

## 18. Repository components and quality assets

| Path | Role | Git policy |
|---|---|---|
| `apps/` | Production and diagnostic UI entry points | Track |
| `modules/` | Product implementation and contracts | Track |
| `assets/` | Fonts, licenses, and UI assets | Track |
| `configs/` | Public configuration examples | Track |
| `data/` | Deterministic fixtures and manifests only | Track selectively |
| `scripts/` | Launcher, model preparation, demos, smoke tools | Track |
| `tests/` | Stability and contract regression suite | Track |
| `evaluation/` | Reproducible STT, LLM, scenario, and reference evaluation | Track code/cases; ignore outputs |

The main automated suite uses `unittest` and covers contracts, concurrency,
media queues, audio, gaze, learner state, Review persistence, Streamlit layout,
LLM grounding, XAI, and voice orchestration. Evaluation code is retained
because it is direct evidence for the report, not disposable runtime output.

## 19. Current validation boundary

The implementation includes automated coverage for the production paths and
has previously completed focused checkpoint testing and whole-suite runs.
However, the following remain physical-environment acceptance tasks rather
than claims made by this repository:

- full browser interaction acceptance after the latest UI refinements;
- microphone, speaker, and continuous-speaking acceptance on the 4060;
- concurrent EyeTheia, EmotiEff, MobileViT, STT, and tutor GPU behavior under
  a realistic Study session;
- real provider behavior under account quota, network interruption, and model
  version changes;
- empirical gaze, emotion, engagement, or fatigue accuracy with participants.

These limitations should appear in the README, presentation, and report so
that engineering completion is not confused with a validated human-subjects
claim.

## 20. Presentation and report extraction guide

| Deliverable section | Reuse from this document |
|---|---|
| Problem and motivation | Sections 1-2 |
| User journey/demo story | Sections 2-3 |
| System architecture | Sections 4-12 |
| Human-centered design | Sections 1, 6, 13 |
| AI/model components | Sections 9-14 and 17 |
| Privacy and safety | Sections 1, 15-17 |
| Engineering contribution | Sections 5, 8, 11, 15 |
| Evaluation plan | Sections 18-19 |
| Limitations and future work | Section 19 |

For presentation slides, prefer the end-to-end flow and one capability table
over a file-level architecture diagram. For the report, cite the primary
evidence paths under each module and distinguish implemented behavior from
pending physical-environment or human-subject validation.
