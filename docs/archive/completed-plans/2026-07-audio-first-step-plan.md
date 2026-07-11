# AttentiveSlides Audio Usability Next Stage Plan

> Scope: Member 3 `Voice / Intent / Multimodal Fusion`, with the minimum UI work needed for Member 4 integration.
> Current goal: make the audio path usable in the real demo, not just evaluated offline.
> Implementation mode for future goal sessions: use `executing-plans` or equivalent task-by-task execution, and keep default tests independent of microphone, CUDA, downloaded models, and real audio.

---

## Why The Plan Changed

The public audio evaluation stage proved that real audio can pass through:

```text
audio file
-> faster-whisper STT
-> Transcript
-> adapter bundle
-> intent/reference/tutor pipeline
```

That stage also produced `mean_cer = 0.5022` on 10 `PolyAI/minds14` `zh-CN` samples with `faster-whisper small`, CUDA, and `int8_float16`.

This high CER is not the most important blocker now because the dataset is not AttentiveSlides command audio. The project needs a usable learning interaction:

```text
click record
-> speak a short learning command
-> see/edit transcript
-> resolve intent + AOI
-> confirm/correct target
-> get tutor response
```

Do not spend the next stage optimizing public-dataset metrics. Focus on real demo usability.

---

## Current Repository State

Already implemented:

- `modules/audio/` contains the STT protocol, config, mock transcriber, and lazy `faster-whisper` transcriber.
- `modules/interaction/speech_to_text.py` exposes `transcribe_audio(audio_path, config=None) -> Transcript`.
- `modules/system/audio_adapters.py` exposes `AudioFileTranscriptProvider`.
- `scripts/transcribe_audio_file.py` runs audio -> `Transcript` JSON.
- `scripts/demo_audio_to_tutor_loop.py` runs audio -> `Transcript` -> existing adapter bundle -> `InteractionResult`.
- `evaluation/eval_audio_pipeline.py` can evaluate manifest audio through real or mock STT.
- `apps/streamlit_demo.py` already renders transcript, mock gaze, confirmation/correction, and tutor response.
- Default unit tests pass without real audio, microphone, CUDA, `datasets`, or `faster-whisper`.

Explicitly not done yet:

- Streamlit push-to-talk / upload-recorded-audio UI.
- Recording from local microphone.
- Transcript edit-and-submit flow after STT.
- Model selection / fallback for `medium` and `large-v3`.
- Remote benchmark of `medium` and `large-v3` on project-style short Chinese commands.
- Streaming ASR.
- STT model fine-tuning.

---

## Remote 4060 / Model Capacity

Remote host:

```text
SSH config host: LenovoLinux_Dorm
OS: Ubuntu
conda env: pyboe
GPU: NVIDIA GeForce RTX 4060 Laptop GPU
VRAM: 8188 MiB total
Observed free VRAM on 2026-07-10: about 7182 MiB
Driver: 595.71.05
Cached model observed: Systran/faster-whisper-small
```

Environment setup:

```bash
source /home/charles/miniconda3/etc/profile.d/conda.sh
conda activate pyboe
export HF_ENDPOINT=https://hf-mirror.com
```

Official resource references:

- OpenAI Whisper README lists approximate original Whisper VRAM as `medium ~5GB`, `large ~10GB`, and `turbo ~6GB`.
- `faster-whisper` README reports a large-v2 GPU benchmark on an 8GB RTX 3070 Ti where `faster-whisper int8` used about `2926MB` VRAM, and `faster-whisper fp16` used about `4525MB` VRAM for the benchmark settings.
- `faster-whisper` README also shows `large-v3` usage with `compute_type="float16"` or `compute_type="int8_float16"`.

Capacity decision:

- `medium` on the 4060 8GB is expected to fit comfortably and should be the stable default for interactive demo work.
- `large-v3` should be tested with `compute_type=int8_float16`, no batching, short recordings, and `beam_size=1` or `beam_size=3`.
- `large-v3 float16` may fit according to faster-whisper's large-v2 benchmark, but `int8_float16` is the safer first deployment setting on an 8GB laptop GPU.
- If `large-v3` cold load or transcription causes out-of-memory or unacceptable latency, the app must fall back to `medium`.
- Fine-tuning is not justified unless `large-v3` and `medium` both fail on clean project-specific short commands.

Recommended model policy:

```text
interactive_default: medium / cuda / int8_float16 / beam_size=1 / language=zh
accuracy_candidate: large-v3 / cuda / int8_float16 / beam_size=1 / language=zh
fallback: small / cuda / int8_float16 / beam_size=1 / language=zh
cpu_fallback: small / cpu / int8 / beam_size=1 / language=zh
```

---

## Next Stage Goal

Build a usable non-streaming voice interaction loop:

```text
Streamlit audio input or local recording script
-> save wav under gitignored data/audio_samples/recorded/
-> transcribe with selected faster-whisper model
-> show transcript to user
-> allow transcript correction before submission
-> run existing adapter pipeline with current/mock gaze state
-> show AOI confirmation/correction
-> show grounded tutor response
```

This is push-to-talk / record-then-transcribe. Do not implement streaming ASR in this stage.

---

## Design Principles

1. Usability over benchmark depth.
   The user should be able to try the demo with real speech within one screen.

2. Human correction is part of the product.
   If STT makes a small mistake, the transcript text box must allow correction before intent parsing.

3. Keep model risk isolated.
   The UI should accept model settings but default to `medium`; failed `large-v3` runs should not break the rest of the demo.

4. Preserve existing contracts.
   Do not change `Transcript` fields. Keep `Transcript(text, language, confidence)` unchanged.

5. Keep default tests light.
   Unit tests must use mock transcribers and temporary files. They must not require microphone access, real model downloads, CUDA, or Hugging Face.

6. Do not fine-tune now.
   Use better pretrained models, language forcing, short-command normalization, and transcript editing before considering training.

---

## Planned Files

Create:

```text
modules/audio/recording.py
modules/audio/model_policy.py
scripts/record_audio_file.py
tests/test_audio_recording.py
tests/test_audio_model_policy.py
```

Modify:

```text
apps/streamlit_demo.py
modules/audio/faster_whisper_transcriber.py
modules/audio/transcriber.py
scripts/demo_audio_to_tutor_loop.py
scripts/transcribe_audio_file.py
requirements-audio.txt
docs/audio_deployment.md
PROJECT_PROGRESS.md
```

Optional if implementation gets large:

```text
modules/system/audio_demo_view_model.py
tests/test_audio_demo_view_model.py
```

Generated local artifacts must remain gitignored:

```text
data/audio_samples/recorded/
data/audio_eval/
```

---

## Task 1: Add Model Policy And Fallback Defaults

Goal: centralize recommended STT settings so CLI and Streamlit use the same defaults.

Implementation:

- Create `modules/audio/model_policy.py`.
- Define named profiles:
  - `fast`: `small`, `cuda`, `int8_float16`, `beam_size=1`, `language="zh"`.
  - `balanced`: `medium`, `cuda`, `int8_float16`, `beam_size=1`, `language="zh"`.
  - `accurate`: `large-v3`, `cuda`, `int8_float16`, `beam_size=1`, `language="zh"`.
  - `cpu`: `small`, `cpu`, `int8`, `beam_size=1`, `language="zh"`.
- Add a helper:

```python
def transcription_config_for_profile(profile: str) -> TranscriptionConfig:
    ...
```

- Add tests that assert exact config fields and unknown-profile errors.

Acceptance:

```bash
python -m unittest tests.test_audio_model_policy -v
python -m unittest discover -s tests -v
```

---

## Task 2: Add Local Recording Utility

Goal: support record-then-transcribe without adding streaming complexity.

Implementation:

- Add optional recording dependency to `requirements-audio.txt`.
- Preferred package: `sounddevice`.
- Create `modules/audio/recording.py`.
- Provide:

```python
def record_wav(output_path: str, duration_sec: float, sample_rate: int = 16000) -> str:
    ...
```

Behavior:

- Lazy import `sounddevice` and `soundfile`.
- Raise a clear `RuntimeError` if recording dependencies are missing.
- Create parent directory automatically.
- Record mono 16 kHz wav.
- Return the saved path.
- Do not import recording dependencies during normal module import.

Tests:

- Mock `sounddevice.rec`, `sounddevice.wait`, and `soundfile.write`.
- Verify parent directory creation, sample rate, mono channel shape, and output path.
- Verify missing dependency error message.

Acceptance:

```bash
python -m unittest tests.test_audio_recording -v
python -m unittest discover -s tests -v
```

---

## Task 3: Add Recording CLI Smoke Tool

Goal: allow terminal-level microphone smoke tests before UI integration.

Implementation:

- Create `scripts/record_audio_file.py`.
- Arguments:
  - `--output`, default `data/audio_samples/recorded/latest.wav`
  - `--duration`, default `4.0`
  - `--sample-rate`, default `16000`
- Print JSON:

```json
{
  "audio_path": "data/audio_samples/recorded/latest.wav",
  "duration_sec": 4.0,
  "sample_rate": 16000
}
```

Acceptance:

```bash
python scripts/record_audio_file.py --duration 3 --output data/audio_samples/recorded/smoke.wav
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --model medium \
  --device cuda \
  --compute-type int8_float16 \
  --language zh
```

The command should transcribe a short Chinese command such as `解释这个`.

---

## Task 4: Make CLI Model Selection Match The Policy

Goal: make existing CLI scripts easier to use with larger models.

Implementation:

- Add `--profile {fast,balanced,accurate,cpu}` to:
  - `scripts/transcribe_audio_file.py`
  - `scripts/demo_audio_to_tutor_loop.py`
- Keep explicit `--model`, `--device`, `--compute-type`, `--language`, and `--beam-size` overrides.
- Default profile should be `balanced`.
- If both profile and explicit flags are provided, explicit flags win.

Acceptance:

```bash
python scripts/transcribe_audio_file.py --audio data/audio_samples/explain_this.wav --engine mock
python scripts/demo_audio_to_tutor_loop.py \
  --audio data/audio_samples/right_figure.wav \
  --engine mock \
  --sensing-preset high_confidence_right_figure
python -m unittest discover -s tests -v
```

Remote real command:

```bash
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --profile accurate
```

---

## Task 5: Add Streamlit Audio Input Mode

Goal: make the demo usable from the UI with a real voice path.

Implementation:

- In `apps/streamlit_demo.py`, add an input mode selector:
  - `Mock scenario text`
  - `Audio file upload`
  - `Recorded wav path`
- Use `st.audio_input` if available in the installed Streamlit version.
- If `st.audio_input` is unavailable, show a file uploader and a text field for a wav path.
- Save uploaded/recorded audio under `data/audio_samples/recorded/`.
- Add model profile selector:
  - `balanced (medium)`
  - `accurate (large-v3)`
  - `fast (small)`
  - `cpu fallback`
- Add a `Transcribe audio` button.
- After transcription, populate the existing learner utterance text area.
- Let the user edit the transcript before running the pipeline.
- Keep existing mock gaze controls and confirmation/correction flow.

Important:

- Do not transcribe repeatedly on every Streamlit rerun.
- Store latest audio path, transcript text, model profile, and error state in `st.session_state`.
- Surface model load or CUDA errors in the UI with a clear fallback suggestion.

Acceptance:

```bash
python -m streamlit run apps/streamlit_demo.py \
  --server.headless true \
  --server.port 8501 \
  --browser.gatherUsageStats false
```

Manual UI smoke:

1. Open the app.
2. Select audio mode.
3. Record or upload a wav saying `解释这个`.
4. Click `Transcribe audio`.
5. Confirm/edit transcript.
6. Confirm AOI.
7. See tutor response.

---

## Task 6: Remote Model Deployment And Benchmark

Goal: verify which model should be used by default for the final demo.

Run on `LenovoLinux_Dorm`:

```bash
cd /home/charles/attentive_slides_eval_work
source /home/charles/miniconda3/etc/profile.d/conda.sh
conda activate pyboe
export HF_ENDPOINT=https://hf-mirror.com
```

First verify GPU:

```bash
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,driver_version --format=csv,noheader
```

Expected:

```text
NVIDIA GeForce RTX 4060 Laptop GPU, about 8188 MiB total
```

Then test model load and one short command audio:

```bash
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --model medium \
  --device cuda \
  --compute-type int8_float16 \
  --language zh \
  --beam-size 1
```

Then:

```bash
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --model large-v3 \
  --device cuda \
  --compute-type int8_float16 \
  --language zh \
  --beam-size 1
```

Decision rule:

- If `large-v3` loads, transcribes short commands reliably, and latency is acceptable for demo use, use `accurate` profile for final demo.
- If `large-v3` is slow or unstable, use `balanced` profile (`medium`) as default and keep `accurate` as an advanced option.
- If both fail, use `fast` (`small`) only as fallback and consider a different pretrained ASR provider before considering fine-tuning.

Record these in `PROJECT_PROGRESS.md` after the actual remote run:

```text
model
compute_type
free VRAM before load
peak/observed used VRAM after load
transcript for 3-5 project commands
latency
default/fallback decision
```

---

## Task 7: Project-Specific Usability Smoke Set

Goal: test system usability with realistic AttentiveSlides commands without turning this into a large evaluation project.

Create 8-12 short spoken commands manually:

```text
解释这个
讲讲右边这个图
这个图是什么意思
总结这一页
考我一下这个概念
一步一步解释这个公式
这个和上一个有什么区别
我该复习哪里
讲简单一点
```

Use these only as a smoke set:

- Are transcripts understandable enough?
- Does intent parsing work after minor STT variation?
- Does deictic reference trigger AOI confirmation?
- Can the user fix transcript errors before submission?
- Does tutor response appear after AOI confirmation?

Do not fine-tune on this set. Do not claim statistical ASR performance from this set.

---

## Task 8: Update Documentation And Progress

Update:

- `docs/audio_deployment.md`
- `PROJECT_PROGRESS.md`

Document:

- recommended default model;
- fallback policy;
- how to run recording CLI;
- how to run Streamlit audio mode;
- remote 4060 result;
- remaining non-scope.

Keep explicit privacy notes:

- no raw microphone audio is committed;
- recorded wav files stay local and gitignored;
- UI should make it clear that microphone use is user-triggered;
- no wake word or background listening in this stage.

---

## Non-Scope For This Stage

Do not implement:

- streaming ASR;
- wake word detection;
- continuous background microphone listening;
- diarization;
- FunASR migration;
- ASR fine-tuning;
- cloud ASR API dependency;
- changes to the `Transcript` schema;
- committing private recordings, generated manifests, or downloaded model weights.

---

## Final Acceptance Criteria

Local:

```bash
python -m unittest discover -s tests -v
python scripts/transcribe_audio_file.py --audio data/audio_samples/explain_this.wav --engine mock
python scripts/demo_audio_to_tutor_loop.py \
  --audio data/audio_samples/right_figure.wav \
  --engine mock \
  --sensing-preset high_confidence_right_figure
python -m streamlit run apps/streamlit_demo.py \
  --server.headless true \
  --server.port 8501 \
  --browser.gatherUsageStats false
```

Remote:

```bash
source /home/charles/miniconda3/etc/profile.d/conda.sh
conda activate pyboe
export HF_ENDPOINT=https://hf-mirror.com
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --profile balanced
python scripts/transcribe_audio_file.py \
  --audio data/audio_samples/recorded/smoke.wav \
  --engine faster_whisper \
  --profile accurate
```

Manual usability:

- The user can record or upload one short command in the UI.
- The UI transcribes it with `medium` or `large-v3`.
- The transcript is visible and editable before pipeline submission.
- The existing gaze/AOI confirmation flow still works.
- The tutor response appears after confirmation.
- If `large-v3` fails, the UI gives a clear fallback path to `medium`.

