# AttentiveSlides project progress

Engineering snapshot as of 2026-07-15.

## Canonical development line

- `main` is the active development and deployment branch. It contains the
  EyeTheia local gaze integration and supersedes the former
  `codex/eyetheia-local-gaze-integration` branch.
- `codex/live-system-integration-v1` is retained as the immutable AutoDL
  integration record.
- `feature/realtime-voice-dialogue` is retained as the implementation source
  and history for the next realtime-voice phase. It is not merged into `main`.
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

## Current operational documentation

- [Live UI usage](docs/live_ui_usage.md)
- [Browser media runtime](docs/browser_media_runtime.md)
- [Continuous interaction design](docs/continuous_interaction_design.md)
- [Interaction contract](docs/interaction_contract.md)
- [Manual targeting](docs/manual_targeting.md)
- [Main tutor integration](docs/main_tutor_integration.md)
- [Audio deployment](docs/audio_deployment.md)

## Next phase

Port the realtime dialogue capabilities from `feature/realtime-voice-dialogue`
onto the current `main` implementation. The migration must preserve the current
EyeTheia gaze path, PDF/AOI behavior, official UI layout, and confirmation gate;
the historical feature branch remains unchanged.
