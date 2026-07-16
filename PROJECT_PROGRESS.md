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

### Gaze heatmap study review

- Status: automatic implementation complete; manual browser acceptance pending
- Scope: server-side derived dwell grids, latest completed review persistence,
  minimal same-canvas Review mode, region-time disclosure, PNG/JSON export
- Privacy: no raw gaze or biometric media persisted
- Verification: four focused GREEN checkpoints, one independent whole-change
  review, one passing full unittest suite; complex browser acceptance delegated
  to the user
- Deployment: attentiveslides-local.service only; EyeTheia unchanged

### EmotiEff learner state and integrated Study Review

- Status: automatic implementation complete; manual browser/GPU concurrency acceptance pending
- Implementation line: local branch `codex/gaze-heatmap-review`, based on
  `96be07d581cff6c5e7102eed01e27b2e353c2086`; the branch has not been pushed.
- Scope: one latest-only face-crop worker combines EmotiEff top emotion and
  engagement with the existing MobileViT fatigue estimate. The Study UI adds a
  stable Learner state popover and non-blocking fatigue/distraction reminders;
  Review adds immutable history, selected-session JSON/delete actions, and
  compact per-session/per-slide state metadata beside the existing heatmap.
- Official source pin: EmotiEffLib commit
  `520a051c64cd191521e5934655314e769a319684`. The verified emotion source is
  16,419,305 bytes with SHA256
  `95aafb39b8bb87964f45e208b9ab31e276e3e5278678db4961d18e6a1b42a141`;
  the engagement source is 5,282,144 bytes with SHA256
  `243b4699eec398a335d32774849f65b2f0e2d63e358df479c5ee95a002cac30d`.
- Prepared runtime artifacts: emotion TorchScript SHA256
  `687a1c9178ef1181f9178cb391fa9c3ca5aa822c2d4f304352b5eebaf8b3e190`
  and weights-only engagement state SHA256
  `ea3b1423935ca783fb19ad740ea0a35b105f33f48159458d2c66574025298826`.
  Only `h5py==3.14.0` was added; TensorFlow, Keras, tf2onnx, the complete
  EmotiEffLib package, and a timm downgrade were not installed.
- Deployment sampling: 4 Hz with 128 frames is an approximately 32-second
  operational window. It does not claim to reproduce the upstream training
  sampling rate, and learner engagement accuracy has not been established by
  manual feature acceptance.
- Privacy boundary: canonical Study Review files persist only existing heatmap
  grids and per-slide time-weighted aggregates. They do not persist face crops,
  raw video/audio, raw gaze points, 1280-D embeddings, per-frame predictions,
  or transcripts.
- Focused GREEN evidence: Checkpoints 1–7 passed 11, 19, 45, 48, 69, 59, and
  76 tests respectively. The single bounded review fix wave passed 83 directly
  affected tests. No baseline suite, RED run, browser automation, lint, type
  check, security scan, or performance test was run.
- Whole-change review: one direct review covered all 16 plan risks. One bounded
  fix wave preserved a frozen failed finish across Start new attempts and
  isolated emotion temporal failures from engagement/fatigue; no unresolved
  Critical or Important finding remains.
- Final unittest discovery: the single budgeted run executed 781 tests in
  15.086 seconds and reported `FAILED (failures=1)`: 780 passed and the only
  failure was the stale whole-file assertion
  `test_current_slide_selectbox_is_removed`, which mistook the new Learner
  state row label for the retired slide selectbox. The assertion was narrowed
  to `_render_slide_selector`; its directly affected 5-test module then passed
  in 0.013 seconds. Per the verification budget, full discovery was not rerun.

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
