# UI + Live Runtime Integration Execution Log

Date: 2026-07-14

Delivery branch: `codex/ui-live-runtime-integration-v1`

Pinned inputs:

- Frontend: `3af3c527b1de4b7cf3abe9d72c32eac6f0a39745`
- Live backend: `e3f193928a2601422d5face51572eeca6ee08cb1`

## Execution ledger

| Task | Status | Evidence | Commit | Notes |
|---|---|---|---|---|
| 0 Merge baseline | complete | 34 frontend tests + 37 live tests passed | `649b2b35` | `origin/feature/api-llm-pipeline` advanced to `287fca5`; the user-approved pinned SHA remains its ancestor and was used. `ort` merged AOI changes without a text conflict. Semantic inspection confirmed `allow_ocr`, one `RLock`, and atomic temp-file replacement. The plan's sample `process_slide(image_path=...)` signature did not match the pinned frontend API; the actual `process_slide(..., dpi=250, *, allow_ocr=True)` API was preserved. |
| 1 Ingress fixes | complete | 4 focused tests failed for the expected missing behavior, then 37 ingress/transport/launcher tests passed | `3116265` | Reload now resets only active media readiness and waits for new video plus audio. `/health` returns 503 when the coordinator task is absent/done/failed; unexpected coordinator errors record the cause and stop a running runtime safely. |
| 2 Canonical deck | complete | Provider module first failed to import; then 8 provider/upload/AOI concurrency tests passed | `44d9821` | One lock, no cache, and no duplicate deck store. |
| 3 Slide component | complete | 7 geometry/component tests + 17 geometry/manual/widget tests passed; one-port browser coordinate gate passed | `99c804b`, `d41a9a9` | Gate exposed a proxy bug: aiohttp decompressed component assets but retained gzip headers. `auto_decompress=False` preserves bytes. Temporary spike was deleted and not committed. |
| 4 Live proposal bridge | complete | 20 bridge/context/sensing/controller/runner tests passed | `0300ed5` | Latest-only proposal transport; background workers do not read Streamlit state or call the tutor. |
| 5 Official UI integration | complete | 110 affected UI/runtime tests passed; browser media status reached `speech_active` / `ready` | `6d315bb` | Official frontend is the launcher default; diagnostic UI remains selectable. One Main Tutor and one exact-once logger path. |
| 6 Acceptance and push | ready to push | 446 tests, compileall, demo, both 8-case evaluations, diagnostic + official HTTP smoke passed | — | Real LLM was unavailable because no API key was configured. Real human voice/calibrated point-gaze remain explicit manual follow-up; no claim of point-gaze accuracy. |

## Checkpoint 0 — merge baseline

- Merge commit: `649b2b35d9ca03d86488cd317eb3841123ba4840`
- Parents: frontend `3af3c52`, live backend `e3f1939`
- Frontend regression command: `/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_interaction_contracts tests.test_manual_targeting tests.test_manual_confirmation tests.test_main_tutor_integration tests.test_uploaded_deck_service -v`
- Frontend result: 34 tests, 0 failures.
- Live regression command: `/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_live_ingress_service tests.test_live_single_port_launcher tests.test_sensing_worker tests.test_turn_context tests.test_system_controller -v`
- Live result: 37 tests, 0 failures.
- Dependency evidence: existing requirements include `streamlit-drawable-canvas-fix`, `aiohttp`, `faster-whisper`, and `webrtcvad-wheels`; no requirements file was added.

## Checkpoint 1 — ingress lifecycle fixes

- RED: reload test failed with `start_count=2` instead of `1` before the readiness reset.
- RED: coordinator tests failed because `health_status` did not exist; route test failed because `health_check` was not accepted.
- GREEN command: `/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_live_ingress_service tests.test_single_port_transport tests.test_live_single_port_launcher -v`
- GREEN result: 37 tests, 0 failures.
- Commit: `3116265f548260614bf6f4fe690d05b8a648687f`.

## Checkpoint 2 — canonical uploaded deck

- RED: all four provider tests failed with `ModuleNotFoundError` before implementation.
- GREEN command: `/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_active_deck_slide_provider tests.test_uploaded_deck_service tests.test_aoi_manager_concurrency -v`
- GREEN result: 8 tests, 0 failures.
- Commit: `44d9821bc22478edc9bf34b0bdafc83785c7bcf3`.

## Checkpoint 3 — viewport component and coordinate gate

- RED: five geometry tests failed because `slide_geometry` did not exist; two component contract tests failed because the component files did not exist.
- Geometry/component GREEN: 7 tests, 0 failures.
- Proxy RED: gzip component test failed with `ClientPayloadError: Can not decode content-encoding: gzip`.
- Proxy GREEN: all 14 launcher tests passed after setting the upstream proxy client to `auto_decompress=False`.
- Browser gate through the public one-port launcher:
  - initial iframe and slide rect both began at `x=380`, `y=184.797`, proving the iframe offset was included;
  - after scrolling, component geometry reported `y=-220.703` in parent viewport CSS pixels;
  - manual drag returned normalized bbox `[0.1707, 0.3453, 0.3902, 0.5004]`;
  - narrowing the layout changed slide width from `820` to `402`, height from `1160.54` to `568.95`, and layout revision to `11`; AOI rects changed consistently;
  - visual inspection confirmed one responsive slide filled the main content width and overlays aligned.
- Final Task 3 command: `/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_slide_geometry tests.test_manual_targeting tests.test_main_ui_widget_inventory -v`.
- Final Task 3 result: 17 tests, 0 failures.
- Commits: proxy `99c804b26d32f925c2a0cfd4b88b25db5e604ed9`; component `d41a9a9e3b91bc82d34ff96d2dd0a4be1f026a60`.

## Checkpoint 4 — Live proposal bridge

- Added opt-in `gaze_grid` aggregation while preserving the existing AOI default.
- The proposal runner publishes only transcript plus frozen grid evidence into a latest-only inbox; it does not import the tutor or logger.
- Browser-coordinate resolution assigns the current layout revision and applies deterministic AOI scoring; low/missing gaze remains explicit.
- GREEN command: `/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_live_ui_bridge tests.test_turn_context tests.test_sensing_worker tests.test_system_controller tests.test_live_turn_runner -v`.
- GREEN result: 20 tests, 0 failures.
- Commit: `0300ed5`.

## Checkpoint 5 — official UI integration

- The launcher defaults to `apps/streamlit_attentive_slides.py`; `--streamlit-app apps/streamlit_live.py` still selects diagnostics.
- The official UI owns Manual/Live selection, confirmation/correction, the existing Main Tutor call, history/XAI, and exact-once JSONL logging.
- `Always confirm` is the default. User-selected confidence auto uses a visible `[0.70, 0.95]` slider with explicit `0.80` default.
- Provider, parse, and validation exhaustion now expose their final failure as a retryable UI error and never display a fallback answer.
- The browser media gate reported active/fresh video, audio, and heartbeat. The UI's periodic status reached `Live transport: armed · Runtime: speech_active · Media: ready`; turning media off returned `Transport: off · Runtime: stopped · Media: waiting` without a callback-rerun warning.
- GREEN affected-suite result: 110 tests, 0 failures; `git diff --check` passed.
- Commit: `6d315bb`.

## Checkpoint 6 — final automated and smoke acceptance

- `compileall` passed for `modules`, `apps`, `scripts`, and `tests`.
- Full discovery loaded and passed 446 tests.
- `scripts/demo_tutor_loop.py` exited 0.
- `evaluation/eval_reference_resolution.py`: 8/8 scenarios, all four reported metrics `1.0`.
- `evaluation/eval_scenario_outputs.py`: 8/8 scenarios, output accuracy `1.0`.
- Diagnostic entrypoint smoke: public root 200 and Streamlit health 200.
- Official default entrypoint smoke: public root 200 and Streamlit health 200. Isolated ports `18601/18602/18603` were used because a separate user-owned `/root/autodl-tmp/workspace/AttentiveSlides` Streamlit process occupied 8502.
- The real browser one-port gate used the official UI and verified same-origin capture plus live status. No real LLM call was attempted because neither supported API key was configured.
- Automated lifecycle coverage verifies low/no gaze fallback, auto-confirm gating, exact-once retry behavior, deck-reload fresh video+audio, coordinator 503, and launcher ingress-loss handling.
- Deliberately pending physical checks: a scripted real-human voice/STT turn and calibrated point gaze. Point gaze/calibration are outside this course-project integration scope; current production behavior is coarse 3×3 gaze.
