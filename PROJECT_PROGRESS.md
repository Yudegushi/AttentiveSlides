# AttentiveSlides project progress

Engineering snapshot as of 2026-07-16.

## Canonical development line

- `main` is the active development and deployment branch. It contains the
  EyeTheia local gaze integration and supersedes the former
  `codex/eyetheia-local-gaze-integration` branch.
- `codex/live-system-integration-v1` is retained as the immutable AutoDL
  integration record.
- `feature/realtime-voice-dialogue` remains as historical implementation
  context. Its commits were not merged or cherry-picked into `main`.
- Completed execution plans, design specifications, and handoff ledgers are
  intentionally kept in Git history instead of the current tree.

## Primary execution environment

- SSH host: `LenovoLinux_Dorm`.
- Active checkout: `/home/charles/repos/AttentiveSlides-eyetheia-local-gaze-integration`.
- Conda environment: `pyboe` (Python 3.10.20).
- GPU: NVIDIA RTX 4060 Laptop GPU.
- Runtime data defaults to a portable user data directory and can be overridden
  with `ATTENTIVE_SLIDES_DATA_DIR`.

## Current main capabilities

- `apps/streamlit_attentive_slides.py` is the production Manual + Live UI.
- Uploaded PDFs preserve layout metadata and produce deterministic AOIs, with
  optional paragraph-level LLM AOIs grounded back to PDF text anchors.
- Browser viewport geometry and local EyeTheia point gaze resolve against the
  visible slide AOIs; the coarse gaze grid remains available as a fallback.
- The live debug overlay exposes the authoritative gaze-to-AOI match without
  changing the confirmed tutoring target.
- Browser camera and microphone ingress, VAD/STT, confirmation-gated targeting,
  grounded tutor responses, conversation history, and XAI remain available from
  the existing live-system integration.
- The official UI supports manual target correction before an AOI-specific tutor
  answer is released.
- Live mode offers Grounded Tutor single-turn and persistent Omni realtime
  engines. Each engine supports push-to-talk and continuous speaking while
  sharing the existing single browser media capture and ingress port.
- Omni keeps one provider session across turns on the same page and confirmed
  target. Page, engine, and confirmed-target changes are explicit history
  boundaries.
- The confirmed AOI remains locked when gaze moves. An explicit switch request
  creates a candidate that must be confirmed or rejected before it can replace
  the active target.
- Grounded Tutor answers remain text-first and can optionally synthesize one
  cached TTS artifact per completed interaction. TTS failure does not invalidate
  the text answer.
- Omni connection/protocol failure switches to the single-turn engine. A
  recovered final transcript re-enters the existing Live proposal and target
  confirmation path rather than calling the tutor directly.

## Current operational documentation

- [Live UI usage](docs/live_ui_usage.md)
- [Browser media runtime](docs/browser_media_runtime.md)
- [Continuous interaction design](docs/continuous_interaction_design.md)
- [Interaction contract](docs/interaction_contract.md)
- [Manual targeting](docs/manual_targeting.md)
- [Main tutor integration](docs/main_tutor_integration.md)
- [Audio deployment](docs/audio_deployment.md)

## Verification status

- Checkpoint focused groups passed on the Lenovo checkout: 11, 19, 68, the
  Checkpoint 4 affected groups, and 54 tests respectively. The bounded review
  fix wave passed 76 focused tests, followed by 12 tests for its final
  concurrency correction.
- One whole-change review covered persistent-session concurrency, media
  transport, UI/fatigue/AOI compatibility, visual grounding, safety, and
  fallback. All Critical/Important findings were addressed in one bounded fix
  wave.
- The full discovery run completed 696 tests with one failure from a stale
  pre-voice compact-layout assertion. That assertion was aligned with the
  refined slide-stage layout and its complete 7-test module passed. Per user
  direction, the full discovery run was not repeated; the other 695 passing
  results were reused.
- `attentiveslides-local.service` and `eyetheia-personalized.service` are active.
  The local proxy health endpoint returns HTTP 200, the fresh startup journal
  has no traceback or OOM, and the RTX 4060 retained more than 6 GiB free VRAM
  during the deployment check.
- Complex browser, microphone, speaker, and real-provider acceptance on the 4060
  is `pending user acceptance`.
- Voice commits remain local to Lenovo and have not been pushed.
