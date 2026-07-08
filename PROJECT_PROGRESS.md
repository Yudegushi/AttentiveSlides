# AttentiveSlides Project Progress

> Purpose: Durable record of completed work and verified current state.  
> Use this file to brief future engineering-optimization sessions.  
> Keep forward-looking planning in `member3_4_next_stage_plan.md`.

## Current Completed Scope

### Member 3/4 Mock Integration Pipeline

Completed:

- `modules/system/pipeline.py` provides `run_interaction(...) -> InteractionResult`.
- `modules/common/schemas.py` defines the shared dataclasses used across intent parsing, reference resolution, tutoring, logging, and UI state.
- `data/scenarios/member3_4_demo_cases.json` contains 8 mock interaction scenarios.
- `scripts/demo_tutor_loop.py` runs the scenario fixture loop and writes JSONL logs.
- `scripts/run_interaction_cli.py` supports manual text input with mock sensing presets.
- `evaluation/eval_reference_resolution.py` evaluates intent, AOI resolution, confirmation mode, and adaptive strategy.
- `evaluation/eval_scenario_outputs.py` evaluates response modes and pending-confirmation answer gating.
- Tests cover intent parsing, reference resolution, tutor/context retrieval, system pipeline behavior, scenario expectations, logging, and evaluation metrics.

Key behavior now implemented:

- Deictic transcript + mock gaze + mock learning-state signals resolve to a slide AOI or whole-slide target.
- Pending confirmation is gated: if confirmation is required and no user-confirmed AOI is available, no final AOI-specific tutor answer is exposed.
- User confirmation or correction overrides the predicted AOI for context retrieval.
- Logs record predicted AOI, confirmed AOI, correction status, response mode, and latency.
- Click-required cases do not silently fall back to whole-slide answering.

### Streamlit UI Demo

Completed:

- `apps/streamlit_demo.py` provides a local Streamlit demo over the existing mock pipeline.
- `modules/system/demo_view_model.py` provides a testable thin view-model layer for UI rendering.
- `tests/test_demo_view_model.py` verifies UI-facing behavior for pending confirmation, confirmed correction, and click-required AOI choices.
- Streamlit was used because it is already installed locally as `streamlit 1.41.1`.
- Gradio is not installed and was not added.

Current UI capabilities:

- Select a scenario from `data/scenarios/member3_4_demo_cases.json`.
- Edit transcript, mock gaze grid, predicted AOI, confidence, stable duration, and observable learning-state signals.
- Render slide AOI boxes from `data/mock_deck/mock_aoi_manifest.json`.
- Show intent, predicted AOI, confidence, adaptive strategy, evidence, and learning-state summary.
- Preserve confirmation-gated answering: pending turns show candidates/evidence and hide the final answer.
- Confirm or correct the AOI, then rerun the same pipeline turn to render a final slide-grounded tutor response.
- Compare expected vs actual scenario fields.
- Append the current turn to `data/logs/streamlit_demo_interactions.jsonl` and inspect recent log rows.

Run command:

```bash
python -m streamlit run apps/streamlit_demo.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
```

### Module 1/2 Adapter Architecture

Completed:

- `modules/system/adapters.py` defines internal provider contracts for slide, transcript, and sensing inputs.
- Mock-backed providers convert the current manifest and scenario fixtures into stable internal dataclasses.
- `ProviderBackedDeckStore` lets provider output run through the existing `run_interaction(...)` pipeline without duplicating tutor/context logic.
- `modules/system/demo_view_model.py` now runs scenarios through the adapter boundary.
- `scripts/demo_tutor_loop.py` now uses the same adapter bundle path as the UI helper.
- Adapter-driven scenario execution matches direct pipeline execution.

Current boundary:

- Real Module 1/2 field mapping is not implemented yet because their final interfaces are not available.
- Future real adapters should map their outputs into `SlideFrame`, `Transcript`, `GazePrediction`, and `LearningState`.
- The verified checkpoint is:

```text
Mock scenario -> adapter providers -> pipeline input bundle -> run_interaction(...) -> InteractionResult
```

## Verified Commands

The latest verified commands from the adapter architecture implementation stage:

```bash
python -m py_compile modules/system/adapters.py modules/system/demo_view_model.py apps/streamlit_demo.py
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
```

Observed results:

- Python compile check passed.
- Unit test suite passed: 29 tests.
- CLI demo completed and wrote `data/logs/demo_interactions.jsonl`.
- Reference-resolution evaluation reported all metrics as `1.0`.
- Scenario-output evaluation reported `output_accuracy = 1.0`.

The latest verified commands from the UI demo implementation stage also included:

```bash
python -m streamlit run apps/streamlit_demo.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
curl -I http://localhost:8501
```

- Streamlit app served `http://localhost:8501` with HTTP `200 OK`.
- Streamlit testing rendered the app without exceptions, displayed pending confirmation, and after clicking confirm displayed the final tutor response.
- The Streamlit server was stopped after verification.

## Current Explicit Non-Scope

Not implemented yet:

- Real webcam or eye-tracking input.
- Real Whisper/STT input.
- Real LLM client or API-key-dependent generation.
- Lenovo 4060 GPU deployment path.
- Live Module 1 slide-processing interface.
- Live Module 2 sensing interface.

Current implementation remains mock-driven by design.

## Useful Next Engineering Questions

For engineering optimization work, inspect these areas first:

- Whether `apps/streamlit_demo.py` should be split into smaller UI components before adding more panels.
- Whether `modules/system/demo_view_model.py` should become the boundary for future UI-independent contract tests.
- How real Module 1/2 outputs should map into the new protocol-style adapter interfaces once field names/formats are available.
- Whether log files under `data/logs/` should stay untracked runtime artifacts.

## Git State Note

The Streamlit UI demo and adapter execution plan were committed and pushed in commit `d51beb7`.
