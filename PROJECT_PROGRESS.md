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

### Member 3 File-Based Audio / STT Integration

Completed:

- `modules/audio/` defines the STT protocol, transcription config, deterministic mock transcriber, and lazy `faster-whisper` transcriber.
- `modules/interaction/speech_to_text.py` exposes `transcribe_audio(audio_path, config=None) -> Transcript`.
- `modules/system/audio_adapters.py` provides `AudioFileTranscriptProvider` for the existing adapter bundle path.
- `scripts/transcribe_audio_file.py` outputs audio-to-`Transcript` JSON.
- `scripts/demo_audio_to_tutor_loop.py` runs audio file -> `Transcript` -> existing adapter bundle -> `InteractionResult`.
- `requirements-audio.txt` keeps `faster-whisper` out of the base dependencies.
- `docs/audio_deployment.md` documents local mock usage, Linux + 4060 settings, CPU fallback, and LenovoLinux_Dorm environment details.
- `data/audio_samples/` is gitignored except for README and `.gitkeep`, so private recordings stay local.

Key behavior now implemented:

- Mock audio filenames map to Chinese STT transcripts for default tests and dry-run demos.
- Real `faster-whisper` import/model loading is lazy and does not break ordinary imports or unit tests.
- Missing audio files fail with a clear `FileNotFoundError` before model loading.
- `Transcript` remains unchanged with only `text`, `language`, and `confidence`.
- Whisper language probability is not treated as transcript confidence; first-stage confidence remains `None`.
- STT-induced Chinese variants such as `讲讲右边这个图` and `这个图是什么意思` are covered by intent parser tests.

Remote verification:

- `faster-whisper==1.2.1` was installed into LenovoLinux_Dorm `pyboe`.
- `HF_ENDPOINT=https://hf-mirror.com` successfully loaded `faster-whisper` `small` on CUDA with `compute_type=int8_float16`.
- A temporary silence wav transcribe smoke returned language `zh` and completed without GPU/runtime errors.

### Member 3 Public Audio Evaluation Harness

Completed:

- `scripts/prepare_audio_eval_samples.py` downloads a small public `PolyAI/minds14` `zh-CN` sample set and writes a local manifest.
- `evaluation/eval_audio_pipeline.py` evaluates manifest audio through STT and the existing adapter pipeline.
- `requirements-audio-eval.txt` keeps optional evaluation dependencies separate from default tests.
- `data/audio_eval/` is gitignored except for README and `.gitkeep`.
- `attentive_slides_audio_first_step_plan.md` now records the next-stage audio evaluation plan and remote run notes.

Key behavior now implemented:

- Public audio evaluation records expected transcript, actual transcript, CER, latency, intent, resolved AOI, confirmation mode, response mode, and pipeline success.
- Default tests still use mock audio only and do not require real audio, CUDA, `datasets`, or `faster-whisper`.
- The downloader uses `datasets` with `Audio(decode=False)` to avoid the heavy `datasets[audio]` / `torchcodec` dependency path.

Remote verification:

- On `LenovoLinux_Dorm`, `pyboe` installed `soundfile` and used existing `datasets`.
- `HF_ENDPOINT=https://hf-mirror.com` was used for Hugging Face access.
- 10 `PolyAI/minds14` `zh-CN` samples were downloaded to the remote local eval directory.
- `faster-whisper` `small`, `device=cuda`, `compute_type=int8_float16`, `language=zh` evaluated all 10 samples.
- Remote eval result: `pipeline_success_count = 10`, `transcript_usable_rate = 1.0`, `mean_cer = 0.5022`, `mean_latency_ms = 551.54`.

### Member 3 Audio Usability Loop

Completed:

- `modules/audio/model_policy.py` centralizes `fast`, `balanced`, `accurate`, and `cpu` transcription profiles.
- `modules/audio/recording.py` provides lazy optional microphone recording through `sounddevice` + `soundfile`.
- `scripts/record_audio_file.py` records short local wav files under the gitignored audio sample path.
- `scripts/transcribe_audio_file.py` and `scripts/demo_audio_to_tutor_loop.py` support `--profile`, with explicit model/device/compute/language/beam overrides still taking precedence.
- `apps/streamlit_demo.py` now offers `Mock scenario text`, `Audio file upload`, and `Recorded wav path` input modes.
- Streamlit audio transcription is manually triggered with `Transcribe audio`, writes the transcript into the editable learner utterance box, then continues through the existing gaze/AOI confirmation and tutor-response flow.
- `docs/audio_usability_smoke_phrases.md` lists the project-specific short phrases needed for manual usability recordings.

Key behavior now implemented:

- Default interactive STT profile is `balanced`: `medium`, `cuda`, `int8_float16`, `beam_size=1`, `language=zh`.
- Accuracy candidate is `accurate`: `large-v3`, `cuda`, `int8_float16`, `beam_size=1`, `language=zh`.
- CPU fallback is `small`, `cpu`, `int8`.
- Default unit tests remain independent of microphone access, CUDA, downloaded models, `datasets`, and `faster-whisper`.
- Private recorded audio remains local and ignored by git.

Remote verification:

- On 2026-07-10, `LenovoLinux_Dorm` reported NVIDIA GeForce RTX 4060 Laptop GPU, `8188 MiB` total VRAM, `602 MiB` used, `7182 MiB` free, driver `595.71.05`.
- Only `faster-whisper-small` was cached before the new model checks.
- `medium`, `device=cuda`, `compute_type=int8_float16`, `language=zh`, `beam_size=1` successfully transcribed one existing public `minds14` sample. The first run took about `550s`, mainly due to model download/cache time.
- `large-v3`, `device=cuda`, `compute_type=int8_float16`, `language=zh`, `beam_size=1` successfully transcribed the same public `minds14` sample. The first run took about `1519s`, mainly due to model download/cache time.
- After caching, separate CLI-process sanity checks took about `5.30s` for `medium` and `4.58s` for `large-v3` on the same public sample.
- The new remote CLI accepted `--profile balanced` and `--profile accurate`; both profile commands mapped to the expected model/device/compute settings.
- No project-specific user recording exists yet on local or remote disk; `docs/audio_usability_smoke_phrases.md` lists the phrases to record next.

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

The latest verified commands from the audio/STT implementation stage:

```bash
python -m unittest discover -s tests -v
python scripts/transcribe_audio_file.py --audio data/audio_samples/explain_this.wav --engine mock
python scripts/demo_audio_to_tutor_loop.py --audio data/audio_samples/right_figure.wav --engine mock --sensing-preset high_confidence_right_figure
```

Observed results:

- Unit test suite passed: 51 tests.
- Mock transcription JSON returned `text = "解释一下这个"`, `language = "zh"`, `confidence = null`.
- Mock audio-to-tutor demo resolved `讲讲右边这个图` to intent `explain`, AOI `right_figure`, response mode `explain`.
- Remote LenovoLinux_Dorm `pyboe` GPU smoke loaded `small` CUDA/int8_float16 and transcribed a temporary silence wav.

The latest verified commands from the public audio evaluation stage:

```bash
python -m unittest discover -s tests -v
python evaluation/eval_audio_pipeline.py --manifest tests/fixtures/audio_eval_manifest.json --engine mock
```

Observed results:

- Unit test suite passed: 57 tests.
- Mock audio eval reported `case_count = 2`, `pipeline_success_count = 2`, `transcript_usable_rate = 1.0`, `mean_cer = 0.0`.

Remote LenovoLinux_Dorm commands:

```bash
source /home/charles/miniconda3/etc/profile.d/conda.sh
conda activate pyboe
export HF_ENDPOINT=https://hf-mirror.com
python -m pip install -r requirements-audio-eval.txt
python scripts/prepare_audio_eval_samples.py --limit 10
python evaluation/eval_audio_pipeline.py \
  --manifest data/audio_eval/minds14_zh_cn/manifest.json \
  --engine faster_whisper \
  --model small \
  --device cuda \
  --compute-type int8_float16 \
  --language zh
```

Observed remote results:

- Public `PolyAI/minds14` `zh-CN` download produced 10 manifest cases.
- Real STT eval completed with `pipeline_success_count = 10`, `transcript_usable_rate = 1.0`, `mean_cer = 0.5022`, `mean_latency_ms = 551.54`.

The latest verified commands from the audio usability stage:

```bash
python -m unittest discover -s tests -v
python scripts/transcribe_audio_file.py --audio data/audio_samples/explain_this.wav --engine mock --profile balanced
python scripts/demo_audio_to_tutor_loop.py --audio data/audio_samples/right_figure.wav --engine mock --profile fast --sensing-preset high_confidence_right_figure
python -m streamlit run apps/streamlit_demo.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
```

Observed results:

- Unit test suite passed: 69 tests.
- Mock profile CLI paths completed without real audio files.
- Streamlit started successfully at `http://localhost:8501` in headless mode and was stopped after the smoke check.
- Remote profile checks on `LenovoLinux_Dorm` completed with cached `medium` and `large-v3` using an existing public `minds14` sample.

## Current Explicit Non-Scope

Not implemented yet:

- Real webcam or eye-tracking input.
- Streaming ASR.
- Real user-recorded audio sample evaluation on the project-specific smoke phrases.
- Real LLM client or API-key-dependent generation.
- Live Module 1 slide-processing interface.
- Live Module 2 sensing interface.

Current implementation remains mock-driven for default tests, with optional
record-then-transcribe `faster-whisper` paths for real audio.

## Useful Next Engineering Questions

For engineering optimization work, inspect these areas first:

- Whether `apps/streamlit_demo.py` should be split into smaller UI components before adding more panels.
- Whether `modules/system/demo_view_model.py` should become the boundary for future UI-independent contract tests.
- How real Module 1/2 outputs should map into the new protocol-style adapter interfaces once field names/formats are available.
- Whether log files under `data/logs/` should stay untracked runtime artifacts.

## Git State Note

The Streamlit UI demo and adapter execution plan were committed and pushed in commit `d51beb7`.
