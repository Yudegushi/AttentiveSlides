# AttentiveSlides Member 3/4 Next Stage Plan

> Purpose: 后续 goal 模式的工作入口。  
> Scope: 成员 3 `Voice / Intent / Multimodal Fusion` 与成员 4 `Tutor Agent / System Integration / Evaluation`。  
> Current baseline: 第一阶段 mock-driven loop 已完成并推送，`python -m unittest discover -s tests -v` 与 `python scripts/demo_tutor_loop.py` 均可运行。

## Implementation Status

As of the current integration-ready stage, the planned Member 3/4 local pipeline has been implemented:

- `modules/system/pipeline.py` provides `run_interaction(...) -> InteractionResult`;
- `UIState` and `InteractionResult` are defined in `modules/common/schemas.py`;
- demo cases live in `data/scenarios/member3_4_demo_cases.json`;
- `scripts/demo_tutor_loop.py` runs from scenario fixtures;
- `scripts/run_interaction_cli.py` supports manual text input with mock sensing presets;
- `evaluation/eval_reference_resolution.py` and `evaluation/eval_scenario_outputs.py` report scenario metrics;
- tests cover pending confirmation, correction override, click-required behavior, scenario fixtures, UI state, logging, and evaluation metrics.

Next checkpoints should start from UI framework choice, real STT/LLM/webcam integration, or Module 1/2 input replacement. Keep the constraints below active unless explicitly revised.

## Next Goal: Module 1/2 Adapter Architecture

Recommended next execution plan:

```text
docs/superpowers/plans/2026-07-09-adapter-architecture.md
```

Scope judgment:

- This adapter stage can start before Module 1/2 teammates finish their real interfaces.
- Implement internal provider contracts and mock-backed adapters now.
- Keep real Module 1/2 adapter implementation blocked until their actual field names, formats, and failure modes are available.
- Preserve all current scenario behavior, UI demo behavior, and confirmation-gated answering.

Checkpoint for this stage:

```text
Mock scenario -> adapter providers -> pipeline input bundle -> run_interaction(...) -> InteractionResult
```

Pause after the mock-backed adapter architecture is implemented and verified. At that point, decide whether to wait for real Module 1/2 interfaces or continue with UI/engineering cleanup.

## Next Goal: Streamlit / Gradio UI Demo

Status after this goal step:

- Streamlit was selected because it is already available locally (`streamlit 1.41.1`); Gradio is not installed.
- `modules/system/demo_view_model.py` now provides a testable thin view-model layer for UI rendering.
- `apps/streamlit_demo.py` now runs a mock-driven local UI demo over the existing scenario fixtures and `run_interaction(...)`.
- `tests/test_demo_view_model.py` covers pending-answer gating, confirmed correction output, and click-required AOI selection options.
- The demo keeps real webcam, Whisper/STT, real LLM, Lenovo GPU, and Module 1/2 live interfaces out of scope.

Run command:

```bash
python -m streamlit run apps/streamlit_demo.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
```

Current UI capabilities:

- select a scenario from `data/scenarios/member3_4_demo_cases.json`;
- edit transcript, mock gaze prediction, confidence, stable duration, and observable learning-state signals;
- render slide AOI boxes from `data/mock_deck/mock_aoi_manifest.json`;
- show intent, predicted AOI, confidence, adaptive strategy, evidence, and learning-state summary;
- preserve confirmation-gated answering: pending turns hide the final answer until the user confirms/corrects an AOI;
- confirm/correct the AOI and rerun the same pipeline turn to produce the final slide-grounded tutor response;
- compare expected vs actual scenario fields;
- append the current turn to `data/logs/streamlit_demo_interactions.jsonl` and inspect recent log rows.

Recommended next checkpoint:

```text
Pause here for a human visual pass of the Streamlit UI.
After that, choose between:
1. UI polish and demonstration scripting;
2. adapter architecture for Module 1/2 replacement inputs;
3. real STT / webcam / LLM integration planning.
```

The next recommended step is a UI demo, before real Module 1/2 inputs are available. This is useful because the current `run_interaction(...)` service already returns all fields needed for a human-centered demo: predicted target, confirmation mode, candidate targets, evidence, correction path, tutor answer, and logging metadata.

Recommended next goal-mode scope:

```text
Build a Streamlit or Gradio demo UI for the existing mock-driven AttentiveSlides pipeline.

Use current scenario fixtures, mock deck AOIs, mock gaze predictions, and mock learning-state signals.
Do not connect real webcam, real Whisper/STT, real LLM, or Lenovo GPU yet.
Preserve the confirmation-gated interaction:
- first call can return pending_confirmation;
- UI shows candidates/evidence and no final AOI-specific answer;
- user can confirm/correct an AOI;
- second call generates the final slide-grounded tutor response.
```

Suggested UI features:

- scenario selector for `data/scenarios/member3_4_demo_cases.json`;
- transcript input box;
- mock gaze / learning-state controls or presets;
- slide AOI display using normalized bounding boxes from the mock manifest;
- evidence panel showing intent, gaze grid, predicted AOI, confidence, and adaptive strategy;
- confirmation panel for `confirm_one`, `choose_top2`, and `click_required`;
- final tutor response panel after confirmation or direct resolution;
- scenario evaluation panel showing expected vs actual fields;
- JSONL log viewer for recent interactions.

Engineering constraints for this UI stage:

- prefer Streamlit unless a Gradio-specific reason is chosen at goal start;
- keep UI thin: call `modules.system.pipeline.run_interaction` rather than duplicating pipeline logic;
- keep mock providers explicit so Module 1/2 outputs can replace them later;
- do not require API keys;
- ask before installing dependencies if Streamlit/Gradio is not already available;
- ask before starting a long-running dev server if the environment requires approval.

Good checkpoint for this UI stage:

```text
Pause after a local UI can run one scenario, display pending confirmation, accept corrected AOI, and render the final tutor response.
Then decide whether to add evaluation dashboard/log viewer polish or move to system adapter architecture.
```

---

## Important Plan Update: Confirmation-Gated Answering

The next-stage pipeline must distinguish pending-confirmation output from final tutor answering. This is required for the project's Human-Centered AI claim: the system should expose uncertainty and wait for confirmation/correction before generating a final AOI-specific explanation.

If `resolved_query.needs_confirmation is true` and `confirmed_aoi_id is None`:

- do not generate a final AOI-specific explanation;
- return a `TutorResponse` with `response_mode = "pending_confirmation"`;
- `UIState` should show `confirmation_message`, `candidate_targets`, `evidence`, and no final answer yet;
- `log_event` should record `predicted_aoi_id`, `confirmed_aoi_id = None`, and `user_corrected = None`.

If `confirmed_aoi_id` is provided:

- override the predicted AOI for context retrieval;
- generate the final `TutorResponse` using `confirmed_aoi_id`;
- set `user_corrected = true` if `confirmed_aoi_id` differs from `predicted_aoi_id`;
- log both `predicted_aoi_id` and `confirmed_aoi_id`.

If `confirmation_mode = "click_required"`:

- `resolved_aoi_id` should remain `None` unless the user explicitly selects an AOI or chooses `whole_slide`;
- do not silently answer using `whole_slide`.

This update supersedes any earlier wording that implies the tutor should always answer immediately after reference resolution.

---


## 0. Stage Judgment

第一阶段已经证明：

```text
Text Transcript
+ Mock GazePrediction
+ Mock LearningState
+ Mock AOI Manifest
-> IntentResult
-> ResolvedQuery
-> TutorContext
-> TutorResponse
-> InteractionLog
```

下一步不应直接跳到真实 webcam、真实 Whisper 或正式 LLM。更稳妥的下一阶段目标是：

> 把当前五个固定 demo case 扩展成一个 integration-ready local demo layer，让成员 3/4 的逻辑可以被 UI、Module 1 slide output、Module 2 sensing output、后续 STT/LLM client 逐步替换输入源。

也就是说，下一阶段重点不是“增加模型能力”，而是把系统层变成可复用、可检查、可演示、可接入的模块。

---

## 1. Context

### Project Context

AttentiveSlides 是一个 Human-Centered AI slide learning assistant。核心 claim 是：

```text
Look = implicit reference
Speech = explicit learning intent
AI = grounded tutoring response
```

系统必须强调：

- gaze 是 coarse AOI grounding，不是 pixel-level eye tracking；
- learning-state 是 observable signals，不是真实情绪/认知状态判断；
- tutor response 必须基于 slide context；
- target inference 必须显示 confidence / evidence / correction path。

### Current Code Context

已存在：

```text
modules/common/schemas.py
modules/interaction/intent_parser.py
modules/interaction/reference_resolver.py
modules/interaction/adaptive_policy.py
modules/interaction/interaction_history.py
modules/tutor/context_retriever.py
modules/tutor/prompt_template.py
modules/tutor/llm_tutor.py
modules/tutor/tutor_agent.py
modules/logging/interaction_logger.py
scripts/demo_tutor_loop.py
data/mock_deck/mock_aoi_manifest.json
tests/
```

当前 demo 是 fixed-case script。下一步需要把它提升为 reusable pipeline service 和 scenario-driven demo。

### Dependency Context

当前实现只依赖 Python standard library。下一阶段优先保持这个优势，除非进入 UI checkpoint 后明确需要 Streamlit / Gradio。

---

## 2. Request

下一阶段推荐请求可以表述为：

```text
Implement the next integration-ready stage for AttentiveSlides Member 3 and Member 4.

Build a reusable local pipeline around the existing mock-driven logic:
- scenario fixtures instead of hard-coded demo cases
- pipeline service that runs one interaction end-to-end
- CLI demo that can run fixed scenarios and optionally accept text input
- UI state model for later Streamlit/Gradio integration
- stronger tests for confirmation, correction, adaptive policy, and logging
- evaluation skeleton for AOI/reference-resolution behavior

Do not implement real webcam, real Whisper, real slide parser, or full production UI yet.
```

---

## 3. Output

### Required Output For Next Stage

#### 3.1 Reusable Pipeline Service

Add a system-level service, for example:

```text
modules/system/pipeline.py
```

Expected interface:

```python
run_interaction(
    transcript: str,
    gaze_prediction: GazePrediction,
    learning_state: LearningState,
    deck_id: str = "mock_deck",
    slide_id: int = 5,
    confirmed_aoi_id: str | None = None,
    history: InteractionHistory | None = None,
) -> InteractionResult
```

`InteractionResult` should include:

```text
intent_result
resolved_query
tutor_response
log_event
ui_state
```

If adding a new dataclass is useful, add it to `modules/common/schemas.py`.

#### 3.2 Scenario Fixtures

Move demo cases out of `scripts/demo_tutor_loop.py` into structured data:

```text
data/scenarios/member3_4_demo_cases.json
```

Each scenario should include:

```text
name
transcript
gaze_prediction
learning_state
expected.intent
expected.resolved_aoi_id
expected.confirmation_mode
expected.adaptive_strategy
expected.response_mode
```

For scenarios where confirmation is required and no `confirmed_aoi_id` is provided, `expected.response_mode` should be `pending_confirmation`, not `explain` / `quiz` / another final answer mode.

The existing five cases must be preserved:

1. high-confidence explain this
2. summarize whole slide
3. medium-confidence quiz this concept
4. explicit right figure target overriding low gaze confidence
5. low screen-facing score triggering ask_confirmation

#### 3.3 Scenario Runner

Refactor:

```text
scripts/demo_tutor_loop.py
```

so it loads scenario JSON, calls the reusable pipeline service, prints concise results, and writes JSONL logs.

Optional but useful:

```text
scripts/run_interaction_cli.py
```

This can accept text transcript from terminal while still using mock gaze / mock learning-state presets. This is still not real STT.

#### 3.4 UI State Model

Add a UI-friendly output schema. It does not need a full frontend yet.

Suggested dataclass:

```text
UIState
```

Fields:

```text
slide_id
aois
highlighted_aoi_id
confirmation_mode
confirmation_message
candidate_targets
evidence
learning_state_summary
transcript
intent
response
```

This prepares Member 4 for Streamlit/Gradio without committing to a UI framework yet.

#### 3.5 Correction Flow

Add explicit two-step confirmation/correction behavior:

```text
Step 1: pending confirmation
transcript = "解释这个"
predicted_aoi_id = right_figure
confirmation_mode = confirm_one
confirmed_aoi_id = None
-> response_mode = pending_confirmation
-> no final AOI-specific explanation

Step 2: user confirms or corrects
confirmed_aoi_id = bottom_caption
-> TutorContext uses bottom_caption
-> response_mode = explain
-> user_corrected = true
```

This is important because the Human-Centered AI claim depends on user confirmation/correction, not just prediction.

#### 3.6 Evaluation Skeleton

Add lightweight evaluation scripts:

```text
evaluation/eval_reference_resolution.py
evaluation/eval_scenario_outputs.py
```

Minimum metrics:

```text
intent_accuracy
resolved_aoi_accuracy
confirmation_mode_accuracy
adaptive_strategy_accuracy
```

These can run on `data/scenarios/member3_4_demo_cases.json` first.

#### 3.7 Tests

Add or extend tests for:

```text
pipeline service returns full InteractionResult
scenario fixture loading
all five demo scenarios match expected fields
needs_confirmation without confirmed_aoi_id returns pending_confirmation
correction overrides predicted AOI
click_required produces unresolved target and safe tutor response
JSONL logging includes confirmed_aoi_id and user_corrected
UIState contains evidence and confirmation mode
```

Expected verification commands:

```bash
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
python evaluation/eval_reference_resolution.py
```

---

## 4. Constraints

### Technical Constraints

- Do not implement real webcam capture in this stage.
- Do not implement real Whisper / faster-whisper in this stage.
- Do not implement real slide parser or OCR in this stage.
- Do not require API keys for tests or demo.
- Do not make Streamlit / Gradio a hard dependency before a checkpoint confirmation.
- Do not introduce a general autonomous agent framework.
- Do not break existing interfaces without updating tests and this plan.
- Keep all tests runnable with standard library unless a dependency is explicitly approved.

### HAI / Claim Constraints

- Do not claim true attention, true fatigue, true confusion, or true emotion.
- Use language like `observable learning-state signals`, `screen-facing score`, `possible review-needed signal`.
- Keep uncertainty visible through `confirmation_mode`, `target_confidence`, `evidence`, and `alternative_targets`.
- If target confidence is low, do not silently answer as if the target is known.
- Tutor answers must remain slide-grounded and should mark any external background explicitly.

### Repository Constraints

- Preserve the three original planning Markdown files.
- Keep generated logs ignored under `data/logs/*.jsonl`.
- Do not remove `.gitkeep` files unless replacing them with tracked content in the same directory.
- Commit/push only after tests pass, unless the user asks for an intermediate checkpoint commit.

---

## 5. Checkpoints

### Checkpoint A: Core Integration Service Complete

Pause is optional here. It is safe to continue without asking if:

- `modules/system/pipeline.py` exists;
- scenario JSON exists;
- `scripts/demo_tutor_loop.py` runs from scenario JSON;
- tests pass.

Evidence:

```bash
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
```

Recommended action: continue to evaluation skeleton if no design conflict appears.

### Checkpoint B: Evaluation Skeleton Complete

Pause is optional here. It is safe to continue without asking if:

- `evaluation/eval_reference_resolution.py` exists;
- it reports metrics for scenario fixtures;
- no external dependency is required.

Evidence:

```bash
python evaluation/eval_reference_resolution.py
```

Recommended action: commit and push if tests pass.

### Checkpoint C: Before Adding UI Framework

Pause and ask user before:

- installing Streamlit / Gradio;
- adding `requirements.txt` entries that require network installation;
- changing the app into a framework-specific frontend;
- starting a local dev server as part of implementation.

Question to ask:

```text
Do you want the next UI checkpoint to use Streamlit, Gradio, or stay CLI/mock-only for now?
```

Recommended default if no answer: stay CLI/mock-only.

### Checkpoint D: Before Real STT / LLM / Webcam

Pause and ask user before:

- using OpenAI/Gemini API keys;
- installing or running faster-whisper;
- accessing microphone or webcam;
- connecting to the Lenovo 4060 Linux laptop;
- introducing model downloads or GPU-specific setup.

Reason: these choices affect environment, privacy, runtime, and demo machine assumptions.

### Checkpoint E: Before Schema-Breaking Changes

Pause and ask user before changing meanings of:

```text
AOI
GazePrediction
LearningState
IntentResult
ResolvedQuery
TutorContext
TutorResponse
InteractionLogEvent
```

Safe additions are fine. Breaking field names or semantics should be confirmed because Modules 1/2 will later integrate against these contracts.

### Checkpoint F: Before Irreversible Or Broad Operations

Pause and ask user before:

- deleting original planning documents;
- rewriting large repo structure;
- force-pushing;
- removing pushed commits;
- adding large binary assets;
- committing credentials, logs with private data, or generated model files.

---

## 6. Recommended Next Goal Mode Scope

For the next goal-mode run, the best concrete target is:

```text
Build the integration-ready Member 3/4 pipeline layer:
scenario fixtures, reusable run_interaction service, UIState schema,
correction flow, scenario runner, evaluation skeleton, tests, commit, and push.
Stop before adding Streamlit/Gradio, real STT, real webcam, or real LLM unless explicitly approved.
```

This target is far enough to move the project materially forward, but stops before environment-heavy or design-sensitive decisions.

---

## 7. Likely Implementation Order

1. Inspect current state and run current tests.
2. Add `modules/system/` package and `run_interaction` service.
3. Add `InteractionResult` and `UIState` dataclasses if needed.
4. Move five demo cases into `data/scenarios/member3_4_demo_cases.json`.
5. Refactor `scripts/demo_tutor_loop.py` to load scenarios.
6. Implement correction path with `confirmed_aoi_id`.
7. Add evaluation script for scenario outputs.
8. Add tests for pipeline, scenarios, correction, UI state, and evaluation behavior.
9. Run verification commands.
10. Commit and push if clean.

---

## 8. Member-Specific Responsibilities

### Member 3 Next Tasks

- Make intent/reference/adaptive logic callable through `run_interaction`.
- Ensure explicit target, gaze target, whole slide, and click-required paths remain stable.
- Add correction-aware reference handling.
- Expand test coverage for bilingual intent and deictic references.
- Keep evidence strings useful for UI display and report discussion.

### Member 4 Next Tasks

- Convert current script flow into reusable system integration.
- Add UI state schema without committing to frontend framework yet.
- Keep TutorAgent task-bounded and slide-grounded.
- Add scenario evaluation scripts for report-ready metrics.
- Ensure JSONL logs record prediction, confirmation, correction, response mode, and latency.

---

## 9. Definition Of Done For Next Stage

The next stage is complete when:

- all scenario cases live in structured fixture data;
- one reusable pipeline function runs a full interaction end to end;
- correction flow is represented in code, logs, tests, and UI state;
- evaluation script reports scenario-level metrics;
- tests pass with standard library only;
- demo script still runs from the project root;
- no real webcam/STT/LLM/UI framework is required;
- changes are committed and pushed to `origin/main`.
