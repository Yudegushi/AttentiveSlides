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
| 1 Ingress fixes | pending | — | — | — |
| 2 Canonical deck | pending | — | — | — |
| 3 Slide component | pending | — | — | Coordinate gate blocks later tasks. |
| 4 Live proposal bridge | pending | — | — | — |
| 5 Official UI integration | pending | — | — | — |
| 6 Acceptance and push | pending | — | — | Real human gaze/voice acceptance may remain pending as authorized. |

## Checkpoint 0 — merge baseline

- Merge commit: `649b2b35d9ca03d86488cd317eb3841123ba4840`
- Parents: frontend `3af3c52`, live backend `e3f1939`
- Frontend regression command: `/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_interaction_contracts tests.test_manual_targeting tests.test_manual_confirmation tests.test_main_tutor_integration tests.test_uploaded_deck_service -v`
- Frontend result: 34 tests, 0 failures.
- Live regression command: `/root/miniconda3/bin/conda run -n attentive-app python -m unittest tests.test_live_ingress_service tests.test_live_single_port_launcher tests.test_sensing_worker tests.test_turn_context tests.test_system_controller -v`
- Live result: 37 tests, 0 failures.
- Dependency evidence: existing requirements include `streamlit-drawable-canvas-fix`, `aiohttp`, `faster-whisper`, and `webrtcvad-wheels`; no requirements file was added.
