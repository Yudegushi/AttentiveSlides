# Module 1/2 Adapter Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a testable adapter layer so AttentiveSlides can keep using mock fixtures now and later replace them with real Module 1 slide outputs and Module 2 sensing outputs.

**Architecture:** Introduce stable internal provider contracts around the existing dataclasses in `modules/common/schemas.py`. The pipeline keeps consuming `Transcript`, `GazePrediction`, `LearningState`, AOIs, and deck context, while adapters translate mock fixtures or future Module 1/2 outputs into those internal types. This stage creates mock-backed adapters and contract tests only; real Module 1/2 integration remains a later mapping task after their interfaces are available.

**Tech Stack:** Python standard library, dataclasses, typing Protocol, unittest, existing mock manifest/scenario fixtures.

## Global Constraints

- Do not connect real webcam, real eye tracking, real Whisper/STT, real LLM, or Lenovo GPU in this stage.
- Do not require API keys or network access.
- Do not change the human-centered invariant: pending confirmation must not expose a final AOI-specific answer.
- Treat gaze as coarse AOI grounding, not pixel-level eye tracking.
- Treat learning-state as observable signals only, not true emotion, attention, fatigue, or cognition.
- Keep existing scenario behavior and evaluation metrics unchanged.
- Keep UI design work out of this stage; another thread will handle visual redesign.
- Do not require finalized Module 1/2 real interfaces for this stage.

---

## Context

Current stable entrypoint:

```python
run_interaction(
    transcript: str,
    gaze_prediction: GazePrediction,
    learning_state: LearningState,
    deck_id: str = "mock_deck",
    slide_id: int = 5,
    confirmed_aoi_id: str | None = None,
    history: InteractionHistory | None = None,
    deck_store: MockDeckStore | None = None,
    tutor: TutorAgent | None = None,
    logger: InteractionLogger | None = None,
) -> InteractionResult
```

Current internal dataclasses already available:

- `AOI`
- `GazePrediction`
- `LearningState`
- `Transcript`
- `InteractionResult`
- `UIState`

Current mock data sources:

- `data/mock_deck/mock_aoi_manifest.json`
- `data/scenarios/member3_4_demo_cases.json`

## Request

Build the adapter architecture that can be executed before Module 1/2 teammates finish their real interfaces:

- Define stable internal provider contracts for slide/deck context, transcript input, and sensing input.
- Implement mock-backed providers using current manifest and scenario fixtures.
- Add a provider-backed deck store compatible with the existing tutor/context retrieval path.
- Add a bundle/runner helper that converts provider outputs into `run_interaction(...)`.
- Refactor demo helper and CLI demo code to consume the adapter layer without changing behavior.
- Add contract tests that prove future real adapters only need to satisfy the internal contracts.

## Output

Expected deliverables after execution:

- New adapter module: `modules/system/adapters.py`.
- New tests: `tests/test_system_adapters.py`.
- Existing tests still pass.
- Existing evaluation scripts still report full accuracy.
- `PROJECT_PROGRESS.md` updated with completed adapter work.
- `member3_4_next_stage_plan.md` updated to mark this adapter checkpoint as done and record the next real-interface checkpoint.

## Constraints

- The adapter layer must not duplicate intent parsing, reference resolution, tutor generation, or logging logic.
- The adapter layer must not change current scenario outputs.
- The adapter layer must not guess real Module 1/2 field names; real field mapping waits for actual interfaces.
- The adapter layer must expose uncertainty/correction data already produced by `run_interaction(...)`; it should not hide confirmation mode or evidence.
- If a future Module 1/2 interface lacks a required field, the real adapter must fail explicitly instead of silently fabricating values.

## Checkpoint

Pause after the mock-backed adapter architecture is implemented and verified:

```text
Mock scenario -> adapter providers -> pipeline input bundle -> run_interaction(...) -> InteractionResult
```

At that checkpoint, do not proceed to real Module 1/2 adapter implementation unless their actual interfaces are available.

---

## File Structure

Create:

- `modules/system/adapters.py`
  - Internal provider contracts.
  - Mock-backed provider implementations.
  - Provider-backed deck store.
  - Pipeline input bundle and runner helper.

- `tests/test_system_adapters.py`
  - Contract tests for provider behavior.
  - Regression tests that adapter-driven scenarios match existing direct scenario execution.

Modify:

- `apps/streamlit_demo.py`
  - No direct change is required if `modules/system/demo_view_model.py` remains the only scenario execution path used by the UI.

- `scripts/demo_tutor_loop.py`
  - Use adapter bundle helpers so CLI/demo and UI share the same mock input boundary.

- `PROJECT_PROGRESS.md`
  - Record completed adapter work after verification.

- `member3_4_next_stage_plan.md`
  - Add status and next checkpoint after implementation.

Do not modify in this stage:

- `modules/interaction/*`
- `modules/tutor/*`
- `modules/logging/*`

---

### Task 1: Adapter Contract Tests

**Files:**

- Create: `tests/test_system_adapters.py`
- Create later in Task 2: `modules/system/adapters.py`

**Interfaces:**

- Consumes existing `InteractionScenario`, `load_scenarios`, `AOI`, `GazePrediction`, `LearningState`, `run_interaction`.
- Produces tests for `SlideFrame`, `SensingFrame`, `PipelineInputBundle`, `MockManifestSlideProvider`, `ScenarioTranscriptProvider`, `ScenarioSensingProvider`, `ProviderBackedDeckStore`, `build_pipeline_input_bundle`, and `run_interaction_from_bundle`.

- [ ] **Step 1: Write failing tests**

Add `tests/test_system_adapters.py` with these test cases:

```python
import unittest

from modules.common.schemas import AOI, GazePrediction, LearningState
from modules.system.adapters import (
    MockManifestSlideProvider,
    PipelineInputBundle,
    ProviderBackedDeckStore,
    ScenarioSensingProvider,
    ScenarioTranscriptProvider,
    build_pipeline_input_bundle,
    run_interaction_from_bundle,
)
from modules.system.pipeline import run_interaction
from modules.system.scenarios import load_scenarios


class SystemAdaptersTest(unittest.TestCase):
    def test_manifest_slide_provider_returns_internal_slide_frame(self):
        provider = MockManifestSlideProvider()

        frame = provider.get_slide_frame(5)

        self.assertEqual(frame.deck_id, "mock_deck")
        self.assertEqual(frame.slide_id, 5)
        self.assertTrue(frame.slide_text)
        self.assertTrue(frame.slide_image_path.endswith("slide_005.png"))
        self.assertIn("right_figure", {aoi.aoi_id for aoi in frame.aois})
        self.assertTrue(all(isinstance(aoi, AOI) for aoi in frame.aois))

    def test_scenario_providers_return_transcript_and_sensing_frame(self):
        scenario = load_scenarios()[0]

        transcript = ScenarioTranscriptProvider(scenario).get_transcript()
        sensing = ScenarioSensingProvider(scenario).get_sensing_frame(slide_id=5)

        self.assertEqual(transcript.text, scenario.transcript)
        self.assertIsInstance(sensing.gaze_prediction, GazePrediction)
        self.assertIsInstance(sensing.learning_state, LearningState)
        self.assertEqual(sensing.gaze_prediction.slide_id, 5)

    def test_provider_backed_deck_store_matches_manifest_contract(self):
        store = ProviderBackedDeckStore(MockManifestSlideProvider())

        slide = store.get_slide(5)
        aois = store.get_aois(5)

        self.assertEqual(store.deck_id, "mock_deck")
        self.assertEqual(slide["slide_id"], 5)
        self.assertEqual(slide["ocr_text"], store.get_slide(5)["ocr_text"])
        self.assertIn("neighbor_slide_text", slide)
        self.assertIn("aois", slide)
        self.assertTrue(all(isinstance(aoi, AOI) for aoi in aois))

    def test_build_pipeline_input_bundle_can_run_existing_pipeline(self):
        scenario = load_scenarios()[0]
        bundle = build_pipeline_input_bundle(
            slide_provider=MockManifestSlideProvider(),
            transcript_provider=ScenarioTranscriptProvider(scenario),
            sensing_provider=ScenarioSensingProvider(scenario),
            slide_id=5,
        )

        self.assertIsInstance(bundle, PipelineInputBundle)
        self.assertEqual(bundle.transcript, scenario.transcript)
        self.assertEqual(bundle.deck_id, "mock_deck")
        self.assertEqual(bundle.slide_id, 5)

        result = run_interaction_from_bundle(bundle)

        self.assertEqual(result.tutor_response.response_mode, "pending_confirmation")
        self.assertIsNone(result.ui_state.response["answer"])

    def test_adapter_driven_scenarios_match_direct_pipeline_results(self):
        slide_provider = MockManifestSlideProvider()

        for scenario in load_scenarios():
            with self.subTest(scenario=scenario.name):
                bundle = build_pipeline_input_bundle(
                    slide_provider=slide_provider,
                    transcript_provider=ScenarioTranscriptProvider(scenario),
                    sensing_provider=ScenarioSensingProvider(scenario),
                    slide_id=5,
                )
                adapter_result = run_interaction_from_bundle(
                    bundle,
                    confirmed_aoi_id=scenario.confirmed_aoi_id,
                )
                direct_result = run_interaction(
                    transcript=scenario.transcript,
                    gaze_prediction=scenario.gaze_prediction,
                    learning_state=scenario.learning_state,
                    confirmed_aoi_id=scenario.confirmed_aoi_id,
                )

                self.assertEqual(adapter_result.resolved_query.intent, direct_result.resolved_query.intent)
                self.assertEqual(adapter_result.resolved_query.resolved_aoi_id, direct_result.resolved_query.resolved_aoi_id)
                self.assertEqual(adapter_result.resolved_query.confirmation_mode, direct_result.resolved_query.confirmation_mode)
                self.assertEqual(adapter_result.resolved_query.adaptive_strategy, direct_result.resolved_query.adaptive_strategy)
                self.assertEqual(adapter_result.tutor_response.response_mode, direct_result.tutor_response.response_mode)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m unittest tests/test_system_adapters.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'modules.system.adapters'`.

---

### Task 2: Adapter Module

**Files:**

- Create: `modules/system/adapters.py`
- Test: `tests/test_system_adapters.py`

**Interfaces:**

- Produces:
  - `SlideFrame`
  - `SensingFrame`
  - `PipelineInputBundle`
  - `SlideProvider`
  - `TranscriptProvider`
  - `SensingProvider`
  - `MockManifestSlideProvider`
  - `ScenarioTranscriptProvider`
  - `ScenarioSensingProvider`
  - `ProviderBackedDeckStore`
  - `build_pipeline_input_bundle(...)`
  - `run_interaction_from_bundle(...)`

- [ ] **Step 1: Implement the minimal adapter module**

Create `modules/system/adapters.py`:

```python
"""Input adapter contracts for Module 1/2 replacement boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from modules.common.schemas import AOI, GazePrediction, InteractionResult, LearningState, Transcript
from modules.interaction.interaction_history import InteractionHistory
from modules.logging.interaction_logger import InteractionLogger
from modules.system.pipeline import run_interaction
from modules.system.scenarios import InteractionScenario
from modules.tutor.context_retriever import DEFAULT_MANIFEST_PATH
from modules.tutor.tutor_agent import TutorAgent


@dataclass(frozen=True)
class SlideFrame:
    deck_id: str
    slide_id: int
    aois: list[AOI]
    slide_text: str
    neighbor_slide_text: str = ""
    slide_image_path: str | None = None


@dataclass(frozen=True)
class SensingFrame:
    gaze_prediction: GazePrediction
    learning_state: LearningState


@dataclass(frozen=True)
class PipelineInputBundle:
    deck_id: str
    slide_id: int
    transcript: str
    gaze_prediction: GazePrediction
    learning_state: LearningState
    deck_store: "ProviderBackedDeckStore"


class SlideProvider(Protocol):
    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        ...


class TranscriptProvider(Protocol):
    def get_transcript(self) -> Transcript:
        ...


class SensingProvider(Protocol):
    def get_sensing_frame(self, slide_id: int) -> SensingFrame:
        ...


class MockManifestSlideProvider:
    def __init__(self, manifest_path: str | Path = DEFAULT_MANIFEST_PATH) -> None:
        self.manifest_path = Path(manifest_path)
        self._manifest = self._load_manifest()

    @property
    def deck_id(self) -> str:
        return self._manifest["deck_id"]

    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        slide = self._get_slide_payload(slide_id)
        return SlideFrame(
            deck_id=self.deck_id,
            slide_id=slide["slide_id"],
            aois=[AOI(**aoi) for aoi in slide["aois"]],
            slide_text=slide["ocr_text"],
            neighbor_slide_text=slide.get("neighbor_slide_text", ""),
            slide_image_path=slide.get("slide_image_path"),
        )

    def _load_manifest(self) -> dict[str, object]:
        with self.manifest_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _get_slide_payload(self, slide_id: int) -> dict[str, object]:
        for slide in self._manifest["slides"]:
            if slide["slide_id"] == slide_id:
                return slide
        raise KeyError(f"Slide {slide_id} not found in {self.manifest_path}.")


class ScenarioTranscriptProvider:
    def __init__(self, scenario: InteractionScenario) -> None:
        self.scenario = scenario

    def get_transcript(self) -> Transcript:
        return Transcript(self.scenario.transcript)


class ScenarioSensingProvider:
    def __init__(self, scenario: InteractionScenario) -> None:
        self.scenario = scenario

    def get_sensing_frame(self, slide_id: int) -> SensingFrame:
        gaze = self.scenario.gaze_prediction
        if gaze.slide_id != slide_id:
            gaze = GazePrediction(
                slide_id=slide_id,
                gaze_grid=gaze.gaze_grid,
                predicted_aoi_id=gaze.predicted_aoi_id,
                confidence=gaze.confidence,
                stable_duration_sec=gaze.stable_duration_sec,
                alternative_targets=list(gaze.alternative_targets),
            )
        return SensingFrame(
            gaze_prediction=gaze,
            learning_state=self.scenario.learning_state,
        )


class ProviderBackedDeckStore:
    def __init__(self, slide_provider: SlideProvider) -> None:
        self.slide_provider = slide_provider
        self._deck_id: str | None = None

    @property
    def deck_id(self) -> str:
        if self._deck_id is None:
            self._deck_id = self.get_slide_frame(5).deck_id
        return self._deck_id

    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        frame = self.slide_provider.get_slide_frame(slide_id)
        if self._deck_id is None:
            self._deck_id = frame.deck_id
        return frame

    def get_slide(self, slide_id: int) -> dict[str, object]:
        frame = self.get_slide_frame(slide_id)
        return {
            "slide_id": frame.slide_id,
            "slide_image_path": frame.slide_image_path,
            "ocr_text": frame.slide_text,
            "neighbor_slide_text": frame.neighbor_slide_text,
            "aois": [
                {
                    "aoi_id": aoi.aoi_id,
                    "bbox": list(aoi.bbox),
                    "type": aoi.type,
                    "name": aoi.name,
                    "text": aoi.text,
                }
                for aoi in frame.aois
            ],
        }

    def get_aois(self, slide_id: int) -> list[AOI]:
        return self.get_slide_frame(slide_id).aois


def build_pipeline_input_bundle(
    slide_provider: SlideProvider,
    transcript_provider: TranscriptProvider,
    sensing_provider: SensingProvider,
    slide_id: int,
) -> PipelineInputBundle:
    deck_store = ProviderBackedDeckStore(slide_provider)
    slide_frame = deck_store.get_slide_frame(slide_id)
    transcript = transcript_provider.get_transcript()
    sensing = sensing_provider.get_sensing_frame(slide_id)

    return PipelineInputBundle(
        deck_id=slide_frame.deck_id,
        slide_id=slide_frame.slide_id,
        transcript=transcript.text,
        gaze_prediction=sensing.gaze_prediction,
        learning_state=sensing.learning_state,
        deck_store=deck_store,
    )


def run_interaction_from_bundle(
    bundle: PipelineInputBundle,
    confirmed_aoi_id: str | None = None,
    history: InteractionHistory | None = None,
    tutor: TutorAgent | None = None,
    logger: InteractionLogger | None = None,
) -> InteractionResult:
    return run_interaction(
        transcript=bundle.transcript,
        gaze_prediction=bundle.gaze_prediction,
        learning_state=bundle.learning_state,
        deck_id=bundle.deck_id,
        slide_id=bundle.slide_id,
        confirmed_aoi_id=confirmed_aoi_id,
        history=history,
        deck_store=bundle.deck_store,
        tutor=tutor,
        logger=logger,
    )
```

- [ ] **Step 2: Run adapter tests**

Run:

```bash
python -m unittest tests/test_system_adapters.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Run full tests**

Run:

```bash
python -m unittest discover -s tests -v
```

Expected: all tests pass.

---

### Task 3: Route Demo Helpers Through Adapter Bundle

**Files:**

- Modify: `modules/system/demo_view_model.py`
- Test: `tests/test_demo_view_model.py`
- Test: `tests/test_system_adapters.py`

**Interfaces:**

- Consumes `build_pipeline_input_bundle`, `MockManifestSlideProvider`, `ScenarioTranscriptProvider`, `ScenarioSensingProvider`, `run_interaction_from_bundle`.
- Preserves `run_scenario_turn(scenario, confirmed_aoi_id=None, logger=None) -> InteractionResult`.

- [ ] **Step 1: Write a regression test**

Add this test to `tests/test_demo_view_model.py`:

```python
def test_run_scenario_turn_uses_adapter_boundary_without_changing_output(self):
    scenario = load_scenarios()[0]

    result = run_scenario_turn(scenario)
    view_model = build_interaction_view_model(result, scenario)

    self.assertEqual(view_model["actual"]["response_mode"], "pending_confirmation")
    self.assertEqual(view_model["actual"]["resolved_aoi_id"], "right_figure")
    self.assertIsNone(view_model["response"]["answer"])
```

- [ ] **Step 2: Run test**

Run:

```bash
python -m unittest tests/test_demo_view_model.py -v
```

Expected: pass before or after refactor. This is a safety net for behavior preservation.

- [ ] **Step 3: Refactor `run_scenario_turn`**

In `modules/system/demo_view_model.py`, change `run_scenario_turn` to build an adapter bundle and call `run_interaction_from_bundle(...)`:

```python
def run_scenario_turn(
    scenario: InteractionScenario,
    confirmed_aoi_id: str | None = None,
    logger: InteractionLogger | None = None,
) -> InteractionResult:
    bundle = build_pipeline_input_bundle(
        slide_provider=MockManifestSlideProvider(),
        transcript_provider=ScenarioTranscriptProvider(scenario),
        sensing_provider=ScenarioSensingProvider(scenario),
        slide_id=scenario.gaze_prediction.slide_id,
    )
    return run_interaction_from_bundle(
        bundle,
        confirmed_aoi_id=confirmed_aoi_id,
        logger=logger,
    )
```

Also update imports in `modules/system/demo_view_model.py`:

```python
from modules.system.adapters import (
    MockManifestSlideProvider,
    ScenarioSensingProvider,
    ScenarioTranscriptProvider,
    build_pipeline_input_bundle,
    run_interaction_from_bundle,
)
```

Remove the direct import of `run_interaction` from `modules.system.pipeline`.

- [ ] **Step 4: Run tests**

Run:

```bash
python -m unittest tests/test_demo_view_model.py tests/test_system_adapters.py -v
```

Expected: all tests pass.

---

### Task 4: Adapter-Driven CLI/Demo Consistency

**Files:**

- Modify: `scripts/demo_tutor_loop.py`
- Test: `tests/test_system_pipeline.py`
- Test: `tests/test_system_adapters.py`

**Interfaces:**

- Consumes existing scenario fixtures.
- Produces same printed/logged scenario results as before.

- [ ] **Step 1: Inspect current script**

Read:

```bash
sed -n '1,240p' scripts/demo_tutor_loop.py
```

- [ ] **Step 2: Refactor script to use adapters**

For each scenario, build a bundle with:

```python
bundle = build_pipeline_input_bundle(
    slide_provider=slide_provider,
    transcript_provider=ScenarioTranscriptProvider(scenario),
    sensing_provider=ScenarioSensingProvider(scenario),
    slide_id=scenario.gaze_prediction.slide_id,
)
result = run_interaction_from_bundle(
    bundle,
    confirmed_aoi_id=scenario.confirmed_aoi_id,
    logger=logger,
)
```

Use one `slide_provider = MockManifestSlideProvider()` before the scenario loop.

- [ ] **Step 3: Run demo script**

Run:

```bash
python scripts/demo_tutor_loop.py
```

Expected:

- Script completes without errors.
- It still writes `data/logs/demo_interactions.jsonl`.
- Printed cases still include pending-confirmation and confirmed-correction scenarios.

- [ ] **Step 4: Run evaluation scripts**

Run:

```bash
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
```

Expected:

- `intent_accuracy = 1.0`
- `resolved_aoi_accuracy = 1.0`
- `confirmation_mode_accuracy = 1.0`
- `adaptive_strategy_accuracy = 1.0`
- `output_accuracy = 1.0`

---

### Task 5: Documentation Update

**Files:**

- Modify: `PROJECT_PROGRESS.md`
- Modify: `member3_4_next_stage_plan.md`

**Interfaces:**

- Consumes verified command outputs from Tasks 2-4.
- Produces compact state for future compacted sessions.

- [ ] **Step 1: Update `PROJECT_PROGRESS.md`**

Add a section:

```markdown
### Module 1/2 Adapter Architecture

Completed:

- `modules/system/adapters.py` defines internal provider contracts for slide, transcript, and sensing inputs.
- Mock-backed providers convert the current manifest and scenario fixtures into stable internal dataclasses.
- `ProviderBackedDeckStore` lets provider output run through the existing `run_interaction(...)` pipeline without duplicating tutor/context logic.
- Adapter-driven scenario execution matches direct pipeline execution.

Current boundary:

- Real Module 1/2 field mapping is not implemented yet because their final interfaces are not available.
- Future real adapters should map their outputs into `SlideFrame`, `Transcript`, `GazePrediction`, and `LearningState`.
```

- [ ] **Step 2: Update `member3_4_next_stage_plan.md`**

Add a short next-goal status block near the top with:

- heading `## Next Goal: Module 1/2 Adapter Architecture`;
- scope bullets saying internal provider contracts and mock-backed adapters are implemented;
- a boundary note saying real Module 1/2 adapters remain blocked until actual interfaces are available;
- checkpoint text `Mock scenario -> adapter providers -> pipeline input bundle -> run_interaction(...) -> InteractionResult`.

- [ ] **Step 3: Run final verification**

Run:

```bash
python -m py_compile modules/system/adapters.py modules/system/demo_view_model.py apps/streamlit_demo.py
python -m unittest discover -s tests -v
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
```

Expected:

- Compile passes.
- All unit tests pass.
- Reference-resolution metrics remain `1.0`.
- Scenario-output accuracy remains `1.0`.

---

## Real Module 1/2 Interface Decision Point

After this plan is implemented, the project can ask Module 1/2 teammates for exact interface details.

Module 1 should provide or map to:

- `deck_id: str`
- `slide_id: int`
- `slide_text: str`
- `neighbor_slide_text: str`
- `slide_image_path: str | None`
- `aois: list[AOI]`, where AOI bboxes are normalized `[x1, y1, x2, y2]`

Module 2 should provide or map to:

- `GazePrediction`
  - `slide_id`
  - `gaze_grid`
  - `predicted_aoi_id`
  - `confidence`
  - `stable_duration_sec`
  - `alternative_targets`
- `LearningState`
  - observable fields only, matching the existing dataclass

Speech/STT should provide or map to:

- `Transcript`
  - `text`
  - optional `language`
  - optional `confidence`

Do not implement real adapters until those actual field names, formats, and failure modes are known.
